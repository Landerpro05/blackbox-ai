from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Issue, Project, Run, RunStatus, Severity
from app.schemas.dashboard import (
    DashboardResponse,
    Metrics,
    ProjectOverview,
    RecentRun,
    TrendPoint,
)


def read_dashboard(session: Session, workspace_id: str = "local") -> DashboardResponse:
    now = datetime.now(UTC)
    first_day = now.date() - timedelta(days=13)
    start = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
    project_ids = select(Project.id).where(Project.workspace_id == workspace_id)
    run_ids = select(Run.id).where(Run.project_id.in_(project_ids))
    project_scope = Project.workspace_id == workspace_id
    run_scope = Run.project_id.in_(project_ids)
    issue_scope = Issue.run_id.in_(run_ids)
    metrics = Metrics(
        projects=session.scalar(
            select(func.count()).select_from(Project).where(project_scope)
        )
        or 0,
        runs=session.scalar(select(func.count()).select_from(Run).where(run_scope))
        or 0,
        issues=session.scalar(
            select(func.count()).select_from(Issue).where(issue_scope)
        )
        or 0,
        critical_issues=session.scalar(
            select(func.count())
            .select_from(Issue)
            .where(issue_scope, Issue.severity == Severity.CRITICAL)
        )
        or 0,
        active_runs=session.scalar(
            select(func.count())
            .select_from(Run)
            .where(run_scope, Run.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]))
        )
        or 0,
    )
    runs_by_day = dict(
        session.execute(
            select(func.date(Run.created_at), func.count())
            .where(run_scope, Run.created_at >= start)
            .group_by(func.date(Run.created_at))
        ).all()
    )
    issues_by_day = dict(
        session.execute(
            select(func.date(Issue.created_at), func.count())
            .where(issue_scope, Issue.created_at >= start)
            .group_by(func.date(Issue.created_at))
        ).all()
    )
    trend = []
    for offset in range(14):
        day = first_day + timedelta(days=offset)
        trend.append(
            TrendPoint(
                date=day,
                runs=runs_by_day.get(day.isoformat(), 0),
                issues=issues_by_day.get(day.isoformat(), 0),
            )
        )

    issue_counts = (
        select(Issue.run_id, func.count().label("total"))
        .group_by(Issue.run_id)
        .subquery()
    )
    recent = session.execute(
        select(Run, Project.name, func.coalesce(issue_counts.c.total, 0))
        .join(Project)
        .outerjoin(issue_counts, issue_counts.c.run_id == Run.id)
        .where(run_scope)
        .order_by(Run.created_at.desc(), Run.id)
        .limit(8)
    ).all()
    run_counts = (
        select(Run.project_id, func.count().label("total"))
        .group_by(Run.project_id)
        .subquery()
    )
    projects = session.execute(
        select(Project, func.coalesce(run_counts.c.total, 0))
        .outerjoin(run_counts, run_counts.c.project_id == Project.id)
        .where(project_scope)
        .order_by(Project.created_at.desc(), Project.id)
        .limit(5)
    ).all()
    return DashboardResponse(
        metrics=metrics,
        trend=trend,
        generated_at=now,
        recent_runs=[
            RecentRun(
                id=run.id,
                project_name=name,
                status=run.status,
                pages_visited=run.pages_visited,
                issue_count=count,
                created_at=run.created_at,
            )
            for run, name, count in recent
        ],
        projects=[
            ProjectOverview(
                id=project.id,
                name=project.name,
                base_url=project.base_url,
                run_count=count,
            )
            for project, count in projects
        ],
    )
