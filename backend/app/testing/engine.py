import asyncio
import time
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urldefrag
from uuid import uuid4

from app.schemas.runs import RunLimits
from app.testing.demo import response_for
from app.testing.evidence import EvidenceStore
from app.testing.policy import (
    DemoPolicy,
    DestinationDenied,
    MAX_ISSUES,
    redact_text,
    redact_url,
)

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    kind: str
    severity: str
    title: str
    description: str
    url: str


@dataclass
class ScannedPage:
    id: str
    url: str
    status_code: int | None
    load_time_ms: int
    depth: int
    screenshot_path: str | None
    findings: list[Finding] = field(default_factory=list)


class DemoEngine:
    """One browser/context/page, with all target traffic fulfilled or aborted.

    Only bundled responses are loaded. There is no route to the real network.
    This is not a general-purpose SSRF-safe web crawler.
    """

    def __init__(self, evidence: EvidenceStore) -> None:
        self.evidence = evidence
        self.browser_connected = False
        self.requests = 0
        self.requests_exhausted = False
        self.blocked_requests = 0
        self._findings: list[Finding] = []
        self._total_findings = 0

    def finding(
        self, kind: str, severity: str, title: str, description: str, url: str
    ) -> None:
        if self._total_findings >= MAX_ISSUES:
            return
        result = Finding(
            kind, severity, title[:200], redact_text(description), redact_url(url)
        )
        if any(
            item.kind == result.kind
            and item.description == result.description
            and item.url == result.url
            for item in self._findings
        ):
            return
        self._findings.append(result)
        self._total_findings += 1

    async def run(
        self,
        run_id: str,
        target: str,
        limits: RunLimits,
        on_page: Callable[[ScannedPage, int], Awaitable[None]],
    ) -> None:
        from playwright.async_api import (
            async_playwright,
            Error,
            TimeoutError as NavigationTimeout,
        )

        policy = DemoPolicy()
        target = policy.authorize(target)
        start_task = asyncio.create_task(async_playwright().start())
        playwright = None
        browser = None
        context = None
        routing_tasks: set[asyncio.Task] = set()
        try:
            playwright = await asyncio.shield(start_task)
            browser = await playwright.chromium.launch(
                headless=True,
                timeout=15_000,
                proxy={"server": "http://127.0.0.1:9"},
                args=[
                    "--disable-gpu",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-domain-reliability",
                    "--disable-sync",
                    "--disable-extensions",
                    "--no-first-run",
                    "--metrics-recording-only",
                    "--proxy-bypass-list=<-loopback>",
                    "--host-resolver-rules=MAP * ~NOTFOUND",
                    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                ],
            )
            self.browser_connected = True
            context = await browser.new_context(
                accept_downloads=False,
                service_workers="block",
                permissions=[],
                viewport={"width": 1280, "height": 720},
                java_script_enabled=True,
            )

            async def handle_request(route):
                request = route.request
                self.requests += 1
                if self.requests > limits.max_requests:
                    self.requests_exhausted = True
                    self.finding(
                        "request_limit",
                        "info",
                        "Límite de peticiones alcanzado",
                        "Se detuvo el recorrido al alcanzar el presupuesto de peticiones.",
                        request.url,
                    )
                    await route.abort("blockedbyclient")
                    return
                try:
                    allowed = policy.authorize(request.url, request.method)
                    if (
                        request.is_navigation_request()
                        and request.frame.parent_frame is not None
                    ):
                        raise DestinationDenied("Los iframes están deshabilitados.")
                except DestinationDenied:
                    self.blocked_requests += 1
                    self.finding(
                        "request_blocked",
                        "info",
                        "Solicitud bloqueada por la política",
                        f"Destino o método no autorizado: {request.method} {redact_url(request.url)}",
                        request.url,
                    )
                    await route.abort("blockedbyclient")
                    return
                response = response_for(
                    allowed.removeprefix("http://blackbox-demo.invalid")
                )
                if response.location:
                    from urllib.parse import urljoin

                    try:
                        policy.authorize(urljoin(allowed, response.location))
                    except DestinationDenied:
                        self.blocked_requests += 1
                        self.finding(
                            "redirect_blocked",
                            "info",
                            "Redirección bloqueada",
                            "La redirección apunta a un destino no autorizado.",
                            allowed,
                        )
                        await route.fulfill(
                            status=403,
                            body="<!doctype html><html lang='es'><title>Redirección bloqueada</title><body>BLACKBOX AI: destino de redirección no autorizado.</body></html>",
                            content_type="text/html; charset=utf-8",
                        )
                        return
                if response.delay_seconds:
                    await asyncio.sleep(response.delay_seconds)
                headers = {
                    "Content-Type": response.content_type,
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                }
                if response.location:
                    headers["Location"] = response.location
                # Never continue_() or fetch(): redirects will be intercepted again.
                try:
                    await route.fulfill(
                        status=response.status, body=response.body, headers=headers
                    )
                except Error:
                    pass  # The navigation may have timed out or been cancelled.

            async def route_request(route):
                task = asyncio.current_task()
                routing_tasks.add(task)
                try:
                    await handle_request(route)
                finally:
                    routing_tasks.discard(task)

            await context.route("**/*", route_request)

            async def block_websocket(route):
                self.blocked_requests += 1
                self.finding(
                    "request_blocked",
                    "info",
                    "WebSocket bloqueado",
                    "Las conexiones WebSocket están deshabilitadas.",
                    route.url,
                )
                await route.close(code=1008, reason="Demo-only policy")

            await context.route_web_socket("**/*", block_websocket)
            page = await context.new_page()

            def configure_page(current):
                current.on("popup", lambda popup: popup.close())
                current.on("dialog", lambda dialog: dialog.dismiss())
                current.on("download", lambda download: download.cancel())
                current.on(
                    "pageerror",
                    lambda error: self.finding(
                        "javascript",
                        "high",
                        "Excepción JavaScript no controlada",
                        str(error),
                        current.url,
                    ),
                )
                current.on(
                    "console",
                    lambda message: (
                        self.finding(
                            "console",
                            "medium",
                            "Error de consola",
                            message.text,
                            current.url,
                        )
                        if message.type == "error"
                        else None
                    ),
                )
                current.on(
                    "response",
                    lambda response: (
                        self.finding(
                            "http",
                            "high" if response.status >= 500 else "medium",
                            f"Respuesta HTTP {response.status}",
                            f"Un subrecurso devolvió HTTP {response.status}.",
                            response.url,
                        )
                        if response.status >= 400
                        and response.request.resource_type != "document"
                        else None
                    ),
                )

            configure_page(page)

            queue = deque([(target, 0)])
            visited: set[str] = set()
            scheduled = {target}
            while (
                queue
                and len(visited) < limits.max_pages
                and not self.requests_exhausted
            ):
                url, depth = queue.popleft()
                if url in visited:
                    continue
                visited.add(url)
                self._findings = []
                started = time.monotonic()
                status = None
                navigated = False
                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=limits.navigation_timeout_seconds * 1000,
                    )
                    status = response.status if response else None
                    navigated = True
                    if status and status >= 400:
                        self.finding(
                            "broken_link" if depth > 0 and status == 404 else "http",
                            "high" if status >= 500 else "medium",
                            f"Respuesta HTTP {status}",
                            f"La página devolvió HTTP {status}.",
                            url,
                        )
                    await page.wait_for_timeout(100)
                except NavigationTimeout:
                    self.finding(
                        "navigation_timeout",
                        "high",
                        "Timeout de navegación",
                        "La página superó el tiempo de navegación permitido.",
                        url,
                    )
                except Error as error:
                    logger.debug("Navigation failure: %s", redact_text(str(error)))
                    self.finding(
                        "navigation",
                        "medium",
                        "Fallo de navegación",
                        "No se pudo completar la navegación. Consulta las solicitudes bloqueadas y la política de destinos.",
                        url,
                    )
                if not navigated:
                    for task in list(routing_tasks):
                        task.cancel()
                    if routing_tasks:
                        await asyncio.gather(
                            *list(routing_tasks), return_exceptions=True
                        )
                    # Replace a failed tab after closing it; never keep two tabs alive.
                    await page.close()
                    page = await context.new_page()
                    configure_page(page)
                load_time = max(0, int((time.monotonic() - started) * 1000))
                links: list[str] = []
                screenshot = None
                page_id = str(uuid4())
                if navigated:
                    try:
                        unlabeled = await page.locator(
                            "input:not([type=hidden]):not([type=submit]),textarea,select"
                        ).evaluate_all(
                            "elements => elements.filter(e => !e.labels?.length && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby')).length"
                        )
                        if unlabeled:
                            self.finding(
                                "form_label",
                                "low",
                                "Campos sin etiqueta accesible",
                                f"Se encontraron {unlabeled} campos sin etiqueta. Solo se inspeccionó el formulario; no se enviaron datos.",
                                url,
                            )
                        links = await page.locator("a[href]").evaluate_all(
                            "elements => elements.slice(0, 200).map(e => e.href)"
                        )
                        # Known demo-sensitive text and all field values are masked.
                        image = await page.screenshot(
                            type="png",
                            full_page=False,
                            timeout=3000,
                            mask=[
                                page.locator("input,textarea,select,[data-sensitive]")
                            ],
                            mask_color="#24324a",
                        )
                        screenshot = self.evidence.save(run_id, page_id, image)
                    except Error:
                        self.finding(
                            "evidence",
                            "low",
                            "Captura no disponible",
                            "No se pudo capturar la página dentro del tiempo permitido.",
                            url,
                        )
                result = ScannedPage(
                    page_id,
                    redact_url(url),
                    status,
                    load_time,
                    depth,
                    screenshot,
                    self._findings.copy(),
                )
                await on_page(result, min(self.requests, limits.max_requests))
                if depth < limits.max_depth:
                    for link in links:
                        clean = urldefrag(link)[0]
                        if policy.navigable(clean):
                            clean = policy.authorize(clean)
                            if clean not in scheduled:
                                scheduled.add(clean)
                                queue.append((clean, depth + 1))
                        if len(scheduled) >= 200:
                            break
        finally:
            # Shield driver startup so cancellation can still stop its subprocess.
            if playwright is None:
                try:
                    playwright = await asyncio.shield(start_task)
                except Exception:
                    playwright = None
            for task in list(routing_tasks):
                task.cancel()
            if routing_tasks:
                await asyncio.gather(*list(routing_tasks), return_exceptions=True)
            try:
                if context is not None:
                    await asyncio.wait_for(context.close(), 5)
            except Exception:
                pass
            try:
                if browser is not None:
                    await asyncio.wait_for(browser.close(), 5)
            finally:
                if playwright is not None:
                    await playwright.stop()
                self.browser_connected = bool(browser and browser.is_connected())
