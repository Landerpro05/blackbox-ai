from typing import Annotated
from uuid import UUID

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select

from app.api.runs import Access, Database, Manager
from app.models import Run, SuiteCase, TestEnvironment, TestSuite
from app.models.entities import utc_now
from app.repositories.runs import run_response
from app.schemas.lab import (
    AvailabilityRequest,
    CaseInput,
    CasePatch,
    EnvironmentInput,
    EnvironmentPatch,
    SuggestionImport,
    SuiteInput,
    SuitePatch,
    SuiteRunCreate,
)
from app.services.lab import (
    LabRepository,
    case_data,
    environment_data,
    policy_for,
    scoped_case,
    scoped_object,
    suite_data,
    suite_execution,
)
from app.testing.local_policy import LocalBroker
from app.testing.policy import DestinationDenied

router = APIRouter(prefix="/api/v1", tags=["testing-lab"])


def repository(session: Database, access: Access, service: Manager):
    return LabRepository(session, access.workspace_id, service.settings)


Repository = Annotated[LabRepository, Depends(repository)]
Limit = Annotated[int, Query(ge=1, le=50)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/lab/capabilities")
def capabilities(service: Manager):
    return {
        "local_enabled": service.settings.local_lab_enabled,
        "allowed_origins": service.settings.local_lab_allowed_origins,
        "arbitrary_apps_enabled": False,
        "remote_enabled": False,
        "mode": "verified_project_catalog",
        "demo_enabled": service.settings.demo_testing_enabled,
        "max_cases": 20,
        "case_types": [
            "http_status",
            "title",
            "element_exists",
            "text_visible",
            "no_js_errors",
            "internal_links",
            "navigate",
        ],
        "ci_status": "not_fetched",
        "workflow_path": ".github/workflows/ci.yml",
    }


@router.get("/projects/{project_id}/environments")
def environments(
    project_id: UUID, repo: Repository, limit: Limit = 20, offset: Offset = 0
):
    return repo.list(TestEnvironment, str(project_id), limit, offset)


@router.post("/projects/{project_id}/environments", status_code=201)
def create_environment(project_id: UUID, data: EnvironmentInput, repo: Repository):
    return repo.environment(str(project_id), data)


@router.patch("/environments/{environment_id}")
def update_environment(environment_id: UUID, data: EnvironmentPatch, repo: Repository):
    row = scoped_object(
        repo.session, TestEnvironment, str(environment_id), repo.workspace
    )
    return repo.environment(row.project_id, data, row.id)


@router.delete("/environments/{environment_id}", status_code=204)
def delete_environment(environment_id: UUID, repo: Repository):
    repo.remove(TestEnvironment, str(environment_id))
    return Response(status_code=204)


@router.post("/environments/{environment_id}/check")
async def check_environment(
    environment_id: UUID, data: AvailabilityRequest, repo: Repository
):
    row = scoped_object(
        repo.session, TestEnvironment, str(environment_id), repo.workspace
    )
    if not data.authorize or data.consent_origin != row.authorized_origin:
        raise HTTPException(
            403, "Autoriza el origen exacto antes de comprobar disponibilidad."
        )
    policy = policy_for(row, repo.settings)
    target = policy.authorize(row.base_url)
    state = "verified"
    if row.kind == "local":
        try:
            await LocalBroker(policy)(target)
        except (httpx2.HTTPError, DestinationDenied):
            state = "unavailable"
    row.last_check_status, row.last_checked_at = state, utc_now()
    repo.session.commit()
    return environment_data(row, repo.settings)


@router.get("/projects/{project_id}/suites")
def suites(project_id: UUID, repo: Repository, limit: Limit = 20, offset: Offset = 0):
    return repo.list(TestSuite, str(project_id), limit, offset)


@router.post("/projects/{project_id}/suites", status_code=201)
def create_suite(project_id: UUID, data: SuiteInput, repo: Repository):
    return repo.suite(str(project_id), data)


@router.get("/suites/{suite_id}")
def get_suite(suite_id: UUID, repo: Repository):
    row = scoped_object(repo.session, TestSuite, str(suite_id), repo.workspace)
    result = suite_data(row)
    result["cases"] = [
        case_data(r)
        for r in repo.session.scalars(
            select(SuiteCase)
            .where(SuiteCase.suite_id == row.id)
            .order_by(SuiteCase.position, SuiteCase.id)
            .limit(20)
        )
    ]
    return result


@router.patch("/suites/{suite_id}")
def update_suite(suite_id: UUID, data: SuitePatch, repo: Repository):
    row = scoped_object(repo.session, TestSuite, str(suite_id), repo.workspace)
    return repo.suite(row.project_id, data, row.id)


@router.delete("/suites/{suite_id}", status_code=204)
def delete_suite(suite_id: UUID, repo: Repository):
    repo.remove(TestSuite, str(suite_id))
    return Response(status_code=204)


@router.post("/suites/{suite_id}/cases", status_code=201)
def create_case(suite_id: UUID, data: CaseInput, repo: Repository):
    return repo.case(str(suite_id), data)


@router.patch("/suite-cases/{case_id}")
def update_case(case_id: UUID, data: CasePatch, repo: Repository):
    row = scoped_case(repo.session, str(case_id), repo.workspace)
    return repo.case(row.suite_id, data, row.id)


@router.delete("/suite-cases/{case_id}", status_code=204)
def delete_case(case_id: UUID, repo: Repository):
    repo.remove(SuiteCase, str(case_id))
    return Response(status_code=204)


@router.post("/suites/{suite_id}/import-ai", status_code=201)
def import_ai(suite_id: UUID, data: SuggestionImport, repo: Repository):
    return repo.import_suggestion(str(suite_id), data)


@router.post("/suites/{suite_id}/runs", status_code=202)
async def start_suite(
    suite_id: UUID, data: SuiteRunCreate, access: Access, service: Manager
):
    return await service.submit_suite(str(suite_id), access.workspace_id, data)


@router.get("/suites/{suite_id}/runs")
def suite_history(
    suite_id: UUID, repo: Repository, limit: Limit = 20, offset: Offset = 0
):
    scoped_object(repo.session, TestSuite, str(suite_id), repo.workspace)
    scope = (Run.suite_id == str(suite_id), Run.workspace_id == repo.workspace)
    return {
        "items": [
            run_response(r)
            for r in repo.session.scalars(
                select(Run)
                .where(*scope)
                .order_by(Run.created_at.desc(), Run.id)
                .limit(limit)
                .offset(offset)
            )
        ],
        "total": repo.session.scalar(
            select(func.count()).select_from(Run).where(*scope)
        )
        or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/runs/{run_id}/suite-results")
def results(run_id: UUID, repo: Repository):
    return suite_execution(repo.session, str(run_id), repo.workspace)
