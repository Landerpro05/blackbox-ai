import socket
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import func, select, text

from app.core.database import build_engine, session_factory
from app.models import Issue, Project, Run, RunStatus, Severity


def payload(**changes):
    return {
        "name": "Mi aplicación",
        "description": "Aplicación propia",
        "base_url": "https://example.com",
        **changes,
    }


@pytest.mark.parametrize("prefix", ["/api/projects", "/api/v1/projects"])
def test_create_read_update_delete_at_both_prefixes(client, prefix):
    created = client.post(prefix, json=payload(name="  Mi aplicación  "))
    assert created.status_code == 201
    body = created.json()
    project_id = body["id"]
    assert created.headers["location"] == f"{prefix}/{project_id}"
    assert body["name"] == "Mi aplicación"
    assert body["description"] == "Aplicación propia"
    assert body["base_url"] == "https://example.com/"
    assert body["max_pages"] == 10
    assert body["created_at"].endswith("Z") and body["updated_at"].endswith("Z")
    assert "workspace_id" not in body
    assert client.get(f"{prefix}/{project_id}").json() == body
    listed = client.get(prefix).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == project_id
    changed = client.patch(
        f"{prefix}/{project_id}",
        json={
            "name": "Actualizado",
            "description": "",
            "base_url": "http://localhost:9000/app",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["name"] == "Actualizado"
    assert changed.json()["description"] == ""
    assert changed.json()["base_url"] == "http://localhost:9000/app"
    deleted = client.delete(f"{prefix}/{project_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(prefix).json()["total"] == 0
    assert client.get(f"{prefix}/{project_id}").status_code == 404


def test_default_description_and_empty_list(client):
    assert client.get("/api/projects").json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }
    assert (
        client.post(
            "/api/projects",
            json={"name": "Sin descripción", "base_url": "https://example.org"},
        ).json()["description"]
        == ""
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"name": " \t\n "},
        {"name": "x" * 121},
        {"name": None},
        {"name": 123},
        {"name": "one\ntwo"},
        {"base_url": ""},
        {"base_url": "not-a-url"},
        {"base_url": "example.com"},
        {"base_url": "https:example.com"},
        {"base_url": "javascript:alert(1)"},
        {"base_url": "file:///C:/Windows"},
        {"base_url": "ftp://example.com"},
        {"base_url": "https://"},
        {"base_url": "https://example.com:99999"},
        {"base_url": "https://exa mple.com"},
        {"base_url": "https://example.com/a\nb"},
        {"base_url": "https://example.com\\admin"},
        {"base_url": "https://user:secret@example.com"},
        {"base_url": "https://example.com/?token=secret"},
        {"base_url": "https://example.com/#secret"},
        {"base_url": "https://example.com/" + "a" * 2048},
        {"base_url": None},
        {"base_url": 123},
        {"description": "x" * 4001},
        {"description": None},
        {"workspace_id": "other"},
        {"id": str(uuid4())},
        {"max_pages": 50},
        {"created_at": "2020-01-01"},
    ],
)
def test_invalid_create_is_rejected_without_writing(client, changes):
    response = client.post("/api/projects", json=payload(**changes))
    assert response.status_code == 422
    assert client.get("/api/projects").json()["total"] == 0


def test_missing_required_fields_and_non_json_body(client):
    assert client.post("/api/projects", json={}).status_code == 422
    assert (
        client.post(
            "/api/projects",
            content='{"name":"X","base_url":"https://example.com"}',
            headers={"Content-Type": "text/plain"},
        ).status_code
        == 415  # Phase 7 rejects unsupported media before parsing authenticated writes.
    )


