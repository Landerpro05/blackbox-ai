import asyncio
import hashlib
import json
import re
from datetime import UTC, timedelta
from decimal import ROUND_CEILING, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import begin_write
from app.core.errors import RunNotFound
from app.models import AIAnalysis, Project, Run
from app.models.entities import utc_now
from app.repositories.runs import scoped_run
from app.schemas.intelligence import AnalysisCreate, AnalysisResponse, EngineResult
from app.services.ai_evidence import DANGEROUS, PROMPT_VERSION, collect, safe_text
from app.services.ai_provider import ProviderError, get_provider, input_estimate
from app.services.ai_rules import analyze_rules, render_tests, test_source

ACTIVE_AI = ("pending", "running")


def scoped_analysis(session, identifier: str, workspace: str) -> AIAnalysis:
    row = session.scalar(
        select(AIAnalysis)
        .join(Run)
        .join(Project)
        .where(
            AIAnalysis.id == identifier,
            AIAnalysis.workspace_id == workspace,
            Run.workspace_id == workspace,
            Project.workspace_id == workspace,
        )
    )
    if row is None:
        raise RunNotFound()
    return row


def response(row: AIAnalysis) -> AnalysisResponse:
    return AnalysisResponse(
        id=row.id,
        run_id=row.run_id,
        mode=row.mode,
        mode_label="Análisis basado en reglas"
        if row.mode == "rules"
        else "Interpretación de modelo LLM",
        provider=row.provider,
        model=row.model,
        status=row.status,
        prompt_version=row.prompt_version,
        created_at=row.created_at,
        completed_at=row.completed_at,
        external_authorized_at=row.external_authorized_at,
        error_message=row.error_message,
        estimated_input_tokens=row.estimated_input_tokens,
        estimated_output_tokens=row.estimated_output_tokens,
        reserved_tokens=row.reserved_tokens,
        reserved_cost_usd=str(row.reserved_cost_usd)
        if row.reserved_cost_usd is not None
        else None,
        actual_input_tokens=row.actual_input_tokens,
        actual_output_tokens=row.actual_output_tokens,
        evidence=row.evidence_json,
        result=row.result_json,
    )


def validate_result(
    result: EngineResult, evidence: dict, maximum: int, secret: str
) -> EngineResult:
    known = {item["id"] for item in evidence["issues"] + evidence["pages"]}
    if evidence["history"]:
        known.add(evidence["history"]["id"])
    issues = {item["id"]: item for item in evidence["issues"]}
    if len(result.findings) > maximum or len(result.suggested_tests) > maximum:
        raise ProviderError("too_many_findings")
    for item in [
        *result.findings,
        *result.suggested_tests,
        *result.hypothetical_relations,
    ]:
        if not set(item.evidence_ids) <= known or len(set(item.evidence_ids)) != len(
            item.evidence_ids
        ):
            raise ProviderError("unknown_evidence")
    for item in [*result.findings, *result.suggested_tests]:
        if not any(key in issues for key in item.evidence_ids):
            raise ProviderError("missing_issue_evidence")
    for test in result.suggested_tests:
        if test_source(test.template, test.evidence_ids, issues) is None:
            raise ProviderError("incompatible_test")
    allowed_urls = {item["url"] for item in evidence["issues"] + evidence["pages"]}
    observed_codes = {
        str(item["status_code"])
        for item in evidence["pages"]
        if item["status_code"] is not None
    }
    for issue in evidence["issues"]:
        observed_codes.update(
            re.findall(
                r"HTTP\s*([1-5]\d\d)",
                issue["title"] + " " + issue["message"],
                re.IGNORECASE,
            )
        )

    def scrub(value):
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if not isinstance(value, str):
            return value
        if re.search(
            r"\b[\w./-]+\.(?:py|tsx?|jsx?|java|go|rs|php|cs)(?::\d+)?\b",
            value,
            re.IGNORECASE,
        ):
            raise ProviderError("unsupported_source_file")
        if (
            not set(re.findall(r"HTTP\s*([1-5]\d\d)", value, re.IGNORECASE))
            <= observed_codes
        ):
            raise ProviderError("unsupported_http_fact")
        if DANGEROUS.search(value) or re.search(
            r"causa confirmada|confirmed cause|arreglo aplicado|fix applied",
            value,
            re.IGNORECASE,
        ):
            raise ProviderError("unsafe_output")
        for url in re.findall(r'https?://[^\s<>"\']+', value):
            if url.rstrip(".,;)") not in allowed_urls:
                raise ProviderError("unknown_url")
        return safe_text(value, secret, 1800)

    return EngineResult.model_validate(scrub(result.model_dump()))


