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
    gloss,
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
    "ouvrais": "ouvrir", "ouvrait": "ouvrir", "ouvrions": "ouvrir", "ouvriez": "ouvrir", "ouvraient": "ouvrir",
}
# Fan subtitles often drop the circumflex. These are paraître/connaître, not the unaccented homograph.
CIRCUMFLEX = {
    "parait": "paraît", "paraitre": "paraître",
    "apparait": "apparaît", "apparaitre": "apparaître",
    "disparait": "disparaît", "disparaitre": "disparaître",
    "connait": "connaît", "connaitre": "connaître",
    "reconnait": "reconnaît", "reconnaitre": "reconnaître",
    "naitre": "naître", "plait": "plaît",
}
AVOIR_COND = {"aurais", "aurait", "aurions", "auriez", "auraient"}
AVOIR_IMPF = {"avais", "avait", "avions", "aviez", "avaient"}
ETRE_COND = {"serais", "serait", "serions", "seriez", "seraient"}
ETRE_IMPF = {"étais", "était", "étions", "étiez", "étaient"}
DET_GENDER = {
    "un": "m", "le": "m", "du": "m", "au": "m", "ce": "m", "cet": "m",
    "mon": "m", "ton": "m", "son": "m", "notre": "m", "votre": "m",
    "une": "f", "la": "f", "cette": "f", "ma": "f", "ta": "f", "sa": "f",
}
PLURAL_DET = {"les", "des", "ces", "mes", "tes", "ses", "nos", "vos", "leurs"}
SUBJECT_CLITIC = {"-il", "-elle", "-on", "-tu", "-je", "-nous", "-vous", "-ils", "-elles", "-ce"}
OBJECT_CLITIC = {"-le", "-la", "-les", "-lui", "-leur", "-moi", "-toi", "-en", "-y"}
CLITIC_GLOSS = {
    "-il": "he (inverted)", "-elle": "she (inverted)", "-on": "one, we (inverted)",
    "-tu": "you (inverted)", "-je": "I (inverted)", "-nous": "we (inverted)",
    "-vous": "you (inverted)", "-ils": "they (inverted)", "-elles": "they (inverted)",
    "-ce": "part of qu'est-ce / est-ce", "-le": "him, it", "-la": "her, it",
    "-les": "them", "-lui": "to him, to her", "-leur": "to them",
    "-moi": "me", "-toi": "you", "-en": "of it, some", "-y": "there",
}
PROPER = {
    "mexique", "france", "paris", "lyon", "marseille", "espagne", "italie", "allemagne",
    "angleterre", "belgique", "suisse", "canada", "japon", "chine", "brésil", "bresil",
    "portugal", "maroc", "algérie", "algerie", "tunisie", "sénégal", "senegal",
}
# Longest phrases first. Tokens are already split on elision and hyphen clitics.
PHRASES: list[tuple[list[str], str, str]] = [
    (["s'", "il", "vous", "plaît"], "s'il vous plaît", "please (polite)"),
    (["s'", "il", "vous", "plait"], "s'il vous plaît", "please (polite)"),
    (["s'", "il", "te", "plaît"], "s'il te plaît", "please (to a friend)"),
    (["s'", "il", "te", "plait"], "s'il te plaît", "please (to a friend)"),
    (["qu'", "est", "-ce", "que"], "qu'est-ce que", "what (question phrase)"),
    (["qu'", "est", "-ce", "qui"], "qu'est-ce qui", "what (question phrase)"),
    (["qu'", "est", "-ce"], "qu'est-ce", "what"),
    (["je", "vous", "en", "supplie"], "je vous en supplie", "I'm begging you"),
    (["en", "pleine", "forme"], "en pleine forme", "in great shape"),
    (["tout", "de", "même"], "tout de même", "all the same, even so"),
    (["tandis", "que"], "tandis que", "whereas, while"),
    (["il", "n'", "y", "a"], "il n'y a", "there is not"),
    (["il", "y", "a"], "il y a", "there is, there are"),
    (["faire", "attention"], "faire attention", "to be careful, to pay attention"),
    (["fais", "attention"], "faire attention", "be careful"),
    (["faites", "attention"], "faire attention", "be careful (polite or plural)"),
    (["fait", "attention"], "faire attention", "be careful"),
    (["quelqu'", "un"], "quelqu'un", "someone"),
]
PHRASES.sort(key=lambda item: -len(item[0]))
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
    typo: str | None = None
    pronominal: bool = False


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
    typos: list[str] = field(default_factory=list)


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


