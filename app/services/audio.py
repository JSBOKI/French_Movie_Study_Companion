"""Dialogue and vocabulary drill tracks for a scene."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.db import one, session
from app.services.lessons import key_lines
from app.services.tts import concat_mp3, silence, synthesize


def audio_root() -> Path:
    path = config.data_dir() / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate(scene_id: int, kind: str = "both") -> dict:
    row = one("SELECT id, lesson_json, idx FROM scenes WHERE id = ?", (scene_id,))
    if not row or not row["lesson_json"]:
        raise ValueError("Scene not found.")
    import json

    lesson = json.loads(row["lesson_json"])
    kinds = ["dialogue", "vocab"] if kind == "both" else [kind]
    tracks = {}
    for item in kinds:
        if item == "dialogue":
            path = _dialogue(scene_id, lesson)
        elif item == "vocab":
            path = _vocab(scene_id, lesson)
        else:
            raise ValueError("kind must be dialogue, vocab, or both.")
        tracks[item] = str(path)
        with session() as conn:
            conn.execute(
                """
                INSERT INTO audio_tracks (scene_id, kind, path, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scene_id, kind) DO UPDATE SET path = excluded.path, created_at = excluded.created_at
                """,
                (scene_id, item, str(path), datetime.now(timezone.utc).isoformat()),
            )
    return tracks


def track_path(scene_id: int, kind: str) -> Path | None:
    row = one("SELECT path FROM audio_tracks WHERE scene_id = ? AND kind = ?", (scene_id, kind))
    if not row:
        return None
    path = Path(row["path"])
    if path.exists():
        return path
    return None


def _dialogue(scene_id: int, lesson: dict) -> Path:
    parts: list[Path] = []
    work = audio_root() / f"scene-{scene_id}"
    work.mkdir(parents=True, exist_ok=True)
    lines = key_lines(lesson, limit=12)
    gap = silence(0.7, work / "gap-07.mp3")
    for index, line in enumerate(lines):
        speaker = line.get("speaker")
        french = synthesize(line["text"], "fr", speaker=speaker)
        english = synthesize(line["translation"] or line["text"], "en")
        pause = silence(_shadow_pause(line["text"]), work / f"pause-{int(_shadow_pause(line['text']) * 10):02d}.mp3")
        parts.extend([french, pause, english, gap, french, gap])
    dest = work / "dialogue.mp3"
    if not parts:
        raise ValueError("This scene has no lines to read aloud.")
    return concat_mp3(parts, dest)


def _vocab(scene_id: int, lesson: dict) -> Path:
    parts: list[Path] = []
    work = audio_root() / f"scene-{scene_id}"
    work.mkdir(parents=True, exist_ok=True)
    pause = silence(1.3, work / "pause-vocab.mp3")
    gap = silence(0.55, work / "gap-055.mp3")
    items = lesson.get("vocabulary") or []
    if not items:
        raise ValueError("This scene has no vocabulary to drill.")
    for item in items:
        word = synthesize(item.get("audio_text") or item["display"], "fr")
        meaning = synthesize(item["gloss"], "en")
        example = synthesize(item["example_fr"], "fr") if item.get("example_fr") else None
        parts.extend([word, pause, meaning, gap])
        if example:
            parts.extend([example, gap])
    dest = work / "vocab.mp3"
    return concat_mp3(parts, dest)


def _shadow_pause(text: str) -> float:
    words = max(1, len(text.split()))
    return max(1.2, min(4.0, words * 0.42))
