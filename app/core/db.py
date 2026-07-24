"""Async SQLAlchemy engine/session management.

Defaults to a local SQLite file (`DATABASE_URL` unset) so the backend slice
runs without any extra setup; point `DATABASE_URL` at Postgres (e.g.
`postgresql+asyncpg://...`) for anything beyond local development. The whole
connection string comes from the environment — nothing hardcoded here.

The engine is built lazily (on first use, not on import) so tests can call
`configure()` with an isolated database before anything touches it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def configure(database_url: str | None = None) -> None:
    """(Re)build the shared engine/session factory.

    Called automatically on first use with `settings.database_url`. Tests
    call this explicitly first, with an isolated database URL, so every
    session opened afterwards (by API routes, by graph nodes, and by the
    test itself) shares that one isolated database instead of each drifting
    to its own separate connection.
    """

    global _engine, _session_factory
    _engine = create_async_engine(database_url or settings.database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


def get_engine() -> AsyncEngine:
    """Return the current engine, building it from settings if needed."""

    if _engine is None:
        configure()
    assert _engine is not None
    return _engine


def _factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        configure()
    assert _session_factory is not None
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a request-scoped session via `Depends(get_db_session)`."""

    async with _factory()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Open a session outside of FastAPI's DI — used by LangGraph persistence nodes."""

    async with _factory()() as session:
        yield session


async def create_tables(base: type["DeclarativeBase"]) -> None:
    """Create every table registered on `base` if it doesn't already exist.

    Takes the ORM `Base` as a parameter (instead of importing
    `app.models.orm_models` directly) so this module stays a generic
    DB-connection utility and doesn't need to know which models exist.
    Called once on app startup; safe to call again (`create_all` is a no-op
    for tables that already exist).
    """

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)
