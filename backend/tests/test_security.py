import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from app.admin import adopt_legacy
from app.core.config import Settings, get_settings
from app.main import app
from app.models import (
    AIAnalysis,
    Project,
    Run,
    RunStatus,
    SuiteCase,
    TestEnvironment,
    TestPage,
    TestSuite,
)
from app.models.security import (
    AuditEvent,
    AuthSession,
    RegistrationInvite,
    User,
    WorkspaceMembership,
)
from app.services.security import bootstrap_invitation, digest, now
from app.testing.policy import DEMO_URL
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

PASSWORD = "Security-fixture-012345!"
ORIGIN = "http://127.0.0.1:5173"


@pytest.fixture
def security_client(database, monkeypatch, tmp_path):
    monkeypatch.setenv("BLACKBOX_EVIDENCE_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("BLACKBOX_DEMO_TESTING_ENABLED", "false")
    monkeypatch.setenv("BLACKBOX_LOCAL_LAB_ENABLED", "false")
    monkeypatch.setenv("BLACKBOX_AI_PROVIDER", "disabled")
    monkeypatch.setenv("BLACKBOX_AI_API_KEY", "")
    get_settings.cache_clear()
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.headers.update(
            {
                "Origin": ORIGIN,
                "X-Blackbox-Request": "1",
                "Content-Type": "application/json",
            }
        )
        yield client


def signup(client, factory, email="owner@example.com"):
    with factory() as session:
        token = bootstrap_invitation(session)
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": PASSWORD,
            "invitation": token,
            "workspace_name": "Privado",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    client.headers.update(
        {
            "X-CSRF-Token": data["csrf_token"],
            "X-Workspace-ID": data["active_workspace_id"],
        }
    )
    return data, token


@pytest.fixture
def owner(security_client, database):
    _, factory, _ = database
    data, _ = signup(security_client, factory)
    return security_client, factory, data


def add_user(factory, workspace, role="member", email="member@example.com"):
    from auth_support import synthetic_hash

    with factory.begin() as session:
        user = User(email=email, password_hash=synthetic_hash())
        session.add(user)
        session.flush()
        session.add(
            WorkspaceMembership(user_id=user.id, workspace_id=workspace, role=role)
        )
        return user.id


def login(client, email, password=None):
    from auth_support import PASSWORD as LEGACY_PASSWORD

    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password or LEGACY_PASSWORD},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    client.headers.update(
        {
            "X-CSRF-Token": data["csrf_token"],
            "X-Workspace-ID": data["active_workspace_id"],
        }
    )
    return data


def credentials(client):
    return {
        "Cookie": f"blackbox_session={client.cookies.get('blackbox_session')}; blackbox_csrf={client.cookies.get('blackbox_csrf')}",
        "X-CSRF-Token": client.headers["X-CSRF-Token"],
        "X-Workspace-ID": client.headers["X-Workspace-ID"],
    }


def test_no_anonymous_resource_access_and_closed_registration(security_client):
    for path in [
        "/api/projects",
        "/api/v1/projects",
        "/api/v1/dashboard",
        "/api/v1/runs",
        "/api/v1/lab/capabilities",
        "/api/v1/testing/capabilities",
        "/api/v1/ai/capabilities",
    ]:
        assert security_client.get(path).status_code == 401
    assert security_client.get("/api/v1/health").status_code == 200
    result = security_client.post(
        "/api/v1/auth/register",
        json={
            "email": "anon@example.com",
            "password": PASSWORD,
            "invitation": "x" * 43,
        },
    )
    assert result.status_code == 403


