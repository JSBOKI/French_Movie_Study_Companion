"""Lessons, review, export, and audio from the original sample subtitle."""

from __future__ import annotations

import io
import subprocess
import zipfile

from app.config import ROOT
from app.services.analyze import analyze_line, line_tip
from app.services.scenes import split_scenes
from app.services.subtitles import parse_subtitle
from app.services.tts import voice_for

SAMPLE = (ROOT / "sample" / "minuit_ligne_6.srt").read_text(encoding="utf-8")


def test_parsers_keep_french_dialogue():
    srt = parse_subtitle(SAMPLE, "minuit.srt")
    assert len(srt) >= 40
    assert srt[0].speaker == "Léa"
    assert "métro" in srt[0].text

    vtt = parse_subtitle(
        "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nLéa : Il y a un café.\n",
        "cafe.vtt",
    )
    assert vtt[0].text == "Il y a un café."
    assert vtt[0].speaker == "Léa"

    ass = parse_subtitle(
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:03.00,Default,Marc,0,0,0,,J'sais pas.\n",
        "cafe.ass",
    )
    assert ass[0].speaker == "Marc"
    assert "J'sais pas" in ass[0].text


def test_sample_splits_into_two_scenes():
    cues = parse_subtitle(SAMPLE, "minuit.srt")
    scenes = split_scenes(cues)
    assert len(scenes) >= 2
    assert len(scenes[0]) >= 8
    assert scenes[1][0].start_ms > scenes[0][-1].end_ms


def test_spoken_french_and_pronunciation_tips():
    line = analyze_line("Léa", 0, 2000, "T'as vu l'heure ? Le dernier métro est déjà parti.")
    notes = {tok.text.lower(): tok.form_note for tok in line.tokens}
    assert "passé composé" in notes["vu"]
    assert any(tok.lemma == "métro" and tok.gender == "m" for tok in line.tokens)
    tip = line_tip("T'as vu l'heure ?")
    assert tip and "tu as" in tip
    liaison = line_tip("On est amis.")
    assert liaison and "Liaison" in liaison
    elision = line_tip("J'habite loin d'ici.")
    assert elision and "Elision" in elision


def test_sample_lessons_cards_and_export(client):
    created = client.post("/api/sample")
    assert created.status_code == 200
    movie_id = created.json()["id"]

    film = client.get(f"/api/movies/{movie_id}")
    assert film.status_code == 200
    body = film.json()
    assert body["scene_count"] >= 2
    assert body["status"] == "ready"

    scene = client.get(f"/api/movies/{movie_id}/scenes/1").json()
    displays = " ".join(item["display"] for item in scene["vocabulary"])
    assert "métro" in displays
    assert any(item["display"].startswith(("le ", "la ", "l'")) for item in scene["vocabulary"])
    grammar = {note["id"] for note in scene["grammar"]}
    assert "passe_compose_imparfait" in grammar
    assert "spoken_french" in grammar
    assert scene["lines"][0]["translation"]
    assert scene["lines"][0]["tokens"]

    later = client.get(f"/api/movies/{movie_id}/scenes/2").json()
    later_lemmas = {item["lemma"] for item in later["vocabulary"]}
    assert "métro" not in later_lemmas
    assert "chelou" in later_lemmas or any(note["id"] == "verlan" for note in later["grammar"])

    known = client.post("/api/known", json={"lemma": "métro", "known": True})
    assert known.status_code == 200
    again = client.get(f"/api/movies/{movie_id}/scenes/1").json()
    assert "métro" not in " ".join(item["display"] for item in again["vocabulary"])

    review = client.get("/api/review/next").json()
    card = review["card"]
    assert card["front"] and card["back"]
    rated = client.post(f"/api/review/{card['id']}", json={"rating": 3})
    assert rated.status_code == 200
    assert "in" in rated.json()["interval"]

    csv_body = client.get(f"/api/movies/{movie_id}/export.csv").content.decode("utf-8-sig")
    assert "French" in csv_body
    assert "English" in csv_body
    package = client.get(f"/api/movies/{movie_id}/export.apkg").content
    assert zipfile.is_zipfile(io.BytesIO(package))


def test_dialogue_mp3(client, monkeypatch):
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True)
    assert ffmpeg.returncode == 0

    def fake_synthesize(text, lang, dest=None, speaker=None):
        from app.services import tts

        path = dest or tts.cached_path(text, lang, speaker)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.stat().st_size < 200:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.12",
                    "-c:a", "libmp3lame", "-q:a", "9", str(path),
                ],
                check=True,
                capture_output=True,
            )
        return path

    monkeypatch.setattr("app.services.audio.synthesize", fake_synthesize)
    movie_id = client.post("/api/sample").json()["id"]
    scene = client.get(f"/api/movies/{movie_id}/scenes/1").json()
    built = client.post(f"/api/scenes/{scene['id']}/audio?kind=dialogue")
    assert built.status_code == 200, built.text
    audio = client.get(f"/api/scenes/{scene['id']}/audio/dialogue.mp3")
    assert audio.status_code == 200
    assert len(audio.content) > 1000
    assert "dialogue" in built.json()["tracks"]


def test_voices_follow_the_speaker():
    assert "Denise" in voice_for("fr", "Léa")
    assert "Henri" in voice_for("fr", "Marc")
    assert voice_for("en", "Léa").startswith("en-")
