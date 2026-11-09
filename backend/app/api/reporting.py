from contextlib import contextmanager
from threading import BoundedSemaphore
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.database import get_session
from app.services import reporting

router = APIRouter(prefix="/api/v1", tags=["reporting"])
Database = Annotated[Session, Depends(get_session)]
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]
_render_slot = BoundedSemaphore(1)


@contextmanager
def render_slot():
    if not _render_slot.acquire(blocking=False):
        raise HTTPException(
            409, "Hay un informe generándose. Inténtalo de nuevo en unos segundos."
        )
    try:
        yield
    finally:
        _render_slot.release()


def download(content: bytes, run_id: UUID, extension: str, media: str) -> Response:
    return Response(
        reporting.bounded(content),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="blackbox-{run_id}.{extension}"',
            "Content-Security-Policy": "default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox",
        },
    )


@router.get("/runs/{run_id}/report")
def report(run_id: UUID, session: Database, access: Access) -> dict:
    return reporting.report_data(session, str(run_id), access.workspace_id)


@router.get("/runs/{run_id}/report/html")
def html(
    run_id: UUID, session: Database, access: Access, include_evidence: bool = True
) -> Response:
    data = reporting.report_data(session, str(run_id), access.workspace_id)
    with render_slot():
        return download(
            reporting.html_report(data, include_evidence), run_id, "html", "text/html"
        )


@router.get("/runs/{run_id}/report/pdf")
def pdf(
    run_id: UUID, session: Database, access: Access, include_evidence: bool = True
) -> Response:
    data = reporting.report_data(session, str(run_id), access.workspace_id)
    with render_slot():
        return download(
            reporting.pdf_report(data, include_evidence),
            run_id,
            "pdf",
            "application/pdf",
        )


@router.get("/runs/{run_id}/export/json")
def json_export(run_id: UUID, session: Database, access: Access) -> Response:
    return download(
        reporting.json_report(
            reporting.report_data(session, str(run_id), access.workspace_id)
        ),
        run_id,
        "json",
        "application/json",
    )


@router.get("/runs/{run_id}/export/csv")
def csv_export(run_id: UUID, session: Database, access: Access) -> Response:
    return download(
        reporting.csv_report(
            reporting.report_data(session, str(run_id), access.workspace_id)
        ),
        run_id,
        "csv",
        "text/csv",
    )


@router.get("/projects/{project_id}/compare")
def comparison(
    project_id: UUID,
    base_run_id: UUID,
    target_run_id: UUID,
    session: Database,
    access: Access,
) -> dict:
    return reporting.compare(
        session,
        str(project_id),
        access.workspace_id,
        str(base_run_id),
        str(target_run_id),
    )


@router.get("/projects/{project_id}/analytics")
def project_analytics(
    project_id: UUID,
    session: Database,
    access: Access,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    return reporting.analytics(
        session, str(project_id), access.workspace_id, limit, offset
    )
