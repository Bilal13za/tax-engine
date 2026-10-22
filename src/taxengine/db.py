"""Database connections and initialisation.

Two SQLite databases, kept strictly separate:
  - tax_knowledge.db : legislation, rules, risks, evidence, procedures,
                       calculation tables, scenarios, sources (the tax library)
  - tax_workdata.db  : taxpayer profiles, assessments, evidence tracking,
                       reconciliations, calculation runs (working data)

Both live under the configured data directory (default: <project>/data,
overridable with TAXENGINE_DATA_DIR). WAL mode; foreign keys enforced.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = PACKAGE_DIR.parent.parent / "schema"


def data_dir() -> Path:
    d = Path(os.environ.get("TAXENGINE_DATA_DIR", PACKAGE_DIR.parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def knowledge_db_path() -> Path:
    return data_dir() / "tax_knowledge.db"


def workdata_db_path() -> Path:
    return data_dir() / "tax_workdata.db"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _schema_applied(conn: sqlite3.Connection, marker_table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (marker_table,)
    )
    return cur.fetchone() is not None


def _apply_schema(conn: sqlite3.Connection, schema_file: Path) -> None:
    with open(schema_file, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.commit()


def get_knowledge_db() -> sqlite3.Connection:
    """Open (creating + initialising on first use) the knowledge database."""
    conn = _connect(knowledge_db_path())
    if not _schema_applied(conn, "tax_rules"):
        _apply_schema(conn, SCHEMA_DIR / "schema_knowledge.sql")
    return conn


def get_workdata_db() -> sqlite3.Connection:
    """Open (creating + initialising on first use) the working-data database."""
    conn = _connect(workdata_db_path())
    if not _schema_applied(conn, "taxpayer_profiles"):
        _apply_schema(conn, SCHEMA_DIR / "schema_workdata.sql")
    return conn


def reset_databases() -> None:
    """Delete both databases (used by tests and fresh installs)."""
    for p in (knowledge_db_path(), workdata_db_path()):
        if p.exists():
            # close WAL sidecars too
            for suffix in ("", "-wal", "-shm", "-journal"):
                q = Path(str(p) + suffix) if suffix else p
                if q.exists():
                    q.unlink()
