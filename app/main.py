"""HTTP API and the single-page study app."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import config
from app.db import init_db, one, rows, session
from app.services import anki_export, audio, metadata, opensubtitles, pipeline, srs, tts

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Bobine", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()


class MovieIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    original_title: str | None = None
    year: int | None = None
    runtime_min: int | None = None
    poster_url: str | None = None
    overview: str | None = None
    source: str | None = "manual"
    external_id: str | None = None


class KnownIn(BaseModel):
    lemma: str
    known: bool = True


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=4)


class OpenSubIn(BaseModel):
    file_id: int


def _movie_or_404(movie_id: int) -> dict:
    movie = one("SELECT * FROM movies WHERE id = ?", (movie_id,))
    if not movie:
        raise HTTPException(404, "Film not found.")
    movie.pop("subtitle_text", None)
    return movie


def _lesson_for_client(raw: str) -> dict:
    lesson = json.loads(raw)
    known = pipeline.known_lemmas()
    lesson["vocabulary"] = [item for item in lesson["vocabulary"] if item["lemma"].lower() not in known]
    lesson["new_count"] = len(lesson["vocabulary"])
    return lesson


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "name": "Bobine"}


@app.get("/api/config")
def public_config() -> dict:
    return config.public_config()


@app.get("/api/movies")
def list_movies() -> list[dict]:
    movies = rows("SELECT * FROM movies ORDER BY id DESC")
    for movie in movies:
        movie.pop("subtitle_text", None)
        counts = one(
            "SELECT COUNT(*) AS scenes FROM scenes WHERE movie_id = ?",
            (movie["id"],),
        )
        movie["scene_count"] = counts["scenes"] if counts else 0
        movie["due"] = srs.stats(movie["id"])["due"]
    return movies


@app.get("/api/movies/search")
async def search_movies(q: str) -> dict:
    try:
        results = await metadata.search_films(q)
    except Exception as exc:  # noqa: BLE001
        return {"results": [], "error": f"Search failed: {exc}"}
    return {"results": results}


@app.post("/api/movies")
def add_movie(payload: MovieIn) -> dict:
    movie = pipeline.create_movie(payload.model_dump())
    movie.pop("subtitle_text", None)
    return movie


@app.post("/api/sample")
def add_sample() -> dict:
    movie = pipeline.create_sample()
    movie.pop("subtitle_text", None)
    return movie


@app.get("/api/movies/{movie_id}")
def get_movie(movie_id: int) -> dict:
    movie = _movie_or_404(movie_id)
    movie["scene_count"] = one("SELECT COUNT(*) AS n FROM scenes WHERE movie_id = ?", (movie_id,))["n"]
    movie["due"] = srs.stats(movie_id)["due"]
    movie["scenes"] = rows(
        "SELECT id, idx, start_ms, end_ms, title, studied FROM scenes WHERE movie_id = ? ORDER BY idx",
        (movie_id,),
    )
    return movie


@app.delete("/api/movies/{movie_id}")
def delete_movie(movie_id: int) -> dict:
    _movie_or_404(movie_id)
    with session() as conn:
        conn.execute("DELETE FROM cards WHERE movie_id = ?", (movie_id,))
        conn.execute("DELETE FROM audio_tracks WHERE scene_id IN (SELECT id FROM scenes WHERE movie_id = ?)", (movie_id,))
        conn.execute("DELETE FROM scenes WHERE movie_id = ?", (movie_id,))
        conn.execute("DELETE FROM cues WHERE movie_id = ?", (movie_id,))
        conn.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
    return {"ok": True}


@app.post("/api/movies/{movie_id}/subtitles")
async def upload_subtitles(movie_id: int, file: UploadFile = File(...)) -> dict:
    _movie_or_404(movie_id)
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "That subtitle file is larger than 8 MB.")
    text = _decode(data)
    pipeline.start_processing(movie_id, text, file.filename or "subtitles.srt")
    return {"ok": True, "status": "processing"}


@app.post("/api/movies/{movie_id}/rebuild")
def rebuild_movie(movie_id: int) -> dict:
    _movie_or_404(movie_id)
    try:
        pipeline.rebuild(movie_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "status": "processing"}


@app.get("/api/movies/{movie_id}/scenes/{idx}")
def get_scene(movie_id: int, idx: int) -> dict:
    row = one(
        "SELECT * FROM scenes WHERE movie_id = ? AND idx = ?",
        (movie_id, idx),
    )
    if not row or not row["lesson_json"]:
        raise HTTPException(404, "Scene not found.")
    lesson = _lesson_for_client(row["lesson_json"])
    lesson["id"] = row["id"]
    lesson["studied"] = bool(row["studied"])
    lesson["movie_id"] = movie_id
    movie = one("SELECT title, original_title FROM movies WHERE id = ?", (movie_id,))
    lesson["movie_title"] = movie["title"] if movie else ""
    fresh = one("SELECT status, progress FROM movies WHERE id = ?", (movie_id,))
    if fresh:
        lesson["movie_status"] = fresh["status"]
        lesson["movie_progress"] = fresh["progress"] or ""
    tracks = rows("SELECT kind FROM audio_tracks WHERE scene_id = ?", (row["id"],))
    lesson["audio"] = [track["kind"] for track in tracks]
    return lesson


@app.post("/api/scenes/{scene_id}/studied")
def mark_studied(scene_id: int) -> dict:
    with session() as conn:
        conn.execute("UPDATE scenes SET studied = 1 WHERE id = ?", (scene_id,))
    return {"ok": True}


@app.get("/api/known")
def list_known() -> dict:
    return {"lemmas": [row["lemma"] for row in rows("SELECT lemma FROM known_words ORDER BY lemma")]}


@app.post("/api/known")
def set_known(payload: KnownIn) -> dict:
    lemma = payload.lemma.strip().lower()
    if not lemma:
        raise HTTPException(400, "Missing word.")
    with session() as conn:
        if payload.known:
            conn.execute(
                "INSERT OR IGNORE INTO known_words (lemma, created_at) VALUES (?, datetime('now'))",
                (lemma,),
            )
            conn.execute("UPDATE cards SET suspended = 1 WHERE lower(lemma) = ?", (lemma,))
        else:
            conn.execute("DELETE FROM known_words WHERE lemma = ?", (lemma,))
            conn.execute("UPDATE cards SET suspended = 0 WHERE lower(lemma) = ?", (lemma,))
    return {"ok": True, "lemma": lemma, "known": payload.known}


@app.get("/api/review/next")
def review_next(movie_id: int | None = None, scene_id: int | None = None) -> dict:
    card = srs.next_card(movie_id, scene_id)
    return {"card": card, "stats": srs.stats(movie_id)}


@app.post("/api/review/{card_id}")
def review_rate(card_id: int, payload: ReviewIn) -> dict:
    try:
        result = srs.review_card(card_id, payload.rating)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@app.get("/api/review/stats")
def review_stats(movie_id: int | None = None) -> dict:
    return srs.stats(movie_id)


@app.get("/api/movies/{movie_id}/export.csv")
def export_csv(movie_id: int) -> Response:
    _movie_or_404(movie_id)
    body = anki_export.render_csv(movie_id)
    return Response(
        content="\ufeff" + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="bobine-{movie_id}.csv"'},
    )


@app.get("/api/movies/{movie_id}/export.apkg")
def export_apkg(movie_id: int) -> Response:
    _movie_or_404(movie_id)
    body = anki_export.render_apkg(movie_id)
    return Response(
        content=body,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="bobine-{movie_id}.apkg"'},
    )


@app.post("/api/scenes/{scene_id}/audio")
def build_audio(scene_id: int, kind: str = "both") -> dict:
    try:
        tracks = audio.generate(scene_id, kind)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Could not build audio: {exc}") from exc
    return {"ok": True, "tracks": list(tracks)}


@app.get("/api/scenes/{scene_id}/audio/{kind}.mp3")
def get_audio(scene_id: int, kind: str) -> FileResponse:
    if kind not in {"dialogue", "vocab"}:
        raise HTTPException(404, "Unknown track.")
    path = audio.track_path(scene_id, kind)
    if not path:
        raise HTTPException(404, "Generate this track first.")
    return FileResponse(path, media_type="audio/mpeg", filename=f"scene-{scene_id}-{kind}.mp3")


@app.get("/api/tts")
def speak(text: str, lang: str = "fr", speaker: str | None = None) -> FileResponse:
    if not text.strip():
        raise HTTPException(400, "Missing text.")
    try:
        path = tts.synthesize(text, lang, speaker=speaker)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Speech failed: {exc}") from exc
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/opensubtitles/search")
def opensub_search(q: str) -> dict:
    try:
        return {"results": opensubtitles.search(q)}
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"OpenSubtitles search failed: {exc}") from exc


@app.post("/api/movies/{movie_id}/opensubtitles")
def opensub_import(movie_id: int, payload: OpenSubIn) -> dict:
    _movie_or_404(movie_id)
    try:
        filename, text = opensubtitles.download(payload.file_id)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"OpenSubtitles download failed: {exc}") from exc
    pipeline.start_processing(movie_id, text, filename)
    return {"ok": True, "filename": filename, "status": "processing"}


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
