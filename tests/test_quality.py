"""Regression tests for the lesson-quality failures reported on a long fan subtitle."""

from __future__ import annotations

import json
import re

from app.db import one
from app.services.analyze import analyze_line
from app.services.audio import drill_voices, english_for_audio
from app.services.grammar import detect_grammar
from app.services.lessons import build_scene_lesson
from app.services.lexicon import gloss, senses
from app.services.scenes import lesson_length, split_scenes
from app.services.translate import polish_translation
from app.services.subtitles import Cue, parse_subtitle
from app.config import ROOT


def _tok(text: str, surface: str):
    line = analyze_line(None, 0, 1000, text)
    low = surface.lower().replace("’", "'")
    for tok in line.tokens:
        if tok.text.lower().replace("’", "'") == low:
            return line, tok
    raise AssertionError(f"{surface!r} not in {text!r}: {[t.text for t in line.tokens]}")


def _lesson(*texts: str):
    cues = []
    t = 0
    for index, text in enumerate(texts, start=1):
        cues.append(Cue(index, t, t + 2000, None, text))
        t += 3000
    return build_scene_lesson(cues, scene_index=1, scene_count=1, taught=set(), known=set())


def test_context_tags_nouns_not_rare_verbs():
    cases = {
        "C'est un type bizarre.": ("type", "NOUN", "type"),
        "La police arrive.": ("police", "NOUN", "police"),
        "C'est une catastrophe.": ("catastrophe", "NOUN", "catastrophe"),
        "Il est en pleine forme.": ("en pleine forme", "EXPR", "en pleine forme"),
        "Le psychologue d’entreprise arrive.": ("entreprise", "NOUN", "entreprise"),
        "Il est devant la fenêtre.": ("devant", "ADP", "devant"),
    }
    for text, (surface, pos, lemma) in cases.items():
        _, tok = _tok(text, surface)
        assert tok.pos == pos, text
        assert tok.lemma == lemma, text
        assert tok.role != "verb"


def test_lemmas_gender_person_and_verb_forms():
    _, parait = _tok("Plus rien ne parait absurde.", "parait")
    assert parait.lemma == "paraître"
    assert "seem" in parait.gloss or "appear" in parait.gloss

    _, ouvrais = _tok("J’ouvrais la porte.", "ouvrais")
    assert ouvrais.lemma == "ouvrir"
    assert "imparfait" in ouvrais.form_note
    assert "1st" in ouvrais.form_note
    assert ouvrais.gloss and ouvrais.gloss.lower() != "verb"

    _, pendule_m = _tok("Il regarde un pendule.", "pendule")
    assert pendule_m.gender == "m"
    assert "pendulum" in pendule_m.gloss
    _, pendule_f = _tok("Il regarde la pendule.", "pendule")
    assert pendule_f.gender == "f"
    assert "clock" in pendule_f.gloss
    lesson, cards = _lesson("Il regarde un pendule.")
    card = next(card for card in cards if card["lemma"] == "pendule")
    assert card["front"].split()[0] in {"un", "le"}
    assert "pendulum" in card["back"]
    assert "clock" not in card["back"]
    _, coat = _tok("Un homme en manteau gris traverse.", "manteau")
    assert coat.gender == "m"

    _, travaille = _tok("Ce garçon travaille.", "travaille")
    assert "3rd" in travaille.form_note
    assert "1st" not in travaille.form_note
    _, dise = _tok("Un café, et que quelqu’un me dise la vérité.", "dise")
    assert "3rd" in dise.form_note
    assert "1st" not in dise.form_note

    _, inquiete = _tok("Ne t’inquiète pas.", "inquiète")
    assert "imperative" in inquiete.form_note
    _, laissez = _tok("Ne me laissez pas tomber.", "laissez")
    assert "imperative" in laissez.form_note

    line = analyze_line(None, 0, 1000, "Elle aurait fait ça.")
    fait = next(tok for tok in line.tokens if tok.text == "fait")
    assert "conditionnel passé" in fait.form_note
    assert "present indicative" not in fait.form_note

    _, fascinant = _tok("C’est fascinant.", "fascinant")
    assert fascinant.pos == "ADJ"
    assert "present participle" in fascinant.form_note
    _, ahurissant = _tok("C’est ahurissant.", "ahurissant")
    assert ahurissant.pos == "ADJ"
    assert "astonishing" in ahurissant.gloss or "mind-boggling" in ahurissant.gloss


