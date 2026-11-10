from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.database import get_session
from app.models import AIAnalysis
from app.repositories.runs import scoped_run
from app.schemas.intelligence import AnalysisCreate, AnalysisList, AnalysisResponse
from app.services.ai_manager import AIManager, response, scoped_analysis
from app.services.security import audit_request

router = APIRouter(prefix="/api/v1", tags=["intelligence"])
Database = Annotated[Session, Depends(get_session)]
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def get_manager(request: Request) -> AIManager:
    return request.app.state.ai_manager


Manager = Annotated[AIManager, Depends(get_manager)]


@router.get("/ai/capabilities")
def capabilities(manager: Manager) -> dict:
    return manager.capabilities()


@router.post(
    "/runs/{run_id}/ai-analysis", response_model=AnalysisResponse, status_code=202
)
async def create(
    run_id: UUID,
    data: AnalysisCreate,
    access: Access,
    manager: Manager,
    result: Response,
    request: Request,
    session: Database,
):
    if data.mode == "llm" and access.role not in {"owner", "admin"}:
        raise HTTPException(403, "Solicitar un LLM externo requiere owner o admin.")
    if data.mode == "llm":
        scoped_run(session, str(run_id), access.workspace_id)
        audit_request(request, "llm.requested", str(run_id), outcome="requested")
    row, fresh = await manager.submit(str(run_id), access.workspace_id, data)
    result.status_code = 202 if fresh else 200
    result.headers["Location"] = f"/api/v1/ai-analyses/{row.id}"
    return row


@router.get("/runs/{run_id}/ai-analysis", response_model=AnalysisList)
def list_analyses(
    run_id: UUID,
    session: Database,
    access: Access,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    scoped_run(session, str(run_id), access.workspace_id)
    scope = (
        AIAnalysis.run_id == str(run_id),
        AIAnalysis.workspace_id == access.workspace_id,
    )
    total = (
        session.scalar(select(func.count()).select_from(AIAnalysis).where(*scope)) or 0
    )
    items = session.scalars(
        select(AIAnalysis)
        .where(*scope)
        .order_by(AIAnalysis.created_at.desc(), AIAnalysis.id)
        .limit(limit)
        .offset(offset)
    )
    return AnalysisList(
        items=[response(row) for row in items], total=total, limit=limit, offset=offset
    )


@router.get("/ai-analyses/{analysis_id}", response_model=AnalysisResponse)
def detail(analysis_id: UUID, session: Database, access: Access):
    return response(scoped_analysis(session, str(analysis_id), access.workspace_id))


@router.post(
    "/ai-analyses/{analysis_id}/cancel",
    response_model=AnalysisResponse,
    status_code=202,
)
async def cancel(analysis_id: UUID, access: Access, manager: Manager):
    return await manager.cancel(str(analysis_id), access.workspace_id)