def test_validation_does_not_echo_secrets(client):
    secret = "do-not-echo-this-password"
    response = client.post(
        "/api/projects", json=payload(base_url=f"https://user:{secret}@example.com")
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert all(
        "input" not in error and "ctx" not in error
        for error in response.json()["detail"]
    )


def test_partial_update_preserves_other_fields_and_updates_time(client, database):
    _, factory, _ = database
    created = client.post("/api/projects", json=payload()).json()
    previous = datetime.now(UTC) - timedelta(days=1)
    with factory.begin() as session:
        project = session.get(Project, created["id"])
        project.created_at = previous
        project.updated_at = previous
    response = client.patch(
        f"/api/projects/{created['id']}", json={"description": "  Nueva descripción  "}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == created["name"]
    assert updated["base_url"] == created["base_url"]
    assert updated["description"] == "Nueva descripción"
    assert datetime.fromisoformat(updated["created_at"]) == previous
    assert datetime.fromisoformat(updated["updated_at"]) > previous


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"name": " "},
        {"base_url": "bad"},
        {"description": None},
        {"name": None},
        {"base_url": None},
        {"workspace_id": "other"},
    ],
)
def test_invalid_patch_does_not_change_project(client, changes):
    created = client.post("/api/projects", json=payload()).json()
    response = client.patch(f"/api/projects/{created['id']}", json=changes)
    assert response.status_code == 422
    assert client.get(f"/api/projects/{created['id']}").json() == created


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_unknown_and_malformed_identifiers(client, method):
    options = {"json": {"name": "Changed"}} if method == "patch" else {}
    assert (
        getattr(client, method)(f"/api/projects/{uuid4()}", **options).status_code
        == 404
    )
    assert (
        getattr(client, method)("/api/projects/not-a-uuid", **options).status_code
        == 422
    )


def test_list_is_paginated_bounded_and_sorted(client, database):
    _, factory, _ = database
    now = datetime.now(UTC)
    with factory.begin() as session:
        for offset in range(25):
            session.add(
                Project(
                    name=f"Project {offset}",
                    base_url="https://example.com",
                    created_at=now - timedelta(hours=offset),
                )
            )
    first = client.get("/api/projects?limit=12&offset=0").json()
    second = client.get("/api/projects?limit=12&offset=12").json()
    last = client.get("/api/projects?limit=12&offset=24").json()
    assert first["total"] == second["total"] == last["total"] == 25
    assert [row["name"] for row in first["items"]] == [
        f"Project {index}" for index in range(12)
    ]
    assert len(second["items"]) == 12 and len(last["items"]) == 1
    assert {row["id"] for row in first["items"]}.isdisjoint(
        row["id"] for row in second["items"]
    )
    assert client.get("/api/projects?offset=999").json()["items"] == []
    for query in ("limit=0", "limit=101", "offset=-1"):
        assert client.get(f"/api/projects?{query}").status_code == 422


def test_api_writes_survive_reopening_database(client, database):
    engine, _, _ = database
    created = client.post("/api/projects", json=payload()).json()
    client.patch(f"/api/projects/{created['id']}", json={"description": "Persistida"})
    other_engine = build_engine(str(engine.url))
    try:
        with session_factory(other_engine)() as session:
            stored = session.get(Project, created["id"])
            assert stored.description == "Persistida"
            assert stored.workspace_id == "local"
    finally:
        other_engine.dispose()


def test_orm_treats_sql_and_html_as_text(client):
    name = "'; DROP TABLE projects; -- <script>alert(1)</script>"
    created = client.post("/api/projects", json=payload(name=name))
    assert created.status_code == 201 and created.json()["name"] == name
    assert client.get("/api/projects").json()["total"] == 1


def test_no_target_network_access_on_crud(client, monkeypatch):
    def forbid_network(*_args, **_kwargs):
        raise AssertionError("Project CRUD must not resolve or connect to target URLs")

    monkeypatch.setattr(socket, "getaddrinfo", forbid_network)
    monkeypatch.setattr(socket, "create_connection", forbid_network)
    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    created = client.post(
        "/api/projects", json=payload(base_url="http://127.0.0.1:9999")
    ).json()
    path = f"/api/projects/{created['id']}"
    assert (
        client.patch(
            path, json={"base_url": "http://169.254.169.254/latest/meta-data"}
        ).status_code
        == 200
    )
    assert client.get(path).status_code == 200
    assert client.get("/api/projects").status_code == 200
    assert client.delete(path).status_code == 204