def test_hyphen_clitics_and_fixed_expressions():
    _, il = _tok("Pourrait-il venir ?", "-il")
    assert il.pos == "PRON"
    verb = analyze_line(None, 0, 1000, "Pourrait-il venir ?").tokens[0]
    assert verb.lemma == "pouvoir"
    assert "imperative" not in verb.form_note

    _, lui = _tok("Dites-lui la vérité.", "-lui")
    assert lui.pos == "PRON"
    dites = analyze_line(None, 0, 1000, "Dites-lui la vérité.").tokens[0]
    assert "imperative" in dites.form_note
    _, le = _tok("Faites-le maintenant.", "-le")
    assert le.pos == "PRON"
    assert le.role != "noun"

    line = analyze_line(None, 0, 1000, "Qu’est-ce que tu veux ?")
    assert line.tokens[0].lemma == "qu'est-ce que"
    assert line.tokens[0].pos == "EXPR"

    for text, lemma in [
        ("S’il vous plaît, entrez.", "s'il vous plaît"),
        ("C’est tout de même vrai.", "tout de même"),
        ("Je vous en supplie.", "je vous en supplie"),
        ("Il lit tandis que je parle.", "tandis que"),
        ("Quelqu’un frappe.", "quelqu'un"),
        ("Il faut faire attention.", "faire attention"),
        ("Il y a un café.", "il y a"),
    ]:
        found = next(tok for tok in analyze_line(None, 0, 1000, text).tokens if tok.lemma == lemma)
        assert found.role == "expr"

    sit = analyze_line(None, 0, 1000, "Je vais m’asseoir.")
    asseoir = next(tok for tok in sit.tokens if tok.lemma == "asseoir")
    assert asseoir.pronominal
    lesson, _cards = _lesson("Je vais m’asseoir.")
    assert any(item["display"] == "s'asseoir" for item in lesson["vocabulary"])

    mex = analyze_line(None, 0, 1000, "Il part au Mexique.")
    name = next(tok for tok in mex.tokens if tok.text == "Mexique")
    assert name.pos == "PROPN"
    assert name.lemma == "Mexique"
    lesson, _cards = _lesson("Il part au Mexique demain.")
    assert all(item["lemma"].lower() != "mexique" for item in lesson["vocabulary"])


def test_subtitle_typos_are_flagged_and_not_taught():
    expectations = {
        "Le bateau est sur la mère.": "mer (the sea)",
        "Je l’ai pas lâcher.": "lâché",
        "J’ai passez la journée ici.": "passé",
        "Les marchants arrivent.": "marchands",
        "Ça m’arrivé souvent.": "m'arrive",
    }
    for text, guess in expectations.items():
        line = analyze_line(None, 0, 1000, text)
        assert line.typos, text
        assert any(guess in note for note in line.typos), (text, line.typos)
        bad = [tok for tok in line.tokens if tok.typo]
        assert bad and all(not tok.gloss for tok in bad)

    # A real infinitive after a participle is not a typo.
    assert not analyze_line(None, 0, 1000, "Je l’ai entendu parler.").typos
    assert not analyze_line(None, 0, 1000, "Elle a fait tomber le verre.").typos

    lesson, cards = _lesson("Je l’ai pas lâcher le sac.", "Le train est en retard.", "Le xyzzy tombe.")
    lemmas = {card["lemma"] for card in cards}
    assert "lâcher" not in lemmas
    assert "xyzzy" not in lemmas
    assert all(card["back"].strip().lower() not in {"verb", "noun", "adjective"} for card in cards)


def test_common_dictionary_senses():
    assert "similar" not in gloss("rejoindre").lower()
    assert "join" in gloss("rejoindre")
    assert "censure" not in gloss("reprendre").lower()
    assert "resume" in gloss("reprendre") or "take again" in gloss("reprendre")
    assert "subjugate" not in gloss("soumettre").lower()
    assert "submit" in gloss("soumettre")
    assert "advertence" not in gloss("attention").lower()
    assert "acuity" not in gloss("attention").lower()
    assert "sassenach" not in gloss("anglais").lower()
    assert "English" in gloss("anglais")
    assert "snag" in gloss("pépin")
    assert len(senses("pépin")) >= 2
    for lemma in (
        "fantastique",
        "urgences",
        "comptabilité",
        "malchance",
        "malchanceux",
        "normal",
        "dîner",
        "allô",
    ):
        text = gloss(lemma)
        assert text, lemma
        assert text.lower() not in {"verb", "noun", "adjective"}
    assert len(senses("rejoindre")) >= 2
    assert len(senses("rejoindre")) <= 3


