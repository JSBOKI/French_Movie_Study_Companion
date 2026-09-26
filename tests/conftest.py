"""Each test gets a fresh SQLite file and data directory."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("TMDB_API_KEY", "")
    monkeypatch.setenv("OPENSUBTITLES_API_KEY", "")
    from app.db import init_db, reset

    reset(tmp_path / "bobine.db")
    init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
