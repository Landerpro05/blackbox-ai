import asyncio
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest
from auth_support import AuthenticatedTestClient as TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.main import app
from app.models import Project, Run, RunStatus, TestPage
from app.schemas.runs import RunLimits
from app.testing.engine import DemoEngine
from app.testing.evidence import EvidenceStore
from app.testing.policy import (
    DEMO_URL,
    DemoPolicy,
    DestinationDenied,
    redact_text,
    redact_url,
)


@pytest.fixture
def demo_client(database, monkeypatch, tmp_path):
    monkeypatch.setenv("BLACKBOX_DEMO_TESTING_ENABLED", "true")
    monkeypatch.setenv("BLACKBOX_EVIDENCE_DIR", str(tmp_path / "evidence"))
    portable = Path(__file__).resolve().parents[2] / ".tools" / "browsers"
    if portable.is_dir() and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(portable))
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client


def create_project(client, path="/"):
    response = client.post(
        "/api/projects", json={"name": "Demo", "base_url": DEMO_URL.rstrip("/") + path}
    )
    assert response.status_code == 201
    return response.json()["id"]


def wait_for(client, run_id, statuses, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200, response.text
        if response.json()["status"] in statuses:
            return response.json()
        time.sleep(0.02)
    raise AssertionError(f"Run did not reach {statuses}")


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/",
        "http://metadata.google.internal/",
        "http://rebind.example/",
        "https://example.com/",
        "https://blackbox-demo.invalid/",
        "http://blackbox-demo.invalid.evil/",
        "http://blackbox-demo.invalid:8000/",
        "http://user:secret@blackbox-demo.invalid/",
        "http://blackbox-demo.invalid/?token=secret",
        "file:///C:/Windows",
        "data:text/html,hi",
    ],
)
def test_policy_denies_every_destination_outside_bundled_demo(url):
    with pytest.raises(DestinationDenied):
        DemoPolicy().authorize(url)


def test_policy_never_resolves_dns_or_accepts_rebinding(monkeypatch):
    calls = []

    def rebinding(*args):
        calls.append(args)
        return [
            (None, None, None, None, ("127.0.0.1" if len(calls) > 1 else "8.8.8.8", 80))
        ]

    monkeypatch.setattr("socket.getaddrinfo", rebinding)
    assert DemoPolicy().authorize(DEMO_URL) == DEMO_URL
    for _ in range(2):
        with pytest.raises(DestinationDenied):
            DemoPolicy().authorize("http://rebind.example/")
    assert calls == []
    with pytest.raises(DestinationDenied):
        DemoPolicy().authorize(DEMO_URL, "POST")


@pytest.mark.parametrize(
    "changes",
    [
        {"max_pages": 21},
        {"max_depth": 4},
        {"navigation_timeout_seconds": 31},
        {"timeout_seconds": 181},
        {"max_requests": 201},
        {"max_pages": True},
        {"max_pages": 0},
    ],
)
def test_limits_have_safe_maximums(changes):
    with pytest.raises(ValueError):
        RunLimits(**changes)


def test_secret_redaction_and_evidence_path_guards(tmp_path):
    assert (
        redact_url("https://user:secret@example.com/path?token=secret#fragment")
        == "https://example.com/path"
    )
    result = redact_text(
        "token=demo-secret password=hidden Bearer abcdef user@example.com https://example.com/a?key=hidden"
    )
    assert not any(
        value in result
        for value in ("demo-secret", "hidden", "abcdef", "user@example.com")
    )
    store = EvidenceStore(tmp_path)
    with pytest.raises(ValueError):
        store.path("../private", str(uuid4()))
    with pytest.raises(ValueError):
        store.path(str(uuid4()), "../../private")
    with pytest.raises(ValueError):
        store.save(str(uuid4()), str(uuid4()), b"not an image")