def test_grammar_does_not_reteach_or_cite_the_wrong_line():
    arrival = analyze_line(None, 0, 1000, "Tu es bien arrivé ? Tout va bien ?")
    command = analyze_line(None, 0, 1000, "Ne me laissez pas tomber.")
    notes = {note.id: note for note in detect_grammar([arrival, command])}
    assert "pronouns" in notes
    cited = notes["pronouns"].examples[0]["fr"]
    assert "laissez" in cited.lower()
    assert "arrivé" not in cited.lower()
    assert not any("object pronoun" in (tok.form_note or "") for tok in arrival.tokens)

    bare = analyze_line(None, 0, 1000, "Pas du tout.")
    spoken = analyze_line(None, 0, 1000, "J'sais pas.")
    negation = {note.id: note for note in detect_grammar([bare, spoken])}["negation"]
    assert all("pas du tout" not in ex["fr"].lower() for ex in negation.examples)
    assert any("sais pas" in ex["fr"].lower() for ex in negation.examples)
    bare_notes = detect_grammar([bare])
    assert all(note.id != "negation" for note in bare_notes)
    assert all(note.id != "contractions" for note in bare_notes)

    rich = [
        analyze_line(None, 0, 1000, "T'as vu l'heure ? Le train est parti."),
        analyze_line(None, 0, 1000, "Il pleuvait et j'avais pas de parapluie."),
        analyze_line(None, 0, 1000, "Il faut que tu partes."),
        analyze_line(None, 0, 1000, "Ne me laissez pas tomber."),
    ]
    first = detect_grammar(rich)
    assert 1 <= len(first) <= 6
    assert all(not note.review for note in first)
    # A later scene that has already taught every pattern only gets a light review.
    again = detect_grammar(
        rich,
        {
            "passe_compose_imparfait",
            "spoken_french",
            "negation",
            "subjunctive",
            "reflexive",
            "contractions",
            "pronouns",
            "verlan",
            "futur_proche",
            "conditional",
            "partitive",
            "agreement",
            "tu_vous",
            "questions",
            "imperative",
            "on_we",
            "depuis",
            "weather",
            "il_y_a",
            "passe_compose",
            "imparfait",
        },
    )
    assert len(again) <= 2
    assert all(note.review and note.title.startswith("Review:") for note in again)


def test_scenes_stay_short_and_get_a_title():
    cues = [
        Cue(i, i * 4000, i * 4000 + 2000, None, f"Le train numéro {i} arrive au quai avec la valise.")
        for i in range(1, 121)
    ]
    scenes = split_scenes(cues)
    assert len(scenes) >= 3
    assert all(len(scene) <= 40 for scene in scenes)

    lesson, cards = _lesson("Le métro est plein.", "Le train part sans nous.")
    assert lesson["title"] != "Scene 1"
    assert "métro" in lesson["title"].lower() or "train" in lesson["title"].lower()
    verb = next(card for card in cards if card["pos"] == "VERB")
    assert "present" not in verb["back"].lower()
    assert "imparfait" not in verb["back"].lower()
    assert "indicative" not in verb["back"].lower()


def test_verb_tense_stays_on_the_example():
    _lesson_body, cards = _lesson("J’ouvrais la fenêtre.")
    card = next(card for card in cards if card["lemma"] == "ouvrir")
    assert card["front"] == "ouvrir"
    assert "imparfait" not in card["back"]
    assert "1st person" not in card["back"]
    assert "imparfait" in card["example_en"]


def test_gloss_fallback_is_not_cached_or_spoken(monkeypatch):
    from app.services import translate
    from app.services.pipeline import create_movie, process_subtitles

    translate._mymemory_blocked = False
    monkeypatch.setattr("app.services.offline_translate.ensure_model", lambda: False)
    calls = {"n": 0}

    class Response:
        status_code = 429

        def raise_for_status(self):
            raise AssertionError("429 should stop the client")

        def json(self):
            return {}

    def fake_get(*_args, **_kwargs):
        calls["n"] += 1
        return Response()

    monkeypatch.setattr(translate.httpx, "get", fake_get)
    movie = create_movie({"title": "Practice night", "year": 2024})
    text = (
        "1\n00:00:01,000 --> 00:00:03,000\nOù est-il ?\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nLe train part.\n"
    )
    process_subtitles(movie["id"], text, "practice.srt")
    assert calls["n"] == 1
    assert translate._mymemory_blocked
    assert one("SELECT source FROM translations WHERE provider = 'gloss'") is None
    assert one("SELECT source FROM translations WHERE provider = 'mymemory'") is None
    stored = one("SELECT lesson_json FROM scenes WHERE movie_id = ?", (movie["id"],))
    lesson = json.loads(stored["lesson_json"])
    for line in lesson["lines"]:
        assert line["translation_kind"] == "gloss"
        low = line["translation"].lower()
        assert "first half" not in low
        assert "polite" not in low
        assert "verb" not in low
        assert english_for_audio(line) == ""
    assert english_for_audio({"translation_kind": "english", "translation": "Where is he?"}) == "Where is he?"
    translate._mymemory_blocked = False


