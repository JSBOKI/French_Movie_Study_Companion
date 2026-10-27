"""Parsers for SRT, WebVTT, and ASS/SSA subtitle files."""

from __future__ import annotations

import re
from dataclasses import dataclass

TS = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})"
)
ASS_TS = re.compile(r"(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})\.(?P<cs>\d{1,2})")
SPEAKER_RE = re.compile(
    r"^\s*(?:[-–]\s*)?(?P<name>[A-ZÀ-Ý][\wÀ-ÿ'’.\-]{0,30})\s*:\s*(?P<body>.+)$",
    re.DOTALL,
)
SOUND_WORD = re.compile(
    r"musique|music|rire|rires|bruit|applaud|soupir|silence|bruitage|chant|sonnerie|porte qui",
    re.I,
)


@dataclass
class Cue:
    idx: int
    start_ms: int
    end_ms: int
    speaker: str | None
    text: str


def _ms(h: str, m: str, s: str, frac: str, width: int) -> int:
    frac = (frac + "000")[:3] if width == 3 else str(int(frac) * (10 if len(frac) == 2 else 100)).zfill(3)
    # width 3: milliseconds already. width 2: centiseconds.
    if width == 2:
        frac = str(int(frac) * (10 if len(frac) == 2 else 1)).zfill(3)[:3]
        # redo cleanly
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000


def parse_timestamp(value: str) -> int | None:
    value = value.strip()
    match = TS.search(value)
    if match:
        frac = match.group("ms")
        ms = int((frac + "000")[:3])
        return ((int(match.group("h")) * 60 + int(match.group("m"))) * 60 + int(match.group("s"))) * 1000 + ms
    match = ASS_TS.search(value)
    if match:
        cs = int(match.group("cs"))
        ms = cs * 10 if len(match.group("cs")) == 2 else cs * 100
        return ((int(match.group("h")) * 60 + int(match.group("m"))) * 60 + int(match.group("s"))) * 1000 + ms
    return None


def clean_markup(text: str) -> str:
    text = text.replace("\\N", " ").replace("\\n", " ").replace("\u2028", " ")
    text = re.sub(r"\{[^}]*\}", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&#39;", "'").replace("&apos;", "'").replace("&quot;", '"')
    text = re.sub(r"[\[\(]([^\]\)]{0,80})[\]\)]", _drop_note, text)
    text = text.replace("♪", " ").replace("♫", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _drop_note(match: re.Match) -> str:
    inner = match.group(1).strip()
    if SOUND_WORD.search(inner) or len(inner.split()) <= 3:
        return " "
    return " "


def split_speaker(text: str) -> tuple[str | None, str]:
    match = SPEAKER_RE.match(text.strip())
    if not match:
        return None, text.strip()
    name = match.group("name").strip()
    # Avoid treating a normal sentence as a name. Names in these files are short.
    if name.lower() in {"il", "elle", "on", "je", "tu", "nous", "vous", "ils", "elles", "et", "mais", "oui"}:
        return None, text.strip()
    return name, re.sub(r"\s+", " ", match.group("body")).strip()


def _accept(text: str) -> str | None:
    text = clean_markup(text)
    if not text or SOUND_WORD.fullmatch(text):
        return None
    speaker, body = split_speaker(text)
    if not body:
        return None
    return body if speaker is None else f"{speaker}::{body}"


def _cue_from_body(idx: int, start: int, end: int, raw: str) -> Cue | None:
    cleaned = clean_markup(raw)
    if not cleaned:
        return None
    speaker, body = split_speaker(cleaned)
    if not body:
        return None
    return Cue(idx, start, end, speaker, body)


def parse_srt(text: str) -> list[Cue]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        time_idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_idx is None:
            continue
        left, right = lines[time_idx].split("-->", 1)
        start = parse_timestamp(left)
        end = parse_timestamp(right)
        if start is None or end is None:
            continue
        body = " ".join(lines[time_idx + 1 :])
        cue = _cue_from_body(len(cues), start, end, body)
        if cue:
            cues.append(cue)
    return cues


def parse_vtt(text: str) -> list[Cue]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    cues: list[Cue] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        left, right = line.split("-->", 1)
        start = parse_timestamp(left)
        end = parse_timestamp(right.split()[0] if right.strip() else right)
        i += 1
        body_lines = []
        while i < len(lines) and lines[i].strip():
            body_lines.append(lines[i].strip())
            i += 1
        if start is None or end is None:
            continue
        cue = _cue_from_body(len(cues), start, end, " ".join(body_lines))
        if cue:
            cues.append(cue)
    return cues


def parse_ass(text: str) -> list[Cue]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    name_idx = 4
    text_idx = 9
    cues: list[Cue] = []
    for line in text.split("\n"):
        raw = line.strip()
        if raw.lower().startswith("format:") and "dialogue" not in raw.lower():
            # The events format line.
            if "text" in raw.lower():
                cols = [c.strip().lower() for c in raw.split(":", 1)[1].split(",")]
                if "name" in cols:
                    name_idx = cols.index("name")
                if "text" in cols:
                    text_idx = cols.index("text")
            continue
        if not raw.lower().startswith("dialogue:"):
            continue
        payload = raw.split(":", 1)[1].strip()
        parts = payload.split(",", max(text_idx, name_idx) + 1)
        # Text is the remainder after text_idx splits. split with maxsplit keeps the tail.
        parts = payload.split(",", text_idx)
        if len(parts) <= text_idx:
            continue
        # Re-split the prefix for the name and times.
        prefix = payload.split(",")
        if len(prefix) <= text_idx:
            continue
        start = parse_timestamp(prefix[1]) if len(prefix) > 1 else None
        end = parse_timestamp(prefix[2]) if len(prefix) > 2 else None
        name = prefix[name_idx].strip() if len(prefix) > name_idx else ""
        body = prefix[text_idx] if len(prefix) > text_idx else ""
        # When text contains commas, prefix[text_idx] is only the first chunk
        # if we didn't limit the split. Rebuild from the limited split.
        body = parts[-1]
        if start is None or end is None:
            continue
        if name and name.lower() not in {"", "default", "*default"}:
            body = f"{name}: {body}"
        cue = _cue_from_body(len(cues), start, end, body)
        if cue:
            cues.append(cue)
    return cues


def parse_subtitle(text: str, filename: str = "") -> list[Cue]:
    name = filename.lower()
    head = text.lstrip("\ufeff")[:200].lower()
    if name.endswith(".vtt") or head.startswith("webvtt"):
        return parse_vtt(text)
    if name.endswith(".ass") or name.endswith(".ssa") or "[events]" in head or "dialogue:" in head[:500].lower():
        # SRT files don't contain Dialogue: at the top. A real ASS file does.
        if name.endswith(".ass") or name.endswith(".ssa") or "[script info]" in head or "[events]" in head:
            return parse_ass(text)
    return parse_srt(text)
