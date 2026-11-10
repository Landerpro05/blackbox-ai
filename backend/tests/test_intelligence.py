import ast
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from alembic import command
from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.config import Settings
from app.main import app
from app.models import AIAnalysis, Issue, Project, Run, RunStatus, Severity, TestPage
from app.schemas.intelligence import EngineResult
from app.services.ai_evidence import MAX_CONTEXT_BYTES, collect
from app.services.ai_manager import validate_result
from app.services.ai_provider import (
    SYSTEM,
    AnthropicProvider,
    ProviderError,
    ProviderResult,
)
from app.services.ai_rules import analyze_rules
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

CASES = json.loads(
    (Path(__file__).parent / "fixtures/ai_evaluation_cases.json").read_text("utf-8")
)


@pytest.fixture(autouse=True)
def forbid_live_llm_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("No live commercial API calls in intelligence tests")

    monkeypatch.setattr("socket.create_connection", deny)


def seed(factory, cases, status=RunStatus.COMPLETED):
    with factory.begin() as session:
        project = Project(
            name="Evaluación reproducible", base_url="http://blackbox-demo.invalid/"
        )
        session.add(project)
        session.flush()
        run = Run(
            project_id=project.id,
            target_url=project.base_url,
            status=status,
            finished_at=datetime.now(UTC) if status == RunStatus.COMPLETED else None,
        )
        session.add(run)
        session.flush()
        page = None
        if not all(case.get("no_pages") for case in cases):
            page = TestPage(
                test_run_id=run.id,
                url=project.base_url,
                status_code=200,
                load_time_ms=50,
            )
            session.add(page)
            session.flush()
            page.screenshot_path = f"{page.id}.png"
        for case in cases:
            for _ in range(case.get("repeat", 1)):
                session.add(
                    Issue(
                        run_id=run.id,
                        kind=case["kind"],
                        severity=Severity.HIGH,
                        title=case["title"],
                        description=case["message"],
                        affected_url=project.base_url,
                        evidence_path=page.screenshot_path if page else None,
                    )
                )
        return project.id, run.id


@pytest.fixture
def ai_case(client, database):
    _, factory, _ = database
    project, run = seed(factory, CASES[:5])
    return {"project": project, "run": run, "factory": factory}


def create(client, run, **options):
    return client.post(f"/api/v1/runs/{run}/ai-analysis", json=options)