def test_typo_guesses_and_corrected_french():
    line = analyze_line(None, 0, 1000, "J'ai une chambre sur la mère.")
    assert any("mer (the sea)" in note for note in line.typos)
    assert line.corrected_text == "J'ai une chambre sur la mer."
    assert "mère" not in line.corrected_text

    worried = analyze_line(None, 0, 1000, "T'inquiété pas.")
    assert any(re.search(r"likely t'inquiéter\b", note) for note in worried.typos)
    assert not any(re.search(r"likely t'inquiéte\b", note) for note in worried.typos)
    assert worried.corrected_text == "t'inquiéter pas."

    coming = analyze_line(None, 0, 1000, "Ça va m'arrivé demain.")
    assert any("m'arriver" in note for note in coming.typos)
    kept = analyze_line(None, 0, 1000, "Ça m’arrivé souvent.")
    assert any("m'arrive" in note for note in kept.typos)
    assert all("m'arriver" not in note for note in kept.typos)

    promised = analyze_line(None, 0, 1000, "Je ferais attention demain.")
    assert any("ferai" in note for note in promised.typos)
    assert promised.corrected_text == "Je ferai attention demain."
    assert any(tok.lemma == "faire attention (à)" for tok in promised.tokens)
    genuine = analyze_line(None, 0, 1000, "Je ferais attention.")
    assert not genuine.typos
    assert any(tok.lemma == "faire attention (à)" for tok in genuine.tokens)


def test_imperative_without_ne_and_context_pos():
    command = analyze_line(None, 0, 1000, "Non t'inquiète pas.")
    verb = next(tok for tok in command.tokens if tok.lemma == "inquiéter")
    assert verb.reading.mood == "imp"
    assert (verb.reading.person, verb.reading.number) == ("2", "s")
    spoken = analyze_line(None, 0, 1000, "T'inquiète pas.")
    spoken_verb = next(tok for tok in spoken.tokens if tok.lemma == "inquiéter")
    assert spoken_verb.reading.mood == "imp"
    invite = analyze_line(None, 0, 1000, "Je t'invite pas.")
    invite_verb = next(tok for tok in invite.tokens if tok.lemma == "inviter")
    assert invite_verb.reading.mood != "imp"

    _, regarde = _tok("Je le regarde.", "regarde")
    assert regarde.pos == "VERB"
    assert regarde.lemma == "regarder"
    assert "look" in regarde.gloss
    _, voyages = _tok("J'ai fait deux voyages.", "voyages")
    assert voyages.pos == "NOUN"
    assert voyages.lemma == "voyage"
    _, vide = _tok("C'est un chariot vide.", "vide")
    assert vide.pos == "ADJ"
    assert vide.lemma == "vide"
    sack = analyze_line(None, 0, 1000, "Vide le sac.")
    assert sack.tokens[0].lemma == "vider"
    assert sack.tokens[0].pos == "VERB"


def test_expressions_glosses_and_scene_titles():
    care = analyze_line(None, 0, 1000, "Je m'occupe de tout.")
    assert any(tok.lemma == "s'occuper de" for tok in care.tokens)
    assert not any(tok.lemma == "occuper" for tok in care.tokens)
    walk = analyze_line(None, 0, 1000, "On se promène.")
    assert any(tok.lemma == "se promener" and "walk" in tok.gloss for tok in walk.tokens)
    cut = analyze_line(None, 0, 1000, "On a été coupés.")
    assert any(tok.lemma == "on a été coupé" and "cut off" in tok.gloss for tok in cut.tokens)

    lesson, _cards = _lesson("Qu'est-ce que tu veux ?", "Qu'est-ce qui se passe ?")
    lemmas = {item["lemma"] for item in lesson["vocabulary"]}
    assert "qu'est-ce" not in lemmas
    assert "qu'est-ce que" in lemmas
    assert "qu'est-ce qui" in lemmas
    alone, _cards = _lesson("Qu'est-ce ?")
    assert all(item["lemma"] != "qu'est-ce" for item in alone["vocabulary"])

    for lemma, snippet in (
        ("allo", "hello"),
        ("promener", "walk"),
        ("diner", "dinner"),
        ("parachutiste", "parachut"),
        ("hé", "hey"),
        ("chambre", "room"),
        ("magnifique", "magnificent"),
        ("urgences", "emergency room"),
    ):
        assert snippet in gloss(lemma).lower()
    _, urgences = _tok("Il est aux urgences.", "urgences")
    assert urgences.lemma == "urgences"
    assert "emergency room" in urgences.gloss
    hospital, hospital_cards = _lesson("Il est aux urgences.")
    assert hospital["title"] == "Les urgences"
    assert next(card["front"] for card in hospital_cards if card["lemma"] == "urgences") == "les urgences"
    _, allo = _tok("Hé, allo.", "allo")
    assert allo.gloss
    _, he = _tok("Hé, allo.", "Hé")
    assert "hey" in he.gloss

    assert _lesson("Le fille arrive.")[0]["title"] == "La fille"
    assert _lesson("Le guêpe vole.")[0]["title"] == "La guêpe"
    assert _lesson("La salut du matin.")[0]["title"].startswith("Le salut")
    paired = _lesson("L'anglais et espagnol arrivent.")[0]["title"]
    assert paired == "L'anglais et l'espagnol"
    assert "mars" not in _lesson("En mars le train part.")[0]["title"].lower()
    assert "an" not in _lesson("Dans un an le quai ferme.")[0]["title"].lower().split()
    assert "voilà" not in _lesson("Voilà le train.")[0]["title"].lower()
    pendulum = _lesson("C'est un pendule.")[0]["title"].lower()
    clock = _lesson("La pendule sonne.")[0]["title"].lower()
    assert "le pendule" in pendulum
    assert "la pendule" in clock


