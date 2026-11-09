"""Versioned, bundled application. No user-provided HTML, proxying or upstream IO."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoResponse:
    status: int
    body: str
    content_type: str = "text/html; charset=utf-8"
    delay_seconds: float = 0
    location: str | None = None


def document(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;background:#101827;color:#d8e7ff;padding:40px;max-width:900px}}a{{color:#80b2ff;display:block;margin:14px 0}}input{{display:block;margin:12px 0;padding:10px;background:#24324a;color:white}}.badge{{color:#8ce0c2}}footer{{margin-top:30px;color:#92a6c8}}</style>
</head><body><p class="badge">BLACKBOX AI · Aplicación de demostración controlada</p><h1>{title}</h1>{body}<footer>Contenido integrado. Ningún dato se envía a una aplicación externa.</footer></body></html>"""


HOME = document(
    "Demo de testing",
    """
<p>Esta aplicación contiene errores intencionados para verificar el motor real.</p>
<a href="/about">Acerca de la demo</a><a href="/missing">Enlace roto (404)</a>
<a href="/server-error">Error del servidor (500)</a><a href="/form">Formulario sin envío</a>
<a href="/redirect">Redirección bloqueada</a><a href="/subresources">Subrecursos bloqueados</a>
<a href="/slow">Respuesta lenta</a><a href="/many/1">Más páginas</a>
<a href="/about#section">Enlace repetido</a><a href="/download.zip">Descarga excluida</a>
<script src="/assets/demo.js"></script>
""",
)


def response_for(path: str) -> DemoResponse:
    if path == "/":
        return DemoResponse(200, HOME)
    if path == "/assets/demo.js":
        return DemoResponse(
            200,
            "console.error('Error de demo token=demo-secret-123'); setTimeout(() => { throw new Error('Excepción de demo password=demo-password-123'); }, 20);",
            "application/javascript",
        )
    if path == "/about":
        return DemoResponse(
            200,
            document(
                "Acerca de", '<a href="/depth/1">Primer nivel</a><a href="/">Inicio</a>'
            ),
        )
    if path.startswith("/depth/") and path.removeprefix("/depth/") in {
        "1",
        "2",
        "3",
        "4",
    }:
        level = int(path.rsplit("/", 1)[1])
        return DemoResponse(
            200,
            document(
                f"Profundidad {level}",
                f'<a href="/depth/{level + 1}">Siguiente nivel</a>',
            ),
        )
    if path == "/server-error":
        return DemoResponse(
            500,
            document("Error de servidor", "<p>Fallo HTTP intencionado de la demo.</p>"),
        )
    if path == "/form":
        return DemoResponse(
            200,
            document(
                "Formulario pasivo",
                '<form action="/submit" method="post"><input name="email" type="email" value="private@example.com"><input type="password" value="demo-password-123"><button>Enviar (no usar)</button></form><p data-sensitive>token=demo-secret-123</p>',
            ),
        )
    if path == "/redirect":
        return DemoResponse(
            302, "", location="http://169.254.169.254/latest/meta-data/"
        )
    if path == "/subresources":
        return DemoResponse(
            200,
            document(
                "Solicitudes no autorizadas",
                """
<img src="http://127.0.0.1:8000/private"><iframe src="http://localhost:8000/"></iframe>
<script src="https://example.com/external.js"></script><script>
fetch('http://169.254.169.254/latest/meta-data/').catch(()=>{});
fetch('/submit', {method:'POST',body:'token=demo-secret-123'}).catch(()=>{});
new WebSocket('ws://127.0.0.1:8000/private');
</script>""",
            ),
        )
    if path == "/slow":
        return DemoResponse(
            200,
            document(
                "Respuesta lenta",
                "<p>Útil para cancelar o probar un timeout de navegación.</p>",
            ),
            delay_seconds=5,
        )
    if path.startswith("/many/") and path.removeprefix("/many/") in {
        str(value) for value in range(1, 25)
    }:
        links = "".join(
            f'<a href="/many/{value}">Página {value}</a>' for value in range(1, 25)
        )
        return DemoResponse(200, document("Recorrido limitado", links))
    return DemoResponse(
        404, document("Página no encontrada", "<p>Enlace interno roto de la demo.</p>")
    )