def wait(client, identifier, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        response = client.get(f"/api/v1/ai-analyses/{identifier}")
        assert response.status_code == 200, response.text
        if response.json()["status"] not in {"pending", "running"}:
            return response.json()
        time.sleep(0.01)
    raise AssertionError("Intelligence job did not finish")


def configured(**changes):
    return Settings(
        _env_file=None,
        ai_provider="anthropic",
        ai_model="fixture-model",
        ai_api_key="fixture-private-key-123",
        ai_cooldown_seconds=0,
        **changes,
    )


def llm_options(**changes):
    return {
        "mode": "llm",
        "authorize_external": True,
        "consent_provider": "anthropic",
        "consent_model": "fixture-model",
        **changes,
    }


class FakeProvider:
    calls = 0

    async def analyze(self, evidence, maximum):
        self.calls += 1
        return ProviderResult(analyze_rules(evidence, maximum), 300, 120)


def enable_fake(settings=None, provider=None):
    provider = provider or FakeProvider()
    app.state.ai_manager.settings = settings or configured()
    app.state.ai_manager.provider_factory = lambda settings: provider
    return provider


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_controlled_rule_evaluations(client, database, case):
    _, factory, _ = database
    _, run = seed(factory, [case])
    response = create(client, run, max_findings=8)
    assert response.status_code == 202, response.text
    result = wait(client, response.json()["id"])
    assert result["status"] == "completed", result["error_message"]
    assert result["mode_label"] == "Análisis basado en reglas"
    assert result["provider"] == "rules"
    assert len(result["result"]["findings"]) == 1
    assert result["evidence"]["groups"][0]["count"] == case.get("repeat", 1)
    assert result["evidence"]["quarantined_messages"] == int(
        case.get("quarantined", False)
    )
    assert all(
        finding["confidence"] == "low" for finding in result["result"]["findings"]
    )
    assert len(result["result"]["suggested_tests"]) == int(case["template"] is not None)
    if case["template"]:
        proposal = result["result"]["suggested_tests"][0]
        assert proposal["template"] == case["template"]
        tree = ast.parse(proposal["code"])
        assert {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } == {"playwright.sync_api"}
        assert "REEMPLAZA_POR_UN_ENTORNO_AUTORIZADO" in proposal["code"]
    text = json.dumps(result)
    for secret in (
        "synthetic-private",
        "synthetic-password",
        "user@example.com",
        "evil.invalid",
        "Ignore previous",
    ):
        assert secret not in text


def test_rules_no_provider_and_persistence_cache(client, ai_case):
    fake = enable_fake()
    first = create(client, ai_case["run"])
    assert first.status_code == 202
    result = wait(client, first.json()["id"])
    assert result["status"] == "completed"
    cached = create(client, ai_case["run"])
    assert cached.status_code == 200 and cached.json()["id"] == result["id"]
    assert fake.calls == 0
    with ai_case["factory"]() as session:
        row = session.get(AIAnalysis, result["id"])
        assert row.result_json == result["result"]
        assert row.active_slot is None and row.reserved_tokens == 0
    listing = client.get(f"/api/v1/runs/{ai_case['run']}/ai-analysis?limit=1").json()
    assert listing["total"] == 1 and len(listing["items"]) == 1
    assert first.headers["location"].endswith(result["id"])


def test_default_capabilities_no_key_exposure(client):
    data = client.get("/api/v1/ai/capabilities").json()
    assert data["rules_enabled"] and not data["llm_enabled"]
    assert data["screenshots_sent"] is False and data["test_execution_enabled"] is False
    enable_fake()
    data = client.get("/api/v1/ai/capabilities")
    assert data.json()["llm_enabled"]
    assert "fixture-private-key" not in data.text and "api_key" not in data.text


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "other"},
        {"mode": "llm", "authorize_external": 1},
        {"authorize_external": "true"},
        {"max_findings": 0},
        {"max_findings": 9},
        {"max_findings": True},
        {"include_history": 1},
        {"api_key": "bad"},
        {"provider": "evil"},
    ],
)
def test_strict_creation_parameters(client, ai_case, options):
    assert create(client, ai_case["run"], **options).status_code == 422


def test_external_consent_and_configuration_required(client, ai_case):
    assert create(client, ai_case["run"], mode="llm").status_code == 403
    assert create(client, ai_case["run"], **llm_options()).status_code == 409
    fake = enable_fake()
    assert (
        create(client, ai_case["run"], mode="llm", authorize_external=True).status_code
        == 409
    )
    assert (
        create(
            client, ai_case["run"], **llm_options(consent_model="changed-model")
        ).status_code
        == 409
    )
    assert fake.calls == 0
    accepted = create(client, ai_case["run"], **llm_options())
    assert accepted.status_code == 202
    result = wait(client, accepted.json()["id"])
    assert result["status"] == "completed", result["error_message"]
    assert result["external_authorized_at"] and result["actual_input_tokens"] == 300
    assert "fixture-private-key" not in json.dumps(result)


def test_workspace_isolation_all_intelligence_routes(client, ai_case):
    identifier = create(client, ai_case["run"]).json()["id"]
    wait(client, identifier)
    app.dependency_overrides[get_workspace_access] = lambda: WorkspaceAccess("other")
    try:
        assert create(client, ai_case["run"]).status_code == 404
        assert (
            client.get(f"/api/v1/runs/{ai_case['run']}/ai-analysis").status_code == 404
        )
        assert client.get(f"/api/v1/ai-analyses/{identifier}").status_code == 404
        assert (
            client.post(f"/api/v1/ai-analyses/{identifier}/cancel").status_code == 404
        )
    finally:
        app.dependency_overrides.clear()
    assert client.get(f"/api/v1/ai-analyses/{uuid4()}").status_code == 404
    assert create(client, "invalid-id").status_code == 422
    assert (
        client.get(f"/api/v1/runs/{ai_case['run']}/ai-analysis?limit=21").status_code
        == 422
    )


