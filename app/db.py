import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import get_settings
from .models import Keyword, Project

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    term TEXT NOT NULL COLLATE NOCASE,
    exact_match INTEGER NOT NULL DEFAULT 0,
    UNIQUE(project_id, term)
);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(get_settings().db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def _keywords(conn, project_id: int) -> list[Keyword]:
    rows = conn.execute(
        "SELECT id, term, exact_match FROM keywords WHERE project_id = ? ORDER BY term COLLATE NOCASE",
        (project_id,),
    ).fetchall()
    return [Keyword(id=r["id"], term=r["term"], exact_match=bool(r["exact_match"])) for r in rows]


def list_projects() -> list[Project]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY name COLLATE NOCASE").fetchall()
        return [Project(**dict(r), keywords=_keywords(conn, r["id"])) for r in rows]


def get_project(project_id: int) -> Project | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return Project(**dict(r), keywords=_keywords(conn, r["id"])) if r else None


def create_project(name: str) -> Project:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        cur = conn.execute("INSERT INTO projects (name, created_at) VALUES (?, ?)", (name.strip(), now))
        project_id = cur.lastrowid
    return get_project(project_id)


def rename_project(project_id: int, name: str) -> Project | None:
    with connect() as conn:
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name.strip(), project_id))
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    with connect() as conn:
        return conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount > 0


def add_keyword(project_id: int, term: str, exact_match: bool) -> Keyword:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO keywords (project_id, term, exact_match) VALUES (?, ?, ?)",
            (project_id, term.strip(), int(exact_match)),
        )
        return Keyword(id=cur.lastrowid, term=term.strip(), exact_match=exact_match)


def delete_keyword(project_id: int, keyword_id: int) -> bool:
    with connect() as conn:
        return (
            conn.execute(
                "DELETE FROM keywords WHERE id = ? AND project_id = ?", (keyword_id, project_id)
            ).rowcount
            > 0
        )
