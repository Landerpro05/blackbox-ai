import json
import os
import subprocess
import sys

import pytest
from app.core.config import BACKEND_ROOT
from app.models import Project, SuiteCase, TestEnvironment, TestSuite
from app.schemas.runs import RunLimits
from app.testing.policy import DEMO_ORIGIN, DEMO_URL


@pytest.mark.parametrize(
    "url",
    [
        "http://127.1:3000",
        "http://2130706433:3000",
        "http://0177.0.0.1:3000",
        "http://127.0.0.1:03000",
    ],
)
def test_environment_rejects_alternative_spellings_before_url_normalization(
    client, url
):
    project = client.post(
        "/api/projects", json={"name": "URL literal", "base_url": DEMO_URL}
    ).json()
    endpoint = f"/api/v1/projects/{project['id']}/environments"
    payload = {"name": "Local", "kind": "local", "base_url": url}
    assert client.post(endpoint, json=payload).status_code == 422
    payload["base_url"] = "http://127.0.0.1:3000"
    environment = client.post(endpoint, json=payload).json()
    assert (
        client.patch(
            f"/api/v1/environments/{environment['id']}", json={"base_url": url}
        ).status_code
        == 422
    )


@pytest.mark.browser
@pytest.mark.parametrize("expected", [1, 2, 3])
def test_cli_runs_persisted_suite_and_distinguishes_fail_error_timeout(
    database, tmp_path, expected
):
    _, factory, _ = database
    limits = RunLimits(navigation_timeout_seconds=1 if expected == 2 else 15)
    with factory.begin() as session:
        project = Project(name="CLI persistida", base_url=DEMO_URL)
        session.add(project)
        session.flush()
        environment = TestEnvironment(
            project_id=project.id,
            workspace_id="local",
            name="Demo",
            kind="demo",
            base_url=DEMO_URL,
            authorized_origin=DEMO_ORIGIN,
            limits=limits.model_dump(),
        )
        suite = TestSuite(
            project_id=project.id,
            workspace_id="local",
            name="Suite CLI",
            description="",
        )
        session.add_all([environment, suite])
        session.flush()
        definition = (
            {"type": "title", "path": "/about", "expected_title": "Incorrecto"}
            if expected == 1
            else {
                "type": "http_status",
                "path": "/slow",
                "minimum": 200,
                "maximum": 200,
            }
        )
        for position in range(2 if expected == 3 else 1):
            session.add(
                SuiteCase(
                    suite_id=suite.id,
                    name=f"Caso {position}",
                    position=position,
                    enabled=True,
                    definition=definition,
                )
            )
        identifiers = project.id, environment.id, suite.id
    runtime = {
        **os.environ,
        "BLACKBOX_DEMO_TESTING_ENABLED": "true",
        "BLACKBOX_LOCAL_LAB_ENABLED": "false",
        "BLACKBOX_AI_PROVIDER": "disabled",
        "BLACKBOX_AI_API_KEY": "",
        "BLACKBOX_EVIDENCE_DIR": str(tmp_path / "evidence"),
    }
    browsers = BACKEND_ROOT.parent / ".tools/browsers"
    if browsers.is_dir():
        runtime.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    output = tmp_path / "suite-results.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "test",
            "--standalone",
            "--project",
            identifiers[0],
            "--environment",
            identifiers[1],
            "--suite",
            identifiers[2],
            "--origin",
            DEMO_ORIGIN,
            "--authorize",
            "--timeout",
            "5" if expected == 3 else "30",
            "--json",
            str(output),
        ],
        cwd=BACKEND_ROOT,
        env=runtime,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    assert result.returncode == expected, result.stderr
    payload = json.loads(output.read_text("utf-8"))
    if expected == 1:
        assert (
            payload["counts"]["fail"] == 1 and payload["run"]["status"] == "completed"
        )
    elif expected == 2:
        assert payload["counts"]["error"] == 1 and payload["run"]["status"] == "failed"
    else:
        assert payload["run"]["status"] == "cancelled"
        assert payload["counts"]["skipped"] >= 1