def test_source_must_be_terminal(client, database):
    _, factory, _ = database
    _, run = seed(factory, CASES[:1], RunStatus.RUNNING)
    assert create(client, run).status_code == 409


def test_context_redacts_and_bounds_without_screenshots(client, ai_case):
    with ai_case["factory"].begin() as session:
        for index in range(210):
            session.add(
                Issue(
                    run_id=ai_case["run"],
                    kind="console",
                    severity=Severity.LOW,
                    title=f"Error {index}",
                    description="x" * 4000 + " token=synthetic-private",
                    affected_url="https://user:secret@example.com/a?token=private",
                )
            )
        result = collect(session, ai_case["run"], "local", True)
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= MAX_CONTEXT_BYTES
    assert len(result["issues"]) <= 20 and len(result["pages"]) <= 10
    assert result["omitted_issues"] > 190
    assert {item["id"] for item in result["issues"]} == {
        key for group in result["groups"] for key in group["evidence_ids"]
    }
    text = json.dumps(result)
    assert (
        "data:image" not in text and ".png" not in text and "evidence_path" not in text
    )
    assert "synthetic-private" not in text and "user:secret" not in text


def test_safe_code_uses_only_literal_paths_never_executes(client, ai_case):
    with ai_case["factory"].begin() as session:
        session.add(
            Issue(
                run_id=ai_case["run"],
                kind="http",
                severity=Severity.HIGH,
                title="HTTP 500",
                description="HTTP 500",
                affected_url='http://blackbox-demo.invalid/");__import__("os").system("id")#',
            )
        )
    result = wait(client, create(client, ai_case["run"], max_findings=8).json()["id"])
    assert result["status"] == "completed", result["error_message"]
    for test in result["result"]["suggested_tests"]:
        tree = ast.parse(test["code"])
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"__import__", "eval", "exec", "open"}
            for node in ast.walk(tree)
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "reference",
        "code",
        "command",
        "url",
        "file",
        "http_fact",
        "confirmed",
        "template",
    ],
)
def test_rejects_ungrounded_or_unsafe_provider_output(client, ai_case, mutation):
    class MalformedProvider:
        async def analyze(self, evidence, maximum):
            result = analyze_rules(evidence, maximum).model_dump()
            if mutation == "reference":
                result["findings"][0]["evidence_ids"] = ["issue:" + str(uuid4())]
            elif mutation == "code":
                result["suggested_tests"][0]["code"] = "print('never')"
            elif mutation == "command":
                result["findings"][0]["hypothesis"] = "powershell Remove-Item private"
            elif mutation == "url":
                result["findings"][0]["hypothesis"] = "Consulta https://evil.invalid/"
            elif mutation == "file":
                result["findings"][0]["hypothesis"] = (
                    "El fallo está en src/server.py:42"
                )
            elif mutation == "http_fact":
                result["findings"][0]["hypothesis"] = "HTTP 503 observado"
            elif mutation == "confirmed":
                result["findings"][0]["hypothesis"] = "Causa confirmada"
            else:
                test = result["suggested_tests"][0]
                test["template"] = "no_console_errors"
                test["evidence_ids"] = [
                    next(
                        item["id"]
                        for item in evidence["issues"]
                        if item["type"] == "http"
                    )
                ]
            return ProviderResult(EngineResult.model_validate(result), 1, 1)

    enable_fake(provider=MalformedProvider())
    result = wait(client, create(client, ai_case["run"], **llm_options()).json()["id"])
    assert result["status"] == "failed" and result["result"] is None
    assert "evil.invalid" not in json.dumps(result) and "server.py" not in json.dumps(
        result
    )
    assert client.get(f"/api/v1/runs/{ai_case['run']}/report/html").status_code == 200


