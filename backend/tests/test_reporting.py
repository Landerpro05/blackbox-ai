import csv
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from io import BytesIO, StringIO
from uuid import uuid4

import pytest
from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.config import get_settings
from app.main import app
from app.models import Issue, Project, Run, RunStatus, Severity, TestPage
from app.services import reporting
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select


@pytest.fixture
def history(client, database, tmp_path, monkeypatch):
    monkeypatch.setenv("BLACKBOX_EVIDENCE_DIR", str(tmp_path / "evidence"))
    get_settings.cache_clear()
    _, factory, _ = database
    with factory.begin() as session:
        project = Project(
            name="Proyecto de calidad", base_url="http://blackbox-demo.invalid/"
        )
        session.add(project)
        session.flush()
        now = datetime.now(UTC)
        runs = []
        pages = []
        for index in range(2):
            run = Run(
                project_id=project.id,
                status=RunStatus.COMPLETED,
                created_at=now + timedelta(seconds=index),
                finished_at=now + timedelta(seconds=index + 1),
                target_url=project.base_url,
                duration_ms=1234,
                pages_visited=1,
                issues_found=2,
            )
            session.add(run)
            session.flush()
            page = TestPage(
                test_run_id=run.id,
                url=project.base_url,
                status_code=200,
                load_time_ms=100 + index * 200,
            )
            session.add(page)
            session.flush()
            page.screenshot_path = f"{page.id}.png"
            path = reporting.EvidenceStore(get_settings().evidence_dir).path(
                run.id, page.id
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (640, 360), "#15213a").save(path)
            for message in ("Persistente", "Anterior" if index == 0 else "Nuevo"):
                session.add(
                    Issue(
                        run_id=run.id,
                        kind="javascript",
                        severity=Severity.HIGH,
                        title=message,
                        description=f"Error {message}",
                        affected_url=project.base_url,
                        evidence_path=page.screenshot_path,
                    )
                )
            runs.append(run.id)
            pages.append(page.id)
        return {
            "project": project.id,
            "base": runs[0],
            "target": runs[1],
            "pages": pages,
            "factory": factory,
        }


def route(history, suffix):
    return f"/api/v1/runs/{history['target']}/{suffix}"


