"""Controlled-project local HTTP only. This is not a sandbox for arbitrary apps."""

from urllib.parse import urlsplit

import httpx2

from app.testing.demo import DemoResponse, response_for
from app.testing.policy import DemoPolicy, DestinationDenied

CATALOG_PATHS = frozenset(
    {
        "/",
        "/about",
        "/missing",
        "/server-error",
        "/form",
        "/redirect",
        "/subresources",
        "/slow",
        "/assets/demo.js",
        "/depth/1",
        "/depth/2",
        "/depth/3",
        "/depth/4",
        *[f"/many/{i}" for i in range(1, 25)],
    }
)


def local_origin(value: str, origin_only: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port is None
            or not 1024 <= parsed.port <= 65535
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value
            or (origin_only and parsed.path not in {"", "/"})
        ):
            raise ValueError()
        host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
        canonical = f"{parsed.scheme}://{host}:{parsed.port}"
        # Reject alternative IP spellings and URL parsers' surprising normalizations.
        if parsed.netloc != f"{host}:{parsed.port}":
            raise ValueError()
        return canonical
    except (ValueError, UnicodeError):
        raise DestinationDenied(
            "Usa un origen exacto HTTP/HTTPS con IP loopback literal y puerto entre 1024 y 65535."
        ) from None


class ControlledLocalPolicy(DemoPolicy):
    def __init__(self, origin: str, allowed_origins: list[str]):
        self.origin = local_origin(origin, True)
        if self.origin not in allowed_origins:
            raise DestinationDenied("El origen no está en la lista local configurada.")

    def authorize(self, url: str, method: str = "GET") -> str:
        if method != "GET" or local_origin(url) != self.origin:
            raise DestinationDenied(
                "El análisis solo autoriza GET en su origen exacto."
            )
        path = urlsplit(url).path or "/"
        if path not in CATALOG_PATHS:
            raise DestinationDenied(
                "La ruta no pertenece a la aplicación controlada del proyecto."
            )
        return self.origin + path


class LocalBroker:
    """Fetch literal loopback outside Chromium; verify every byte before execution."""

    def __init__(
        self, policy: ControlledLocalPolicy, timeout: float = 3, transport=None
    ):
        self.policy, self.timeout, self.transport = policy, timeout, transport

    async def __call__(self, url: str) -> DemoResponse:
        allowed = self.policy.authorize(url)
        expected = response_for(urlsplit(allowed).path)
        async with (
            httpx2.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=self.timeout,
                transport=self.transport,
                limits=httpx2.Limits(max_connections=1),
            ) as client,
            client.stream(
                "GET", allowed, headers={"Accept-Encoding": "identity"}
            ) as response,
        ):
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 1_000_000:
                    raise DestinationDenied(
                        "Respuesta local fuera de los límites del catálogo."
                    )
            if (
                response.status_code != expected.status
                or bytes(body) != expected.body.encode("utf-8")
                or response.headers.get("content-type") != expected.content_type
                or response.headers.get("location") != expected.location
            ):
                raise DestinationDenied(
                    "El contenido no coincide con la versión controlada del proyecto."
                )
        # Delay already occurred in the HTTP server. Never replay response headers/cookies.
        return DemoResponse(
            expected.status,
            expected.body,
            expected.content_type,
            location=expected.location,
        )