def test_workspace_scope_cannot_be_supplied_by_client(client, database):
    _, factory, _ = database
    with factory.begin() as session:
        foreign = Project(
            name="Other workspace", base_url="https://example.com", workspace_id="other"
        )
        session.add(foreign)
        session.flush()
        foreign_id = foreign.id
        run = Run(project_id=foreign_id, status=RunStatus.RUNNING)
        session.add(run)
        session.flush()
        session.add(
            Issue(
                run_id=run.id,
                kind="http",
                severity=Severity.CRITICAL,
                description="Hidden",
                affected_url="https://example.com",
            )
        )
    assert (
        client.get("/api/projects", headers={"X-Workspace-Id": "other"}).status_code
        == 404  # Phase 7 validates membership rather than ignoring a supplied ID.
    )
    for method in ("get", "patch", "delete"):
        options = {"json": {"name": "Attack"}} if method == "patch" else {}
        assert (
            getattr(client, method)(
                f"/api/projects/{foreign_id}", **options
            ).status_code
            == 404
        )
    dashboard = client.get("/api/v1/dashboard").json()
    assert all(value == 0 for value in dashboard["metrics"].values())
    assert dashboard["recent_runs"] == dashboard["projects"] == []
    assert all(day["runs"] == day["issues"] == 0 for day in dashboard["trend"])


def test_dashboard_reflects_crud_and_cascade_deletion(client, database):
    _, factory, _ = database
    created = client.post("/api/projects", json=payload()).json()
    assert client.get("/api/v1/dashboard").json()["metrics"]["projects"] == 1
    client.patch(f"/api/projects/{created['id']}", json={"name": "Nuevo nombre"})
    assert (
        client.get("/api/v1/dashboard").json()["projects"][0]["name"] == "Nuevo nombre"
    )
    with factory.begin() as session:
        run = Run(project_id=created["id"], status=RunStatus.COMPLETED)
        session.add(run)
        session.flush()
        session.add(
            Issue(
                run_id=run.id,
                kind="http",
                severity=Severity.CRITICAL,
                description="Error",
                affected_url="https://example.com",
            )
        )
    assert client.delete(f"/api/projects/{created['id']}").status_code == 204
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 0
        assert session.scalar(select(func.count()).select_from(Issue)) == 0
    assert all(
        value == 0
        for value in client.get("/api/v1/dashboard").json()["metrics"].values()
    )


def test_project_database_failures_return_safe_503(client, database):
    engine, _, _ = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE projects"))
    response = client.get("/api/projects")
    assert response.status_code == 503
    assert "SELECT" not in response.text and "sqlite" not in response.text.lower()
    response = client.post("/api/projects", json=payload())
    assert response.status_code == 503


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_cors_supports_mutations_only_from_allowed_origins(client, method):
    for origin, expected in [
        ("http://127.0.0.1:5173", 200),
        ("https://untrusted.example", 400),
    ]:
        response = client.options(
            "/api/projects",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert response.status_code == expected


def test_phase_two_migration_preserves_phase_one_rows(database):
    engine, _, config = database
    command.downgrade(config, "8d56efc7b5b4")
    project_id, run_id, issue_id = str(uuid4()), str(uuid4()), str(uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects (id,name,base_url,created_at,updated_at) VALUES (:id,'Existing','https://example.com',:now,:now)"
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
    with session_factory(engine)() as session:
        project = session.get(Project, project_id)
        assert (
            project.name == "Existing"
            and project.description == ""
            and project.workspace_id == "local"
        )
        assert session.get(Run, run_id).project_id == project_id
        assert session.get(Issue, issue_id).run_id == run_id
