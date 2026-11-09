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
