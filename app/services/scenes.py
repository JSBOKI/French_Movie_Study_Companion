"""Split one film subtitle into study scenes."""

from __future__ import annotations

from app.services.subtitles import Cue

MINUTE = 60_000
TARGET = 10 * MINUTE
MIN_SCENE = 7 * MINUTE
MAX_SCENE = 13 * MINUTE
SHORT_FILM = 16 * MINUTE
CLEAR_GAP = 8_000
SOFT_GAP = 3_500
MIN_CUES = 3
MAX_LINES = 40
TARGET_LINES = 34


def split_scenes(cues: list[Cue]) -> list[list[Cue]]:
    if not cues:
        return []
    total = cues[-1].end_ms - cues[0].start_ms
    if total <= SHORT_FILM:
        cuts = _clear_breaks(cues)
        if cuts:
            scenes = _groups(cues, cuts)
        elif total <= 12 * MINUTE:
            scenes = [cues]
        else:
            scenes = _split_long(cues)
    else:
        scenes = _split_long(cues)
    return _limit_lines(scenes)


def _limit_lines(scenes: list[list[Cue]]) -> list[list[Cue]]:
    """A beginner lesson stays near 30–40 lines, even inside a long stretch of dialogue."""
    limited: list[list[Cue]] = []
    for scene in scenes:
        if len(scene) <= MAX_LINES:
            limited.append(scene)
            continue
        start = 0
        while start < len(scene):
            end = min(len(scene), start + MAX_LINES)
            if end < len(scene):
                window = range(start + 18, end)
                best = max(window, key=lambda i: scene[i].start_ms - scene[i - 1].end_ms, default=end - 1)
                if scene[best].start_ms - scene[best - 1].end_ms >= SOFT_GAP:
                    end = best
            limited.append(scene[start:end])
            start = end
    return [scene for scene in limited if scene]


def _clear_breaks(cues: list[Cue]) -> list[int]:
    """Indexes of the last cue before a real silence. Split AFTER that cue."""
    cuts = []
    for i in range(len(cues) - 1):
        gap = cues[i + 1].start_ms - cues[i].end_ms
        if gap >= CLEAR_GAP and i >= MIN_CUES - 1 and i < len(cues) - MIN_CUES:
            cuts.append(i)
    return cuts


def _groups(cues: list[Cue], cuts: list[int]) -> list[list[Cue]]:
    scenes: list[list[Cue]] = []
    start = 0
    for cut in cuts:
        scenes.append(cues[start : cut + 1])
        start = cut + 1
    if start < len(cues):
        scenes.append(cues[start:])
    return [scene for scene in scenes if scene]


def _split_long(cues: list[Cue]) -> list[list[Cue]]:
    scenes: list[list[Cue]] = []
    start = 0
    while start < len(cues):
        origin = cues[start].start_ms
        window_lo = origin + MIN_SCENE
        window_hi = origin + MAX_SCENE
        target = origin + TARGET
        best_i = None
        best_key = None
        last_in_window = None
        for i in range(start, len(cues) - 1):
            boundary = cues[i].end_ms
            if boundary < window_lo:
                continue
            last_in_window = i
            gap = cues[i + 1].start_ms - boundary
            if boundary > window_hi:
                break
            if gap >= SOFT_GAP:
                # Closer to 10 minutes wins. A longer silence breaks the tie.
                key = (abs(boundary - target), -gap)
                if best_key is None or key < best_key:
                    best_key = key
                    best_i = i
        if best_i is None:
            best_i = last_in_window if last_in_window is not None else len(cues) - 1
        # Fold a tiny leftover into this scene.
        rest_start = best_i + 1
        if rest_start >= len(cues):
            scenes.append(cues[start:])
            break
        rest_dur = cues[-1].end_ms - cues[rest_start].start_ms
        if rest_dur < 4 * MINUTE:
            scenes.append(cues[start:])
            break
        scenes.append(cues[start : best_i + 1])
        start = best_i + 1
    return scenes
