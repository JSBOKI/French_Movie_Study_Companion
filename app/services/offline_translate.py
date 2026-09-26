"""Offline French→English sentences via CTranslate2.

The Argos French–English model is downloaded on first use. Only the translation
model and the SentencePiece vocab are kept; torch and stanza are not imported.
Encode, translate, and decode run one sentence at a time under a lock, because
SentencePiece is not safe to share across threads or a large batch.
"""

from __future__ import annotations

import io
import json
import re
import threading
import zipfile
from pathlib import Path

import httpx

from app import config

_INDEX = "https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json"
_lock = threading.Lock()
_translator = None
_processor = None
_ready = False
_error = ""

# Mid-sentence capitals that are ordinary English words, not names.
# "Mexico" is absent on purpose: a place name may stay capitalized.
_COMMON = frozenset(
    """
    a an the and but or if so as at by for from in into of off on onto out over to up with
    about after again against all also am any are aren't as be because been before being
    between both but by can can't come comes coming could did didn't do does doesn't doing
    don don't down during each few further had has hasn't have haven't having he her here
    hers herself him himself his how i if in into is isn't it its itself just me more most
    my myself no nor not now of off on once only or other our ours ourselves out over own
    same she she's should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was wasn't we were we're weren't
    what when where which while who whom why will with won't would you your you're yours
    yourself yourselves
    addendum bed classes class coming go goes going leave leaves left woman women man men
    indifferent people person time day way thing things got get gets make makes made like
    just really very still already again another
    """.split()
)
_ALLOWED_CAP = frozenset({"i", "i'm", "i’ll", "i've", "i’ve", "i'd", "i’d", "i'll", "i’ll"})
_WORD = re.compile(r"[A-Za-zÀ-ÿ]+(?:['’][A-Za-zÀ-ÿ]+)?|[.!?…]")


def _packages_dir() -> Path:
    path = config.data_dir() / "argos" / "packages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def status() -> str:
    if _ready:
        return "ready"
    return _error or "not loaded"


def translation_sane(french: str, english: str) -> bool:
    """Reject empty output and a capitalized ordinary word dropped into the middle."""
    text = (english or "").strip()
    if not text:
        return False
    if "feel:" in text.lower() and "feel" not in (french or "").lower():
        return False
    sentence_start = True
    for match in _WORD.finditer(text):
        piece = match.group(0)
        if piece in ".!?…":
            sentence_start = True
            continue
        if sentence_start:
            sentence_start = False
            continue
        low = piece.lower().replace("’", "'")
        if low in _ALLOWED_CAP or low.startswith("i'"):
            continue
        if piece[:1].isupper() and low in _COMMON:
            return False
    return True


def ensure_model() -> bool:
    """Download the French–English model into DATA_DIR if it is not there yet."""
    global _translator, _processor, _ready, _error
    if _ready:
        return True
    with _lock:
        if _ready:
            return True
        try:
            package = _installed_package() or _download_package()
            import ctranslate2
            import sentencepiece as spm

            _translator = ctranslate2.Translator(
                str(package / "model"),
                device="cpu",
                compute_type="int8",
                inter_threads=1,
                intra_threads=1,
            )
            _processor = spm.SentencePieceProcessor(model_file=str(package / "sentencepiece.model"))
            _ready = True
            _error = ""
            return True
        except Exception as exc:  # noqa: BLE001 — the caller falls back to a labeled gloss
            _error = str(exc)
            _ready = False
            return False


def _installed_package() -> Path | None:
    root = _packages_dir()
    if not root.exists():
        return None
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if not (path / "sentencepiece.model").exists() or not (path / "model" / "model.bin").exists():
            continue
        meta = path / "metadata.json"
        if not meta.exists():
            return path
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("from_code") == "fr" and data.get("to_code") == "en":
            return path
    return None


def _download_package() -> Path:
    response = httpx.get(_INDEX, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    catalog = response.json()
    packages = catalog if isinstance(catalog, list) else catalog.get("packages") or []
    chosen = next(
        item
        for item in packages
        if item.get("from_code") == "fr" and item.get("to_code") == "en"
    )
    payload = None
    for link in chosen.get("links") or []:
        fetched = httpx.get(link, timeout=180.0, follow_redirects=True)
        if fetched.status_code == 200 and fetched.content:
            payload = fetched.content
            break
    if not payload:
        raise RuntimeError("The French–English translation model could not be downloaded.")
    dest = _packages_dir() / "translate-fr_en"
    keep = ("sentencepiece.model", "metadata.json")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/", 1)[-1]
            if name in keep or name.startswith("model/"):
                target = dest / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
    if not (dest / "model" / "model.bin").exists() or not (dest / "sentencepiece.model").exists():
        raise RuntimeError("The translation model archive did not contain a model.")
    return dest


def _translate_one(sentence: str) -> str:
    """Encode, translate, and decode a single sentence. Caller holds _lock."""
    assert _translator is not None and _processor is not None
    if not sentence:
        return ""
    tokens = _processor.encode(sentence, out_type=str)
    translated = _translator.translate_batch(
        [tokens],
        beam_size=1,
        num_hypotheses=1,
        max_batch_size=1,
        batch_type="examples",
        replace_unknowns=True,
    )
    text = _processor.decode_pieces(translated[0].hypotheses[0])
    text = text.replace("▁", " ").replace("_", " ").strip()
    if text.lower().startswith("feel:"):
        text = text.split(":", 1)[1].strip()
    return text


def translate_batch(sentences: list[str]) -> list[str] | None:
    if not sentences:
        return []
    if not ensure_model():
        return None
    output: list[str] = []
    with _lock:
        for sentence in sentences:
            prepared = sentence.replace("’", "'").replace("‘", "'").strip()
            text = _translate_one(prepared)
            if not translation_sane(prepared, text):
                text = _translate_one(prepared)
                if not translation_sane(prepared, text):
                    text = ""
            output.append(text)
    return output
