import argparse
import csv
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CSV_FIELDS = [
    "song_id", "title", "artist", "reason",
    "candidate_title", "candidate_artists", "album",
    "release_date", "spotify_url", "spotify_track_id",
    "selection",
]


def normalize(text):
    text = (text or "").casefold().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("&", " and ")
    text = re.sub(r"\b(feat|ft|featuring)\b.*$", "", text)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def split_artists(text):
    return [
        normalize(part)
        for part in (text or "").split(",")
        if normalize(part)
    ]


def get_access_token():
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "Spotify credentials missing. Check backend/.env."
        )

    response = requests.post(
        "https://accounts.spotify.com/api/token",
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
        timeout=20,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Spotify authentication failed: HTTP {response.status_code}. "
            f"{response.text[:250]}"
        )

    return response.json()["access_token"]


def spotify_search(session, token, query):
    params = {
        "q": query,
        "type": "track",
        "limit": 10,
        "market": "US",
    }
    headers = {"Authorization": f"Bearer {token}"}

    response = session.get(
        "https://api.spotify.com/v1/search",
        headers=headers,
        params=params,
        timeout=20,
    )

    if response.status_code == 429:
        body = response.text[:500]

        if "QUOTA_EXCEEDED" in body.upper():
                raise RuntimeError(
                "Spotify development quota exceeded.\n"
                f"Spotify response: {body}\n"
                "Progress has been saved."
            )

        try:
            wait = int(response.headers.get("Retry-After", "5"))
        except ValueError:
            wait = 5

        wait = max(1, min(wait, 60))
        print(f"  Spotify rate limit. Waiting {wait} seconds...")
        time.sleep(wait)

        response = session.get(
            "https://api.spotify.com/v1/search",
            headers=headers,
            params=params,
            timeout=20,
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Spotify search failed: HTTP {response.status_code}. "
            f"Response: {response.text[:250]}"
        )

    return response.json().get("tracks", {}).get("items", [])


def search_spotify(session, token, title, artist):
    queries = []

    for part in (artist or "").split(","):
        part = part.strip()
        if part:
            queries.append(f'track:"{title}" artist:"{part}"')

    queries.append(f'track:"{title}"')

    found = {}

    for query in queries:
        for track in spotify_search(session, token, query):
            if track.get("id"):
                found[track["id"]] = track

        time.sleep(0.15)

    return list(found.values())


def artist_credits_match(wanted_artists, track):
    credits = {
        normalize(item.get("name", ""))
        for item in track.get("artists", [])
    }

    return bool(wanted_artists) and all(
        artist in credits for artist in wanted_artists
    )


def find_exact_matches(title, artist, tracks):
    wanted_title = normalize(title)

    title_matches = [
        track for track in tracks
        if normalize(track.get("name", "")) == wanted_title
    ]

    exact_matches = [
        track for track in title_matches
        if artist_credits_match(split_artists(artist), track)
    ]

    return title_matches, exact_matches


def candidate_details(track):
    album = track.get("album") or {}

    return {
        "candidate_title": track.get("name", ""),
        "candidate_artists": ", ".join(
            item.get("name", "")
            for item in track.get("artists", [])
        ),
        "album": album.get("name", ""),
        "release_date": album.get("release_date", ""),
        "spotify_url": (
            track.get("external_urls") or {}
        ).get("spotify", ""),
        "spotify_track_id": track.get("id", ""),
    }


def open_database(db_path):
    if not db_path.is_file():
        sys.exit(f"ERROR: Database file not found: {db_path}")

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row

    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(song)")
    }

    required = {
        "id", "title", "artist", "spotify_url", "spotify_track_id"
    }

    if not required.issubset(columns):
        connection.close()
        sys.exit(
            "ERROR: song table is missing required columns. "
            f"Found: {', '.join(sorted(columns))}"
        )

    return connection


def get_report_path(db_path):
    return db_path.with_name("spotify_unmatched_review.csv")