@pytest.mark.parametrize(
    "suffix,media",
    [
        ("report/html", "text/html"),
        ("report/pdf", "application/pdf"),
        ("export/json", "application/json"),
        ("export/csv", "text/csv"),
    ],
)
def test_downloads_real_persisted_data(client, history, suffix, media):
    response = client.get(route(history, suffix))
    assert response.status_code == 200, response.text[:300]
    assert response.headers["content-type"].startswith(media)
    assert response.headers["content-disposition"].startswith(
        f'attachment; filename="blackbox-{history["target"]}.'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert len(response.content) < reporting.MAX_RESPONSE_BYTES
    if suffix.endswith("pdf"):
        reader = PdfReader(BytesIO(response.content))
        assert len(reader.pages) >= 3
        text = " ".join(p.extract_text() for p in reader.pages)
        assert "BLACKBOX AI" in text and "Nuevo" in text and "Página 1" in text
        assert not reader.trailer["/Root"].get("/OpenAction")
        assert not any(page.get("/Annots") for page in reader.pages)
        output = get_settings().evidence_dir.parents[0] / "verified.pdf"
        output.write_bytes(response.content)
    elif suffix.endswith("json"):
        data = response.json()
        assert data["summary"]["issues"] == 2
        assert data["summary"]["average_navigation_ms"] == 300
        assert data["summary"]["javascript_errors"] == 2
        assert data["issues"][0]["reproduction_steps"] is None
        assert "evidence_path" not in response.text
    elif suffix.endswith("csv"):
        rows = list(csv.DictReader(StringIO(response.content.decode("utf-8-sig"))))
        assert len(rows) == 2
        assert rows[0]["run_id"] == history["target"]
    else:

        class Inspector(HTMLParser):
            def handle_starttag(self, tag, attrs):
                assert tag not in {"script", "iframe", "object", "embed", "link"}
                for key, value in attrs:
                    assert not key.startswith("on")
                    if key in {"src", "href"}:
                        assert value.startswith("data:image/png;base64,")

        Inspector().feed(response.text)
        assert "data:image/png;base64," in response.text
        assert "default-src" in response.text


@pytest.mark.parametrize(
    "suffix", ["report", "report/html", "report/pdf", "export/json", "export/csv"]
)
def test_workspace_and_missing_downloads(client, history, suffix):
    app.dependency_overrides[get_workspace_access] = lambda: WorkspaceAccess("other")
    try:
        assert client.get(route(history, suffix)).status_code == 404
    finally:
        app.dependency_overrides.clear()
    assert client.get(f"/api/v1/runs/{uuid4()}/{suffix}").status_code == 404
    assert client.get(f"/api/v1/runs/not-a-uuid/{suffix}").status_code == 422


def test_all_exports_escape_and_redact_historical_secrets(client, history):
    payload = (
        '<script>alert(1)</script><img src="https://evil.invalid/" onerror="alert(2)">'
    )
    with history["factory"].begin() as session:
        issue = session.scalar(select(Issue).where(Issue.run_id == history["target"]))
        issue.title = payload
        issue.description = (
            payload
            + ' token="very private credential" password=hidden user@example.com C:\\Users\\private\\config.env https://u:p@example.com/?key=hidden'
        )
        issue.reproduction_steps = '=HYPERLINK("https://evil.invalid")'
        issue.affected_url = (
            "https://user:secret@example.com/a?token=supersecret#private"
        )
    for suffix in ("report/html", "export/json", "export/csv"):
        response = client.get(route(history, suffix))
        text = response.content.decode("utf-8-sig")
        assert all(
            secret not in text
            for secret in (
                "very private credential",
                "password=hidden",
                "user@example.com",
                "supersecret",
                "user:secret",
                "config.env",
            )
        )
        if suffix.endswith("html"):
            assert payload not in text
            assert "&lt;script&gt;" in text
        elif suffix.endswith("csv"):
            rows = list(csv.DictReader(StringIO(text)))
            assert next(row for row in rows if row["id"] == issue.id)[
                "reproduction_steps"
            ].startswith("'=")
    pdf = PdfReader(BytesIO(client.get(route(history, "report/pdf")).content))
    assert "very private credential" not in " ".join(
        p.extract_text() for p in pdf.pages
    )


def test_evidence_cannot_escape_run_or_directory(client, history, tmp_path):
    with history["factory"].begin() as session:
        page = session.get(TestPage, history["pages"][1])
        page.screenshot_path = f"{history['pages'][0]}.png"
        issue = session.scalar(select(Issue).where(Issue.run_id == history["target"]))
        issue.evidence_path = "../../secrets.png"
    data = client.get(route(history, "export/json")).json()
    assert all(not page["evidence_available"] for page in data["pages"])
    assert all(issue["evidence_page_id"] is None for issue in data["issues"])
    assert "data:image" not in client.get(route(history, "report/html")).text
    # A canonical filename also cannot resolve a symlink outside the evidence root.
    store = reporting.EvidenceStore(get_settings().evidence_dir)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (store.root / str(uuid4())).symlink_to(outside, target_is_directory=True)
    except OSError:
        return  # Windows may disallow symlinks without developer mode.
    link = next(p for p in store.root.iterdir() if p.is_symlink())
    with pytest.raises(ValueError):
        store.path(link.name, str(uuid4()))


def test_evidence_corrupt_and_oversized_files_are_omitted(client, history):
    path = reporting.EvidenceStore(get_settings().evidence_dir).path(
        history["target"], history["pages"][1]
    )
    for content in (b"not a PNG", b"x" * (reporting.MAX_IMAGE_BYTES + 1)):
        path.write_bytes(content)
        text = client.get(route(history, "report/html")).text
        assert "data:image/png" not in text
        assert "Omitidas o no disponibles: 1" in text


def test_evidence_option_and_count_budget(client, history):
    with history["factory"].begin() as session:
        original = session.get(TestPage, history["pages"][1])
        for _ in range(5):
            page = TestPage(
                test_run_id=history["target"],
                url=original.url,
                status_code=200,
                load_time_ms=0,
            )
            session.add(page)
            session.flush()
            page.screenshot_path = f"{page.id}.png"
            path = reporting.EvidenceStore(get_settings().evidence_dir).path(
                history["target"], page.id
            )
            Image.new("RGB", (10, 10)).save(path)
    html = client.get(route(history, "report/html")).text
    assert html.count("data:image/png;base64,") == reporting.MAX_IMAGES
    assert "Omitidas o no disponibles: 2" in html
    assert (
        "data:image/png"
        not in client.get(route(history, "report/html?include_evidence=false")).text
    )


def compare_url(history):
    return f"/api/v1/projects/{history['project']}/compare?base_run_id={history['base']}&target_run_id={history['target']}"


def test_comparison_new_resolved_persistent_is_read_only(client, history):
    with history["factory"]() as session:
        before = [
            (i.id, i.status, i.description) for i in session.scalars(select(Issue))
        ]
    data = client.get(compare_url(history)).json()
    assert data["counts"] == {
        "NEW": 1,
        "RESOLVED": 1,
        "PERSISTENT": 1,
        "UNCONFIRMED": 0,
    }
    assert data["partial"] is False
    assert len({item["fingerprint"] for item in data["items"]}) == 3
    with history["factory"]() as session:
        assert before == [
            (i.id, i.status, i.description) for i in session.scalars(select(Issue))
        ]


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.CANCELLED])
@pytest.mark.parametrize("which", ["base", "target"])
def test_partial_runs_never_claim_resolution(client, history, status, which):
    with history["factory"].begin() as session:
        session.get(Run, history[which]).status = status
    data = client.get(compare_url(history)).json()
    assert data["counts"]["RESOLVED"] == 0
    assert data["counts"]["UNCONFIRMED"] == 1
    assert data["partial"] is True


