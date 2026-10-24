"""Database engine and sessions."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import SCHEMA_VERSION
from .config import ConnectionConfig
from .models import Base, PropertySettings, SchemaInfo, User

_engine: Engine | None = None
_Session: sessionmaker | None = None


class DatabaseNotReady(Exception):
    """Tables are missing or the schema is from a different version."""


def make_engine(cfg_or_url: ConnectionConfig | str) -> Engine:
    if isinstance(cfg_or_url, str):
        url, args = cfg_or_url, {}
    else:
        url, args = cfg_or_url.url(), cfg_or_url.connect_args()
        if cfg_or_url.engine == "mysql" and cfg_or_url.ssl == "prefer":
            args = _mysql_prefer_ssl(cfg_or_url, args)
    if url.startswith("sqlite"):
        eng = create_engine(url, future=True)

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        return eng
    # Hosted databases (e.g. Filess.io shared plans) limit connections, so the
    # pool is kept deliberately small and checked before each use.
    # READ COMMITTED makes every statement see the latest committed rows after a
    # row lock is taken (MySQL's default REPEATABLE READ would read an old snapshot
    # and could let two desks book the same room).
    return create_engine(
        url, connect_args=args, isolation_level="READ COMMITTED", pool_size=2, max_overflow=2, pool_pre_ping=True,
        pool_recycle=240, pool_timeout=20, future=True,
    )


def _mysql_prefer_ssl(cfg: ConnectionConfig, args: dict) -> dict:
    """PyMySQL treats any SSL option as mandatory; emulate 'use SSL if the server offers it'."""
    import pymysql
    try:
        pymysql.connect(host=cfg.host, port=cfg.port, user=cfg.username, password=cfg.password,
                        database=cfg.database, **args).close()
        return args
    except pymysql.err.OperationalError as e:
        if e.args and e.args[0] == 2026:  # server has no SSL
            return {k: v for k, v in args.items() if k != "ssl"}
        return args  # other errors surface normally on first use


def init(cfg_or_url: ConnectionConfig | str) -> Engine:
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = make_engine(cfg_or_url)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not initialised")
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    """A unit of work: commits on success, rolls back on any error."""
    if _Session is None:
        raise RuntimeError("Database not initialised")
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def missing_tables(eng: Engine | None = None) -> list[str]:
    eng = eng or engine()
    existing = set(inspect(eng).get_table_names())
    return sorted(t for t in Base.metadata.tables if t not in existing)


def check_ready() -> None:
    missing = missing_tables()
    if missing:
        raise DatabaseNotReady(
            "The database is reachable but these tables are missing: " + ", ".join(missing)
            + ". Run the setup SQL scripts (see the sql folder) or use “Create tables”.")
    with session() as s:
        ver = s.scalar(select(SchemaInfo.version).order_by(SchemaInfo.id.desc()))
        if ver is None:
            raise DatabaseNotReady("schema_info is empty. Run 02_required_data.sql.")
        if ver > SCHEMA_VERSION:
            raise DatabaseNotReady(
                f"The database was set up by a newer version of ReserveMe (schema {ver}). "
                "Please update this app.")
        if s.scalar(select(PropertySettings.id)) is None:
            raise DatabaseNotReady("No property settings found. Run 02_required_data.sql.")
        if s.scalar(select(User.id)) is None:
            raise DatabaseNotReady("No users found. Run 02_required_data.sql.")


def create_all_and_seed(eng: Engine | None = None, with_sample: bool = False) -> None:
    """Create tables and the required first rows (used by tests and the setup button)."""
    from .seed import seed_required, seed_sample
    eng = eng or engine()
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, future=True)
    with S() as s:
        seed_required(s)
        if with_sample:
            seed_sample(s)
        s.commit()
