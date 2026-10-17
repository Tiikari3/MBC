import argparse
import csv
import re
import shutil
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--db", default="mbc_local.db")
parser.add_argument("--csv", default="spotify_links.csv")
args = parser.parse_args()

db_path = Path(args.db)
csv_path = Path(args.csv)

if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path}")

if not csv_path.exists():
    raise SystemExit(f"CSV not found: {csv_path}")

updates = []
seen_ids = set()

with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
    reader = csv.DictReader(file)

    if not {"song_id", "spotify_url"}.issubset(reader.fieldnames or []):
        raise SystemExit("CSV must have song_id and spotify_url columns.")

    for row in reader:
        song_id = (row.get("song_id") or "").strip()
        url = (row.get("spotify_url") or "").strip()

        if not song_id and not url:
            continue

        if not song_id.isdigit():
            raise SystemExit(f"Invalid song_id: {song_id}")

        if song_id in seen_ids:
            raise SystemExit(f"Duplicate song_id: {song_id}")
        seen_ids.add(song_id)

        parsed = urlparse(url)
        parts = parsed.path.strip("/").split("/")

        if (
            parsed.hostname != "open.spotify.com"
            or len(parts) != 2
            or parts[0] != "track"
            or not re.fullmatch(r"[A-Za-z0-9]+", parts[1])
        ):
            raise SystemExit(
                f"Invalid Spotify track URL for song {song_id}: {url}"
            )

        track_id = parts[1]
        updates.append((int(song_id), url.split("?")[0], track_id))

if not updates:
    raise SystemExit("No songs found in the CSV.")

connection = sqlite3.connect(db_path)

try:
    # Check every song exists before making any changes.
    for song_id, url, track_id in updates:
        result = connection.execute(
            "SELECT id, spotify_url, spotify_track_id "
            "FROM song WHERE id = ?",
            (song_id,)
        ).fetchone()

        if result is None:
            raise SystemExit(f"Song ID {song_id} not found in database.")

    pending = []
    skipped = []

    for song_id, url, track_id in updates:
        result = connection.execute(
            "SELECT spotify_url, spotify_track_id "
            "FROM song WHERE id = ?",
            (song_id,)
        ).fetchone()

        if result[0] or result[1]:
            skipped.append(song_id)
        else:
            pending.append((song_id, url, track_id))

    print(f"CSV songs: {len(updates)}")
    print(f"Ready to import: {len(pending)}")
    print(f"Already linked; will skip: {len(skipped)}")

    if not pending:
        raise SystemExit("Nothing to import.")

    confirmation = input(
        "\nType APPLY to back up the database and import these links: "
    )

    if confirmation != "APPLY":
        raise SystemExit("Cancelled. No changes made.")

    backup_path = db_path.with_name(
        db_path.stem + "_before_spotify_import" + db_path.suffix
    )

    # Create a consistent SQLite backup.
    backup = sqlite3.connect(backup_path)
    connection.backup(backup)
    backup.close()

    connection.execute("BEGIN")

    for song_id, url, track_id in pending:
        connection.execute(
            """
            UPDATE song
            SET spotify_url = ?, spotify_track_id = ?
            WHERE id = ?
              AND (spotify_url IS NULL OR spotify_url = '')
              AND (spotify_track_id IS NULL OR spotify_track_id = '')
            """,
            (url, track_id, song_id)
        )

    connection.commit()

    print(f"\nImport complete. Database backup: {backup_path}")
    print(f"Links imported: {len(pending)}")
    print(f"Existing links skipped: {len(skipped)}")

except Exception:
    connection.rollback()
    raise
finally:
    connection.close()