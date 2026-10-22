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

    # Importing the models registers them on Base.metadata. Without this,
    # ``create_all`` silently created NOTHING and the full-text triggers
    # failed with "no such table: main.businesses" - it only worked because
    # every caller happened to have imported the API modules first.
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sync_missing_columns)
        await conn.run_sync(_sync_missing_indexes)
        await conn.run_sync(_sync_fts)

    try:
        await backfill_business_identity()
    except Exception as exc:  # pragma: no cover - never block a boot
        logger.warning("identity backfill skipped: %s", exc)

    try:
        await backfill_people_dimensions()
    except Exception as exc:  # pragma: no cover - never block a boot
        logger.warning("people-dimension backfill skipped: %s", exc)


async def backfill_business_identity(batch_size: int = 2000) -> int:
    """One-time backfill of the derived Business identity columns.

    ``phone_e164``, ``domain`` and ``is_demo`` are populated by a
    before_insert/before_update listener, so every row *written* after the
    columns existed has them. Rows that predate the columns do not - and a
    legacy database would silently have no phone dedupe (the raw column was
    compared against a normalised value) and no way to tell demo data from
    real leads.

    The scan is chunked and only touches rows whose derived values are
    missing, so it costs nothing on a healthy database.
    """
    from sqlalchemy import select
    from app.models.business import (
        Business,
        normalize_phone_e164,
        canonical_domain_of,
    )

    fixed = 0
    # A phone that is not a number ("N/A", "call for details") normalises
    # to None, so the row would keep matching the WHERE clause after the
    # update and this loop would never end. Tracking the ids that have
    # been looked at bounds it.
    seen: set = set()
    async with async_session_maker() as db:
        while True:
            query = select(
                Business.id,
                Business.phone,
                Business.phone_e164,
                Business.website,
                Business.domain,
                Business.source,
                Business.extra_data,
                Business.is_demo,
            ).where(
                (Business.phone_e164.is_(None) & Business.phone.isnot(None))
                | (Business.domain.is_(None) & Business.website.isnot(None))
                | Business.is_demo.is_(None)
            )
            if seen:
                query = query.where(Business.id.notin_(seen))
            rows = (await db.execute(query.limit(batch_size))).all()
            if not rows:
                break
            for (bid, phone, phone_e164, website, domain, source, extra, is_demo) in rows:
                seen.add(bid)
                new_phone = phone_e164 or normalize_phone_e164(phone)
                new_domain = domain or canonical_domain_of(website)
                extra_map = extra if isinstance(extra, dict) else {}
                new_demo = is_demo if is_demo is not None else bool(
                    extra_map.get("seeded") or source == "google_maps_seed"
                )
                await db.execute(
                    Business.__table__.update()
                    .where(Business.id == bid)
                    .values(phone_e164=new_phone, domain=new_domain, is_demo=new_demo)
                )
                fixed += 1
            await db.commit()
    if fixed:
        logger.info("schema sync: backfilled %s business identity row(s)", fixed)
    return fixed