def test_quota_cache_cost_and_fallback(client, ai_case):
    fake = enable_fake(
        configured(ai_input_usd_per_million=3, ai_output_usd_per_million=15)
    )
    first = wait(
        client,
        create(client, ai_case["run"], **llm_options(max_findings=1)).json()["id"],
    )
    assert first["status"] == "completed" and float(first["reserved_cost_usd"]) > 0
    assert (
        first["reserved_tokens"]
        == (first["estimated_input_tokens"] + first["estimated_output_tokens"]) * 2
    )
    assert (
        create(client, ai_case["run"], **llm_options(max_findings=1)).status_code == 200
    )
    wait(
        client,
        create(client, ai_case["run"], **llm_options(max_findings=2)).json()["id"],
    )
    assert (
        create(client, ai_case["run"], **llm_options(max_findings=3)).status_code == 429
    )
    assert fake.calls == 2
    assert (
        wait(client, create(client, ai_case["run"]).json()["id"])["status"]
        == "completed"
    )


@pytest.mark.parametrize(
    "settings",
    [
        {"ai_daily_token_limit": 1000},
        {
            "ai_daily_budget_usd": 0.000001,
            "ai_input_usd_per_million": 3,
            "ai_output_usd_per_million": 15,
        },
    ],
)
def test_budget_rejected_before_provider_call(client, ai_case, settings):
    fake = enable_fake(configured(**settings))
    assert create(client, ai_case["run"], **llm_options()).status_code == 429
    assert fake.calls == 0


def test_cooldown_and_day_quota(client, ai_case):
    settings = configured(ai_daily_call_limit=1)
    settings.ai_cooldown_seconds = 600
    fake = enable_fake(settings)
    wait(client, create(client, ai_case["run"], **llm_options()).json()["id"])
    assert (
        create(client, ai_case["run"], **llm_options(max_findings=2)).status_code == 429
    )
    assert fake.calls == 1


def test_background_job_cancel_and_project_guard(client, ai_case):
    class SlowProvider:
        async def analyze(self, evidence, maximum):
            await asyncio.sleep(30)

    enable_fake(provider=SlowProvider())
    response = create(client, ai_case["run"], **llm_options())
    assert response.status_code == 202
    identifier = response.json()["id"]
    assert client.get("/api/v1/health").status_code == 200
    assert create(client, ai_case["run"], max_findings=2).status_code == 409
    assert client.delete(f"/api/projects/{ai_case['project']}").status_code == 409
    cancelled = client.post(f"/api/v1/ai-analyses/{identifier}/cancel")
    assert cancelled.status_code == 202 and cancelled.json()["status"] == "cancelled"
    with ai_case["factory"]() as session:
        assert session.get(AIAnalysis, identifier).active_slot is None
    assert (
        wait(client, create(client, ai_case["run"]).json()["id"])["status"]
        == "completed"
    )


def test_provider_exception_never_leaks_and_failed_calls_use_quota(client, ai_case):
    class FailingProvider:
        async def analyze(self, evidence, maximum):
            raise RuntimeError(
                "fixture-private-key-123 /etc/config.env raw provider body"
            )

    enable_fake(provider=FailingProvider())
    for _ in range(2):
        result = wait(
            client, create(client, ai_case["run"], **llm_options()).json()["id"]
        )
        assert result["status"] == "failed"
        assert "fixture-private-key" not in json.dumps(
            result
        ) and "/etc/" not in json.dumps(result)
    assert create(client, ai_case["run"], **llm_options()).status_code == 429


def provider_body(evidence):
    return {
        "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": analyze_rules(evidence, 5).model_dump_json()}
        ],
        "usage": {"input_tokens": 20, "output_tokens": 30},
    }


