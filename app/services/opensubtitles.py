"""Optional OpenSubtitles search. The app never requires it."""

from __future__ import annotations

import gzip
import io
import zipfile

import httpx

from app import config

API = "https://api.opensubtitles.com/api/v1"
UA = "Bobine v1.0"


def _headers() -> dict[str, str]:
    key = config.opensubtitles_api_key()
    if not key:
        raise RuntimeError("OpenSubtitles is off until OPENSUBTITLES_API_KEY is set.")
    return {"Api-Key": key, "User-Agent": UA, "Accept": "application/json"}


def search(query: str) -> list[dict]:
    response = httpx.get(
        f"{API}/subtitles",
        headers=_headers(),
        params={"query": query, "languages": "fr", "order_by": "download_count"},
        timeout=20.0,
    )
    response.raise_for_status()
    found = []
    for item in response.json().get("data") or []:
        attributes = item.get("attributes") or {}
        for file in attributes.get("files") or []:
            found.append(
                {
                    "file_id": file.get("file_id"),
                    "file_name": file.get("file_name") or attributes.get("release") or "subtitles",
                    "language": attributes.get("language") or "fr",
                    "release": attributes.get("release") or "",
                    "download_count": attributes.get("download_count") or 0,
                    "hearing_impaired": bool(attributes.get("hearing_impaired")),
                }
            )
    return found[:12]


def download(file_id: int) -> tuple[str, str]:
    response = httpx.post(
        f"{API}/download",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"file_id": file_id},
        timeout=30.0,
    )
    response.raise_for_status()
    link = response.json().get("link")
    if not link:
        raise RuntimeError("OpenSubtitles did not return a download link.")
    payload = httpx.get(link, timeout=40.0, follow_redirects=True)
    payload.raise_for_status()
    return _decode_payload(payload.content, file_id)


def _decode_payload(data: bytes, file_id: int) -> tuple[str, str]:
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith((".srt", ".vtt", ".ass", ".ssa"))]
            if not names:
                raise RuntimeError("The subtitle archive did not contain a text subtitle.")
            name = names[0]
            data = archive.read(name)
            filename = name.rsplit("/", 1)[-1]
    else:
        filename = f"opensubtitles-{file_id}.srt"
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return filename, data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return filename, data.decode("utf-8", errors="replace")
