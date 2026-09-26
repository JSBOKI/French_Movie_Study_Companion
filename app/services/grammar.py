"""Grammar notes grounded in the lines of one scene. Explanations stay in plain English."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.services.analyze import Line

VERLAN = {
    "chelou": ("louche", "sketchy, dodgy"),
    "ouf": ("fou", "crazy"),
    "meuf": ("femme", "woman"),
    "keuf": ("flic", "cop"),
    "relou": ("lourd", "annoying"),
    "zarbi": ("bizarre", "weird"),
    "tromé": ("métro", "metro"),
}


@dataclass
class Note:
    id: str
    title: str
    explanation: str
    examples: list[dict] = field(default_factory=list)
    priority: int = 50
    review: bool = False


def _ex(line: Line, note: str = "") -> dict:
    return {"fr": line.text, "en": line.translation, "note": note}


def _low(line: Line) -> str:
    return line.text.lower().replace("’", "'")


def detect_grammar(lines: list[Line], already_seen: set[str] | None = None) -> list[Note]:
    notes: list[Note] = []
    pc = [line for line in lines if _has_role(line, "participle", compound=True)]
    imp = [line for line in lines if _has_tense(line, "impf")]
    if pc and imp:
        notes.append(
            Note(
                id="passe_compose_imparfait",
                priority=1,
                title="Passé composé or imparfait?",
                explanation=(
                    "Both tenses talk about the past, and films use them side by side. "
                    "The passé composé is a finished event: auxiliary avoir or être in the present, "
                    "plus a past participle (on a raté, la porte s'est fermée). "
                    "The imparfait is the background, a description, or a habit. "
                    "You can often hear it in the endings -ais, -ait, -ions, -iez, -aient "
                    "(j'étais, il faisait, tu lisais). "
                    "A handy English test: if you could say “was …-ing” or “used to”, it is usually the imparfait. "
                    "If it is one completed action in the story, it is the passé composé."
                ),
                examples=[_ex(pc[0], "Passé composé: a completed event."), _ex(imp[0], "Imparfait: background or habit.")],
            )
        )
    elif pc:
        notes.append(_passe(pc))
    elif imp:
        notes.append(_imparfait(imp))

    spoken = [line for line in lines if re.search(r"\b(t'as|t'es|j'sais|j'suis|j'vais|y'a)\b", _low(line))]
    if spoken:
        notes.append(
            Note(
                id="spoken_french",
                priority=4,
                title="Spoken shortcuts: t'as, j'sais, y'a",
                explanation=(
                    "Film dialogue rarely sounds like a textbook. A few vowels disappear. "
                    "« t'as » means « tu as », « t'es » means « tu es », « j'sais » means « je sais », "
                    "and « y'a » means « il y a » (there is / there are). "
                    "The meaning is the same as the full form. You will see the full form in writing and the short form in speech."
                ),
                examples=[_ex(spoken[0])],
            )
        )

    dropped = []
    full = []
    for line in lines:
        low = _low(line)
        for clause in re.split(r"[.!?]", low):
            has_ne = bool(re.search(r"\bne\b|\bn'", clause))
            has_pas = bool(re.search(r"\b(pas|jamais|rien)\b", clause))
            has_plus = bool(re.search(r"\bplus\b", clause)) and bool(
                re.search(r"n'|ne |y'a plus|a plus|plus de|plus personne", clause)
            )
            bare = re.fullmatch(r"pas du tout", clause.strip(" .!?"))
            if bare:
                continue
            if (has_pas or has_plus) and has_ne:
                full.append(line)
            elif (has_pas or (has_plus and not has_ne)) and _has_verb(line):
                dropped.append(line)
    if dropped or full:
        bits = [
            "Negation in careful French is two words: ne … pas, ne … jamais, ne … plus, ne … rien. "
            "The ne comes before the verb, and pas (or jamais, plus, rien) comes after it: "
            "« mes parents ne disaient rien »."
        ]
        if dropped:
            bits.append(
                "In spoken French the ne is very often dropped. « j'sais pas » means « je ne sais pas », "
                "and « c'est pas grave » means « ce n'est pas grave ». The pas alone still means “not”."
            )
        if any(re.search(r"\bpas de\b", _low(line)) for line in lines):
            bits.append(
                "After a negation, “some” disappears: « j'ai pas de parapluie » uses de, not un. "
                "Compare « j'ai un parapluie » (I have an umbrella) with « j'ai pas de parapluie » (I don't have an umbrella)."
            )
        examples = []
        if full:
            examples.append(_ex(full[0], "Full ne … pas / jamais / plus."))
        if dropped:
            examples.append(_ex(dropped[0], "Spoken French, with ne left out."))
        notes.append(
            Note(
                id="negation",
                priority=5,
                title="Negation, and the missing ne",
                explanation=" ".join(bits),
                examples=examples[:2],
            )
        )

    sub_lines = [line for line in lines if _has_mood(line, "sub") or _trigger(line)]
    if sub_lines:
        notes.append(
            Note(
                id="subjunctive",
                priority=6,
                title="The subjunctive after certain que-phrases",
                explanation=(
                    "After phrases like « il faut que », « vouloir que », « aimerais que », « avant que », "
                    "and « jusqu'à ce que », French uses the subjunctive. It marks something wanted, needed, or not-yet-real, "
                    "not a plain fact. "
                    "For many -er verbs the subjunctive looks exactly like the ordinary present: « qu'on trouve », « qu'il ferme ». "
                    "The clue is the phrase in front, not a new ending. "
                    "Some verbs do change. « lire » becomes « lise » (not « lit »), and « revoir » becomes « revoie » (not « revoit »). "
                    "When you hear que after faut, vouloir, or avant, expect this mood."
                ),
                examples=[_ex(sub_lines[0])],
            )
        )

    reflex = [line for line in lines if _reflexive(line)]
    if reflex:
        notes.append(
            Note(
                id="reflexive",
                priority=7,
                title="Reflexive verbs: se, me, te",
                explanation=(
                    "A reflexive verb points back at the subject with me, te, se, nous, or vous. "
                    "« je m'en souviens » is se souvenir (to remember), and « on se connaît » is se connaître. "
                    "In the passé composé, reflexive verbs take être, not avoir: « la porte s'est fermée ». "
                    "The past participle then often agrees with the subject, which is why you see the extra e on fermée "
                    "(la porte is feminine). "
                    "In a negative command the pronoun stays in front: « te fais pas de souci » is the spoken form of "
                    "« ne te fais pas de souci ». A positive command would put it after the verb (« fais-toi »), "
                    "but films mostly use the negative pattern."
                ),
                examples=[_ex(reflex[0])],
            )
        )

    contraction = re.compile(r"\b(du|au|aux)\b|\bd'|\bl'")

    def _shows_contraction(line: Line) -> bool:
        low = _low(line).strip(" .!?…")
        # « pas du tout » is a fixed answer, not de + le.
        if low == "pas du tout":
            return False
        return bool(contraction.search(_low(line)))

    contraction_lines = [line for line in lines if _shows_contraction(line)]
    if contraction_lines:
        sample = contraction_lines[0]
        notes.append(
            Note(
                id="contractions",
                priority=8,
                title="Contractions: du, au, and d'",
                explanation=(
                    "Little words fuse so they are easier to say. "
                    "de + le becomes du (« près du canal » = près de le canal). "
                    "à + le becomes au (« au coin » = à le coin), and à + les becomes aux. "
                    "de + les is des. "
                    "Before a vowel sound, the e or a drops: de + accord → d'accord, de + argent → d'argent, "
                    "le + heure → l'heure. "
                    "You do not say « de le » or « à le » in ordinary French."
                ),
                examples=[_ex(sample)],
            )
        )

    pronouns = [line for line in lines if _object_pronoun(line)]
    if pronouns:
        notes.append(
            Note(
                id="pronouns",
                priority=10,
                title="Object pronouns sit before the verb",
                explanation=(
                    "Words like me, te, le, la, les, lui, leur, y, and en usually come before the verb, "
                    "not after it as in English. « je t'invite » is “I invite you”, and « je le cherche » is “I'm looking for it”. "
                    "When two pronouns share a verb, the order is: me / te / nous / vous, then le / la / les, "
                    "then lui / leur, then y, then en. "
                    "« je m'en souviens » is me + en: en replaces « de + something » (se souvenir de). "
                    "« on y va » uses y for “there” (à + a place). "
                    "The same pronouns stay in front in the passé composé: « je t'ai attendu », « tu m'as invitée »."
                ),
                examples=[_ex(pronouns[0])],
            )
        )

    verlan_hits = []
    for line in lines:
        for word in VERLAN:
            if re.search(rf"\b{word}\b", _low(line)):
                verlan_hits.append((line, word))
    if verlan_hits:
        glosses = ", ".join(f"« {word} » from « {base} » ({en})" for _, word in verlan_hits[:4] for base, en in [VERLAN[word]])
        # unique words
        seen = []
        bits = []
        for line, word in verlan_hits:
            if word in seen:
                continue
            seen.append(word)
            base, en = VERLAN[word]
            bits.append(f"« {word} » flips « {base} » ({en})")
        notes.append(
            Note(
                id="verlan",
                priority=3,
                title="Verlan and film slang",
                explanation=(
                    "Verlan is a spoken-French game that swaps syllables. "
                    + "; ".join(bits)
                    + ". You will hear it constantly in films and almost never in a textbook drill. "
                    "The ordinary word is what you want in careful writing. The verlan word is what the character actually says."
                ),
                examples=[_ex(verlan_hits[0][0])],
            )
        )

    proche = [line for line in lines if _futur_proche(line)]
    if proche:
        notes.append(
            Note(
                id="futur_proche",
                priority=10,
                title="Near future: aller + infinitive",
                explanation=(
                    "A very common way to talk about what is about to happen is the present of aller plus an infinitive. "
                    "« je vais demander » means “I'm going to ask”. "
                    "This is not the same as aller followed by a place: « on va au café » just means “we're going to the café”. "
                    "Look for a verb in the infinitive (usually ending in -er, -ir, -re, or -oir) right after vais, vas, va, allons, or vont."
                ),
                examples=[_ex(proche[0])],
            )
        )

    cond = [line for line in lines if _has_mood(line, "cond")]
    if cond:
        notes.append(
            Note(
                id="conditional",
                priority=11,
                title="The conditional: would",
                explanation=(
                    "The conditional is the “would” form. The ending looks like the future plus the imparfait: "
                    "-rais, -rais, -rait, -rions, -riez, -raient. "
                    "« j'aimerais » means “I would like”. It is softer than « je veux » (I want), which is why people use it for invitations and wishes. "
                    "A wish about someone else often continues with que and the subjunctive: « j'aimerais qu'on se revoie »."
                ),
                examples=[_ex(cond[0])],
            )
        )

    if any(re.search(r"\bde la\b|\bdu\b|\bpas de\b|\bd'eau\b|\bd'argent\b", _low(line)) for line in lines):
        sample = next(
            line
            for line in lines
            if re.search(r"\bde la\b|\bpas de\b|\bverre d'", _low(line))
        ) if any(re.search(r"\bde la\b|\bpas de\b|\bverre d'", _low(line)) for line in lines) else lines[0]
        if any(re.search(r"\bde la\b|\bpas de\b|\bd'eau\b", _low(line)) for line in lines):
            notes.append(
                Note(
                    id="partitive",
                    priority=12,
                    title="Some: du, de la, de l', and pas de",
                    explanation=(
                        "French often says “some” even when English leaves it out. "
                        "Use du before a masculine noun (du chocolat), de la before a feminine noun (de la lumière), "
                        "and de l' before a vowel (de l'eau). "
                        "After a negation, all of those become de: « pas d'argent », « pas de train ». "
                        "« un verre d'eau » is “a glass of water” — here de means “of”, and the e drops before the vowel in eau."
                    ),
                    examples=[_ex(sample)],
                )
            )

    feminine = [line for line in lines if re.search(r"\b\w+ée\b", _low(line)) and _has_role(line, "participle")]
    if feminine:
        notes.append(
            Note(
                id="agreement",
                priority=13,
                title="Why the participle grows an e",
                explanation=(
                    "Past participles sometimes agree, and the extra e (or s) is the visible sign. "
                    "With être, the participle usually agrees with the subject: « la porte s'est fermée » "
                    "because porte is feminine. "
                    "With avoir, it agrees with a direct object that comes before the verb. "
                    "In « tu m'as invitée », m' means Léa, so invitée takes the feminine e. "
                    "Said to a man, the same sentence would be « tu m'as invité », with no e. "
                    "« je dois être rentrée » uses the same feminine ending because the speaker is talking about herself."
                ),
                examples=[_ex(feminine[0])],
            )
        )

    tu_vous = any(re.search(r"\btu\b|\bt'", _low(line)) for line in lines) and any(
        re.search(r"s'il vous plaît|monsieur|vous ", _low(line)) for line in lines
    )
    if tu_vous:
        sample = next(line for line in lines if re.search(r"vous", _low(line)))
        notes.append(
            Note(
                id="tu_vous",
                priority=14,
                title="Tu with friends, vous with the waiter",
                explanation=(
                    "French has two words for “you”. Tu is for one person you know well: friends, family, children. "
                    "Vous is the polite form for a stranger or anyone you want to treat with distance, and it is also the plural. "
                    "In a café, customers say « s'il vous plaît » to the waiter, then turn back to a friend with tu. "
                    "The verb ending changes with it: tu écoutes, but vous écoutez."
                ),
                examples=[_ex(sample)],
            )
        )

    questions = [line for line in lines if "?" in line.text]
    if questions:
        estce = [line for line in questions if re.search(r"qu'est-ce|est-ce que", _low(line))]
        explanation = (
            "Spoken questions often keep ordinary word order and simply rise at the end: « on y va ? », « t'as une carte ? ». "
            "You do not have to invert the verb. "
            "« est-ce que » is a polite spoken marker you can park in front of a statement to make it a question. "
            "« qu'est-ce qu'il y a ? » means “what's the matter?” — qu'est-ce que asks “what”, and the rest is « il y a »."
        )
        notes.append(
            Note(
                id="questions",
                priority=15,
                title="Questions in speech",
                explanation=explanation,
                examples=[_ex(estce[0] if estce else questions[0])],
            )
        )

    commands = [line for line in lines if _imperative(line)]
    if commands:
        notes.append(
            Note(
                id="imperative",
                priority=16,
                title="Commands",
                explanation=(
                    "A command uses the verb with no subject pronoun: « viens » (you, come), « attends » (wait), « prends » (take), « regarde » (look). "
                    "« allez » on its own, before a comma, is often just “come on”, not an order to a group. "
                    "Negative commands put ne (often dropped) and the pronoun in front: « te fais pas de souci »."
                ),
                examples=[_ex(commands[0])],
            )
        )

    if any(re.search(r"\bon\b", _low(line)) for line in lines):
        sample = next(line for line in lines if re.search(r"\bon\b", _low(line)))
        notes.append(
            Note(
                id="on_we",
                priority=9,
                title="On means “we”",
                explanation=(
                    "In conversation, on plus a singular verb almost always means “we”, not the textbook “one”. "
                    "« on a raté le train » is “we missed the train”. "
                    "« nous avons » is correct too, but friends in a film will say on. "
                    "The verb stays in the third person singular: on va, on est, on a."
                ),
                examples=[_ex(sample)],
            )
        )

    depuis = [line for line in lines if re.search(r"\bdepuis\b", _low(line))]
    if depuis:
        notes.append(
            Note(
                id="depuis",
                priority=18,
                title="Depuis uses the present",
                explanation=(
                    "English says “we have known each other since high school”, with a past form. "
                    "French uses the present when the situation is still true: « on se connaît depuis le lycée ». "
                    "Depuis marks the starting point. The present says it has not stopped."
                ),
                examples=[_ex(depuis[0])],
            )
        )

    weather = [line for line in lines if re.search(r"\bil (fait|faisait) (froid|chaud|beau|mauvais)", _low(line))]
    if weather:
        notes.append(
            Note(
                id="weather",
                priority=19,
                title="Weather uses faire",
                explanation=(
                    "French does not say “it is cold” with être. It uses faire: « il fait froid », « il faisait froid ». "
                    "The same pattern gives « il fait chaud » and « il fait beau ». "
                    "In the past description of a scene, faire goes into the imparfait: il faisait froid."
                ),
                examples=[_ex(weather[0])],
            )
        )

    if any(re.search(r"\bil y a\b|\by'a\b", _low(line)) for line in lines):
        sample = next(line for line in lines if re.search(r"\bil y a\b|\by'a\b", _low(line)))
        notes.append(
            Note(
                id="il_y_a",
                priority=20,
                title="Il y a",
                explanation=(
                    "« il y a » means “there is” or “there are”. It does not change for plural: "
                    "il y a un café, il y a des gens. "
                    "Spoken French shortens it to « y'a ». "
                    "The negative is « il n'y a plus » (there is no longer) or, with the ne dropped, « y'a plus »."
                ),
                examples=[_ex(sample)],
            )
        )

    notes.sort(key=lambda note: note.priority)
    seen = already_seen or set()
    fresh = [note for note in notes if note.id not in seen]
    repeated = [note for note in notes if note.id in seen]
    # New patterns only. A later scene may add at most two already-taught notes, marked as review.
    chosen = fresh[:6]
    if len(chosen) < 2:
        for note in repeated[:2]:
            note.review = True
            note.title = "Review: " + note.title
            chosen.append(note)
    # A misspelled subtitle can still show that a pattern exists, but it is not the example.
    typo_text = {line.text for line in lines if line.typos}
    if typo_text:
        for note in chosen:
            note.examples = [ex for ex in note.examples if ex.get("fr") not in typo_text]
    return chosen


def _has_role(line: Line, role: str, compound: bool = False) -> bool:
    for tok in line.tokens:
        if tok.role == role:
            if compound and "passé composé" not in tok.form_note:
                continue
            return True
    return False


def _has_tense(line: Line, tense: str) -> bool:
    return any(tok.reading and tok.reading.tense == tense and tok.reading.mood == "ind" for tok in line.tokens)


def _has_mood(line: Line, mood: str) -> bool:
    return any(tok.reading and tok.reading.mood == mood for tok in line.tokens)


def _trigger(line: Line) -> bool:
    low = _low(line)
    return bool(re.search(r"faut qu|veux qu|veut qu|voul\w* qu|aimerais qu|avant qu|jusqu'à ce qu|pour qu", low))


def _reflexive(line: Line) -> bool:
    lows = [tok.text.lower().replace("’", "'") for tok in line.tokens]
    for i, low in enumerate(lows):
        if low in {"me", "te", "se", "m'", "t'", "s'"} and i + 1 < len(lows):
            return True
    return False


def _object_pronoun(line: Line) -> bool:
    """A real object pronoun, not the subject tu/vous whose gloss also starts with you."""
    objects = {"me", "te", "se", "m'", "t'", "s'", "lui", "leur", "en", "y"}
    for tok in line.tokens:
        low = tok.text.lower().replace("’", "'")
        if "object pronoun" in (tok.form_note or ""):
            return True
        if low in objects and tok.pos == "PRON":
            return True
        if low.startswith("-") and low in {"-le", "-la", "-les", "-lui", "-leur", "-moi", "-toi", "-en", "-y"}:
            return True
    return bool(re.search(r"\b(m'en|t'en|s'en)\b|\bon y\b", _low(line)))


def _has_verb(line: Line) -> bool:
    return any(tok.role in {"verb", "aux", "participle"} or tok.pos == "VERB" for tok in line.tokens)


def _futur_proche(line: Line) -> bool:
    lows = [tok.text.lower().replace("’", "'") for tok in line.tokens if tok.is_word]
    infinitive_endings = ("er", "ir", "re", "oir", "dre")
    for i, low in enumerate(lows[:-1]):
        if low in {"vais", "vas", "va", "allons", "allez", "vont"} and lows[i + 1].endswith(infinitive_endings):
            if lows[i + 1] not in {"er", "ir"}:
                return True
    return False


def _imperative(line: Line) -> bool:
    stripped = re.sub(r"^(allez,\s*)", "", line.text.strip(), flags=re.I)
    first = re.match(r"^[A-Za-zÀ-ÿ']+", stripped)
    if not first:
        return False
    word = first.group(0).lower().replace("’", "'")
    return word in {"viens", "venez", "attends", "attendez", "prends", "prenez", "regarde", "regardez", "entre", "entrez", "écoute", "écoutez", "dis", "dites"}


def _passe(lines: list[Line]) -> Note:
    return Note(
        id="passe_compose",
        priority=2,
        title="Passé composé",
        explanation=(
            "The passé composé is the everyday past tense for a finished event. "
            "Take the present of avoir (or être for reflexive verbs and many verbs of movement) and add the past participle. "
            "« j'ai couru » is avoir + couru. « la porte s'est fermée » is être, because the verb is reflexive."
        ),
        examples=[_ex(lines[0])],
    )


def _imparfait(lines: list[Line]) -> Note:
    return Note(
        id="imparfait",
        priority=2,
        title="Imparfait",
        explanation=(
            "The imparfait describes how things were, or what used to happen. "
            "Listen for -ais, -ait, -ions, -iez, -aient: j'étais, il faisait, tu lisais. "
            "It is the background of a scene, not the single action that moves the story."
        ),
        examples=[_ex(lines[0])],
    )
