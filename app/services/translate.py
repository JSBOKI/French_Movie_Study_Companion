"""English for a French line: curated lines, optional MyMemory, then a study gloss."""

from __future__ import annotations

import json
import re

import httpx

from app.config import PACKAGE
from app.db import one, session
from app.services.analyze import Line

_SEED: dict[str, str] | None = None


def _seed() -> dict[str, str]:
    global _SEED
    if _SEED is None:
        path = PACKAGE / "data" / "seed_translations.json"
        _SEED = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _SEED


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def translate_line(line: Line) -> None:
    key = normalize(line.text)
    seeded = _seed().get(key)
    if seeded:
        line.translation = seeded
        line.translation_kind = "english"
        return
    cached = one("SELECT target, provider FROM translations WHERE source = ?", (key,))
    if cached:
        line.translation = cached["target"]
        line.translation_kind = "english" if cached["provider"] != "gloss" else "gloss"
        return
    remote = _mymemory(key)
    if remote:
        _store(key, remote, "mymemory")
        line.translation = remote
        line.translation_kind = "english"
        return
    gloss = _gloss(line)
    _store(key, gloss, "gloss")
    line.translation = gloss
    line.translation_kind = "gloss"


def _store(source: str, target: str, provider: str) -> None:
    with session() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO translations (source, target, provider) VALUES (?, ?, ?)",
            (source, target, provider),
        )


def _mymemory(text: str) -> str | None:
    if len(text) > 450:
        text = text[:450]
    try:
        response = httpx.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "fr|en"},
            timeout=8.0,
            headers={"User-Agent": "Bobine/1.0 (French film study)"},
        )
        response.raise_for_status()
        payload = response.json()
        translated = (payload.get("responseData") or {}).get("translatedText") or ""
    except (httpx.HTTPError, ValueError):
        return None
    upper = translated.upper()
    if not translated or "MYMEMORY WARNING" in upper or "QUERY LENGTH" in upper:
        return None
    return translated


def _gloss(line: Line) -> str:
    words = []
    for tok in line.tokens:
        if not tok.is_word:
            if tok.text in {".", "?", "!", ",", ";", ":"}:
                words.append(tok.text)
            continue
        gloss = tok.gloss.split(",")[0].split(";")[0].strip()
        gloss = re.sub(r"\([^)]*\)", "", gloss).strip()
        gloss = gloss.removeprefix("to ").strip()
        if gloss:
            words.append(gloss)
        else:
            words.append(tok.text)
    text = " ".join(words)
    text = re.sub(r"\s+([?.!,;:])", r"\1", text)
    return text[:1].upper() + text[1:] if text else line.text


def enhance_with_llm(lesson: dict) -> dict:
    """Optional polish. The rule-based lesson stands on its own if this is skipped."""
    from app import config

    if not config.llm_api_key():
        return lesson
    payload = {
        "lines": [{"fr": line["text"], "en": line["translation"]} for line in lesson["lines"]],
        "grammar": [{"id": note["id"], "title": note["title"], "explanation": note["explanation"]} for note in lesson["grammar"]],
    }
    system = (
        "You help a beginner English speaker study French from a film scene. "
        "Rewrite the English translations so they sound natural and faithful. "
        "You may lightly edit a grammar explanation so it is clearer, but do not add grammar "
        "that is not already identified, and do not invent lines. "
        "Return JSON only: {\"translations\": {\"<exact French line>\": \"<English>\"}, "
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
    grammar = data.get("grammar") or {}
    for note in lesson["grammar"]:
        updated = grammar.get(note["id"])
        if isinstance(updated, str) and 40 <= len(updated) <= 1200:
            note["explanation"] = updated.strip()
    return lesson
