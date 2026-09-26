"""French lexicon: FreeDict glosses, frequency bands, and verb forms."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import lru_cache

from app.config import PACKAGE

DATA = PACKAGE / "data"

# Learner-facing corrections and slang the bilingual dictionary misses or garbles.
OVERRIDES: dict[str, dict] = {
    "avoir": {"p": "VERB", "g": "", "e": "to have"},
    "être": {"p": "VERB", "g": "", "e": "to be"},
    "aller": {"p": "VERB", "g": "", "e": "to go"},
    "faire": {"p": "VERB", "g": "", "e": "to do, to make"},
    "dire": {"p": "VERB", "g": "", "e": "to say"},
    "voir": {"p": "VERB", "g": "", "e": "to see"},
    "savoir": {"p": "VERB", "g": "", "e": "to know (a fact or how)"},
    "connaître": {"p": "VERB", "g": "", "e": "to know (a person or a place)"},
    "vouloir": {"p": "VERB", "g": "", "e": "to want"},
    "pouvoir": {"p": "VERB", "g": "", "e": "can, to be able to"},
    "devoir": {"p": "VERB", "g": "", "e": "to have to, must"},
    "falloir": {"p": "VERB", "g": "", "e": "to be necessary (il faut)"},
    "prendre": {"p": "VERB", "g": "", "e": "to take"},
    "venir": {"p": "VERB", "g": "", "e": "to come"},
    "partir": {"p": "VERB", "g": "", "e": "to leave"},
    "rentrer": {"p": "VERB", "g": "", "e": "to come home, to go back in"},
    "entrer": {"p": "VERB", "g": "", "e": "to go in"},
    "rester": {"p": "VERB", "g": "", "e": "to stay"},
    "attendre": {"p": "VERB", "g": "", "e": "to wait"},
    "fermer": {"p": "VERB", "g": "", "e": "to close"},
    "ouvrir": {"p": "VERB", "g": "", "e": "to open"},
    "courir": {"p": "VERB", "g": "", "e": "to run"},
    "rater": {"p": "VERB", "g": "", "e": "to miss"},
    "lire": {"p": "VERB", "g": "", "e": "to read"},
    "habiter": {"p": "VERB", "g": "", "e": "to live (in a place)"},
    "dessiner": {"p": "VERB", "g": "", "e": "to draw"},
    "regarder": {"p": "VERB", "g": "", "e": "to look, to watch"},
    "aimer": {"p": "VERB", "g": "", "e": "to like, to love"},
    "croire": {"p": "VERB", "g": "", "e": "to think, to believe"},
    "entendre": {"p": "VERB", "g": "", "e": "to hear"},
    "travailler": {"p": "VERB", "g": "", "e": "to work"},
    "écouter": {"p": "VERB", "g": "", "e": "to listen"},
    "donner": {"p": "VERB", "g": "", "e": "to give"},
    "chercher": {"p": "VERB", "g": "", "e": "to look for"},
    "arriver": {"p": "VERB", "g": "", "e": "to arrive"},
    "sourire": {"p": "VERB", "g": "", "e": "to smile"},
    "pleuvoir": {"p": "VERB", "g": "", "e": "to rain"},
    "arrêter": {"p": "VERB", "g": "", "e": "to stop"},
    "revoir": {"p": "VERB", "g": "", "e": "to see again"},
    "raccompagner": {"p": "VERB", "g": "", "e": "to take someone home"},
    "partager": {"p": "VERB", "g": "", "e": "to share, to split"},
    "promettre": {"p": "VERB", "g": "", "e": "to promise"},
    "parler": {"p": "VERB", "g": "", "e": "to speak, to talk"},
    "demander": {"p": "VERB", "g": "", "e": "to ask"},
    "trouver": {"p": "VERB", "g": "", "e": "to find"},
    "inviter": {"p": "VERB", "g": "", "e": "to invite, to treat someone"},
    "souvenir": {"p": "VERB", "g": "", "e": "to remember (se souvenir)"},
    "connaître": {"p": "VERB", "g": "", "e": "to know (a person or a place)"},
    "train": {"p": "NOUN", "g": "m", "e": "train"},
    "taxi": {"p": "NOUN", "g": "m", "e": "taxi"},
    "table": {"p": "NOUN", "g": "f", "e": "table"},
    "minuit": {"p": "NOUN", "g": "m", "e": "midnight"},
    "prof": {"p": "NOUN", "g": "m", "e": "teacher (short for professeur)"},
    "professeur": {"p": "NOUN", "g": "m", "e": "teacher"},
    "lycée": {"p": "NOUN", "g": "m", "e": "high school"},
    "souci": {"p": "NOUN", "g": "m", "e": "worry"},
    "matin": {"p": "NOUN", "g": "m", "e": "morning"},
    "café": {"p": "NOUN", "g": "m", "e": "café, coffee shop; coffee"},
    "carte": {"p": "NOUN", "g": "f", "e": "card; map"},
    "addition": {"p": "NOUN", "g": "f", "e": "the bill (in a café)"},
    "canal": {"p": "NOUN", "g": "m", "e": "canal"},
    "métro": {"p": "NOUN", "g": "m", "e": "metro, subway"},
    "heure": {"p": "NOUN", "g": "f", "e": "hour, time"},
    "porte": {"p": "NOUN", "g": "f", "e": "door"},
    "quai": {"p": "NOUN", "g": "m", "e": "platform"},
    "couloir": {"p": "NOUN", "g": "m", "e": "corridor"},
    "ami": {"p": "NOUN", "g": "m", "e": "friend"},
    "mère": {"p": "NOUN", "g": "f", "e": "mother"},
    "parent": {"p": "NOUN", "g": "m", "e": "parent"},
    "livre": {"p": "NOUN", "g": "m", "e": "book"},
    "chapitre": {"p": "NOUN", "g": "m", "e": "chapter"},
    "argent": {"p": "NOUN", "g": "m", "e": "money"},
    "endroit": {"p": "NOUN", "g": "m", "e": "place"},
    "ligne": {"p": "NOUN", "g": "f", "e": "line"},
    "vent": {"p": "NOUN", "g": "m", "e": "wind"},
    "soir": {"p": "NOUN", "g": "m", "e": "evening"},
    "phrase": {"p": "NOUN", "g": "f", "e": "sentence"},
    "numéro": {"p": "NOUN", "g": "m", "e": "number (phone number)"},
    "seconde": {"p": "NOUN", "g": "f", "e": "second"},
    "fois": {"p": "NOUN", "g": "f", "e": "time (as in 'next time')"},
    "idée": {"p": "NOUN", "g": "f", "e": "idea"},
    "monsieur": {"p": "NOUN", "g": "m", "e": "sir"},
    "chocolat": {"p": "NOUN", "g": "m", "e": "chocolate"},
    "thé": {"p": "NOUN", "g": "m", "e": "tea"},
    "serveur": {"p": "NOUN", "g": "m", "e": "waiter"},
    "rue": {"p": "NOUN", "g": "f", "e": "street"},
    "coin": {"p": "NOUN", "g": "m", "e": "corner"},
    "fenêtre": {"p": "NOUN", "g": "f", "e": "window"},
    "pluie": {"p": "NOUN", "g": "f", "e": "rain"},
    "parapluie": {"p": "NOUN", "g": "m", "e": "umbrella"},
    "veste": {"p": "NOUN", "g": "f", "e": "jacket"},
    "téléphone": {"p": "NOUN", "g": "m", "e": "phone"},
    "sac": {"p": "NOUN", "g": "m", "e": "bag"},
    "verre": {"p": "NOUN", "g": "m", "e": "glass"},
    "eau": {"p": "NOUN", "g": "f", "e": "water"},
    "lumière": {"p": "NOUN", "g": "f", "e": "light"},
    "quartier": {"p": "NOUN", "g": "m", "e": "neighborhood"},
    "boisson": {"p": "NOUN", "g": "f", "e": "drink"},
    "travail": {"p": "NOUN", "g": "m", "e": "work"},
    "personne": {"p": "NOUN", "g": "f", "e": "person, nobody"},
    "bout": {"p": "NOUN", "g": "m", "e": "end"},
    "fond": {"p": "NOUN", "g": "m", "e": "bottom"},
    "chose": {"p": "NOUN", "g": "f", "e": "thing"},
    "désolé": {"p": "ADJ", "g": "", "e": "sorry"},
    "fatigué": {"p": "ADJ", "g": "", "e": "tired"},
    "fâché": {"p": "ADJ", "g": "", "e": "annoyed, cross"},
    "mouillé": {"p": "ADJ", "g": "", "e": "wet"},
    "ouvert": {"p": "ADJ", "g": "", "e": "open"},
    "vide": {"p": "ADJ", "g": "", "e": "empty"},
    "froid": {"p": "ADJ", "g": "", "e": "cold"},
    "chaud": {"p": "ADJ", "g": "", "e": "warm, hot"},
    "gentil": {"p": "ADJ", "g": "", "e": "kind"},
    "petit": {"p": "ADJ", "g": "", "e": "little, small"},
    "long": {"p": "ADJ", "g": "", "e": "long"},
    "calme": {"p": "ADJ", "g": "", "e": "quiet, calm"},
    "vrai": {"p": "ADJ", "g": "", "e": "true"},
    "prochain": {"p": "ADJ", "g": "", "e": "next"},
    "dernier": {"p": "ADJ", "g": "", "e": "last"},
    "bon": {"p": "ADJ", "g": "", "e": "good"},
    "grave": {"p": "ADJ", "g": "", "e": "serious"},
    "français": {"p": "ADJ", "g": "", "e": "French"},
    "chelou": {"p": "ADJ", "g": "", "e": "sketchy, dodgy (verlan of louche)", "slang": "verlan"},
    "ouf": {"p": "ADJ", "g": "", "e": "crazy (verlan of fou)", "slang": "verlan"},
    "meuf": {"p": "NOUN", "g": "f", "e": "woman (verlan of femme)", "slang": "verlan"},
    "keuf": {"p": "NOUN", "g": "m", "e": "cop (verlan of flic)", "slang": "verlan"},
    "relou": {"p": "ADJ", "g": "", "e": "annoying (verlan of lourd)", "slang": "verlan"},
    "zarbi": {"p": "ADJ", "g": "", "e": "weird (verlan of bizarre)", "slang": "verlan"},
    "toujours": {"p": "ADV", "g": "", "e": "always, still"},
    "maintenant": {"p": "ADV", "g": "", "e": "now"},
    "demain": {"p": "ADV", "g": "", "e": "tomorrow"},
    "encore": {"p": "ADV", "g": "", "e": "still, again"},
    "vraiment": {"p": "ADV", "g": "", "e": "really"},
    "loin": {"p": "ADV", "g": "", "e": "far"},
    "dehors": {"p": "ADV", "g": "", "e": "outside"},
    "tôt": {"p": "ADV", "g": "", "e": "early"},
    "bien": {"p": "ADV", "g": "", "e": "well, good"},
    "beaucoup": {"p": "ADV", "g": "", "e": "a lot"},
    "merci": {"p": "INTJ", "g": "", "e": "thank you"},
    "bonjour": {"p": "INTJ", "g": "", "e": "hello"},
    "bonsoir": {"p": "INTJ", "g": "", "e": "good evening"},
    "d'accord": {"p": "INTJ", "g": "", "e": "OK, all right"},
}

CLOSED = {
    "je": "I",
    "j": "I",
    "tu": "you (someone you know well)",
    "il": "he, it",
    "elle": "she, it",
    "on": "we (in everyday speech), or 'one'",
    "nous": "we",
    "vous": "you (polite, or more than one person)",
    "ils": "they (masculine)",
    "elles": "they (feminine)",
    "me": "me, to me, myself",
    "te": "you, to you, yourself",
    "se": "oneself, himself, herself",
    "moi": "me",
    "toi": "you",
    "lui": "him, her, to him, to her",
    "leur": "their, or to them",
    "eux": "them",
    "le": "the, or him/it",
    "la": "the, or her/it",
    "les": "the, or them",
    "un": "a, one",
    "une": "a, one (feminine)",
    "des": "some, or de + les",
    "du": "de + le (of the, from the), or some",
    "au": "à + le (to the, at the)",
    "aux": "à + les (to the)",
    "de": "of, from",
    "à": "to, at",
    "et": "and",
    "ou": "or",
    "mais": "but",
    "donc": "so",
    "car": "because",
    "que": "that",
    "qui": "who, which",
    "quoi": "what",
    "dont": "of which, whose",
    "où": "where",
    "ne": "first half of a negation (ne…pas)",
    "pas": "not",
    "plus": "no longer, or more",
    "jamais": "never",
    "rien": "nothing",
    "dans": "in",
    "sur": "on",
    "sous": "under",
    "avec": "with",
    "sans": "without",
    "pour": "for, in order to",
    "par": "by, through",
    "en": "in, or the pronoun 'some / of it'",
    "y": "there (replaces à + a place)",
    "chez": "at the home of",
    "vers": "toward",
    "entre": "between",
    "ce": "this, that",
    "ça": "that, it",
    "cela": "that",
    "c": "ce, shortened (c'est = it is)",
    "mon": "my",
    "ma": "my",
    "mes": "my",
    "ton": "your",
    "ta": "your",
    "tes": "your",
    "son": "his, her, its",
    "sa": "his, her, its",
    "ses": "his, her, its",
    "notre": "our",
    "votre": "your",
    "oui": "yes",
    "non": "no",
    "si": "if, or yes (after a negative question)",
    "très": "very",
    "trop": "too, too much",
    "aussi": "also, as",
    "alors": "then, so",
    "puis": "then",
    "tout": "all, very",
    "tous": "all",
    "toute": "all",
    "cette": "this, that",
    "cet": "this, that",
    "ces": "these, those",
    "ici": "here",
    "là": "there",
    "juste": "just, right",
    "même": "same, even",
    "autre": "other",
    "peu": "little, not much",
    "comme": "like, as",
    "quand": "when",
    "comment": "how",
    "pourquoi": "why",
    "parce": "because (parce que)",
    "depuis": "since, for (a length of time)",
    "avant": "before",
    "après": "after",
    "pendant": "during",
    "moins": "less",
    "assez": "enough",
    "déjà": "already",
    "enfin": "finally, well",
    "toujours": "always, still",
    "encore": "still, again",
    "maintenant": "now",
    "vraiment": "really",
    "bien": "well",
    "mal": "badly",
    "mieux": "better",
    "près": "near",
    "loin": "far",
    "devant": "in front of",
    "derrière": "behind",
    "seulement": "only",
    "aussi": "also",
    "non": "no",
    "l'": "le or la, shortened before a vowel sound",
    "d'": "de, shortened before a vowel sound",
    "j'": "je (I), shortened before a vowel sound",
    "n'": "ne, shortened before a vowel sound",
    "m'": "me, shortened before a vowel sound",
    "t'": "te (you), shortened — in « t'as » it stands for tu",
    "s'": "se, shortened before a vowel sound",
    "c'": "ce, shortened, as in c'est (it is)",
    "qu'": "que (that), shortened before a vowel sound",
    "jusqu'": "jusque (until), shortened",
    "-ce": "part of qu'est-ce que / est-ce que",
    "-t": "a linking -t- used in inverted questions",
}

H_ASPIRE = {
    "haricot", "héros", "hors", "haine", "haut", "honte", "hibou", "hérisson",
    "handicap", "hall", "hockey", "homard", "haie", "hache", "hanche", "hasard",
    "héron", "hollandais", "hongrois", "hideux", "hiérarchie",
}

ETRE_VERBS = {
    "aller", "arriver", "descendre", "devenir", "entrer", "monter", "mourir",
    "naître", "partir", "passer", "rester", "retourner", "revenir", "sortir",
    "tomber", "venir", "rentrer", "repartir", "intervenir", "parvenir",
    "devenir", "survenir",
}

SKIP_LEMMAS = {
    "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "me", "te", "se",
    "moi", "toi", "lui", "leur", "le", "la", "les", "un", "une", "des", "de", "à",
    "et", "ou", "mais", "donc", "or", "ni", "car", "que", "qui", "quoi", "dont", "où",
    "ne", "pas", "plus", "jamais", "rien", "personne", "dans", "sur", "sous", "avec",
    "sans", "pour", "par", "en", "y", "ce", "cet", "cette", "ces", "ça", "cela",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "notre", "nos",
    "votre", "vos", "oui", "non", "si", "très", "trop", "aussi", "alors", "donc",
    "puis", "enfin", "juste", "là", "ici", "même", "autre", "peu", "comme", "quand",
    "comment", "pourquoi", "parce", "depuis", "avant", "après", "pendant", "moins",
    "assez", "déjà", "encore", "bien", "mal", "tout", "tous", "toute", "toutes",
    "au", "du", "aux", "d'", "l'", "j'", "n'", "m'", "t'", "s'", "c'", "qu'",
    "chez", "vers", "entre", "près", "devant", "derrière", "seulement", "aussi",
    "être",
}

LEVEL_LABEL = {
    "A1": "A1 · very common",
    "A2": "A2 · common",
    "B1": "B1 · useful",
    "B2": "B2 · less common",
    "C1": "C1 · rare",
}

POS_LABEL = {
    "NOUN": "noun",
    "VERB": "verb",
    "ADJ": "adjective",
    "ADV": "adverb",
    "INTJ": "expression",
    "EXPR": "expression",
    "PRON": "pronoun",
    "DET": "determiner",
    "ADP": "preposition",
    "AUX": "auxiliary",
}


@dataclass(frozen=True)
class Reading:
    lemma: str
    mood: str
    tense: str
    person: str
    number: str
    gender: str


_dict: dict | None = None
_ranks: dict | None = None
_forms: dict | None = None
_verb_rank: dict | None = None


def load() -> None:
    global _dict, _ranks, _forms, _verb_rank
    if _dict is not None:
        return
    _dict = json.loads((DATA / "fra_eng.json").read_text(encoding="utf-8"))
    _ranks = json.loads((DATA / "fr_ranks.json").read_text(encoding="utf-8"))
    with gzip.open(DATA / "verbs.json.gz", "rt", encoding="utf-8") as handle:
        blob = json.load(handle)
    _forms = blob["forms"]
    _verb_rank = {k: int(v) for k, v in blob.get("verb_rank", {}).items()}


def reset_cache() -> None:
    readings_for.cache_clear()


def entry(lemma: str) -> dict | None:
    load()
    key = lemma.lower().replace("’", "'")
    if key in OVERRIDES:
        return OVERRIDES[key]
    assert _dict is not None
    return _dict.get(key)


def rank_of(lemma: str, surface: str | None = None) -> int | None:
    load()
    assert _ranks is not None and _verb_rank is not None
    vals = []
    if lemma in _verb_rank:
        vals.append(_verb_rank[lemma])
    if lemma in _ranks:
        vals.append(int(_ranks[lemma]))
    if surface and surface.lower() in _ranks:
        vals.append(int(_ranks[surface.lower()]))
    return min(vals) if vals else None


def level_for(rank: int | None) -> str:
    if rank is None:
        return ""
    if rank <= 700:
        return "A1"
    if rank <= 1800:
        return "A2"
    if rank <= 4500:
        return "B1"
    if rank <= 12000:
        return "B2"
    return "C1"


def level_label(level: str) -> str:
    return LEVEL_LABEL.get(level, level)


def noun_phrase(lemma: str, gender: str) -> tuple[str, str] | None:
    if gender not in {"m", "f"} or not lemma:
        return None
    first = lemma[0].lower()
    aspire = lemma.lower() in H_ASPIRE
    vowelish = first in "aeiouàâäéèêëîïôöùûüÿœæh" and not aspire
    if gender == "f":
        definite, indefinite = ("l'" if vowelish else "la"), "une"
    else:
        definite, indefinite = ("l'" if vowelish else "le"), "un"

    def join(article: str) -> str:
        if article.endswith("'"):
            return article + lemma
        return f"{article} {lemma}"

    return join(definite), join(indefinite)


def parse_tag(tag: str) -> Reading:
    lemma, morph, feats = tag.split("|")
    mood, _, tense = morph.partition(".")
    person = number = gender = ""
    if feats and feats[0] in "123":
        person = feats[0]
        feats = feats[1:]
    if feats[:1] in {"s", "p"}:
        number = feats[0]
        feats = feats[1:]
    if feats[:1] in {"m", "f"}:
        gender = feats[0]
    return Reading(lemma, mood, tense, person, number, gender)


@lru_cache(maxsize=20000)
def readings_for(surface: str) -> tuple[Reading, ...]:
    load()
    assert _forms is not None
    tags = _forms.get(surface.lower().replace("’", "'"), [])
    return tuple(parse_tag(tag) for tag in tags)


def lemma_rank(lemma: str) -> int:
    found = rank_of(lemma)
    return found if found is not None else 10**9
