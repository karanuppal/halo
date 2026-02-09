from __future__ import annotations

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None
_SESSIONMAKER: sessionmaker | None = None


def _default_db_url() -> str:
    # Local-only default. Production must provide DATABASE_URL explicitly.
    return "sqlite+pysqlite:///.local/halo.db"


def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine.

    We cache based on DATABASE_URL so tests can override DATABASE_URL before first use.
    """

    global _ENGINE, _ENGINE_URL, _SESSIONMAKER

    url = os.getenv("DATABASE_URL", _default_db_url())

    if _ENGINE is not None and _ENGINE_URL == url:
        return _ENGINE

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _ENGINE = create_engine(url, future=True, connect_args=connect_args)
    _ENGINE_URL = url
    _SESSIONMAKER = sessionmaker(bind=_ENGINE, class_=Session, autocommit=False, autoflush=False)
    return _ENGINE


def db_session() -> Session:
    get_engine()  # ensure _SESSIONMAKER is created
    assert _SESSIONMAKER is not None
    return _SESSIONMAKER()