def test_scene_length_overview_and_clean_grammar_examples():
    assert lesson_length(0, 120_000) == "about 2 min"
    assert lesson_length(0, 45_000) == "about 1 min"
    lesson, _cards = _lesson("Le train part.", "Il pleuvait.")
    assert "about 1 min" in lesson["time_label"]
    assert "Review, Review" not in lesson["overview"]

    rich = [
        "T'as vu l'heure ? Le train est parti.",
        "Il pleuvait et j'avais pas de parapluie.",
        "Il faut que tu partes.",
        "Ne me laissez pas tomber.",
    ]
    cues = [Cue(i, i * 3000, i * 3000 + 2000, None, text) for i, text in enumerate(rich, start=1)]
    reviewed, _cards = build_scene_lesson(
        cues,
        scene_index=3,
        scene_count=4,
        taught=set(),
        known=set(),
        seen_grammar={
            "passe_compose_imparfait",
            "spoken_french",
            "negation",
            "subjunctive",
            "reflexive",
            "contractions",
            "pronouns",
            "verlan",
            "futur_proche",
            "conditional",
            "partitive",
            "agreement",
            "tu_vous",
            "questions",
            "imperative",
            "on_we",
            "depuis",
            "weather",
            "il_y_a",
            "passe_compose",
            "imparfait",
        },
    )
    assert "You'll work on Review" not in reviewed["overview"]
    assert "Review:" not in reviewed["overview"]
    assert "You'll work on " in reviewed["overview"]

    bad = analyze_line(None, 0, 1000, "Je ferais attention demain.")
    good = analyze_line(None, 0, 1000, "Je ferai attention ce soir.")
    good.translation = "I'll be careful tonight."
    for note in detect_grammar([bad, good]):
        assert all("ferais" not in ex["fr"] for ex in note.examples)
        for ex in note.examples:
            if ex["fr"] == good.text:
                assert ex["en"] == "I'll be careful tonight."


def test_idiom_post_edits_and_dash_voices():
    assert polish_translation("On devrait se défoncer.", "We should get high.") == "We should give it our all."
    assert polish_translation("Je vais me défoncer.", "I'm going to get high.") == "I'm going to give it my all."
    sent = polish_translation("Avant de vous envoyer au Mexique.", "Before you sent to Mexico.")
    assert sent == "Before sending you to Mexico."
    seeds = polish_translation(
        "Le nombre de pépins qu'elle aurait pu avoir.",
        "The number of seeds she could have had.",
    )
    assert seeds == "The number of snags she could have had."
    dropped = polish_translation(
        "Le nombre de pépins qu'elle aurait pu avoir.",
        "The number she could have had.",
    )
    assert "snag" in dropped
    fruit = polish_translation("Le pépin de la pomme.", "The seed of the apple.")
    assert "seed" in fruit
    assert "snag" not in fruit

    voices = drill_voices(
        [
            {"text": "- Où est-il ?", "speaker": None},
            {"text": "- Je ne sais pas. - Si, regarde.", "speaker": None},
        ],
        "dashes",
    )
    assert [speaker for _text, speaker in voices] == ["Léa", "Marc", "Léa"]
    continued = drill_voices(
        [
            {"text": "Bonjour. - Salut.", "speaker": None},
            {"text": "Ça va.", "speaker": None},
        ],
        "dashes",
    )
    assert [speaker for _text, speaker in continued] == ["Léa", "Marc", "Marc"]
    named = drill_voices([{"text": "Où est-il ?", "speaker": "Nina"}], "named")
    assert named == [("Où est-il ?", "Nina")]
    lesson, _cards = _lesson("Bonjour. - Salut.")
    assert lesson["voice_mode"] == "dashes"