def test_demo_disabled_by_default_and_authorization_required(client):
    project_id = create_project(client)
    assert client.get("/api/v1/testing/capabilities").json()["demo_enabled"] is False
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
        ).status_code
        == 403
    )
    assert (
        client.post(f"/api/v1/projects/{project_id}/runs", json={}).status_code == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": False}
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/projects/{project_id}/runs").json()["items"] == []


def test_public_and_other_local_projects_cannot_be_scanned(demo_client):
    for url in ("https://example.com", "http://127.0.0.1:8000"):
        project_id = demo_client.post(
            "/api/projects", json={"name": "Not authorized", "base_url": url}
        ).json()["id"]
        assert (
            demo_client.post(
                f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
            ).status_code
            == 403
        )


@pytest.mark.parametrize("authorization", [1, "true", None, {}])
def test_authorization_must_be_an_explicit_json_boolean(client, authorization):
    project_id = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": authorization}
    )
    assert response.status_code == 422


def test_production_cannot_enable_the_demo():
    from app.core.config import Settings

    with pytest.raises(ValueError):
        Settings(environment="production", demo_testing_enabled=True)


def test_engine_failure_is_sanitized_and_releases_resources(demo_client):
    class FailingEngine(WaitingEngine):
        async def run(self, run_id, target, limits, on_page):
            self.browser_connected = True
            try:
                raise RuntimeError("secret=do-not-store-me /internal/private/path")
            finally:
                self.browser_connected = False

    app.state.run_manager.engine_factory = FailingEngine
    project_id = create_project(demo_client)
    created = demo_client.post(
        f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
    ).json()
    run = wait_for(demo_client, created["id"], {"failed"})
    assert (
        "do-not-store-me" not in run["error_message"]
        and "/internal/" not in run["error_message"]
    )
    assert not WaitingEngine.instances[-1].browser_connected


def test_active_slot_is_unique_in_sqlite(database):
    from sqlalchemy.exc import IntegrityError

    _, factory, _ = database
    with factory.begin() as session:
        project = Project(name="Slot", base_url=DEMO_URL)
        session.add(project)
        session.flush()
        project_id = project.id
        session.add(Run(project_id=project_id, active_slot=1))
    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(Run(project_id=project_id, active_slot=1))


def test_phase_three_migration_preserves_issues_and_backfills_workspace(database):
    from datetime import UTC, datetime
    from alembic import command
    from sqlalchemy import text
    from app.models import Issue

    engine, factory, config = database
    command.downgrade(config, "b72c4f2810a1")
    project_id, run_id, issue_id = str(uuid4()), str(uuid4()), str(uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (id,name,base_url,workspace_id,created_at,updated_at) VALUES (:id,'Existing','https://example.com','foreign',:now,:now)"
            ),
            {"id": project_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO runs (id,project_id,status,created_at) VALUES (:id,:project,'completed',:now)"
            ),
            {"id": run_id, "project": project_id, "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO issues (id,run_id,kind,severity,description,affected_url,created_at) VALUES (:id,:run,'http','high','Existing','https://example.com',:now)"
            ),
            {"id": issue_id, "run": run_id, "now": now},
        )
    command.upgrade(config, "head")
    with factory() as session:
        run = session.get(Run, run_id)
        assert run.workspace_id == "foreign" and run.issues_found == 1
        assert run.target_url == "https://example.com"
        assert session.get(Issue, issue_id).description == "Existing"


@pytest.mark.browser
def test_real_browser_closes_after_persistence_callback_failure(
    demo_client, monkeypatch
):
    engines = []

    def factory(evidence):
        engine = DemoEngine(evidence)
        engines.append(engine)
        return engine

    def fail_write(*args):
        raise RuntimeError("Simulated database callback failure")

    service = app.state.run_manager
    service.engine_factory = factory
    monkeypatch.setattr(service.writer, "page", fail_write)
    project_id = create_project(demo_client)
    created = demo_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"authorize_demo": True, "limits": {"max_pages": 1}},
    ).json()
    run = wait_for(demo_client, created["id"], {"failed"})
    assert run["pages_scanned"] == 0
    assert engines and not engines[-1].browser_connected
    directory = service.evidence.root / created["id"]
    assert not list(directory.glob("*.png"))


class WaitingEngine(DemoEngine):
    instances = []

    def __init__(self, evidence):
        super().__init__(evidence)
        self.instances.append(self)

    async def run(self, run_id, target, limits, on_page):
        self.browser_connected = True
        try:
            await asyncio.Event().wait()
        finally:
            self.browser_connected = False


