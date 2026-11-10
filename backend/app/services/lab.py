from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.errors import RunBusy, RunNotFound
from app.models import (
    CaseResult,
    Project,
    Run,
    RunStatus,
    SuiteCase,
    TestEnvironment,
    TestSuite,
)
from app.models.entities import utc_now
from app.repositories.runs import ACTIVE, run_response, scoped_run
from app.schemas.lab import CaseInput, EnvironmentInput
from app.schemas.runs import RunLimits
from app.services.ai_manager import scoped_analysis
from app.services.ai_rules import test_source
from app.services.reporting import clean, date, scoped_project
from app.testing.local_policy import ControlledLocalPolicy, local_origin
from app.testing.policy import DEMO_ORIGIN, DemoPolicy


def scoped_object(session, model, identifier, workspace):
    row = session.scalar(
        select(model)
        .join(Project)
        .where(
            model.id == identifier,
            model.workspace_id == workspace,
            Project.workspace_id == workspace,
        )
    )
    if row is None:
        raise RunNotFound()
    return row


def scoped_case(session, identifier, workspace):
    row = session.scalar(
        select(SuiteCase)
        .join(TestSuite)
        .join(Project)
        .where(
            SuiteCase.id == identifier,
            TestSuite.workspace_id == workspace,
            Project.workspace_id == workspace,
        )
    )
    if row is None:
        raise RunNotFound()
    return row


def environment_data(row, settings):
    enabled = (
        settings.demo_testing_enabled
        if row.kind == "demo"
        else settings.local_lab_enabled
    )
    allowed = (
        row.kind == "demo"
        or row.authorized_origin in settings.local_lab_allowed_origins
    )
    state = (
        "disabled" if not enabled else "origin_not_allowed" if not allowed else "ready"
    )
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "kind": row.kind,
        "base_url": row.base_url,
        "authorized_origin": row.authorized_origin,
        "limits": row.limits,
        "configuration_state": state,
        "last_check_status": row.last_check_status,
        "last_checked_at": date(row.last_checked_at),
        "created_at": date(row.created_at),
        "updated_at": date(row.updated_at),
    }


def suite_data(row):
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "created_at": date(row.created_at),
        "updated_at": date(row.updated_at),
    }


def case_data(row):
    return {
        "id": row.id,
        "suite_id": row.suite_id,
        "name": row.name,
        "position": row.position,
        "enabled": row.enabled,
        "definition": row.definition,
    }


def policy_for(environment, settings):
    if environment.kind == "demo":
        if not settings.demo_testing_enabled:
            raise HTTPException(403, "La demostración está deshabilitada.")
        return DemoPolicy()
    if not settings.local_lab_enabled:
        raise HTTPException(403, "Local Testing Lab está deshabilitado en el servidor.")
    return ControlledLocalPolicy(
        environment.authorized_origin, settings.local_lab_allowed_origins
    )


