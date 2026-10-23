"""Database engine, session factory and declarative base (PROVISIONAL core).

M2 modules receive a ``Session`` through the ``get_session`` FastAPI
dependency and never build engines themselves, so swapping this file for the
real ENG-009 bootstrap does not touch module code.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models in the workspace backend."""


def _connect_args(database_url: str) -> dict:
    # SQLite needs this for multi-threaded FastAPI workers; other drivers
    # must not receive it.
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


@lru_cache(maxsize=None)
def get_engine(database_url: str) -> Engine:
    """One engine per URL per process."""
    return create_engine(database_url, connect_args=_connect_args(database_url))


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory shared by the app dependency and the tests."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the configured engine."""
    engine = get_engine(get_settings().database_url)
    with make_session_factory(engine)() as session:
        yield session
