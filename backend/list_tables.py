import sqlite3

connection = sqlite3.connect("mbc_local.db")

tables = connection.execute(
    "SELECT name FROM sqlite_master "
    "WHERE type='table' ORDER BY name"
).fetchall()

print("Database contents:\n")

for (table_name,) in tables:
    # Table names come from SQLite's own table list.
    count = connection.execute(
        f'SELECT COUNT(*) FROM "{table_name}"'
    ).fetchone()[0]

    print(f"{table_name}: {count} records")

connection.close()