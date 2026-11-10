"""End-to-end tests of our local React application and controlled demo engine.

Only disposable databases and loopback servers are used; no public target tests.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from app.core.config import BACKEND_ROOT


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stop_owned(process):
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=False,
            )
        else:
            process.terminate()
        process.wait(timeout=15)


def wait_http(url, process):
    for _ in range(150):
        if process.poll() is not None:
            raise AssertionError(
                "The local verification server exited before becoming ready."
            )
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            time.sleep(0.1)
    raise AssertionError(f"Local verification server unavailable: {url}")


@pytest.fixture
def local_application(tmp_path, monkeypatch):
    root = BACKEND_ROOT.parent
    frontend = root / "frontend"
    node = root / ".tools" / "node" / "node.exe"
    if not node.is_file():
        node = shutil.which("node")
    if (
        not node
        or not (frontend / "node_modules" / "vite" / "bin" / "vite.js").is_file()
    ):
        pytest.skip(
            "Install Node.js and frontend dependencies to run the local browser UI test."
        )
    browsers = root / ".tools" / "browsers"
    if browsers.is_dir() and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    api_port, ui_port = free_port(), free_port()
    api_url, ui_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    environment = {
        **os.environ,
        "BLACKBOX_ENVIRONMENT": "test",
        "BLACKBOX_DATABASE_URL": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "BLACKBOX_EVIDENCE_DIR": str(tmp_path / "evidence"),
        "BLACKBOX_DEMO_TESTING_ENABLED": "true",
        "BLACKBOX_LOCAL_LAB_ENABLED": "false",
        "BLACKBOX_LOCAL_LAB_ALLOWED_ORIGINS": "[]",
        "BLACKBOX_AI_PROVIDER": "disabled",
        "BLACKBOX_AI_API_KEY": "",
        "BLACKBOX_AI_MODEL": "",
        "BLACKBOX_CORS_ORIGINS": json.dumps([ui_url]),
        "VITE_API_BASE_URL": f"{api_url}/api/v1",
    }
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        **flags,
    )
    assert migration.returncode == 0, migration.stderr
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--workers",
            "1",
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **flags,
    )
    ui = None
    try:
        wait_http(f"{api_url}/api/v1/health", api)
        ui = subprocess.Popen(
            [
                str(node),
                str(frontend / "node_modules" / "vite" / "bin" / "vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                str(ui_port),
                "--strictPort",
            ],
            cwd=frontend,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **flags,
        )
        wait_http(ui_url, ui)
        yield ui_url, api_url
    finally:
        if ui:
            stop_owned(ui)
        stop_owned(api)


@pytest.mark.browser
def test_react_start_results_filters_screenshots_mobile_and_cancellation(
    local_application,
):
    from playwright.sync_api import sync_playwright, expect

    ui_url, api_url = local_application
    errors = []
    blocked = []
    artifacts = BACKEND_ROOT.parent / ".tools" / "qa"
    artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1080})

            def own_servers_only(route):
                if route.request.url.startswith((ui_url + "/", api_url + "/")):
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()

            context.route("**/*", own_servers_only)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ui_url + "/projects")
            page.get_by_role(
                "button", name="Crear proyecto de demostración", exact=True
            ).click()
            expect(
                page.get_by_role(
                    "heading", name="Demostración BLACKBOX AI", exact=False
                )
            ).to_be_visible()
            project_url = page.url
            page.get_by_label("Páginas máximas", exact=True).fill("7")
            page.get_by_label("Timeout de navegación (s)", exact=True).fill("1")
            page.get_by_label("Autorizo analizar únicamente").check()
            page.get_by_role("button", name="Iniciar análisis", exact=True).click()
            page.wait_for_url(re.compile(r"/runs/[0-9a-f-]+$"))
            completed_url = page.url
            expect(
                page.get_by_role("heading", name="Resultados del análisis", exact=False)
            ).to_be_visible(timeout=30000)
            expect(page.locator(".run-progress .status-pill")).to_have_text(
                "Completado"
            )
            expect(page.locator(".evidence-card")).to_have_count(7)
            assert page.locator(".issue-card").count() > 0
            page.get_by_label("Severidad", exact=False).select_option("high")
            assert page.locator(".issue-card").count() > 0
            assert all(
                value == "Alta"
                for value in page.locator(
                    ".issue-card .status-pill"
                ).all_text_contents()
            )
            page.get_by_label("Severidad", exact=False).select_option("all")
            first_image = page.locator(".evidence-card img").first
            first_image.scroll_into_view_if_needed()
            expect(first_image).to_have_js_property("naturalWidth", 1280)
            form_image = (
                page.locator(".evidence-card").filter(has_text="/form").locator("img")
            )
            image_url = form_image.get_attribute("src")
            assert image_url.startswith(api_url + "/")
            image_response = page.request.get(image_url)
            assert image_response.ok
            (artifacts / "phase3-demo-form.png").write_bytes(image_response.body())
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=artifacts / "phase3-results-desktop.png")

            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function(
                "document.querySelector('.sidebar').getBoundingClientRect().right <= 0"
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(path=artifacts / "phase3-results-mobile.png")
            page.get_by_role("button", name="Abrir menú", exact=True).click()
            expect(
                page.locator('nav[aria-label="Navegación principal"]').get_by_role(
                    "link", name="Análisis", exact=True
                )
            ).to_be_visible()
            page.get_by_role("button", name="Cerrar menú", exact=True).click()

            page.goto(project_url)
            page.get_by_role("link", name="Editar", exact=True).click()
            page.get_by_label("URL base", exact=False).fill(
                "http://blackbox-demo.invalid/slow"
            )
            page.get_by_role("button", name="Guardar cambios", exact=True).click()
            page.get_by_label("Autorizo analizar únicamente").check()
            page.get_by_role("button", name="Iniciar análisis", exact=True).click()
            page.wait_for_url(re.compile(r"/runs/[0-9a-f-]+$"))
            page.get_by_role("button", name="Cancelar análisis", exact=True).click()
            expect(page.locator(".run-progress .status-pill")).to_have_text(
                "Cancelado", timeout=20000
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            assert not errors, errors
            assert not blocked, blocked
        finally:
            browser.close()


@pytest.mark.browser
def test_testing_lab_environment_suite_editor_execution_evidence_and_mobile(
    local_application,
):
    from playwright.sync_api import expect, sync_playwright

    ui_url, api_url = local_application
    artifacts = BACKEND_ROOT.parent / ".tools/qa"
    artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1080})
            context.route(
                "**/*",
                lambda route: (
                    route.continue_()
                    if route.request.url.startswith((ui_url + "/", api_url + "/"))
                    else route.abort()
                ),
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            project = context.request.post(
                api_url + "/api/projects",
                data={
                    "name": "Laboratorio E2E",
                    "base_url": "http://blackbox-demo.invalid/",
                },
            ).json()
            page.goto(ui_url + "/lab?project=" + project["id"])
            expect(
                page.get_by_role("heading", name="Entornos", exact=True)
            ).to_be_visible()
            page.get_by_label("Nombre del entorno", exact=True).fill("Demo E2E")
            page.get_by_label("Tipo", exact=True).select_option("demo")
            page.get_by_role("button", name="Crear entorno", exact=True).click()
            expect(page.get_by_text("Entorno guardado.", exact=True)).to_be_visible()
            page.get_by_role("button", name="Comprobar", exact=True).click()
            page.get_by_role(
                "button", name="Autorizar comprobación", exact=True
            ).click()
            expect(page.get_by_text("Catálogo verificado.", exact=True)).to_be_visible()
            page.get_by_role("button", name="Test Suites", exact=True).click()
            page.get_by_label("Nombre de la suite", exact=True).fill(
                "Comprobaciones E2E"
            )
            page.get_by_role("button", name="Crear suite", exact=True).click()
            expect(
                page.get_by_role("heading", name="Comprobaciones E2E", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Añadir caso", exact=True).click()
            page.get_by_label("Nombre del caso", exact=True).fill("Título correcto")
            page.get_by_label("Tipo de prueba", exact=True).select_option("title")
            page.get_by_label("Título esperado", exact=True).fill("Acerca de")
            page.get_by_role("button", name="Guardar caso", exact=True).click()
            expect(page.get_by_text("Caso guardado.", exact=True)).to_be_visible()
            page.get_by_role("button", name="Añadir caso", exact=True).click()
            page.get_by_label("Nombre del caso", exact=True).fill("Título incorrecto")
            page.get_by_label("Tipo de prueba", exact=True).select_option("title")
            page.get_by_label("Título esperado", exact=True).fill("No coincide")
            page.get_by_role("button", name="Guardar caso", exact=True).click()
            expect(page.get_by_text("1. Título incorrecto", exact=True)).to_be_visible()
            page.get_by_label("Entorno autorizado", exact=True).select_option(
                label="Demo E2E · ready"
            )
            expect(
                page.get_by_role("button", name="Ejecutar suite autorizada", exact=True)
            ).to_be_disabled()
            page.get_by_label(
                "Autorizo esta ejecución de solo lectura", exact=False
            ).check()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=artifacts / "phase6-lab-desktop.png", full_page=True)
            page.get_by_role(
                "button", name="Ejecutar suite autorizada", exact=True
            ).click()
            page.wait_for_url(re.compile(r"/runs/[0-9a-f-]+$"))
            results_url = page.url
            results = page.get_by_role(
                "region", name="Resultados de la suite", exact=True
            )
            expect(results.get_by_text("pass: 1", exact=True)).to_be_visible(
                timeout=30000
            )
            expect(results.get_by_text("fail: 1", exact=True)).to_be_visible()
            expect(
                results.get_by_role("link", name="Evidencia", exact=True)
            ).to_have_count(2)
            results.get_by_label("Mostrar solo fallos y errores", exact=True).check()
            expect(
                results.get_by_role("link", name="Evidencia", exact=True)
            ).to_have_count(1)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().right <= 0")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(
                path=artifacts / "phase6-results-mobile.png", full_page=True
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            page.goto(ui_url + "/lab?project=" + project["id"])
            page.get_by_role("button", name="Integración CI/CD", exact=True).click()
            expect(
                page.get_by_text("Estado remoto: sin consultar.", exact=False)
            ).to_be_visible()
            page.get_by_role("button", name="Test Suites", exact=True).click()
            page.get_by_role("button", name="Comprobaciones E2E", exact=True).click()
            expect(
                page.get_by_role("link", name=re.compile("Completado"))
            ).to_be_visible()
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=artifacts / "phase6-lab-mobile.png", full_page=True)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            assert not errors, errors
            assert results_url
        finally:
            browser.close()


@pytest.mark.browser
def test_phase4_downloads_analytics_comparison_and_offline_html(local_application):
    from playwright.sync_api import sync_playwright, expect
    from pypdf import PdfReader

    ui_url, api_url = local_application
    artifacts = BACKEND_ROOT.parent / ".tools" / "qa"
    artifacts.mkdir(parents=True, exist_ok=True)
    errors, blocked = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
        try:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1080}, accept_downloads=True
            )

            def own_servers_only(route):
                if route.request.url.startswith((ui_url + "/", api_url + "/")):
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()

            context.route("**/*", own_servers_only)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ui_url + "/projects")
            page.get_by_role(
                "button", name="Crear proyecto de demostración", exact=True
            ).click()
            expect(
                page.get_by_role(
                    "heading", name="Demostración BLACKBOX AI", exact=False
                )
            ).to_be_visible()
            project_url = page.url
            project_id = project_url.rsplit("/", 1)[-1]
            run_urls = []
            for _ in range(2):
                page.get_by_label("Páginas máximas", exact=True).fill("1")
                page.get_by_label("Autorizo analizar únicamente").check()
                page.get_by_role("button", name="Iniciar análisis", exact=True).click()
                page.wait_for_url(re.compile(r"/runs/[0-9a-f-]+$"))
                expect(page.locator(".run-progress .status-pill")).to_have_text(
                    "Completado", timeout=30000
                )
                run_urls.append(page.url)
                expect(
                    page.get_by_role("button", name="Descargar PDF", exact=True)
                ).to_be_visible()
                if len(run_urls) == 1:
                    page.goto(project_url)

            panel = page.get_by_role("region", name="Informe de ejecución", exact=True)
            expect(panel.locator(".severity-summary > div")).to_have_count(5)
            page.get_by_label("Incluir capturas en HTML y PDF").check()
            for extension in ("html", "pdf", "json", "csv"):
                with page.expect_download() as download_info:
                    page.get_by_role(
                        "button", name=f"Descargar {extension.upper()}", exact=True
                    ).click()
                download = download_info.value
                assert download.failure() is None
                path = artifacts / f"phase4-report.{extension}"
                download.save_as(path)
                assert path.stat().st_size > 0
                assert download.suggested_filename.endswith("." + extension)
            pdf = PdfReader(artifacts / "phase4-report.pdf")
            assert len(pdf.pages) >= 3
            assert any("Excepción JavaScript" in p.extract_text() for p in pdf.pages)
            exported = json.loads((artifacts / "phase4-report.json").read_text("utf-8"))
            assert exported["summary"]["pages"] == 1
            assert exported["summary"]["issues"] > 0
            assert "demo-secret-123" not in (
                artifacts / "phase4-report.html"
            ).read_text("utf-8")
            page.screenshot(path=artifacts / "phase4-run-desktop.png", full_page=True)

            page.goto(project_url)
            expect(
                page.get_by_role(
                    "img",
                    name="Evolución real de incidencias y navegación por ejecución",
                )
            ).to_be_visible()
            expect(page.locator(".project-analytics .report-facts")).to_contain_text(
                "Ejecuciones2"
            )
            page.locator(".project-analytics").scroll_into_view_if_needed()
            page.screenshot(path=artifacts / "phase4-analytics-desktop.png")
            page.get_by_role(
                "link", name="Comparar ejecuciones del proyecto", exact=False
            ).click()
            expect(page.get_by_label("Proyecto para comparar")).to_have_value(
                project_id
            )
            page.get_by_role("button", name="Comparar ejecuciones", exact=True).click()
            expect(
                page.get_by_role(
                    "heading", name="Resultado de la comparación", exact=True
                )
            ).to_be_visible()
            expect(page.locator(".comparison-issue")).to_have_count(
                exported["summary"]["issues"]
            )
            page.get_by_label("Clasificación", exact=True).select_option("NEW")
            expect(
                page.get_by_text("Sin incidencias en esta clasificación.", exact=True)
            ).to_be_visible()
            page.get_by_label("Clasificación", exact=True).select_option("PERSISTENT")
            expect(page.locator(".comparison-issue")).to_have_count(
                exported["summary"]["issues"]
            )
            page.screenshot(
                path=artifacts / "phase4-comparison-desktop.png", full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function(
                "document.querySelector('.sidebar').getBoundingClientRect().right <= 0"
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(
                path=artifacts / "phase4-comparison-mobile.png", full_page=True
            )
            page.goto(run_urls[1])
            expect(
                page.get_by_role("button", name="Descargar PDF", exact=True)
            ).to_be_visible()
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(path=artifacts / "phase4-run-mobile.png", full_page=True)

            # Open the actual downloaded HTML locally with every HTTP request blocked.
            offline = browser.new_context(offline=True)
            offline_page = offline.new_page()
            external_requests = []
            offline_page.on(
                "request",
                lambda request: (
                    external_requests.append(request.url)
                    if request.url.startswith(("http:", "https:"))
                    else None
                ),
            )
            offline_page.goto((artifacts / "phase4-report.html").as_uri())
            expect(
                offline_page.get_by_role(
                    "heading", name="Resumen ejecutivo", exact=True
                )
            ).to_be_visible()
            expect(offline_page.locator("img")).to_have_count(1)
            expect(offline_page.locator("img")).to_have_js_property(
                "naturalWidth", 1280
            )
            assert not external_requests
            offline_page.screenshot(
                path=artifacts / "phase4-offline-html.png", full_page=True
            )
            offline.close()
            assert not errors, errors
            assert not blocked, blocked
        finally:
            browser.close()


@pytest.mark.browser
def test_phase5_rules_persistence_copy_and_external_confirmation(local_application):
    from playwright.sync_api import sync_playwright, expect

    ui_url, api_url = local_application
    artifacts = BACKEND_ROOT.parent / ".tools" / "qa"
    artifacts.mkdir(parents=True, exist_ok=True)
    errors, blocked = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--disable-gpu"])
        try:
            context = browser.new_context(viewport={"width": 1440, "height": 1080})
            context.grant_permissions(
                ["clipboard-read", "clipboard-write"], origin=ui_url
            )

            def own_servers_only(route):
                if route.request.url.startswith((ui_url + "/", api_url + "/")):
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()

            context.route("**/*", own_servers_only)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ui_url + "/projects")
            page.get_by_role(
                "button", name="Crear proyecto de demostración", exact=True
            ).click()
            page.get_by_label("Páginas máximas", exact=True).fill("1")
            page.get_by_label("Autorizo analizar únicamente").check()
            page.get_by_role("button", name="Iniciar análisis", exact=True).click()
            page.wait_for_url(re.compile(r"/runs/[0-9a-f-]+$"))
            run_url = page.url
            expect(page.locator(".run-progress .status-pill")).to_have_text(
                "Completado", timeout=30000
            )
            page.get_by_role("button", name="Analizar con IA", exact=True).click()
            dialog = page.get_by_role("dialog", name="Analizar incidencias", exact=True)
            expect(dialog).to_be_visible()
            expect(dialog.get_by_label("Modo de análisis", exact=True)).to_have_value(
                "rules"
            )
            expect(
                dialog.get_by_text("LLM externo sin configurar.", exact=False)
            ).to_be_visible()
            dialog.get_by_role(
                "button", name="Iniciar interpretación", exact=True
            ).click()
            panel = page.get_by_role("region", name="AI Intelligence", exact=True)
            expect(panel.locator(".ai-state-row .status-pill")).to_have_text(
                "Completado", timeout=15000
            )
            expect(
                panel.get_by_role(
                    "heading", name="Resumen basado en reglas", exact=True
                )
            ).to_be_visible()
            expect(panel.locator(".ai-finding")).to_have_count(2)
            expect(panel.locator(".ai-test")).to_have_count(2)
            assert "synthetic-private" not in panel.inner_text()
            first_code = panel.locator(".ai-code").first.inner_text()
            assert "REEMPLAZA_POR_UN_ENTORNO_AUTORIZADO" in first_code
            panel.get_by_role("button", name="Copiar código", exact=True).first.click()
            expect(
                panel.get_by_role("button", name="Copiado", exact=True)
            ).to_be_visible()
            assert (
                page.evaluate("navigator.clipboard.readText()").replace("\r\n", "\n")
                == first_code
            )
            panel.locator(".ai-finding .ai-citations a").first.click()
            expect(panel.locator(".ai-evidence-list")).to_be_visible()
            panel.scroll_into_view_if_needed()
            page.screenshot(path=artifacts / "phase5-rules-desktop.png", full_page=True)
            panel.locator(".ai-finding").first.screenshot(
                path=artifacts / "phase5-finding-desktop.png"
            )
            panel.locator(".ai-test").first.screenshot(
                path=artifacts / "phase5-test-desktop.png"
            )
            detail_link = panel.get_by_role(
                "link", name="Abrir interpretación", exact=False
            )
            detail_url = detail_link.get_attribute("href")
            page.goto(ui_url + detail_url)
            expect(
                page.get_by_role(
                    "heading", name="Interpretación de resultados", exact=False
                )
            ).to_be_visible()
            expect(
                page.get_by_role("heading", name="Resumen basado en reglas", exact=True)
            ).to_be_visible()
            page.reload()
            expect(page.locator(".ai-test")).to_have_count(2)
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function(
                "document.querySelector('.sidebar').getBoundingClientRect().right <= 0"
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            )
            page.screenshot(path=artifacts / "phase5-rules-mobile.png", full_page=True)
            page.locator(".ai-finding").first.screenshot(
                path=artifacts / "phase5-finding-mobile.png"
            )

            # Only the capabilities/failed-submit UI is simulated. No LLM request leaves QA.
            capabilities = page.request.get(api_url + "/api/v1/ai/capabilities").json()
            capabilities.update(
                llm_enabled=True, provider="anthropic", model="fixture-model"
            )
            page.route(
                "**/api/v1/ai/capabilities",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(capabilities),
                ),
            )
            captured = []

            def reject_external(route):
                if route.request.method == "POST":
                    captured.append(route.request.post_data_json)
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body=json.dumps({"detail": "Proveedor simulado no disponible"}),
                    )
                else:
                    route.continue_()

            page.route("**/api/v1/runs/*/ai-analysis", reject_external)
            page.goto(run_url)
            page.get_by_role("button", name="Analizar con IA", exact=True).click()
            dialog = page.get_by_role("dialog", name="Analizar incidencias", exact=True)
            dialog.get_by_label("Modo de análisis", exact=True).select_option("llm")
            expect(dialog.get_by_text("fixture-model", exact=False)).to_be_visible()
            expect(
                dialog.get_by_role("button", name="Iniciar interpretación", exact=True)
            ).to_be_disabled()
            assert not captured
            dialog.get_by_label(
                "Autorizo enviar estas evidencias redactadas", exact=False
            ).check()
            expect(
                dialog.get_by_role("button", name="Iniciar interpretación", exact=True)
            ).to_be_enabled()
            page.screenshot(
                path=artifacts / "phase5-consent-mobile.png", full_page=True
            )
            dialog.screenshot(path=artifacts / "phase5-consent-dialog.png")
            dialog.get_by_role(
                "button", name="Iniciar interpretación", exact=True
            ).click()
            expect(dialog.get_by_role("alert")).to_contain_text(
                "El servicio no está disponible"
            )
            assert captured == [
                {
                    "mode": "llm",
                    "authorize_external": True,
                    "max_findings": 5,
                    "include_history": True,
                    "consent_provider": "anthropic",
                    "consent_model": "fixture-model",
                }
            ]
            dialog.get_by_role("button", name="Cancelar", exact=True).click()
            expect(
                panel.get_by_role(
                    "heading", name="Resumen basado en reglas", exact=True
                )
            ).to_be_visible()
            assert not errors, errors
            assert not blocked, blocked
        finally:
            browser.close()
