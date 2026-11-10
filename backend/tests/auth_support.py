"""Synthetic identity provisioning for legacy tests, followed by real API login.

No production dependency overrides, authentication bypass or real credentials.
"""

from functools import lru_cache

from app.core.config import get_settings
from app.core.database import build_engine, session_factory
from app.models.security import User, Workspace, WorkspaceMembership
from app.services.security import password_operation
from fastapi.testclient import TestClient as RawTestClient
from sqlalchemy import select

EMAIL = "owner@example.com"
PASSWORD = "Fase7-pruebas-012345!"


@lru_cache
def synthetic_hash():
    return password_operation(PASSWORD)


def ensure_identity(factory, workspace="local"):
    with factory.begin() as session:
        if session.get(Workspace, workspace) is None:
            session.add(Workspace(id=workspace, name="Workspace de pruebas"))
            session.flush()
        user = session.scalar(select(User).where(User.email == EMAIL))
        if user is None:
            user = User(email=EMAIL, password_hash=synthetic_hash())
            session.add(user)
            session.flush()
        if session.get(WorkspaceMembership, (user.id, workspace)) is None:
            session.add(
                WorkspaceMembership(
                    user_id=user.id, workspace_id=workspace, role="owner"
                )
            )
        return user.id


def provision_configured_database():
    engine = build_engine(get_settings().database_url)
    try:
        ensure_identity(session_factory(engine))
    finally:
        engine.dispose()


class AuthenticatedTestClient(RawTestClient):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("base_url", "http://127.0.0.1:8000")
        super().__init__(*args, **kwargs)

    def __enter__(self):
        result = super().__enter__()
        ensure_identity(self.app.state.session_factory)
        origin = get_settings().cors_origins[0]
        self.headers.update(
            {
                "Origin": origin,
                "X-Blackbox-Request": "1",
                "Content-Type": "application/json",
            }
        )
        response = self.post(
            "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        self.headers.update(
            {"X-CSRF-Token": response.json()["csrf_token"], "X-Workspace-ID": "local"}
        )
        return result


def login_browser_context(context, api_url, ui_url):
    result = context.request.post(
        api_url + "/api/v1/auth/login",
        data={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": ui_url, "X-Blackbox-Request": "1"},
    )
    assert result.status == 200
    return {
        "Origin": ui_url,
        "X-Blackbox-Request": "1",
        "X-CSRF-Token": result.json()["csrf_token"],
        "X-Workspace-ID": "local",
    }
