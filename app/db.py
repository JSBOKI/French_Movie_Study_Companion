"""SQLite persistence for a single local user."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from app import config

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_path: str | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    original_title TEXT,
    year INTEGER,
    runtime_min INTEGER,
    poster_url TEXT,
    overview TEXT,
    source TEXT,
    external_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    progress TEXT,
    error TEXT,
    subtitle_text TEXT,
    subtitle_name TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cues (
    id INTEGER PRIMARY KEY,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    speaker TEXT,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    id INTEGER PRIMARY KEY,
    movie_id INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    title TEXT,
    lesson_json TEXT,
    studied INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    movie_id INTEGER NOT NULL,
    scene_id INTEGER NOT NULL,
    lemma TEXT NOT NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    example_fr TEXT,
    example_en TEXT,
    audio_text TEXT,
    pos TEXT,
    gender TEXT,
    level TEXT,
    fsrs_json TEXT NOT NULL,
    suspended INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS known_words (
    lemma TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translations (
    source TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    provider TEXT
);

CREATE TABLE IF NOT EXISTS audio_tracks (
    id INTEGER PRIMARY KEY,
    scene_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(scene_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_cues_movie ON cues(movie_id, idx);
CREATE INDEX IF NOT EXISTS idx_scenes_movie ON scenes(movie_id, idx);
CREATE INDEX IF NOT EXISTS idx_cards_due ON cards(suspended, movie_id);
"""


def reset(path=None) -> None:
    """Point the database at a new file. Used by tests and startup."""
    global _conn, _path
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
        _path = str(path) if path else None


def _connect() -> sqlite3.Connection:
    global _conn, _path
    target = _path or str(config.data_dir() / "bobine.db")
    if _conn is not None and _path == target:
        return _conn
    if _conn is not None:
        _conn.close()
    _path = target
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _conn = conn
    return conn


def init_db() -> None:
    with _lock:
        _connect()


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with session() as conn:
        found = conn.execute(sql, params).fetchall()
        return [dict(row) for row in found]


def one(sql: str, params: tuple = ()) -> dict | None:
    found = rows(sql, params)
    return found[0] if found else None
