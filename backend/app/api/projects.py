from collections.abc import Generator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.access import WorkspaceAccess, get_workspace_access
from app.core.database import get_session
from app.models import Project
from app.repositories.projects import ProjectRepository
from app.schemas.projects import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def get_repository(
    session: Annotated[Session, Depends(get_session)],
    access: Annotated[WorkspaceAccess, Depends(get_workspace_access)],
) -> Generator[ProjectRepository, None, None]:
    try:
        yield ProjectRepository(session, access.workspace_id)
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail="No se pudo completar la operación. Inténtalo de nuevo.",
        ) from None


Repository = Annotated[ProjectRepository, Depends(get_repository)]


def require_project(repository: ProjectRepository, project_id: UUID) -> Project:
    project = repository.get(str(project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    return project


@router.get("", response_model=ProjectListResponse)
def list_projects(
    repository: Repository,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    projects, total = repository.list(limit, offset)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(project) for project in projects],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate, repository: Repository, response: Response, request: Request
) -> ProjectResponse:
    project = repository.create(data)
    response.headers["Location"] = f"{request.url.path}/{project.id}"
    return ProjectResponse.model_validate(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: UUID, repository: Repository) -> ProjectResponse:
    return ProjectResponse.model_validate(require_project(repository, project_id))


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID, data: ProjectUpdate, repository: Repository
) -> ProjectResponse:
    project = repository.update(require_project(repository, project_id), data)
    return ProjectResponse.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: UUID, repository: Repository) -> Response:
    repository.delete(require_project(repository, project_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
