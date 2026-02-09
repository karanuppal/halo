from __future__ import annotations

from collections.abc import Generator

from services.api.app.db.database import db_session
from sqlalchemy.orm import Session


def get_db() -> Generator[Session, None, None]:
    db = db_session()
    try:
        yield db
    finally:
        db.close()