def test_single_active_run_cancel_states_and_project_mutation_guards(demo_client):
    service = app.state.run_manager
    service.engine_factory = WaitingEngine
    project_id = create_project(demo_client)
    first = demo_client.post(
        f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
    )
    assert first.status_code == 202 and first.json()["status"] == "pending"
    run_id = first.json()["id"]
    wait_for(demo_client, run_id, {"running"})
    assert (
        demo_client.post(
            f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
        ).status_code
        == 409
    )
    assert (
        demo_client.patch(
            f"/api/projects/{project_id}", json={"name": "Cannot edit"}
        ).status_code
        == 409
    )
    assert demo_client.delete(f"/api/projects/{project_id}").status_code == 409
    assert demo_client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 202
    result = wait_for(demo_client, run_id, {"cancelled"})
    assert result["finished_at"] and result["cancellation_requested"]
    assert not WaitingEngine.instances[-1].browser_connected
    assert (
        demo_client.post(f"/api/v1/runs/{run_id}/cancel").json()["status"]
        == "cancelled"
    )
    second = demo_client.post(
        f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
    )
    assert second.status_code == 202
    demo_client.post(f"/api/v1/runs/{second.json()['id']}/cancel")
    wait_for(demo_client, second.json()["id"], {"cancelled"})
    assert (
        demo_client.patch(
            f"/api/projects/{project_id}", json={"name": "Now editable"}
        ).status_code
        == 200
    )


def test_mock_global_timeout_releases_slot(demo_client):
    app.state.run_manager.engine_factory = WaitingEngine
    project_id = create_project(demo_client)
    response = demo_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"authorize_demo": True, "limits": {"timeout_seconds": 1}},
    )
    run = wait_for(demo_client, response.json()["id"], {"failed"})
    assert "timeout global" in run["error_message"]
    assert not WaitingEngine.instances[-1].browser_connected


