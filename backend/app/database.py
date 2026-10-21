from typing import AsyncGenerator
import logging
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import settings

logger = logging.getLogger(__name__)

is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine_kwargs = {"echo": False, "future": True}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    # Postgres providers close idle connections (RDS does it after 5 minutes).
    # Without pre-ping the first request after an idle period dies with an
    # InterfaceError instead of transparently opening a fresh connection.
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 1800

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)


if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """Apply the SQLite pragmas SQLAlchemy does not set for you.

        * ``foreign_keys=ON`` - SQLite disables foreign keys per-connection by
          default, so every ``ondelete="CASCADE"`` in the models was a no-op
          and deleting a lead orphaned its contacts.
        * ``journal_mode=WAL`` - the default rollback journal makes a write
          block every reader for the duration of the transaction, which meant a
          long CSV import froze the whole application.
        * ``busy_timeout`` - without it a concurrent writer raises
          "database is locked" immediately instead of waiting.
        """
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

Base = declarative_base()


async def ensure_schema() -> None:
    """Create missing tables, columns and indexes.

    Every entry point calls this - the HTTP API, the CLI and the MCP server.
    It used to run only in the API's lifespan, so the CLI and the MCP server
    crashed with "no such column" the moment a model added a column. That
    made the agent surface a second-class citizen that could not survive a
    schema change.

    Additive only: it creates what is missing and never drops or retypes
    anything, so it is safe to run on every boot.
    """
    from sqlalchemy import inspect as sa_inspect

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_missing_columns)
        await conn.run_sync(_sync_missing_indexes)


def _sync_missing_columns(sync_conn) -> None:
    """ALTER TABLE ADD COLUMN for any model column the live database lacks.

    Deriving from the models means a new column needs no migration
    bookkeeping, which is what self-hosted users actually need.
    """
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    dialect = sync_conn.dialect

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col.type.compile(dialect)}'
            default = getattr(col.default, "arg", None)
            if default is not None and not callable(default):
                ddl += f" DEFAULT {default!r}" if isinstance(default, str) else f" DEFAULT {default}"
            try:
                sync_conn.execute(text(ddl))
                logger.info("schema sync: added %s.%s", table.name, col.name)
            except Exception as exc:  # pragma: no cover - dialect-specific limits
                logger.warning("schema sync skipped %s.%s: %s", table.name, col.name, exc)


def _sync_missing_indexes(sync_conn) -> None:
    """Creates any index the models declare that the live database lacks.

    The column sync only ever added columns. That meant adding
    ``index=True`` to a model did nothing for existing deployments - so the
    indexes that make the lead list fast (contacts.business_id,
    businesses.created_at, sends.campaign_id, ...) were missing on every
    database created before the model changed. On a 500k-row table that is
    the difference between a 42ms lookup and a full scan.

    Idempotent and safe to run on every boot.
    """
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {idx["name"] for idx in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in present:
                continue
            try:
                # Compile against the *sync* dialect. The async engine's
                # dialect cannot execute DDL, and `Index.create(bind=...)`
                # expects a Connection, not a dialect.
                from sqlalchemy.schema import CreateIndex
                ddl = str(CreateIndex(index).compile(dialect=sync_conn.dialect))
                sync_conn.execute(text(ddl))
                logger.info("schema sync: created index %s", index.name)
            except Exception as exc:  # pragma: no cover - dialect-specific limits
                logger.warning("schema sync skipped index %s: %s", index.name, exc)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