class AIManager:
    def __init__(self, factory, settings, provider_factory=get_provider):
        self.factory, self.settings, self.provider_factory = (
            factory,
            settings,
            provider_factory,
        )
        self._task = None
        self._active_id = None
        self._closing = False
        self._mutex = asyncio.Lock()

    def ready(self) -> bool:
        return bool(
            self.settings.ai_provider != "disabled"
            and self.settings.ai_model
            and self.settings.ai_api_key
            and self.settings.ai_api_key.get_secret_value().strip()
        )

    def capabilities(self) -> dict:
        return {
            "rules_enabled": True,
            "llm_enabled": self.ready(),
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model,
            "external_confirmation_required": True,
            "screenshots_sent": False,
            "max_context_bytes": 12000,
            "max_findings": 8,
            "max_output_tokens": self.settings.ai_max_output_tokens,
            "max_attempts": self.settings.ai_max_retries + 1,
            "daily_call_limit": self.settings.ai_daily_call_limit,
            "daily_token_limit": self.settings.ai_daily_token_limit,
            "daily_budget_usd": self.settings.ai_daily_budget_usd,
            "prices_configured": self.settings.ai_input_usd_per_million is not None
            and self.settings.ai_output_usd_per_million is not None,
            "test_execution_enabled": False,
        }

    async def start(self):
        def recover():
            with self.factory.begin() as session:
                session.execute(
                    update(AIAnalysis)
                    .where(AIAnalysis.status.in_(ACTIVE_AI))
                    .values(
                        status="failed",
                        active_slot=None,
                        completed_at=utc_now(),
                        error_message="El servidor se reinició antes de completar la interpretación.",
                    )
                )

        await asyncio.to_thread(recover)

    async def close(self):
        self._closing = True
        if self._task:
            identifier = self._active_id
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            if identifier:
                await self._write(
                    self._finish,
                    identifier,
                    "cancelled",
                    None,
                    "Interpretación cancelada al cerrar el servidor.",
                    None,
                    None,
                )

    async def _write(self, operation, *args):
        work = asyncio.create_task(asyncio.to_thread(operation, *args))
        try:
            return await asyncio.shield(work)
        except asyncio.CancelledError:
            await work
            raise

    def _create(self, run_id: str, workspace: str, options: AnalysisCreate):
        with self.factory() as session:
            begin_write(session)
            scoped_run(session, run_id, workspace)
            if options.mode == "llm":
                if not options.authorize_external:
                    raise HTTPException(
                        403,
                        "Autoriza expresamente el envío de evidencias redactadas al proveedor externo.",
                    )
                if not self.ready():
                    raise HTTPException(
                        409,
                        "El proveedor LLM no está configurado. Puedes usar el análisis basado en reglas.",
                    )
                if (
                    options.consent_provider != self.settings.ai_provider
                    or options.consent_model != self.settings.ai_model
                ):
                    raise HTTPException(
                        409,
                        "La configuración del proveedor cambió o falta su confirmación. Revisa proveedor y modelo antes de autorizar.",
                    )
            secret = (
                self.settings.ai_api_key.get_secret_value()
                if self.settings.ai_api_key
                else ""
            )
            evidence = collect(
                session, run_id, workspace, options.include_history, secret
            )
            provider = self.settings.ai_provider if options.mode == "llm" else "rules"
            model = (
                self.settings.ai_model if options.mode == "llm" else "deterministic-v1"
            )
            digest = hashlib.sha256(
                json.dumps(
                    [
                        evidence,
                        options.mode,
                        provider,
                        model,
                        options.max_findings,
                        PROMPT_VERSION,
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            cached = session.scalar(
                select(AIAnalysis)
                .where(
                    AIAnalysis.run_id == run_id,
                    AIAnalysis.workspace_id == workspace,
                    AIAnalysis.context_hash == digest,
                    AIAnalysis.status.in_(("pending", "running", "completed")),
                )
                .order_by(AIAnalysis.created_at.desc())
                .limit(1)
            )
            if cached:
                return response(cached), False, evidence
            if session.scalar(
                select(AIAnalysis.id).where(AIAnalysis.active_slot == 1).limit(1)
            ):
                raise HTTPException(
                    409, "Ya hay una interpretación activa. Espera a que termine."
                )
            now = utc_now()
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            scope = (AIAnalysis.workspace_id == workspace, AIAnalysis.created_at >= day)
            calls = (
                session.scalar(
                    select(func.count())
                    .select_from(AIAnalysis)
                    .where(*scope, AIAnalysis.mode == options.mode)
                )
                or 0
            )
            input_tokens = input_estimate(evidence) if options.mode == "llm" else 0
            output_tokens = (
                self.settings.ai_max_output_tokens if options.mode == "llm" else 0
            )
            reserved = (input_tokens + output_tokens) * (
                self.settings.ai_max_retries + 1
            )
            cost = None
            if options.mode == "llm":
                run_calls = (
                    session.scalar(
                        select(func.count())
                        .select_from(AIAnalysis)
                        .where(
                            AIAnalysis.run_id == run_id,
                            AIAnalysis.workspace_id == workspace,
                            AIAnalysis.mode == "llm",
                        )
                    )
                    or 0
                )
                latest = session.scalar(
                    select(AIAnalysis.created_at)
                    .where(
                        AIAnalysis.workspace_id == workspace, AIAnalysis.mode == "llm"
                    )
                    .order_by(AIAnalysis.created_at.desc())
                    .limit(1)
                )
                spent_tokens = session.scalar(
                    select(
                        func.coalesce(func.sum(AIAnalysis.reserved_tokens), 0)
                    ).where(*scope, AIAnalysis.mode == "llm")
                )
                if (
                    calls >= self.settings.ai_daily_call_limit
                    or run_calls >= self.settings.ai_run_call_limit
                    or spent_tokens + reserved > self.settings.ai_daily_token_limit
                ):
                    raise HTTPException(
                        429,
                        "Se alcanzó una cuota local de IA. Usa el modo basado en reglas.",
                        headers={"Retry-After": "60"},
                    )
                if latest and now - latest.replace(
                    tzinfo=latest.tzinfo or UTC
                ) < timedelta(seconds=self.settings.ai_cooldown_seconds):
                    raise HTTPException(
                        429,
                        "Espera antes de solicitar otra interpretación externa.",
                        headers={"Retry-After": str(self.settings.ai_cooldown_seconds)},
                    )
                if (
                    self.settings.ai_input_usd_per_million is not None
                    and self.settings.ai_output_usd_per_million is not None
                ):
                    cost = (
                        (
                            Decimal(str(self.settings.ai_input_usd_per_million))
                            * input_tokens
                            + Decimal(str(self.settings.ai_output_usd_per_million))
                            * output_tokens
                        )
                        * (self.settings.ai_max_retries + 1)
                        / 1000000
                    ).quantize(Decimal("0.00000001"), rounding=ROUND_CEILING)
                    spent = session.scalar(
                        select(
                            func.coalesce(func.sum(AIAnalysis.reserved_cost_usd), 0)
                        ).where(*scope, AIAnalysis.mode == "llm")
                    )
                    if self.settings.ai_daily_budget_usd is not None and Decimal(
                        str(spent)
                    ) + cost > Decimal(str(self.settings.ai_daily_budget_usd)):
                        raise HTTPException(
                            429,
                            "Se alcanzó el presupuesto local de IA. Usa el modo basado en reglas.",
                        )
            elif calls >= 100:
                raise HTTPException(
                    429, "Se alcanzó la cuota diaria de análisis por reglas."
                )
            row = AIAnalysis(
                run_id=run_id,
                workspace_id=workspace,
                provider=provider,
                model=model,
                mode=options.mode,
                status="pending",
                prompt_version=PROMPT_VERSION,
                context_hash=digest,
                evidence_json=evidence,
                estimated_input_tokens=input_tokens,
                estimated_output_tokens=output_tokens,
                reserved_tokens=reserved,
                reserved_cost_usd=cost,
                external_authorized_at=now if options.mode == "llm" else None,
                active_slot=1,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                raise HTTPException(409, "Ya hay una interpretación activa.") from None
            return response(row), True, evidence

    async def submit(self, run_id: str, workspace: str, options: AnalysisCreate):
        async with self._mutex:
            if self._closing:
                raise HTTPException(
                    503, "El servicio de interpretación se está cerrando."
                )
            creation = asyncio.create_task(
                asyncio.to_thread(self._create, run_id, workspace, options)
            )
            try:
                created, fresh, evidence = await asyncio.shield(creation)
            except asyncio.CancelledError:
                created, fresh, evidence = await creation
                if fresh:
                    await self._write(
                        self._finish, created.id, "cancelled", None, None, None, None
                    )
                raise
            if fresh:
                self._active_id = created.id
                self._task = asyncio.create_task(
                    self._execute(created.id, options, evidence),
                    name=f"blackbox-ai-{created.id}",
                )
            return created, fresh

    def _running(self, identifier):
        with self.factory.begin() as session:
            row = session.get(AIAnalysis, identifier)
            if row and row.status == "pending":
                row.status = "running"

    def _finish(self, identifier, status, result, error, incoming, outgoing):
        with self.factory.begin() as session:
            row = session.get(AIAnalysis, identifier)
            if row and row.status in ACTIVE_AI:
                row.status, row.result_json, row.error_message = status, result, error
                row.completed_at, row.active_slot = utc_now(), None
                row.actual_input_tokens, row.actual_output_tokens = incoming, outgoing

    async def _execute(self, identifier, options, evidence):
        status, result, error, incoming, outgoing = "failed", None, None, None, None
        try:
            await self._write(self._running, identifier)
            if options.mode == "rules":
                interpreted = await asyncio.to_thread(
                    analyze_rules, evidence, options.max_findings
                )
            else:
                async with asyncio.timeout(
                    self.settings.ai_timeout_seconds
                    * (self.settings.ai_max_retries + 1)
                    + 3
                ):
                    output = await self.provider_factory(self.settings).analyze(
                        evidence, options.max_findings
                    )
                interpreted, incoming, outgoing = (
                    output.result,
                    output.input_tokens,
                    output.output_tokens,
                )
            secret = (
                self.settings.ai_api_key.get_secret_value()
                if self.settings.ai_api_key
                else ""
            )
            interpreted = validate_result(
                interpreted, evidence, options.max_findings, secret
            )
            result = render_tests(interpreted, evidence).model_dump()
            status = "completed"
        except asyncio.CancelledError:
            status, error = (
                "cancelled",
                "Interpretación cancelada. Una solicitud externa ya enviada puede generar cargos.",
            )
        except ProviderError:
            error = "El proveedor no pudo devolver una respuesta segura y válida. Puedes usar el análisis basado en reglas."
        except TimeoutError:
            error = "Se alcanzó el timeout de la interpretación. Puedes usar el análisis basado en reglas."
        except Exception:  # noqa: BLE001 - isolate all AI failures; never expose raw exceptions
            # Never persist arbitrary provider exceptions, prompts, responses or keys.
            error = "No se pudo completar la interpretación. Los resultados originales se conservan."
        finally:
            await self._write(
                self._finish, identifier, status, result, error, incoming, outgoing
            )
            if self._active_id == identifier:
                self._active_id = None

    async def cancel(self, identifier: str, workspace: str):
        def read():
            with self.factory() as session:
                return response(scoped_analysis(session, identifier, workspace))

        current = await asyncio.to_thread(read)
        if identifier == self._active_id and self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            await self._write(
                self._finish,
                identifier,
                "cancelled",
                None,
                "Interpretación cancelada. Una solicitud externa ya enviada puede generar cargos.",
                None,
                None,
            )
            self._active_id = None
            current = await asyncio.to_thread(read)
        return current
