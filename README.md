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

1. **Add a film.** Search uses Wikidata and needs no key. You can also type the title yourself. Upload a `.srt`, `.vtt`, or `.ass`/`.ssa` subtitle. The film is split on real pauses in the dialogue, or into stretches of about 8–12 minutes.
2. **Read a scene.** New words show the dictionary form, noun gender with an article (`le métro`, `la pluie`), and for verbs the infinitive plus the tense, mood, and person in the line. Grammar notes only appear when that pattern is in the scene: passé composé beside imparfait, negation with a dropped *ne*, the subjunctive after *il faut que*, reflexives, contractions, pronoun order, and spoken forms such as *t'as*, *j'sais pas*, *y'a*, and verlan (*chelou*). Tap a word in the dialogue for the gloss. Later scenes do not reteach words or grammar points you have already had, and **I know this** removes a word from future lists and suspends its card.
3. **Review.** Each new word becomes a card (French with article, English, an example line). Review uses [FSRS](https://github.com/open-spaced-repetition/py-fsrs). Progress is stored in SQLite. Export a film as CSV or an Anki `.apkg` from the film page.
4. **Listen.** A scene can build two MP3s: a dialogue drill (French, a pause to repeat, English, French again) and a vocabulary drill. Léa is read with `fr-FR-DeniseNeural` and Marc with `fr-FR-HenriNeural`. Lines and words also play from the lesson and from a card. Where it helps, a line carries a short liaison or elision note.

## What works with no API key

| Feature | Needs |
| --- | --- |
| Wikidata film search, manual entry | nothing |
| Subtitle upload, scene split, lessons, glosses, grammar | nothing |
| FreeDict-based dictionary, frequency levels, verb forms shipped in `app/data` | nothing |
| Flashcards, FSRS, Anki CSV and `.apkg` | nothing |
| Sample short | nothing |
| Line and drill speech | network access to Microsoft Edge voices, no key |
| Film posters and richer search | `TMDB_API_KEY` |
| Search and download French subtitles | `OPENSUBTITLES_API_KEY` |
| Polished translations and grammar wording | `LLM_API_KEY` |
| A different speech engine | `TTS_PROVIDER=openai` or `espeak` |

Translations of lines you have not seen before try the free MyMemory service, then a word-by-word gloss. The sample lines are translated locally. The app never bundles copyrighted subtitles.

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
| `DATA_DIR` | `data/user` | SQLite database, audio, and speech cache |
| `HOST`, `PORT` | `0.0.0.0`, `8000` | Bind address |

## Deploying later

Run `python -m app` behind a reverse proxy. Keep a single worker: the database is SQLite. Persist `DATA_DIR` across restarts, and install `ffmpeg`. The server needs outbound network for Wikidata search and for Edge voices. There is no login, so do not put it on the public internet without something in front that restricts who can open it (a private VPN, HTTP auth, or a localhost tunnel).

Dictionary data is a compact FreeDict French–English extract, an OpenSubtitles frequency list, and verb forms generated with verbecc. Sources and licenses are in `app/data/SOURCES.md`.

## Tests

```bash
.venv/bin/pytest
```
