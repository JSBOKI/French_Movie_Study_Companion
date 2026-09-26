"""Tokenize a French line and recover dictionary forms, gender, and verb features."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import simplemma

from app.services.lexicon import (
    CLOSED,
    ETRE_VERBS,
    POS_LABEL,
    Reading,
    entry,
    lemma_rank,
    noun_phrase,
    readings_for,
)

INFORMAL = {
    "t'as": ("avoir", "2", "s", "tu as", "you have — spoken « tu as »"),
    "t'es": ("être", "2", "s", "tu es", "you are — spoken « tu es »"),
    "t'étais": ("être", "2", "s", "tu étais", "you were — spoken « tu étais »"),
    "j'sais": ("savoir", "1", "s", "je sais", "I know — spoken « je sais »"),
    "j'suis": ("être", "1", "s", "je suis", "I am — spoken « je suis »"),
    "j'vais": ("aller", "1", "s", "je vais", "I am going — spoken « je vais »"),
    "y'a": ("avoir", "3", "s", "il y a", "there is / there are — spoken « il y a »"),
}

FIXED = {"d'accord", "aujourd'hui", "quelqu'un", "quelqu'une"}

AVOIR_PRESENT = {"ai", "as", "a", "avons", "avez", "ont"}
ETRE_PRESENT = {"suis", "es", "est", "sommes", "êtes", "sont"}
SUBJECTS = {
    "je": ("1", "s"),
    "j'": ("1", "s"),
    "tu": ("2", "s"),
    "il": ("3", "s"),
    "elle": ("3", "s"),
    "on": ("3", "s"),
    "nous": ("1", "p"),
    "vous": ("2", "p"),
    "ils": ("3", "p"),
    "elles": ("3", "p"),
    "ce": ("3", "s"),
    "c'": ("3", "s"),
}
REFLEXIVES = {"me", "te", "se", "m'", "t'", "s'", "nous", "vous"}
DETERMINERS = {
    "le", "la", "les", "l'", "un", "une", "des", "du", "au", "aux",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses",
    "notre", "nos", "votre", "vos", "leur", "leurs", "ce", "cet", "cette", "ces",
}
BETWEEN = {"pas", "jamais", "plus", "déjà", "encore", "vraiment", "bien", "trop", "même", "très"}
ELISION_LEFT = re.compile(
    r"^(qu|lorsqu|puisqu|jusqu|j|l|d|m|t|s|n|c)(['’])(.+)$",
    re.I,
)
HYPHEN_CLITIC = re.compile(
    r"^(.+?)-(t-)?(ce|tu|il|elle|on|nous|vous|ils|elles|je|moi|toi|le|la|les|lui|leur|en|y)$",
    re.I,
)
# Words that also collide with rare verb forms (tu/taire, plus/plaire, maintenant/maintenir).
HARD_FUNCTION = {
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
    "me", "te", "se", "moi", "toi", "lui", "leur", "ne", "pas", "plus", "jamais", "rien",
    "le", "la", "les", "un", "une", "des", "du", "au", "aux", "de", "à", "et", "ou", "mais",
    "que", "qui", "quoi", "dont", "où", "ce", "cet", "cette", "ces", "ça", "cela",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "notre", "nos", "votre", "vos",
    "oui", "non", "si", "très", "trop", "aussi", "alors", "donc", "puis", "enfin",
    "juste", "là", "ici", "même", "tout", "tous", "toute", "toutes", "bien", "mal", "comme",
    "quand", "comment", "pourquoi", "depuis", "avant", "après", "dans", "sur", "sous",
    "avec", "sans", "pour", "par", "en", "y", "chez", "vers", "près", "loin", "déjà",
    "encore", "maintenant", "vraiment", "peu", "assez", "moins", "toujours", "seulement",
    "l'", "d'", "j'", "n'", "m'", "t'", "s'", "c'", "qu'", "jusqu'",
}
ELISION_LEMMA = {
    "j'": "je", "l'": "le", "d'": "de", "m'": "me", "t'": "te", "s'": "se",
    "n'": "ne", "c'": "ce", "qu'": "que", "jusqu'": "jusque",
}
PREFER_LEMMA = {
    "faut": "falloir", "faudra": "falloir", "faudrait": "falloir", "faille": "falloir",
}
TOKEN_RE = re.compile(
    r"[0-9]+|[A-Za-zÀ-ÖØ-öø-ÿŒœ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿŒœ]+)*(?:-[A-Za-zÀ-ÖØ-öø-ÿŒœ]+)*|[^\s\w]",
    re.UNICODE,
)

TENSE_EN = {
    "pres": "present",
    "impf": "imparfait",
    "fut": "future",
    "ps": "passé simple",
    "past": "past",
}
MOOD_EN = {
    "ind": "indicative",
    "cond": "conditional",
    "sub": "subjunctive",
    "imp": "imperative",
    "part": "participle",
    "inf": "infinitive",
}
PERSON_EN = {"1": "1st person", "2": "2nd person", "3": "3rd person"}
NUMBER_EN = {"s": "singular", "p": "plural"}


@dataclass
class Tok:
    text: str
    lemma: str = ""
    pos: str = ""
    gloss: str = ""
    gender: str | None = None
    is_word: bool = True
    role: str = "other"
    form_note: str = ""
    reading: Reading | None = None
    slang: str | None = None


@dataclass
class Line:
    speaker: str | None
    start_ms: int
    end_ms: int
    text: str
    translation: str = ""
    translation_kind: str = "gloss"
    tokens: list[Tok] = field(default_factory=list)
    tip: str | None = None


def explode(token: str) -> list[str]:
    low = token.lower().replace("’", "'")
    if low in INFORMAL or low in FIXED:
        return [token]
    match = ELISION_LEFT.match(token)
    if match and low not in FIXED:
        left = match.group(1) + match.group(2)
        rest = match.group(3)
        return [left, *explode(rest)]
    hyphen = HYPHEN_CLITIC.match(token)
    if hyphen:
        head = hyphen.group(1)
        tee = hyphen.group(2) or ""
        tail = hyphen.group(3)
        pieces = explode(head)
        if tee:
            pieces.append("-" + tee.rstrip("-"))
        pieces.append("-" + tail)
        return pieces
    return [token]


def _norm(text: str) -> str:
    return text.lower().replace("’", "'")


def describe(reading: Reading, informal: str | None = None, compound: str | None = None) -> str:
    if reading.mood == "part" and reading.tense == "past":
        gender = {"m": "masculine", "f": "feminine"}.get(reading.gender, "")
        number = NUMBER_EN.get(reading.number, "")
        extra = " ".join(bit for bit in (gender, number) if bit)
        base = "past participle" + (f", {extra}" if extra else "")
    elif reading.mood == "imp":
        base = "imperative, " + _person(reading)
    elif reading.mood == "sub":
        base = f"subjunctive {TENSE_EN.get(reading.tense, reading.tense)}, {_person(reading)}"
    elif reading.mood == "cond":
        base = f"conditional, {_person(reading)}"
    elif reading.mood == "inf":
        base = "infinitive"
    else:
        base = f"{TENSE_EN.get(reading.tense, reading.tense)} indicative, {_person(reading)}"
    if compound:
        base += f", in the {compound}"
    if informal:
        base += f" — the spoken form of « {informal} »"
    return base


def _person(reading: Reading) -> str:
    if not reading.person:
        return ""
    return f"{PERSON_EN.get(reading.person, reading.person)} {NUMBER_EN.get(reading.number, '')}".strip()


def _subject_before(tokens: list[str], index: int) -> tuple[str, str] | None:
    for j in range(index - 1, -1, -1):
        low = _norm(tokens[j])
        if low in {",", ".", "?", "!", ";", ":"}:
            break
        if low in SUBJECTS and low not in {"ce"}:
            return SUBJECTS[low]
        if low in REFLEXIVES or low in BETWEEN or low in {"ne", "n'"}:
            continue
        if low in DETERMINERS:
            continue
        # A content word blocks the search.
        if low.isalpha() or "'" in low:
            # Object pronouns and short adverbs were handled. Stop.
            if low not in {"y", "en", "-ce", "-t"}:
                break
    return None


def _aux_before(tokens: list[str], index: int) -> tuple[str, str] | None:
    """Return (avoir|être, surface) if a present-tense auxiliary sits just before this word."""
    saw_reflexive = False
    for j in range(index - 1, max(-1, index - 6), -1):
        low = _norm(tokens[j])
        if low in {".", "?", "!", ";", ":"}:
            break
        if low in BETWEEN or low in {"ne", "n'"}:
            continue
        if low in REFLEXIVES:
            saw_reflexive = True
            continue
        if low in INFORMAL and INFORMAL[low][0] == "avoir" and "tu as" in INFORMAL[low][3]:
            return ("avoir", low)
        if low == "t'es":
            return ("être", low)
        if low in AVOIR_PRESENT:
            return ("avoir", low)
        if low in ETRE_PRESENT:
            return ("être-reflexive" if saw_reflexive else "être", low)
        break
    return None


def _subjunctive_flags(pieces: list[str]) -> list[bool]:
    """True on the finite verb governed by a subjunctive trigger."""
    lows = [_norm(p) for p in pieces]
    flags = [False] * len(pieces)
    armed = False
    for i, low in enumerate(lows):
        if low in {"que", "qu'"}:
            window = " ".join(lows[max(0, i - 5) : i])
            if re.search(r"faut|veux|veut|voul|aimerais|avant|pour|bien|afin|\bce$", window):
                armed = True
            continue
        if not armed:
            continue
        finite = [r for r in readings_for(low) if r.mood in {"ind", "sub", "cond", "imp"}]
        if finite or low in INFORMAL:
            flags[i] = True
            armed = False
    return flags


def _function_token(surface: str) -> Tok | None:
    low = _norm(surface)
    if low not in HARD_FUNCTION:
        return None
    gloss = CLOSED.get(low) or ""
    lemma = ELISION_LEMMA.get(low, low)
    if low in {"le", "la", "les", "un", "une", "des", "du", "au", "aux", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "ce", "cet", "cette", "ces", "l'"}:
        pos = "DET"
    elif low in {"je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "me", "te", "se", "moi", "toi", "lui", "leur", "j'", "m'", "t'", "s'", "c'", "qu'"}:
        pos = "PRON"
    elif low in {"de", "à", "dans", "sur", "sous", "avec", "sans", "pour", "par", "chez", "vers", "près", "depuis", "avant", "après", "d'", "jusqu'"}:
        pos = "ADP"
    elif low in {"et", "ou", "mais", "donc", "puis"}:
        pos = "CCONJ"
    elif low in {"que", "qui", "si", "quand", "comme", "parce"}:
        pos = "SCONJ"
    elif low in {"oui", "non"}:
        pos = "INTJ"
    else:
        pos = "ADV"
    return Tok(text=surface, lemma=lemma, pos=pos, gloss=gloss, is_word=True, role="closed")


def _choose(readings: tuple[Reading, ...], *, subject, aux, subjunctive: bool, clause_start: bool, prev: str, surface: str = "") -> Reading | None:
    if not readings:
        return None
    pool = list(readings)
    forced = PREFER_LEMMA.get(_norm(surface))
    if forced:
        preferred = [r for r in pool if r.lemma == forced]
        if preferred:
            pool = preferred
    # « Promis ? » is the participle, not the passé simple, when nobody is the subject.
    if not subject:
        parts = [r for r in pool if r.mood == "part"]
        only_simple = parts and all(r.mood == "part" or (r.mood == "ind" and r.tense == "ps") for r in pool)
        if only_simple:
            pool = parts
    if aux and aux[0] == "avoir":
        parts = [r for r in pool if r.mood == "part" and r.tense == "past"]
        if parts:
            pool = parts
    elif aux and aux[0].startswith("être"):
        parts = [r for r in pool if r.mood == "part" and r.tense == "past"]
        reflexive = aux[0] == "être-reflexive"
        if parts and (reflexive or any(r.lemma in ETRE_VERBS for r in parts)):
            pool = [r for r in parts if r.lemma in ETRE_VERBS] or parts
            if reflexive:
                pool = parts
        else:
            pool = [r for r in pool if r.mood != "part"] or pool
    else:
        finite = [r for r in pool if r.mood != "part"]
        if finite:
            pool = finite
    if subjunctive:
        subs = [r for r in pool if r.mood == "sub"]
        if subs:
            pool = subs
    else:
        plain = [r for r in pool if r.mood != "sub"]
        if plain:
            pool = plain
    spoken = [r for r in pool if not (r.mood == "ind" and r.tense == "ps")]
    if spoken:
        pool = spoken
    if subject:
        matched = [r for r in pool if r.person == subject[0] and (not r.number or r.number == subject[1])]
        if matched:
            pool = matched
    if clause_start and subject is None:
        commands = [r for r in pool if r.mood == "imp"]
        if commands:
            pool = commands
    # suis: suivre only when an object pronoun is glued to it. Otherwise être.
    lemmas = {r.lemma for r in pool}
    if "être" in lemmas and "suivre" in lemmas:
        if prev in {"le", "la", "les", "l'", "me", "te", "m'", "t'", "nous", "vous"}:
            pool = [r for r in pool if r.lemma == "suivre"] or pool
        else:
            pool = [r for r in pool if r.lemma == "être"] or pool
    if "être" in {r.lemma for r in pool} and len({r.lemma for r in pool}) > 1 and prev not in {"le", "la", "les"}:
        etre = [r for r in pool if r.lemma == "être"]
        others = [r for r in pool if r.lemma != "être"]
        # Keep être unless another lemma is a dramatically better person match we already filtered.
        if etre and all(lemma_rank(r.lemma) > lemma_rank("être") for r in others):
            pool = etre
    pool.sort(key=lambda r: lemma_rank(r.lemma))
    return pool[0]


def _gloss_for(lemma: str, pos: str) -> tuple[str, str | None, str | None]:
    found = entry(lemma)
    if not found:
        return "", None, None
    return found.get("e", ""), found.get("g") or None, found.get("slang")


def _closed_gloss(low: str) -> str:
    return CLOSED.get(low, "")


def analyze_line(speaker: str | None, start_ms: int, end_ms: int, text: str, *, subjunctive_spans: list[tuple[int, int]] | None = None) -> Line:
    raw_pieces: list[str] = []
    for piece in TOKEN_RE.findall(text):
        raw_pieces.extend(explode(piece))
    # Subjunctive if a trigger's "que" governs this token. Callers may pass char spans;
    # we also detect locally from the line.
    subjunctive_at = _subjunctive_flags(raw_pieces)
    clause_start = True
    tokens: list[Tok] = []
    for index, surface in enumerate(raw_pieces):
        low = _norm(surface)
        if not re.search(r"[A-Za-zÀ-ÿ0-9]", surface):
            tokens.append(Tok(text=surface, is_word=False, role="punct"))
            if surface in {".", "?", "!", ";", ","}:
                clause_start = True
                subject = None
            continue
        function = _function_token(surface)
        if function is not None:
            tokens.append(function)
            clause_start = False
            continue
        informal = INFORMAL.get(low)
        aux = _aux_before(raw_pieces, index)
        prev = _norm(raw_pieces[index - 1]) if index else ""
        subject = _subject_before(raw_pieces, index)
        readings = () if informal else readings_for(low)
        # A determiner in front of a dictionary noun beats a stray verb reading (le livre).
        noun_entry = entry(simplemma.lemmatize(low, lang="fr"))
        prefer_noun = prev in DETERMINERS and noun_entry and noun_entry.get("p") == "NOUN" and not aux
        chosen = None if prefer_noun or informal else _choose(
            readings,
            subject=subject,
            aux=aux,
            subjunctive=subjunctive_at[index] and not aux,
            clause_start=clause_start and subject is None,
            prev=prev,
            surface=low,
        )
        tok = Tok(text=surface)
        if informal:
            lemma, person, number, spoken, gloss = informal
            mood, tense = ("ind", "impf") if low == "t'étais" else ("ind", "pres")
            reading = Reading(lemma, mood, tense, person, number, "")
            tok.lemma = lemma
            tok.pos = "VERB"
            tok.gloss = gloss
            tok.reading = reading
            tok.role = "verb"
            tok.form_note = describe(reading, informal=spoken)
        elif low in FIXED:
            found = entry(low) or {}
            tok.lemma = low
            tok.pos = found.get("p") or "INTJ"
            tok.gloss = found.get("e") or _closed_gloss(low)
            tok.role = "expr"
        elif chosen and not prefer_noun:
            tok.reading = chosen
            tok.lemma = chosen.lemma
            tok.pos = "VERB"
            gloss, _, slang = _gloss_for(chosen.lemma, "VERB")
            tok.gloss = gloss or "verb"
            tok.slang = slang
            compound = None
            etre_event = bool(
                aux
                and aux[0].startswith("être")
                and (aux[0] == "être-reflexive" or chosen.lemma in ETRE_VERBS)
            )
            if aux and chosen.mood == "part" and (aux[0] == "avoir" or etre_event):
                compound = "passé composé"
                tok.role = "participle"
            elif chosen.mood == "part" and not etre_event and aux and aux[0].startswith("être"):
                # être + a non-motion participle is usually a description: est ouvert, suis désolé.
                adjective = entry(simplemma.lemmatize(_norm(surface), lang="fr")) or entry(chosen.lemma)
                if adjective and adjective.get("p") == "ADJ":
                    tok.lemma = simplemma.lemmatize(_norm(surface), lang="fr")
                    if entry(tok.lemma) is None:
                        tok.lemma = chosen.lemma
                    found = entry(tok.lemma) or adjective
                    tok.pos = "ADJ"
                    tok.gloss = found.get("e", tok.gloss)
                    tok.role = "adj"
                    tok.reading = None
                    tok.form_note = ""
                    if _norm(surface) != tok.lemma and _norm(surface).endswith("e") and not tok.lemma.endswith("e"):
                        tok.form_note = f"feminine form of « {tok.lemma} »"
                else:
                    tok.role = "participle"
            elif chosen.mood == "part":
                adjective = entry(_norm(surface)) or entry(simplemma.lemmatize(_norm(surface), lang="fr"))
                if adjective and adjective.get("p") == "ADJ" and not aux:
                    tok.lemma = simplemma.lemmatize(_norm(surface), lang="fr")
                    found = entry(tok.lemma) or adjective
                    tok.pos = "ADJ"
                    tok.gloss = found.get("e", "")
                    tok.role = "adj"
                    tok.reading = None
                    tok.form_note = "adjective here, describing a state"
                else:
                    tok.role = "participle"
            elif any(r.lemma == chosen.lemma and r.mood != "part" for r in readings) and aux and aux[1] == low:
                tok.role = "aux"
            else:
                tok.role = "aux" if low in AVOIR_PRESENT | ETRE_PRESENT and chosen.lemma in {"avoir", "être"} else "verb"
            # The auxiliary token itself is not a participle.
            if low in AVOIR_PRESENT | ETRE_PRESENT and chosen.lemma in {"avoir", "être"} and chosen.mood != "part":
                tok.role = "aux"
                compound = None
            if tok.role != "adj":
                tok.form_note = describe(chosen, compound=compound if tok.role == "participle" else None)
            elif not tok.form_note:
                tok.form_note = "adjective here, describing a state"
        else:
            lemma = simplemma.lemmatize(low, lang="fr")
            found = entry(lemma) or entry(low) or {}
            tok.lemma = lemma
            tok.pos = found.get("p") or ""
            tok.gloss = found.get("e") or _closed_gloss(low) or _closed_gloss(lemma)
            tok.gender = found.get("g") or None
            tok.slang = found.get("slang")
            if tok.pos == "NOUN":
                tok.role = "noun"
            elif tok.pos == "ADJ":
                tok.role = "adj"
            elif tok.pos == "VERB":
                tok.role = "verb"
            elif low in CLOSED or lemma in CLOSED:
                tok.role = "closed"
                tok.pos = tok.pos or "PRON"
                if not tok.gloss:
                    tok.gloss = _closed_gloss(low) or _closed_gloss(lemma)
            else:
                tok.role = "other"
            if tok.pos == "ADJ" and low != lemma and low.endswith("e") and not lemma.endswith("e"):
                tok.form_note = f"feminine form of « {lemma} »"
            elif tok.pos == "NOUN" and low != lemma:
                tok.form_note = f"dictionary form: {lemma}"
        if not tok.gloss and low in CLOSED:
            tok.gloss = CLOSED[low]
        if tok.pos == "NOUN" and not tok.gender:
            found = entry(tok.lemma)
            if found:
                tok.gender = found.get("g") or None
        tokens.append(tok)
        if surface[:1].isalnum():
            clause_start = False
    _fix_object_pronouns(tokens)
    return Line(speaker=speaker, start_ms=start_ms, end_ms=end_ms, text=text, tokens=tokens, tip=line_tip(text))


def _is_present_aux(surface: str, kind: str) -> bool:
    low = _norm(surface)
    if kind == "avoir":
        return low in AVOIR_PRESENT
    return low in ETRE_PRESENT


def _fix_object_pronouns(tokens: list[Tok]) -> None:
    """le/la/les/l' before a finite verb, after a subject, are pronouns, not articles."""
    for i, tok in enumerate(tokens):
        low = _norm(tok.text)
        if low not in {"le", "la", "les", "l'"}:
            continue
        nxt = next((t for t in tokens[i + 1 :] if t.is_word), None)
        prev = next((t for t in reversed(tokens[:i]) if t.is_word), None)
        if nxt and nxt.role in {"verb", "aux"} and prev and _norm(prev.text) in SUBJECTS:
            tok.role = "closed"
            tok.pos = "PRON"
            tok.lemma = "le"
            tok.gloss = {"le": "him, it", "la": "her, it", "les": "them", "l'": "him, her, it"}[low]
            tok.form_note = "object pronoun, placed before the verb"