def _aux_kind(low: str) -> str | None:
    if low in AVOIR_PRESENT:
        return "avoir"
    if low in AVOIR_COND:
        return "avoir-cond"
    if low in AVOIR_IMPF:
        return "avoir-impf"
    if low in ETRE_PRESENT:
        return "être"
    if low in ETRE_COND:
        return "être-cond"
    if low in ETRE_IMPF:
        return "être-impf"
    return None


def _compound_name(kind: str) -> str | None:
    if kind.startswith("avoir-cond") or kind.startswith("être-cond"):
        return "conditionnel passé"
    if kind.startswith("avoir-impf") or kind.startswith("être-impf"):
        return "plus-que-parfait"
    if kind.startswith("avoir") or kind.startswith("être"):
        return "passé composé"
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
        kind = _aux_kind(low)
        if kind:
            if kind.startswith("être") and saw_reflexive:
                kind = kind + "-reflexive" if "reflexive" not in kind else kind
            return (kind, low)
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
    if aux and aux[0].startswith("avoir"):
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
    pool.sort(key=lambda r: (lemma_rank(r.lemma), 0 if entry(r.lemma) else 1, r.lemma))
    return pool[0]


def _gloss_for(lemma: str, pos: str) -> tuple[str, str | None, str | None]:
    found = entry(lemma)
    if not found:
        return "", None, None
    text = gloss(lemma)
    if text.lower() in {"verb", "noun", "adjective"}:
        text = ""
    return text, found.get("g") or None, found.get("slang")


def _closed_gloss(low: str) -> str:
    return CLOSED.get(low, "")


def _lookup_surface(low: str) -> str:
    return CIRCUMFLEX.get(low, low)


def _expression_at(pieces: list[str], index: int) -> tuple[int, str, str] | None:
    lows = [_norm(piece) for piece in pieces]
    for phrase, lemma, meaning in PHRASES:
        end = index + len(phrase)
        if end <= len(lows) and lows[index:end] == phrase:
            return end, lemma, meaning
    return None


def _join_pieces(pieces: list[str]) -> str:
    out = ""
    for piece in pieces:
        if out and not piece.startswith("-") and not out.endswith(("'", "’", "-")):
            out += " "
        out += piece
    return out


def _det_gender_before(pieces: list[str], index: int) -> str:
    for j in range(index - 1, -1, -1):
        low = _norm(pieces[j])
        if low in DET_GENDER:
            return DET_GENDER[low]
        if low in DETERMINERS or low in {"de", "d'"}:
            return ""
        found = entry(low) or entry(simplemma.lemmatize(low, lang="fr"))
        if found and found.get("p") == "ADJ":
            continue
        break
    return ""


def _rare_verb_twin(surface: str, lemma: str) -> bool:
    """typer/type, policer/police, fenêtrer/fenêtre, former/forme."""
    if lemma == surface:
        return False
    if lemma == surface + "r":
        return True
    stem = surface[:-1] if surface.endswith("e") else surface
    return lemma == stem + "er"


def _noun_override(low: str, prev: str, gender: str) -> dict | None:
    """After a determiner, a noun reading beats a stray verb homograph."""
    if prev not in DETERMINERS and prev not in {"de", "d'"} and not gender:
        return None
    found = entry(low) or entry(simplemma.lemmatize(low, lang="fr"))
    if found and found.get("p") in {"NOUN", "ADJ"}:
        return found
    readings = readings_for(_lookup_surface(low))
    lemmas = {reading.lemma for reading in readings}
    if lemmas and all(_rare_verb_twin(low, lemma) for lemma in lemmas):
        return {"p": "NOUN", "g": gender, "e": ""}
    if readings and all(reading.mood == "part" for reading in readings) and found is None:
        # « d'entreprise » is not the participle of entreprendre.
        if prev in {"d'", "de", "du", "des", "l'", "la", "le", "un", "une"}:
            return {"p": "NOUN", "g": gender, "e": ""}
    if prev in DETERMINERS and not readings:
        return {"p": "NOUN", "g": gender, "e": ""}
    return None