def test_typo_lines_are_translated_from_the_correction(monkeypatch):
    from app.services.pipeline import create_movie, process_subtitles

    seen: list[str] = []

    def fake_batch(texts):
        seen.extend(texts)
        out = []
        for text in texts:
            if "sur la mer" in text and "mère" not in text:
                out.append("I have a room on the sea.")
            elif "défonc" in text:
                out.append("We should get high.")
            elif text.startswith("Avant de vous"):
                out.append("Before you sent to Mexico.")
            elif "pépin" in text:
                out.append("The number she could have had.")
            elif "pleuvait" in text:
                out.append("It was raining.")
            else:
                out.append("Okay.")
        return out

    monkeypatch.setattr("app.services.offline_translate.ensure_model", lambda: True)
    monkeypatch.setattr("app.services.offline_translate.translate_batch", fake_batch)
    movie = create_movie({"title": "Practice lines", "year": 2024})
    text = (
        "1\n00:00:01,000 --> 00:00:03,000\nJ'ai une chambre sur la mère.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nOn devrait se défoncer.\n\n"
        "3\n00:00:07,000 --> 00:00:09,000\nAvant de vous envoyer au Mexique.\n\n"
        "4\n00:00:10,000 --> 00:00:12,000\nLe nombre de pépins qu'elle aurait pu avoir.\n\n"
        "5\n00:00:13,000 --> 00:01:50,000\nIl pleuvait.\n"
    )
    process_subtitles(movie["id"], text, "practice.srt")
    assert any("sur la mer" in source and "mère" not in source for source in seen)
    assert all("sur la mère" not in source for source in seen)
    stored = one("SELECT lesson_json FROM scenes WHERE movie_id = ?", (movie["id"],))
    lesson = json.loads(stored["lesson_json"])
    by_fr = {line["text"]: line["translation"] for line in lesson["lines"]}
    assert by_fr["J'ai une chambre sur la mère."] == "I have a room on the sea."
    assert by_fr["On devrait se défoncer."] == "We should give it our all."
    assert by_fr["Avant de vous envoyer au Mexique."] == "Before sending you to Mexico."
    assert "snag" in by_fr["Le nombre de pépins qu'elle aurait pu avoir."]
    assert by_fr["Il pleuvait."] == "It was raining."
    chambre = next(item for item in lesson["vocabulary"] if item["lemma"] == "chambre")
    assert "sea" in chambre["example_en"]
    assert "mother" not in chambre["example_en"].lower()
    for note in lesson["grammar"]:
        for example in note["examples"]:
            assert "ferais" not in example["fr"]
            if example["fr"] == "Il pleuvait.":
                assert example["en"] == "It was raining."
    assert "about 2 min" in lesson["time_label"] or "about 1 min" in lesson["time_label"]


def _reading(text: str, surface: str):
    _line, tok = _tok(text, surface)
    assert tok.reading, (text, surface, tok.form_note, tok.pos, tok.lemma)
    return tok.reading


