import sys
import os
import tempfile
import pytest

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ.setdefault("USE_CELERY", "false")

from app.database import Base, engine, async_session_maker  # noqa: E402
import app.models  # noqa: E402,F401  (registers every model on Base.metadata)


@pytest.fixture(scope="session", autouse=True)
async def create_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture(autouse=True)
async def reset_db():
    """Per-test isolation.

    The temp DB and engine are session-scoped (module-level ``engine`` imported
    at collection time), so rows written by one test would otherwise leak into
    the next. Wipe every table before each test so dedupe/import assertions see
    a clean slate regardless of execution order.
    """
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Drop child tables first to satisfy FK constraints; SQLite is tolerant,
        # but deleting in reverse dependency order is correct for all backends.
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f"DELETE FROM {table.name}"))
    yield


@pytest.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session
