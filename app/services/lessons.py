"""Build a scene lesson: new vocabulary, the grammar that actually appears, and glossed lines."""

from __future__ import annotations

import re
from collections import defaultdict

from app.services.analyze import Line, Tok, analyze_line, display_noun, plural_headword, pos_label
from app.services.grammar import Note, detect_grammar
from app.services.lexicon import SKIP_LEMMAS, entry, level_for, level_label, noun_phrase, rank_of
from app.services.scenes import lesson_length
from app.services.subtitles import Cue
from app.services.translate import translate_line

EXPRESSIONS = [
    ("il n'y a plus", "il n'y a plus", "there is no longer", "il n'y a plus"),
    ("il y a", "il y a", "there is, there are", "il y a"),
    ("y'a", "il y a", "there is, there are (spoken y'a)", "y'a"),
    ("s'il vous plaît", "s'il vous plaît", "please (polite)", "s'il vous plaît"),
    ("s'il te plaît", "s'il te plaît", "please (to a friend)", "s'il te plaît"),
    ("qu'est-ce qu'il y a", "qu'est-ce qu'il y a", "what's the matter?", "qu'est-ce qu'il y a"),
    ("qu'est-ce qui", "qu'est-ce qui", "what (question phrase)", "qu'est-ce qui"),
    ("qu'est-ce que", "qu'est-ce que", "what (question phrase)", "qu'est-ce que"),
    ("tout à l'heure", "tout à l'heure", "a moment ago, or in a little while", "tout à l'heure"),
    ("d'accord", "d'accord", "OK, all right", "d'accord"),
    ("je ne sais pas", "je ne sais pas", "I don't know", "je ne sais pas"),
    ("s'il vous plaît", "s'il vous plaît", "please (polite)", "s'il vous plaît"),
    ("tout de même", "tout de même", "all the same, even so", "tout de même"),
    ("je vous en supplie", "je vous en supplie", "I'm begging you", "je vous en supplie"),
    ("tandis que", "tandis que", "whereas, while", "tandis que"),
    ("quelqu'un", "quelqu'un", "someone", "quelqu'un"),
    ("faire attention à", "faire attention (à)", "to be careful; to pay attention", "faire attention"),
    ("faire attention", "faire attention (à)", "to be careful; to pay attention", "faire attention"),
    ("s'occuper de", "s'occuper de", "to take care of; to deal with", "s'occuper de"),
    ("se promener", "se promener", "to go for a walk", "se promener"),
    ("on a été coupés", "on a été coupé", "we got cut off", "on a été coupé"),
    ("on a été coupées", "on a été coupé", "we got cut off", "on a été coupé"),
    ("on a été coupée", "on a été coupé", "we got cut off", "on a été coupé"),
    ("on a été coupé", "on a été coupé", "we got cut off", "on a été coupé"),
    ("en pleine forme", "en pleine forme", "in great shape", "en pleine forme"),
]

CONTENT = {"NOUN", "VERB", "ADJ", "ADV", "INTJ"}


def build_scene_lesson(
    cues: list[Cue],
    *,
    scene_index: int,
    scene_count: int,
    taught: set[str],
    known: set[str],
    seen_grammar: set[str] | None = None,
) -> tuple[dict, list[dict]]:
    lines = [_prepare(cue) for cue in cues]
    vocab, taught_now = _vocabulary(lines, taught=taught, known=known)
    carried = _count_carried(lines, taught)
    grammar = detect_grammar(lines, seen_grammar)
    overview, grammar_points = _overview(scene_index, vocab, grammar, carried)
    start = cues[0].start_ms
    end = cues[-1].end_ms
    title = _scene_title(vocab, lines, scene_index)
    lesson = {
        "scene_index": scene_index,
        "scene_count": scene_count,
        "title": title,
        "time_label": f"{_clock(start)}–{_clock(end)} · {lesson_length(start, end)}",
        "start_ms": start,
        "end_ms": end,
        "overview": overview,
        "grammar_points": grammar_points,
        "new_count": len(vocab),
        "carried_over": carried,
        "vocabulary": vocab,
        "grammar": [
            {
                "id": note.id,
                "title": note.title,
                "explanation": note.explanation,
                "examples": note.examples,
                "review": note.review,
            }
            for note in grammar
        ],
        "voice_mode": _voice_mode(lines),
        "lines": [_line_json(line) for line in lines],
    }
    cards = [_card(item, scene_index) for item in vocab]
    for lemma in taught_now:
        taught.add(lemma)
    return lesson, cards


