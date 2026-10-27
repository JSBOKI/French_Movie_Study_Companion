# Lexicon sources

The files in this directory are derived data, not film subtitles.

- `fra_eng.json` is a compact extract of the [FreeDict](https://freedict.org/) French–English dictionary, release 0.4.1 (about 7,700 headwords). Original TEI: `fra-eng` in [freedict/fd-dictionaries](https://github.com/freedict/fd-dictionaries). Authors include Horst Eyermann and John Darrington. License: **GPL-2.0-or-later**. A few learner-facing glosses and genders in the app override noisy or wrong FreeDict rows (for example `lycée` is masculine).
- `fr_ranks.json` is the rank order of the 2018 French 50k list from [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords), built from OpenSubtitles. License: **CC-BY-SA-4.0**. Frequency bands in the UI (A1–C1) are a rough guide for learners, not an official CEFR word list.
- `verbs.json.gz` lists inflected forms of French verbs produced with [verbecc](https://github.com/bretttolbert/verbecc) 2.0 (LGPL-3.0). The forms themselves are standard conjugation facts. The app uses them to recover the infinitive and the tense, mood, and person of a film line.

Do not add copyrighted subtitle files here.
