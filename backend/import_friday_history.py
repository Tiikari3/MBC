"""
Import historical Friday Themes proposals, votes, and wheel selections.

Run from the backend folder:
    python import_friday_history.py --workbook MPE_Moosic_Ranks.xlsx --dry-run
    python import_friday_history.py --workbook MPE_Moosic_Ranks.xlsx --apply

The script defaults to DRY RUN. It does not commit database changes unless --apply
is supplied. Back up the database first, and check the report before applying.

Expected workbook:
- The proposal/voting table and selection-history table can be on the same worksheet.
- Header rows are detected anywhere on the selected worksheet.
- Default worksheet: Themes. Default workbook: Music_Book_Club.xlsx.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import inspect, text
from sqlmodel import Session, select

# Run this script from backend/ so `main` resolves to backend/main.py.
from main import (
    engine,
    User,
    Song,
    FridayThemeProposal,
    FridayThemeProposalVote,
    FridayThemeWheelSelection,
)

# EDIT THESE VALUES to match the actual usernames in your database.
# Keys are the names as they appear in the workbook; values are exact account usernames.
USER_MAPPING = {
    "Logan": "loganworsdell",
    "Parker": "Parker",
    "Giacomo": "PapiPetro",
    "Rosey": "rosey0316",
    "TTAC": "typiont814",
    "Weston": "WestonMiller",
    "Flocco": "Flocco",
    "Jake": "awesomegear3",
}

COMBINED_JAKE_FLOCCO = "Jake / Flocco"
FLOCCO_STARTS_AFTER_ROW = 60

MANUAL_POSTER_BY_HISTORY_ROW = {
    44: "Flocco",  # Change to "Flocco" if Flocco is correct.
}

MANUAL_SONG_ID_BY_HISTORY_ROW = {
    19: 407,  # "Time" — enter the correct existing Song ID.
    22: 839,  # "Face My Fears" — enter the correct existing Song ID.
    26: 765,  # "Jog Pra Lua" — enter the correct existing Song ID.
    29: 371,  # "Who Dat Girl" — enter the correct existing Song ID.
}

PROPOSAL_SHEET_DEFAULT = "Themes"
HISTORY_SHEET_DEFAULT = "Themes"


def resolve_combined_name(name: str, excel_row: int) -> str:
    """Determine whether a combined Jake / Flocco entry belongs to Jake or Flocco."""
    if norm(name) == norm(COMBINED_JAKE_FLOCCO):
        return "Flocco" if excel_row > FLOCCO_STARTS_AFTER_ROW else "Jake"

    return name

def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def norm(value: Any) -> str:
    value = unicodedata.normalize("NFKC", clean(value)).casefold()
    return re.sub(r"\s+", " ", value).strip()


def header_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm(value))


def find_table_header(ws, required_headers: set[str], table_label: str):
    """Find a table's header row anywhere on a worksheet, not only row 1."""
    max_row = ws.max_row or 0
    if max_row == 0:
        # Fall back to scanning actual cell rows if worksheet dimensions are missing.
        max_row = max((cell.row for row in ws.iter_rows() for cell in row if cell.value is not None), default=0)
    for row_num in range(1, max_row + 1):
        keys = {header_key(cell.value) for cell in ws[row_num] if clean(cell.value)}
        if required_headers.issubset(keys):
            return row_num
    raise ValueError(
        f"Could not find the {table_label} header row on worksheet '{ws.title}'. "
        f"Expected headers including: {', '.join(sorted(required_headers))}."
    )


