"""SQLAlchemy engine, session factory and FastAPI dependency."""
from __future__ import annotations

import logging

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

log = logging.getLogger("screener.db")

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


# Columns added after the first release: (table, column, SQL type). Old databases get them on start-up.
NEW_COLUMNS = [
    ("jobs", "owner_id", "INTEGER REFERENCES users(id)"),
    ("users", "status", "VARCHAR(20) NOT NULL DEFAULT 'active'"),
    ("users", "status_reason", "VARCHAR(500) NOT NULL DEFAULT ''"),
    ("users", "status_changed_at", "DATETIME"),
    ("users", "last_login_at", "DATETIME"),
    ("users", "deleted_at", "DATETIME"),
    ("users", "purged_at", "DATETIME"),
]


def _add_missing_columns() -> None:
    insp = inspect(engine)
    existing = {t: {c["name"] for c in insp.get_columns(t)} for t in {t for t, _, _ in NEW_COLUMNS}}
    added = []
    with engine.begin() as conn:
        for table, col, ddl in NEW_COLUMNS:
            if col not in existing[table]:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                added.append(f"{table}.{col}")
        if "jobs.owner_id" in added:
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_jobs_owner_id ON jobs (owner_id)")
        if "users.status" in added:
            # Admins can no longer own jobs, so an old admin who owns jobs becomes a recruiter
            n = conn.exec_driver_sql(
                "UPDATE users SET role = 'recruiter' WHERE role = 'admin' AND id IN "
                "(SELECT DISTINCT owner_id FROM jobs WHERE owner_id IS NOT NULL)").rowcount
            conn.exec_driver_sql(
                "INSERT INTO audit_events (created_at, category, action, reason, outcome, detail, flagged) "
                "VALUES (CURRENT_TIMESTAMP, 'admin', 'migration', ?, 'success', ?, 0)",
                ("Upgraded to separate admin and recruiter accounts", f'{{"admins_made_recruiters": {n}}}'))
    if added:
        log.info("database upgraded, added columns: %s", ", ".join(added))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