def test_anthropic_wire_contract_schema_and_no_tools(client, ai_case):
    with ai_case["factory"]() as session:
        evidence = collect(session, ai_case["run"], "local", False)
    calls = []

    def handle(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "fixture-private-key-123"
        assert payload["system"].startswith(SYSTEM)
        assert "tools" not in payload and "thinking" not in payload
        assert "untrusted_evidence" in payload["messages"][0]["content"]
        assert "fixture-private-key" not in request.content.decode()
        assert payload["output_config"]["format"]["type"] == "json_schema"
        assert "maxLength" not in json.dumps(payload["output_config"])
        return httpx2.Response(200, json=provider_body(evidence))

    result = asyncio.run(
        AnthropicProvider(configured(), httpx2.MockTransport(handle)).analyze(
            evidence, 5
        )
    )
    assert result.input_tokens == 20 and len(calls) == 1


@pytest.mark.parametrize("status", [429, 503, 529])
def test_rate_limit_retries_are_bounded(client, ai_case, status, monkeypatch):
    calls = []

    async def no_sleep(*args):
        pass

    monkeypatch.setattr("app.services.ai_provider.asyncio.sleep", no_sleep)

    def handle(request):
        calls.append(request)
        return httpx2.Response(status, text="secret raw body")

    with pytest.raises(ProviderError) as error:
        asyncio.run(
            AnthropicProvider(configured(), httpx2.MockTransport(handle)).analyze({}, 5)
        )
    assert len(calls) == 2 and "secret" not in str(error.value)


@pytest.mark.parametrize(
    "body",
    [
        {"stop_reason": "max_tokens"},
        {"stop_reason": "end_turn", "content": [{"type": "tool_use"}]},
        {"stop_reason": "end_turn", "content": [{"type": "text", "text": "not json"}]},
        {"stop_reason": "end_turn", "content": None},
        None,
    ],
)
def test_malformed_provider_responses(body):
    with pytest.raises(ProviderError):
        asyncio.run(
            AnthropicProvider(
                configured(),
                httpx2.MockTransport(lambda r: httpx2.Response(200, json=body)),
            ).analyze({}, 5)
        )


def test_provider_redirect_oversize_and_timeout_are_never_followed():
    calls = []

    def redirect(request):
        calls.append(request)
        return httpx2.Response(302, headers={"Location": "http://169.254.169.254/"})

    with pytest.raises(ProviderError):
        asyncio.run(
            AnthropicProvider(configured(), httpx2.MockTransport(redirect)).analyze(
                {}, 5
            )
        )
    assert len(calls) == 1
    with pytest.raises(ProviderError):
        asyncio.run(
            AnthropicProvider(
                configured(),
                httpx2.MockTransport(
                    lambda r: httpx2.Response(200, content=b"x" * 128001)
                ),
            ).analyze({}, 5)
        )

    def timeout(request):
        raise httpx2.ReadTimeout("raw key must not escape")

    with pytest.raises(ProviderError, match="timeout_or_network"):
        asyncio.run(
            AnthropicProvider(configured(), httpx2.MockTransport(timeout)).analyze(
                {}, 5
            )
        )


def test_migration_preserves_phase4_data_and_recovery(database):
    _, factory, config = database
    _, run_id = seed(factory, CASES[:1])
    command.downgrade(config, "c39d87a4e620")
    with factory() as session:
        # At phase 4, phase-6 columns intentionally do not exist. Query the
        # historical columns explicitly rather than loading today's full mapper.
        assert (
            session.scalar(select(Run.id).where(Run.id == run_id)) == run_id
            and session.scalar(select(func.count()).select_from(Issue)) == 1
        )
    command.upgrade(config, "head")
    with factory.begin() as session:
        row = AIAnalysis(
            run_id=run_id,
            workspace_id="local",
            provider="rules",
            model="deterministic-v1",
            mode="rules",
            status="running",
            active_slot=1,
            prompt_version="intelligence-v1",
            context_hash="a" * 64,
            evidence_json={},
        )
        session.add(row)
        session.flush()
        identifier = row.id
    with TestClient(app) as client:
        recovered = client.get(f"/api/v1/ai-analyses/{identifier}").json()
        assert recovered["status"] == "failed"
    with factory() as session:
        assert session.get(AIAnalysis, identifier).active_slot is None
    command.check(config)


def test_project_deletion_cascades_ai_results(client, ai_case):
    identifier = create(client, ai_case["run"]).json()["id"]
    wait(client, identifier)
    assert client.delete(f"/api/projects/{ai_case['project']}").status_code == 204
    assert client.get(f"/api/v1/ai-analyses/{identifier}").status_code == 404
    with ai_case["factory"]() as session:
        assert session.get(AIAnalysis, identifier) is None


def test_budget_configuration_requires_prices():
    with pytest.raises(ValidationError):
        configured(ai_daily_budget_usd=1)


def test_separate_cooldown_before_quota_and_history_snapshot(client, ai_case):
    from datetime import timedelta

    settings = configured()
    settings.ai_cooldown_seconds = 600
    fake = enable_fake(settings)
    wait(client, create(client, ai_case["run"], **llm_options()).json()["id"])
    response = create(client, ai_case["run"], **llm_options(max_findings=2))
    assert response.status_code == 429 and response.headers["retry-after"] == "600"
    assert fake.calls == 1
    with ai_case["factory"].begin() as session:
        target = session.get(Run, ai_case["run"])
        previous = Run(
            project_id=target.project_id,
            target_url=target.target_url,
            created_at=target.created_at - timedelta(seconds=1),
            finished_at=target.created_at,
            status=RunStatus.COMPLETED,
        )
        session.add(previous)
        session.flush()
        session.add(
            Issue(
                run_id=previous.id,
                kind="http",
                severity=Severity.HIGH,
                title="Respuesta HTTP 404",
                description="La página devolvió HTTP 404.",
                affected_url=target.target_url,
            )
        )
    with ai_case["factory"]() as session:
        evidence = collect(session, ai_case["run"], "local", True)
        assert evidence["history"]["base_run_id"] == previous.id
        assert evidence["history"]["counts"]["PERSISTENT"] == 1
        assert collect(session, ai_case["run"], "local", False)["history"] is None


def test_cancel_before_background_task_starts_releases_slot(client, ai_case):
    from app.schemas.intelligence import AnalysisCreate
    from app.services.ai_manager import AIManager

    async def scenario():
        manager = AIManager(ai_case["factory"], Settings(_env_file=None))
        created, _ = await manager.submit(ai_case["run"], "local", AnalysisCreate())
        await manager.close()
        return created.id

    identifier = asyncio.run(scenario())
    with ai_case["factory"]() as session:
        row = session.get(AIAnalysis, identifier)
        assert row.status in {"cancelled", "completed"} and row.active_slot is None


def test_complete_long_urls_are_preserved_in_context_and_code(client, database):
    _, factory, _ = database
    _, run = seed(factory, CASES[:1])
    url = "http://blackbox-demo.invalid/" + "route/" * 140
    with factory.begin() as session:
        issue = session.scalar(select(Issue).where(Issue.run_id == run))
        issue.affected_url = url
    result = wait(client, create(client, run).json()["id"])
    assert result["status"] == "completed"
    assert result["evidence"]["issues"][0]["url"] == url
    assert url.split(".invalid", 1)[1] in result["result"]["suggested_tests"][0]["code"]


def test_missing_url_does_not_invent_a_test_path(client, database):
    _, factory, _ = database
    _, run = seed(factory, CASES[:1])
    with factory.begin() as session:
        session.scalar(
            select(Issue).where(Issue.run_id == run)
        ).affected_url = "file:///private"
    result = wait(client, create(client, run).json()["id"])
    assert result["status"] == "completed" and result["result"]["suggested_tests"] == []


def test_template_uses_compatible_cited_issue_url(client, ai_case):
    from app.services.ai_rules import render_tests

    with ai_case["factory"]() as session:
        evidence = collect(session, ai_case["run"], "local", False)
    result = analyze_rules(evidence, 8)
    js = next(issue for issue in evidence["issues"] if issue["type"] == "javascript")
    http = next(issue for issue in evidence["issues"] if issue["type"] == "http")
    js["url"], http["url"] = (
        "http://blackbox-demo.invalid/js-path",
        "http://blackbox-demo.invalid/http-path",
    )
    test = next(
        test for test in result.suggested_tests if test.template == "http_status"
    )
    test.evidence_ids = [js["id"], http["id"]]
    result = validate_result(result, evidence, 8, "")
    rendered = render_tests(result, evidence)
    code = next(
        test.code for test in rendered.suggested_tests if test.template == "http_status"
    )
    assert 'BASE_URL + "/http-path"' in code and 'BASE_URL + "/js-path"' not in code
