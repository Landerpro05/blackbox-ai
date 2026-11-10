import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from uuid import uuid4

import httpx2
import pytest
from alembic import command
from app.cli import exit_code
from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.config import BACKEND_ROOT, Settings, get_settings
from app.lab_server import LabHandler
from app.main import app
from app.models import (
    AIAnalysis,
    Issue,
    Project,
    Run,
    RunStatus,
    TestEnvironment,
    TestSuite,
)
from app.testing.demo import response_for
from app.testing.local_policy import ControlledLocalPolicy, LocalBroker, local_origin
from app.testing.policy import DEMO_ORIGIN, DEMO_URL, DestinationDenied
from auth_support import AuthenticatedTestClient as TestClient
from sqlalchemy import text


@pytest.fixture
def controlled_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), LabHandler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.fixture
def lab_client(database, monkeypatch, tmp_path, controlled_server):
    monkeypatch.setenv("BLACKBOX_DEMO_TESTING_ENABLED", "true")
    monkeypatch.setenv("BLACKBOX_LOCAL_LAB_ENABLED", "true")
    monkeypatch.setenv(
        "BLACKBOX_LOCAL_LAB_ALLOWED_ORIGINS", json.dumps([controlled_server])
    )
    monkeypatch.setenv("BLACKBOX_AI_PROVIDER", "disabled")
    monkeypatch.setenv("BLACKBOX_AI_API_KEY", "")
    monkeypatch.setenv("BLACKBOX_EVIDENCE_DIR", str(tmp_path / "evidence"))
    browsers = BACKEND_ROOT.parent / ".tools/browsers"
    if browsers.is_dir() and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client


def create_lab(client, origin=DEMO_ORIGIN, kind="demo", limits=None):
    project = client.post(
        "/api/projects", json={"name": "Testing Lab", "base_url": origin + "/"}
    ).json()
    payload = {"name": "Desarrollo", "kind": kind, "base_url": origin + "/"}
    if limits:
        payload["limits"] = limits
    environment_response = client.post(
        f"/api/v1/projects/{project['id']}/environments", json=payload
    )
    assert environment_response.status_code == 201, environment_response.text
    suite_response = client.post(
        f"/api/v1/projects/{project['id']}/suites", json={"name": "Suite principal"}
    )
    assert suite_response.status_code == 201, suite_response.text
    return project, environment_response.json(), suite_response.json()


