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
NUMBER_DET = {
    "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix",
    "onze", "douze", "treize", "quatorze", "quinze", "seize", "vingt", "trente",
    "quarante", "cinquante", "soixante", "cent", "mille", "plusieurs", "quelques",
    "zéro", "zero",
}
# Words that can sit in front of a command without making it a statement.
DISCOURSE = {
    "non", "oui", "alors", "bon", "ben", "eh", "hé", "he", "oh", "allez",
    "mais", "donc", "euh", "bah", "hein", "voyons",
}
_FUTURE_PROMISE = re.compile(
    r"\b(demain|bientôt|bientot|ce soir|cette nuit|plus tard|tout à l'heure|tout a l'heure|"
    r"après-demain|apres-demain|après demain|apres demain|dorénavant|dorenavant|"
    r"désormais|desormais|promis|promets|jure)\b|\bprochaine?\b",
    re.I,
)
_INFINITIVE_LEMMAS = {
    "aller", "devoir", "pouvoir", "vouloir", "falloir", "venir", "compter",
    "laisser", "oser", "penser", "espérer", "essayer", "commencer", "savoir",
}
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
    typo_high: bool = False
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
    corrected_text: str = ""


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


def _subject_before_clitic(pieces: list[str], index: int) -> bool:
    """True when le/la/les/l' just after a subject is a pronoun, not an article."""
    j = index - 2
    while j >= 0 and _norm(pieces[j]) in {"ne", "n'"}:
        j -= 1
    if j < 0:
        return False
    return _norm(pieces[j]) in SUBJECTS


_BARE_OBJECT = {"le", "la", "les", "l'", "lui", "leur", "en", "y", "me", "te", "se", "m'", "t'", "s'"}
_CLAUSE_BREAK = {",", ".", "?", "!", ";", ":"}


def _raw_is_object_pronoun(pieces: list[str], index: int) -> bool:
    """vous/nous is an object when ne, another subject, or a noun sits to its left."""
    if _norm(pieces[index]) not in {"vous", "nous"}:
        return False
    for j in range(index - 1, -1, -1):
        word = _norm(pieces[j])
        if word in _CLAUSE_BREAK:
            break
        if word in {"ne", "n'"} or (word in SUBJECTS and word not in {"ce"}):
            return True
        if word in {"monde", "gens", "chacun", "chacune", "quelqu'un", "quelqu'une"}:
            return True
        if word in _BARE_OBJECT or word in BETWEEN or word in DETERMINERS or word in DISCOURSE or word in {"qu'", "que", "qui", "tout"}:
            continue
        found = entry(word) or entry(simplemma.lemmatize(word, lang="fr"))
        if found and found.get("p") == "NOUN":
            return True
        break
    return False


def _subject_before(tokens: list[str], index: int) -> tuple[str, str] | None:
    for j in range(index - 1, -1, -1):
        low = _norm(tokens[j])
        if low in _CLAUSE_BREAK:
            break
        if low in {"vous", "nous"} and _raw_is_object_pronoun(tokens, j):
            continue
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
            # « Vous voulez » has a subject, so the vous-form is not a command.
            stated = [r for r in pool if r.mood != "imp"]
            if stated:
                pool = stated
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
    """typer/type, policer/police, fenêtrer/fenêtre, former/forme, terrer/terre."""
    if lemma == surface:
        return False
    bases = [surface]
    if surface.endswith("s") and len(surface) > 3:
        bases.append(surface[:-1])
    for base in bases:
        if lemma == base + "r":
            return True
        stem = base[:-1] if base.endswith("e") else base
        if stem and lemma == stem + "er":
            return True
    return False


_NOUNISH_PREV = {"de", "d'", "sans", "avec", "par", "pour", "en", "dans", "sur", "sous", "vers"}


def _dictionary_noun(low: str) -> dict | None:
    found = entry(low) or entry(simplemma.lemmatize(low, lang="fr"))
    if found and found.get("p") == "NOUN":
        return found
    return None


def _verb_homograph(low: str) -> bool:
    """A dictionary noun that only collides with a rare twin or a participle."""
    readings = readings_for(_lookup_surface(low))
    if not readings:
        return False
    return all(_rare_verb_twin(low, reading.lemma) or reading.mood == "part" for reading in readings)


def _noun_override(low: str, prev: str, gender: str) -> dict | None:
    """After a determiner or a bare noun, a noun reading beats a stray verb homograph."""
    prepish = prev in DETERMINERS or prev in NUMBER_DET or prev in _NOUNISH_PREV or bool(gender)
    if not prepish:
        if (not prev or prev in _CLAUSE_BREAK) and _verb_homograph(low):
            return _dictionary_noun(low)
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


