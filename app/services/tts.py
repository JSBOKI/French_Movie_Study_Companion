"""Pluggable text-to-speech. Edge neural voices need no API key."""

from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
from pathlib import Path

import httpx

from app import config

FEMALE_NAMES = {
    "léa", "lea", "marie", "anna", "julie", "emma", "chloé", "chloe", "lucie",
    "nina", "sophie", "camille", "claire", "sarah", "ines", "inès", "manon",
}
MALE_NAMES = {
    "marc", "jean", "paul", "pierre", "luc", "thomas", "hugo", "louis",
    "antoine", "julien", "nicolas", "omar", "alexandre", "simon", "mathieu",
}


def cache_dir() -> Path:
    path = config.data_dir() / "tts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_for(lang: str, speaker: str | None = None) -> str:
    if lang.startswith("en"):
        return config.tts_voice_en()
    name = (speaker or "").strip().lower()
    if name in MALE_NAMES:
        return config.tts_voice_fr_male()
    if name in FEMALE_NAMES:
        return config.tts_voice_fr()
    if speaker:
        # Stable assignment for an unknown name.
        if sum(ord(ch) for ch in name) % 2:
            return config.tts_voice_fr_male()
    return config.tts_voice_fr()


def cached_path(text: str, lang: str, speaker: str | None = None) -> Path:
    voice = voice_for(lang, speaker)
    rate = config.tts_rate() if lang.startswith("fr") else "+0%"
    provider = config.tts_provider()
    key = f"{provider}|{voice}|{rate}|{text.strip()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return cache_dir() / f"{digest}.mp3"


def synthesize(text: str, lang: str, dest: Path | None = None, speaker: str | None = None) -> Path:
    text = " ".join(text.split())
    if not text:
        raise ValueError("Nothing to speak.")
    if len(text) > 600:
        text = text[:600]
    path = dest or cached_path(text, lang, speaker)
    if path.exists() and path.stat().st_size > 400:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    voice = voice_for(lang, speaker)
    provider = config.tts_provider()
    if provider == "openai":
        _openai(text, voice, path)
    elif provider == "espeak":
        _espeak(text, lang, path)
    else:
        try:
            _edge(text, voice, path, config.tts_rate() if lang.startswith("fr") else "+0%")
        except Exception:
            _espeak(text, lang, path)
    if not path.exists() or path.stat().st_size < 200:
        raise RuntimeError("Speech synthesis did not produce an audio file.")
    return path


def _edge(text: str, voice: str, dest: Path, rate: str) -> None:
    import edge_tts

    async def run() -> None:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(dest))

    asyncio.run(run())


def _openai(text: str, voice: str, dest: Path) -> None:
    key = config.tts_api_key()
    if not key:
        raise RuntimeError("TTS_PROVIDER=openai needs TTS_API_KEY or OPENAI_API_KEY.")
    # OpenAI voices are alloy/nova/… Map neural Edge names back to a usable voice.
    openai_voice = "nova" if "Denise" in voice or voice.startswith("fr") else "alloy"
    if voice in {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}:
        openai_voice = voice
    response = httpx.post(
        f"{config.tts_base_url()}/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "gpt-4o-mini-tts", "voice": openai_voice, "input": text},
        timeout=60.0,
    )
    response.raise_for_status()
    dest.write_bytes(response.content)


def _espeak(text: str, lang: str, dest: Path) -> None:
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    ffmpeg = shutil.which("ffmpeg")
    if not espeak or not ffmpeg:
        raise RuntimeError("Edge speech failed and espeak/ffmpeg are not installed.")
    voice = "fr" if lang.startswith("fr") else "en"
    wav = dest.with_suffix(".wav")
    subprocess.run([espeak, "-v", voice, "-s", "135", "-w", str(wav), text], check=True, capture_output=True)
    subprocess.run(
        [ffmpeg, "-y", "-i", str(wav), "-c:a", "libmp3lame", "-q:a", "6", str(dest)],
        check=True,
        capture_output=True,
    )
    wav.unlink(missing_ok=True)


def silence(seconds: float, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 200:
        return dest
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to build the drill audio.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", "-q:a", "7", str(dest),
        ],
        check=True,
        capture_output=True,
    )
    return dest


def concat_mp3(parts: list[Path], dest: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to build the drill audio.")
    list_file = dest.with_suffix(".txt")
    list_file.write_text("".join(f"file '{path}'\n" for path in parts), encoding="utf-8")
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:a", "libmp3lame", "-q:a", "5", str(dest)],
        check=True,
        capture_output=True,
    )
    list_file.unlink(missing_ok=True)
    return dest