def table_rows(ws, header_row: int, table_label: str):
    """Read just one table's columns from its header row onward.

    This supports proposal and history tables either stacked vertically or placed
    side by side on the same worksheet. A trailing blank-header column is included
    when available (the proposal table may store Passed there).
    """
    if table_label == "proposal":
        known = {
            "proponent", "proposer", "themesuggestion", "theme", "themename",
            "themedescriptionoptional", "themedescription", "description", "result",
            "status", "outcome", "logan", "parker", "giacomo", "rosey", "ttac",
            "weston", "jakeflocco",
        }
        start_keys = {"proponent", "proposer"}
    else:
        known = {
            "poster", "themepool", "theme", "themename", "picked", "picked?",
            "selected", "date", "selecteddate", "selectiondate", "winningsong",
            "song", "winnersong", "winner", "winningmember", "winnerusername",
        }
        start_keys = {"poster"}

    header_cells = list(ws[header_row])
    recognized_cols = [
        i + 1 for i, cell in enumerate(header_cells)
        if header_key(cell.value) in known and clean(cell.value)
    ]
    # Because both tables are side-by-side, cells from the history table can
    # contain values like "Logan" on the proposal header row. Do not mistake
    # those data values for proposal column headers: stop before the history
    # table's Poster column.
    if table_label == "proposal":
        history_start_col = None
        for candidate_row in ws.iter_rows():
            keys_in_row = {header_key(cell.value) for cell in candidate_row if clean(cell.value)}
            if {"poster", "themepool", "picked", "date", "winningsong", "winner"}.issubset(keys_in_row):
                poster_cells = [
                    cell.column for cell in candidate_row
                    if header_key(cell.value) == "poster"
                ]
                if poster_cells:
                    history_start_col = min(poster_cells)
                    break
        if history_start_col is not None:
            recognized_cols = [col for col in recognized_cols if col < history_start_col]
    if not recognized_cols:
        return []
    anchors = [i for i in recognized_cols if header_key(ws.cell(header_row, i).value) in start_keys]
    if not anchors:
        raise ValueError(f"Found some {table_label} headers on row {header_row}, but not its identifying header.")
    start_col = min(anchors)

    # The two tables are side-by-side on Themes. The history table has an
    # intentionally blank description header between "Theme Pool" and "Picked".
    # Therefore, do not stop at the first blank header; keep all columns through
    # the last recognized header. The proposal table also has a blank result
    # column immediately after its last named vote column.
    end_col = max(recognized_cols)
    if table_label == "proposal":
        next_col = end_col + 1
        if next_col <= (ws.max_column or 0) and not clean(ws.cell(header_row, next_col).value):
            end_col = next_col

    headers = [clean(ws.cell(header_row, col).value) or f"__column_{col}" for col in range(start_col, end_col + 1)]
    result = []
    expected_any = (
        {"proponent", "proposer", "themesuggestion", "theme", "themename"}
        if table_label == "proposal"
        else {"poster", "themepool", "theme", "themename"}
    )
    for row_num in range(header_row + 1, ws.max_row + 1):
        values = [ws.cell(row_num, col).value for col in range(start_col, end_col + 1)]
        if not any(clean(v) for v in values):
            continue
        row_keys = {
            header_key(headers[i]) for i, v in enumerate(values)
            if clean(v) and not headers[i].startswith("__column_")
        }
        # Skip rows belonging to the other table when tables are stacked vertically.
        if not (row_keys & expected_any):
            continue
        result.append({"_excel_row": row_num, **{headers[i]: values[i] for i in range(len(values))}})
    return result


def get_value(row: dict, *aliases: str) -> Any:
    lookup = {header_key(k): v for k, v in row.items() if not k.startswith("_")}
    for alias in aliases:
        key = header_key(alias)
        if key in lookup:
            return lookup[key]
    return None

def vote_entries_for_row(row: dict, excel_row: int):
    """Split the combined Jake / Flocco vote column using the Excel row number."""
    entries = []

    # Read the normal vote columns for everyone except Jake and Flocco.
    for source_name in USER_MAPPING:
        if norm(source_name) in {
            norm("Jake"),
            norm("Flocco"),
            norm(COMBINED_JAKE_FLOCCO),
        }:
            continue

        vote_cell = get_value(row, source_name)

        # Blank means the person did not vote.
        if clean(vote_cell):
            entries.append((source_name, vote_cell))

    # Interpret the combined column as Jake or Flocco based on the row.
    combined_vote = get_value(row, COMBINED_JAKE_FLOCCO)

    if clean(combined_vote):
        voter_name = resolve_combined_name(
            COMBINED_JAKE_FLOCCO,
            excel_row,
        )
        entries.append((voter_name, combined_vote))

    return entries


