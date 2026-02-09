from __future__ import annotations

import os

from services.api.app.db.database import get_engine
from services.api.app.db.models import Base


def init_db() -> None:
    if os.getenv("HALO_DB_AUTO_CREATE", "true").strip().lower() not in {"1", "true", "yes", "y"}:
        return

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
