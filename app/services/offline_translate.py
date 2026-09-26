"""Offline French→English sentences via Argos Translate. The model downloads on first use."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from app import config

_lock = threading.Lock()
_translator = None
_tokenizer = None
_ready = False
_error = ""


def _packages_dir() -> Path:
    path = config.data_dir() / "argos" / "packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def status() -> str:
    if _ready:
        return "ready"
    return _error or "not loaded"


def ensure_model() -> bool:
    """Install the French–English Argos package if it is not already on disk."""
    global _translator, _tokenizer, _ready, _error
    if _ready:
        return True
    with _lock:
        if _ready:
            return True
        os.environ["ARGOS_PACKAGES_DIR"] = str(_packages_dir())
        os.environ["ARGOS_STANZA_AVAILABLE"] = "0"
        try:
            import ctranslate2
            from argostranslate import package, settings

            settings.package_data_dir = _packages_dir()
            settings.package_data_dir.mkdir(parents=True, exist_ok=True)
            settings.package_dirs = [settings.package_data_dir]
            installed = [pkg for pkg in package.get_installed_packages() if pkg.from_code == "fr" and pkg.to_code == "en"]
            if not installed:
                package.update_package_index()
                available = package.get_available_packages()
                chosen = next(pkg for pkg in available if pkg.from_code == "fr" and pkg.to_code == "en")
                chosen.install()
                installed = [pkg for pkg in package.get_installed_packages() if pkg.from_code == "fr" and pkg.to_code == "en"]
            pkg = installed[0]
            model = str(Path(pkg.package_path) / "model")
            _translator = ctranslate2.Translator(model, device="cpu", compute_type="int8", inter_threads=1)
            _tokenizer = pkg.tokenizer
            _ready = True
            _error = ""
            return True
        except Exception as exc:  # noqa: BLE001 — the caller falls back to a labeled gloss
            _error = str(exc)
            _ready = False
            return False


def translate_batch(sentences: list[str]) -> list[str] | None:
    if not sentences:
        return []
    if not ensure_model():
        return None
    assert _translator is not None and _tokenizer is not None
    # Straight apostrophes match the cache key and avoid a bad SentencePiece piece.
    prepared = [sentence.replace("’", "'").replace("‘", "'").strip() for sentence in sentences]
    tokenized = [_tokenizer.encode(sentence) for sentence in prepared]
    translated = _translator.translate_batch(
        tokenized,
        beam_size=1,
        num_hypotheses=1,
        max_batch_size=16,
        batch_type="examples",
        replace_unknowns=True,
    )
    output = []
    for item in translated:
        text = _tokenizer.decode(item.hypotheses[0]).strip()
        if text.lower().startswith("feel:"):
            text = text.split(":", 1)[1].strip()
        output.append(text)
    return output
