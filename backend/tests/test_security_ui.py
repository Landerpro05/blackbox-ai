import pytest
from app.core.config import BACKEND_ROOT
from auth_support import EMAIL, PASSWORD
from playwright.sync_api import expect, sync_playwright
from test_browser_ui import local_application as local_application  # noqa: PLC0414 — explicit pytest fixture re-export


@pytest.mark.browser
def test_login_workspace_cache_role_change_password_and_logout(
    local_application, tmp_path
):
    ui_url, api_url = local_application
    artifacts = BACKEND_ROOT.parent / ".tools/qa"
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
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
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(ui_url + "/projects")
            page.wait_for_url(ui_url + "/login")
            expect(
                page.get_by_role("heading", name="Iniciar sesión", exact=True)
            ).to_be_visible()
            page.screenshot(path=artifacts / "phase7-login-desktop.png", full_page=True)
            page.get_by_label("Correo electrónico", exact=True).fill(EMAIL)
            page.get_by_label("Contraseña", exact=True).fill(PASSWORD)
            page.get_by_role("button", name="Entrar", exact=True).click()
            page.wait_for_url(ui_url + "/")
            expect(page.get_by_label("Workspace activo", exact=True)).to_have_value(
                "local"
            )
            cookies = context.cookies(api_url)
            session = next(c for c in cookies if c["name"] == "blackbox_session")
            assert session["httpOnly"] and session["sameSite"] == "Strict"
            assert page.evaluate(
                "!document.cookie.includes('blackbox_session') && localStorage.length === 0"
            )
            identity = context.request.get(api_url + "/api/v1/auth/session").json()
            headers = {
                "Origin": ui_url,
                "X-Blackbox-Request": "1",
                "X-CSRF-Token": identity["csrf_token"],
                "X-Workspace-ID": "local",
            }
            project = context.request.post(
                api_url + "/api/projects",
                headers=headers,
                data={
                    "name": "Solo workspace original",
                    "base_url": "http://blackbox-demo.invalid/",
                },
            ).json()
            page.goto(ui_url + "/projects")
            expect(
                page.get_by_text("Solo workspace original", exact=True)
            ).to_be_visible()
            page.goto(ui_url + "/account")
            expect(
                page.get_by_role("heading", name="Sesiones", exact=True)
            ).to_be_visible()
            page.get_by_label("Nombre del nuevo workspace", exact=True).fill(
                "Workspace aislado"
            )
            page.get_by_role("button", name="Crear workspace", exact=True).click()
            expect(page.get_by_text("Workspace creado.", exact=True)).to_be_visible()
            page.get_by_label("Workspace activo", exact=True).select_option(
                label="Workspace aislado"
            )
            page.wait_for_url(ui_url + "/")
            page.goto(ui_url + "/projects")
            expect(
                page.get_by_text("Solo workspace original", exact=True)
            ).to_have_count(0)
            page.screenshot(
                path=artifacts / "phase7-workspace-isolation.png", full_page=True
            )
            page.get_by_label("Workspace activo", exact=True).select_option("local")
            page.wait_for_url(ui_url + "/")
            page.goto(ui_url + "/projects")
            expect(
                page.get_by_text("Solo workspace original", exact=True)
            ).to_be_visible()
            # Controlled invitation and signup create a real viewer membership.
            invitation = context.request.post(
                api_url + "/api/v1/workspaces/local/invitations",
                headers=headers,
                data={"email": "viewer@example.com", "role": "viewer"},
            )
            assert invitation.status == 201
            registered = context.request.post(
                api_url + "/api/v1/auth/register",
                headers={"Origin": ui_url, "X-Blackbox-Request": "1"},
                data={
                    "email": "viewer@example.com",
                    "password": PASSWORD,
                    "invitation": invitation.json()["invitation"],
                },
            )
            assert registered.status == 201
            page.reload()
            expect(page.get_by_text("Solo lectura:", exact=False)).to_be_visible()
            page.goto(ui_url + "/projects/new")
            expect(page.get_by_role("alert")).to_contain_text("Acceso denegado")
            page.goto(ui_url + "/lab?project=" + project["id"])
            expect(
                page.get_by_role("button", name="Crear entorno", exact=True)
            ).to_be_disabled()
            page.goto(ui_url + "/account")
            expect(
                page.get_by_role("heading", name="Permisos de tu rol", exact=True)
            ).to_be_visible()
            expect(
                page.get_by_role("heading", name="Sesiones", exact=True)
            ).to_be_visible()
            page.screenshot(
                path=artifacts / "phase7-account-desktop.png", full_page=True
            )
            page.get_by_label("Contraseña actual", exact=True).fill(PASSWORD)
            page.get_by_label("Nueva contraseña", exact=True).fill(
                "New-security-password-123"
            )
            page.get_by_role(
                "button", name="Actualizar contraseña y revocar sesiones", exact=True
            ).click()
            page.wait_for_url(ui_url + "/login")
            expect(
                page.get_by_text("Contraseña actualizada.", exact=False)
            ).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=artifacts / "phase7-login-mobile.png", full_page=True)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth + 1"
            )
            page.get_by_label("Correo electrónico", exact=True).fill(
                "viewer@example.com"
            )
            page.get_by_label("Contraseña", exact=True).fill(
                "New-security-password-123"
            )
            page.get_by_role("button", name="Entrar", exact=True).click()
            page.wait_for_url(ui_url + "/")
            # Expire the persisted session while React still considers it valid.
            page.wait_for_load_state("networkidle")
            import sqlite3

            with sqlite3.connect(tmp_path / "test.db") as db:
                db.execute(
                    "UPDATE auth_sessions SET expires_at='2000-01-01 00:00:00' WHERE user_id IN (SELECT id FROM users WHERE email='viewer@example.com') AND revoked_at IS NULL"
                )
            page.get_by_role("button", name="Abrir menú", exact=True).click()
            page.get_by_role("link", name="Proyectos", exact=True).click()
            page.wait_for_url(ui_url + "/login")
            expect(
                page.get_by_text("La sesión ha terminado.", exact=False)
            ).to_be_visible()
            expect(
                page.get_by_text("Solo workspace original", exact=True)
            ).to_have_count(0)
            page.get_by_label("Correo electrónico", exact=True).fill(
                "viewer@example.com"
            )
            page.get_by_label("Contraseña", exact=True).fill(
                "New-security-password-123"
            )
            page.get_by_role("button", name="Entrar", exact=True).click()
            page.wait_for_url(ui_url + "/")
            page.get_by_role("button", name="Abrir menú", exact=True).click()
            page.get_by_role("button", name="Cerrar sesión", exact=True).click()
            page.wait_for_url(ui_url + "/login")
            assert not any(
                c["name"] == "blackbox_session" for c in context.cookies(api_url)
            )
            assert not errors, errors
        finally:
            browser.close()
