import time

import pytest
from app.models.security import AuditEvent
from app.testing.policy import DEMO_URL
from sqlalchemy import select
from test_engine import demo_client as demo_client  # noqa: PLC0414 — explicit pytest fixture re-export


@pytest.mark.browser
def test_real_run_start_and_cancel_are_audited_with_actor(demo_client, database):
    client = demo_client
    actor = client.get("/api/v1/auth/session").json()["user"]["id"]
    project = client.post(
        "/api/projects",
        json={"name": "Audit engine", "base_url": DEMO_URL.rstrip("/") + "/slow"},
    ).json()
    response = client.post(
        f"/api/v1/projects/{project['id']}/runs",
        json={"authorize_demo": True, "limits": {"max_pages": 1}},
    )
    assert response.status_code == 202
    identifier = response.json()["id"]
    assert client.post(f"/api/v1/runs/{identifier}/cancel").status_code == 202
    for _ in range(500):
        row = client.get(f"/api/v1/runs/{identifier}").json()
        if row["status"] not in {"running", "pending"}:
            break
        time.sleep(0.03)
    assert row["status"] == "cancelled"
    with database[1]() as session:
        events = list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.resource_id == identifier)
            )
        )
        assert {"run.started", "run.cancel_requested"} <= {
            row.event_type for row in events
        }
        assert all(
            row.user_id == actor and row.workspace_id == "local" for row in events
        )
