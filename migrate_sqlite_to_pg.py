"""One-time migration: copy saved projects from the old SQLite file into PostgreSQL.

Users are NOT copied (Postgres seeds its own demo users on init). Projects are
upserted by id, so running this twice is safe.

Run:  python migrate_sqlite_to_pg.py
"""
import json
import os
import sqlite3

import store

SQLITE = os.path.join(os.path.dirname(__file__), "furnishing_engine.db")


def main():
    if not os.path.isfile(SQLITE):
        print(f"No SQLite file at {SQLITE} — nothing to migrate.")
        return

    store.init_db()  # ensure PG database + tables + seed users exist

    src = sqlite3.connect(SQLITE)
    src.row_factory = sqlite3.Row
    rows = src.execute("SELECT id, name, data FROM projects").fetchall()

    moved = 0
    for r in rows:
        try:
            data = json.loads(r["data"])
        except (json.JSONDecodeError, TypeError):
            print(f"  skip {r['name']!r} (bad JSON)")
            continue
        store.save_project(r["name"], data, r["id"])
        moved += 1

    src.close()
    print(f"Migrated {moved}/{len(rows)} project(s) from SQLite -> PostgreSQL ({store.PG['dbname']}).")


if __name__ == "__main__":
    main()
