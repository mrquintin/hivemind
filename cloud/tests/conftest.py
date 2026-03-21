"""Shared fixtures for integration tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

# -- SQLite compat: map PostgreSQL JSONB → JSON for SQLite --
# We hook into the SQLite type compiler so it knows how to render JSONB as JSON.
from sqlalchemy.dialects import sqlite as sqlite_dialect
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base
from app.deps import get_db
from app.main import app

# Teach the SQLite compiler to emit "JSON" when it encounters a JSONB column
sqlite_dialect.base.SQLiteTypeCompiler.visit_JSONB = (
    lambda self, type_, **kw: "JSON"
)

# SQLite in-memory database
TEST_DATABASE_URL = "sqlite:///file::memory:?cache=shared"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@event.listens_for(test_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def _import_all_models():
    """Import every model so SQLAlchemy registers them with Base.metadata."""
    import app.models.agent  # noqa: F401
    import app.models.analysis  # noqa: F401
    import app.models.client  # noqa: F401
    import app.models.client_data  # noqa: F401
    import app.models.knowledge_base  # noqa: F401
    import app.models.knowledge_document  # noqa: F401
    import app.models.scraped_source  # noqa: F401
    import app.models.simulation_formula  # noqa: F401
    import app.models.text_chunk  # noqa: F401


_import_all_models()


@pytest.fixture()
def db_session():
    """Create all tables, yield a session, then tear down."""
    Base.metadata.create_all(bind=test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with overridden DB dependency."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _make_token(sub: str = "testuser", role: str = "operator", expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + (timedelta(hours=-1) if expired else timedelta(hours=1))
    return jwt.encode(
        {"sub": sub, "role": role, "exp": exp},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


@pytest.fixture()
def operator_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token()}"}


@pytest.fixture()
def client_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(sub='client-1', role='client')}"}


@pytest.fixture()
def expired_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_make_token(expired=True)}"}