def _governing_subject(pieces: list[str], index: int) -> str | None:
    """Subject pronoun or noun governing this verb. Object vous/nous does not count."""
    j = index - 1
    while j >= 0:
        word = _norm(pieces[j])
        if word in _CLAUSE_BREAK:
            break
        if word in {"ne", "n'"} or word in _BARE_OBJECT or word in BETWEEN or word in {"pas", "plus", "jamais", "rien"}:
            j -= 1
            continue
        if word in {"vous", "nous"}:
            if _raw_is_object_pronoun(pieces, j):
                j -= 1
                continue
            return word
        if word in SUBJECTS and word not in {"ce"}:
            return word
        if word in {"monde", "gens", "chacun", "chacune", "quelqu'un", "quelqu'une"}:
            return "noun"
        if word in DISCOURSE:
            j -= 1
            continue
        found = entry(word) or entry(simplemma.lemmatize(word, lang="fr"))
        if found and found.get("p") == "NOUN":
            return "noun"
        return None
    return None


def _imperative_person(pieces: list[str], index: int) -> tuple[str, str] | None:
    """Commands keep an object clitic even when spoken French drops ne: « t'inquiète pas »."""
    if _governing_subject(pieces, index):
        return None
    lows = [_norm(piece) for piece in pieces]
    j = index - 1
    saw_ne = False
    saw_clitic = False
    while j >= 0 and lows[j] not in _CLAUSE_BREAK:
        word = lows[j]
        if word in {"ne", "n'"}:
            saw_ne = True
            j -= 1
            continue
        if word in REFLEXIVES or word in _BARE_OBJECT or word in {"vous", "nous"}:
            saw_clitic = True
            j -= 1
            continue
        if word in DISCOURSE:
            j -= 1
            continue
        return None
    nxt = lows[index + 1] if index + 1 < len(lows) else ""
    object_after = nxt in OBJECT_CLITIC
    subject_after = nxt in SUBJECT_CLITIC or nxt == "-t"
    neg_after = nxt in {"pas", "plus", "jamais", "rien"}
    if subject_after and not saw_ne:
        return None
    if not (saw_ne or object_after or (neg_after and (saw_ne or saw_clitic))):
        return None
    verb = lows[index]
    if verb.endswith("ez") or verb in {"dites", "faites", "soyez", "ayez", "allez"}:
        return ("2", "p")
    if verb.endswith("ons"):
        return ("1", "p")
    return ("2", "s")


def _built_pronoun_is_object(tokens: list[Tok], index: int) -> bool:
    low = _norm(tokens[index].text)
    if low not in {"vous", "nous"}:
        return False
    for earlier in range(index - 1, -1, -1):
        tok = tokens[earlier]
        if not tok.is_word:
            if tok.text in ".?!;:":
                break
            continue
        prev = _norm(tok.text)
        if prev in {"ne", "n'"} or (prev in SUBJECTS and prev not in {"ce"}):
            return True
        if tok.pos == "NOUN" or tok.role == "noun" or prev in {"monde", "gens", "chacun", "chacune"}:
            return True
        if prev in _BARE_OBJECT or prev in BETWEEN or prev in DETERMINERS or prev in DISCOURSE or tok.pos in {"DET", "ADJ", "ADP", "ADV"}:
            continue
        break
    return False


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
        if low in {"vous", "nous"} and _built_pronoun_is_object(tokens, index):
            continue
        if low in SUBJECTS and tok.pos == "PRON" and low not in {"ce"}:
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


def _adjective_after_noun(tokens: list[Tok], low: str, nxt: str) -> dict | None:
    """« un chariot vide » is the adjective empty, unless an object follows (« vide le sac »)."""
    prev = next((tok for tok in reversed(tokens) if tok.is_word), None)
    if not prev or prev.pos != "NOUN" or prev.role == "typo":
        return None
    found = entry(low)
    if not found or found.get("p") != "ADJ":
        return None
    if nxt in DETERMINERS or nxt in NUMBER_DET or nxt in {"de", "d'"}:
        return None
    return found


def _licenses_infinitive(tokens: list[Tok], index: int) -> bool:
    for tok in reversed(tokens[max(0, index - 6) : index]):
        low = _norm(tok.text)
        if low in REFLEXIVES or low in {"ne", "n'", "pas", "plus", "jamais"}:
            continue
        if tok.lemma in _INFINITIVE_LEMMAS or low in {"va", "vais", "vas", "vont", "allons", "allez"}:
            return True
        if tok.is_word and tok.role not in {"closed", "punct"}:
            return False
    return False


_INF_SKIP = _BARE_OBJECT | DETERMINERS | {"ne", "n'", "pas", "plus", "jamais", "qu'", "que", "qui"}


