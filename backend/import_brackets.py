"""
Import historical Song of the Month and Song of the Year brackets.

Run a dry run first:
    python import_brackets.py --workbook "Music_Book_Club(1).xlsx"

Only write to the database after reviewing the dry-run report:
    python import_brackets.py --workbook "Music_Book_Club(1).xlsx" --apply

This script never creates or edits Song or User records.
"""

import argparse
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from sqlmodel import Session, select

from main import (
    engine,
    User,
    Song,
    BracketTournament,
    BracketMatch,
    BracketVote,
)

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Replace these example values with the EXACT usernames in Supabase.
# These are account usernames, not the short labels from Excel.
#
# L, P, G, R, T, W, F and J are the labels used in the monthly sheets.
# S1 and S2 also appear in the annual sheet; verify what they represent
# before mapping them to real accounts.
VOTER_MAPPING = {
    "L":  "loganworsdell",
    "P":  "Parker",
    "G":  "PapiPetro",
    "R":  "rosey0316",
    "T":  "typiont814",
    "W":  "WestonMiller",
    "F":  "Flocco",
    "J":  "awesomegear3",
}


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def norm(value):
    value = unicodedata.normalize("NFKC", clean(value)).casefold()
    return re.sub(r"\s+", " ", value).strip()


def is_marked(value):
    return norm(value) == "x"


def parse_seed_description(value):
    """
    The workbook labels matchups like 'Seed 1 vs 2'.

    The sheet does not explicitly label rounds. For organizing imported
    matches in the website, this estimates a round from the higher seed.
    This is a display grouping, not proof of a standard elimination tree.
    """
    match = re.search(
        r"seed\s*(\d+)\s*vs\.?\s*(\d+)",
        clean(value),
        flags=re.IGNORECASE,
    )
    if not match:
        return None, None

    seed_a, seed_b = int(match.group(1)), int(match.group(2))
    highest_seed = max(seed_a, seed_b)
    round_number = max(1, math.ceil(math.log2(highest_seed)))

    return round_number, highest_seed


def resolve_song(title, songs_by_title):
    key = norm(title)

    if not key or key == "tbd":
        return None, "blank/TBD"

    matches = songs_by_title.get(key, [])

    if len(matches) == 1:
        return matches[0], None

    if not matches:
        return None, f"no existing song titled {title!r}"

    return None, f"ambiguous song title {title!r}: multiple database records"


def get_month_sections(ws):
    if ws.max_row is None or ws.max_row < 1:
        return []
    """Find month labels in column A and the table header below each label."""
    sections = []

    for row_number in range(1, (ws.max_row or 0) + 1):
        label = norm(ws.cell(row_number, 1).value)

        if label in MONTHS:
            header_row = row_number + 1

            if norm(ws.cell(header_row, 1).value) == "description":
                sections.append((MONTHS[label], header_row))

    return sections


def read_month_rows(ws, year):
    """
    Monthly layout:
      B:H = voters for Song 1
      I:M = Song 1, Score 1, Winner, Score 2, Song 2
      N:T = voters for Song 2
    """
    records = []
    sections = get_month_sections(ws)

    for section_index, (month, header_row) in enumerate(sections):
        next_header = (
            sections[section_index + 1][1] - 1
            if section_index + 1 < len(sections)
            else ws.max_row
        )

        for row_number in range(header_row + 1, next_header + 1):
            description = clean(ws.cell(row_number, 1).value)

            if not description:
                continue

            round_number, highest_seed = parse_seed_description(description)

            if round_number is None:
                continue

            records.append({
                "sheet": ws.title,
                "year": year,
                "month": month,
                "bracket_type": "month",
                "row": row_number,
                "description": description,
                "round_number": round_number,
                "highest_seed": highest_seed,
                "song_a_title": clean(ws.cell(row_number, 9).value),
                "score_a": ws.cell(row_number, 10).value,
                "winner_title": clean(ws.cell(row_number, 11).value),
                "score_b": ws.cell(row_number, 12).value,
                "song_b_title": clean(ws.cell(row_number, 13).value),
                "votes_a": [
                    (clean(ws.cell(header_row, col).value),
                     ws.cell(row_number, col).value)
                    for col in range(2, 9)
                    if clean(ws.cell(header_row, col).value)
                ],
                "votes_b": [
                    (clean(ws.cell(header_row, col).value),
                     ws.cell(row_number, col).value)
                    for col in range(14, 21)
                    if clean(ws.cell(header_row, col).value)
                ],
            })

    return records


