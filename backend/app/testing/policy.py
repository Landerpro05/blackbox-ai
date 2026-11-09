import re
from urllib.parse import urlsplit, urlunsplit

DEMO_ORIGIN = "http://blackbox-demo.invalid"
DEMO_URL = DEMO_ORIGIN + "/"
MAX_ISSUES = 200


class DestinationDenied(ValueError):
    pass


class DemoPolicy:
    """No DNS allowlist: only in-process, versioned demo responses may be served.

    Never call route.continue_(), route.fetch(), urllib, requests or a resolver.
    A URL being public/global does not authorize remote browsing.
    """

    def authorize(self, url: str, method: str = "GET") -> str:
        try:
            parsed = urlsplit(url)
            if (
                method != "GET"
                or parsed.scheme != "http"
                or parsed.hostname != "blackbox-demo.invalid"
                or parsed.port not in (None, 80)
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or "\\" in url
                or any(char.isspace() for char in url)
            ):
                raise DestinationDenied(
                    "Solo se permite la demostración integrada y peticiones GET."
                )
        except (ValueError, UnicodeError):
            raise DestinationDenied("Destino no autorizado para esta fase.") from None
        return DEMO_ORIGIN + (parsed.path or "/")

    def navigable(self, url: str) -> bool:
        try:
            clean = self.authorize(url)
            path = urlsplit(clean).path.lower()
            return not re.search(
                r"(?:logout|signout|delete|remove|destroy|purchase|checkout|submit|payment)|\.(?:zip|exe|msi|pdf|dmg|bat|ps1)$",
                path,
            )
        except DestinationDenied:
            return False


def redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port
        netloc = host + (f":{port}" if port else "")
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))[:2048]
    except ValueError:
        return "[URL omitida]"


def redact_text(value: str) -> str:
    value = re.sub(
        r"https?://[^\s<>\"']+", lambda match: redact_url(match.group()), value
    )
    value = re.sub(r"(?i)\b(Bearer)\s+[^\s,;]+", r"\1 [REDACTADO]", value)
    value = re.sub(
        r"(?i)\b(password|passwd|token|api[_-]?key|authorization|cookie|secret)\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTADO]",
        value,
    )
    value = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[correo oculto]", value
    )
    return value[:4000]
