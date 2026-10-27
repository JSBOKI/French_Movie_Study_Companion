"""Mounted in Bobine for the Bookshelf reader (source: bookshelf-pipeline twenty-watts/teacher-api). Live "pop-up teacher" endpoint for the Bookshelf reader (Twenty Watts / Ray's Bookshelf).

POST /api/teacher  JSON (sent by app.js teacherPayload):
  {book, book_title, book_title_orig, author, chapter, chapter_title, chapter_no, released, planned,
   reading_lang, explain_lang, passage, word, context, note, spoilers_ok, question, kind, history:[{role, content}]}
-> {"answer": "..."}   (chapter links are written as [[ch055|label]], which the app turns into jump buttons)

Works two ways:
  * standalone:  uvicorn teacher:app --port 8000          (FastAPI app)
  * mounted into an existing FastAPI service:  from teacher import router; app.include_router(router)
Env:
  TEACHER_API_KEY   (falls back to LLM_API_KEY, then XAI_API_KEY / OPENAI_API_KEY)   key for an OpenAI-compatible chat API
  TEACHER_BASE_URL  (falls back to LLM_BASE_URL, default https://api.openai.com/v1; xAI: https://api.x.ai/v1)
  TEACHER_MODEL     (falls back to LLM_MODEL, default gpt-4o-mini)
  TEACHER_ORIGINS   comma list, default https://twenty-watts.onrender.com,https://rays-bookshelf.onrender.com
  TEACHER_RATE      requests per IP per hour (default 60); TEACHER_DAILY global cap per day (default 500)
No key -> 503 {"error": "teacher not configured"} and the app falls back to its offline notes / copy-a-question button."""
import json, os, time, threading, urllib.request
from collections import defaultdict, deque
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

ORIGINS = {o.strip().rstrip('/') for o in os.environ.get('TEACHER_ORIGINS', 'https://twenty-watts.onrender.com,https://rays-bookshelf.onrender.com').split(',') if o.strip()}
RATE = int(os.environ.get('TEACHER_RATE', '60')); DAILY = int(os.environ.get('TEACHER_DAILY', '500'))
LANG = {'en': 'English', 'ja': 'Japanese (natural, N2-level, with readings in parentheses for hard kanji)', 'ko': 'Korean'}
_hits = defaultdict(deque); _day = [time.strftime('%F'), 0]; _lock = threading.Lock()

def _key(): return next((os.environ[k].strip() for k in ('TEACHER_API_KEY', 'LLM_API_KEY') if os.environ.get(k, '').strip()), '')
def _base(): return (os.environ.get('TEACHER_BASE_URL') or os.environ.get('LLM_BASE_URL') or 'https://api.openai.com/v1').rstrip('/')
def _model(): return os.environ.get('TEACHER_MODEL') or os.environ.get('LLM_MODEL') or 'gpt-4o-mini'

SYSTEM = """You are 先生 (Sensei), a warm, patient literature teacher inside a trilingual (Japanese / Korean / English) e-reader.
Your student is an adult (a physician) learning to read Japanese at about JLPT N2. He highlighted a passage he finds confusing.
Rules:
1. Ground every answer in the PASSAGE and CONTEXT supplied. If you rely on general knowledge of the book, say so; never invent quotations, chapter numbers or plot.
2. Answer in {explain}. Quote Japanese words/phrases from the passage when explaining them (with reading if hard), then explain.
3. Be guided and interactive: lead with a one- or two-sentence plain meaning, then only what the question needs (short paragraphs or bullets, under ~220 words). End with one gentle check-question or a suggestion of what to look at next, when useful.
4. Kinds: phrase = key words and nuance; grammar = break the sentence into parts and name each pattern; refers = what it points back/forward to; why = the author's purpose, theme, technique; simple = restate in very easy language; quiz = ONE multiple-choice question (3 options), give the answer only after he replies; free = his own question.
5. SPOILERS: the student has read up to chapter {upto} of {planned}. {spoil}
6. When you mention another chapter of this book, write it as [[chNNN|short label]] with a 3-digit zero-padded chapter number in the book's continuous numbering (e.g. [[ch055|Ch. 55, the testament begins]]), so the app can link it.
7. Plain text only (no Markdown headings or tables)."""