class LabRepository:
    def __init__(self, session, workspace, settings):
        self.session, self.workspace, self.settings = session, workspace, settings

    def begin(self):
        self.session.execute(text("BEGIN IMMEDIATE"))

    def guard(self, project_id):
        if self.session.scalar(
            select(Run.id)
            .where(Run.project_id == project_id, Run.status.in_(ACTIVE))
            .limit(1)
        ):
            raise RunBusy("El proyecto tiene una ejecución activa.")

    def save(self, row):
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise HTTPException(
                409, "La posición del caso ya está ocupada o el recurso cambió."
            ) from None
        return row

    def list(self, model, project_id, limit, offset):
        scoped_project(self.session, project_id, self.workspace)
        scope = (model.project_id == project_id, model.workspace_id == self.workspace)
        total = (
            self.session.scalar(select(func.count()).select_from(model).where(*scope))
            or 0
        )
        rows = self.session.scalars(
            select(model)
            .where(*scope)
            .order_by(model.created_at.desc(), model.id)
            .limit(limit)
            .offset(offset)
        )
        return {
            "items": [
                environment_data(r, self.settings)
                if model is TestEnvironment
                else suite_data(r)
                for r in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def environment(self, project_id, data, identifier=None):
        self.begin()
        scoped_project(self.session, project_id, self.workspace)
        self.guard(project_id)
        if identifier:
            row = scoped_object(
                self.session, TestEnvironment, identifier, self.workspace
            )
            merged = {
                key: getattr(row, key) for key in ("name", "kind", "base_url", "limits")
            }
            merged.update(data.model_dump(exclude_unset=True))
            try:
                data = EnvironmentInput.model_validate(merged)
            except ValidationError:
                raise HTTPException(
                    422, "La configuración del entorno no es válida."
                ) from None
        else:
            row = TestEnvironment(project_id=project_id, workspace_id=self.workspace)
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        row.authorized_origin = (
            DEMO_ORIGIN if data.kind == "demo" else local_origin(data.base_url)
        )
        row.last_checked_at, row.last_check_status = None, None
        return environment_data(self.save(row), self.settings)

    def suite(self, project_id, data, identifier=None):
        self.begin()
        scoped_project(self.session, project_id, self.workspace)
        self.guard(project_id)
        row = (
            scoped_object(self.session, TestSuite, identifier, self.workspace)
            if identifier
            else TestSuite(project_id=project_id, workspace_id=self.workspace)
        )
        for key, value in data.model_dump(exclude_unset=bool(identifier)).items():
            setattr(row, key, value)
        return suite_data(self.save(row))

    def case(self, suite_id, data, identifier=None):
        self.begin()
        suite = scoped_object(self.session, TestSuite, suite_id, self.workspace)
        self.guard(suite.project_id)
        if identifier:
            row = scoped_case(self.session, identifier, self.workspace)
            values = {
                key: getattr(row, key)
                for key in ("name", "position", "enabled", "definition")
            }
            values.update(data.model_dump(exclude_unset=True))
            data = CaseInput.model_validate(values)
        else:
            if (
                self.session.scalar(
                    select(func.count())
                    .select_from(SuiteCase)
                    .where(SuiteCase.suite_id == suite_id)
                )
                >= 20
            ):
                raise HTTPException(422, "Cada suite admite hasta 20 casos.")
            row = SuiteCase(suite_id=suite_id)
        for key, value in data.model_dump().items():
            setattr(row, key, value)
        suite.updated_at = utc_now()
        return case_data(self.save(row))

    def remove(self, model, identifier):
        self.begin()
        if model is SuiteCase:
            row = scoped_case(self.session, identifier, self.workspace)
            project_id = scoped_object(
                self.session, TestSuite, row.suite_id, self.workspace
            ).project_id
        else:
            row = scoped_object(self.session, model, identifier, self.workspace)
            project_id = row.project_id
        self.guard(project_id)
        self.session.delete(row)
        self.session.commit()

    def import_suggestion(self, suite_id, data):
        if not data.confirm:
            raise HTTPException(
                403, "Confirma la conversión de la sugerencia antes de importarla."
            )
        suite = scoped_object(self.session, TestSuite, suite_id, self.workspace)
        analysis = scoped_analysis(self.session, str(data.analysis_id), self.workspace)
        run = scoped_run(self.session, analysis.run_id, self.workspace)
        if run.project_id != suite.project_id:
            raise RunNotFound()
        suggestions = (analysis.result_json or {}).get("suggested_tests", [])
        if analysis.status != "completed" or data.suggestion_index >= len(suggestions):
            raise HTTPException(422, "La sugerencia no está disponible.")
        suggestion = suggestions[data.suggestion_index]
        issues = {i["id"]: i for i in analysis.evidence_json["issues"]}
        source = test_source(suggestion["template"], suggestion["evidence_ids"], issues)
        if source is None:
            raise HTTPException(422, "No hay una URL registrada compatible.")
        definition = (
            {
                "type": "http_status",
                "path": urlsplit(source["url"]).path or "/",
                "minimum": 100,
                "maximum": 399,
            }
            if suggestion["template"] == "http_status"
            else {"type": "no_js_errors", "path": urlsplit(source["url"]).path or "/"}
        )
        try:
            converted = CaseInput(
                name=data.name,
                position=data.position,
                enabled=False,
                definition=definition,
            )
        except ValidationError:
            raise HTTPException(
                422, "La sugerencia no se puede convertir a un caso compatible."
            ) from None
        return self.case(suite_id, converted)


def suite_execution(session, identifier, workspace):
    run = scoped_run(session, identifier, workspace)
    rows = list(
        session.scalars(
            select(CaseResult)
            .where(CaseResult.run_id == run.id)
            .order_by(CaseResult.position, CaseResult.id)
            .limit(20)
        )
    )
    counts = {
        key: sum(row.status == key for row in rows)
        for key in ("pending", "pass", "fail", "error", "skipped")
    }
    return {
        "run": run_response(run),
        "environment": run.environment_snapshot,
        "counts": counts,
        "cases": [
            {
                "id": r.id,
                "name": r.name,
                "position": r.position,
                "definition": r.definition,
                "status": r.status,
                "message": clean(r.message),
                "duration_ms": r.duration_ms,
                "evidence_url": f"/runs/{run.id}/pages/{r.page_id}/screenshot"
                if r.page_id
                else None,
            }
            for r in rows
        ],
    }


def prepare_suite_run(factory, settings, suite_id, workspace, data):
    with factory() as session:
        repository = LabRepository(session, workspace, settings)
        repository.begin()
        suite = scoped_object(session, TestSuite, suite_id, workspace)
        environment = scoped_object(
            session, TestEnvironment, str(data.environment_id), workspace
        )
        if environment.project_id != suite.project_id:
            raise RunNotFound()
        if not data.authorize or data.consent_origin != environment.authorized_origin:
            raise HTTPException(
                403, "Autoriza expresamente el origen exacto de esta ejecución."
            )
        policy = policy_for(environment, settings)
        target = policy.authorize(environment.base_url)
        limits = RunLimits.model_validate(environment.limits)
        cases = list(
            session.scalars(
                select(SuiteCase)
                .where(SuiteCase.suite_id == suite_id, SuiteCase.enabled.is_(True))
                .order_by(SuiteCase.position, SuiteCase.id)
                .limit(20)
            )
        )
        if not cases:
            raise HTTPException(422, "La suite no tiene casos habilitados.")
        if len(cases) > limits.max_pages:
            raise HTTPException(
                422,
                "Los casos habilitados superan el presupuesto de páginas del entorno.",
            )
        origin = environment.authorized_origin
        for case in cases:
            definition = CaseInput(
                name=case.name,
                position=case.position,
                enabled=case.enabled,
                definition=case.definition,
            ).definition.model_dump()
            policy.authorize(origin + definition["path"])
            if definition["type"] == "navigate":
                policy.authorize(origin + definition["destination"])
        run = Run(
            project_id=suite.project_id,
            workspace_id=workspace,
            target_url=target,
            status=RunStatus.QUEUED,
            active_slot=1,
            limits=limits.model_dump(),
            suite_id=suite.id,
            environment_id=environment.id,
            environment_snapshot={
                "id": environment.id,
                "name": environment.name,
                "kind": environment.kind,
                "base_url": environment.base_url,
                "authorized_origin": origin,
                "suite_name": suite.name,
            },
        )
        session.add(run)
        try:
            session.flush()
            snapshots = []
            for case in cases:
                row = CaseResult(
                    run_id=run.id,
                    case_id=case.id,
                    name=case.name,
                    position=case.position,
                    definition=case.definition,
                )
                session.add(row)
                session.flush()
                snapshots.append({"result_id": row.id, "definition": row.definition})
            session.commit()
        except IntegrityError:
            session.rollback()
            raise RunBusy("Ya hay una ejecución activa.") from None
        return (
            run_response(run),
            target,
            limits,
            {"kind": environment.kind, "origin": origin, "cases": snapshots},
        )
