from pathlib import Path
from getpass import getpass
from main import SQLModel

from sqlalchemy import (
    create_engine,
    MetaData,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import make_url


# Database file located beside this script in backend/
BASE_DIR = Path(__file__).resolve().parent
SQLITE_FILE = BASE_DIR / "mbc_local.db"

EXPECTED_TABLES = {
    "user",
    "song",
    "vote",
    "fridaythemeproposal",
    "fridaythemeproposalvote",
    "fridaythemewheelselection",
}


def main():
    if not SQLITE_FILE.exists():
        raise FileNotFoundError(
            f"Could not find database: {SQLITE_FILE}"
        )

    # Connect to SQLite without changing the source database.
    source_engine = create_engine(
        f"sqlite:///{SQLITE_FILE.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    source_meta = MetaData()
    source_meta.reflect(bind=source_engine)

    source_tables = set(source_meta.tables.keys())

    missing = EXPECTED_TABLES - source_tables
    if missing:
        raise RuntimeError(
            "Expected tables missing from SQLite: "
            + ", ".join(sorted(missing))
            + "\nActual tables: "
            + ", ".join(sorted(source_tables))
        )

    print("SQLite database:", SQLITE_FILE)
    print("\nSource row counts:")

    for name in sorted(EXPECTED_TABLES):
        table = source_meta.tables[name]
        with source_engine.connect() as conn:
            count = conn.execute(
                select(table).with_only_columns(
                    text("count(*)")
                )
            ).scalar_one()
        print(f"  {name}: {count}")

    print("\nPaste your Supabase pooler URL.")
    print("It will not be printed or saved by this script.")
    raw_url = getpass("Supabase pooler URL: ").strip()

    if not raw_url:
        raise ValueError("No database URL supplied.")

    url = make_url(raw_url)

    if url.get_backend_name() not in ("postgresql", "postgres"):
        raise ValueError("The URL must connect to PostgreSQL.")

    # Use the psycopg 3 driver installed in Step 1.
    url = url.set(drivername="postgresql+psycopg")

    target_engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 15},
    )

    try:
        # Check the connection and inspect existing destination tables.
        with target_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        target_inspector = inspect(target_engine)
        existing_tables = set(target_inspector.get_table_names())

        # Create missing tables using the reflected SQLite schema.
        # Existing tables are never dropped or recreated.
        selected_meta = MetaData()

        for name in sorted(EXPECTED_TABLES):
            source_meta.tables[name].to_metadata(selected_meta)

        # Create PostgreSQL tables from the application's SQLModel definitions,
        # not from SQLite's reflected schema.
        model_tables = []
        missing_model_tables = []

        for table_name in sorted(EXPECTED_TABLES):
            table = SQLModel.metadata.tables.get(table_name)

            if table is None:
                missing_model_tables.append(table_name)
            else:
                model_tables.append(table)

        if missing_model_tables:
            raise RuntimeError(
                "These tables are missing from main.py's SQLModel definitions: "
                + ", ".join(missing_model_tables)
            )

        SQLModel.metadata.create_all(
            target_engine,
            tables=model_tables,
        )

        target_inspector = inspect(target_engine)

        # Check that existing target schemas can accept the source data.
        for name in sorted(EXPECTED_TABLES):
            source_columns = {
                col["name"]
                for col in inspect(source_engine).get_columns(name)
            }
            target_columns = {
                col["name"]
                for col in target_inspector.get_columns(name)
            }

            missing_columns = source_columns - target_columns
            if missing_columns:
                raise RuntimeError(
                    f"Supabase table {name} is missing columns: "
                    + ", ".join(sorted(missing_columns))
                )

        # Do not merge into populated tables or risk duplicate IDs.
        with target_engine.connect() as conn:
            for name in sorted(EXPECTED_TABLES):
                count = conn.execute(
                    text(f'SELECT count(*) FROM "{name}"')
                ).scalar_one()

                if count:
                    raise RuntimeError(
                        f"Supabase table {name} already has {count} rows. "
                        "Import stopped without inserting data. "
                        "Use an empty destination database or review "
                        "the existing data before proceeding."
                    )

        # Import in dependency order, respecting declared foreign keys.
        ordered_tables = selected_meta.sorted_tables

        with target_engine.begin() as target_conn:
            with source_engine.connect() as source_conn:
                for table in ordered_tables:
                    rows = source_conn.execute(
                        select(source_meta.tables[table.name])
                    ).mappings().all()

                    if rows:
                        target_conn.execute(
                            table.insert(),
                            [dict(row) for row in rows],
                        )

                    print(
                        f"Imported {len(rows)} rows into {table.name}"
                    )

          # Reset serial sequences after importing existing IDs.
        with target_engine.begin() as conn:
            for name in sorted(EXPECTED_TABLES):
                columns = {
                    col["name"]
                    for col in target_inspector.get_columns(name)
                }
                if "id" not in columns:
                    continue

                sequence = conn.execute(
                    text("""
                        SELECT pg_get_serial_sequence(
                            current_schema() || '.' || quote_ident(:table_name),
                            'id'
                        )
                    """),
                    {"table_name": name},
                ).scalar_one_or_none()

                if not sequence:
                    continue

                max_id = conn.execute(
                    text(f'SELECT MAX(id) FROM "{name}"')
                ).scalar_one()

                if max_id is not None:
                    conn.execute(
                        text("SELECT setval(CAST(:seq AS regclass), :val, true)"),
                        {"seq": sequence, "val": max_id},
                    )
        # Verify counts against the original SQLite database.
        print("\nVerification:")
        successful = True

        with target_engine.connect() as target_conn:
            with source_engine.connect() as source_conn:
                for name in sorted(EXPECTED_TABLES):
                    table = source_meta.tables[name]

                    source_count = source_conn.execute(
                        select(text("count(*)")).select_from(table)
                    ).scalar_one()

                    target_count = target_conn.execute(
                        text(f'SELECT count(*) FROM "{name}"')
                    ).scalar_one()

                    okay = source_count == target_count
                    successful = successful and okay

                    print(
                        f"  {name}: SQLite={source_count}, "
                        f"Supabase={target_count} "
                        f"{'OK' if okay else 'MISMATCH'}"
                    )

        if not successful:
            raise RuntimeError("Row count verification failed.")

        print("\nMigration completed successfully.")
        print("Your SQLite database remains unchanged.")

    finally:
        target_engine.dispose()
        source_engine.dispose()


if __name__ == "__main__":
    main()