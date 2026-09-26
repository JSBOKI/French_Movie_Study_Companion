"""Run the study app: python -m app"""

import threading

import uvicorn

from app.config import host, port
from app.db import init_db


def _preload_translator() -> None:
    """Fetch the offline model after the process is up, so /api/health can answer first."""
    try:
        from app.services.offline_translate import ensure_model

        ensure_model()
    except Exception:
        return


def main() -> None:
    init_db()
    threading.Thread(target=_preload_translator, name="bobine-model", daemon=True).start()
    uvicorn.run("app.main:app", host=host(), port=port(), reload=False)


if __name__ == "__main__":
    main()