def test_regressions_gender_idioms_and_cache():
    # A real infinitive after à/de/pour/sans or a modal is not a typo.
    for text in (
        "J'avais qu'à la ranger.",
        "Il faut la réveiller.",
        "Je vais passer.",
        "C'est pour passer.",
        "Il part sans réveiller.",
        "J'avais qu'à la réveiller.",
    ):
        assert not analyze_line(None, 0, 1000, text).typos, text
    kept = analyze_line(None, 0, 1000, "Je l'ai pas lâcher.")
    assert any("lâché" in note for note in kept.typos)

    merchants = analyze_line(None, 0, 1000, "Les marchants arrivent.")
    assert any("marchands" in note for note in merchants.typos)
    assert merchants.corrected_text == "Les marchands arrivent."
    de_merchants = analyze_line(None, 0, 1000, "Il parle de marchants.")
    assert any("marchands" in note for note in de_merchants.typos)
    assert not analyze_line(None, 0, 1000, "Ce sont des plans mouvants.").typos

    dashed = analyze_line(None, 0, 1000, "- J'ai une chambre sur la mère.")
    assert dashed.corrected_text == "- J'ai une chambre sur la mer."
    assert " -" not in dashed.corrected_text.replace("- J'", "")

    for text, surface in (
        ("Vous voulez pas venir.", "voulez"),
        ("si vous êtes pas là.", "êtes"),
        ("Vous allez pas partir.", "allez"),
        ("Vous vous reposez jamais ?", "reposez"),
        ("Si vous vous sentez mal.", "sentez"),
        ("Vous pouvez pas entrer.", "pouvez"),
    ):
        reading = _reading(text, surface)
        assert reading.mood != "imp", (text, reading)
        assert (reading.person, reading.number) == ("2", "p"), (text, reading)
    future = _reading("vous en aurez besoin.", "aurez")
    assert future.mood != "imp"
    assert future.tense == "fut"
    assert (future.person, future.number) == ("2", "p")
    worry = _reading("Non t'inquiète pas.", "inquiète")
    assert worry.mood == "imp" and worry.number == "s"

    arrive = _reading("qu'il vous arrive malheur.", "arrive")
    assert arrive.person == "3"
    governed = _reading("Il faut qu'il vous arrive malheur.", "arrive")
    assert governed.person == "3" and governed.mood == "sub"
    assert _reading("pour qu'il se passe quelque chose.", "passe").person == "3"
    assert _reading("qu'ils vous disent la vérité.", "disent").person == "3"
    watch = _reading("Tout le monde vous regarde.", "regarde")
    assert watch.person == "3" and watch.lemma == "regarder"

    earth = analyze_line(None, 0, 1000, "terre de contrastes.")
    terre = next(tok for tok in earth.tokens if tok.text.lower() == "terre")
    contrast = next(tok for tok in earth.tokens if "contrast" in tok.text.lower())
    assert terre.pos == "NOUN" and terre.lemma != "terrer"
    assert contrast.pos == "NOUN" and "contraster" not in (contrast.lemma or "")
    fear = next(tok for tok in analyze_line(None, 0, 1000, "sans crainte.").tokens if tok.text.lower() == "crainte")
    assert fear.pos == "NOUN" and fear.lemma == "crainte"
    assert not gloss("suite").lower().startswith("train")
    assert "rest" in gloss("suite") or "follows" in gloss("suite")

    station = _lesson("Le nez saigne.", "Il va au commissariat.")[0]["title"].lower()
    assert "le commissariat" in station
    assert "la commissariat" not in station
    girl = next(card for card in _lesson("Le fille arrive.")[1] if card["lemma"] == "fille")
    assert girl["front"] == "la fille"
    wasp = next(card for card in _lesson("Un guêpe vole.")[1] if card["lemma"] == "guêpe")
    assert wasp["front"] == "la guêpe"
    agency = next(card for card in _lesson("L'agence ferme.")[1] if card["lemma"] == "agence")
    assert agency["gender"] == "f"
    assert "feminine" in agency["back"]
    pendulum = next(card for card in _lesson("C'est un pendule.")[1] if card["lemma"] == "pendule")
    clock = next(card for card in _lesson("La pendule sonne.")[1] if card["lemma"] == "pendule")
    assert pendulum["gender"] == "m"
    assert clock["gender"] == "f"

    titled = _lesson("Putain de merde.", "Le train part.", "La porte ferme.")[0]["title"].lower()
    assert "merde" not in titled and "putain" not in titled

    lesson, _cards = _lesson("Le train est sur la mère.", "Le train part.")
    train = next(item for item in lesson["vocabulary"] if item["lemma"] == "train")
    assert train["example_fr"] == "Le train part."

    points = _lesson("Il faut que tu partes.", "Ne me laissez pas tomber.")[0]
    assert points["grammar_points"]
    assert all(point not in points["overview"] for point in points["grammar_points"])
    assert "You'll work on " in points["overview"]

    from app.services.translate import note_future_spelling

    later = {
        "text": "Je ferais attention.",
        "corrected_text": "Je ferais attention.",
        "translation": "I'll be careful.",
        "translation_kind": "english",
        "typos": [],
    }
    note_future_spelling(later)
    assert any("ferai" in note for note in later["typos"])
    assert later["translation"] == "I'll be careful."
    assert later["corrected_text"] == "Je ferai attention."
    conditional = {
        "text": "Je ferais attention.",
        "corrected_text": "Je ferais attention.",
        "translation": "I would be careful.",
        "translation_kind": "english",
        "typos": [],
    }
    note_future_spelling(conditional)
    assert conditional["typos"] == []
    assert conditional["corrected_text"] == "Je ferais attention."

    assert polish_translation("On est paumé.", "We're broke.") == "We're lost."
    assert polish_translation("On est paumé dans la ville.", "We're broke in the city.") == "We're lost in the city."
    assert "cut off" in polish_translation("On a été coupé.", "We've been cut.").lower()
    assert polish_translation("Appelez-moi vite.", "Call me quickly.") == "Call me soon."
    assert polish_translation("Hé bien, voilà.", "Hey well, there it is.").startswith("Well")

    from app.services.offline_translate import translate_batch, translation_sane
    from app.services.translate import _store, clear_cached_translations

    assert not translation_sane("Elle va se coucher.", "she's going to bed Classes")
    assert translation_sane("Il part au Mexique.", "He is leaving for Mexico.")
    assert not translation_sane("Bonjour.", "")
    _store("Elle va se coucher.", "she's going to bed Classes", "argos")
    assert one("SELECT target FROM translations WHERE source = ?", ("Elle va se coucher.",)) is None
    _store("Bonjour.", "Hello.", "argos")
    assert one("SELECT target FROM translations WHERE source = ?", ("Bonjour.",))["target"] == "Hello."
    clear_cached_translations()
    assert one("SELECT source FROM translations") is None


