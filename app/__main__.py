"""Run the study app: python -m app"""

import uvicorn

from app.config import host, port
from app.db import init_db


def main() -> None:
    init_db()
    uvicorn.run("app.main:app", host=host(), port=port(), reload=False)


if __name__ == "__main__":
    main()