def test_registration_argon2_cookie_hashes_normalization_and_no_legacy_adoption(
    security_client, database, caplog
):
    _, factory, _ = database
    data, invitation = signup(security_client, factory, "  Owner@EXAMPLE.com  ")
    assert data["user"]["email"] == "owner@example.com"
    assert data["active_workspace_id"] != "local"
    with factory() as session:
        user = session.get(User, data["user"]["id"])
        assert (
            user.password_hash.startswith("$argon2id$")
            and PASSWORD not in user.password_hash
        )
        row = session.scalar(select(AuthSession))
        assert row.token_hash != security_client.cookies.get("blackbox_session")
        assert row.csrf_hash == digest(data["csrf_token"])
        assert (
            session.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .where(WorkspaceMembership.workspace_id == "local")
            )
            == 0
        )
        assert session.scalar(select(RegistrationInvite)).used_at is not None
    current = security_client.get("/api/v1/auth/session")
    assert current.status_code == 200
    assert PASSWORD not in caplog.text and invitation not in caplog.text
    assert (
        security_client.post(
            "/api/v1/auth/register",
            json={
                "email": "next@example.com",
                "password": PASSWORD,
                "invitation": invitation,
            },
        ).status_code
        == 403
    )


def test_cookies_are_httponly_and_session_rotates_on_login(owner):
    client, _, _ = owner
    old = client.cookies.get("blackbox_session")
    response = client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert any(
        "blackbox_session=" in cookie
        and "HttpOnly" in cookie
        and "SameSite=strict" in cookie
        and "Path=/" in cookie
        for cookie in cookies
    )
    assert client.cookies.get("blackbox_session") != old
    assert (
        "password" not in json.dumps(response.json())
        and "token_hash" not in response.text
    )


@pytest.mark.parametrize(
    "mutation", ["missing", "wrong", "cookie", "origin", "request_header", "media"]
)
def test_csrf_origin_and_json_are_enforced(owner, mutation):
    client, _, _ = owner
    headers = dict(client.headers)
    if mutation == "missing":
        headers.pop("x-csrf-token", None)
    if mutation == "wrong":
        headers["x-csrf-token"] = "z" * 43
    if mutation == "cookie":
        headers["cookie"] = (
            f"blackbox_session={client.cookies.get('blackbox_session')}; blackbox_csrf={'z' * 43}"
        )
    if mutation == "origin":
        headers["origin"] = "http://evil.invalid"
    if mutation == "request_header":
        headers.pop("x-blackbox-request", None)
    if mutation == "media":
        headers["content-type"] = "text/plain"
    # Use a built request so omitted headers are truly omitted, not merged.
    request = client.build_request(
        "POST", "/api/projects", json={"name": "CSRF", "base_url": DEMO_URL}
    )
    for key in [
        "x-csrf-token",
        "x-blackbox-request",
        "origin",
        "content-type",
        "cookie",
    ]:
        if key in headers:
            request.headers[key] = headers[key]
        elif key != "cookie":
            request.headers.pop(key, None)
    response = client.send(request)
    assert response.status_code == (415 if mutation == "media" else 403), response.text


def test_login_errors_are_generic_and_bruteforce_limited(owner):
    client, factory, _ = owner
    for email in ["owner@example.com", "unknown@example.com"]:
        result = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert result.status_code == 401
        assert result.json() == {"detail": "Credenciales no válidas."}
    outcomes = [
        client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.com", "password": "wrong-password"},
        ).status_code
        for _ in range(6)
    ]
    assert 429 in outcomes and outcomes[-1] == 429
    with factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "auth.login_failed")
            )
            >= 2
        )


@pytest.mark.parametrize("kind", ["absolute", "idle", "revoked", "inactive"])
def test_session_expiration_revocation_and_inactive_accounts(owner, kind):
    client, factory, data = owner
    with factory.begin() as session:
        row = session.scalar(
            select(AuthSession).where(
                AuthSession.token_hash == digest(client.cookies.get("blackbox_session"))
            )
        )
        if kind == "absolute":
            row.expires_at = now() - timedelta(seconds=1)
        if kind == "idle":
            row.last_seen_at = now() - timedelta(minutes=61)
        if kind == "revoked":
            row.revoked_at = now()
        if kind == "inactive":
            session.get(User, data["user"]["id"]).is_active = False
    assert client.get("/api/v1/auth/session").status_code == 401
    assert client.get("/api/projects").status_code == 401


