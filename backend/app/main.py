from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.routes import router
from app.api.projects import router as projects_router
from app.api.runs import router as runs_router
from app.core.config import get_settings
from app.core.database import build_engine, session_factory
from app.repositories.runs import RunNotFound
from app.services.run_manager import DemoDisabled, RunBusy, RunManager
from app.testing.policy import DestinationDenied
from sqlalchemy.exc import SQLAlchemyError


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    engine = build_engine(get_settings().database_url)
    application.state.session_factory = session_factory(engine)
    manager = RunManager(
        application.state.session_factory, get_settings(), str(engine.url.database)
    )
    application.state.run_manager = manager
    try:
        await manager.start()
        yield
    finally:
        try:
            await manager.close()
        finally:
            engine.dispose()


app = FastAPI(
    title="BLACKBOX AI",
    version="0.1.0",
    description="Phase 3: real Playwright testing of the bundled controlled demo. Remote browsing disabled.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Accept", "Content-Type"],
)


@app.middleware("http")
async def no_store_api(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.include_router(router)
app.include_router(projects_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api")
app.include_router(runs_router)


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
            "detail": "Solo se permite analizar la demostración integrada. La navegación remota y otras aplicaciones locales están deshabilitadas."
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