def _prepare(cue: Cue) -> Line:
    line = analyze_line(cue.speaker, cue.start_ms, cue.end_ms, cue.text)
    translate_line(line)
    # Grammar examples want the translation, so fill tips that quote English later.
    for token in line.tokens:
        if token.gloss and line.translation_kind == "english":
            pass
    return line


def _vocabulary(lines: list[Line], *, taught: set[str], known: set[str]) -> tuple[list[dict], set[str]]:
    buckets: dict[str, dict] = {}
    for line_index, line in enumerate(lines):
        for tok in line.tokens:
            if not _keep_token(tok):
                continue
            key = tok.lemma.lower()
            if key in known or key in taught or key in SKIP_LEMMAS:
                continue
            slot = buckets.setdefault(
                key,
                {
                    "lemma": tok.lemma,
                    "pos": tok.pos,
                    "gender": tok.gender,
                    "gloss": tok.gloss,
                    "slang": tok.slang,
                    "count": 0,
                    "forms": [],
                    "example": line,
                    "surface": tok.text,
                    "form_note": tok.form_note,
                    "audio": "",
                    "pronominal": False,
                    "early": line_index < 4,
                },
            )
            if line_index < 4:
                slot["early"] = True
            slot["count"] += 1
            if tok.form_note and tok.form_note not in slot["forms"]:
                slot["forms"].append(tok.form_note)
            if tok.gender and not slot["gender"]:
                slot["gender"] = tok.gender
            if tok.pronominal:
                slot["pronominal"] = True
            if _prefer_example(line, tok, slot):
                slot["form_note"] = tok.form_note
                slot["surface"] = tok.text
                slot["example"] = line

    ranked = []
    for key, slot in buckets.items():
        found = entry(slot["lemma"]) or {}
        pos = slot["pos"] or found.get("p") or ""
        if pos not in CONTENT:
            continue
        # Dictionary gender. Pendule is the exception: the article changes the meaning.
        if slot["lemma"].lower() == "pendule":
            gender = slot["gender"] or found.get("g") or ""
        else:
            gender = found.get("g") or slot["gender"] or ""
        if gender and slot.get("gloss"):
            gloss = slot["gloss"]
        else:
            gloss = found.get("e") or slot["gloss"]
        if not gloss:
            continue
        slang = found.get("slang") or slot["slang"]
        rank = rank_of(slot["lemma"], slot["surface"])
        level = level_for(rank)
        score = slot["count"] * 100
        if pos == "NOUN":
            score += 40
        elif pos == "VERB":
            score += 34
        elif pos == "ADJ":
            score += 28
        elif pos == "INTJ":
            score += 30
        if slang:
            score += 50
        # Concrete scene words (métro, quai, parapluie) should not lose every tie to tiny function-like verbs.
        if pos == "NOUN" and rank and 1200 <= rank <= 15000:
            score += 22
        # Nouns in the opening lines are what the scene is about.
        if pos == "NOUN" and slot.get("early"):
            score += 36
        if rank:
            score += max(0, 18 - int(rank**0.5) / 8)
        display, indefinite, audio = _display(slot["lemma"], pos, gender, gloss, slot.get("pronominal", False))
        ranked.append(
            {
                "lemma": slot["lemma"],
                "display": display,
                "indefinite": indefinite,
                "pos": pos,
                "pos_label": pos_label(pos),
                "gender": gender or "",
                "gender_label": {"m": "masculine", "f": "feminine"}.get(gender or "", ""),
                "gloss": gloss,
                "level": level,
                "level_label": level_label(level) if level else "frequency unknown",
                "count": slot["count"],
                "form_note": slot["form_note"],
                "example_fr": slot["example"].text,
                "example_en": slot["example"].translation,
                "audio_text": audio,
                "slang": slang,
                "score": score,
                "expression": False,
                "pronominal": slot.get("pronominal", False),
                "early": bool(slot.get("early")),
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["lemma"]))

    expressions = _expressions(lines, taught, known)
    # Expressions first, then a mix of content words. Cap verbs so a scene still teaches nouns.
    chosen = expressions[:4]
    seen = {item["lemma"].lower() for item in chosen}
    verb_count = 0
    for item in ranked:
        if item["lemma"].lower() in seen:
            continue
        if item["lemma"] == "plaire":
            continue
        if item["pos"] == "VERB" and verb_count >= 4:
            continue
        chosen.append(item)
        seen.add(item["lemma"].lower())
        if item["pos"] == "VERB":
            verb_count += 1
        if len(chosen) >= 16:
            break
    chosen = _rescue_scene_nouns(chosen, ranked)
    for item in chosen:
        item.pop("score", None)
    return chosen, {item["lemma"].lower() for item in chosen}