def test_missing_page_or_different_limits_do_not_prove_resolution(client, history):
    with history["factory"].begin() as session:
        session.get(
            TestPage, history["pages"][1]
        ).url = "http://blackbox-demo.invalid/other"
    assert client.get(compare_url(history)).json()["counts"]["UNCONFIRMED"] == 1
    with history["factory"].begin() as session:
        session.get(TestPage, history["pages"][1]).url = "http://blackbox-demo.invalid/"
        session.get(Run, history["target"]).limits = {"max_pages": 1}
    assert client.get(compare_url(history)).json()["counts"]["RESOLVED"] == 0


def test_active_and_invalid_comparison(client, history):
    assert (
        client.get(
            compare_url(history).replace(history["base"], history["target"])
        ).status_code
        == 422
    )
    assert (
        client.get(
            compare_url(history).replace(history["project"], str(uuid4()))
        ).status_code
        == 404
    )
    with history["factory"].begin() as session:
        session.get(Run, history["target"]).status = RunStatus.RUNNING
    assert client.get(compare_url(history)).status_code == 409
    assert client.get(route(history, "export/json")).status_code == 409


def test_fingerprint_ignores_ids_dates_and_durations_preserves_http_status():
    first = {
        "type": "http",
        "url": "http://EXAMPLE.com:80/a",
        "title": "HTTP 404",
        "description": "Request 123ms at 2026-11-09T12:00:00Z " + str(uuid4()),
    }
    other = {
        **first,
        "url": "http://example.com/a",
        "description": "Request 456ms at 2026-11-10T14:00:00Z " + str(uuid4()),
    }
    assert reporting.fingerprint(first) == reporting.fingerprint(other)
    assert reporting.fingerprint(first) != reporting.fingerprint(
        {**first, "title": "HTTP 500"}
    )


