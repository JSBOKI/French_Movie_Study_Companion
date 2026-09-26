(() => {
  const root = document.querySelector("#app");
  const state = {
    config: null,
    results: [],
    subs: [],
    card: null,
    revealed: false,
    toast: "",
    busy: "",
    word: null,
    poll: null,
  };

  const esc = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const clock = (ms) => {
    const total = Math.max(0, Math.floor(Number(ms) / 1000));
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    const mm = String(m).padStart(2, "0");
    const ss = String(s).padStart(2, "0");
    return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
  };

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : undefined,
      ...options,
      body: options.body && !(options.body instanceof FormData) && typeof options.body !== "string"
        ? JSON.stringify(options.body)
        : options.body,
    });
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
    if (!response.ok) {
      const detail = data && (data.detail || data.error);
      throw new Error(typeof detail === "string" ? detail : "Request failed.");
    }
    return data;
  }

  function stopPoll() {
    if (state.poll) clearInterval(state.poll);
    state.poll = null;
  }

  function parseRoute() {
    const raw = (location.hash || "#/").slice(1);
    const [path, query = ""] = raw.split("?");
    const parts = path.split("/").filter(Boolean);
    const params = new URLSearchParams(query);
    return { parts, params };
  }

  function go(hash) {
    if (location.hash === hash) render();
    else location.hash = hash;
  }

  let renderToken = 0;

  let lastPath = "";
  if ("scrollRestoration" in history) history.scrollRestoration = "manual";

  async function render() {
    const token = ++renderToken;
    const pathOnly = (location.hash || "#/").split("?")[0];
    const pathChanged = pathOnly !== lastPath;
    lastPath = pathOnly;
    stopPoll();
    state.word = null;
    const { parts, params } = parseRoute();
    const paint = (html) => {
      if (token !== renderToken) return false;
      root.innerHTML = html;
      if (pathChanged) {
        window.scrollTo(0, 0);
        requestAnimationFrame(() => window.scrollTo(0, 0));
      }
      return true;
    };
    try {
      if (!state.config) state.config = await api("/api/config");
      if (parts[0] === "add") return viewAdd(paint);
      if (parts[0] === "film" && parts[2] === "scene") return viewLesson(paint, Number(parts[1]), Number(parts[3]));
      if (parts[0] === "film" && parts[1]) return viewFilm(paint, Number(parts[1]));
      if (parts[0] === "review") return viewReview(paint, params.get("movie"), params.get("scene"));
      return viewLibrary(paint);
    } catch (error) {
      paint(shell("Films", `<div class="banner error">${esc(error.message)}</div>`, "films"));
    }
  }

  function shell(title, body, tab) {
    document.title = `${title} — Bobine`;
    return `
      <div class="shell">
        <header class="top">
          <a class="brand" href="#/">
            <span class="reel" aria-hidden="true"></span>
            <span class="brand-name">Bobine<span>French through film</span></span>
          </a>
        </header>
        <main class="page" id="main">${body}</main>
        <nav class="nav" aria-label="Primary">
          <a href="#/" class="${tab === "films" ? "active" : ""}">Films</a>
          <a href="#/review" class="${tab === "review" ? "active" : ""}">Review</a>
        </nav>
      </div>`;
  }

  async function viewLibrary(paint) {
    const movies = await api("/api/movies");
    const cards = movies.map((movie) => `
      <a class="film-card" href="#/film/${movie.id}">
        ${poster(movie)}
        <div>
          <strong>${esc(movie.title)}</strong>
          <div class="meta">${esc(metaLine(movie))}</div>
          <div class="chips">
            <span class="chip">${movie.scene_count || 0} scenes</span>
            ${movie.due ? `<span class="chip due">${movie.due} due</span>` : ""}
            <span class="chip">${esc(movie.status || "draft")}</span>
          </div>
        </div>
      </a>`).join("");
    const empty = movies.length ? "" : `
      <div class="empty">
        <div class="sprocket" aria-hidden="true"></div>
        <p class="lede">Name a film, add a French subtitle, and Bobine splits it into scene lessons: the words, the grammar in those lines, flashcards, and an audio drill.</p>
      </div>`;
    paint(shell("Films", `
      <section class="hero">
        <div>
          <h1>Study the film in front of you.</h1>
          ${empty}
          <div class="row">
            <button class="btn" data-action="sample" ${state.busy === "sample" ? "disabled" : ""}>${state.busy === "sample" ? "Building the short…" : "Try the sample short"}</button>
            <a class="btn-quiet" href="#/add">Add a film</a>
          </div>
        </div>
      </section>
      <div class="film-grid">${cards}</div>
    `, "films"));
  }

  function poster(movie) {
    const letter = esc((movie.title || "?").slice(0, 1));
    if (movie.poster_url) {
      return `<img class="poster" alt="" src="${esc(movie.poster_url)}" onerror="this.outerHTML='<div class=poster>${letter}</div>'">`;
    }
    return `<div class="poster" aria-hidden="true">${letter}</div>`;
  }

  function metaLine(movie) {
    const bits = [];
    if (movie.original_title && movie.original_title !== movie.title) bits.push(movie.original_title);
    if (movie.year) bits.push(String(movie.year));
    if (movie.runtime_min) bits.push(`${movie.runtime_min} min`);
    return bits.join(" · ") || (movie.overview || "").slice(0, 110);
  }

  async function viewAdd(paint) {
    const cfg = state.config || {};
    const results = state.results.map((film, index) => `
      <button class="result" data-action="pick" data-index="${index}">
        ${film.poster_url ? `<img alt="" src="${esc(film.poster_url)}">` : `<div class="poster">${esc((film.title || "?").slice(0, 1))}</div>`}
        <span><strong>${esc(film.title)}</strong><br><span class="meta">${esc([film.original_title, film.year, film.source].filter(Boolean).join(" · "))}</span></span>
      </button>`).join("");
    paint(shell("Add a film", `
      <h1>Add a film</h1>
      <p class="lede">Search uses Wikidata, with no key. ${cfg.tmdb ? "TMDB is on, so posters and years can come from there too." : "Set TMDB_API_KEY if you want TMDB posters as well."}</p>
      <section class="panel">
        <form id="search-form">
          <label for="q">Film title</label>
          <input id="q" name="q" type="search" placeholder="Amélie, Les quatre cents coups…" required>
          <div class="row" style="margin-top:12px">
            <button class="btn" type="submit">Search</button>
          </div>
        </form>
        <div class="results">${results}</div>
      </section>
      <section class="panel">
        <h2>Or type it yourself</h2>
        <form id="manual-form">
          <label for="title">Title</label>
          <input id="title" name="title" type="text" required>
          <label for="original_title">Original title</label>
          <input id="original_title" name="original_title" type="text">
          <label for="year">Year</label>
          <input id="year" name="year" type="number" inputmode="numeric" min="1890" max="2100">
          <label for="runtime_min">Runtime (minutes)</label>
          <input id="runtime_min" name="runtime_min" type="number" inputmode="numeric" min="1" max="400">
          <label for="overview">Note</label>
          <textarea id="overview" name="overview"></textarea>
          <div class="row" style="margin-top:12px"><button class="btn pine" type="submit">Save film</button></div>
        </form>
      </section>
    `, "films"));
  }

  async function viewFilm(paint, id) {
    const movie = await api(`/api/movies/${id}`);
    if (movie.status === "processing" || movie.status === "translating") {
      state.poll = setInterval(async () => {
        const fresh = await api(`/api/movies/${id}`);
        if (fresh.status !== movie.status || fresh.progress !== movie.progress) render();
      }, 900);
    }
    const scenes = (movie.scenes || []).map((scene) => `
      <a class="scene-link" href="#/film/${id}/scene/${scene.idx}">
        <span><strong>${esc(scene.title || "Scene " + scene.idx)}</strong><br><span class="meta">${clock(scene.start_ms)}–${clock(scene.end_ms)}</span></span>
        <span class="chip">${scene.studied ? "studied" : "open"}</span>
      </a>`).join("");
    const banner = movie.status === "processing" || movie.status === "translating"
      ? `<div class="banner">${esc(movie.progress || "Building lessons…")}</div>`
      : movie.status === "error"
        ? `<div class="banner error">${esc(movie.error || "The subtitle could not be read.")}</div>`
        : "";
    const subs = state.config.opensubtitles ? `
      <section class="panel">
        <h2>OpenSubtitles</h2>
        <p class="meta">French subtitles for “${esc(movie.title)}”. A download starts the lesson build.</p>
        <form id="os-form"><div class="row">
          <input id="os-q" type="search" value="${esc(movie.title)}" aria-label="Subtitle search">
          <button class="btn-quiet" type="submit">Search</button>
        </div></form>
        <div class="results">${state.subs.map((file) => `
          <button class="result" data-action="os-import" data-file="${esc(file.file_id)}" style="grid-template-columns:1fr">
            <span><strong>${esc(file.file_name)}</strong><br><span class="meta">${esc(file.release || "")} · ${file.download_count || 0} downloads</span></span>
          </button>`).join("")}</div>
      </section>` : "";
    if (paint(shell(movie.title, `
      ${banner}
      <div class="film-card" style="margin-bottom:16px; box-shadow:none; background:transparent; padding:0">
        ${poster(movie)}
        <div>
          <h1>${esc(movie.title)}</h1>
          <p class="meta">${esc(metaLine(movie))}</p>
          <p>${esc(movie.overview || "")}</p>
        </div>
      </div>
      <div class="row" style="margin-bottom:16px">
        <label class="file">Upload subtitles<input id="subtitle-file" type="file" accept=".srt,.vtt,.ass,.ssa,text/plain"></label>
        <a class="btn pine" href="#/review?movie=${id}">Review ${movie.due ? `(${movie.due})` : ""}</a>
        <a class="btn-ghost" href="/api/movies/${id}/export.csv">CSV</a>
        <a class="btn-ghost" href="/api/movies/${id}/export.apkg">Anki</a>
        <button class="btn-ghost" data-action="rebuild" data-id="${id}">Rebuild</button>
        <button class="btn-ghost" data-action="delete" data-id="${id}">Delete</button>
      </div>
      <p class="meta">Subtitles stay on this machine. .srt, .vtt, and .ass/.ssa. A long film becomes a series of scenes, about 8–12 minutes, or a shorter cut when the dialogue pauses.</p>
      <div class="scene-list">${scenes || `<p class="lede">No scenes yet. Upload a French subtitle to build the lessons.</p>`}</div>
      ${subs}
    `, "films"))) root.dataset.movieId = String(id);
  }

  async function viewLesson(paint, movieId, idx) {
    const lesson = await api(`/api/movies/${movieId}/scenes/${idx}`);
    const vocab = (lesson.vocabulary || []).map((item) => `
      <article class="word-card">
        <div class="row" style="justify-content:space-between">
          <div class="fr" lang="fr">${esc(item.display)}</div>
          ${item.level ? `<span class="chip ${esc(item.level.toLowerCase())}">${esc(item.level)}</span>` : ""}
        </div>
        <div class="en">${esc(item.gloss)}</div>
        <div class="note">${esc([item.pos_label, item.gender_label, item.pos === "VERB" ? "" : item.form_note].filter(Boolean).join(" · "))}</div>
        ${item.example_fr ? `<p class="example" lang="fr">${esc(item.example_fr)}<span>${esc(item.pos === "VERB" && item.form_note ? item.form_note + " — " : "")}${esc(item.example_en || "")}</span></p>` : ""}
        <div class="row" style="margin-top:8px">
          <button class="btn-tiny" data-action="speak" data-text="${esc(item.audio_text || item.display)}" data-lang="fr">Hear it</button>
          <button class="btn-tiny" data-action="known" data-lemma="${esc(item.lemma)}">I know this</button>
        </div>
      </article>`).join("");
    const grammar = (lesson.grammar || []).map((note) => `
      <article class="panel grammar">
        <h3>${esc(note.title)} ${note.review ? `<span class="chip">review</span>` : ""}</h3>
        <p>${esc(note.explanation)}</p>
        ${(note.examples || []).slice(0, 2).map((ex) => `
          <p class="ex"><em lang="fr">${esc(ex.fr)}</em><br><span class="meta">${esc(ex.en || "")}</span></p>`).join("")}
      </article>`).join("");
    const lines = (lesson.lines || []).map((line, lineIndex) => `
      <article class="line">
        <header>
          <span class="speaker ${/marc/i.test(line.speaker || "") ? "marc" : ""}">${esc(line.speaker || "—")}</span>
          <span>${clock(line.start_ms)}</span>
        </header>
        <p class="dialogue" lang="fr">${tokensHtml(line.tokens, lineIndex)}</p>
        ${translationHtml(line)}
        ${(line.typos || []).map((note) => `<p class="tip">${esc(note)}</p>`).join("")}
        ${line.tip ? `<p class="tip">${esc(line.tip)}</p>` : ""}
        <button class="btn-tiny" data-action="speak" data-text="${esc(line.text)}" data-lang="fr" data-speaker="${esc(line.speaker || "")}">Play line</button>
      </article>`).join("");
    const pending = (lesson.lines || []).some((line) => line.translation_kind === "pending") || lesson.movie_status === "translating";
    if (pending) {
      state.poll = setInterval(() => render(), 1200);
    }
    const audioReady = new Set(lesson.audio || []);
    const prev = idx > 1 ? `<a class="btn-ghost" href="#/film/${movieId}/scene/${idx - 1}">Previous</a>` : "";
    const next = idx < lesson.scene_count ? `<a class="btn-ghost" href="#/film/${movieId}/scene/${idx + 1}">Next scene</a>` : "";
    state.lesson = lesson;
    if (!paint(shell(lesson.title, `
      <p class="meta"><a href="#/film/${movieId}">${esc(lesson.movie_title)}</a> · ${esc(lesson.time_label || "")}</p>
      <h1>${esc(lesson.title)} <span class="meta">of ${lesson.scene_count}</span></h1>
      ${lesson.movie_status === "translating" ? `<div class="banner">${esc(lesson.movie_progress || "Translating the dialogue…")}</div>` : ""}
      <p class="lede">${esc(lesson.overview || "")}</p>
      <div class="row" style="margin-bottom:14px">
        ${prev}${next}
        <a class="btn pine" href="#/review?movie=${movieId}&scene=${lesson.id}">Cards from this scene</a>
        <button class="btn-ghost" data-action="studied" data-id="${lesson.id}" ${lesson.studied ? "disabled" : ""}>${lesson.studied ? "Marked studied" : "Mark studied"}</button>
        <a class="btn-ghost" href="#audio">Audio</a>
      </div>
      <div class="layout lesson">
        <div>
          <h2>New words</h2>
          <p class="meta">${lesson.new_count} to learn here. Words already taught, or marked known, stay in the dialogue and drop off this list.</p>
          <div class="vocab-grid">${vocab || `<p>Nothing new in this scene. The dialogue is using words you have already met.</p>`}</div>
          <h2 style="margin-top:18px">Grammar in this scene</h2>
          ${grammar || `<p class="meta">No new pattern stood out beyond what earlier scenes covered.</p>`}
        </div>
        <div>
          <h2>Dialogue</h2>
          <p class="meta">Tap a word for the dictionary form, gender, and the tense it is in.</p>
          <div class="script">${lines}</div>
          <section class="panel audio-box" id="audio">
            <h2>Listen and shadow</h2>
            <p>${esc(voiceBlurb(lesson.voice_mode))} The English is spoken only when it is a real sentence, not a word-by-word gloss. No API key: these are Edge neural voices, and the machine needs a network.</p>
            <div class="row">
              <button class="btn" data-action="audio" data-scene="${lesson.id}" data-kind="dialogue" ${state.busy === "dialogue" ? "disabled" : ""}>${audioReady.has("dialogue") ? "Rebuild dialogue MP3" : "Build dialogue MP3"}</button>
              <button class="btn-quiet" data-action="audio" data-scene="${lesson.id}" data-kind="vocab" ${state.busy === "vocab" ? "disabled" : ""}>${audioReady.has("vocab") ? "Rebuild vocab MP3" : "Build vocab MP3"}</button>
            </div>
            ${state.busy === "dialogue" || state.busy === "vocab" ? `<p>Building the ${esc(state.busy)} track… this can take a minute.</p>` : ""}
            ${trackPlayer(lesson.id, "dialogue", audioReady)}
            ${trackPlayer(lesson.id, "vocab", audioReady)}
          </section>
        </div>
      </div>
    `, "films"))) return;
    root.dataset.lesson = JSON.stringify({ movieId, idx });
  }

  function translationHtml(line) {
    if (line.translation_kind === "gloss") {
      return `<p class="translation"><span class="chip">word-by-word</span> ${esc(line.translation || "")}</p>`;
    }
    if (line.translation_kind === "pending" || !line.translation) {
      return `<p class="translation">Translation coming…</p>`;
    }
    return `<p class="translation">${esc(line.translation)}</p>`;
  }

  function voiceBlurb(mode) {
    if (mode === "named") {
      return "Named speakers are split between Denise and Henri. A name that is not clearly male uses Denise.";
    }
    if (mode === "dashes") {
      return "This subtitle marks speakers with dashes, so the voices alternate: Denise, then Henri.";
    }
    return "This subtitle has no speaker names, so the drill uses one French voice, Denise.";
  }

  function trackPlayer(sceneId, kind, ready) {
    if (!ready.has(kind)) return "";
    const src = `/api/scenes/${sceneId}/audio/${kind}.mp3`;
    const label = kind === "dialogue" ? "Dialogue drill" : "Vocabulary drill";
    return `<div style="margin-top:12px"><strong>${label}</strong><audio controls src="${src}"></audio><div><a href="${src}" download>Download ${label} MP3</a></div></div>`;
  }

  function tokensHtml(tokens, lineIndex) {
    if (!tokens || !tokens.length) return "";
    return tokens.map((tok, index) => {
      const space = index && gap(tokens[index - 1], tok) ? " " : "";
      if (!tok.is_word) return space + esc(tok.text);
      return `${space}<button type="button" class="tok" data-action="word" data-line="${lineIndex}" data-token="${index}">${esc(tok.text)}</button>`;
    }).join("");
  }

  function gap(prev, tok) {
    const text = tok.text || "";
    if (".,;:?!…%)]»".includes(text)) return false;
    if ("([«".includes(prev.text || "")) return false;
    if (text.startsWith("-") || (prev.text || "").endsWith("-")) return false;
    if ((prev.text || "").endsWith("'") || (prev.text || "").endsWith("’")) return false;
    return true;
  }

  async function viewReview(paint, movieId, sceneId) {
    const query = new URLSearchParams();
    if (movieId) query.set("movie_id", movieId);
    if (sceneId) query.set("scene_id", sceneId);
    const payload = await api(`/api/review/next?${query.toString()}`);
    state.card = payload.card;
    const stats = payload.stats || {};
    if (!state.card) {
      paint(shell("Review", `
        <h1>Nothing due.</h1>
        <p class="lede">${stats.total ? "You are caught up. New cards appear as soon as a scene is built." : "Add a film and a subtitle first. Cards are created with each scene."}</p>
        ${stats.next_due ? `<p class="meta">Next card ${esc(stats.next_due)}</p>` : ""}
        <a class="btn" href="#/">Back to films</a>
      `, "review"));
      return;
    }
    const card = state.card;
    if (!paint(shell("Review", `
      <p class="meta">${esc(card.movie_title || "")} · scene ${esc(card.scene_index)} · ${stats.due || card.remaining} due</p>
      <div class="card-stage">
        <button class="flash" data-action="reveal" type="button" aria-expanded="${state.revealed}">
          <div class="front" lang="fr">${esc(card.front)}</div>
          ${card.level ? `<div><span class="chip ${esc(String(card.level).toLowerCase())}">${esc(card.level)}</span></div>` : ""}
          ${state.revealed ? `
            <div class="back">${esc(card.back)}</div>
            <p class="ex" lang="fr">${esc(card.example_fr || "")}</p>
            <p class="ex">${esc(card.example_en || "")}</p>` : `<p class="meta">Tap the card to see the English.</p>`}
        </button>
        <div class="row" style="justify-content:center">
          <button class="btn-tiny" data-action="speak" data-text="${esc(card.audio_text || card.front)}" data-lang="fr">Hear the word</button>
          ${card.example_fr ? `<button class="btn-tiny" data-action="speak" data-text="${esc(card.example_fr)}" data-lang="fr">Hear the line</button>` : ""}
        </div>
        <div class="toast">${esc(state.toast)}</div>
        ${state.revealed ? `
          <div class="grades">
            <button class="again" data-action="rate" data-rating="1">Again</button>
            <button class="hard" data-action="rate" data-rating="2">Hard</button>
            <button class="good" data-action="rate" data-rating="3">Good</button>
            <button class="easy" data-action="rate" data-rating="4">Easy</button>
          </div>
          <p class="meta" style="text-align:center">Keys 1–4 after you reveal. Scheduling is FSRS.</p>` : ""}
      </div>
    `, "review"))) return;
    root.dataset.review = JSON.stringify({ movieId: movieId || "", sceneId: sceneId || "" });
  }

  function showWord(button) {
    const lineIndex = Number(button.dataset.line);
    const tokenIndex = Number(button.dataset.token);
    const tok = state.lesson?.lines?.[lineIndex]?.tokens?.[tokenIndex];
    if (!tok) return;
    const cached = root.querySelectorAll(".line")[lineIndex];
    cached?.querySelectorAll(".tok").forEach((el) => el.classList.remove("on"));
    button.classList.add("on");
    let sheet = document.querySelector(".sheet");
    if (!sheet) {
      sheet = document.createElement("div");
      sheet.className = "sheet";
      root.appendChild(sheet);
    }
    const bits = [tok.pos_label, tok.gender ? (tok.gender === "f" ? "feminine" : "masculine") : "", tok.form_note].filter(Boolean).join(" · ");
    sheet.innerHTML = `
      <div class="row" style="justify-content:space-between">
        <div class="lemma" lang="fr">${esc(tok.lemma || tok.text)}</div>
        <button class="btn-tiny" data-action="close-word" type="button">Close</button>
      </div>
      <div class="gloss">${esc(tok.gloss || "No gloss yet")}</div>
      <p class="meta" style="color:#d9cbb8">${esc(bits)}</p>
      <button class="btn-tiny" data-action="speak" data-text="${esc(tok.lemma || tok.text)}" data-lang="fr">Hear it</button>
    `;
  }

  async function speak(text, lang, speaker) {
    const params = new URLSearchParams({ text, lang: lang || "fr" });
    if (speaker) params.set("speaker", speaker);
    const response = await fetch(`/api/tts?${params.toString()}`);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || "Speech failed.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    await audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  }

  root.addEventListener("click", async (event) => {
    const el = event.target.closest("[data-action]");
    if (!el) return;
    const action = el.dataset.action;
    try {
      if (action === "sample") {
        el.disabled = true;
        el.textContent = "Building the short…";
        const movie = await api("/api/sample", { method: "POST" });
        go(`#/film/${movie.id}/scene/1`);
      } else if (action === "pick") {
        const film = state.results[Number(el.dataset.index)];
        const movie = await api("/api/movies", { method: "POST", body: film });
        go(`#/film/${movie.id}`);
      } else if (action === "delete") {
        if (!confirm("Delete this film, its lessons, and its cards?")) return;
        await api(`/api/movies/${el.dataset.id}`, { method: "DELETE" });
        go("#/");
      } else if (action === "rebuild") {
        await api(`/api/movies/${el.dataset.id}/rebuild`, { method: "POST" });
        render();
      } else if (action === "studied") {
        await api(`/api/scenes/${el.dataset.id}/studied`, { method: "POST" });
        render();
      } else if (action === "known") {
        await api("/api/known", { method: "POST", body: { lemma: el.dataset.lemma, known: true } });
        render();
      } else if (action === "speak") {
        await speak(el.dataset.text, el.dataset.lang, el.dataset.speaker);
      } else if (action === "word") {
        showWord(el);
      } else if (action === "close-word") {
        document.querySelector(".sheet")?.remove();
      } else if (action === "reveal") {
        state.revealed = true;
        state.toast = "";
        render();
      } else if (action === "rate") {
        const card = state.card;
        const result = await api(`/api/review/${card.id}`, { method: "POST", body: { rating: Number(el.dataset.rating) } });
        state.revealed = false;
        state.toast = result.interval || "";
        render();
      } else if (action === "audio") {
        state.busy = el.dataset.kind;
        await render();
        await api(`/api/scenes/${el.dataset.scene}/audio?kind=${el.dataset.kind}`, { method: "POST" });
        state.busy = "";
        await render();
      } else if (action === "os-import") {
        const movieId = root.dataset.movieId;
        await api(`/api/movies/${movieId}/opensubtitles`, { method: "POST", body: { file_id: Number(el.dataset.file) } });
        render();
      }
    } catch (error) {
      state.busy = "";
      alert(error.message);
    }
  });

  root.addEventListener("submit", async (event) => {
    const form = event.target;
    if (form.id === "search-form") {
      event.preventDefault();
      const q = new FormData(form).get("q");
      const data = await api(`/api/movies/search?q=${encodeURIComponent(q)}`);
      state.results = data.results || [];
      if (data.error) alert(data.error);
      if (!state.results.length && !data.error) alert("No film matched that title. You can type it in below.");
      render();
    } else if (form.id === "manual-form") {
      event.preventDefault();
      const raw = Object.fromEntries(new FormData(form).entries());
      const body = {
        title: raw.title,
        original_title: raw.original_title || raw.title,
        year: raw.year ? Number(raw.year) : null,
        runtime_min: raw.runtime_min ? Number(raw.runtime_min) : null,
        overview: raw.overview || "",
        source: "manual",
      };
      const movie = await api("/api/movies", { method: "POST", body });
      go(`#/film/${movie.id}`);
    } else if (form.id === "os-form") {
      event.preventDefault();
      const q = document.querySelector("#os-q").value;
      const data = await api(`/api/opensubtitles/search?q=${encodeURIComponent(q)}`);
      state.subs = data.results || [];
      render();
    }
  });

  root.addEventListener("change", async (event) => {
    if (event.target.id !== "subtitle-file") return;
    const file = event.target.files && event.target.files[0];
    const movieId = root.dataset.movieId;
    if (!file || !movieId) return;
    const body = new FormData();
    body.append("file", file);
    try {
      await api(`/api/movies/${movieId}/subtitles`, { method: "POST", body });
      render();
    } catch (error) {
      alert(error.message);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!location.hash.startsWith("#/review")) return;
    if (event.target.matches("input, textarea")) return;
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      if (!state.revealed) {
        state.revealed = true;
        render();
      }
    }
    if (state.revealed && "1234".includes(event.key)) {
      const button = root.querySelector(`[data-rating="${event.key}"]`);
      button?.click();
    }
  });

  window.addEventListener("hashchange", () => {
    state.revealed = false;
    state.toast = "";
    state.results = location.hash.startsWith("#/add") ? state.results : [];
    document.querySelector(".sheet")?.remove();
    render();
  });

  if (!location.hash) location.hash = "#/";
  render();
})();