def _rescue_scene_nouns(chosen: list[dict], ranked: list[dict]) -> list[dict]:
    """Keep a few less obvious scene nouns, such as métro or parapluie."""
    seen = {item["lemma"].lower() for item in chosen}
    extras = [
        item
        for item in ranked
        if item["pos"] == "NOUN" and item["level"] in {"B1", "B2", "C1"} and item["lemma"].lower() not in seen
    ]
    # Opening-line nouns (the métro you just missed) come before rarer leftovers.
    extras.sort(key=lambda item: (0 if item.get("early") else 1, -(rank_of(item["lemma"]) or 0)))
    for extra in extras[:3]:
        if len(chosen) < 18:
            chosen.append(extra)
            seen.add(extra["lemma"].lower())
            continue
        for index in range(len(chosen) - 1, -1, -1):
            current = chosen[index]
            if current.get("expression") or current["pos"] == "VERB":
                continue
            if current["level"] in {"A1", "A2"} and current["pos"] == "ADJ":
                chosen[index] = extra
                seen.add(extra["lemma"].lower())
                break
    return chosen


def _form_rank(note: str) -> int:
    text = note.lower()
    if "subjunctive" in text:
        return 6
    if "conditional" in text:
        return 5
    if "imparfait" in text:
        return 5
    if "passé composé" in text:
        return 4
    if "imperative" in text:
        return 1
    if "feminine" in text:
        return 3
    if "present" in text:
        return 2
    if note:
        return 1
    return 0


def _keep_token(tok: Tok) -> bool:
    if not tok.is_word or tok.role in {"punct", "closed", "aux", "typo", "propn", "expr"}:
        return False
    if tok.typo or tok.pos in {"DET", "ADP", "PRON", "CCONJ", "SCONJ", "AUX", "PROPN", "EXPR"}:
        return False
    if len(tok.lemma) < 2:
        return False
    if not tok.gloss or tok.gloss.strip().lower() in {"verb", "noun", "adjective"}:
        return False
    return True


# Conjugated forms that are not a single fixed spelling in the subtitle.
_EXPR_RES = [
    (
        re.compile(r"\b(?:m'|t'|s'|me |te |se |nous |vous )occup\w*\s+d['e]", re.I),
        "s'occuper de",
        "to take care of; to deal with",
        "s'occuper de",
    ),
    (
        re.compile(r"\b(?:m'|t'|s'|me |te |se |nous |vous )prom[eè]n\w*", re.I),
        "se promener",
        "to go for a walk",
        "se promener",
    ),
    (
        re.compile(r"\bon a été coupée?s?\b", re.I),
        "on a été coupé",
        "we got cut off",
        "on a été coupé",
    ),
    (
        re.compile(r"\b(?:faire|fais|fait|faisons|faites|font)\s+attention(?:\s+à\b)?", re.I),
        "faire attention (à)",
        "to be careful; to pay attention",
        "faire attention",
    ),
]


def _pattern_in(hay: str, pattern: str, patterns: list[tuple]) -> bool:
    """Match a whole expression. A shorter prefix such as qu'est-ce does not win."""
    start = 0
    plen = len(pattern)
    while True:
        index = hay.find(pattern, start)
        if index < 0:
            return False
        before = hay[index - 1] if index else ""
        after = hay[index + plen : index + plen + 1]
        if (before and before.isalnum()) or (after and after.isalnum()):
            start = index + 1
            continue
        if any(len(other) > plen and hay.startswith(other, index) for other, *_rest in patterns):
            start = index + 1
            continue
        return True


