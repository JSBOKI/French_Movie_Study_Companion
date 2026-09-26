"""English for a French line.

The default path is an offline Argos model, run in batches after the lesson is saved.
A word-by-word gloss is only a labeled last resort: it is not cached and not read aloud.
MyMemory is not used once it returns 429. An LLM key can upgrade the Argos English.
"""

from __future__ import annotations

import json
import re

import httpx

from app.config import PACKAGE
from app.db import one, rows, session
from app.services.analyze import Line

_SEED: dict[str, str] | None = None
_mymemory_blocked = False

META_GLOSS = re.compile(
    r"first half|shortened|polite|object pronoun|part of |linking|inverted|spoken form",
    re.I,
)


def _seed() -> dict[str, str]:
    global _SEED
    if _SEED is None:
        path = PACKAGE / "data" / "seed_translations.json"
        _SEED = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _SEED


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'").replace("‘", "'").strip())


_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")


def sentence_pieces(text: str) -> list[str]:
    """Translate clause by clause so a later question is not dropped."""
    parts = [part.strip(" \t-–—") for part in _SENTENCE.findall(text)]
    parts = [part for part in parts if part]
    return parts or [normalize(text)]


def translate_line(line: Line) -> None:
    """Fill a line from the seed or a real cached translation. Never calls the network."""
    key = normalize(line.text)
    seeded = _seed().get(key)
    if seeded:
        line.translation = seeded
        line.translation_kind = "english"
        return
    cached = one(
        "SELECT target, provider FROM translations WHERE source = ? AND provider != 'gloss'",
        (key,),
    )
    if cached and cached["target"].strip():
        line.translation = cached["target"]
        line.translation_kind = "english"
        return
    line.translation = ""
    line.translation_kind = "pending"


def translate_movie(movie_id: int, progress) -> None:
    """Translate every still-pending line, then write the lessons back."""
    from app.services.offline_translate import ensure_model, translate_batch

    scenes = rows(
        "SELECT id, lesson_json FROM scenes WHERE movie_id = ? ORDER BY idx",
        (movie_id,),
    )
    pending: list[str] = []
    seen: set[str] = set()
    parsed = []
    for scene in scenes:
        lesson = json.loads(scene["lesson_json"])
        parsed.append((scene["id"], lesson))
        for line in lesson["lines"]:
            if line.get("translation_kind") == "english" and line.get("translation"):
                continue
            for piece in sentence_pieces(line["text"]):
                key = normalize(piece)
                if key in seen:
                    continue
                seen.add(key)
                pending.append(piece)
    if not pending:
        progress(movie_id, "ready", f"{len(parsed)} scenes ready")
        return

    progress(movie_id, "translating", "Preparing the offline translator")
    done: dict[str, str] = {}
    if ensure_model():
        step = 16
        for start in range(0, len(pending), step):
            chunk = pending[start : start + step]
            progress(movie_id, "translating", f"Translating lines {start + len(chunk)} of {len(pending)}")
            translated = translate_batch(chunk)
            if not translated:
                break
            for source, target in zip(chunk, translated):
                target = target.strip()
                if target:
                    done[normalize(source)] = target
                    _store(normalize(source), target, "argos")
    else:
        _mymemory_fill(pending, done, movie_id, progress)

    still = [text for text in pending if normalize(text) not in done]
    if still:
        progress(movie_id, "translating", "Finishing a few lines word by word")
    _write_back(parsed, done)
    progress(movie_id, "ready", f"{len(parsed)} scenes ready")


def _mymemory_fill(pending: list[str], done: dict[str, str], movie_id: int, progress) -> None:
    global _mymemory_blocked
    for index, text in enumerate(pending, start=1):
        if _mymemory_blocked:
            break
        if index == 1 or index % 20 == 0:
            progress(movie_id, "translating", f"Asking MyMemory ({index} of {len(pending)})")
        translated = _mymemory(normalize(text))
        if translated:
            done[normalize(text)] = translated
            _store(normalize(text), translated, "mymemory")


def _write_back(parsed: list[tuple[int, dict]], done: dict[str, str]) -> None:
    for scene_id, lesson in parsed:
        for line in lesson["lines"]:
            english = _join_translation(line["text"], done)
            if english:
                line["translation"] = english
                line["translation_kind"] = "english"
            elif line.get("translation_kind") != "english":
                line["translation"] = _gloss_line(line)
                line["translation_kind"] = "gloss"
        for item in lesson.get("vocabulary") or []:
            english = _join_translation(item.get("example_fr") or "", done)
            if english:
                item["example_en"] = english
        from app import config

        if config.llm_api_key():
            lesson = enhance_with_llm(lesson)
        with session() as conn:
            conn.execute(
                "UPDATE scenes SET lesson_json = ? WHERE id = ?",
                (json.dumps(lesson, ensure_ascii=False), scene_id),
            )
            for item in lesson.get("vocabulary") or []:
                example_en = item.get("example_en") or ""
                if item.get("pos") == "VERB" and item.get("form_note"):
                    example_en = f"{item['form_note']} — {example_en}" if example_en else item["form_note"]
                conn.execute(
                    "UPDATE cards SET example_en = ? WHERE scene_id = ? AND lemma = ? AND example_fr = ?",
                    (example_en, scene_id, item["lemma"], item.get("example_fr") or ""),
                )