async def backfill_people_dimensions(batch_size: int = 2000) -> int:
    """Backfills the People-table dimensions on existing rows.

    ``city`` / ``state`` / ``market_tier`` on a business and ``seniority``
    / ``is_decision_maker`` on a contact are all derived on write by event
    listeners, so rows written after the columns existed already have them.
    Rows that predate the columns do not, and without a backfill a legacy
    database would answer "every owner in Pune" with an empty list while
    looking perfectly healthy.

    The scan only touches rows whose derived values are missing, so it
    costs nothing on an up-to-date database.
    """
    from sqlalchemy import null, select
    from sqlalchemy.orm import selectinload
    from app.models.business import Business
    from app.models.contact import Contact, FABRICATED_TITLE
    from app.locations.india import extract_city_state, market_tier
    from app.enricher.seniority import classify_seniority, is_decision_maker

    fixed = 0
    async with async_session_maker() as db:
        # Raw SQL, deliberately.
        #
        # Two separate traps make the ORM unusable here:
        #
        # 1. A Core UPDATE against a mapper-enabled table invokes the
        #    ``before_update`` event, whose handler marks the ORM object
        #    dirty. The commit then flushes that object and rewrites *all*
        #    of its columns - including the ones the UPDATE had just
        #    corrected. The correction was silently undone every time.
        # 2. An ORM column SELECT after the commit re-populates the
        #    identity-mapped object with the row's stored value, which
        #    marks it dirty again; the next flush writes the stale value
        #    back. Even a read-only verification query could undo the
        #    write it was verifying.
        #
        # Both traps were silent: the backfill reported success every time
        # and changed nothing.
        last_id = 0
        while True:
            rows = (await db.execute(text(
                "SELECT id, address, city, state, market_tier FROM businesses "
                "WHERE address IS NOT NULL AND id > :last ORDER BY id LIMIT :lim"
            ), {"last": last_id, "lim": batch_size})).all()
            if not rows:
                break
            for bid, address, city, state, tier in rows:
                last_id = bid
                parsed_city, parsed_state = extract_city_state(address)
                new_tier = market_tier(parsed_city)
                if (city, state, tier) == (parsed_city, parsed_state, new_tier):
                    continue
                await db.execute(text(
                    "UPDATE businesses SET city=:city, state=:state, "
                    "market_tier=:tier WHERE id=:id"
                ), {
                    "city": parsed_city,
                    "state": parsed_state,
                    "tier": new_tier,
                    "id": bid,
                })
                fixed += 1
            await db.commit()

        last_id = 0
        while True:
            contacts = (await db.execute(text(
                "SELECT c.id, c.title, c.seniority, c.is_decision_maker, "
                "c.first_name, c.person_identified, b.name "
                "FROM contacts c JOIN businesses b ON c.business_id = b.id "
                "WHERE c.id > :last AND ("
                "  c.title IS NOT NULL OR "
                "  (c.first_name IS NOT NULL AND c.first_name != '')"
                ") ORDER BY c.id LIMIT :lim"
            ), {"last": last_id, "lim": batch_size})).all()
            if not contacts:
                break
            for cid, title, seniority, is_dm, first_name, person_id, biz_name in contacts:
                last_id = cid
                title = (title or "").strip()
                if title and title.lower() == FABRICATED_TITLE.lower():
                    # The placeholder the discovery path used to invent for
                    # every business. It is not a person's title, so it must
                    # not keep a seniority band or count as a founder. The
                    # first name was invented the same way - the business
                    # name's first word - so it goes too.
                    new_first = first_name
                    if biz_name and first_name and biz_name.split():
                        if (
                            first_name.strip().lower()
                            == biz_name.split()[0].strip().lower()
                        ):
                            new_first = None
                    await db.execute(text(
                        "UPDATE contacts SET title=NULL, first_name=:first, "
                        "seniority=NULL, is_decision_maker=0, "
                        "person_identified=0 WHERE id=:id"
                    ), {"first": new_first, "id": cid})
                    fixed += 1
                    continue

                band = classify_seniority(title) if title else None
                dm = 1 if is_decision_maker(band) else 0
                # A human is identified by a title, or by a name that is not
                # just the business name's first word.
                named_person = bool(
                    first_name and biz_name and biz_name.split()
                    and first_name.strip().lower()
                    != biz_name.split()[0].strip().lower()
                )
                is_person = 1 if (person_id or named_person or title) else 0
                if (
                    seniority == band
                    and bool(is_dm) == bool(dm)
                    and bool(person_id) == bool(is_person)
                ):
                    continue
                await db.execute(text(
                    "UPDATE contacts SET seniority=:seniority, "
                    "is_decision_maker=:dm, person_identified=:person "
                    "WHERE id=:id"
                ), {
                    "seniority": band,
                    "dm": dm,
                    "person": is_person,
                    "id": cid,
                })
                fixed += 1
            await db.commit()

    if fixed:
        logger.info("schema sync: backfilled %s people dimension(s)", fixed)
    return fixed


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
                # The inspector is a snapshot taken before the ALTER, so it
                # does not know about the column we just added. Without this
                # the next boot logs a bogus "duplicate column name"
                # warning on every start.
                have.add(col.name)
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
                present.add(index.name)
            except Exception as exc:  # pragma: no cover - dialect-specific limits
                logger.warning("schema sync skipped index %s: %s", index.name, exc)


