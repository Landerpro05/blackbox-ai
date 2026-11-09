from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core.database import build_engine, session_factory
from app.models import Issue, Project, Run, RunStatus, Severity


def test_health_checks_migrated_database(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "blackbox-ai",
        "version": "0.1.0",
        "environment": "test",
        "database": "connected",
    }
    assert response.headers["cache-control"] == "no-store"


def test_empty_dashboard_has_real_zero_counts(client):
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"] == {
        "projects": 0,
        "runs": 0,
        "issues": 0,
        "critical_issues": 0,
        "active_runs": 0,
    }
    assert body["recent_runs"] == body["projects"] == []
    assert len(body["trend"]) == 14
    assert all(day["runs"] == day["issues"] == 0 for day in body["trend"])
    assert body["generated_at"].endswith("Z")


def test_dashboard_aggregates_persisted_rows_without_join_inflation(client, database):
    _, factory, _ = database
    now = datetime.now(UTC)
    with factory.begin() as session:
        first = Project(name="Own application", base_url="https://example.com")
        second = Project(name="Second application", base_url="https://example.org")
        session.add_all([first, second])
        session.flush()
        recent = Run(
            project_id=first.id,
            status=RunStatus.COMPLETED,
            pages_visited=2,
            created_at=now,
        )
        old = Run(
            project_id=first.id,
            status=RunStatus.FAILED,
            created_at=now - timedelta(days=20),
        )
        active = Run(
            project_id=second.id,
            status=RunStatus.QUEUED,
            created_at=now - timedelta(minutes=1),
        )
        session.add_all([recent, old, active])
        session.flush()
        session.add_all(
            [
                Issue(
                    run_id=recent.id,
                    kind="http",
                    severity=Severity.CRITICAL,
                    description="HTTP 500",
                    affected_url="https://example.com",
                    created_at=now,
                ),
                Issue(
                    run_id=recent.id,
                    kind="javascript",
                    severity=Severity.HIGH,
                    description="JS error",
                    affected_url="https://example.com",
                    created_at=now,
                ),
                Issue(
                    run_id=old.id,
                    kind="http",
                    severity=Severity.LOW,
                    description="HTTP 404",
                    affected_url="https://example.com/old",
                    created_at=now - timedelta(days=20),
                ),
            ]
        )
    body = client.get("/api/v1/dashboard").json()
    assert body["metrics"] == {
        "projects": 2,
        "runs": 3,
        "issues": 3,
        "critical_issues": 1,
        "active_runs": 1,
    }
    assert body["recent_runs"][0]["issue_count"] == 2
    assert body["recent_runs"][0]["project_name"] == "Own application"
    assert body["recent_runs"][0]["created_at"].endswith("Z")
    assert sum(point["runs"] for point in body["trend"]) == 2
    assert sum(point["issues"] for point in body["trend"]) == 2
    assert sorted(project["run_count"] for project in body["projects"]) == [1, 2]


def test_history_is_bounded_and_sorted(client, database):
    _, factory, _ = database
    with factory.begin() as session:
        project = Project(name="History", base_url="https://example.com")
        session.add(project)
        session.flush()
        for offset in range(12):
            session.add(
                Run(
                    project_id=project.id,
                    created_at=datetime.now(UTC) - timedelta(hours=offset),
                )
            )
    rows = client.get("/api/v1/dashboard").json()["recent_runs"]
    assert len(rows) == 8
    assert [row["created_at"] for row in rows] == sorted(
        (row["created_at"] for row in rows), reverse=True
    )


def test_data_survives_a_new_database_connection(database):
    engine, factory, _ = database
    with factory.begin() as session:
        session.add(Project(name="Persistent", base_url="https://example.com"))
    another_engine = build_engine(str(engine.url))
    try:
        with session_factory(another_engine)() as session:
            assert session.scalar(select(Project.name)) == "Persistent"
    finally:
        another_engine.dispose()


def test_sqlite_enforces_foreign_keys_and_limits(database):
    _, factory, _ = database
    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(Run(project_id="missing-project"))
    with pytest.raises(IntegrityError), factory.begin() as session:
        session.add(
            Project(name="Invalid", base_url="https://example.com", max_pages=1000)
        )


def test_project_deletion_cascades_in_database(database):
    _, factory, _ = database
    with factory.begin() as session:
        project = Project(name="Cascade", base_url="https://example.com")
        session.add(project)
        session.flush()
        run = Run(project_id=project.id)
        session.add(run)
        session.flush()
        session.add(
            Issue(
                run_id=run.id,
                kind="http",
                severity=Severity.HIGH,
                description="Error",
                affected_url="https://example.com",
            )
        )
    with factory.begin() as session:
        session.execute(delete(Project))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 0
        assert session.scalar(select(func.count()).select_from(Issue)) == 0


def test_migration_round_trip_and_metadata_match(database):
    engine, _, config = database
    command.check(config)
    command.downgrade(config, "base")
    assert "projects" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert {"projects", "runs", "issues", "alembic_version"} <= set(
        inspect(engine).get_table_names()
    )


def test_missing_schema_returns_503_without_sql_details(client, database):
    engine, _, _ = database
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE issues"))
        connection.execute(text("DROP TABLE runs"))
        connection.execute(text("DROP TABLE projects"))
    assert client.get("/api/v1/health").status_code == 503
    response = client.get("/api/v1/dashboard")
    assert response.status_code == 503
    assert "SELECT" not in response.text


def test_cors_allows_development_origin_only(client):
    allowed = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    rejected = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