def test_long_original_subtitle_shape():
    path = ROOT / "sample" / "huit_cents_repliques.srt"
    text = path.read_text(encoding="utf-8")
    assert "’" in text
    cues = parse_subtitle(text, path.name)
    assert len(cues) >= 800
    blob = " ".join(cue.text for cue in cues)
    for snippet in ("sur la mère", "lâcher", "passez", "marchants", "m’arrivé", "Où est-il"):
        assert snippet in blob
    scenes = split_scenes(cues)
    assert all(3 <= len(scene) <= 40 for scene in scenes)
    assert len(scenes) >= 15


def test_garbage_output_is_retried_and_serialized(monkeypatch):
    import threading
    import time

    from app.services.offline_translate import translate_batch

    answers = iter(["she's going to bed Classes", "She is going to bed."])
    monkeypatch.setattr("app.services.offline_translate.ensure_model", lambda: True)
    monkeypatch.setattr("app.services.offline_translate._translate_one", lambda _text: next(answers))
    assert translate_batch(["Elle va se coucher."]) == ["She is going to bed."]

    again = iter(["she's going to bed Classes", "still Classes here"])
    monkeypatch.setattr("app.services.offline_translate._translate_one", lambda _text: next(again))
    assert translate_batch(["Elle va se coucher."]) == [""]

    state = {"inside": 0, "max": 0}
    gate = threading.Lock()

    def fake(_text: str) -> str:
        with gate:
            state["inside"] += 1
            state["max"] = max(state["max"], state["inside"])
        time.sleep(0.02)
        with gate:
            state["inside"] -= 1
        return "Hello."

    monkeypatch.setattr("app.services.offline_translate._translate_one", fake)
    threads = [threading.Thread(target=lambda: translate_batch(["Un.", "Deux."])) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert state["max"] == 1


def test_rebuild_clears_cached_translations(monkeypatch):
    from app.db import session
    from app.services.pipeline import create_movie, rebuild
    from app.services.translate import _store

    movie = create_movie({"title": "Cache", "year": 2024})
    with session() as conn:
        conn.execute(
            "UPDATE movies SET subtitle_text = ?, subtitle_name = ? WHERE id = ?",
            ("1\n00:00:01,000 --> 00:00:03,000\nIl pleuvait.\n", "cache.srt", movie["id"]),
        )
    _store("Bonjour tout le monde.", "Hello everyone.", "argos")
    assert one("SELECT source FROM translations WHERE source = ?", ("Bonjour tout le monde.",))
    monkeypatch.setattr("app.services.pipeline.start_processing", lambda *_args, **_kwargs: None)
    rebuild(movie["id"])
    assert one("SELECT source FROM translations") is None


def test_scene_review_count_is_the_scene(client):
    from fsrs import Card

    from app.db import session
    from app.services.pipeline import create_movie
    from app.services.srs import stats

    movie = create_movie({"title": "Due counts", "year": 2024})
    payload = Card().to_json()
    with session() as conn:
        first = conn.execute(
            "INSERT INTO scenes (movie_id, idx, start_ms, end_ms, title, studied) VALUES (?, 1, 0, 1000, 'Un', 0)",
            (movie["id"],),
        ).lastrowid
        second = conn.execute(
            "INSERT INTO scenes (movie_id, idx, start_ms, end_ms, title, studied) VALUES (?, 2, 2000, 3000, 'Deux', 0)",
            (movie["id"],),
        ).lastrowid
        for scene_id, lemma in ((first, "train"), (first, "porte"), (second, "mer")):
            conn.execute(
                """
                INSERT INTO cards
                    (movie_id, scene_id, lemma, front, back, example_fr, example_en, audio_text, pos, gender, level, fsrs_json, suspended, created_at)
                VALUES (?, ?, ?, ?, 'word', '', '', ?, 'NOUN', 'm', 'A1', ?, 0, '2024-01-01')
                """,
                (movie["id"], scene_id, lemma, lemma, lemma, payload),
            )
    assert stats(movie["id"], first)["due"] == 2
    assert stats(movie["id"])["due"] == 3
    body = client.get(f"/api/review/next?movie_id={movie['id']}&scene_id={first}").json()
    assert body["stats"]["due"] == 2
    assert body["card"]["scene_id"] == first


def test_password_cookie_when_configured(client, monkeypatch):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/movies").status_code == 200
    monkeypatch.setenv("APP_PASSWORD", "correct horse")
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/movies").status_code == 401
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/login"
    bad = client.post("/login", data={"password": "nope"})
    assert bad.status_code == 200
    assert "does not match" in bad.text
    good = client.post("/login", data={"password": "correct horse"}, follow_redirects=False)
    assert good.status_code == 303
    assert client.get("/api/movies").status_code == 200
    assert client.get("/login", follow_redirects=False).status_code == 200
