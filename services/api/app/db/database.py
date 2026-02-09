from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _default_db_url() -> str:
    # Local-only default. Production must provide DATABASE_URL explicitly.
    return "sqlite+pysqlite:///.local/halo.db"


def get_engine():
    url = os.getenv("DATABASE_URL", _default_db_url())
    # sqlite needs special arg for multithreaded FastAPI dev server.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, future=True, connect_args=connect_args)


SessionLocal = sessionmaker(bind=get_engine(), class_=Session, autocommit=False, autoflush=False)


def db_session() -> Session:
    return SessionLocal()
