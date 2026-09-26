"""Runtime configuration. Every integration is optional; the app runs with none set."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent


def data_dir() -> Path:
    path = Path(os.environ.get("DATA_DIR", ROOT / "data" / "user")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def host() -> str:
    return os.environ.get("HOST", "0.0.0.0")


def port() -> int:
    return int(os.environ.get("PORT", "8000"))


def tmdb_api_key() -> str:
    return os.environ.get("TMDB_API_KEY", "").strip()


def opensubtitles_api_key() -> str:
    return os.environ.get("OPENSUBTITLES_API_KEY", "").strip()


def llm_api_key() -> str:
    return os.environ.get("LLM_API_KEY", "").strip()


def llm_base_url() -> str:
    return os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def llm_model() -> str:
    return os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()


def tts_provider() -> str:
    """edge (default, no key), openai, or espeak."""
    return os.environ.get("TTS_PROVIDER", "edge").strip().lower() or "edge"


def tts_api_key() -> str:
    return os.environ.get("TTS_API_KEY", os.environ.get("OPENAI_API_KEY", "")).strip()


def tts_base_url() -> str:
    return os.environ.get("TTS_BASE_URL", "https://api.openai.com/v1").rstrip("/")


def tts_voice_fr() -> str:
    return os.environ.get("TTS_VOICE_FR", "fr-FR-DeniseNeural")


def tts_voice_fr_male() -> str:
    return os.environ.get("TTS_VOICE_FR_MALE", "fr-FR-HenriNeural")


def tts_voice_en() -> str:
    return os.environ.get("TTS_VOICE_EN", "en-US-JennyNeural")


def tts_rate() -> str:
    return os.environ.get("TTS_RATE", "-8%")


def public_config() -> dict:
    provider = tts_provider()
    return {
        "tmdb": bool(tmdb_api_key()),
        "opensubtitles": bool(opensubtitles_api_key()),
        "llm": bool(llm_api_key()),
        "llm_model": llm_model() if llm_api_key() else None,
        "tts_provider": provider,
        "tts_needs_key": provider == "openai",
        "features_without_keys": [
            "Wikidata and Wikipedia film search",
            "Manual film entry",
            "Subtitle upload (.srt, .vtt, .ass)",
            "Scene lessons, grammar, and glosses",
            "Flashcards with FSRS review",
            "Anki CSV and .apkg export",
            "French and English speech via Edge neural voices (needs network, no key)",
        ],
    }