def test_password_change_revokes_all_sessions_and_validates_current_password(owner):
    client, factory, _ = owner
    old = credentials(client)
    login(client, "owner@example.com", PASSWORD)
    assert (
        client.post(
            "/api/v1/auth/password",
            json={
                "current_password": "wrong",
                "new_password": "New-security-password-123",
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": "short"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            json={
                "current_password": PASSWORD,
                "new_password": "New-security-password-123",
            },
        ).status_code
        == 204
    )
    assert client.get("/api/v1/auth/session", headers=old).status_code == 401
    assert client.get("/api/v1/auth/session").status_code == 401
    login(client, "owner@example.com", "New-security-password-123")
    assert client.get("/api/projects").status_code == 200
    with factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.event_type == "auth.password_changed")
            )
            == 1
        )


def test_logout_and_individual_session_revocation(owner):
    client, _, _ = owner
    first = credentials(client)
    first_id = client.get("/api/v1/auth/sessions").json()["items"][0]["id"]
    login(client, "owner@example.com", PASSWORD)
    sessions = client.get("/api/v1/auth/sessions").json()["items"]
    second_id = next(row["id"] for row in sessions if row["current"])
    assert second_id != first_id
    second = credentials(client)
    assert (
        client.delete(f"/api/v1/auth/sessions/{second_id}", headers=first).status_code
        == 204
    )
    assert client.get("/api/v1/auth/session", headers=second).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=first).status_code == 204
    assert client.get("/api/v1/auth/session", headers=first).status_code == 401


@pytest.mark.parametrize("role", ["owner", "admin", "member", "viewer"])
def test_permissions_by_role_are_applied_on_backend(owner, role):
    client, factory, data = owner
    workspace = data["active_workspace_id"]
    if role != "owner":
        add_user(factory, workspace, role)
        login(client, "member@example.com")
    response = client.post(
        "/api/projects", json={"name": "Permisos", "base_url": DEMO_URL}
    )
    assert response.status_code == (403 if role == "viewer" else 201)
    assert client.get("/api/projects").status_code == 200
    audit = client.get(f"/api/v1/workspaces/{workspace}/audit")
    assert audit.status_code == (200 if role in {"owner", "admin"} else 403)
    if role != "viewer":
        assert client.delete(f"/api/projects/{response.json()['id']}").status_code == (
            204 if role in {"owner", "admin"} else 403
        )
    result = client.post(
        f"/api/v1/workspaces/{workspace}/invitations",
        json={"email": "invited@example.com", "role": "member"},
    )
    assert result.status_code == (201 if role == "owner" else 403)


def test_invitations_are_email_bound_expiring_and_one_use(owner):
    client, factory, data = owner
    workspace = data["active_workspace_id"]
    created = client.post(
        f"/api/v1/workspaces/{workspace}/invitations",
        json={"email": "Invited@example.com", "role": "viewer"},
    )
    assert created.status_code == 201
    token = created.json()["invitation"]
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrong@example.com",
                "password": PASSWORD,
                "invitation": token,
            },
        ).status_code
        == 403
    )
    result = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invited@example.com",
            "password": PASSWORD,
            "invitation": token,
        },
    )
    assert (
        result.status_code == 201 and result.json()["workspaces"][0]["role"] == "viewer"
    )
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "invited@example.com",
                "password": PASSWORD,
                "invitation": token,
            },
        ).status_code
        == 403
    )
    with factory() as session:
        row = session.scalar(
            select(RegistrationInvite).where(
                RegistrationInvite.token_hash == digest(token)
            )
        )
        assert row.used_at is not None and row.token_hash != token


