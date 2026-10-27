from fastapi.testclient import TestClient
from app.main import app

O = {"Origin": "https://twenty-watts.onrender.com"}
P = {"passage": "x", "question": "why?", "chapter_no": 6, "planned": 110}

def test_teacher_no_key(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    c = TestClient(app)
    r = c.post("/api/teacher", json=P, headers=O)
    assert r.status_code == 503 and "LLM_API_KEY" in r.json()["detail"]
    assert r.headers["access-control-allow-origin"] == O["Origin"]
    assert c.post("/api/teacher", json=P, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.options("/api/teacher", headers={**O, "Access-Control-Request-Method": "POST"}).status_code == 204
    assert c.get("/api/movies").status_code == 401   # rest of the app still gated

def test_teacher_answers(monkeypatch):
    import app.teacher as t
    monkeypatch.setenv("LLM_API_KEY", "dummy")
    monkeypatch.setattr(t, "_chat", lambda msgs: "stub answer")
    r = TestClient(app).post("/api/teacher", json=P, headers={"Origin": "https://rays-bookshelf.onrender.com"})
    assert r.status_code == 200 and r.json()["answer"] == "stub answer"
