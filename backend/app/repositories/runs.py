from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.models import Issue, Project, Run, RunStatus, Severity, TestPage
from app.models.entities import utc_now
from app.core.errors import RunNotFound
from app.schemas.runs import RunLimits, RunResponse, IssueResponse, PageResponse
from app.testing.engine import ScannedPage
from app.testing.policy import redact_text, redact_url

ACTIVE = (RunStatus.QUEUED, RunStatus.RUNNING)


def scoped_run(session: Session, run_id: str, workspace: str) -> Run:
    run = session.scalar(
        select(Run)
        .join(Project)
        .where(
            Run.id == run_id,
            Run.workspace_id == workspace,
            Project.workspace_id == workspace,
        )
    )
    if run is None:
        raise RunNotFound()
    return run


def run_response(run: Run) -> RunResponse:
    return RunResponse(
        id=run.id,
        project_id=run.project_id,
        status="pending" if run.status == RunStatus.QUEUED else run.status.value,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        pages_scanned=run.pages_visited,
        issues_found=run.issues_found,
        request_count=run.request_count,
        duration_ms=run.duration_ms,
        error_message=run.error_message,
        cancellation_requested=run.cancellation_requested,
        limits=RunLimits.model_validate(run.limits or {}),
    )


def screenshot_url(run_id: str, filename: str | None) -> str | None:
    from uuid import UUID

    if not filename:
        return None
    try:
        identifier = str(UUID(filename.removesuffix(".png")))
    except ValueError:
        return None
    return f"/runs/{run_id}/pages/{identifier}/screenshot"


def issue_response(issue: Issue) -> IssueResponse:
    return IssueResponse(
        id=issue.id,
        test_run_id=issue.run_id,
        type=issue.kind,
        severity=issue.severity.value,
        title=issue.title or issue.kind,
        description=redact_text(issue.description),
        url=redact_url(issue.affected_url),
        evidence_url=screenshot_url(issue.run_id, issue.evidence_path),
        created_at=issue.created_at,
    )


def page_response(page: TestPage) -> PageResponse:
    return PageResponse(
        id=page.id,
        test_run_id=page.test_run_id,
        url=page.url,
        status_code=page.status_code,
        load_time_ms=page.load_time_ms,
        depth=page.depth,
        screenshot_url=screenshot_url(page.test_run_id, page.screenshot_path),
        scanned_at=page.scanned_at,
    )


class RunWriter:
    """Short, independent transactions; no Session crosses async task boundaries."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def recover_interrupted(self) -> int:
        with self.factory.begin() as session:
            result = session.execute(
                update(Run)
                .where(Run.status.in_(ACTIVE))
                .values(
                    status=RunStatus.FAILED,
                    finished_at=utc_now(),
                    active_slot=None,
                    error_message="El servidor se reinició antes de finalizar el análisis.",
                )
            )
            return result.rowcount

    def mark_running(self, run_id: str) -> None:
        with self.factory.begin() as session:
            run = session.get(Run, run_id)
            if run and run.status == RunStatus.QUEUED:
                run.status = RunStatus.RUNNING
                run.started_at = utc_now()

    def page(
        self, run_id: str, result: ScannedPage, requests: int, elapsed_ms: int
    ) -> None:
        with self.factory.begin() as session:
            run = session.get(Run, run_id)
            if run is None or run.status != RunStatus.RUNNING:
                return
            session.add(
                TestPage(
                    id=result.id,
                    test_run_id=run_id,
                    url=result.url,
                    status_code=result.status_code,
                    load_time_ms=result.load_time_ms,
                    depth=result.depth,
                    screenshot_path=result.screenshot_path,
                )
            )
            for issue in result.findings:
                session.add(
                    Issue(
                        run_id=run_id,
                        kind=issue.kind,
                        severity=Severity(issue.severity),
                        title=issue.title,
                        description=issue.description,
                        affected_url=issue.url,
                        evidence_path=result.screenshot_path,
                    )
                )
            run.pages_visited += 1
            run.issues_found += len(result.findings)
            run.request_count = requests
            run.duration_ms = elapsed_ms

    def finish(
        self,
        run_id: str,
        status: RunStatus,
        elapsed_ms: int,
        requests: int,
        error: str | None,
    ) -> None:
        with self.factory.begin() as session:
            run = session.get(Run, run_id)
            if run and run.status in ACTIVE:
                run.status = status
                run.duration_ms = elapsed_ms
                run.request_count = requests
                run.error_message = error
                run.finished_at = utc_now()
                run.active_slot = None

    def request_cancel(self, run_id: str, workspace: str) -> RunResponse:
        with self.factory.begin() as session:
            run = scoped_run(session, run_id, workspace)
            if run.status in ACTIVE:
                run.cancellation_requested = True
            response = run_response(run)
        return response
