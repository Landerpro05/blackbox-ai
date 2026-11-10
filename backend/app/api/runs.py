from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.database import get_session
from app.models import Issue, Project, Run, TestPage
from app.repositories.runs import (
    RunNotFound,
    scoped_run,
    run_response,
    issue_response,
    page_response,
)
from app.schemas.runs import (
    RunCreate,
    RunLimits,
    RunResponse,
    IssueResponse,
    PageResponse,
)
from app.services.run_manager import RunManager
from app.testing.policy import DEMO_URL
from app.services.security import audit_request

router = APIRouter(prefix="/api/v1", tags=["testing"])
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]
Database = Annotated[Session, Depends(get_session)]


def manager(request: Request) -> RunManager:
    return request.app.state.run_manager


Manager = Annotated[RunManager, Depends(manager)]


@router.get("/testing/capabilities")
def capabilities(service: Manager) -> dict:
    return {
        "mode": "controlled_demo",
        "demo_enabled": service.settings.demo_testing_enabled,
        "remote_enabled": False,
        "demo_url": DEMO_URL,
        "defaults": RunLimits().model_dump(),
        "maximums": {
            "max_pages": 20,
            "max_depth": 3,
            "navigation_timeout_seconds": 30,
            "timeout_seconds": 180,
            "max_requests": 200,
        },
    }


@router.post("/projects/{project_id}/runs", response_model=RunResponse, status_code=202)
async def start_run(
    project_id: UUID,
    data: RunCreate,
    access: Access,
    service: Manager,
    request: Request,
) -> RunResponse:
    result = await service.submit(str(project_id), access.workspace_id, data)
    audit_request(request, "run.started", result.id)
    return result


@router.get("/projects/{project_id}/runs")
def project_runs(
    project_id: UUID,
    access: Access,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    project = session.scalar(
        select(Project.id).where(
            Project.id == str(project_id), Project.workspace_id == access.workspace_id
        )
    )
    if project is None:
        raise RunNotFound()
    scope = (Run.project_id == str(project_id), Run.workspace_id == access.workspace_id)
    total = session.scalar(select(func.count()).select_from(Run).where(*scope)) or 0
    rows = session.scalars(
        select(Run)
        .where(*scope)
        .order_by(Run.created_at.desc(), Run.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [run_response(run) for run in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: UUID, access: Access, session: Database) -> RunResponse:
    return run_response(scoped_run(session, str(run_id), access.workspace_id))


@router.get("/runs")
def all_runs(
    access: Access,
    session: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    scope = (
        Run.workspace_id == access.workspace_id,
        Project.workspace_id == access.workspace_id,
    )
    total = (
        session.scalar(
            select(func.count()).select_from(Run).join(Project).where(*scope)
        )
        or 0
    )
    rows = session.scalars(
        select(Run)
        .join(Project)
        .where(*scope)
        .order_by(Run.created_at.desc(), Run.id)
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [run_response(run) for run in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}/issues", response_model=list[IssueResponse])
def get_issues(
    run_id: UUID, access: Access, session: Database, severity: str | None = None
) -> list[IssueResponse]:
    scoped_run(session, str(run_id), access.workspace_id)
    statement = (
        select(Issue)
        .where(Issue.run_id == str(run_id))
        .order_by(Issue.created_at, Issue.id)
    )
    if severity:
        if severity not in {"info", "low", "medium", "high", "critical"}:
            raise HTTPException(422, "Severidad no válida.")
        statement = statement.where(Issue.severity == severity)
    return [issue_response(issue) for issue in session.scalars(statement.limit(200))]


@router.get("/runs/{run_id}/pages", response_model=list[PageResponse])
def get_pages(run_id: UUID, access: Access, session: Database) -> list[PageResponse]:
    scoped_run(session, str(run_id), access.workspace_id)
    return [
        page_response(page)
        for page in session.scalars(
            select(TestPage)
            .where(TestPage.test_run_id == str(run_id))
            .order_by(TestPage.scanned_at, TestPage.id)
            .limit(20)
        )
    ]


@router.post("/runs/{run_id}/cancel", response_model=RunResponse, status_code=202)
async def cancel_run(
    run_id: UUID, access: Access, service: Manager, request: Request
) -> RunResponse:
    result = await service.cancel(str(run_id), access.workspace_id)
    audit_request(request, "run.cancel_requested", str(run_id))
    return result


@router.get("/runs/{run_id}/pages/{page_id}/screenshot")
def screenshot(
    run_id: UUID, page_id: UUID, access: Access, session: Database, service: Manager
) -> FileResponse:
    scoped_run(session, str(run_id), access.workspace_id)
    page = session.scalar(
        select(TestPage).where(
            TestPage.id == str(page_id), TestPage.test_run_id == str(run_id)
        )
    )
    if not page or not page.screenshot_path:
        raise RunNotFound()
    path = service.evidence.path(str(run_id), str(page_id))
    if not path.is_file():
        raise RunNotFound()
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{page_id}.png"'},
    )