def _expressions(lines: list[Line], taught: set[str], known: set[str]) -> list[dict]:
    found = []
    seen = set()
    patterns = sorted(EXPRESSIONS, key=lambda item: -len(item[0]))
    for pattern, lemma, gloss, audio in patterns:
        if lemma.lower() in seen or lemma.lower() in taught or lemma.lower() in known:
            continue
        for line in lines:
            hay = line.text.lower().replace("’", "'")
            if not _pattern_in(hay, pattern, patterns):
                continue
            found.append(
                {
                    "lemma": lemma,
                    "display": lemma,
                    "indefinite": "",
                    "pos": "EXPR",
                    "pos_label": "expression",
                    "gender": "",
                    "gender_label": "",
                    "gloss": gloss,
                    "level": "A1",
                    "level_label": "A1 · very common",
                    "count": 1,
                    "form_note": "",
                    "example_fr": line.text,
                    "example_en": line.translation,
                    "audio_text": audio,
                    "slang": None,
                    "expression": True,
                }
            )
            seen.add(lemma.lower())
            break
    for regex, lemma, gloss, audio in _EXPR_RES:
        if lemma.lower() in seen or lemma.lower() in taught or lemma.lower() in known:
            continue
        for line in lines:
            if line.typos:
                continue
            hay = line.text.lower().replace("’", "'")
            if not regex.search(hay):
                continue
            found.append(
                {
                    "lemma": lemma,
                    "display": lemma,
                    "indefinite": "",
                    "pos": "EXPR",
                    "pos_label": "expression",
                    "gender": "",
                    "gender_label": "",
                    "gloss": gloss,
                    "level": "A1",
                    "level_label": "A1 · very common",
                    "count": 1,
                    "form_note": "",
                    "example_fr": line.text,
                    "example_en": line.translation,
                    "audio_text": audio,
                    "slang": None,
                    "expression": True,
                }
            )
            seen.add(lemma.lower())
            break
    return found


def _display(lemma: str, pos: str, gender: str | None, gloss_text: str, pronominal: bool = False) -> tuple[str, str, str]:
    if pos == "NOUN" and gender:
        pair = display_noun(lemma, gender)
        return pair[0], pair[1], pair[0]
    if pos == "VERB":
        head = lemma
        if pronominal:
            head = "s'" + lemma if lemma[:1].lower() in "aeiouàâäéèêëîïôöh" else "se " + lemma
        return head, "", head
    return lemma, "", lemma


def _count_carried(lines: list[Line], taught: set[str]) -> int:
    seen = set()
    for line in lines:
        for tok in line.tokens:
            key = tok.lemma.lower()
            if key in taught and key not in seen and _keep_token(tok):
                seen.add(key)
    return len(seen)


def _point_name(title: str) -> str:
    return re.sub(r"^Review:\s*", "", title).strip()


def _prefer_example(line: Line, tok: Tok, slot: dict) -> bool:
    """A line with no typo flag wins over a flagged one when both contain the word."""
    new_clean = not line.typos
    old_clean = not slot["example"].typos
    if new_clean != old_clean:
        return new_clean
    return _form_rank(tok.form_note) > _form_rank(slot["form_note"])


def _overview(index: int, vocab: list[dict], grammar: list[Note], carried: int) -> tuple[str, list[str]]:
    points = [_point_name(note.title) for note in grammar[:3]]
    grammar_bit = " You'll work on the points below." if points else ""
    carried_bit = ""
    if carried and index > 1:
        carried_bit = f" {carried} words from earlier scenes come back in the dialogue and are not taught again."
    text = (
        f"Scene {index} introduces {len(vocab)} new words from this stretch of the film."
        + grammar_bit
        + carried_bit
    )
    return text, points


def _line_json(line: Line) -> dict:
    return {
        "speaker": line.speaker,
        "start_ms": line.start_ms,
        "end_ms": line.end_ms,
        "text": line.text,
        "corrected_text": line.corrected_text or line.text,
        "translation": line.translation,
        "translation_kind": line.translation_kind,
        "tip": line.tip,
        "typos": line.typos,
        "tokens": [
            {
                "text": tok.text,
                "lemma": tok.lemma,
                "pos": tok.pos,
                "pos_label": pos_label(tok.pos) if tok.pos else "",
                "gloss": tok.gloss,
                "gender": tok.gender,
                "is_word": tok.is_word,
                "form_note": tok.form_note,
                "role": tok.role,
                "typo": tok.typo or "",
            }
            for tok in line.tokens
        ],
    }