def resolve_sheet(workbook, requested_name: str | None, required_headers: set[str]):
    if requested_name:
        if requested_name not in workbook.sheetnames:
            raise ValueError(
                f"Sheet '{requested_name}' not found. Workbook sheets: {workbook.sheetnames}"
            )
        return workbook[requested_name]

    # Prefer the known workbook tab name, then search all worksheets.
    if "Themes" in workbook.sheetnames:
        return workbook["Themes"]
    for ws in workbook.worksheets:
        try:
            find_table_header(ws, required_headers, "requested")
            return ws
        except ValueError:
            continue
    raise ValueError(
        f"Could not identify a worksheet with headers {sorted(required_headers)}. "
        f"Available worksheets: {workbook.sheetnames}"
    )


def parse_date(value: Any) -> date | None:
    if value is None or clean(value) == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = clean(value)
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    # Excel may export a date with a timestamp suffix.
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def mapped_users(session: Session):
    users = session.exec(select(User)).all()
    by_username = {norm(u.username): u for u in users}
    result = {}
    problems = []
    for source_name, username in USER_MAPPING.items():
        if not username or username.startswith("REPLACE_WITH_"):
            problems.append(f"USER_MAPPING needs the real username for '{source_name}'.")
            continue
        user = by_username.get(norm(username))
        if user is None:
            problems.append(
                f"Mapped username '{username}' for '{source_name}' was not found in the database."
            )
        else:
            result[norm(source_name)] = user
    return result, problems


def ensure_history_columns():
    """Add nullable result links without deleting or rewriting existing data."""
    inspector = inspect(engine)
    if not inspector.has_table("fridaythemewheelselection"):
        raise RuntimeError(
            "fridaythemewheelselection table does not exist. Confirm Friday Themes "
            "models are included in backend/main.py and the app has initialized the database."
        )
    existing = {col["name"] for col in inspector.get_columns("fridaythemewheelselection")}
    dialect = engine.url.get_backend_name()
    with engine.begin() as conn:
        if "winning_song_id" not in existing:
            if dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE fridaythemewheelselection "
                    "ADD COLUMN IF NOT EXISTS winning_song_id INTEGER NULL"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE fridaythemewheelselection ADD COLUMN winning_song_id INTEGER NULL"
                ))
        if "winner_id" not in existing:
            if dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE fridaythemewheelselection "
                    "ADD COLUMN IF NOT EXISTS winner_id INTEGER NULL"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE fridaythemewheelselection ADD COLUMN winner_id INTEGER NULL"
                ))
        if "winning_song_title" not in existing:
            if dialect == "postgresql":
                conn.execute(text(
                    "ALTER TABLE fridaythemewheelselection "
                    "ADD COLUMN IF NOT EXISTS winning_song_title VARCHAR NULL"
                ))
            else:
                conn.execute(text(
                    "ALTER TABLE fridaythemewheelselection ADD COLUMN winning_song_title VARCHAR NULL"
                ))