def test_no_role_escalation_and_last_owner_protected(owner):
    client, factory, data = owner
    workspace, user = data["active_workspace_id"], data["user"]["id"]
    assert (
        client.patch(
            f"/api/v1/workspaces/{workspace}/members/{user}", json={"role": "admin"}
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/api/v1/workspaces/{workspace}/members/{user}").status_code
        == 409
    )
    member = add_user(factory, workspace)
    login(client, "member@example.com")
    assert (
        client.patch(
            f"/api/v1/workspaces/{workspace}/members/{member}", json={"role": "owner"}
        ).status_code
        == 403
    )
    assert client.post(
        f"/api/v1/runs/{uuid4()}/ai-analysis",
        json={"mode": "llm", "authorize_external": True},
    ).status_code in {403, 422}
    assert (
        client.post(
            "/api/projects",
            json={"name": "Spoof", "base_url": DEMO_URL, "workspace_id": "local"},
        ).status_code
        == 422
    )
    assert (
        client.get("/api/projects", headers={"X-Workspace-ID": "local"}).status_code
        == 404
    )


def test_concurrent_owner_demotions_keep_at_least_one_owner(owner):
    client, factory, data = owner
    workspace = data["active_workspace_id"]
    first_id, first = data["user"]["id"], credentials(client)
    second_id = add_user(factory, workspace, "owner")
    login(client, "member@example.com")
    second = credentials(client)

    def demote(user, headers):
        return client.patch(
            f"/api/v1/workspaces/{workspace}/members/{user}",
            headers=headers,
            json={"role": "member"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(demote, first_id, first),
            executor.submit(demote, second_id, second),
        ]
        outcomes = [future.result() for future in futures]
    assert sorted(outcomes) == [200, 409]
    with factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .where(
                    WorkspaceMembership.workspace_id == workspace,
                    WorkspaceMembership.role == "owner",
                )
            )
            == 1
        )


def test_foreign_resources_downloads_relations_and_aggregates_are_isolated(owner):
    client, factory, data = owner
    original = data["active_workspace_id"]
    with factory.begin() as session:
        project = Project(name="Privado A", base_url=DEMO_URL, workspace_id=original)
        session.add(project)
        session.flush()
        run = Run(
            project_id=project.id,
            workspace_id=original,
            status=RunStatus.COMPLETED,
            target_url=DEMO_URL,
        )
        suite = TestSuite(
            project_id=project.id, workspace_id=original, name="Suite A", description=""
        )
        env = TestEnvironment(
            project_id=project.id,
            workspace_id=original,
            name="Demo A",
            kind="demo",
            base_url=DEMO_URL,
            authorized_origin=DEMO_URL.rstrip("/"),
            limits={},
        )
        session.add_all([run, suite, env])
        session.flush()
        page = TestPage(
            test_run_id=run.id, url=DEMO_URL, status_code=200, load_time_ms=1
        )
        session.add(page)
        session.flush()
        image = io.BytesIO()
        Image.new("RGB", (2, 2)).save(image, "PNG")
        page.screenshot_path = app.state.run_manager.evidence.save(
            run.id, page.id, image.getvalue()
        )
        analysis = AIAnalysis(
            run_id=run.id,
            workspace_id=original,
            provider="rules",
            model="rules",
            mode="rules",
            status="completed",
            prompt_version="v1",
            context_hash="a" * 64,
            evidence_json={},
        )
        session.add(analysis)
        session.flush()
        identifiers = {
            "project": project.id,
            "run": run.id,
            "suite": suite.id,
            "env": env.id,
            "page": page.id,
            "analysis": analysis.id,
        }
    other = client.post("/api/v1/workspaces", json={"name": "Otro"}).json()["id"]
    add_user(factory, other, "owner", "outsider@example.com")
    login(client, "outsider@example.com")
    p, r, s, e, image, ai = [
        identifiers[key]
        for key in ["project", "run", "suite", "env", "page", "analysis"]
    ]
    for path in [
        f"/projects/{p}",
        f"/projects/{p}/runs",
        f"/projects/{p}/analytics",
        f"/projects/{p}/environments",
        f"/projects/{p}/suites",
        f"/suites/{s}",
        f"/suites/{s}/runs",
        f"/runs/{r}",
        f"/runs/{r}/issues",
        f"/runs/{r}/pages",
        f"/runs/{r}/pages/{image}/screenshot",
        f"/runs/{r}/report",
        f"/runs/{r}/report/html",
        f"/runs/{r}/report/pdf",
        f"/runs/{r}/export/json",
        f"/runs/{r}/export/csv",
        f"/runs/{r}/suite-results",
        f"/runs/{r}/ai-analysis",
        f"/ai-analyses/{ai}",
        f"/projects/{p}/compare?base_run_id={r}&target_run_id={uuid4()}",
    ]:
        response = client.get("/api/v1" + path)
        assert response.status_code == 404, (path, response.text)
    for method, path, body in [
        ("DELETE", f"/projects/{p}", None),
        ("PATCH", f"/projects/{p}", {"name": "Attacker"}),
        ("DELETE", f"/environments/{e}", None),
        ("DELETE", f"/suites/{s}", None),
        ("POST", f"/runs/{r}/cancel", None),
        ("POST", f"/ai-analyses/{ai}/cancel", None),
        (
            "POST",
            f"/environments/{e}/check",
            {"authorize": True, "consent_origin": DEMO_URL.rstrip("/")},
        ),
    ]:
        response = client.request(
            method, "/api/v1" + path, **({"json": body} if body is not None else {})
        )
        assert response.status_code == 404, (path, response.text)
    assert client.get("/api/v1/dashboard").json()["metrics"]["projects"] == 0
    assert client.get("/api/v1/runs").json()["total"] == 0
    assert client.get("/api/v1/projects").json()["total"] == 0
    assert (
        client.get(
            f"/api/v1/runs/{r}", headers={"X-Workspace-ID": original}
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/runs/{r}?workspace={original}", headers={"X-Workspace-ID": ""}
        ).status_code
        == 404
    )


