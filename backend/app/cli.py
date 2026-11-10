"""Thin API client: shared RunManager, validation, consent and browser engine."""

import argparse
import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import httpx2
from sqlalchemy.exc import SQLAlchemyError

from app.testing.policy import DEMO_URL


def exit_code(result: dict) -> int:
    if result["run"]["status"] == "cancelled":
        return 3
    if result["run"]["status"] != "completed" or result["counts"]["error"]:
        return 2
    return 1 if result["counts"]["fail"] else 0


def parser():
    root = argparse.ArgumentParser(description="BLACKBOX AI · Testing local autorizado")
    root.add_argument("command", choices=["demo", "test"])
    root.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    root.add_argument(
        "--standalone",
        action="store_true",
        help="API en proceso; requiere una base de datos libre",
    )
    root.add_argument(
        "--database", type=Path, help="SQLite independiente; solo con --standalone"
    )
    root.add_argument("--project", type=UUID)
    root.add_argument("--suite", type=UUID)
    root.add_argument("--environment", type=UUID)
    root.add_argument("--origin", help="Origen exacto consentido del entorno")
    root.add_argument(
        "--authorize", action="store_true", help="Autorizar esta ejecución"
    )
    root.add_argument(
        "--timeout", type=int, default=180, choices=range(5, 301), metavar="5..300"
    )
    root.add_argument("--json", type=Path, dest="output")
    return root


@asynccontextmanager
async def client_for(args):
    if not args.standalone:
        parsed = urlsplit(args.api)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/api/v1"
        ):
            raise ValueError("La CLI solo se conecta a una API HTTP de loopback.")
        async with httpx2.AsyncClient(
            base_url=args.api.rstrip("/") + "/",
            trust_env=False,
            follow_redirects=False,
            timeout=15,
        ) as client:
            yield client
        return
    if args.database:
        destination = args.database.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.environ["BLACKBOX_DATABASE_URL"] = f"sqlite:///{destination.as_posix()}"
    from alembic import command
    from alembic.config import Config

    from app.core.config import BACKEND_ROOT, get_settings

    get_settings.cache_clear()
    portable = BACKEND_ROOT.parent / ".tools" / "browsers"
    if portable.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(portable))
    # Acquire the application's lock BEFORE touching migrations. A running API keeps it.
    from app.core.database import build_engine
    from app.services.worker_lock import WorkerLock

    engine = build_engine(get_settings().database_url)
    lock = WorkerLock(str(engine.url.database))
    try:
        lock.acquire()
        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    finally:
        lock.release()
        engine.dispose()
    from app.main import app

    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="http://127.0.0.1/api/v1/",
            timeout=15,
        ) as client,
    ):
        yield client


async def execute(args):
    async with client_for(args) as client:

        async def api(method, path, data=None):
            response = await client.request(
                method, path, **({"json": data} if data is not None else {})
            )
            if not 200 <= response.status_code < 300:
                raise ValueError(
                    f"La API rechazó la operación (HTTP {response.status_code}). Revisa configuración y consentimiento."
                )
            return response.json() if response.status_code != 204 else None

        if args.command == "demo":
            project = await api(
                "POST", "projects", {"name": "Demo CLI", "base_url": DEMO_URL}
            )
            environment = await api(
                "POST",
                f"projects/{project['id']}/environments",
                {"name": "Demo integrada", "kind": "demo", "base_url": DEMO_URL},
            )
            suite = await api(
                "POST", f"projects/{project['id']}/suites", {"name": "Verificación CLI"}
            )
            for position, definition in enumerate(
                [
                    {
                        "type": "http_status",
                        "path": "/about",
                        "minimum": 200,
                        "maximum": 200,
                    },
                    {"type": "title", "path": "/about", "expected_title": "Acerca de"},
                    {"type": "element_exists", "path": "/about", "selector": "h1"},
                    {"type": "no_js_errors", "path": "/about"},
                ]
            ):
                await api(
                    "POST",
                    f"suites/{suite['id']}/cases",
                    {
                        "name": definition["type"],
                        "position": position,
                        "definition": definition,
                    },
                )
            suite_id, environment_id, origin = (
                suite["id"],
                environment["id"],
                environment["authorized_origin"],
            )
        else:
            suite = await api("GET", f"suites/{args.suite}")
            if suite["project_id"] != str(args.project):
                raise ValueError("La suite no pertenece al proyecto indicado.")
            suite_id, environment_id, origin = (
                str(args.suite),
                str(args.environment),
                args.origin,
            )
        run = await api(
            "POST",
            f"suites/{suite_id}/runs",
            {
                "environment_id": environment_id,
                "authorize": True,
                "consent_origin": origin,
            },
        )
        deadline, previous, interrupted = time.monotonic() + args.timeout, None, False
        result = None
        try:
            while True:
                result = await api("GET", f"runs/{run['id']}/suite-results")
                progress = (result["run"]["status"], result["counts"])
                if progress != previous:
                    print(
                        f"{run['id']} · {progress[0]} · {progress[1]}",
                        file=sys.stderr,
                        flush=True,
                    )
                    previous = progress
                if result["run"]["status"] not in {"pending", "running"}:
                    break
                if time.monotonic() >= deadline:
                    interrupted = True
                    await api("POST", f"runs/{run['id']}/cancel")
                    # Wait for cleanup before returning, bounded independently.
                    for _ in range(100):
                        result = await api("GET", f"runs/{run['id']}/suite-results")
                        if result["run"]["status"] not in {"pending", "running"}:
                            break
                        await asyncio.sleep(0.1)
                    break
                await asyncio.sleep(0.25)
        except (asyncio.CancelledError, KeyboardInterrupt):
            await api("POST", f"runs/{run['id']}/cancel")
            raise
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return 3 if interrupted else exit_code(result)


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if not args.authorize:
        argument_parser.error("Se requiere --authorize para cada ejecución.")
    if args.database and not args.standalone:
        argument_parser.error("--database requiere --standalone.")
    if args.command == "test" and not all(
        [args.project, args.suite, args.environment, args.origin]
    ):
        argument_parser.error(
            "test requiere --project, --suite, --environment y --origin."
        )
    try:
        return asyncio.run(execute(args))
    except KeyboardInterrupt:
        return 3
    except (httpx2.HTTPError, ValueError, RuntimeError, OSError, SQLAlchemyError):
        print(
            "No se pudo completar la ejecución. Revisa la API local, la configuración, el consentimiento y el bloqueo de la base de datos.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
