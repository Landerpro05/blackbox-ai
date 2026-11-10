from collections.abc import Generator
from pathlib import Path
from sqlite3 import Connection

from fastapi import Request
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import BACKEND_ROOT


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("This local version supports SQLite only.")
    if url.database and url.database != ":memory:":
        path = Path(url.database)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(path.resolve()))
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 10},
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: Connection, _record: ConnectionPoolEntry) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def begin_write(session: Session) -> None:
    """Serialize check-and-write operations, with an explicit dialect boundary.

    PostgreSQL support here is preparatory; the application's engine/worker
    adapter still deliberately rejects unverified non-SQLite operation.
    """
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))
    elif dialect == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(4774451407313060417)"))
    else:
        raise ValueError("Dialecto de escritura no admitido.")


def get_session(request: Request) -> Generator[Session, None, None]:
    # The application owns the engine; tests can override this dependency.
    with request.app.state.session_factory() as session:
        yield session