def read_year_rows(ws, year):
    """
    Annual layout:
      B:C = S1/S2 (ignored)
      D:J = voter labels on Song 1's side
      K:O = Song 1, Score 1, Winner, Score 2, Song 2
      P:V = voter labels on Song 2's side
    """
    records = []
    header_row = 2

    for row_number in range(header_row + 1, (ws.max_row or 0) + 1):
        description = clean(ws.cell(row_number, 1).value)

        if not description:
            continue

        round_number, highest_seed = parse_seed_description(description)

        if round_number is None:
            continue

        records.append({
            "sheet": ws.title,
            "year": year,
            "month": None,
            "bracket_type": "year",
            "row": row_number,
            "description": description,
            "round_number": round_number,
            "highest_seed": highest_seed,
            "song_a_title": clean(ws.cell(row_number, 11).value),
            "score_a": ws.cell(row_number, 12).value,
            "winner_title": clean(ws.cell(row_number, 13).value),
            "score_b": ws.cell(row_number, 14).value,
            "song_b_title": clean(ws.cell(row_number, 15).value),
            "votes_a": [
                (clean(ws.cell(header_row, col).value),
                 ws.cell(row_number, col).value)
                for col in range(4, 11)
                if clean(ws.cell(header_row, col).value)
            ],
            "votes_b": [
                (clean(ws.cell(header_row, col).value),
                 ws.cell(row_number, col).value)
                for col in range(16, 23)
                if clean(ws.cell(header_row, col).value)
            ],
        })

    return records


