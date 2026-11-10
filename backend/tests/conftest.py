from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from auth_support import AuthenticatedTestClient as TestClient

from app.core.config import BACKEND_ROOT, get_settings
from app.core.database import build_engine, session_factory
from app.main import app


@pytest.fixture
def database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("BLACKBOX_DATABASE_URL", url)
    monkeypatch.setenv("BLACKBOX_ENVIRONMENT", "test")
    get_settings.cache_clear()
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    engine = build_engine(url)
    try:
        yield engine, session_factory(engine), config
    finally:
        engine.dispose()
        get_settings.cache_clear()


@pytest.fixture
def client(database):
    with TestClient(app) as test_client:
        yield test_client
