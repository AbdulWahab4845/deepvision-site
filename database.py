"""
Database setup for DeepVision.ai.

Locally: uses SQLite, a real database that lives as a single file at
data/inquiries.db. No server to install or run.

In production (Render): reads DATABASE_URL from an environment variable
pointing at a free Neon Postgres database instead. This avoids needing
Render's paid "persistent disk" feature entirely, because the data lives
on Neon's servers, not on Render's filesystem.

Locally, DATABASE_URL is simply not set, so it falls back to SQLite
automatically — no code changes needed to switch between the two.
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'inquiries.db'}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()