def read_checkpoint(report):
    """Load prior results and preserve manual selections."""
    by_song = {}
    selections = {}

    if not report.exists():
        return by_song, selections

    try:
        with report.open(
            "r", newline="", encoding="utf-8-sig"
        ) as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames or not {
                "song_id", "selection"
            }.issubset(reader.fieldnames):
                sys.exit(
                    "ERROR: Existing CSV is missing required columns. "
                    "Make a backup and inspect it before continuing."
                )

            for original in reader:
                song_id = (original.get("song_id") or "").strip()

                if not song_id:
                    continue

                row = {
                    field: original.get(field, "") or ""
                    for field in CSV_FIELDS
                }

                by_song.setdefault(song_id, []).append(row)

                choice = row["selection"].strip()
                track_id = row["spotify_track_id"]

                if choice:
                    selections.setdefault(song_id, {})[
                        track_id
                    ] = choice

    except (OSError, csv.Error) as error:
        sys.exit(f"ERROR: Could not read checkpoint CSV: {error}")

    return by_song, selections


def write_checkpoint(report, rows):
    """Write to a temporary file, then atomically replace the CSV."""
    temp = report.with_suffix(report.suffix + ".tmp")

    try:
        with temp.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=CSV_FIELDS,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())

        temp.replace(report)

    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def review_songs(connection, db_path, limit):
    songs = connection.execute("""
        SELECT id, title, artist
        FROM song
        WHERE (spotify_url IS NULL OR TRIM(spotify_url) = '')
          AND (spotify_track_id IS NULL OR TRIM(spotify_track_id) = '')
        ORDER BY id
    """).fetchall()

    report = get_report_path(db_path)
    old_rows, selections = read_checkpoint(report)

    # A non-empty reason means the song finished its search.
    completed = {
        song_id
        for song_id, rows in old_rows.items()
        if rows and any(row.get("reason", "").strip() for row in rows)
    }

    pending = [
        song for song in songs
        if str(song["id"]) not in completed
    ]

    if limit:
        pending = pending[:limit]

    song_order = [str(song["id"]) for song in songs]

    for song_id in old_rows:
        if song_id not in song_order:
            song_order.append(song_id)

    def all_rows():
        output = []

        for song_id in song_order:
            for original in old_rows.get(song_id, []):
                row = dict(original)
                track_id = row.get("spotify_track_id", "")
                saved_choice = selections.get(
                    song_id, {}
                ).get(track_id, "")

                if saved_choice:
                    row["selection"] = saved_choice

                output.append(row)

        return output

    # Create the CSV before making any Spotify requests.
    try:
        write_checkpoint(report, all_rows())
    except OSError as error:
        sys.exit(f"ERROR: Could not create CSV checkpoint: {error}")

    print(f"Database: {db_path}")
    print(f"Songs remaining to search: {len(pending)}")
    print(f"Previously completed songs: {len(completed)}")
    print("Mode: REVIEW ONLY — no database updates")
    print(f"Checkpoint CSV: {report}\n")

    if not pending:
        print("No songs remain to search. Review the CSV.")
        return

    try:
        token = get_access_token()
    except (requests.RequestException, RuntimeError, KeyError) as error:
        print(f"ERROR: {error}")
        print(f"Checkpoint CSV preserved: {report}")
        return

    session = requests.Session()
    processed = 0

    for number, song in enumerate(pending, start=1):
        song_id = str(song["id"])
        title = song["title"] or ""
        artist = song["artist"] or ""

        print(f"[{number}/{len(pending)}] {title} — {artist}")

        if not title.strip() or not artist.strip():
            old_rows[song_id] = [{
                "song_id": song_id,
                "title": title,
                "artist": artist,
                "reason": "Missing title or artist",
                "selection": "",
            }]

        else:
            try:
                tracks = search_spotify(
                    session, token, title, artist
                )
            except (
                requests.RequestException, RuntimeError
            ) as error:
                try:
                    write_checkpoint(report, all_rows())
                except OSError as save_error:
                    print(f"ERROR saving CSV: {save_error}")

                print(f"\nERROR: {error}")
                print(f"Progress saved to: {report}")
                print(f"Songs completed this run: {processed}")
                print(
                    "Run the same command again later to resume. "
                    "Completed songs will be skipped."
                )
                return

            title_matches, exact_matches = find_exact_matches(
                title, artist, tracks
            )

            if len(exact_matches) == 1:
                reason = (
                    "Exact title and artist match — confirm manually"
                )
            elif len(exact_matches) > 1:
                reason = (
                    "Multiple exact title and artist matches "
                    f"({len(exact_matches)} candidates)"
                )
            elif title_matches:
                reason = "Title matched; artist credits need review"
            elif tracks:
                reason = "Possible candidates; verify title and artist"
            else:
                reason = "No Spotify candidates returned"

            new_rows = []

            for track in tracks:
                row = {
                    "song_id": song_id,
                    "title": title,
                    "artist": artist,
                    "reason": reason,
                    **candidate_details(track),
                    "selection": "",
                }

                track_id = row["spotify_track_id"]
                row["selection"] = selections.get(
                    song_id, {}
                ).get(track_id, "")

                new_rows.append(row)

                print(
                    f"  Candidate: {row['candidate_title']} — "
                    f"{row['candidate_artists']} ({row['album']})"
                )

            if not new_rows:
                new_rows.append({
                    "song_id": song_id,
                    "title": title,
                    "artist": artist,
                    "reason": reason,
                    "selection": "",
                })
                print(f"  REVIEW: {reason}")

            old_rows[song_id] = new_rows

        # Save after EACH song so an interruption doesn't lose progress.
        try:
            write_checkpoint(report, all_rows())
        except OSError as error:
            print(f"\nERROR: Could not save checkpoint: {error}")
            print("Stop here; do not import until the CSV is saved.")
            return

        processed += 1

    print("\n--- Review summary ---")
    print(f"Songs completed this run: {processed}")
    print(f"Review CSV: {report}")
    print("No database changes were made.")
    print("Enter SELECT in one candidate row per song you approve.")


