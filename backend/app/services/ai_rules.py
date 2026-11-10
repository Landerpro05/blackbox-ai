"""Transparent diagnostic rules and trusted Playwright templates, never execution."""

import json
from urllib.parse import urlsplit

from app.schemas.intelligence import EngineResult, Finding, StoredResult, TestPlan

RULES = {
    "suite_assertion": ("La comprobación declarada no coincide con el resultado observado.", "Revisa la expectativa del caso y la evidencia de su ejecución.", "Corrige el comportamiento o ajusta una expectativa únicamente si estaba equivocada.", None),
    "suite_error": ("La comprobación no pudo completarse dentro de los límites o de la política.", "Revisa disponibilidad, timeouts y el origen autorizado antes de repetir.", "Soluciona el bloqueo de ejecución antes de interpretar la ausencia de un fallo.", None),
    "http": (
        "La respuesta HTTP observada puede indicar una ruta inexistente o un fallo del servidor.",
        "Comprueba el código HTTP, la ruta y los logs del servidor en tu entorno autorizado.",
        "Revisa el enrutamiento o el manejo de errores de esa respuesta.",
        "http_status",
    ),
    "broken_link": (
        "El destino del enlace puede no existir o haber cambiado de ruta.",
        "Revisa el destino del enlace y las rutas publicadas.",
        "Actualiza el enlace o restaura la ruta prevista.",
        "http_status",
    ),
    "javascript": (
        "Una excepción JavaScript puede interrumpir parte del comportamiento de la página.",
        "Reproduce el flujo en un entorno propio y revisa la traza con sus mapas de código.",
        "Inspecciona la operación que lanza la excepción y añade manejo del caso fallido.",
        "no_page_errors",
    ),
    "console": (
        "Un mensaje de consola puede señalar un fallo de la aplicación o de una dependencia.",
        "Identifica qué operación produce el mensaje y revisa sus dependencias.",
        "Corrige el origen del mensaje después de reproducirlo.",
        "no_console_errors",
    ),
    "navigation_timeout": (
        "La navegación puede exceder el presupuesto por lentitud o una espera que no termina.",
        "Mide la carga y revisa solicitudes pendientes en un entorno propio.",
        "Investiga el recurso lento antes de ajustar el timeout.",
        None,
    ),
    "form_label": (
        "Puede haber campos sin una etiqueta accesible asociada.",
        "Inspecciona los campos y sus etiquetas en el DOM.",
        "Asocia etiquetas accesibles a los campos que las necesiten.",
        None,
    ),
}
GENERAL = (
    "La información registrada no permite atribuir una causa técnica concreta.",
    "Consulta el tipo, URL y mensajes disponibles; recopila más evidencia en un entorno autorizado.",
    "No apliques cambios sin reproducir y aislar el comportamiento.",
    None,
)
TEMPLATE_KINDS = {
    "http_status": {"http", "broken_link"},
    "no_page_errors": {"javascript"},
    "no_console_errors": {"console"},
}


def test_source(template: str, ids: list[str], issues: dict) -> dict | None:
    for key in ids:
        issue = issues.get(key)
        if not issue or issue["type"] not in TEMPLATE_KINDS[template]:
            continue
        try:
            parsed = urlsplit(issue["url"])
            if (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and not any(
                    marker in issue["url"]
                    for marker in ("[REDACTADO]", "[correo oculto]", "[ruta omitida]")
                )
            ):
                return issue
        except ValueError:
            continue
    return None


def analyze_rules(evidence: dict, max_findings: int) -> EngineResult:
    by_id = {issue["id"]: issue for issue in evidence["issues"]}
    findings, tests = [], []
    for group in evidence["groups"][:max_findings]:
        ids = group["evidence_ids"][:10]
        issue = by_id[ids[0]]
        cause, diagnostic, recommendation, template = RULES.get(issue["type"], GENERAL)
        if issue["quarantined"]:
            cause, diagnostic, recommendation, template = GENERAL
        limitation = "Hipótesis sin confirmar: no hay código fuente ni traza completa que establezca la causa."
        findings.append(
            Finding(
                hypothesis=cause,
                confidence="low",
                evidence_ids=ids,
                diagnostic_steps=[diagnostic],
                recommendations=[recommendation],
                limitations=[limitation],
            )
        )
        if template and test_source(template, ids, by_id):
            tests.append(
                TestPlan(
                    template=template,
                    objective="Comprobar que el comportamiento observado no se reproduce tras una corrección revisada.",
                    evidence_ids=ids,
                    preconditions=[
                        "Disponer de un entorno propio autorizado y pytest-playwright instalado.",
                        "Sustituir BASE_URL por el entorno autorizado; la demo virtual solo existe dentro del motor.",
                    ],
                    actions=["Abrir la ruta registrada en una página nueva."],
                    assertions=[
                        "No observar el error registrado durante la navegación inicial."
                    ],
                    limitations=[
                        "Plantilla no ejecutada. No cubre interacciones que no hayan sido registradas.",
                        "Los listeners durante la navegación no prueban ausencia de errores posteriores.",
                    ],
                )
            )
    return EngineResult(
        summary=f"Análisis basado en reglas: {evidence['summary']['issues']} incidencias registradas, {len(evidence['issues'])} incluidas en el contexto y {len(evidence['groups'])} grupos deterministas. Las posibles causas no están confirmadas.",
        findings=findings,
        recommendations=["Reproduce cada hallazgo antes de aplicar una corrección."],
        suggested_tests=tests,
        hypothetical_relations=[],
        limitations=[
            "Diagnóstico por reglas, sin modelo generativo ni acceso al código fuente.",
            f"Contexto acotado: {evidence['omitted_issues']} incidencias y {evidence['omitted_pages']} páginas omitidas.",
            "El análisis no aplica arreglos ni ejecuta los tests propuestos.",
        ],
    )


def render_tests(result: EngineResult, evidence: dict) -> StoredResult:
    issues = {issue["id"]: issue for issue in evidence["issues"]}
    output = result.model_dump()
    for index, plan in enumerate(output["suggested_tests"]):
        issue = test_source(plan["template"], plan["evidence_ids"], issues)
        if issue is None:
            raise ValueError(
                "No hay un destino completo y compatible para la plantilla."
            )
        path = urlsplit(issue["url"]).path or "/"
        # JSON string literals prevent evidence from injecting Python statements.
        literal = json.dumps(path, ensure_ascii=True)
        header = (
            "from playwright.sync_api import Page\n\n"
            "# PROPUESTA NO EJECUTADA. Revisa el código y usa un entorno autorizado.\n"
            "# La demo virtual no es una URL accesible fuera del motor BLACKBOX AI.\n"
            'BASE_URL = "REEMPLAZA_POR_UN_ENTORNO_AUTORIZADO"\n\n'
        )
        if plan["template"] == "http_status":
            body = f'    response = page.goto(BASE_URL + {literal}, wait_until="domcontentloaded")\n    assert response is not None\n    assert response.status < 400\n'
        else:
            event = "pageerror" if plan["template"] == "no_page_errors" else "console"
            callback = (
                "lambda error: errors.append(str(error))"
                if event == "pageerror"
                else 'lambda message: errors.append(message.text) if message.type == "error" else None'
            )
            body = f'    errors = []\n    page.on("{event}", {callback})\n    page.goto(BASE_URL + {literal}, wait_until="load")\n    assert not errors, errors\n'
        plan["code"] = header + f"def test_suggested_{index + 1}(page: Page):\n" + body
    return StoredResult.model_validate(output)