def _preposition_or_modal_licenses(tokens: list[Tok], index: int) -> bool:
    """à/de/pour/sans, or a modal, licenses a real infinitive. Skip one article or clitic."""
    for tok in reversed(tokens[:index]):
        low = _norm(tok.text)
        if low in _CLAUSE_BREAK:
            break
        if low in _INF_SKIP or low in BETWEEN:
            continue
        if low in {"à", "de", "d'", "pour", "sans"}:
            return True
        if tok.lemma in _INFINITIVE_LEMMAS or low in {"va", "vais", "vas", "vont", "allons", "allez", "faut"}:
            return True
        return False
    return False


def _attested_form(surface: str) -> bool:
    return bool(entry(surface) or readings_for(surface))


def _flag_typos(tokens: list[Tok], text: str) -> list[str]:
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
        licensed = _preposition_or_modal_licenses(tokens, index)
        if (
            not licensed
            and recent_aux(index, "avoir")
            and not participle_between(index)
            and tok.reading
            and tok.reading.mood == "inf"
            and low.endswith("er")
        ):
            guess = low[:-2] + "é"
        elif (
            not licensed
            and recent_aux(index, "avoir")
            and not participle_between(index)
            and low.endswith("ez")
            and tok.reading
            and tok.reading.mood in {"ind", "imp"}
        ):
            guess = {"passer": "passé"}.get(tok.lemma, "")
            if not guess and tok.lemma.endswith("er"):
                guess = tok.lemma[:-2] + "é"
        elif low.endswith("ants") and not entry(low) and not readings_for(low):
            # « marchants » after de/les is the noun marchands. A missed plural
            # adjective (« mouvants ») is not a singular participle.
            noun = low[:-4] + "ands"
            prev = prevs[-1] if prevs else ""
            singular = noun[:-1] if noun.endswith("s") else noun
            found = entry(noun) or entry(singular)
            if found and found.get("p") == "NOUN" and prev in (DETERMINERS | NUMBER_DET | {"de", "d'", "des", "du"}):
                guess = noun
        elif (
            index
            and prevs
            and prevs[-1] in {"m'", "t'", "s'"}
            and tok.reading
            and tok.reading.lemma.endswith("er")
            and not recent_aux(index, "avoir")
            and not recent_aux(index, "être")
            and low.endswith("é")
        ):
            # « t'inquiété » is not a word; « va m'arrivé » wants the infinitive.
            # « Ça m'arrivé » still wants the attested present « m'arrive ».
            naive = low[:-1] + "e"
            clitic = prevs[-1]
            if _licenses_infinitive(tokens, index) or not _attested_form(naive):
                guess = clitic + tok.reading.lemma
            else:
                guess = clitic + naive
        elif (
            tok.reading
            and tok.reading.mood == "cond"
            and tok.reading.person == "1"
            and tok.reading.number == "s"
            and low.endswith("ais")
            and _FUTURE_PROMISE.search(text)
        ):
            guess = low[:-1]
        elif low == "mère" and "la" in prevs[-2:] and any(word in {"sur", "dans", "en", "sous", "vers"} for word in prevs):
            guess = "mer (the sea)"
        if not guess:
            continue
        label = f"possible subtitle typo, likely {guess}"
        tok.typo = guess
        tok.typo_high = True
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
        # « Je le regarde »: le is an object pronoun. « à la route » keeps the article.
        if prev in {"le", "la", "les", "l'"} and _subject_before_clitic(raw_pieces, index) and not aux:
            prefer_noun = False
        adj_here = None if aux or informal else _adjective_after_noun(tokens, low, nxt)
        chosen = None if prefer_noun or informal or adj_here else _choose(
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
            if adj_here:
                lemma = low
                found = adj_here
            elif prefer_noun and noun_entry:
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
        if _norm(surface) == "urgences":
            tok.lemma = "urgences"
            tok.pos = "NOUN"
            tok.role = "noun"
            tok.gloss = gloss("urgences") or "the emergency room; emergencies"
            tok.gender = "f"
            if (tok.form_note or "").startswith("dictionary form"):
                tok.form_note = ""
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
    typos = _flag_typos(tokens, text)
    # Replace typos in the original string before expressions fold several words into one token.
    corrected = corrected_sentence(tokens, text)
    _collapse_expressions(tokens)
    return Line(
        speaker=speaker,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        tokens=tokens,
        tip=line_tip(text),
        typos=typos,
        corrected_text=corrected,
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


_CUTOFF = {"coupé", "coupée", "coupés", "coupées", "coupe", "coupes"}
_NO_SPACE_BEFORE = set(".,?!;:…»)")
_NO_SPACE_AFTER = set("'’-(«")


def _next_word(tokens: list[Tok], start: int) -> int | None:
    j = start
    while j < len(tokens):
        if tokens[j].is_word:
            return j
        j += 1
    return None


def _future_homophone_typo(tok: Tok) -> bool:
    """« ferais » → « ferai » is still the verb inside « faire attention »."""
    if not tok.typo:
        return False
    guess = re.sub(r"\s*\([^)]*\)", "", tok.typo).strip().lower()
    surface = _norm(tok.text)
    return bool(surface.endswith("ais") and guess == surface[:-1])


def _collapse_expressions(tokens: list[Tok]) -> None:
    """Fold conjugated multi-word phrases into one expression token."""
    i = 0
    while i < len(tokens):
        span = _expression_span(tokens, i)
        if not span:
            i += 1
            continue
        end, lemma, meaning = span
        if any(tokens[k].typo and not _future_homophone_typo(tokens[k]) for k in range(i, end)):
            i += 1
            continue
        text = _join_surface([tok.text for tok in tokens[i:end]])
        tokens[i:end] = [Tok(text=text, lemma=lemma, pos="EXPR", gloss=meaning, role="expr")]
        i += 1


def _expression_span(tokens: list[Tok], index: int) -> tuple[int, str, str] | None:
    tok = tokens[index]
    if not tok.is_word or tok.role == "expr":
        return None
    if tok.typo and not _future_homophone_typo(tok):
        return None
    low = _norm(tok.text)
    if low == "on":
        j1 = _next_word(tokens, index + 1)
        j2 = _next_word(tokens, j1 + 1) if j1 is not None else None
        j3 = _next_word(tokens, j2 + 1) if j2 is not None else None
        if (
            j1 is not None
            and j2 is not None
            and j3 is not None
            and _norm(tokens[j1].text) == "a"
            and _norm(tokens[j2].text) in {"été", "ete"}
            and _norm(tokens[j3].text) in _CUTOFF
        ):
            return j3 + 1, "on a été coupé", "we got cut off"
    if low in REFLEXIVES:
        verb = _next_word(tokens, index + 1)
        if verb is not None and tokens[verb].lemma == "promener":
            return verb + 1, "se promener", "to go for a walk"
        if verb is not None and tokens[verb].lemma == "occuper":
            prep = _next_word(tokens, verb + 1)
            if prep is not None and _norm(tokens[prep].text) in {"de", "d'"}:
                return prep + 1, "s'occuper de", "to take care of; to deal with"
    if tok.lemma == "faire":
        noun = _next_word(tokens, index + 1)
        if noun is not None and (tokens[noun].lemma == "attention" or _norm(tokens[noun].text) == "attention"):
            end = noun + 1
            prep = _next_word(tokens, noun + 1)
            if prep is not None and _norm(tokens[prep].text) in {"à", "a"}:
                end = prep + 1
            return end, "faire attention (à)", "to be careful; to pay attention"
    return None


def _join_surface(pieces: list[str]) -> str:
    out = ""
    for piece in pieces:
        if not piece:
            continue
        if not out:
            out = piece
            continue
        if piece[0] in _NO_SPACE_BEFORE or piece.startswith("-") or out[-1] in _NO_SPACE_AFTER:
            out += piece
        else:
            out += " " + piece
    return out


def corrected_sentence(tokens: list[Tok], original: str) -> str:
    """French with high-confidence typos replaced inside the original spacing.

    Speaker dashes keep their spaces. Only a confident guess is substituted,
    and only that word, so the rest of the line is left as printed.
    """
    pairs: list[tuple[int, int, str]] = []
    search_from = 0
    folded = original.lower()
    for index, tok in enumerate(tokens):
        if not tok.typo or not tok.typo_high:
            continue
        guess = re.sub(r"\s*\([^)]*\)", "", tok.typo).strip()
        if not guess:
            continue
        span = tok.text
        prev = tokens[index - 1].text if index else ""
        prev_norm = _norm(prev)
        guess_norm = guess.lower().replace("’", "'")
        if prev_norm and guess_norm.startswith(prev_norm):
            span = prev + tok.text
        idx = folded.find(span.lower(), search_from)
        if idx < 0 and span != tok.text:
            span = tok.text
            idx = folded.find(span.lower(), search_from)
        if idx < 0:
            continue
        pairs.append((idx, idx + len(span), guess))
        search_from = idx + len(span)
    if not pairs:
        return original
    out = original
    for start, end, repl in reversed(pairs):
        out = out[:start] + repl + out[end:]
    return out


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


def plural_headword(lemma: str) -> bool:
    """« urgences » is stored as its own plural headword, not « l'urgences »."""
    key = (lemma or "").lower()
    if not key.endswith("s"):
        return False
    return simplemma.lemmatize(key, lang="fr") != key


def display_noun(lemma: str, gender: str | None) -> tuple[str, str]:
    if gender and plural_headword(lemma):
        return f"les {lemma}", ""
    if gender:
        phrase = noun_phrase(lemma, gender)
        if phrase:
            return phrase
    return lemma, ""
