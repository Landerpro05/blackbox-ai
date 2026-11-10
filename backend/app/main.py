import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.intelligence import router as intelligence_router
from app.api.lab import router as lab_router
from app.api.projects import router as projects_router
from app.api.reporting import router as reporting_router
from app.api.routes import router
from app.api.runs import router as runs_router
from app.api.security import router as security_router
from app.core.config import get_settings
from app.core.database import build_engine, session_factory
from app.core.security_middleware import SecurityMiddleware
from app.models.security import AuditEvent
from app.repositories.runs import RunNotFound
from app.services.ai_manager import AIManager
from app.services.run_manager import DemoDisabled, RunBusy, RunManager
from app.services.security import (
    LocalLimiter,
    get_current_user,
    now,
    password_operation,
)
from app.testing.policy import DestinationDenied


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    engine = build_engine(get_settings().database_url)
    application.state.session_factory = session_factory(engine)
    application.state.rate_limiter = LocalLimiter()
    application.state.dummy_password_hash = password_operation(
        "not-a-user-password-" + secrets.token_hex(16)
    )
    logging.getLogger("uvicorn.access").disabled = True
    security_logger = logging.getLogger("blackbox.security")
    security_logger.disabled = False
    security_logger.setLevel(logging.INFO)
    if not security_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        security_logger.addHandler(handler)
    security_logger.propagate = False
    manager = RunManager(
        application.state.session_factory, get_settings(), str(engine.url.database)
    )
    application.state.run_manager = manager
    intelligence = AIManager(application.state.session_factory, get_settings())
    application.state.ai_manager = intelligence
    try:
        await manager.start()
        # Only the process holding the worker lock performs retention/recovery.
        with application.state.session_factory.begin() as retention_session:
            retention_session.execute(
                delete(AuditEvent).where(
                    AuditEvent.created_at
                    < now() - timedelta(days=get_settings().audit_retention_days)
                )
            )
        await intelligence.start()
        yield
    finally:
        try:
            try:
                await intelligence.close()
            finally:
                await manager.close()
        finally:
            engine.dispose()


app = FastAPI(
    title="BLACKBOX AI",
    version="0.1.0",
    description="Phase 7: authenticated workspaces, revocable sessions and controlled testing. No public deployment or arbitrary browsing.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=[
        "Accept",
        "Content-Type",
        "X-CSRF-Token",
        "X-Workspace-ID",
        "X-Blackbox-Request",
    ],
)
app.add_middleware(SecurityMiddleware)


@app.middleware("http")
async def no_store_api(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.include_router(router)
protected = [Depends(get_current_user)]
app.include_router(projects_router, prefix="/api/v1", dependencies=protected)
app.include_router(projects_router, prefix="/api", dependencies=protected)
app.include_router(runs_router, dependencies=protected)
app.include_router(reporting_router, dependencies=protected)
app.include_router(intelligence_router, dependencies=protected)
app.include_router(lab_router, dependencies=protected)
app.include_router(security_router)


@app.exception_handler(RunNotFound)
async def run_not_found(_request: Request, _error: RunNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": "Proyecto, análisis o evidencia no encontrados."},
    )


@app.exception_handler(RunBusy)
async def run_busy(_request: Request, _error: RunBusy) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Ya existe un análisis activo. Espera o cancélalo antes de continuar."
        },
    )


@app.exception_handler(DemoDisabled)
async def demo_disabled(_request: Request, _error: DemoDisabled) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": "La demostración está deshabilitada. Activa BLACKBOX_DEMO_TESTING_ENABLED en el servidor local."
        },
    )


@app.exception_handler(DestinationDenied)
async def destination_denied(
    _request: Request, _error: DestinationDenied
) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": "Destino bloqueado. Solo se permite la demo integrada o el catálogo local verificado en un origen autorizado."
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(_request: Request, _error: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "No se pudo completar la operación con la base de datos."},
    )


@app.exception_handler(RequestValidationError)
async def validation_error(
    _request: Request, error: RequestValidationError
) -> JSONResponse:
    # Do not echo request inputs (e.g. a URL containing a password) in errors.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                for item in error.errors()
            ]
        },
    )
