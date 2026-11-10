from urllib.parse import urljoin


async def evaluate(page, definition, status, engine, policy, responder):
    """Fixed operations only. No user-provided Python, JS, XPath or actions."""
    kind = definition["type"]
    if status is None:
        return "error", "No se pudo completar la navegación inicial."
    if kind == "http_status":
        passed = definition["minimum"] <= status <= definition["maximum"]
        return (
            ("pass" if passed else "fail"),
            f"HTTP observado: {status}; rango esperado: {definition['minimum']}–{definition['maximum']}.",
        )
    if kind == "title":
        passed = await page.title() == definition["expected_title"]
    elif kind == "element_exists":
        passed = await page.locator(definition["selector"]).count() > 0
    elif kind == "text_visible":
        passed = await page.get_by_text(
            definition["text"], exact=False
        ).first.is_visible()
    elif kind == "no_js_errors":
        passed = not any(
            item.kind in {"javascript", "console"} for item in engine._findings
        )
    elif kind == "navigate":
        destination = policy.authorize(urljoin(page.url, definition["destination"]))
        response = await page.goto(
            destination,
            wait_until="domcontentloaded",
            timeout=engine.navigation_timeout_ms,
        )
        passed = (
            page.url == destination and response is not None and response.status < 400
        )
    elif kind == "internal_links":
        links = await page.locator("a[href]").evaluate_all(
            "elements => elements.slice(0, 20).map(e => e.href)"
        )
        checked = set()
        for link in links:
            from app.testing.policy import DestinationDenied

            try:
                allowed = policy.authorize(link.split("#", 1)[0])
            except DestinationDenied:
                continue
            if not policy.navigable(allowed) or allowed in checked:
                continue
            checked.add(allowed)
            engine.requests += 1
            if engine.requests > engine.request_budget:
                engine.requests_exhausted = True
                return (
                    "error",
                    "Se agotó el presupuesto de solicitudes al verificar enlaces.",
                )
            response = await responder(allowed)
            if response.location:
                policy.authorize(urljoin(allowed, response.location))
            if response.status >= 400:
                return (
                    "fail",
                    "Se observó un enlace interno con respuesta HTTP de error.",
                )
        return (
            "pass",
            f"Enlaces internos autorizados verificados: {len(checked)} (máximo 20).",
        )
    else:
        raise ValueError("Tipo declarativo no admitido.")
    return (
        ("pass" if passed else "fail"),
        "La comprobación coincide con la expectativa."
        if passed
        else "La comprobación no coincide con la expectativa declarada.",
    )
