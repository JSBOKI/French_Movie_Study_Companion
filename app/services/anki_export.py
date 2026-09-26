"""Anki CSV and .apkg exports."""

from __future__ import annotations

import csv
import io
import random
from pathlib import Path

import genanki

from app.db import one, rows

MODEL_ID = 1607392321


def _model() -> genanki.Model:
    return genanki.Model(
        MODEL_ID,
        "Bobine French",
        fields=[
            {"name": "French"},
            {"name": "English"},
            {"name": "ExampleFR"},
            {"name": "ExampleEN"},
            {"name": "Audio"},
        ],
        templates=[
            {
                "name": "Recognition",
                "qfmt": '<div class="fr">{{French}}</div><br>{{Audio}}',
                "afmt": '{{FrontSide}}<hr id="answer"><div class="en">{{English}}</div><br><div class="ex">{{ExampleFR}}</div><div class="ex">{{ExampleEN}}</div>',
            }
        ],
        css=(
            ".card { font-family: Georgia, serif; font-size: 22px; text-align: center; color: #1e1a16; background: #f7f3ec; }"
            ".fr { font-size: 32px; }"
            ".en { font-family: sans-serif; font-size: 20px; }"
            ".ex { font-size: 16px; color: #5c564e; margin-top: 8px; }"
        ),
    )


def cards_for_export(movie_id: int) -> list[dict]:
    return rows(
        """
        SELECT cards.*, scenes.idx AS scene_index, movies.title AS movie_title
        FROM cards
        JOIN scenes ON scenes.id = cards.scene_id
        JOIN movies ON movies.id = cards.movie_id
        WHERE cards.movie_id = ? AND cards.suspended = 0
        ORDER BY scenes.idx, cards.id
        """,
        (movie_id,),
    )


def render_csv(movie_id: int) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["French", "English", "Example French", "Example English", "Movie", "Scene", "Level", "POS"])
    for card in cards_for_export(movie_id):
        writer.writerow(
            [
                card["front"],
                card["back"],
                card["example_fr"],
                card["example_en"],
                card["movie_title"],
                card["scene_index"],
                card["level"],
                card["pos"],
            ]
        )
    return buffer.getvalue()


def render_apkg(movie_id: int) -> bytes:
    movie = one("SELECT title FROM movies WHERE id = ?", (movie_id,))
    title = movie["title"] if movie else "Bobine"
    deck = genanki.Deck(random.randrange(1 << 30), f"Bobine — {title}")
    model = _model()
    media: list[str] = []
    for card in cards_for_export(movie_id):
        audio_field = ""
        path = card.get("audio_text")
        # Audio files are added when a cached pronunciation already exists.
        cached = _cached_audio(card["audio_text"] or card["front"])
        if cached:
            media.append(str(cached))
            audio_field = f"[sound:{cached.name}]"
        note = genanki.Note(
            model=model,
            fields=[card["front"], card["back"], card["example_fr"] or "", card["example_en"] or "", audio_field],
            tags=["bobine", f"scene{card['scene_index']}", (card["level"] or "unrated").lower()],
            guid=genanki.guid_for("bobine", str(movie_id), card["lemma"]),
        )
        deck.add_note(note)
    package = genanki.Package(deck)
    package.media_files = media
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(suffix=".apkg") as handle:
        package.write_to_file(handle.name)
        return Path(handle.name).read_bytes()


def _cached_audio(text: str) -> Path | None:
    from app.services.tts import cached_path

    path = cached_path(text, "fr")
    if path.exists() and path.stat().st_size > 500:
        return path
    return None