def create_backup(connection, db_path):
    backup = db_path.with_name(
        f"{db_path.stem}.backup_spotify_"
        f"{datetime.now():%Y%m%d_%H%M%S}{db_path.suffix}"
    )

    with sqlite3.connect(str(backup)) as backup_connection:
        connection.backup(backup_connection)

    return backup


def apply_reviewed(connection, db_path):
    report = get_report_path(db_path)

    if not report.is_file():
        sys.exit(
            f"ERROR: Review CSV not found: {report}\n"
            "Run review mode first."
        )

    try:
        with report.open(
            "r", newline="", encoding="utf-8-sig"
        ) as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames or not set(
                CSV_FIELDS
            ).issubset(set(reader.fieldnames)):
                sys.exit(
                    "ERROR: CSV is missing required columns. "
                    "Generate a fresh review CSV."
                )

            rows = list(reader)

    except (OSError, csv.Error) as error:
        sys.exit(f"ERROR: Could not read review CSV: {error}")

    selected = {}

    for line, row in enumerate(rows, start=2):
        choice = (row.get("selection") or "").strip().upper()

        if not choice:
            continue

        if choice != "SELECT":
            sys.exit(
                f"ERROR: Invalid selection on CSV line {line}. "
                "Use SELECT or leave blank."
            )

        song_id = (row.get("song_id") or "").strip()
        track_id = (row.get("spotify_track_id") or "").strip()
        spotify_url = (row.get("spotify_url") or "").strip()

        if not song_id.isdigit():
            sys.exit(f"ERROR: Invalid song_id on line {line}.")

        if not track_id or not re.fullmatch(
            r"[A-Za-z0-9]+", track_id
        ):
            sys.exit(f"ERROR: Invalid track ID on line {line}.")

        expected_url = f"https://open.spotify.com/track/{track_id}"

        if not re.fullmatch(
            rf"https://open\.spotify\.com/track/"
            rf"{re.escape(track_id)}/?(?:\?[^\s]*)?",
            spotify_url,
        ):
            sys.exit(
                f"ERROR: Spotify URL and track ID don't match "
                f"on CSV line {line}."
            )

        song_id = int(song_id)

        if song_id in selected:
            sys.exit(
                f"ERROR: Song ID {song_id} has multiple SELECT rows. "
                "Leave only one selected candidate per song."
            )

        selected[song_id] = {
            "url": expected_url,
            "track_id": track_id,
            "title": row.get("title", ""),
            "candidate_title": row.get("candidate_title", ""),
            "candidate_artists": row.get("candidate_artists", ""),
        }

    if not selected:
        print("No rows marked SELECT. Database unchanged.")
        return

    for song_id in selected:
        song = connection.execute(
            "SELECT id, spotify_url, spotify_track_id "
            "FROM song WHERE id = ?",
            (song_id,),
        ).fetchone()

        if song is None:
            sys.exit(
                f"ERROR: Song ID {song_id} doesn't exist. "
                "No updates made."
            )

        if (
            (song["spotify_url"] or "").strip()
            or (song["spotify_track_id"] or "").strip()
        ):
            sys.exit(
                f"ERROR: Song ID {song_id} already has a Spotify "
                "field populated. No updates made."
            )

    print(f"Database: {db_path}")
    print(f"Selected songs to link: {len(selected)}")
    print("\nSelections to apply:")

    for song_id, choice in selected.items():
        print(
            f"  ID {song_id}: {choice['title']} -> "
            f"{choice['candidate_title']} — "
            f"{choice['candidate_artists']}"
        )

    confirmation = input(
        "\nType APPLY to back up the database and save these links: "
    ).strip()

    if confirmation != "APPLY":
        print("Cancelled. No database changes made.")
        return

    backup = create_backup(connection, db_path)
    print(f"Backup created: {backup}")

    try:
        connection.execute("BEGIN")

        for song_id, choice in selected.items():
            cursor = connection.execute("""
                UPDATE song
                SET spotify_url = ?, spotify_track_id = ?
                WHERE id = ?
                  AND (spotify_url IS NULL OR TRIM(spotify_url) = '')
                  AND (spotify_track_id IS NULL OR TRIM(spotify_track_id) = '')
            """, (
                choice["url"], choice["track_id"], song_id
            ))

            if cursor.rowcount != 1:
                raise RuntimeError(
                    f"Song ID {song_id} could not be updated safely."
                )

        connection.commit()

    except Exception as error:
        connection.rollback()
        sys.exit(
            f"ERROR: Updates rolled back: {error}\n"
            f"Backup: {backup}"
        )

    print(f"\nSuccessfully linked {len(selected)} songs.")
    print("Only spotify_url and spotify_track_id were changed.")


def main():
    parser = argparse.ArgumentParser(
        description="Review and manually link historical songs to Spotify."
    )

    parser.add_argument(
        "--db", required=True,
        help="SQLite database path, such as mbc_local.db",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply-reviewed", action="store_true",
        help="Apply only candidates marked SELECT in the review CSV.",
    )

    parser.add_argument(
        "--limit", type=int, default=0,
        help="Search at most N remaining songs (0 means all).",
    )

    args = parser.parse_args()

    if args.limit < 0:
        sys.exit("ERROR: --limit cannot be negative.")

    if args.apply_reviewed and args.limit:
        sys.exit("ERROR: Don't use --limit with --apply-reviewed.")

    db_path = Path(args.db)

    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()

    connection = open_database(db_path)

    try:
        if args.apply_reviewed:
            apply_reviewed(connection, db_path)
        else:
            review_songs(connection, db_path, args.limit)
    finally:
        connection.close()


if __name__ == "__main__":
    main()