def _imperative_person(pieces: list[str], index: int) -> tuple[str, str] | None:
    lows = [_norm(piece) for piece in pieces]
    j = index - 1
    while j >= 0 and lows[j] not in {".", "?", "!", ";", ":", ","}:
        if lows[j] in {"ne", "n'"} or lows[j] in REFLEXIVES or lows[j] in {"le", "la", "les", "lui", "leur", "en", "y"}:
            j -= 1
            continue
        return None
    nxt = lows[index + 1] if index + 1 < len(lows) else ""
    saw_ne = any(lows[k] in {"ne", "n'"} for k in range(j + 1, index))
    object_after = nxt in OBJECT_CLITIC
    subject_after = nxt in SUBJECT_CLITIC or nxt == "-t"
    neg_after = nxt in {"pas", "plus", "jamais", "rien"}
    if subject_after and not saw_ne:
        return None
    if not (saw_ne or object_after or (neg_after and saw_ne)):
        return None
    verb = lows[index]
    if verb.endswith("ez") or verb in {"dites", "faites", "soyez", "ayez", "allez"}:
        return ("2", "p")
    if verb.endswith("ons"):
        return ("1", "p")
    return ("2", "s")


def _subject_from_built(tokens: list[Tok]) -> tuple[str, str] | None:
    for index in range(len(tokens) - 1, -1, -1):
        tok = tokens[index]
        if not tok.is_word:
            if tok.text in ".?!;:":
                break
            continue
        low = _norm(tok.text)
        if tok.pos == "DET":
            continue
        if low in SUBJECTS and tok.pos == "PRON":
            return SUBJECTS[low]
        if low in {"quelqu'un", "quelqu'une", "chacun", "chacune"}:
            return ("3", "s")
        if tok.pos == "NOUN" or tok.role == "noun":
            number = "s"
            for earlier in range(index - 1, -1, -1):
                prev = tokens[earlier]
                if prev.pos == "DET":
                    number = "p" if _norm(prev.text) in PLURAL_DET else "s"
                    break
                if prev.pos != "ADJ":
                    break
            return ("3", number)
        if low in REFLEXIVES or low in {"le", "la", "les", "lui", "leur", "en", "y"} or low in BETWEEN or low in {"ne", "n'"} or tok.pos in {"ADJ", "ADP", "ADV"}:
            continue
        break
    return None


def _apply_gender(tok: Tok, pieces: list[str], index: int) -> None:
    gender = _det_gender_before(pieces, index)
    if gender:
        tok.gender = gender
    elif tok.pos == "NOUN" and not tok.gender:
        found = entry(tok.lemma)
        if found:
            tok.gender = found.get("g") or None
    if tok.lemma == "pendule":
        if tok.gender == "m":
            tok.gloss = "pendulum"
        elif tok.gender == "f":
            tok.gloss = "clock"


def _flag_typos(tokens: list[Tok]) -> list[str]:
    notes: list[str] = []

    def recent_aux(index: int, kind: str) -> bool:
        for tok in reversed(tokens[max(0, index - 6) : index]):
            low = _norm(tok.text)
            if tok.role == "aux" and kind == "avoir" and tok.lemma == "avoir":
                return True
            if tok.role == "aux" and kind == "être" and tok.lemma == "être":
                return True
            if kind == "avoir" and low in AVOIR_PRESENT | AVOIR_COND | AVOIR_IMPF | {"t'as"}:
                return True
            if kind == "être" and low in ETRE_PRESENT | ETRE_COND | ETRE_IMPF | {"t'es"}:
                return True
            if low in {".", "?", "!"}:
                break
        return False

    def participle_between(index: int) -> bool:
        """« a entendu parler » already has its participle; the infinitive is a complement."""
        for tok in tokens[max(0, index - 6) : index]:
            if tok.role == "participle" or (tok.reading and tok.reading.mood == "part"):
                return True
        return False

    for index, tok in enumerate(tokens):
        if not tok.is_word or tok.role == "expr":
            continue
        low = _norm(tok.text)
        prevs = [_norm(item.text) for item in tokens[max(0, index - 4) : index]]
        guess = ""
        if (
            recent_aux(index, "avoir")
            and not participle_between(index)
            and tok.reading
            and tok.reading.mood == "inf"
            and low.endswith("er")
        ):
            guess = low[:-2] + "é"
        elif (
            recent_aux(index, "avoir")
            and not participle_between(index)
            and low.endswith("ez")
            and tok.reading
            and tok.reading.mood in {"ind", "imp"}
        ):
            guess = {"passer": "passé"}.get(tok.lemma, "")
            if not guess and tok.lemma.endswith("er"):
                guess = tok.lemma[:-2] + "é"
        elif low.endswith("ants") and not entry(low) and not readings_for(low):
            singular = low[:-1]
            if entry(singular) or readings_for(singular):
                guess = singular
        elif (
            index
            and prevs
            and prevs[-1] in {"m'", "t'", "s'"}
            and tok.reading
            and tok.reading.mood == "part"
            and tok.reading.tense == "past"
            and not recent_aux(index, "avoir")
            and not recent_aux(index, "être")
            and low.endswith("é")
        ):
            guess = prevs[-1] + low[:-1] + "e"
        elif low == "mère" and "la" in prevs[-2:] and any(word in {"sur", "dans", "en", "sous", "vers"} for word in prevs):
            guess = "mer (the sea)"
        if not guess:
            continue
        label = f"possible subtitle typo, likely {guess}"
        tok.typo = guess
        tok.role = "typo"
        tok.form_note = label
        tok.gloss = ""
        notes.append(f"{tok.text}: {label}")
    return notes