def test_security_headers_body_limits_host_and_forwarding_headers(owner):
    client, _, _ = owner
    response = client.get("/api/projects")
    for key in [
        "x-content-type-options",
        "x-frame-options",
        "content-security-policy",
        "referrer-policy",
        "permissions-policy",
        "x-request-id",
    ]:
        assert key in response.headers
    assert (
        client.get("/api/projects", headers={"Host": "rebind.invalid"}).status_code
        == 400
    )
    assert client.post("/api/projects", content=b"x" * 65537).status_code == 413
    assert client.get("/api/projects?workspace=foreign").status_code == 400


def test_legacy_adoption_is_explicit_and_downgrade_protects_users(owner, database):
    client, factory, data = owner
    with factory.begin() as session:
        legacy = Project(name="Histórico", base_url=DEMO_URL, workspace_id="local")
        session.add(legacy)
        session.flush()
        identifier = legacy.id
    assert client.get(f"/api/projects/{identifier}").status_code == 404
    with factory() as session, pytest.raises(ValueError):
        adopt_legacy(session, "owner@example.com", False)
    with factory() as session:
        adopt_legacy(session, "owner@example.com", True)
    assert (
        client.get(
            f"/api/projects/{identifier}", headers={"X-Workspace-ID": "local"}
        ).status_code
        == 200
    )
    with factory() as session, pytest.raises(ValueError):
        adopt_legacy(session, "owner@example.com", True)
    with pytest.raises(RuntimeError, match="Downgrade bloqueado"):
        command.downgrade(database[2], "e62f1b809a73")
    with factory() as session:
        assert session.get(Project, identifier) is not None
        assert session.get(User, data["user"]["id"]) is not None
    command.check(database[2])


def test_safe_migration_roundtrip_without_users_preserves_nonempty_history(database):
    _, factory, config = database
    with factory.begin() as session:
        project = Project(name="Anterior", base_url=DEMO_URL)
        session.add(project)
        session.flush()
        identifier = project.id
    command.downgrade(config, "e62f1b809a73")
    command.upgrade(config, "head")
    with factory() as session:
        assert session.get(Project, identifier).workspace_id == "local"
        assert (
            session.scalar(select(func.count()).select_from(WorkspaceMembership)) == 0
        )
    command.check(config)


def test_production_rejects_insecure_configuration():
    with pytest.raises(ValueError):
        Settings(_env_file=None, environment="production", deployment_mode="local")
    with pytest.raises(ValueError):
        Settings(_env_file=None, deployment_mode="https", cors_origins=[ORIGIN])
    with pytest.raises(ValueError):
        Settings(_env_file=None, cors_origins=["*"])


