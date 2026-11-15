"""TerraTrend Database Foundation.

SQLAlchemy 2.0 base configuration, SQLite PRAGMA listener, naming conventions,
session management context managers, and dual-dialect upsert helper.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Sequence, Type

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import Config

log = logging.getLogger("teratrend.db")

# Constraint naming conventions for portable Alembic migrations
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Base model class with explicit metadata naming conventions."""
    metadata = metadata


_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def get_engine(database_url: Optional[str] = None) -> Engine:
    """Create or return existing SQLAlchemy engine."""
    global _engine
    if _engine is not None and database_url is None:
        return _engine

    url = database_url or Config.DATABASE_URL
    is_sqlite = url.startswith("sqlite")

    connect_args = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=False,
    )

    if is_sqlite:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.close()

    if database_url is None:
        _engine = engine

    return engine


def get_session_factory(database_url: Optional[str] = None) -> sessionmaker[Session]:
    """Return configured sessionmaker."""
    global _session_factory
    if _session_factory is not None and database_url is None:
        return _session_factory

    engine = get_engine(database_url)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    if database_url is None:
        _session_factory = factory
    return factory


@contextmanager
def get_session(database_url: Optional[str] = None) -> Generator[Session, None, None]:
    """Context manager for database sessions.
    
    Commits on success, rolls back on exception, and always closes the session.
    """
    factory = get_session_factory(database_url)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Session:
    """Flask request-scoped session helper wired to teardown_appcontext."""
    from flask import g
    if "db_session" not in g:
        factory = get_session_factory()
        g.db_session = factory()
    return g.db_session


def close_db_session(exception: Optional[BaseException] = None) -> None:
    """Flask appcontext teardown callback to close request session."""
    from flask import g
    session: Optional[Session] = g.pop("db_session", None)
    if session is not None:
        if exception is not None:
            session.rollback()
        session.close()


def upsert(
    session: Session,
    model: Type[Any],
    values: Dict[str, Any] | List[Dict[str, Any]],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
) -> None:
    """Portable upsert supporting SQLite and PostgreSQL.
    
    Executes an `INSERT ... ON CONFLICT (conflict_cols) DO UPDATE SET update_cols`.
    """
    if not values:
        return

    dialect_name = session.bind.dialect.name if session.bind else "sqlite"

    if dialect_name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        stmt = sqlite_insert(model)
        val_list = [values] if isinstance(values, dict) else values
        if not val_list:
            return

        set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
        final_stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_=set_dict
        )
        session.execute(final_stmt, val_list)

    elif dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(model)
        val_list = [values] if isinstance(values, dict) else values
        if not val_list:
            return

        set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
        final_stmt = stmt.on_conflict_do_update(
            index_elements=conflict_cols,
            set_=set_dict
        )
        session.execute(final_stmt, val_list)

    else:
        # Generic fallback
        val_list = [values] if isinstance(values, dict) else values
        for val in val_list:
            filter_kwargs = {c: val[c] for c in conflict_cols if c in val}
            existing = session.query(model).filter_by(**filter_kwargs).first()
            if existing:
                for col in update_cols:
                    if col in val:
                        setattr(existing, col, val[col])
            else:
                session.add(model(**val))
