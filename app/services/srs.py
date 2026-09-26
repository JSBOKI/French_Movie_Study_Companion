"""FSRS review scheduling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler

from app.db import one, rows, session

_scheduler = Scheduler(enable_fuzzing=False)


def review_card(card_id: int, rating: int) -> dict:
    if rating not in {1, 2, 3, 4}:
        raise ValueError("Rating must be 1 (again), 2 (hard), 3 (good), or 4 (easy).")
    row = one("SELECT * FROM cards WHERE id = ?", (card_id,))
    if not row:
        raise ValueError("Card not found.")
    card = Card.from_json(row["fsrs_json"])
    updated, _log = _scheduler.review_card(card, Rating(rating))
    payload = updated.to_json()
    with session() as conn:
        conn.execute("UPDATE cards SET fsrs_json = ? WHERE id = ?", (payload, card_id))
    return {
        "card_id": card_id,
        "due": updated.due.isoformat(),
        "state": updated.state.name.lower(),
        "interval": _interval_phrase(updated.due),
    }


def next_card(movie_id: int | None = None, scene_id: int | None = None) -> dict | None:
    due = _due_rows(movie_id, scene_id)
    if not due:
        return None
    return _public(due[0], remaining=len(due))


def stats(movie_id: int | None = None) -> dict:
    due = _due_rows(movie_id, None)
    sql = "SELECT fsrs_json, suspended FROM cards"
    params: tuple = ()
    if movie_id:
        sql += " WHERE movie_id = ?"
        params = (movie_id,)
    all_rows = rows(sql, params)
    upcoming = None
    now = datetime.now(timezone.utc)
    for row in all_rows:
        if row["suspended"]:
            continue
        card = Card.from_json(row["fsrs_json"])
        if card.due > now and (upcoming is None or card.due < upcoming):
            upcoming = card.due
    active = [row for row in all_rows if not row["suspended"]]
    return {
        "due": len(due),
        "total": len(active),
        "next_due": upcoming.isoformat() if upcoming else None,
    }


def _due_rows(movie_id: int | None, scene_id: int | None) -> list[dict]:
    sql = "SELECT cards.*, scenes.idx AS scene_index, movies.title AS movie_title FROM cards JOIN scenes ON scenes.id = cards.scene_id JOIN movies ON movies.id = cards.movie_id WHERE cards.suspended = 0"
    params: list = []
    if movie_id:
        sql += " AND cards.movie_id = ?"
        params.append(movie_id)
    if scene_id:
        sql += " AND cards.scene_id = ?"
        params.append(scene_id)
    now = datetime.now(timezone.utc)
    found = []
    for row in rows(sql, tuple(params)):
        card = Card.from_json(row["fsrs_json"])
        if card.due <= now:
            row["_due"] = card.due
            found.append(row)
    found.sort(key=lambda row: (row["_due"], row["id"]))
    return found


def _public(row: dict, remaining: int) -> dict:
    return {
        "id": row["id"],
        "movie_id": row["movie_id"],
        "movie_title": row["movie_title"],
        "scene_id": row["scene_id"],
        "scene_index": row["scene_index"],
        "lemma": row["lemma"],
        "front": row["front"],
        "back": row["back"],
        "example_fr": row["example_fr"],
        "example_en": row["example_en"],
        "audio_text": row["audio_text"] or row["front"],
        "pos": row["pos"],
        "level": row["level"],
        "remaining": remaining,
    }


def _interval_phrase(due: datetime) -> str:
    delta = due - datetime.now(timezone.utc)
    if delta <= timedelta(minutes=2):
        return "again in a minute"
    if delta < timedelta(hours=1):
        minutes = max(1, int(delta.total_seconds() // 60))
        return f"again in {minutes} min"
    if delta < timedelta(days=1):
        hours = max(1, int(delta.total_seconds() // 3600))
        return f"again in {hours} h"
    days = max(1, delta.days)
    return f"again in {days} day" + ("s" if days != 1 else "")