def test_secure_cookie_flags_https_and_host_configuration(database, monkeypatch):
    monkeypatch.setenv("BLACKBOX_DEPLOYMENT_MODE", "https")
    monkeypatch.setenv("BLACKBOX_CORS_ORIGINS", '["https://127.0.0.1:5173"]')
    get_settings.cache_clear()
    _, factory, _ = database
    with factory() as session:
        token = bootstrap_invitation(session)
    with TestClient(app, base_url="https://127.0.0.1:8000") as client:
        client.headers.update(
            {"Origin": "https://127.0.0.1:5173", "X-Blackbox-Request": "1"}
        )
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "secure@example.com",
                "password": PASSWORD,
                "invitation": token,
            },
        )
        assert response.status_code == 201, response.text
        assert any(
            "__Host-blackbox_session=" in c and "Secure" in c and "HttpOnly" in c
            for c in response.headers.get_list("set-cookie")
        )
        current = client.get("/api/v1/auth/session")
        assert (
            current.status_code == 200
            and "strict-transport-security" in current.headers
        )
        assert (
            client.get("http://127.0.0.1:8000/api/v1/auth/session").status_code == 400
        )
        assert (
            client.get(
                "/api/v1/auth/session", headers={"Host": "rebind.invalid"}
            ).status_code
            == 400
        )
        assert client.get("/docs").status_code == 404


def test_expired_invitation_and_weak_password_do_not_create_user(
    security_client, database
):
    _, factory, _ = database
    with factory() as session:
        token = bootstrap_invitation(session)
    assert (
        security_client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com",
                "password": "x" * 14,
                "invitation": token,
            },
        ).status_code
        == 422
    )
    with factory.begin() as session:
        session.scalar(select(RegistrationInvite)).expires_at = now() - timedelta(
            seconds=1
        )
    assert (
        security_client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@example.com",
                "password": PASSWORD,
                "invitation": token,
            },
        ).status_code
        == 403
    )
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 0


def test_concurrent_signup_consumes_bootstrap_only_once(security_client, database):
    _, factory, _ = database
    with factory() as session:
        token = bootstrap_invitation(session)

    def create(index):
        return security_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"user{index}@example.com",
                "password": PASSWORD,
                "invitation": token,
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, [1, 2]))
    assert sorted(results) == [201, 403]
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
        assert (
            session.scalar(select(func.count()).select_from(WorkspaceMembership)) == 1
        )


def test_audit_records_projects_llm_requests_and_redacted_structured_logs(
    owner, caplog
):
    import logging

    client, factory, data = owner
    logger = logging.getLogger("blackbox.security")
    logger.addHandler(caplog.handler)
    try:
        response = client.post(
            "/api/projects",
            json={"name": "PrivateMarker-password=do-not-log", "base_url": DEMO_URL},
        )
        assert response.status_code == 201
        identifier = response.json()["id"]
        with factory.begin() as session:
            run = Run(
                project_id=identifier,
                workspace_id=data["active_workspace_id"],
                target_url=DEMO_URL,
                status=RunStatus.COMPLETED,
            )
            session.add(run)
            session.flush()
            run_id = run.id
        denied = client.post(
            f"/api/v1/runs/{run_id}/ai-analysis",
            json={"mode": "llm", "authorize_external": True},
        )
        assert (
            denied.status_code == 409
        )  # Provider is explicitly disabled; no call is made.
        assert client.delete(f"/api/projects/{identifier}").status_code == 204
    finally:
        logger.removeHandler(caplog.handler)
    with factory() as session:
        events = list(
            session.scalars(
                select(AuditEvent).where(
                    AuditEvent.workspace_id == data["active_workspace_id"]
                )
            )
        )
        assert {"project.created", "project.deleted", "llm.requested"} <= {
            e.event_type for e in events
        }
        assert all("PrivateMarker" not in (e.resource_id or "") for e in events)
    logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "blackbox.security"
    ]
    assert logs and all("request_id" in entry for entry in logs)
    assert "PrivateMarker" not in caplog.text and PASSWORD not in caplog.text


def test_audit_retention_purges_only_old_rows(database):
    _, factory, _ = database
    with factory.begin() as session:
        session.add_all(
            [
                AuditEvent(
                    event_type="old",
                    outcome="success",
                    created_at=now() - timedelta(days=91),
                ),
                AuditEvent(
                    event_type="recent",
                    outcome="success",
                    created_at=now() - timedelta(days=1),
                ),
            ]
        )
    with TestClient(app, base_url="http://127.0.0.1:8000"), factory() as session:
        assert list(session.scalars(select(AuditEvent.event_type))) == ["recent"]


