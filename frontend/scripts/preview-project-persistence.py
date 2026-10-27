"""Local ENG-011 review harness using the real persistence router, not app.main."""

import argparse
import os
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", type=Path, required=True, help="Dedicated aew-eng011-preview* directory for disposable SQLite data")
parser.add_argument("--port", type=int, default=8011)
args = parser.parse_args()
preview_directory = args.directory.resolve()
if not preview_directory.name.startswith("aew-eng011-preview"):
    parser.error("Use a dedicated directory whose name starts with aew-eng011-preview")
preview_directory.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{preview_directory / 'preview.sqlite3'}"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi import FastAPI  # noqa: E402
import uvicorn  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.db import Base, get_engine  # noqa: E402
from app.modules.persistence.router import router  # noqa: E402

Base.metadata.create_all(get_engine(get_settings().database_url))
app = FastAPI(title="ENG-011 isolated persistence review")
app.include_router(router)
print(f"Disposable preview database: {preview_directory / 'preview.sqlite3'}")
print("Only project persistence is mounted. This does not verify full-app startup, GitHub access or sponsor integrations.")
uvicorn.run(app, host="127.0.0.1", port=args.port)