def _join_translation(text: str, done: dict[str, str]) -> str:
    pieces = sentence_pieces(text)
    translated = [done.get(normalize(piece), "") for piece in pieces]
    if pieces and all(translated):
        return " ".join(translated)
    return ""


def _store(source: str, target: str, provider: str) -> None:
    if provider == "gloss":
        return
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO translations (source, target, provider) VALUES (?, ?, ?)",
            (source, target, provider),
        )


def _mymemory(text: str) -> str | None:
    global _mymemory_blocked
    if _mymemory_blocked or not text:
        return None
    if len(text) > 450:
        text = text[:450]
    try:
        response = httpx.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "fr|en"},
            timeout=8.0,
            headers={"User-Agent": "Bobine/1.0 (https://github.com/JSBOKI/French_Movie_Study_Companion)"},
        )
    except httpx.HTTPError:
        return None
    if response.status_code == 429:
        _mymemory_blocked = True
        return None
    try:
        response.raise_for_status()
        translated = (response.json().get("responseData") or {}).get("translatedText") or ""
    except (httpx.HTTPError, ValueError):
        return None
    upper = translated.upper()
    if not translated or "MYMEMORY WARNING" in upper or "QUERY LENGTH" in upper:
        if "429" in upper or "QUOTA" in upper:
            _mymemory_blocked = True
        return None
    return translated


def _gloss_line(line: dict) -> str:
    words = []
    for tok in line.get("tokens") or []:
        if not tok.get("is_word"):
            if tok.get("text") in {".", "?", "!", ",", ";", ":"}:
                words.append(tok["text"])
            continue
        if tok.get("role") in {"closed", "punct", "typo"}:
            continue
        piece = (tok.get("gloss") or "").split(";")[0].split(",")[0].strip()
        piece = re.sub(r"\([^)]*\)", "", piece).strip()
        if not piece or META_GLOSS.search(piece) or piece.lower() in {"verb", "noun", "adjective"}:
            continue
        words.append(piece.removeprefix("to ").strip())
    text = " ".join(words)
    text = re.sub(r"\s+([?.!,;:])", r"\1", text)
    return text[:1].upper() + text[1:] if text else ""


def enhance_with_llm(lesson: dict) -> dict:
    """Optional polish. The offline translation stands on its own if this is skipped."""
    from app import config

    if not config.llm_api_key():
        return lesson
    payload = {
        "lines": [{"fr": line["text"], "en": line.get("translation") or ""} for line in lesson["lines"]],
        "vocabulary": [
            {"lemma": item["lemma"], "gloss": item["gloss"], "sentence": item.get("example_fr") or ""}
            for item in lesson.get("vocabulary") or []
        ],
        "grammar": [{"id": note["id"], "title": note["title"], "explanation": note["explanation"]} for note in lesson["grammar"]],
    }
    system = (
        "You help a beginner English speaker study French from a film scene. "
        "Rewrite the English translations so they sound natural and faithful. "
        "For each vocabulary item, pick the sense that fits the sentence and return it as gloss. "
        "You may lightly edit a grammar explanation so it is clearer, but do not add grammar "
        "that is not already identified, and do not invent lines. "
        "Return JSON only: {\"translations\": {\"<exact French line>\": \"<English>\"}, "
        "\"glosses\": {\"<lemma>\": \"<in-context English>\"}, "
        "\"grammar\": {\"<id>\": \"<explanation>\"}}."
    )
    try:
        response = httpx.post(
            f"{config.llm_base_url()}/chat/completions",
            headers={"Authorization": f"Bearer {config.llm_api_key()}", "Content-Type": "application/json"},
            json={
                "model": config.llm_model(),
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            timeout=40.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```json\s*|\s*```$", "", content.strip())
        data = json.loads(content)
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return lesson
    translations = data.get("translations") or {}
    for line in lesson["lines"]:
        updated = translations.get(line["text"])
        if isinstance(updated, str) and updated.strip():
            line["translation"] = updated.strip()
            line["translation_kind"] = "english"
            _store(normalize(line["text"]), line["translation"], "llm")
    glosses = data.get("glosses") or {}
    for item in lesson.get("vocabulary") or []:
        updated = glosses.get(item["lemma"])
        if isinstance(updated, str) and updated.strip() and updated.strip().lower() not in {"verb", "noun"}:
            item["gloss"] = updated.strip()
    grammar = data.get("grammar") or {}
    for note in lesson["grammar"]:
        updated = grammar.get(note["id"])
        if isinstance(updated, str) and 40 <= len(updated) <= 1200:
            note["explanation"] = updated.strip()
    return lesson