def add_case(client, suite, definition, position=0, enabled=True):
    response = client.post(
        f"/api/v1/suites/{suite['id']}/cases",
        json={
            "name": f"Caso {position}",
            "position": position,
            "enabled": enabled,
            "definition": definition,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def start(client, suite, environment):
    return client.post(
        f"/api/v1/suites/{suite['id']}/runs",
        json={
            "environment_id": environment["id"],
            "authorize": True,
            "consent_origin": environment["authorized_origin"],
        },
    )


def wait_result(client, identifier, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{identifier}/suite-results")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["run"]["status"] not in {"pending", "running"}:
            return result
        time.sleep(0.03)
    raise AssertionError("Suite did not finish within test budget")


@pytest.mark.parametrize(
    "value",
    [
        "http://localhost:3000",
        "http://127.1:3000",
        "http://2130706433:3000",
        "http://0177.0.0.1:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:80",
        "http://127.0.0.1:03000",
        "http://0.0.0.0:3000",
        "http://192.168.1.1:3000",
        "http://169.254.169.254:3000",
        "https://example.com:3000",
        "http://rebind.example:3000",
        "http://user:secret@127.0.0.1:3000",
        "http://127.0.0.1:3000?token=secret",
        "http://127.0.0.1:3000#x",
        "file:///etc/passwd",
        "data:text/html,hi",
        "ftp://127.0.0.1:3000",
        "http://[::ffff:127.0.0.1]:3000",
        "http://127.0.0.1:3000\\@example.com",
    ],
)
def test_local_origin_denies_ambiguous_dns_private_and_unsafe_urls(value):
    with pytest.raises(DestinationDenied):
        local_origin(value)


def test_exact_origin_methods_catalog_and_no_dns(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Validation must never resolve DNS or open sockets")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    origin = "http://127.0.0.1:3000"
    policy = ControlledLocalPolicy(origin, [origin, "http://127.0.0.1:3001"])
    assert policy.authorize(origin + "/about") == origin + "/about"
    assert local_origin("https://[::1]:3000/") == "https://[::1]:3000"
    for path in [
        "/private",
        "/../about",
        "/%61bout",
        "/submit",
        "/download.zip",
        "/?x=1",
    ]:
        with pytest.raises(DestinationDenied):
            policy.authorize(origin + path)
    with pytest.raises(DestinationDenied):
        policy.authorize("http://127.0.0.1:3001/")
    with pytest.raises(DestinationDenied):
        policy.authorize(origin + "/", "POST")
    assert Settings(_env_file=None).local_lab_enabled is False


@pytest.mark.parametrize(
    "mutation", ["body", "status", "location", "content-type", "size"]
)
def test_broker_rejects_any_unverified_content_without_following_redirects(mutation):
    calls = []
    expected = response_for("/about")

    def responder(request):
        calls.append(str(request.url))
        headers = {"content-type": expected.content_type}
        body, status = expected.body, expected.status
        if mutation == "body":
            body += "<script>window.pwned=true</script>"
        if mutation == "status":
            status = 500
        if mutation == "location":
            headers["location"] = "http://127.0.0.1:8000/private"
        if mutation == "content-type":
            headers["content-type"] = "text/plain"
        if mutation == "size":
            body = "x" * 1_000_001
        return httpx2.Response(status, text=body, headers=headers)

    origin = "http://127.0.0.1:3000"
    broker = LocalBroker(
        ControlledLocalPolicy(origin, [origin]),
        transport=httpx2.MockTransport(responder),
    )
    with pytest.raises(DestinationDenied):
        asyncio.run(broker(origin + "/about"))
    assert calls == [origin + "/about"]
    with pytest.raises(DestinationDenied):
        asyncio.run(broker("http://127.0.0.1:8000/private"))
    assert len(calls) == 1


def test_environment_suite_crud_persistence_and_no_io(client, database, monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Registration must not access any URL")

    monkeypatch.setattr(LocalBroker, "__call__", deny)
    project, env, suite = create_lab(client, "http://127.0.0.1:3000", "local")
    assert env["configuration_state"] == "disabled"
    assert (
        client.get("/api/v1/lab/capabilities").json()["arbitrary_apps_enabled"] is False
    )
    updated = client.patch(
        f"/api/v1/environments/{env['id']}",
        json={"name": "Actualizado", "base_url": "http://127.0.0.1:3001/about"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["authorized_origin"] == "http://127.0.0.1:3001"
    assert (
        client.patch(
            f"/api/v1/suites/{suite['id']}", json={"description": "Persistida"}
        ).status_code
        == 200
    )
    case = add_case(
        client,
        suite,
        {"type": "title", "expected_title": "Acerca de", "path": "/about"},
    )
    assert (
        client.patch(
            f"/api/v1/suite-cases/{case['id']}", json={"enabled": False, "position": 3}
        ).status_code
        == 200
    )
    detail = client.get(f"/api/v1/suites/{suite['id']}").json()
    assert (
        detail["cases"][0]["position"] == 3 and detail["cases"][0]["enabled"] is False
    )
    assert (
        client.get(f"/api/v1/projects/{project['id']}/environments?limit=1").json()[
            "total"
        ]
        == 1
    )
    assert client.get(f"/api/v1/projects/{project['id']}/suites").json()["total"] == 1
    _, factory, _ = database
    with factory() as session:
        assert session.get(TestEnvironment, env["id"]).name == "Actualizado"
        assert session.get(TestSuite, suite["id"]).description == "Persistida"
    assert client.delete(f"/api/v1/suite-cases/{case['id']}").status_code == 204
    assert client.delete(f"/api/v1/suites/{suite['id']}").status_code == 204
    assert client.delete(f"/api/v1/environments/{env['id']}").status_code == 204
    assert client.get(f"/api/v1/suites/{suite['id']}").status_code == 404


@pytest.mark.parametrize(
    "definition",
    [
        {"type": "python", "code": "raise Exception()"},
        {"type": "no_js_errors", "javascript": "alert(1)"},
        {"type": "element_exists", "selector": "xpath=//*"},
        {"type": "element_exists", "selector": "button >> text=Delete"},
        {"type": "http_status", "minimum": 500, "maximum": 200},
        {"type": "http_status", "minimum": True},
        {"type": "title", "expected_title": ""},
        {"type": "navigate", "destination": "//example.com"},
        {"type": "navigate", "destination": "javascript:alert(1)"},
        {"type": "text_visible", "text": "x", "path": "/%2e%2e/private"},
    ],
)
def test_declarative_schema_never_accepts_code_or_unsafe_paths(client, definition):
    _, _, suite = create_lab(client)
    response = client.post(
        f"/api/v1/suites/{suite['id']}/cases",
        json={"name": "Prueba inválida", "position": 0, "definition": definition},
    )
    assert response.status_code == 422, response.text


def test_invalid_environments_limits_and_workspace_scope(client, database):
    project, env, suite = create_lab(client)
    for payload in [
        {"name": " ", "kind": "local", "base_url": "http://127.0.0.1:3000"},
        {"name": "X", "kind": "local", "base_url": "http://localhost:3000"},
        {"name": "X", "kind": "staging", "base_url": "https://example.com"},
        {
            "name": "X",
            "kind": "demo",
            "base_url": DEMO_URL,
            "limits": {"max_pages": 21},
        },
        {"name": "X", "kind": "demo", "base_url": DEMO_URL, "token": "secret"},
    ]:
        assert (
            client.post(
                f"/api/v1/projects/{project['id']}/environments", json=payload
            ).status_code
            == 422
        )
    assert client.patch(f"/api/v1/environments/{env['id']}", json={}).status_code == 422
    assert (
        client.patch(
            f"/api/v1/environments/{env['id']}",
            json={"base_url": "http://localhost:3000"},
        ).status_code
        == 422
    )
    app.dependency_overrides[get_workspace_access] = lambda: WorkspaceAccess("other")
    try:
        assert client.get(f"/api/v1/suites/{suite['id']}").status_code == 404
        assert (
            client.get(f"/api/v1/projects/{project['id']}/environments").status_code
            == 404
        )
        assert client.delete(f"/api/v1/environments/{env['id']}").status_code == 404
    finally:
        app.dependency_overrides.clear()
    assert client.delete(f"/api/v1/environments/{uuid4()}").status_code == 404


def test_consent_disabled_modes_and_case_order_conflicts(client):
    _, env, suite = create_lab(client)
    add_case(client, suite, {"type": "http_status"})
    assert start(client, suite, env).status_code == 403
    for consent in [
        {"authorize": False, "consent_origin": env["authorized_origin"]},
        {"authorize": True, "consent_origin": "http://127.0.0.1:3001"},
    ]:
        consent["environment_id"] = env["id"]
        assert (
            client.post(f"/api/v1/suites/{suite['id']}/runs", json=consent).status_code
            == 403
        )
    assert (
        client.post(
            f"/api/v1/suites/{suite['id']}/cases",
            json={
                "name": "Duplicado",
                "position": 0,
                "definition": {"type": "http_status"},
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/environments/{env['id']}/check",
            json={"authorize": False, "consent_origin": env["authorized_origin"]},
        ).status_code
        == 403
    )


@pytest.mark.browser
def test_real_local_catalog_all_seven_case_types_failures_history_and_ai(
    lab_client, controlled_server
):
    client = lab_client
    _project, env, suite = create_lab(client, controlled_server, "local")
    assert (
        client.post(
            f"/api/v1/environments/{env['id']}/check",
            json={"authorize": True, "consent_origin": env["authorized_origin"]},
        ).json()["last_check_status"]
        == "verified"
    )
    definitions = [
        {"type": "http_status", "path": "/about"},
        {"type": "title", "path": "/about", "expected_title": "Acerca de"},
        {"type": "element_exists", "path": "/about", "selector": "h1"},
        {"type": "text_visible", "path": "/about", "text": "Acerca de"},
        {"type": "no_js_errors", "path": "/about"},
        {"type": "internal_links", "path": "/depth/1"},
        {"type": "navigate", "path": "/about", "destination": "/depth/1"},
        {"type": "title", "path": "/about", "expected_title": "Título incorrecto"},
        {"type": "no_js_errors", "path": "/"},
    ]
    cases = [add_case(client, suite, d, i) for i, d in enumerate(definitions)]
    add_case(
        client, suite, {"type": "http_status", "path": "/missing"}, 20, enabled=False
    )
    response = start(client, suite, env)
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    assert (
        client.patch(
            f"/api/v1/environments/{env['id']}", json={"name": "Busy"}
        ).status_code
        == 409
    )
    result = wait_result(client, identifier)
    assert result["run"]["status"] == "completed", result
    assert result["counts"] == {
        "pending": 0,
        "pass": 7,
        "fail": 2,
        "error": 0,
        "skipped": 0,
    }, result
    assert exit_code(result) == 1
    assert all(c["evidence_url"] for c in result["cases"])
    assert client.get("/api/v1" + result["cases"][0]["evidence_url"]).status_code == 200
    assert client.get(f"/api/v1/suites/{suite['id']}/runs").json()["total"] == 1
    assert (
        client.patch(
            f"/api/v1/environments/{env['id']}",
            json={"base_url": controlled_server + "/about"},
        ).status_code
        == 200
    )
    assert client.delete(f"/api/v1/suites/{suite['id']}").status_code == 204
    preserved = client.get(f"/api/v1/runs/{identifier}/suite-results").json()
    assert preserved["environment"]["base_url"] == controlled_server + "/"
    assert preserved["cases"][0]["definition"] == result["cases"][0]["definition"]
    analysis = client.post(
        f"/api/v1/runs/{identifier}/ai-analysis", json={"mode": "rules"}
    )
    assert analysis.status_code == 202, analysis.text
    analysis_id = analysis.json()["id"]
    for _ in range(200):
        details = client.get(f"/api/v1/ai-analyses/{analysis_id}").json()
        if details["status"] not in {"pending", "running"}:
            break
        time.sleep(0.03)
    assert details["status"] == "completed", details
    assert cases


@pytest.mark.browser
@pytest.mark.parametrize(
    "path,limits,expected",
    [
        ("/slow", {"navigation_timeout_seconds": 1}, "failed"),
        ("/slow", {"timeout_seconds": 1}, "failed"),
        ("/subresources", {}, "completed"),
        ("/redirect", {}, "failed"),
        ("/", {"max_requests": 1}, "failed"),
    ],
)
def test_real_demo_timeouts_redirects_subresources_and_budgets(
    lab_client, path, limits, expected
):
    _, env, suite = create_lab(lab_client, limits=limits)
    add_case(lab_client, suite, {"type": "http_status", "path": path})
    response = start(lab_client, suite, env)
    assert response.status_code == 202, response.text
    result = wait_result(lab_client, response.json()["id"])
    assert result["run"]["status"] == expected, result
    if expected == "failed":
        assert result["counts"]["error"] == 1
        assert exit_code(result) == 2
    if path == "/subresources":
        issues = lab_client.get(f"/api/v1/runs/{result['run']['id']}/issues").json()
        assert any(i["type"] == "request_blocked" for i in issues)


@pytest.mark.browser
def test_real_cancellation_pending_cases_and_active_slot_reuse(lab_client):
    _, env, suite = create_lab(lab_client)
    add_case(lab_client, suite, {"type": "http_status", "path": "/slow"})
    identifier = start(lab_client, suite, env).json()["id"]
    assert start(lab_client, suite, env).status_code == 409
    assert lab_client.post(f"/api/v1/runs/{identifier}/cancel").status_code == 202
    result = wait_result(lab_client, identifier)
    assert result["run"]["status"] == "cancelled"
    assert result["counts"]["skipped"] == 1
    assert exit_code(result) == 3
    assert lab_client.delete(f"/api/v1/suites/{suite['id']}").status_code == 204


def test_unknown_catalog_path_rejected_before_browser_or_network(
    lab_client, controlled_server, monkeypatch
):
    _, env, suite = create_lab(lab_client, controlled_server, "local")
    add_case(lab_client, suite, {"type": "http_status", "path": "/private"})

    def deny(*args, **kwargs):
        raise AssertionError("Preflight must reject before IO")

    monkeypatch.setattr(LocalBroker, "__call__", deny)
    assert start(lab_client, suite, env).status_code == 403


def test_migration_roundtrip_preserves_existing_runs_issues_ai(database):
    engine, factory, config = database
    with factory.begin() as session:
        project = Project(name="Histórico", base_url=DEMO_URL)
        session.add(project)
        session.flush()
        run = Run(
            project_id=project.id, status=RunStatus.COMPLETED, target_url=DEMO_URL
        )
        session.add(run)
        session.flush()
        issue = Issue(
            run_id=run.id,
            kind="http",
            severity="high",
            description="HTTP500",
            affected_url=DEMO_URL,
        )
        ai = AIAnalysis(
            run_id=run.id,
            workspace_id="local",
            provider="rules",
            model="rules-v1",
            mode="rules",
            status="completed",
            prompt_version="v1",
            context_hash="a" * 64,
            evidence_json={},
        )
        session.add_all([issue, ai])
        session.flush()
        ids = run.id, issue.id, ai.id
    command.downgrade(config, "d51e09a3b842")
    with engine.connect() as connection:
        for table, identifier in zip(
            ["runs", "issues", "ai_analyses"], ids, strict=True
        ):
            assert (
                connection.scalar(
                    text(f"SELECT id FROM {table} WHERE id=:id"), {"id": identifier}
                )
                == identifier
            )
    command.upgrade(config, "head")
    command.check(config)
    with factory() as session:
        assert session.get(Run, ids[0]).environment_snapshot == {}
        assert session.get(AIAnalysis, ids[2]) is not None


@pytest.mark.browser
def test_actual_cli_demo_json_and_exit_codes(tmp_path, monkeypatch):
    browsers = BACKEND_ROOT.parent / ".tools/browsers"
    environment = {
        **os.environ,
        "BLACKBOX_ENVIRONMENT": "test",
        "BLACKBOX_DEMO_TESTING_ENABLED": "true",
        "BLACKBOX_AI_PROVIDER": "disabled",
        "BLACKBOX_AI_API_KEY": "",
        "BLACKBOX_EVIDENCE_DIR": str(tmp_path / "evidence"),
    }
    if browsers.is_dir():
        environment.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    output = tmp_path / "results.json"
    command_args = [
        sys.executable,
        "-m",
        "app.cli",
        "demo",
        "--bootstrap",
        "--email",
        "owner@example.com",
        "--password-stdin",
        "--standalone",
        "--database",
        str(tmp_path / "cli.db"),
        "--json",
        str(output),
    ]
    denied = subprocess.run(
        command_args,
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert denied.returncode == 2 and not output.exists()
    result = subprocess.run(
        [*command_args, "--authorize"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=40,
        input="Fase7-pruebas-012345!\n",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    persisted = json.loads(output.read_text("utf-8"))
    assert persisted["counts"]["pass"] == 4
    assert "completed" in result.stderr
    assert "api_key" not in output.read_text("utf-8")


@pytest.mark.parametrize(
    "status,fail,error,code",
    [
        ("completed", 0, 0, 0),
        ("completed", 1, 0, 1),
        ("completed", 1, 1, 2),
        ("failed", 0, 1, 2),
        ("cancelled", 0, 0, 3),
    ],
)
def test_cli_distinguishes_assertions_execution_and_cancellation(
    status, fail, error, code
):
    assert (
        exit_code({"run": {"status": status}, "counts": {"fail": fail, "error": error}})
        == code
    )


def test_case_count_budget_and_cross_project_preflight(lab_client):
    _, env, suite = create_lab(lab_client, limits={"max_pages": 1})
    add_case(lab_client, suite, {"type": "http_status"}, 0)
    add_case(lab_client, suite, {"type": "http_status"}, 1)
    assert start(lab_client, suite, env).status_code == 422
    _, other_env, _ = create_lab(lab_client)
    assert start(lab_client, suite, other_env).status_code == 404
    for position in range(2, 20):
        add_case(lab_client, suite, {"type": "http_status"}, position)
    assert (
        lab_client.post(
            f"/api/v1/suites/{suite['id']}/cases",
            json={
                "name": "Caso 21",
                "position": 20,
                "definition": {"type": "http_status"},
            },
        ).status_code
        == 422
    )


@pytest.mark.browser
def test_actual_unverified_local_body_never_reaches_browser(
    lab_client, controlled_server, monkeypatch
):
    original = LabHandler.do_GET

    def altered(handler):
        if handler.path == "/about":
            body = b"<script>fetch('http://127.0.0.1:8000/private');throw Error('UNTRUSTED_MARKER')</script>"
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        else:
            original(handler)

    monkeypatch.setattr(LabHandler, "do_GET", altered)
    _, env, suite = create_lab(lab_client, controlled_server, "local")
    add_case(lab_client, suite, {"type": "no_js_errors", "path": "/about"})
    response = start(lab_client, suite, env)
    assert response.status_code == 202
    result = wait_result(lab_client, response.json()["id"])
    assert result["run"]["status"] == "failed" and result["counts"]["error"] == 1
    issues = lab_client.get(f"/api/v1/runs/{result['run']['id']}/issues").json()
    assert any(i["type"] == "local_integrity" for i in issues)
    assert "UNTRUSTED_MARKER" not in json.dumps(issues)


def test_real_broker_connects_only_literal_loopback(controlled_server, monkeypatch):
    original, resolutions = socket.getaddrinfo, []

    def resolve(host, *args, **kwargs):
        resolutions.append(host)
        assert host in {"127.0.0.1", b"127.0.0.1"}
        return original(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    policy = ControlledLocalPolicy(controlled_server, [controlled_server])
    response = asyncio.run(LocalBroker(policy)(controlled_server + "/about"))
    assert response.body == response_for("/about").body
    assert all(host in {"127.0.0.1", b"127.0.0.1"} for host in resolutions)


def test_ai_import_requires_review_and_ignores_generated_code(client, database):
    project, env, suite = create_lab(client)
    _, factory, _ = database
    with factory.begin() as session:
        run = Run(
            project_id=project["id"], status=RunStatus.COMPLETED, target_url=DEMO_URL
        )
        session.add(run)
        session.flush()
        analysis = AIAnalysis(
            run_id=run.id,
            workspace_id="local",
            provider="rules",
            model="rules-v1",
            mode="rules",
            status="completed",
            prompt_version="v1",
            context_hash="b" * 64,
            evidence_json={
                "issues": [
                    {
                        "id": "evidence-1",
                        "type": "http",
                        "url": DEMO_ORIGIN + "/server-error",
                    }
                ]
            },
            result_json={
                "suggested_tests": [
                    {
                        "template": "http_status",
                        "evidence_ids": ["evidence-1"],
                        "code": "raise RuntimeError('never execute')",
                    }
                ]
            },
        )
        session.add(analysis)
        session.flush()
        identifier = analysis.id
    payload = {
        "analysis_id": identifier,
        "suggestion_index": 0,
        "name": "HTTP revisado",
        "position": 0,
        "confirm": False,
    }
    assert (
        client.post(f"/api/v1/suites/{suite['id']}/import-ai", json=payload).status_code
        == 403
    )
    payload["confirm"] = True
    response = client.post(f"/api/v1/suites/{suite['id']}/import-ai", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["enabled"] is False
    assert response.json()["definition"] == {
        "type": "http_status",
        "path": "/server-error",
        "minimum": 100,
        "maximum": 399,
    }
    assert start(client, suite, env).status_code == 403