def _prompt(d):
    spoil = ('He has opted in to spoilers for this passage: you may explain later events plainly.' if d.get('spoilers_ok') else
             'Do NOT reveal events after his current chapter. If the honest answer depends on later plot, say that it is a forward reference, '
             'say roughly where it pays off (part / chapter) without saying what happens, and ask "Want the spoiler?". He can tap a button to opt in.')
    sys_ = SYSTEM.format(explain=LANG.get(d.get('explain_lang'), 'English'), upto=d.get('chapter_no', '?'), planned=d.get('planned', '?'), spoil=spoil)
    ctx = (f"BOOK: {d.get('book_title')} ({d.get('book_title_orig')}) by {d.get('author')}. Reading in: {d.get('reading_lang')}.\n"
           f"CHAPTER: {d.get('chapter_title')} (chapter {d.get('chapter_no')}; {d.get('released')} of {d.get('planned')} chapters published so far).\n"
           f"CONTEXT (surrounding paragraphs):\n{str(d.get('context') or '')[:6000]}\n\nPASSAGE (highlighted):\n{str(d.get('passage') or '')[:2000]}\n"
           + (f"WORD tapped: {d.get('word')}\n" if d.get('word') else '')
           + (f"TEACHER'S PREPARED NOTE (trusted, use it): {d.get('note')}\n" if d.get('note') else ''))
    msgs = [{'role': 'system', 'content': sys_}, {'role': 'user', 'content': ctx + '\n(The questions follow.)'}, {'role': 'assistant', 'content': 'Understood. Ready.'}]
    for h in (d.get('history') or [])[-8:]:
        if h.get('role') in ('user', 'assistant') and h.get('content'): msgs.append({'role': h['role'], 'content': str(h['content'])[:2000]})
    msgs.append({'role': 'user', 'content': f"[{d.get('kind') or 'free'}] {str(d.get('question') or '')[:1000]}"})
    return msgs

def _allowed(origin): return origin and origin.rstrip('/') in ORIGINS
def _cors(origin): return {'Access-Control-Allow-Origin': origin, 'Vary': 'Origin', 'Access-Control-Allow-Methods': 'POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '86400'}

def _limited(ip):
    now = time.time()
    with _lock:
        if _day[0] != time.strftime('%F'): _day[:] = [time.strftime('%F'), 0]
        q = _hits[ip]
        while q and now - q[0] > 3600: q.popleft()
        if len(q) >= RATE or _day[1] >= DAILY: return True
        q.append(now); _day[1] += 1; return False

def _chat(msgs):
    req = urllib.request.Request(_base() + '/chat/completions', data=json.dumps({'model': _model(), 'messages': msgs, 'temperature': 0.4, 'max_tokens': 700}).encode(),
                                 headers={'Authorization': 'Bearer ' + _key(), 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=40) as r: return json.load(r)['choices'][0]['message']['content'].strip()

router = APIRouter()

@router.options('/api/teacher')
def teacher_preflight(request: Request):
    o = request.headers.get('origin', '')
    return Response(status_code=204, headers=_cors(o)) if _allowed(o) else Response(status_code=403)

@router.post('/api/teacher')
async def teacher(request: Request):
    o = request.headers.get('origin', '')
    if not _allowed(o): return JSONResponse({'error': 'origin not allowed'}, status_code=403)
    h = _cors(o)
    if not _key(): return JSONResponse({'error': 'teacher not configured', 'detail': 'LLM_API_KEY is not set on this service'}, status_code=503, headers=h)
    ip = (request.headers.get('x-forwarded-for') or (request.client.host if request.client else '')).split(',')[0].strip()
    if _limited(ip): return JSONResponse({'error': 'rate limited'}, status_code=429, headers=h)
    try: d = await request.json()
    except Exception: return JSONResponse({'error': 'bad json'}, status_code=400, headers=h)
    if not isinstance(d, dict) or not str(d.get('passage') or '').strip() or not str(d.get('question') or '').strip(): return JSONResponse({'error': 'passage and question required'}, status_code=400, headers=h)
    try:
        import anyio; ans = await anyio.to_thread.run_sync(_chat, _prompt(d))
    except Exception as e: return JSONResponse({'error': 'upstream: ' + type(e).__name__}, status_code=502, headers=h)
    return JSONResponse({'answer': ans}, headers=h)

@router.get('/api/teacher/health')
def teacher_health(): return {'ok': True, 'configured': bool(_key()), 'model': _model() if _key() else None}