def _card(item: dict, scene_index: int) -> dict:
    back_bits = [item["gloss"]]
    if item.get("gender_label"):
        back_bits.append(item["gender_label"] + " noun")
    example_en = item["example_en"]
    if item.get("pos") == "VERB" and item.get("form_note"):
        example_en = f"{item['form_note']} — {example_en}" if example_en else item["form_note"]
    return {
        "lemma": item["lemma"],
        "front": item["display"],
        "back": " · ".join(bit for bit in back_bits if bit),
        "example_fr": item["example_fr"],
        "example_en": example_en,
        "audio_text": item["audio_text"],
        "pos": item["pos"],
        "gender": item.get("gender") or "",
        "level": item.get("level") or "",
        "scene_index": scene_index,
    }


_NOT_TITLE = {
    "voilà", "voila", "voici", "an", "ans",
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
}
# Kept out of scene titles only. A card can still teach the word.
_VULGAR = {
    "merde", "putain", "con", "connard", "connasse", "cul", "bite", "chier", "chiasse",
    "foutre", "niquer", "nique", "salope", "enculé", "encule", "enculer", "bordel",
    "pute", "couille", "couilles", "emmerdeur", "emmerdeuse",
}


def _title_label(lemma: str, line_gender: str | None) -> str | None:
    """Dictionary gender, with an article. Pendule keeps the article in the line."""
    key = (lemma or "").lower()
    if not key or key in _NOT_TITLE or key in _VULGAR:
        return None
    found = entry(key) or {}
    if found.get("p") not in {None, "", "NOUN"}:
        return None
    if key == "pendule":
        gender = line_gender or ""
    else:
        gender = found.get("g") or ""
    if gender not in {"m", "f"}:
        return None
    if plural_headword(key):
        return f"les {key}"
    phrase = noun_phrase(key, gender)
    if not phrase:
        return None
    return phrase[0]


def _scene_title(vocab: list[dict], lines: list[Line], index: int) -> str:
    nouns: list[str] = []
    seen: set[str] = set()

    def add(lemma: str, line_gender: str | None) -> None:
        label = _title_label(lemma, line_gender)
        if not label or label.lower() in seen:
            return
        nouns.append(label)
        seen.add(label.lower())

    for item in vocab:
        if item.get("pos") == "NOUN":
            add(item.get("lemma") or "", item.get("gender") or "")
        if len(nouns) >= 2:
            break
    if len(nouns) < 2:
        for line in lines:
            for tok in line.tokens:
                if tok.pos != "NOUN" or tok.role == "typo" or not tok.lemma:
                    continue
                add(tok.lemma, tok.gender)
                if len(nouns) >= 2:
                    break
            if len(nouns) >= 2:
                break
    nouns = nouns[:2]
    if len(nouns) >= 2:
        title = f"{nouns[0]} et {nouns[1]}"
    elif nouns:
        title = nouns[0]
    else:
        exprs = [item["display"] for item in vocab if item.get("expression")]
        title = exprs[0] if exprs else f"Scene {index}"
    return title[:1].upper() + title[1:]


def _voice_mode(lines: list[Line]) -> str:
    if any(line.speaker for line in lines):
        return "named"
    if any(re.search(r"(?:^|\s)[-–—]\s*\S", line.text) for line in lines):
        return "dashes"
    return "single"


def _clock(ms: int) -> str:
    total = max(0, ms) // 1000
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def key_lines(lesson: dict, limit: int = 12) -> list[dict]:
    """Lines worth putting on the dialogue drill: they carry new words or a grammar example."""
    vocab_lemmas = {item["lemma"].lower() for item in lesson["vocabulary"]}
    scored = []
    for line in lesson["lines"]:
        score = 0
        for tok in line["tokens"]:
            if tok.get("lemma", "").lower() in vocab_lemmas:
                score += 2
        if line.get("tip"):
            score += 1
        if score:
            scored.append((score, line))
    if len(lesson["lines"]) <= limit:
        return list(lesson["lines"])
    picked = [line for _, line in sorted(scored, key=lambda pair: -pair[0])[:limit]]
    order = {id(line): i for i, line in enumerate(lesson["lines"])}
    picked.sort(key=lambda line: next(i for i, raw in enumerate(lesson["lines"]) if raw is line))
    return picked
