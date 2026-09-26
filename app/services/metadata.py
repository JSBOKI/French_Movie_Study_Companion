"""Film metadata from Wikidata, with an optional TMDB upgrade."""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from app import config

UA = "Bobine/1.0 (French film study; educational; contact: local)"
FILM_WORDS = re.compile(r"\b(film|movie|motion picture|short film|documentary|animated film|cine)\b", re.I)
REJECT_WORDS = re.compile(r"\b(television series|tv series|episode|album|song|human|person|village|city|commune)\b", re.I)


async def search_films(query: str) -> list[dict]:
    query = query.strip()
    if len(query) < 2:
        return []
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=12.0, follow_redirects=True) as client:
        tmdb: list[dict] = []
        wiki: list[dict] = []
        if config.tmdb_api_key():
            try:
                tmdb = await _tmdb(client, query)
            except httpx.HTTPError:
                tmdb = []
        try:
            wiki = await _wikidata(client, query)
        except httpx.HTTPError:
            wiki = []
    return _merge(tmdb, wiki)[:8]


async def _wikidata(client: httpx.AsyncClient, query: str) -> list[dict]:
    hits = []
    seen = set()
    for language in ("en", "fr"):
        response = await client.get(
            "https://www.wikidata.org/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": query,
                "language": language,
                "uselang": "en",
                "type": "item",
                "limit": 8,
                "format": "json",
            },
        )
        response.raise_for_status()
        for item in response.json().get("search", []):
            qid = item.get("id")
            if not qid or qid in seen:
                continue
            description = item.get("description") or ""
            if REJECT_WORDS.search(description):
                continue
            if description and not FILM_WORDS.search(description):
                continue
            seen.add(qid)
            hits.append(item)
    detailed = []
    for item in hits[:6]:
        try:
            film = await _entity(client, item)
        except httpx.HTTPError:
            film = None
        if film:
            detailed.append(film)
    return detailed


async def _entity(client: httpx.AsyncClient, item: dict) -> dict | None:
    qid = item["id"]
    response = await client.get(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    response.raise_for_status()
    entity = response.json()["entities"][qid]
    claims = entity.get("claims", {})
    if not _is_film(claims) and not FILM_WORDS.search(item.get("description") or ""):
        return None
    labels = entity.get("labels", {})
    title = (labels.get("en") or labels.get("fr") or {}).get("value") or item.get("label")
    original = _monolingual(claims.get("P1476")) or (labels.get("fr") or {}).get("value") or title
    year = _year(claims.get("P577"))
    runtime = _runtime(claims.get("P2047"))
    image = _image(claims.get("P18"))
    return {
        "title": title,
        "original_title": original,
        "year": year,
        "runtime_min": runtime,
        "poster_url": image,
        "overview": item.get("description") or "",
        "source": "wikidata",
        "external_id": qid,
    }


def _is_film(claims: dict) -> bool:
    # Q11424 film, Q24862 short film, Q506240 television film, Q202866 documentary film
    allowed = {"Q11424", "Q24862", "Q506240", "Q202866", "Q29168811"}
    for claim in claims.get("P31", []):
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        if isinstance(value, dict) and value.get("id") in allowed:
            return True
    return False


def _monolingual(claims: list | None) -> str | None:
    if not claims:
        return None
    value = ((claims[0].get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
    if isinstance(value, dict):
        return value.get("text")
    return None


def _year(claims: list | None) -> int | None:
    if not claims:
        return None
    value = ((claims[0].get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
    time = value.get("time") if isinstance(value, dict) else None
    if not time:
        return None
    match = re.search(r"(\d{4})", time)
    return int(match.group(1)) if match else None


def _runtime(claims: list | None) -> int | None:
    if not claims:
        return None
    value = ((claims[0].get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
    if not isinstance(value, dict):
        return None
    try:
        amount = abs(int(float(value.get("amount"))))
    except (TypeError, ValueError):
        return None
    if amount > 400:
        amount = round(amount / 60)
    return amount or None


def _image(claims: list | None) -> str:
    if not claims:
        return ""
    value = ((claims[0].get("mainsnak") or {}).get("datavalue") or {}).get("value")
    if not isinstance(value, str):
        return ""
    name = value.replace(" ", "_")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quote(name)}?width=500"


async def _tmdb(client: httpx.AsyncClient, query: str) -> list[dict]:
    response = await client.get(
        "https://api.themoviedb.org/3/search/movie",
        params={
            "api_key": config.tmdb_api_key(),
            "query": query,
            "include_adult": "false",
            "language": "en-US",
        },
    )
    response.raise_for_status()
    results = []
    for item in (response.json().get("results") or [])[:5]:
        runtime = None
        overview = item.get("overview") or ""
        try:
            detail = await client.get(
                f"https://api.themoviedb.org/3/movie/{item['id']}",
                params={"api_key": config.tmdb_api_key()},
            )
            if detail.status_code == 200:
                runtime = detail.json().get("runtime")
                overview = detail.json().get("overview") or overview
        except httpx.HTTPError:
            runtime = None
        poster = item.get("poster_path") or ""
        year = None
        if item.get("release_date"):
            year = int(item["release_date"][:4])
        results.append(
            {
                "title": item.get("title") or item.get("original_title"),
                "original_title": item.get("original_title") or item.get("title"),
                "year": year,
                "runtime_min": runtime,
                "poster_url": f"https://image.tmdb.org/t/p/w342{poster}" if poster else "",
                "overview": overview,
                "source": "tmdb",
                "external_id": f"tmdb:{item['id']}",
            }
        )
    return results


def _merge(primary: list[dict], secondary: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for item in primary + secondary:
        key = (re.sub(r"\W+", "", (item.get("title") or "").lower()), item.get("year"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged
