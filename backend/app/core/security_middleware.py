import asyncio
import json
import logging
import time
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger("blackbox.security")


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        settings = get_settings()
        request = Request(scope)
        identifier = str(uuid4())

        async def reject(message, status):
            logger.info(
                json.dumps(
                    {
                        "event": "http.rejected",
                        "request_id": identifier,
                        "status": status,
                    }
                )
            )
            headers = {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                "Referrer-Policy": "no-referrer",
                "X-Request-ID": identifier,
            }
            return await JSONResponse({"detail": message}, status, headers=headers)(
                scope, receive, send
            )

        if request.url.hostname not in settings.api_hosts:
            return await reject("Host no autorizado.", 400)
        if settings.deployment_mode == "https" and request.url.scheme != "https":
            return await reject("Se requiere HTTPS.", 400)
        if settings.deployment_mode == "https" and request.url.path in {
            "/docs",
            "/redoc",
            "/openapi.json",
        }:
            return await reject("Recurso no disponible.", 404)
        try:
            if (
                request.headers.get("content-length")
                and int(request.headers["content-length"]) > settings.max_body_bytes
            ):
                return await reject("Cuerpo demasiado grande.", 413)
        except ValueError:
            return await reject("Longitud no válida.", 400)
        # Read and cap the actual stream as well; Content-Length is not trusted.
        messages, size = [], 0
        deadline = time.monotonic() + settings.body_timeout_seconds
        while True:
            try:
                message = await asyncio.wait_for(
                    receive(), max(0, deadline - time.monotonic())
                )
            except TimeoutError:
                return await reject("Se agotó el tiempo para recibir el cuerpo.", 408)
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > settings.max_body_bytes:
                return await reject("Cuerpo demasiado grande.", 413)
            messages.append(message)
            if not message.get("more_body", False):
                break
        position = 0

        async def replay():
            nonlocal position
            if position < len(messages):
                message = messages[position]
                position += 1
                return message
            return await receive()

        status = 500

        async def secured_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                additions = {
                    "cache-control": "no-store",
                    "x-content-type-options": "nosniff",
                    "referrer-policy": "no-referrer",
                    "x-frame-options": "DENY",
                    "permissions-policy": "camera=(), microphone=(), geolocation=()",
                    "x-request-id": identifier,
                    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                }
                if settings.deployment_mode == "https":
                    additions["strict-transport-security"] = "max-age=31536000"
                elif request.url.path in {"/docs", "/redoc"}:
                    additions["content-security-policy"] = (
                        "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
                    )
                headers.extend(
                    (key.encode(), value.encode())
                    for key, value in additions.items()
                    if key.encode() not in existing
                )
                message = {**message, "headers": headers}
            await send(message)

        limiter = getattr(scope.get("app").state, "rate_limiter", None)
        if limiter and request.url.path.startswith("/api/"):
            try:
                limiter.check(
                    (
                        "api",
                        "local"
                        if settings.deployment_mode == "local"
                        else request.client.host
                        if request.client
                        else "unknown",
                    ),
                    settings.api_requests_per_minute,
                    60,
                )
            except HTTPException as error:
                return await JSONResponse(
                    {"detail": error.detail}, error.status_code, headers=error.headers
                )(scope, replay, secured_send)
        started = time.monotonic()
        try:
            await self.app(scope, replay, secured_send)
        finally:
            route = scope.get("route")
            logger.info(
                json.dumps(
                    {
                        "event": "http.request",
                        "request_id": identifier,
                        "method": scope["method"],
                        "route": route.path if route else "unmatched",
                        "status": status,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    }
                )
            )
