# Bobine

Bobine builds French study sessions from a film. You name the movie, add a French subtitle, and it turns that one long file into scene lessons: the vocabulary and grammar actually in the dialogue, flashcards, and audio drills you can shadow.

It is aimed at an English speaker around beginner to lower-intermediate level. A single local user is enough; there is no account system.

## Run it

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app
```

Then open http://127.0.0.1:8000 . `ffmpeg` must be on your PATH for the drill MP3s (single-line playback can fall back without it only when Edge speech succeeds and you do not concatenate).

Try **Try the sample short** on the home screen. That loads `sample/minuit_ligne_6.srt`, an original practice dialogue (not a commercial film) with two scenes: a missed last metro, then a late café.

`HOST` and `PORT` change the bind address (default `0.0.0.0:8000`). Movies, lessons, cards, and known words live in `DATA_DIR` (default `data/user/`).

## What you can do

1. **Add a film.** Search uses Wikidata and needs no key. You can also type the title yourself. Upload a `.srt`, `.vtt`, or `.ass`/`.ssa` subtitle. The film is split on pauses, then each lesson is kept to about 30–40 lines (often about two minutes) so a long scene does not become one huge list. The scene title comes from the nouns in that stretch, with the dictionary gender.
2. **Read a scene.** New words show the dictionary form, noun gender taken from the article in the line (`un pendule` is a pendulum, `la pendule` is a clock), and verbs as the infinitive. The tense, mood, and person stay on the example, not on the headword. Grammar notes only appear when that pattern is really in the scene: passé composé beside imparfait, negation with a dropped *ne*, the subjunctive after *il faut que*, reflexives, pronoun order, and spoken forms such as *t'as*, *j'sais pas*, and *y'a*. A later scene does not pad its notes back up with everything from scene 1; a repeat is marked **review**, and at most two of those are added. Tap a word for the gloss. **I know this** removes a word from future lists and suspends its card. A suspicious subtitle form is flagged (`possible subtitle typo`) and is not turned into a card.
3. **Review.** Each new word becomes a card (French with article, English, an example line). Review uses [FSRS](https://github.com/open-spaced-repetition/py-fsrs). Progress is stored in SQLite. Export a film as CSV or an Anki `.apkg` from the film page.
4. **Listen.** A scene can build two MP3s: a dialogue drill (French, a pause to repeat, English, French again) and a vocabulary drill. Named speakers are split between `fr-FR-DeniseNeural` and `fr-FR-HenriNeural`. A subtitle with no names uses one voice. Dash dialogue switches voice when the speaker changes, including a second dash in the same cue. If a line only has a word-by-word gloss, the drill skips the English instead of reading it aloud. Lines and words also play from the lesson and from a card. Spoken shortcuts such as *t'as* and a real liaison get a short note; a plain apostrophe does not. A likely subtitle typo is translated from the corrected French.

## What works with no API key

| Feature | Needs |
| --- | --- |
| Wikidata film search, manual entry | nothing |
| Subtitle upload, scene split, lessons, glosses, grammar | nothing |
| FreeDict-based dictionary, frequency levels, verb forms shipped in `app/data` | nothing |
| Flashcards, FSRS, Anki CSV and `.apkg` | nothing |
| Sample short | nothing |
| Line and drill speech | network access to Microsoft Edge voices, no key |
| French→English line translations | nothing; an Argos model (~80 MB) downloads on first use into `DATA_DIR` |
| Film posters and richer search | `TMDB_API_KEY` |
| Search and download French subtitles | `OPENSUBTITLES_API_KEY` |
| In-context sense picking and a polish of the English | `LLM_API_KEY` |
| A different speech engine | `TTS_PROVIDER=openai` or `espeak` |

Line translations use an offline Argos French→English model. The lesson opens while that runs, with a progress line. The sample lines are already translated, so the short demo does not download the model. If Argos cannot be installed, the app tries MyMemory once and stops after the first quota error (HTTP 429) instead of calling it for every line. A word-by-word gloss is labeled in the lesson, is not saved as a translation, and is not read aloud. The app never bundles copyrighted subtitles.

`sample/huit_cents_repliques.srt` is a longer original practice file (a night at a fictional port clinic, not a commercial film) for trying a full-length subtitle. It uses curly apostrophes, spoken shortcuts, and a few deliberate typos.

## Optional environment variables

| Variable | Default | Role |
| --- | --- | --- |
| `TMDB_API_KEY` | empty | Add TMDB results when you search for a film |
| `OPENSUBTITLES_API_KEY` | empty | Enable French subtitle search and download |
| `LLM_API_KEY` | empty | Optional rewrite of translations and grammar notes |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible chat endpoint |
| `LLM_MODEL` | `gpt-4o-mini` | Model name when a key is set |
| `TTS_PROVIDER` | `edge` | `edge`, `openai`, or `espeak` |
| `TTS_API_KEY` | falls back to `OPENAI_API_KEY` | Key for `TTS_PROVIDER=openai` |
| `TTS_BASE_URL` | `https://api.openai.com/v1` | Speech endpoint for OpenAI |
| `TTS_VOICE_FR` | `fr-FR-DeniseNeural` | Default French voice |
| `TTS_VOICE_FR_MALE` | `fr-FR-HenriNeural` | Voice for male speaker names |
| `TTS_VOICE_EN` | `en-US-JennyNeural` | English voice in the drills |
| `TTS_RATE` | `-8%` | French speaking rate |
| `DATA_DIR` | `data/user` | SQLite database, audio, speech cache, and the Argos model |
| `HOST`, `PORT` | `0.0.0.0`, `8000` | Bind address |

## Deploying later

Run `python -m app` behind a reverse proxy. Keep a single worker: the database is SQLite. Persist `DATA_DIR` across restarts, and install `ffmpeg`. The server needs outbound network for Wikidata search, for the one-time Argos model download, and for Edge voices. There is no login, so do not put it on the public internet without something in front that restricts who can open it (a private VPN, HTTP auth, or a localhost tunnel).

Dictionary data is a compact FreeDict French–English extract, an OpenSubtitles frequency list, and verb forms generated with verbecc. Sources and licenses are in `app/data/SOURCES.md`.

## Tests

```bash
.venv/bin/pytest
```
