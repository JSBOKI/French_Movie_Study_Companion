"""Turn an uploaded subtitle into ordered scene lessons and flashcards."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from fsrs import Card

from app.config import ROOT
from app.db import one, rows, session
from app.services.lessons import build_scene_lesson
from app.services.scenes import split_scenes
from app.services.subtitles import parse_subtitle
from app.services.translate import translate_movie

SAMPLE_SRT = ROOT / "sample" / "minuit_ligne_6.srt"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def known_lemmas() -> set[str]:
    return {row["lemma"].lower() for row in rows("SELECT lemma FROM known_words")}


def create_movie(payload: dict) -> dict:
    with session() as conn:
        cur = conn.execute(
            """
            INSERT INTO movies
                (title, original_title, year, runtime_min, poster_url, overview, source, external_id, status, progress, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', '', ?)
            """,
            (
                payload["title"].strip(),
                (payload.get("original_title") or payload["title"]).strip(),
                payload.get("year"),
                payload.get("runtime_min"),
                payload.get("poster_url") or "",
                payload.get("overview") or "",
                payload.get("source") or "manual",
                payload.get("external_id") or "",
                now(),
            ),
        )
        movie_id = cur.lastrowid
    found = one("SELECT * FROM movies WHERE id = ?", (movie_id,))
    assert found is not None
    return found


def create_sample() -> dict:
    movie = create_movie(
        {
            "title": "Minuit, ligne 6",
            "original_title": "Minuit, ligne 6",
            "year": 2024,
            "runtime_min": 5,
            "overview": (
                "An original practice short written for this app, not a commercial film. "
                "Léa and Marc miss the last metro and end up in a late-night café. "
                "The dialogue is here so you can try lessons, flashcards, and audio with no subtitle hunt."
            ),
            "source": "sample",
        }
    )
    text = SAMPLE_SRT.read_text(encoding="utf-8")
    process_subtitles(movie["id"], text, "minuit_ligne_6.srt")
    found = one("SELECT * FROM movies WHERE id = ?", (movie["id"],))
    assert found is not None
    return found


def start_processing(movie_id: int, text: str, filename: str) -> None:
    def job() -> None:
        try:
            process_subtitles(movie_id, text, filename)
        except Exception as exc:  # noqa: BLE001 — surface the message in the UI
            _status(movie_id, "error", "Could not build lessons", str(exc))

    threading.Thread(target=job, daemon=True).start()


def process_subtitles(movie_id: int, text: str, filename: str) -> None:
    _status(movie_id, "processing", "Reading the subtitle")
    cues = parse_subtitle(text, filename)
    if len(cues) < 2:
        raise ValueError("That file did not contain enough dialogue to build a lesson.")
    with session() as conn:
        conn.execute("DELETE FROM cards WHERE movie_id = ?", (movie_id,))
        conn.execute("DELETE FROM scenes WHERE movie_id = ?", (movie_id,))
        conn.execute("DELETE FROM cues WHERE movie_id = ?", (movie_id,))
        conn.execute(
            "UPDATE movies SET subtitle_text = ?, subtitle_name = ? WHERE id = ?",
            (text, filename, movie_id),
        )
        for cue in cues:
            conn.execute(
                "INSERT INTO cues (movie_id, idx, start_ms, end_ms, speaker, text) VALUES (?, ?, ?, ?, ?, ?)",
                (movie_id, cue.idx, cue.start_ms, cue.end_ms, cue.speaker, cue.text),
            )
    groups = split_scenes(cues)
    taught: set[str] = set()
    seen_grammar: set[str] = set()
    known = known_lemmas()
    total = len(groups)
    for index, group in enumerate(groups, start=1):
        _status(movie_id, "processing", f"Studying scene {index} of {total}")
        lesson, cards = build_scene_lesson(
            group,
            scene_index=index,
            scene_count=total,
            taught=taught,
            known=known,
            seen_grammar=seen_grammar,
        )
        seen_grammar.update(note["id"] for note in lesson["grammar"])
        with session() as conn:
            cur = conn.execute(
                """
                INSERT INTO scenes (movie_id, idx, start_ms, end_ms, title, lesson_json, studied)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    movie_id,
                    index,
                    group[0].start_ms,
                    group[-1].end_ms,
                    lesson["title"],
                    json.dumps(lesson, ensure_ascii=False),
                ),
            )
            scene_id = cur.lastrowid
            for card in cards:
                conn.execute(
                    """
                    INSERT INTO cards
                        (movie_id, scene_id, lemma, front, back, example_fr, example_en, audio_text,
                         pos, gender, level, fsrs_json, suspended, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        movie_id,
                        scene_id,
                        card["lemma"],
                        card["front"],
                        card["back"],
                        card["example_fr"],
                        card["example_en"],
                        card["audio_text"],
                        card["pos"],
                        card["gender"],
                        card["level"],
                        Card().to_json(),
                        now(),
                    ),
                )
    translate_movie(movie_id, _status)


def rebuild(movie_id: int) -> None:
    movie = one("SELECT subtitle_text, subtitle_name FROM movies WHERE id = ?", (movie_id,))
    if not movie or not movie["subtitle_text"]:
        raise ValueError("This film has no subtitle to rebuild from.")
    start_processing(movie_id, movie["subtitle_text"], movie["subtitle_name"] or "subtitles.srt")


def _status(movie_id: int, status: str, progress: str, error: str | None = None) -> None:
    with session() as conn:
        conn.execute(
            "UPDATE movies SET status = ?, progress = ?, error = ? WHERE id = ?",
            (status, progress, error, movie_id),
        )
