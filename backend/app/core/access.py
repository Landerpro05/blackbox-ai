from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.security import WorkspaceMembership
from app.services.security import Principal, get_current_user


@dataclass(frozen=True)
class WorkspaceAccess:
    workspace_id: str
    user_id: str | None = None
    role: str = "owner"


def get_workspace_access(
    request: Request,
    principal: Annotated[Principal, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> WorkspaceAccess:
    header = request.headers.get("x-workspace-id")
    query = request.query_params.get("workspace")
    if header and query and header != query:
        raise HTTPException(400, "Los contextos de workspace no coinciden.")
    identifier = header or query or principal.workspace_id
    membership = (
        session.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.user_id == principal.user_id,
                WorkspaceMembership.workspace_id == identifier,
            )
        )
        if identifier and len(identifier) <= 64
        else None
    )
    if membership is None:
        raise HTTPException(404, "Workspace no disponible.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if membership.role == "viewer":
            raise HTTPException(403, "Tu rol solo permite consultar resultados.")
        if (
            request.method == "DELETE"
            and request.url.path.rstrip("/").split("/")[-2] == "projects"
            and membership.role not in {"owner", "admin"}
        ):
            raise HTTPException(403, "Eliminar proyectos requiere owner o admin.")
    request.state.workspace_id = identifier
    return WorkspaceAccess(identifier, principal.user_id, membership.role)