def test_analytics_aggregates_and_paginates(client, history):
    response = client.get(
        f"/api/v1/projects/{history['project']}/analytics?limit=1&offset=1"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] == 2 and data["total_issues"] == 4
    assert data["by_severity"]["high"] == 4
    assert data["by_type"] == [{"type": "javascript", "count": 4}]
    assert data["average_navigation_ms"] == 200
    assert len(data["items"]) == 1 and data["items"][0]["id"] == history["base"]
    assert data["regression"]["counts"]["NEW"] == 1
    assert (
        client.get(
            f"/api/v1/projects/{history['project']}/analytics?limit=51"
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/projects/{history['project']}/analytics?offset=-1"
        ).status_code
        == 422
    )


def test_empty_analytics_and_cross_workspace_access(client, history):
    empty = client.post(
        "/api/projects", json={"name": "Vacío", "base_url": "https://example.com/"}
    ).json()["id"]
    data = client.get(f"/api/v1/projects/{empty}/analytics").json()
    assert data["total_runs"] == data["total_issues"] == 0
    assert (
        data["average_navigation_ms"] is None
        and data["regression"] is None
        and data["items"] == []
    )
    app.dependency_overrides[get_workspace_access] = lambda: WorkspaceAccess("other")
    try:
        assert client.get(compare_url(history)).status_code == 404
        assert (
            client.get(f"/api/v1/projects/{history['project']}/analytics").status_code
            == 404
        )
    finally:
        app.dependency_overrides.clear()


def test_report_details_are_bounded_and_totals_are_not_truncated(
    client, history, monkeypatch
):
    with history["factory"].begin() as session:
        session.add_all(
            [
                Issue(
                    run_id=history["target"],
                    kind="http",
                    severity=Severity.MEDIUM,
                    title="HTTP 404",
                    description="Error",
                    affected_url="http://blackbox-demo.invalid/",
                )
                for _ in range(205)
            ]
        )
    data = client.get(route(history, "export/json")).json()
    assert len(data["issues"]) == 200
    assert data["summary"]["issues"] == 207 and data["omitted"]["issues"] == 7
    assert client.get(compare_url(history)).json()["counts"]["RESOLVED"] == 0
    monkeypatch.setattr(reporting, "MAX_RESPONSE_BYTES", 100)
    assert client.get(route(history, "export/json")).status_code == 413


@pytest.mark.parametrize(
    "cell", ["=1+1", "+SUM(1)", "-1+2", "@SUM(1)", "  =1", "\tvalue", "\n=1"]
)
def test_csv_formula_neutralization(cell):
    report = {
        "run": {"id": str(uuid4()), "status": "completed"},
        "summary": {"issues": 1},
        "omitted": {"issues": 0},
        "issues": [{"title": cell}],
    }
    rows = list(
        csv.DictReader(StringIO(reporting.csv_report(report).decode("utf-8-sig")))
    )
    assert rows[0]["title"].startswith("'")


def test_render_concurrency_rejects_without_queueing_and_preserves_scope(
    client, history
):
    from app.api.reporting import _render_slot

    assert _render_slot.acquire(blocking=False)
    try:
        assert client.get(route(history, "report/pdf")).status_code == 409
        assert client.get(route(history, "report/html")).status_code == 409
        assert client.get(route(history, "export/json")).status_code == 200
        app.dependency_overrides[get_workspace_access] = lambda: WorkspaceAccess(
            "other"
        )
        assert client.get(route(history, "report/pdf")).status_code == 404
    finally:
        app.dependency_overrides.clear()
        _render_slot.release()
    assert client.get(route(history, "report/pdf")).status_code == 200