def test_cross_workspace_runs_and_evidence_are_inaccessible(demo_client, database):
    _, factory, _ = database
    with factory.begin() as session:
        project = Project(name="Foreign", base_url=DEMO_URL, workspace_id="foreign")
        session.add(project)
        session.flush()
        run = Run(
            project_id=project.id, workspace_id="foreign", status=RunStatus.COMPLETED
        )
        session.add(run)
        session.flush()
        page = TestPage(test_run_id=run.id, url=DEMO_URL, load_time_ms=10)
        session.add(page)
        session.flush()
        run_id, project_id, page_id = run.id, project.id, page.id
    for suffix in ("", "/issues", "/pages", f"/pages/{page_id}/screenshot"):
        assert demo_client.get(f"/api/v1/runs/{run_id}{suffix}").status_code == 404
    assert demo_client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 404
    assert demo_client.get(f"/api/v1/projects/{project_id}/runs").status_code == 404
    assert (
        demo_client.post(
            f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("enabled", ["true", "false"])
def test_server_restart_recovers_interrupted_runs(
    database, monkeypatch, tmp_path, enabled
):
    _, factory, _ = database
    with factory.begin() as session:
        project = Project(name="Restart", base_url=DEMO_URL)
        session.add(project)
        session.flush()
        run = Run(project_id=project.id, status=RunStatus.RUNNING, active_slot=1)
        session.add(run)
        session.flush()
        run_id = run.id
    monkeypatch.setenv("BLACKBOX_DEMO_TESTING_ENABLED", enabled)
    monkeypatch.setenv("BLACKBOX_EVIDENCE_DIR", str(tmp_path / "evidence"))
    get_settings.cache_clear()
    with TestClient(app) as client:
        result = client.get(f"/api/v1/runs/{run_id}").json()
        assert result["status"] == "failed" and "reinició" in result["error_message"]
    with factory() as session:
        assert session.get(Run, run_id).active_slot is None


def test_worker_database_lock_prevents_multiple_executors(tmp_path):
    from app.services.worker_lock import WorkerLock

    first = WorkerLock(str(tmp_path / "test.db"))
    second = WorkerLock(str(tmp_path / "test.db"))
    first.acquire()
    try:
        with pytest.raises(RuntimeError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


@pytest.mark.browser
def test_real_chromium_detects_persists_and_redacts_results(demo_client, database):
    project_id = create_project(demo_client)
    created = demo_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={
            "authorize_demo": True,
            "limits": {"max_pages": 10, "navigation_timeout_seconds": 1},
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    result = wait_for(demo_client, run_id, {"completed", "failed"}, timeout=25)
    assert result["status"] == "completed", result
    assert result["pages_scanned"] == 10 and result["issues_found"] > 0
    issues = demo_client.get(f"/api/v1/runs/{run_id}/issues").json()
    pages = demo_client.get(f"/api/v1/runs/{run_id}/pages").json()
    kinds = {issue["type"] for issue in issues}
    assert {
        "http",
        "javascript",
        "console",
        "broken_link",
        "redirect_blocked",
        "request_blocked",
        "navigation_timeout",
        "form_label",
    } <= kinds
    assert any(page["status_code"] == 500 for page in pages)
    assert all(page["depth"] <= 2 for page in pages)
    assert any(
        page["url"].endswith("/many/1") and page["status_code"] == 200 for page in pages
    )
    assert not any(
        secret in str(issues)
        for secret in ("demo-secret-123", "demo-password-123", "private@example.com")
    )
    screenshot = next(
        page["screenshot_url"] for page in pages if page["screenshot_url"]
    )
    image = demo_client.get("/api/v1" + screenshot)
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert image.headers["content-type"] == "image/png"
    high = demo_client.get(f"/api/v1/runs/{run_id}/issues?severity=high").json()
    assert high and all(issue["severity"] == "high" for issue in high)
    assert (
        demo_client.get(f"/api/v1/runs/{run_id}/issues?severity=wrong").status_code
        == 422
    )
    assert demo_client.get(f"/api/v1/projects/{project_id}/runs").json()["total"] == 1
    _, factory, _ = database
    with factory() as session:
        stored = session.get(Run, run_id)
        assert stored.active_slot is None and stored.pages_visited == 10
        assert (
            len(
                list(
                    session.scalars(
                        select(TestPage).where(TestPage.test_run_id == run_id)
                    )
                )
            )
            == 10
        )
    assert demo_client.delete(f"/api/projects/{project_id}").status_code == 204
    assert not app.state.run_manager.evidence.path(run_id, pages[0]["id"]).exists()


@pytest.mark.browser
@pytest.mark.parametrize(
    "path,limits,expected_count,maximum_depth",
    [
        ("/many/1", RunLimits(max_pages=3, max_depth=2), 3, 2),
        ("/depth/1", RunLimits(max_pages=10, max_depth=1), 2, 1),
        ("/subresources", RunLimits(max_pages=3, max_requests=1), 1, 0),
    ],
)
def test_real_crawler_budgets(demo_client, path, limits, expected_count, maximum_depth):
    project_id = create_project(demo_client, path)
    created = demo_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"authorize_demo": True, "limits": limits.model_dump()},
    )
    run_id = created.json()["id"]
    result = wait_for(demo_client, run_id, {"completed", "failed"})
    assert result["status"] == "completed", result
    assert result["pages_scanned"] == expected_count
    pages = demo_client.get(f"/api/v1/runs/{run_id}/pages").json()
    assert max(page["depth"] for page in pages) <= maximum_depth


@pytest.mark.browser
def test_real_browser_cancellation_and_global_timeout_close_resources(demo_client):
    engines = []

    def factory(evidence):
        engine = DemoEngine(evidence)
        engines.append(engine)
        return engine

    app.state.run_manager.engine_factory = factory
    project_id = create_project(demo_client, "/slow")
    created = demo_client.post(
        f"/api/v1/projects/{project_id}/runs", json={"authorize_demo": True}
    )
    run_id = created.json()["id"]
    wait_for(demo_client, run_id, {"running"})
    deadline = time.monotonic() + 10
    while (
        not engines or not engines[-1].browser_connected
    ) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert engines and engines[-1].browser_connected
    demo_client.post(f"/api/v1/runs/{run_id}/cancel")
    assert wait_for(demo_client, run_id, {"cancelled"})["status"] == "cancelled"
    assert not engines[-1].browser_connected
    second = demo_client.post(
        f"/api/v1/projects/{project_id}/runs",
        json={"authorize_demo": True, "limits": {"timeout_seconds": 1}},
    ).json()
    result = wait_for(demo_client, second["id"], {"failed"})
    assert "timeout global" in result["error_message"]
    assert not engines[-1].browser_connected
