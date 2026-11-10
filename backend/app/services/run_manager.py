import asyncio
import logging
import os
import time
from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import DemoDisabled, RunBusy
from app.models import Project, Run, RunStatus
from app.repositories.runs import RunNotFound, RunWriter, run_response
from app.schemas.runs import RunCreate, RunLimits, RunResponse
from app.services.worker_lock import WorkerLock
from app.testing.engine import DemoEngine, ScannedPage
from app.testing.evidence import EvidenceStore
from app.testing.policy import DemoPolicy

logger = logging.getLogger(__name__)


class RunManager:
    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        database_path: str,
        engine_factory: Callable[[EvidenceStore], DemoEngine] = DemoEngine,
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.writer = RunWriter(factory)
        self.evidence = EvidenceStore(settings.evidence_dir)
        self.engine_factory = engine_factory
        self.worker_lock = WorkerLock(database_path)
        self._task: asyncio.Task | None = None
        self._cancel: asyncio.Event | None = None
        self._active_id: str | None = None
        self._mutex = asyncio.Lock()
        self._closing = False

    async def start(self) -> None:
        if (
            (self.settings.demo_testing_enabled or self.settings.local_lab_enabled)
            and os.name == "nt"
            and isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop)
        ):
            raise RuntimeError(
                "En Windows inicia la demo sin --reload ni múltiples workers para usar ProactorEventLoop."
            )
        self.worker_lock.acquire()
        try:
            await asyncio.to_thread(self.writer.recover_interrupted)
        except BaseException:
            self.worker_lock.release()
            raise

    async def close(self) -> None:
        self._closing = True
        try:
            if self._task:
                if not self._task.done() and self._cancel:
                    self._cancel.set()
                await asyncio.gather(self._task, return_exceptions=True)
        finally:
            self.worker_lock.release()

    def _create(
        self, project_id: str, workspace: str, data: RunCreate
    ) -> tuple[RunResponse, str]:
        with self.factory() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            project = session.scalar(
                select(Project).where(
                    Project.id == project_id, Project.workspace_id == workspace
                )
            )
            if project is None:
                raise RunNotFound()
            if not self.settings.demo_testing_enabled:
                raise DemoDisabled(
                    "La demostración está deshabilitada en la configuración del servidor."
                )
            target = DemoPolicy().authorize(project.base_url)
            run = Run(
                project_id=project.id,
                workspace_id=workspace,
                target_url=target,
                status=RunStatus.QUEUED,
                limits=data.limits.model_dump(),
                active_slot=1,
            )
            session.add(run)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise RunBusy(
                    "Ya existe un análisis activo. Espera a que termine o cancélalo."
                ) from None
            session.refresh(run)
            return run_response(run), target, data.limits, None

    async def submit(
        self, project_id: str, workspace: str, data: RunCreate
    ) -> RunResponse:
        return await self._submit(self._create, project_id, workspace, data)

    async def submit_suite(self, suite_id, workspace, data):
        from app.services.lab import prepare_suite_run

        return await self._submit(
            prepare_suite_run, self.factory, self.settings, suite_id, workspace, data
        )

    async def _submit(self, create, *args):
        async with self._mutex:
            if self._closing or (self._task is not None and not self._task.done()):
                raise RunBusy(
                    "Ya existe un análisis activo. Espera a que termine o cancélalo."
                )
            creation = asyncio.create_task(asyncio.to_thread(create, *args))
            try:
                response, target, limits, specification = await asyncio.shield(creation)
            except asyncio.CancelledError:
                response, target, limits, specification = await creation
                await asyncio.to_thread(
                    self.writer.finish,
                    response.id,
                    RunStatus.CANCELLED,
                    0,
                    0,
                    "La petición se canceló antes de iniciar el navegador.",
                )
                raise
            self._cancel = asyncio.Event()
            self._active_id = response.id
            self._task = asyncio.create_task(
                self._execute(response.id, target, limits, self._cancel, specification),
                name=f"blackbox-run-{response.id}",
            )
            return response

    async def cancel(self, run_id: str, workspace: str) -> RunResponse:
        response = await asyncio.to_thread(
            self.writer.request_cancel, run_id, workspace
        )
        if run_id == self._active_id and self._cancel:
            self._cancel.set()
        return response

    async def _execute(
        self,
        run_id: str,
        target: str,
        limits: RunLimits,
        cancellation: asyncio.Event,
        specification: dict | None = None,
    ) -> None:
        started = time.monotonic()
        engine = None
        status = RunStatus.FAILED
        message = None
        work = None
        cancel_waiter = None
        try:
            engine = self.engine_factory(self.evidence)
            if specification:
                from app.testing.local_policy import ControlledLocalPolicy, LocalBroker

                if specification["kind"] == "local":
                    engine.policy = ControlledLocalPolicy(
                        specification["origin"], self.settings.local_lab_allowed_origins
                    )
                    engine.responder = LocalBroker(
                        engine.policy, min(3, limits.navigation_timeout_seconds)
                    )
                engine.cases = specification["cases"]
            await asyncio.to_thread(self.writer.mark_running, run_id)

            async def on_page(page: ScannedPage, requests: int) -> None:
                write = asyncio.create_task(
                    asyncio.to_thread(
                        self.writer.page,
                        run_id,
                        page,
                        requests,
                        int((time.monotonic() - started) * 1000),
                    )
                )
                try:
                    await asyncio.shield(write)
                except asyncio.CancelledError:
                    await write
                    raise
                except Exception:
                    if page.screenshot_path:
                        self.evidence.remove_page(run_id, page.id)
                    raise

            work = asyncio.create_task(engine.run(run_id, target, limits, on_page))
            cancel_waiter = asyncio.create_task(cancellation.wait())
            remaining = max(0, limits.timeout_seconds - (time.monotonic() - started))
            done, _ = await asyncio.wait(
                {work, cancel_waiter},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation.is_set():
                status = RunStatus.CANCELLED
                work.cancel()
            elif work in done:
                await work
                status = RunStatus.COMPLETED
            else:
                message = "Se alcanzó el timeout global del análisis."
                work.cancel()
            if not work.done():
                try:
                    await work
                except asyncio.CancelledError:
                    pass
        except asyncio.CancelledError:
            status = RunStatus.CANCELLED
            if work:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
        except Exception:
            # Do not persist arbitrary browser exceptions, paths or raw page data.
            message = "El motor no pudo completar el análisis. Comprueba la instalación de Chromium y los registros locales."
            logger.warning("Analysis failed; run_id=%s", run_id)
        finally:
            if cancel_waiter:
                cancel_waiter.cancel()
                await asyncio.gather(cancel_waiter, return_exceptions=True)
            if work and not work.done():
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
            elif work:
                await asyncio.gather(work, return_exceptions=True)
            try:
                await asyncio.to_thread(
                    self.writer.finish,
                    run_id,
                    status,
                    int((time.monotonic() - started) * 1000),
                    engine.requests if engine else 0,
                    message,
                )
            finally:
                self._active_id = None
