"""Session / persistence (component 7 + user_responses).

Saved projects are persisted to PostgreSQL. A project bundles its areas,
placements, and the final selection (choices + measurements + computed values) for
each placement — the full interview result — stored as one JSONB document.

Connection is configured via environment variables (with local defaults):
    FE_PG_HOST (localhost)  FE_PG_PORT (5432)  FE_PG_USER (postgres)
    FE_PG_PASSWORD (postgres)  FE_PG_DB (furnishing_engine)
The target database is created automatically on first run.
"""
import os
import time
import uuid
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

PG = {
    "host": os.environ.get("FE_PG_HOST", "localhost"),
    "port": int(os.environ.get("FE_PG_PORT", "5432")),
    "user": os.environ.get("FE_PG_USER", "postgres"),
    "password": os.environ.get("FE_PG_PASSWORD", "postgres"),
    "dbname": os.environ.get("FE_PG_DB", "furnishing_engine"),
}

SEED_USERS = [
    ("Ramesh", "supervisor", "1111"),
    ("Sita", "measurer", "2222"),
    ("Imran", "tailor", "3333"),
    ("Arjun", "installer", "4444"),
    ("Vijay", "installer", "5555"),
]


def _ensure_database():
    """Create the target database if it does not exist (connect via 'postgres')."""
    params = {**PG, "dbname": "postgres"}
    conn = psycopg2.connect(**params)
    conn.autocommit = True  # CREATE DATABASE cannot run inside a transaction
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG["dbname"],))
            if not cur.fetchone():
                cur.execute(f'CREATE DATABASE "{PG["dbname"]}"')
    finally:
        conn.close()


@contextmanager
def _cursor():
    """Yield a dict-cursor; commit (or roll back) and close the connection on exit."""
    conn = psycopg2.connect(**PG)
    try:
        with conn:  # commits on success, rolls back on exception
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()


def init_db():
    _ensure_database()
    with _cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                data        JSONB NOT NULL,   -- full project JSON (areas/placements/selections)
                created_at  BIGINT NOT NULL,
                updated_at  BIGINT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id    TEXT PRIMARY KEY,
                name  TEXT NOT NULL,
                role  TEXT NOT NULL,        -- supervisor | measurer | tailor | installer
                pin   TEXT NOT NULL
            )
            """
        )
        cur.execute("SELECT COUNT(*) AS n FROM users")
        if cur.fetchone()["n"] == 0:
            for name, role, pin in SEED_USERS:
                cur.execute(
                    "INSERT INTO users (id, name, role, pin) VALUES (%s,%s,%s,%s)",
                    (str(uuid.uuid4()), name, role, pin),
                )


def save_project(name: str, data: dict, project_id: str | None = None) -> str:
    now = int(time.time())
    pid = project_id or str(uuid.uuid4())
    payload = psycopg2.extras.Json(data)
    with _cursor() as cur:
        cur.execute("SELECT id FROM projects WHERE id = %s", (pid,))
        if cur.fetchone():
            cur.execute(
                "UPDATE projects SET name = %s, data = %s, updated_at = %s WHERE id = %s",
                (name, payload, now, pid),
            )
        else:
            cur.execute(
                "INSERT INTO projects (id, name, data, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                (pid, name, payload, now, now),
            )
    return pid


def list_projects():
    with _cursor() as cur:
        cur.execute(
            "SELECT id, name, created_at, updated_at FROM projects ORDER BY updated_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def get_project(project_id: str):
    with _cursor() as cur:
        cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
        row = cur.fetchone()
    if not row:
        return None
    return dict(row)  # row["data"] is already parsed from JSONB into a dict


def delete_project(project_id: str):
    with _cursor() as cur:
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))


def delete_all_projects():
    with _cursor() as cur:
        cur.execute("DELETE FROM projects")


# ---------------------------------------------------------------- users / login
def list_users():
    with _cursor() as cur:
        cur.execute("SELECT id, name, role FROM users ORDER BY role, name")
        return [dict(r) for r in cur.fetchall()]


def login(name: str, pin: str):
    with _cursor() as cur:
        cur.execute("SELECT id, name, role FROM users WHERE name = %s AND pin = %s", (name, pin))
        r = cur.fetchone()
    return dict(r) if r else None


def add_user(name: str, role: str, pin: str) -> str:
    uid = str(uuid.uuid4())
    with _cursor() as cur:
        cur.execute("INSERT INTO users (id, name, role, pin) VALUES (%s,%s,%s,%s)", (uid, name, role, pin))
    return uid


def delete_user(user_id: str):
    with _cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))


# ------------------------------------------------------ granular per-item update
def patch_item(project_id: str, item_id: str, updates: dict) -> bool:
    """Update fields on ONE placement (by id) inside a project — used for task
    assignment / status / photos so two workers don't overwrite the whole project.
    `updates` keys are dotted paths, e.g. {"assign.prep": "<uid>", "work.status": "done"}."""
    with _cursor() as cur:
        cur.execute("SELECT data FROM projects WHERE id = %s", (project_id,))
        row = cur.fetchone()
        if not row:
            return False
        data = row["data"]  # already a dict from JSONB
        target = None
        for room in data.get("rooms", []):
            for p in room.get("placements", []):
                if p.get("id") == item_id:
                    target = p
                    break
            if target:
                break
        if target is None:
            return False
        for dotted, value in updates.items():
            keys = dotted.split(".")
            obj = target
            for k in keys[:-1]:
                obj = obj.setdefault(k, {})
            obj[keys[-1]] = value
        cur.execute(
            "UPDATE projects SET data = %s, updated_at = %s WHERE id = %s",
            (psycopg2.extras.Json(data), int(time.time()), project_id),
        )
    return True
