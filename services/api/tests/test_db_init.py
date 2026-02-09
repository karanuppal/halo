from pathlib import Path

from sqlalchemy import inspect


def test_init_db_creates_tables(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "halo_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")

    from services.api.app.db.database import get_engine
    from services.api.app.db.init_db import init_db

    init_db()

    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())

    assert "households" in tables
    assert "event_log" in tables