def test_real_body_stream_is_bounded_even_without_content_length(owner):
    client, _, _ = owner
    response = client.post("/api/projects", content=(b"x" * 20000 for _ in range(4)))
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"


def test_slow_body_is_cancelled_before_routing(database, monkeypatch):
    import asyncio

    from app.core.security_middleware import SecurityMiddleware

    monkeypatch.setenv("BLACKBOX_BODY_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    messages = []

    async def forbidden(scope, receive, send):
        raise AssertionError("Slow body must be rejected before routing")

    async def receive():
        await asyncio.sleep(2)
        return {"type": "http.request", "body": b"{}"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "query_string": b"",
        "headers": [(b"host", b"127.0.0.1:8000")],
        "scheme": "http",
        "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 12345),
    }
    asyncio.run(SecurityMiddleware(forbidden)(scope, receive, send))
    assert messages[0]["status"] == 408


def test_cross_references_between_valid_ids_cannot_escape_workspace(owner):
    client, factory, data = owner
    original = data["active_workspace_id"]
    with factory.begin() as session:
        project = Project(name="A", base_url=DEMO_URL, workspace_id=original)
        session.add(project)
        session.flush()
        suite = TestSuite(
            project_id=project.id, workspace_id=original, name="A", description=""
        )
        env = TestEnvironment(
            project_id=project.id,
            workspace_id=original,
            name="A",
            kind="demo",
            base_url=DEMO_URL,
            authorized_origin=DEMO_URL.rstrip("/"),
            limits={},
        )
        run = Run(
            project_id=project.id,
            workspace_id=original,
            target_url=DEMO_URL,
            status=RunStatus.COMPLETED,
        )
        session.add_all([suite, env, run])
        session.flush()
        case = SuiteCase(
            suite_id=suite.id,
            name="A",
            position=0,
            enabled=True,
            definition={
                "type": "http_status",
                "path": "/",
                "minimum": 200,
                "maximum": 200,
            },
        )
        page = TestPage(
            test_run_id=run.id, url=DEMO_URL, status_code=200, load_time_ms=1
        )
        analysis = AIAnalysis(
            run_id=run.id,
            workspace_id=original,
            provider="rules",
            model="rules",
            mode="rules",
            status="completed",
            prompt_version="v1",
            context_hash="a" * 64,
            evidence_json={},
            result_json={},
        )
        session.add_all([case, page, analysis])
        session.flush()
        foreign = {
            "case": case.id,
            "page": page.id,
            "run": run.id,
            "env": env.id,
            "ai": analysis.id,
        }
    second = client.post("/api/v1/workspaces", json={"name": "B"}).json()["id"]
    with factory.begin() as session:
        p = Project(name="B", base_url=DEMO_URL, workspace_id=second)
        session.add(p)
        session.flush()
        r = Run(
            project_id=p.id,
            workspace_id=second,
            target_url=DEMO_URL,
            status=RunStatus.COMPLETED,
        )
        s = TestSuite(project_id=p.id, workspace_id=second, name="B", description="")
        session.add_all([r, s])
        session.flush()
        local = {"project": p.id, "run": r.id, "suite": s.id}
    add_user(factory, second, "owner", "second@example.com")
    login(client, "second@example.com")
    assert (
        client.get(
            f"/api/v1/projects/{local['project']}/compare?base_run_id={foreign['run']}&target_run_id={local['run']}"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/runs/{local['run']}/pages/{foreign['page']}/screenshot"
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/suite-cases/{foreign['case']}", json={"enabled": False}
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/suite-cases/{foreign['case']}").status_code == 404
    assert (
        client.post(
            f"/api/v1/suites/{local['suite']}/runs",
            json={
                "environment_id": foreign["env"],
                "authorize": True,
                "consent_origin": DEMO_URL.rstrip("/"),
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/suites/{local['suite']}/import-ai",
            json={
                "analysis_id": foreign["ai"],
                "suggestion_index": 0,
                "name": "Attack",
                "position": 0,
                "confirm": True,
            },
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/workspaces/{original}/members").status_code == 404
