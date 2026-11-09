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
from app.core.config import get_settings
from app.core.database import build_engine, session_factory


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    engine = build_engine(get_settings().database_url)
    application.state.session_factory = session_factory(engine)
    try:
        yield
    finally:
        engine.dispose()


app = FastAPI(
    title="BLACKBOX AI",
    version="0.1.0",
    description="Local web testing platform. Phase 2: project management without target navigation.",
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