#: Full-text search over the lead fields. A ``LIKE '%term%`` across four
#: columns cannot use an index, so every search was a full table scan -
#: ~345ms at 500k rows, over the 300ms target. An FTS5 virtual table with
#: the **trigram** tokenizer is an inverted index AND has the same
#: substring semantics as LIKE, so the results are identical.
_FTS_TABLE = "businesses_fts"
_FTS_CREATE = (
    f"CREATE VIRTUAL TABLE {_FTS_TABLE} USING fts5("
    "name, address, phone, website, content='businesses', content_rowid='id', "
    "tokenize='trigram')"
)
_FTS_DDL = [
    f"CREATE TRIGGER IF NOT EXISTS businesses_fts_ai AFTER INSERT ON businesses BEGIN\n"
    f"  INSERT INTO {_FTS_TABLE}(rowid, name, address, phone, website)\n"
    "  VALUES (new.id, new.name, new.address, new.phone, new.website);\n"
    "END",
    f"CREATE TRIGGER IF NOT EXISTS businesses_fts_ad AFTER DELETE ON businesses BEGIN\n"
    f"  INSERT INTO {_FTS_TABLE}({_FTS_TABLE}, rowid, name, address, phone, website)\n"
    "  VALUES ('delete', old.id, old.name, old.address, old.phone, old.website);\n"
    "END",
    f"CREATE TRIGGER IF NOT EXISTS businesses_fts_au AFTER UPDATE ON businesses BEGIN\n"
    f"  INSERT INTO {_FTS_TABLE}({_FTS_TABLE}, rowid, name, address, phone, website)\n"
    "  VALUES ('delete', old.id, old.name, old.address, old.phone, old.website);\n"
    f"  INSERT INTO {_FTS_TABLE}(rowid, name, address, phone, website)\n"
    "  VALUES (new.id, new.name, new.address, new.phone, new.website);\n"
    "END",
]


def _sync_fts(sync_conn) -> None:
    """Creates the FTS5 search index (SQLite only) and backfills it.

    Postgres gets ``pg_trgm`` in production deployments; this path is the
    zero-dependency equivalent for the default SQLite install. If FTS5 is
    unavailable the application falls back to the ``LIKE`` scan, so failure
    here degrades performance, never correctness.
    """
    dialect_name = sync_conn.dialect.name
    if dialect_name != "sqlite":
        return

    try:
        # Recreate if the existing table uses a different tokenizer (an
        # earlier build created a default-tokenizer table, which does not
        # have substring semantics).
        existing = sync_conn.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"
        ), {"n": _FTS_TABLE}).first()
        if existing and existing[0] and "trigram" not in existing[0]:
            sync_conn.execute(text(f"DROP TABLE IF EXISTS {_FTS_TABLE}"))
            existing = None
        if not existing:
            sync_conn.execute(text(_FTS_CREATE))
    except Exception as exc:
        logger.info("full-text search index unavailable (%s) - using LIKE fallback", exc)
        return

    # Each trigger is created independently: a trigger that fails to create
    # must not take the others down with it, and a missing trigger only
    # means the index drifts (the backfill below repairs it).
    for ddl in _FTS_DDL:
        try:
            sync_conn.execute(text(ddl))
        except Exception as exc:
            logger.warning("full-text search trigger failed: %s", exc)

    # Backfill: the triggers only fire on new writes, so an existing
    # database needs a rebuild. 'rebuild' is a no-op when already in sync.
    try:
        sync_conn.execute(text(f"INSERT INTO {_FTS_TABLE}({_FTS_TABLE}) VALUES('rebuild')"))
        logger.info("schema sync: rebuilt full-text search index")
    except Exception as exc:  # pragma: no cover
        logger.warning("full-text search backfill failed: %s", exc)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
