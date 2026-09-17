import os
import tempfile

import pytest

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


@pytest.fixture
async def db_session():
    async with async_session_maker() as session:
        yield session
