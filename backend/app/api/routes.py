from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.database import get_session
from app.repositories.dashboard import read_dashboard
from app.schemas.dashboard import DashboardResponse, HealthResponse

router = APIRouter(prefix="/api/v1")
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(
    session: DatabaseSession, settings: Annotated[Settings, Depends(get_settings)]
) -> HealthResponse:
    try:
        session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        session.execute(text("SELECT 1 FROM projects LIMIT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503, detail="Database unavailable or migrations missing."
        ) from None
    return HealthResponse(environment=settings.environment)


@router.get("/dashboard", response_model=DashboardResponse, tags=["dashboard"])
def dashboard(
    session: DatabaseSession,
    access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
) -> DashboardResponse:
    try:
        return read_dashboard(session, access.workspace_id)
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503, detail="Dashboard unavailable. Check database migrations."
        ) from None
