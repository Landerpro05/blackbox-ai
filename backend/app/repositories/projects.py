from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Project
from app.schemas.projects import ProjectCreate, ProjectUpdate


class ProjectRepository:
    def __init__(self, session: Session, workspace_id: str) -> None:
        self.session = session
        self.workspace_id = workspace_id

    def list(self, limit: int, offset: int) -> tuple[list[Project], int]:
        scope = Project.workspace_id == self.workspace_id
        total = (
            self.session.scalar(select(func.count()).select_from(Project).where(scope))
            or 0
        )
        items = list(
            self.session.scalars(
                select(Project)
                .where(scope)
                .order_by(Project.created_at.desc(), Project.id)
                .offset(offset)
                .limit(limit)
            )
        )
        return items, total

    def get(self, project_id: str) -> Project | None:
        return self.session.scalar(
            select(Project).where(
                Project.id == project_id,
                Project.workspace_id == self.workspace_id,
            )
        )

    def create(self, data: ProjectCreate) -> Project:
        project = Project(**data.model_dump(), workspace_id=self.workspace_id)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def update(self, project: Project, data: ProjectUpdate) -> Project:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        self.session.commit()
        self.session.refresh(project)
        return project

    def delete(self, project: Project) -> None:
        self.session.delete(project)
        self.session.commit()