def line_tip(text: str) -> str | None:
    low = text.lower().replace("’", "'")
    if re.search(r"\bt'as\b", low):
        return "« t'as » is spoken French for « tu as ». The u disappears, and it sounds like one syllable, [ta]."
    if re.search(r"\bt'es\b", low):
        return "« t'es » is spoken French for « tu es » — the u drops."
    if re.search(r"\bj'sais\b", low):
        return "« j'sais » drops the e of « je ». You will hear something close to [ʃsɛ], not a full « je sais »."
    if re.search(r"\by'a\b", low):
        return "« y'a » is the spoken form of « il y a » (there is / there are). The « il » disappears."
    if re.search(r"\bon est\b", low):
        return "Liaison: in « on est », the silent n of « on » is pronounced and links the words, [ɔ̃.nɛ]."
    if re.search(r"\b(les|des|mes|tes|ses|nous|vous)\s+[aeiouhàéèêîôû]", low):
        return "Liaison: the normally silent final consonant is pronounced because the next word starts with a vowel sound."
    if re.search(r"\b[ldjnmtsc]'|\bqu'", low):
        return "Elision: the vowel in le, de, je, ne, me, te, se, ce, or que drops before a vowel sound — l'heure, j'habite, d'accord."
    return None


def pos_label(pos: str) -> str:
    return POS_LABEL.get(pos, pos.lower())


def display_noun(lemma: str, gender: str | None) -> tuple[str, str]:
    if gender:
        phrase = noun_phrase(lemma, gender)
        if phrase:
            return phrase
    return lemma, ""