def analyze_line(speaker: str | None, start_ms: int, end_ms: int, text: str, *, subjunctive_spans: list[tuple[int, int]] | None = None) -> Line:
    raw_pieces: list[str] = []
    for piece in TOKEN_RE.findall(text):
        raw_pieces.extend(explode(piece))
    # Subjunctive if a trigger's "que" governs this token. Callers may pass char spans;
    # we also detect locally from the line.
    subjunctive_at = _subjunctive_flags(raw_pieces)
    clause_start = True
    tokens: list[Tok] = []
    index = 0
    while index < len(raw_pieces):
        surface = raw_pieces[index]
        low = _norm(surface)
        if not re.search(r"[A-Za-zÀ-ÿ0-9]", surface):
            tokens.append(Tok(text=surface, is_word=False, role="punct"))
            if surface in {".", "?", "!", ";", ","}:
                clause_start = True
            index += 1
            continue
        phrase = _expression_at(raw_pieces, index)
        if phrase:
            end, lemma, meaning = phrase
            tokens.append(
                Tok(
                    text=_join_pieces(raw_pieces[index:end]),
                    lemma=lemma,
                    pos="EXPR",
                    gloss=meaning,
                    is_word=True,
                    role="expr",
                )
            )
            clause_start = False
            index = end
            continue
        if low in CLITIC_GLOSS or low in SUBJECT_CLITIC or low in OBJECT_CLITIC:
            tokens.append(
                Tok(
                    text=surface,
                    lemma=low.lstrip("-"),
                    pos="PRON",
                    gloss=CLITIC_GLOSS.get(low, "pronoun"),
                    is_word=True,
                    role="closed",
                    form_note="pronoun attached with a hyphen",
                )
            )
            clause_start = False
            index += 1
            continue
        if low in PROPER or (surface[:1].isupper() and not clause_start and surface[:1].isalpha()):
            tokens.append(
                Tok(
                    text=surface,
                    lemma=surface[0].upper() + surface[1:],
                    pos="PROPN",
                    gloss=(entry(low) or {}).get("e") or "",
                    is_word=True,
                    role="propn",
                )
            )
            clause_start = False
            index += 1
            continue
        nxt = _norm(raw_pieces[index + 1]) if index + 1 < len(raw_pieces) else ""
        if low in {"devant", "derrière"} and not any(reading.mood == "inf" for reading in readings_for(nxt)):
            tokens.append(
                Tok(text=surface, lemma=low, pos="ADP", gloss=CLOSED.get(low, low), is_word=True, role="closed")
            )
            clause_start = False
            index += 1
            continue
        function = _function_token(surface)
        if function is not None:
            tokens.append(function)
            clause_start = False
            index += 1
            continue
        informal = INFORMAL.get(low)
        aux = _aux_before(raw_pieces, index)
        prev = _norm(raw_pieces[index - 1]) if index else ""
        imp_person = _imperative_person(raw_pieces, index)
        subject = imp_person or _subject_from_built(tokens) or _subject_before(raw_pieces, index)
        readings = () if informal else readings_for(_lookup_surface(low))
        gender_hint = _det_gender_before(raw_pieces, index)
        noun_entry = _noun_override(low, prev, gender_hint)
        prefer_noun = bool(noun_entry) and noun_entry.get("p") == "NOUN" and not aux
        if noun_entry and noun_entry.get("p") == "ADJ" and prev in DETERMINERS:
            prefer_noun = False
        chosen = None if prefer_noun or informal else _choose(
            readings,
            subject=subject,
            aux=aux,
            subjunctive=subjunctive_at[index] and not aux,
            clause_start=clause_start and subject is None,
            prev=prev,
            surface=_lookup_surface(low),
        )
        if imp_person and chosen is not None:
            person, number = imp_person
            if chosen.mood != "imp":
                chosen = Reading(chosen.lemma, "imp", "pres", person, number, "")
        tok = Tok(text=surface)
        if informal:
            lemma, person, number, spoken, spoken_gloss = informal
            mood, tense = ("ind", "impf") if low == "t'étais" else ("ind", "pres")
            reading = Reading(lemma, mood, tense, person, number, "")
            tok.lemma = lemma
            tok.pos = "VERB"
            tok.gloss = spoken_gloss
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
            word_gloss, _, slang = _gloss_for(chosen.lemma, "VERB")
            tok.gloss = word_gloss
            tok.slang = slang
            compound = None
            etre_event = bool(
                aux
                and aux[0].startswith("être")
                and ("reflexive" in aux[0] or chosen.lemma in ETRE_VERBS)
            )
            if aux and chosen.mood == "part" and (aux[0].startswith("avoir") or etre_event):
                compound = _compound_name(aux[0])
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
                    if chosen.tense == "pres":
                        tok.form_note = f"present participle of « {chosen.lemma} », used as an adjective"
                    elif _norm(surface) != tok.lemma and _norm(surface).endswith("e") and not tok.lemma.endswith("e"):
                        tok.form_note = f"feminine form of « {tok.lemma} »"
                else:
                    tok.role = "participle"
            elif chosen.mood == "part" and chosen.tense == "pres" and prev != "en":
                adjective = entry(_norm(surface)) or {}
                tok.lemma = _norm(surface) if adjective.get("p") == "ADJ" else chosen.lemma
                tok.pos = "ADJ"
                tok.gloss = gloss(tok.lemma) or f"present participle of {chosen.lemma}"
                tok.role = "adj"
                tok.reading = None
                tok.form_note = f"present participle of « {chosen.lemma} », used as an adjective"
            elif chosen.mood == "part":
                adjective = entry(_norm(surface)) or entry(simplemma.lemmatize(_norm(surface), lang="fr"))
                if adjective and adjective.get("p") == "ADJ" and not aux:
                    tok.lemma = simplemma.lemmatize(_norm(surface), lang="fr")
                    found = entry(tok.lemma) or adjective
                    tok.pos = "ADJ"
                    tok.gloss = gloss(tok.lemma) or found.get("e", "")
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
            aux_surfaces = AVOIR_PRESENT | AVOIR_COND | AVOIR_IMPF | ETRE_PRESENT | ETRE_COND | ETRE_IMPF
            if low in aux_surfaces and chosen.lemma in {"avoir", "être"} and chosen.mood != "part":
                tok.role = "aux"
                compound = None
            if tok.role != "adj":
                tok.form_note = describe(chosen, compound=compound if tok.role == "participle" else None)
            elif not tok.form_note:
                tok.form_note = "adjective here, describing a state"
        else:
            if prefer_noun and noun_entry:
                guessed = simplemma.lemmatize(low, lang="fr")
                head = entry(guessed)
                # « des trains » is train. « la police » must not become the rare verb policer.
                if (
                    head
                    and head.get("p") in {"NOUN", "ADJ"}
                    and not _rare_verb_twin(low, guessed)
                ):
                    lemma = guessed
                    found = head
                else:
                    lemma = low
                    found = noun_entry
            else:
                lemma = simplemma.lemmatize(low, lang="fr")
                found = entry(lemma) or entry(low) or {}
            tok.lemma = lemma
            tok.pos = found.get("p") or ""
            tok.gloss = gloss(lemma) or found.get("e") or _closed_gloss(low) or _closed_gloss(lemma)
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
        if tok.gloss.strip().lower() in {"verb", "noun", "adjective"}:
            tok.gloss = ""
        if tok.pos == "NOUN":
            _apply_gender(tok, raw_pieces, index)
        prev_low = _norm(tokens[-1].text) if tokens else ""
        if tok.pos == "VERB" and prev_low in REFLEXIVES and (
            tok.lemma in {"asseoir", "assoir", "souvenir"} or prev_low in {"se", "s'"}
        ):
            tok.pronominal = True
            if tok.lemma == "assoir":
                tok.lemma = "asseoir"
        tokens.append(tok)
        if surface[:1].isalnum():
            clause_start = False
        index += 1
    _fix_object_pronouns(tokens)
    typos = _flag_typos(tokens)
    return Line(
        speaker=speaker,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        tokens=tokens,
        tip=line_tip(text),
        typos=typos,
    )


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
    return None


def pos_label(pos: str) -> str:
    return POS_LABEL.get(pos, pos.lower())


def display_noun(lemma: str, gender: str | None) -> tuple[str, str]:
    if gender:
        phrase = noun_phrase(lemma, gender)
        if phrase:
            return phrase
    return lemma, ""