def load_voter_lookup(session, issues):
    users = session.exec(select(User)).all()
    users_by_username = {norm(user.username): user for user in users}
    result = {}

    for label, username in VOTER_MAPPING.items():
        if not username or username.startswith("REPLACE_WITH_"):
            continue

        user = users_by_username.get(norm(username))

        if user is None:
            issues.append(
                f"Voter label {label!r}: database username "
                f"{username!r} was not found."
            )
        else:
            result[norm(label)] = user

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workbook",
        default="Music_Book_Club(1).xlsx",
        help="Path to the Excel workbook",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the import to the database; otherwise dry run",
    )
    args = parser.parse_args()

    workbook_path = Path(args.workbook)

    if not workbook_path.exists():
        sys.exit(f"Workbook not found: {workbook_path.resolve()}")

    workbook = load_workbook(
        workbook_path,
        data_only=True,
        read_only=False,
)

    all_records = []

    for sheet_name, year in [
        ("2025 Song of the Month", 2025),
        ("2026 Song of the Month", 2026),
    ]:
        if sheet_name not in workbook.sheetnames:
            print(f"WARNING: missing worksheet {sheet_name!r}")
            continue

        records = read_month_rows(workbook[sheet_name], year)
        all_records.extend(records)
        print(f"{sheet_name}: found {len(records)} matchup rows")

    annual_sheet = "2025 Song of the Year"

    if annual_sheet in workbook.sheetnames:
        records = read_year_rows(workbook[annual_sheet], 2025)
        all_records.extend(records)
        print(f"{annual_sheet}: found {len(records)} matchup rows")

    if not all_records:
        sys.exit("No matchup rows were found. Nothing imported.")

    issues = []
    warnings = []

    with Session(engine) as session:
        # Never append a second copy of the same tournaments.
        existing = session.exec(select(BracketTournament)).all()

        if existing:
            sys.exit(
                "BracketTournament already contains records. "
                "This script will not overwrite or duplicate them."
            )

        songs = session.exec(select(Song)).all()
        songs_by_title = defaultdict(list)

        for song in songs:
            songs_by_title[norm(song.title)].append(song)

        voters = load_voter_lookup(session, issues)

        prepared = []
        round_counts = defaultdict(int)

        for record in all_records:
            song_a, problem_a = resolve_song(
                record["song_a_title"], songs_by_title
            )
            song_b, problem_b = resolve_song(
                record["song_b_title"], songs_by_title
            )

            if problem_a not in (None, "blank/TBD"):
                issues.append(
                    f'{record["year"]}/{record["month"]} '
                    f'[{record["sheet"]}] row {record["row"]}: Song 1: {problem_a}'
                )

            if problem_b not in (None, "blank/TBD"):
                issues.append(
                    f'{record["year"]}/{record["month"]} '
                    f'[{record["sheet"]}] row {record["row"]}: Song 2: {problem_b}'
                )

            if song_a is None and song_b is None:
                warnings.append(
                    f'[{record["sheet"]}] row {record["row"]}: both matchup songs are blank/TBD.'
                )
                continue

            winner = None

            if norm(record["winner_title"]) not in ("", "tbd"):
                winner_matches = [
                    song for song in (song_a, song_b)
                    if song and norm(song.title) == norm(record["winner_title"])
                ]

                if len(winner_matches) == 1:
                    winner = winner_matches[0]
                else:
                    issues.append(
                        f'[{record["sheet"]}] row {record["row"]}: winner '
                        f'{record["winner_title"]!r} does not uniquely match '
                        f'one of the two matchup songs.'
                    )

            vote_rows = []
            seen_voters = set()

            for side, choices, side_song in (
                ("A", record["votes_a"], song_a),
                ("B", record["votes_b"], song_b),
            ):
                for label, cell_value in choices:
                    if not is_marked(cell_value):
                        continue

                    user = voters.get(norm(label))

                    if user is None:
                        issues.append(
                            f'[{record["sheet"]}] row {record["row"]}: vote marked for '
                            f'{label!r}, but that label has no valid user mapping.'
                        )
                        continue

                    if side_song is None:
                        issues.append(
                            f'[{record["sheet"]}] row {record["row"]}: voter {label!r} marked '
                            f'a vote for a blank/TBD song.'
                        )
                        continue

                    if user.id in seen_voters:
                        issues.append(
                            f'[{record["sheet"]}] row {record["row"]}: voter {label!r} is marked '
                            f'on both sides of the matchup.'
                        )
                        continue

                    seen_voters.add(user.id)
                    vote_rows.append((user, side_song))

            if winner is None and norm(record["winner_title"]) not in ("", "tbd"):
                # The winner could not be matched; do not import a possibly
                # incorrect completed result.
                continue

            if song_a and song_b and norm(record["winner_title"]) in ("", "tbd"):
                status = "open"
            elif winner:
                status = "complete"
            else:
                status = "open"

            score_a = record["score_a"]
            score_b = record["score_b"]
            vote_a_count = sum(1 for _, song in vote_rows if song == song_a)
            vote_b_count = sum(1 for _, song in vote_rows if song == song_b)

            try:
                if score_a is not None and int(score_a) != vote_a_count:
                    warnings.append(
                        f'[{record["sheet"]}] row {record["row"]}: Score 1 is {score_a}, '
                        f'but imported individual votes on side A total '
                        f'{vote_a_count}.'
                    )
                if score_b is not None and int(score_b) != vote_b_count:
                    warnings.append(
                        f'[{record["sheet"]}] row {record["row"]}: Score 2 is {score_b}, '
                        f'but imported individual votes on side B total '
                        f'{vote_b_count}.'
                    )
            except (TypeError, ValueError):
                pass

            prepared.append({
                **record,
                "song_a": song_a,
                "song_b": song_b,
                "winner": winner,
                "status": status,
                "vote_rows": vote_rows,
            })

        print("\n--- IMPORT SUMMARY ---")
        print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
        print(f"Matchups prepared: {len(prepared)}")
        print(f"Songs in database: {len(songs)}")
        print(f"Voter labels mapped: {len(voters)}")
        print(f"Errors requiring review: {len(issues)}")
        print(f"Warnings: {len(warnings)}")

        for warning in warnings[:100]:
            print("WARNING:", warning)

        for issue in issues[:200]:
            print("ERROR:", issue)

        if len(warnings) > 100:
            print(f"... plus {len(warnings) - 100} more warnings")

        if len(issues) > 200:
            print(f"... plus {len(issues) - 200} more errors")

        if not args.apply:
            print("\nDry run only. No database changes were made.")
            print("Fix the mappings and review the report before using --apply.")
            return

        # Group records into their tournaments.
        grouped = defaultdict(list)

        for record in prepared:
            grouped[(
                record["bracket_type"],
                record["year"],
                record["month"],
            )].append(record)

        # One transaction: if anything fails, no partial import is committed.
        try:
            for (bracket_type, year, month), matches in grouped.items():
                tournament = BracketTournament(
                    bracket_type=bracket_type,
                    year=year,
                    month=month,
                    voter_target=6,
                    status=(
                        "complete"
                        if all(m["status"] == "complete" for m in matches)
                        else "active"
                    ),
                    # The workbook does not explicitly identify a single
                    # champion field, so do not guess one here.
                    champion_song_id=None,
                    created_by_user_id=next(iter(voters.values())).id,
                )
                session.add(tournament)
                session.flush()

                match_numbers = defaultdict(int)

                for record in sorted(
                    matches,
                    key=lambda m: (m["round_number"], m["row"]),
                ):
                    round_number = record["round_number"]
                    match_numbers[round_number] += 1

                    match = BracketMatch(
                        tournament_id=tournament.id,
                        round_number=round_number,
                        matchup_number=match_numbers[round_number],
                        song_a_id=(
                            record["song_a"].id if record["song_a"] else None
                        ),
                        song_b_id=(
                            record["song_b"].id if record["song_b"] else None
                        ),
                        winner_song_id=(
                            record["winner"].id if record["winner"] else None
                        ),
                        status=record["status"],
                    )
                    session.add(match)
                    session.flush()

                    for user, voted_song in record["vote_rows"]:
                        session.add(
                            BracketVote(
                                match_id=match.id,
                                voter_id=user.id,
                                song_id=voted_song.id,
                            )
                        )

            session.commit()

        except Exception:
            session.rollback()
            raise

        print("\nImport committed successfully.")
        print(f"Tournaments imported: {len(grouped)}")
        print(f"Matchups imported: {len(prepared)}")
        print("Existing songs and user accounts were not modified.")


if __name__ == "__main__":
    main()