def test_image_byte_budget_and_page_limit(client, history, monkeypatch):
    monkeypatch.setattr(reporting, "MAX_TOTAL_IMAGE_BYTES", 1)
    assert "data:image/png" not in client.get(route(history, "report/html")).text
    with history["factory"].begin() as session:
        session.add_all(
            [
                TestPage(
                    test_run_id=history["target"],
                    url=f"http://blackbox-demo.invalid/{i}",
                    status_code=200,
                    load_time_ms=1,
                )
                for i in range(24)
            ]
        )
    data = client.get(route(history, "export/json")).json()
    assert len(data["pages"]) == 20 and data["summary"]["pages"] == 25
    assert data["omitted"]["pages"] == 5
    assert client.get(compare_url(history)).json()["counts"]["RESOLVED"] == 0


def test_metrics_survive_type_group_limit(client, history):
    with history["factory"].begin() as session:
        for index in range(51):
            session.add_all(
                [
                    Issue(
                        run_id=history["target"],
                        kind=f"custom_{index}",
                        severity=Severity.LOW,
                        title="Aviso",
                        description="Aviso",
                        affected_url="http://blackbox-demo.invalid/",
                    )
                    for _ in range(2)
                ]
            )
        session.add(
            Issue(
                run_id=history["target"],
                kind="http",
                severity=Severity.HIGH,
                title="HTTP 500",
                description="Error HTTP",
                affected_url="http://blackbox-demo.invalid/",
            )
        )
    data = client.get(route(history, "export/json")).json()
    assert len(data["summary"]["by_type"]) == 50
    assert data["summary"]["http_errors"] == 1
    assert data["summary"]["issues"] == 105


def test_foreign_project_comparison_and_inconsistent_workspace(client, history):
    other = client.post(
        "/api/projects", json={"name": "Otro", "base_url": "https://example.com/"}
    ).json()["id"]
    with history["factory"].begin() as session:
        run = session.get(Run, history["target"])
        run.project_id = other
    assert client.get(compare_url(history)).status_code == 404
    with history["factory"].begin() as session:
        run = session.get(Run, history["target"])
        run.project_id = history["project"]
        run.workspace_id = "other"
    assert client.get(route(history, "export/json")).status_code == 404
    data = client.get(f"/api/v1/projects/{history['project']}/analytics").json()
    assert data["total_runs"] == 1 and data["total_issues"] == 2


def test_duplicate_fingerprints_are_grouped(client, history):
    with history["factory"].begin() as session:
        issue = session.scalar(
            select(Issue).where(
                Issue.run_id == history["target"], Issue.title == "Persistente"
            )
        )
        session.add(
            Issue(
                run_id=issue.run_id,
                kind=issue.kind,
                severity=Severity.CRITICAL,
                title=issue.title,
                description=issue.description,
                affected_url=issue.affected_url,
            )
        )
    data = client.get(compare_url(history)).json()
    assert data["counts"]["PERSISTENT"] == 1


def test_safe_urls_keep_distinct_http_paths_and_hide_file_paths():
    assert reporting.safe_url("http://example.com/a") == "http://example.com/a"
    assert reporting.safe_url("http://example.com/b") == "http://example.com/b"
    assert reporting.safe_url("file:///C:/Users/private/config.env") == "[URL omitida]"
    assert (
        reporting.clean("Error C:\\Users\\private\\config.env")
        == "Error [ruta omitida]"
    )


def test_empty_csv_keeps_zero_totals_and_pdf_handles_unicode(client, history):
    with history["factory"].begin() as session:
        for issue in session.scalars(
            select(Issue).where(Issue.run_id == history["target"])
        ):
            session.delete(issue)
        session.get(Project, history["project"]).name = "Proyecto áéñ 漢字 🧪"
    response = client.get(route(history, "export/csv"))
    rows = list(csv.DictReader(StringIO(response.content.decode("utf-8-sig"))))
    assert (
        len(rows) == 1
        and rows[0]["total_issues"] == "0"
        and rows[0]["omitted_issues"] == "0"
    )
    pdf = client.get(route(history, "report/pdf"))
    assert pdf.status_code == 200
    text = " ".join(
        page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages
    )
    assert "Proyecto áéñ" in text and "No se registraron incidencias" in text
