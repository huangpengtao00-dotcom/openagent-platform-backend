from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import load_settings


class Base(DeclarativeBase):
    pass


settings = load_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "runs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("runs")}
    if "timeout_seconds" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE runs ADD COLUMN timeout_seconds INTEGER"))