def main():
    parser = argparse.ArgumentParser(description="Import historical Friday Themes workbook data.")
    parser.add_argument("--workbook", default="Music_Book_Club.xlsx", help="Path to the Excel workbook")
    parser.add_argument("--proposal-sheet", default=None, help="Exact worksheet name for proposal/vote table")
    parser.add_argument("--history-sheet", default=None, help="Exact worksheet name for selection history")
    parser.add_argument("--apply", action="store_true", help="Commit changes; without this, runs a dry run")
    parser.add_argument("--no-schema-change", action="store_true",
                        help="Do not add history result columns (winning song/winner details cannot be saved)")
    args = parser.parse_args()

    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        sys.exit(
            f"Workbook not found: {workbook_path.resolve()}\n"
            "Place the workbook in the backend folder or pass --workbook with its path."
        )

    workbook = load_workbook(workbook_path, data_only=True, read_only=False)
    proposal_ws = resolve_sheet(workbook, args.proposal_sheet or PROPOSAL_SHEET_DEFAULT,
                                {"proponent", "themesuggestion"})
    history_ws = resolve_sheet(workbook, args.history_sheet or HISTORY_SHEET_DEFAULT,
                               {"poster", "themepool"})
    # Both tables can live on the same worksheet, with their headers on different rows
    # or in different columns. Detect each header row independently.
    proposal_header_row = find_table_header(proposal_ws, {"proponent", "themesuggestion"}, "proposal")
    history_header_row = find_table_header(history_ws, {"poster", "themepool"}, "history")
    proposal_rows = table_rows(proposal_ws, proposal_header_row, "proposal")
    history_rows = table_rows(history_ws, history_header_row, "history")

    print(f"Workbook: {workbook_path.resolve()}")
    print(f"Proposal table: {proposal_ws.title}, header row {proposal_header_row} ({len(proposal_rows)} rows)")
    print(f"History table: {history_ws.title}, header row {history_header_row} ({len(history_rows)} rows)")
    print(f"Mode: {'APPLY (database writes enabled)' if args.apply else 'DRY RUN (no import writes)'}")

    if args.apply and not args.no_schema_change:
        ensure_history_columns()

    added_proposals = added_votes = added_selections = 0
    skipped_votes = unmatched_songs = 0
    issues: list[str] = []

    with Session(engine) as session:
        user_map, mapping_issues = mapped_users(session)
        issues.extend(mapping_issues)
        db_users = session.exec(select(User)).all()
        print(f"Database users found: {len(db_users)}")
        if mapping_issues:
            print("\nUSER MAPPING ISSUES:")
            for issue in mapping_issues:
                print(f"  - {issue}")

        proposals = session.exec(select(FridayThemeProposal)).all()
        songs = session.exec(select(Song)).all()
        selections = session.exec(select(FridayThemeWheelSelection)).all()

        proposal_by_signature = {}
        for proposal in proposals:
            key = (
                proposal.proposer_id,
                norm(proposal.name),
                norm(proposal.description),
            )
            proposal_by_signature.setdefault(key, []).append(proposal)

        proposal_source_map = {}
        planned_proposals = []

        print("\nPROPOSALS AND VOTES")
        for row in proposal_rows:
            row_num = row["_excel_row"]
            proposer_name = resolve_combined_name(
            clean(get_value(row, "Proponent", "Proposer")),
            row_num,
            )
            theme_name = clean(get_value(row, "Theme Suggestion", "Theme", "Theme Name"))
            description = clean(get_value(row, "Theme Description (Optional)", "Theme Description", "Description"))
            status_text = norm(get_value(row, "Result", "Status", "Outcome", "Passed"))
            # Some sheets have an unnamed final column. Fall back to the last non-empty cell.
            if not status_text:
                values = [v for k, v in row.items() if k != "_excel_row" and clean(v)]
                if values:
                    last = norm(values[-1])
                    if last in {"passed", "approved", "denied", "rejected", "pending"}:
                        status_text = last

            proposer = user_map.get(norm(proposer_name))
            if not proposer:
                issues.append(f"Proposal sheet row {row_num}: unknown/unmapped proposer '{proposer_name}'.")
                continue
            if not theme_name:
                issues.append(f"Proposal sheet row {row_num}: missing theme name.")
                continue

            if status_text in {"passed", "approved", "yes", "true"}:
                status = "approved"
            elif status_text in {"denied", "rejected", "failed", "no"}:
                status = "denied"
            else:
                status = "pending"

            signature = (proposer.id, norm(theme_name), norm(description))
            matches = proposal_by_signature.get(signature, [])
            if len(matches) > 1:
                issues.append(
                    f"Proposal sheet row {row_num}: multiple existing proposals match "
                    f"{theme_name!r} by {proposer_name}; skipped as ambiguous."
                )
                continue
            if matches:
                proposal = matches[0]
                print(f"  Existing proposal reused: {theme_name} (row {row_num})")
            else:
                proposal = FridayThemeProposal(
                    name=theme_name,
                    description=description,
                    proposer_id=proposer.id,
                    status=status,
                )
                planned_proposals.append(proposal)
                proposal_by_signature.setdefault(signature, []).append(proposal)
                added_proposals += 1
                if args.apply:
                    session.add(proposal)
                print(f"  {'Would add' if not args.apply else 'Add'} proposal: {theme_name} [{status}]")

            # For imported historical data, the sheet's recorded outcome is authoritative.
            if matches and proposal.status != status:
                print(f"  Status update: {theme_name}: {proposal.status} -> {status}")
                if args.apply:
                    proposal.status = status
                    session.add(proposal)

            proposal_source_map[norm(theme_name)] = proposal

            # Vote cells are recognized only for the configured member columns.
            for source_voter_name, vote_cell in vote_entries_for_row(row, row_num):
                vote_text = norm(vote_cell)
                if not vote_text:
                    continue  # Blank means no vote was cast.
                if vote_text not in {"in favor", "in favour", "opposed"}:
                    issues.append(
                        f"Proposal sheet row {row_num}, {source_voter_name}: "
                        f"unrecognized vote {clean(vote_cell)!r}; left unchanged."
                    )
                    continue
                voter = user_map.get(norm(source_voter_name))
                if not voter:
                    continue
                in_favor = vote_text in {"in favor", "in favour"}
                existing_vote = session.exec(
                    select(FridayThemeProposalVote).where(
                        FridayThemeProposalVote.proposal_id == proposal.id,
                        FridayThemeProposalVote.voter_id == voter.id,
                    )
                ).first() if proposal.id is not None else None

                if existing_vote:
                    if existing_vote.in_favor != in_favor:
                        issues.append(
                            f"Proposal '{theme_name}', voter '{source_voter_name}': "
                            "existing vote conflicts with workbook; left unchanged."
                        )
                    continue

                added_votes += 1
                if args.apply:
                    # New proposals receive their votes in the second pass, after IDs exist.
                    if proposal.id is not None:
                        session.add(FridayThemeProposalVote(
                            proposal_id=proposal.id,
                            voter_id=voter.id,
                            in_favor=in_favor,
                        ))
                else:
                    print(f"    Would add vote: {source_voter_name} = {clean(vote_cell)}")

        if args.apply:
            session.flush()
            # After new proposals have IDs, import votes for proposals that were new.
            # The first pass above can only add votes for pre-existing proposal IDs.
            for row in proposal_rows:
                proposer_name = clean(get_value(row, "Proponent", "Proposer"))
                theme_name = clean(get_value(row, "Theme Suggestion", "Theme", "Theme Name"))
                description = clean(get_value(row, "Theme Description (Optional)", "Theme Description", "Description"))
                proposer = user_map.get(norm(proposer_name))
                if not proposer or not theme_name:
                    continue
                proposal = session.exec(select(FridayThemeProposal).where(
                    FridayThemeProposal.proposer_id == proposer.id,
                    FridayThemeProposal.name == theme_name,
                    FridayThemeProposal.description == description,
                )).first()
                if not proposal:
                    continue

                row_num = row["_excel_row"]

                for source_voter_name, vote_cell in vote_entries_for_row(row, row_num):
                    vote_text = norm(vote_cell)
                    if vote_text not in {"in favor", "in favour", "opposed"}:
                        continue
                    voter = user_map.get(norm(source_voter_name))
                    if not voter:
                        continue
                    existing_vote = session.exec(select(FridayThemeProposalVote).where(
                        FridayThemeProposalVote.proposal_id == proposal.id,
                        FridayThemeProposalVote.voter_id == voter.id,
                    )).first()
                    if not existing_vote:
                        session.add(FridayThemeProposalVote(
                            proposal_id=proposal.id,
                            voter_id=voter.id,
                            in_favor=vote_text in {"in favor", "in favour"},
                        ))

        print("\nSELECTION HISTORY")
        # Refresh proposals after pending inserts have IDs when applying.
        if args.apply:
            session.flush()
            proposals = session.exec(select(FridayThemeProposal)).all()
        all_proposals = session.exec(select(FridayThemeProposal)).all()
        for row in history_rows:
            row_num = row["_excel_row"]
            poster_name = clean(get_value(row, "Poster", "Proponent", "Spinner"))
            theme_name = clean(get_value(row, "Theme Pool", "Theme", "Theme Name"))
            picked_text = norm(get_value(row, "Picked?", "Picked", "Selected"))
            selected_date = parse_date(get_value(row, "Date", "Selected Date", "Selection Date"))
            winning_title = clean(get_value(row, "Winning Song", "Song", "Winner Song"))
            winner_name = clean(get_value(row, "Winner", "Winning Member", "Winner Username"))

            # Accommodate the legacy table as pasted in chat, where the headers are
            # shifted one column left from the values:
            # description | Yes | date | song title | winner under an unnamed final header.
            if picked_text not in {"yes", "y", "true", "picked", "selected"}:
                shifted_picked = norm(get_value(row, "Date"))
                shifted_date = parse_date(get_value(row, "Winning Song"))
                if shifted_picked in {"yes", "y", "true", "picked", "selected"} and shifted_date:
                    picked_text = shifted_picked
                    selected_date = shifted_date
                    winning_title = clean(get_value(row, "Winner"))
                    unnamed_values = [
                        clean(v) for k, v in row.items()
                        if k.startswith("__column_") and clean(v)
                    ]
                    winner_name = unnamed_values[-1] if unnamed_values else ""

            if not theme_name:
                issues.append(f"History sheet row {row_num}: missing theme name.")
                continue

            # Match by normalized name; require exactly one proposal unless an imported
            # proposal from this workbook already resolved the row.
            candidates = [p for p in all_proposals if norm(p.name) == norm(theme_name)]
            proposal = proposal_source_map.get(norm(theme_name))
            if proposal is None:
                if len(candidates) == 1:
                    proposal = candidates[0]
                elif len(candidates) > 1:
                    issues.append(
                        f"History row {row_num}: multiple proposals named {theme_name!r}; "
                        "selection not imported until the match is clarified."
                    )
                    continue
                else:
                    issues.append(
                        f"History row {row_num}: no proposal found for theme {theme_name!r}; "
                        "selection not imported."
                    )
                    continue

            if picked_text not in {"yes", "y", "true", "picked", "selected"}:
                print(f"  Unpicked theme preserved as proposal only: {theme_name}")
                continue

            if not selected_date:
                issues.append(f"History row {row_num}: picked theme {theme_name!r} has invalid/missing date.")
                continue

            # Apply a manual poster correction when configured.
            poster_name = MANUAL_POSTER_BY_HISTORY_ROW.get(
                row_num, poster_name
            )

            poster = user_map.get(norm(poster_name))
            if not poster:
                issues.append(f"History row {row_num}: unknown/unmapped poster '{poster_name}'.")
                continue

            winner = user_map.get(norm(winner_name)) if winner_name else None
            if winner_name and not winner:
                issues.append(f"History row {row_num}: winner '{winner_name}' is not mapped; winner left blank.")

            song_id = None

            if row_num in MANUAL_SONG_ID_BY_HISTORY_ROW:
                manual_song_id = MANUAL_SONG_ID_BY_HISTORY_ROW[row_num]

                if manual_song_id is not None:
                    song = next(
                        (s for s in songs if s.id == manual_song_id),
                        None,
                    )

                    if song is None:
                        issues.append(
                            f"History row {row_num}: manual Song ID "
                            f"{manual_song_id} was not found; "
                            "song link left blank."
                        )
                        unmatched_songs += 1
                    else:
                        song_id = song.id
                        print(
                            f"  Manual song match: {winning_title} "
                            f"-> Song #{song.id} ({song.title})"
                        )

                else:
                    # Override configured, but no Song ID entered yet.
                    unmatched_songs += 1
                    issues.append(
                        f"History row {row_num}: manual Song ID is still "
                        f"None for {winning_title!r}; song link left blank."
                    )

            elif winning_title:
                matches = [
                    song for song in songs
                    if norm(song.title) == norm(winning_title)
                ]

                if len(matches) == 1:
                    song_id = matches[0].id
                    song = matches[0]
                    print(
                        f"  Song matched: {winning_title} -> Song #{song.id} "
                        f"(Spotify metadata "
                        f"{'present' if song.spotify_url or song.spotify_track_id else 'not present'})"
                    )

                elif len(matches) == 0:
                    unmatched_songs += 1
                    issues.append(
                        f"History row {row_num}: winning song "
                        f"{winning_title!r} not found in Song table; "
                        "selection can be imported without song link."
                    )

                else:
                    unmatched_songs += 1
                    issues.append(
                        f"History row {row_num}: {len(matches)} Song records "
                        f"have title {winning_title!r}; "
                        "song link left blank until reviewed."
                    )

            existing_selection = next(
                (s for s in selections if s.proposal_id == proposal.id),
                None,
            )
            if existing_selection:
                print(f"  Existing selection found for {theme_name}; not duplicating.")
                continue

            print(
                f"  {'Would add' if not args.apply else 'Add'} selection: {theme_name} | "
                f"{selected_date.isoformat()} | {winning_title or 'no song'} | "
                f"{winner_name or 'no winner'}"
            )
            added_selections += 1
            if args.apply:
                # Keep the existing model API compatible while writing the two optional
                # history links through SQL after the base selection row is inserted.
                selection = FridayThemeWheelSelection(
                    proposal_id=proposal.id,
                    selected_at=datetime.combine(
                        selected_date,
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    ),
                    spun_by_id=poster.id,
                )
                session.add(selection)
                session.flush()
                if not args.no_schema_change:
                    session.execute(text(
                        "UPDATE fridaythemewheelselection "
                        "SET winning_song_id = :song_id, winning_song_title = :song_title, "
                        "winner_id = :winner_id WHERE id = :selection_id"
                    ), {
                        "song_id": song_id,
                        "song_title": winning_title or None,
                        "winner_id": winner.id if winner else None,
                        "selection_id": selection.id,
                    })

        if args.apply:
            session.commit()
            print("\nDatabase transaction committed.")

    print("\nSUMMARY")
    print(f"  Proposals to add / added: {added_proposals}")
    print(f"  Votes to add / added: {added_votes}")
    print(f"  Selections to add / added: {added_selections}")
    print(f"  Winning songs unmatched/ambiguous: {unmatched_songs}")
    print(f"  Issues to review: {len(issues)}")
    if issues:
        print("\nREVIEW THESE ITEMS:")
        for issue in issues:
            print(f"  - {issue}")
    if not args.apply:
        print("\nDry run only: no proposal, vote, or selection records were committed.")
        print("Review the report, fill in USER_MAPPING, back up the database, then rerun with --apply.")
    elif args.no_schema_change:
        print("\nWARNING: --no-schema-change was used, so winning song/winner links were not saved.")
    else:
        print(
            "\nReminder: add winning_song_id and winner_id as optional fields to "
            "FridayThemeWheelSelection in main.py so the API can expose the imported details."
        )


if __name__ == "__main__":
    main()
