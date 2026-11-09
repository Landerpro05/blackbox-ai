"""Bounded, offline reports. Persisted evidence is data, never a template or path."""

import base64
import csv
import hashlib
import json
import re
from datetime import UTC, datetime
from html import escape
from io import BytesIO, StringIO
from uuid import UUID

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import RunNotFound
from app.models import Issue, Project, Run, RunStatus, Severity, TestPage
from app.repositories.runs import ACTIVE, scoped_run
from app.testing.evidence import EvidenceStore
from app.testing.policy import redact_text, redact_url

MAX_ISSUES = 200
MAX_PAGES = 20
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 3_000_000
MAX_TOTAL_IMAGE_BYTES = 4_000_000
MAX_RESPONSE_BYTES = 12_000_000
HEURISTIC = (
    "Comparación heurística v1: tipo, URL sin consulta/fragmento y mensaje normalizado. "
    "Se agrupan duplicados; puede haber falsos positivos y negativos. RESOLVED significa "
    "no observado en una página revisitada, no una garantía de corrección. "
    "Los análisis tienen cobertura limitada por sus presupuestos."
)


def clean(value: str | None, limit: int = 4000) -> str:
    value = (value or "")[:16000]
    # Hide quoted credentials, local paths and control characters in historical data too.
    value = re.sub(
        r"""(?i)["']?(password|passwd|token|api[_-]?key|authorization|cookie|secret)["']?\s*[:=]\s*["'][^"']*["']""",
        r"\1=[REDACTADO]",
        value,
    )
    value = redact_text(value)
    value = re.sub(
        r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/]|file:///)[^\s<>]+|/(?:home|Users|var|etc|tmp)/[^\s<>]+",
        "[ruta omitida]",
        value,
    )
    return "".join(c for c in value if ord(c) >= 32 or c in "\n\t")[:limit]


def safe_url(value: str) -> str:
    from urllib.parse import urlsplit

    try:
        if urlsplit(value).scheme.lower() not in {"http", "https"}:
            return "[URL omitida]"
        return clean(redact_url(value), 2048)
    except ValueError:
        return "[URL omitida]"


def date(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(UTC).isoformat()


def terminal(run: Run) -> None:
    if run.status in ACTIVE or run.finished_at is None:
        raise HTTPException(409, "Espera a que finalice el análisis.")


def scoped_project(session: Session, project_id: str, workspace: str) -> Project:
    project = session.scalar(
        select(Project).where(
            Project.id == project_id, Project.workspace_id == workspace
        )
    )
    if project is None:
        raise RunNotFound()
    return project


def summary(session: Session, run: Run) -> dict:
    severity = {item.value: 0 for item in Severity}
    severity.update(
        {
            key.value: count
            for key, count in session.execute(
                select(Issue.severity, func.count())
                .where(Issue.run_id == run.id)
                .group_by(Issue.severity)
            )
        }
    )
    kinds = {
        clean(key, 60): count
        for key, count in session.execute(
            select(Issue.kind, func.count())
            .where(Issue.run_id == run.id)
            .group_by(Issue.kind)
            .order_by(func.count().desc())
            .limit(50)
        )
    }
    page_count, average = session.execute(
        select(func.count(), func.avg(TestPage.load_time_ms)).where(
            TestPage.test_run_id == run.id
        )
    ).one()
    http, javascript, broken = session.execute(
        select(
            func.coalesce(
                func.sum(case((Issue.kind.in_(("http", "broken_link")), 1), else_=0)), 0
            ),
            func.coalesce(
                func.sum(case((Issue.kind.in_(("javascript", "console")), 1), else_=0)),
                0,
            ),
            func.coalesce(func.sum(case((Issue.kind == "broken_link", 1), else_=0)), 0),
        ).where(Issue.run_id == run.id)
    ).one()
    return {
        "pages": page_count,
        "issues": sum(severity.values()),
        "by_severity": severity,
        "by_type": kinds,
        "http_errors": http,
        "javascript_errors": javascript,
        "broken_links": broken,
        "average_navigation_ms": round(average, 1) if average is not None else None,
    }


def issue_data(issue: Issue, page_ids: set[str]) -> dict:
    page_id = None
    try:
        if issue.evidence_path and re.fullmatch(
            r"[0-9a-f-]{36}\.png", issue.evidence_path
        ):
            candidate = str(UUID(issue.evidence_path[:-4]))
            if candidate in page_ids:
                page_id = candidate
    except ValueError:
        pass
    return {
        "id": issue.id,
        "type": clean(issue.kind, 60),
        "severity": issue.severity.value,
        "title": clean(issue.title or issue.kind, 200),
        "description": clean(issue.description),
        "url": safe_url(issue.affected_url),
        "reproduction_steps": clean(issue.reproduction_steps)
        if issue.reproduction_steps
        else None,
        "evidence_page_id": page_id,
    }


def report_data(session: Session, run_id: str, workspace: str) -> dict:
    run = scoped_run(session, run_id, workspace)
    terminal(run)
    project = scoped_project(session, run.project_id, workspace)
    stats = summary(session, run)
    pages = list(
        session.scalars(
            select(TestPage)
            .where(TestPage.test_run_id == run.id)
            .order_by(TestPage.scanned_at, TestPage.id)
            .limit(MAX_PAGES)
        )
    )
    page_ids = {page.id for page in pages if page.screenshot_path == f"{page.id}.png"}
    issues = list(
        session.scalars(
            select(Issue)
            .where(Issue.run_id == run.id)
            .order_by(Issue.created_at, Issue.id)
            .limit(MAX_ISSUES)
        )
    )
    warnings = [
        "Cobertura limitada a las páginas y presupuestos de esta ejecución. Los datos textuales se redactan; revisa las capturas antes de compartirlas."
    ]
    if run.status != RunStatus.COMPLETED:
        warnings.append(
            "Ejecución parcial: sus resultados no prueban la ausencia de errores."
        )
    omitted = {
        "issues": max(0, stats["issues"] - len(issues)),
        "pages": max(0, stats["pages"] - len(pages)),
    }
    if any(omitted.values()):
        warnings.append(
            "Se han omitido detalles por los límites del informe; el resumen conserva los totales SQL."
        )
    return {
        "schema_version": 1,
        "brand": "BLACKBOX AI",
        "project": {"id": project.id, "name": clean(project.name, 120)},
        "run": {
            "id": run.id,
            "status": run.status.value,
            "target_url": safe_url(run.target_url or project.base_url),
            "created_at": date(run.created_at),
            "started_at": date(run.started_at),
            "finished_at": date(run.finished_at),
            "duration_ms": run.duration_ms,
        },
        "summary": stats,
        "warnings": warnings,
        "omitted": omitted,
        "issues": [issue_data(issue, page_ids) for issue in issues],
        "pages": [
            {
                "id": p.id,
                "url": safe_url(p.url),
                "status_code": p.status_code,
                "load_time_ms": p.load_time_ms,
                "evidence_available": p.id in page_ids,
            }
            for p in pages
        ],
    }


def evidence_images(
    report: dict, include: bool
) -> tuple[list[tuple[dict, bytes]], int]:
    """Read only same-run UUID-owned, bounded, decoded PNGs; strip metadata."""
    candidates = [p for p in report["pages"] if p["evidence_available"]]
    result = []
    size = 0
    store = EvidenceStore(get_settings().evidence_dir)
    if include:
        for page in candidates:
            if len(result) >= MAX_IMAGES:
                break
            try:
                path = store.path(report["run"]["id"], page["id"])
                if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
                    continue
                with path.open("rb") as stream:
                    raw = stream.read(MAX_IMAGE_BYTES + 1)
                if len(raw) > MAX_IMAGE_BYTES:
                    continue
                with Image.open(BytesIO(raw)) as image:
                    if (
                        image.format != "PNG"
                        or image.width > 1920
                        or image.height > 1080
                        or getattr(image, "n_frames", 1) != 1
                    ):
                        continue
                    image.load()
                    buffer = BytesIO()
                    converted = image.convert("RGB")
                    converted.info.clear()
                    converted.save(buffer, format="PNG")
                    data = buffer.getvalue()
                if (
                    len(data) > MAX_IMAGE_BYTES
                    or size + len(data) > MAX_TOTAL_IMAGE_BYTES
                ):
                    continue
                size += len(data)
                result.append((page, data))
            except (
                OSError,
                ValueError,
                UnidentifiedImageError,
                Image.DecompressionBombError,
            ):
                continue
    return result, len(candidates) - len(result)


def bounded(data: bytes) -> bytes:
    if len(data) > MAX_RESPONSE_BYTES:
        raise HTTPException(
            413, "El informe supera el tamaño permitido. Desactiva las capturas."
        )
    return data


def json_report(report: dict) -> bytes:
    return bounded(
        json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")
    )


def csv_report(report: dict) -> bytes:
    output = StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "run_id",
            "run_status",
            "total_issues",
            "omitted_issues",
            "id",
            "type",
            "severity",
            "title",
            "description",
            "url",
            "reproduction_steps",
            "evidence_page_id",
        ]
    )

    def cell(value):
        text = str(value if value is not None else "")
        return (
            "'" + text
            if text.lstrip().startswith(("=", "+", "-", "@"))
            or text.startswith(("\t", "\r", "\n"))
            else text
        )

    for issue in report["issues"] or [{}]:
        writer.writerow(
            [
                cell(v)
                for v in [
                    report["run"]["id"],
                    report["run"]["status"],
                    report["summary"]["issues"],
                    report["omitted"]["issues"],
                    *[
                        issue.get(key)
                        for key in (
                            "id",
                            "type",
                            "severity",
                            "title",
                            "description",
                            "url",
                            "reproduction_steps",
                            "evidence_page_id",
                        )
                    ],
                ]
            ]
        )
    return bounded(output.getvalue().encode("utf-8-sig"))


def html_report(report: dict, include_evidence: bool = True) -> bytes:
    e = lambda value: escape(
        str(value if value is not None else "Sin datos"), quote=True
    )
    images, omitted = evidence_images(report, include_evidence)
    stats = report["summary"]
    parts = [
        '<!doctype html><html lang="es"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; img-src data:; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">',
        "<title>BLACKBOX AI - Informe</title><style>body{font:15px/1.6 system-ui,sans-serif;background:#090e1a;color:#e7edf8;margin:0}main{max-width:1050px;margin:auto;padding:40px 24px}h1{font-size:38px}h2{color:#82b0ff;margin-top:36px}article,.cover{background:#111b2e;border:1px solid #293650;border-radius:12px;padding:22px;margin:18px 0}p,td,dd{overflow-wrap:anywhere;white-space:pre-wrap}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #293650}img{max-width:100%;height:auto}small{color:#afbdd2}dt{color:#afbdd2}dd{margin:0 0 12px}.notice{border-left:3px solid #f5b74f;padding-left:14px}@media print{body{background:white;color:#172033}article,.cover{background:white;break-inside:avoid}h2{color:#275bb0}}</style></head><body><main>",
        f'<header class="cover"><small>BLACKBOX AI / INFORME DE TESTING</small><h1>{e(report["project"]["name"])}</h1><p>{e(report["run"]["target_url"])}</p><dl>',
    ]
    for key, label in [
        ("id", "Ejecución"),
        ("created_at", "Fecha UTC"),
        ("status", "Estado"),
        ("duration_ms", "Duración (ms)"),
    ]:
        parts.append(f"<dt>{label}</dt><dd>{e(report['run'][key])}</dd>")
    parts.append(
        "</dl></header><h2>Resumen ejecutivo</h2><table><thead><tr><th>Métrica</th><th>Valor</th></tr></thead><tbody>"
    )
    for label, value in metric_rows(stats):
        parts.append(f"<tr><th>{e(label)}</th><td>{e(value)}</td></tr>")
    parts.append("</tbody></table>")
    for warning in report["warnings"]:
        parts.append(f'<p class="notice">{e(warning)}</p>')
    parts.append(
        f"<p>Detalles omitidos: {e(report['omitted'])}</p><h2>Incidencias</h2>"
    )
    if not report["issues"]:
        parts.append("<p>No se registraron incidencias en las páginas analizadas.</p>")
    for issue in report["issues"]:
        parts.append(
            f"<article><small>{e(issue['severity'])} / {e(issue['type'])}</small><h3>{e(issue['title'])}</h3><p>{e(issue['id'])}</p><p>{e(issue['url'])}</p><p>{e(issue['description'])}</p><p>Evidencia: {e(issue['evidence_page_id'] or 'No disponible')}</p>"
        )
        if issue["reproduction_steps"]:
            parts.append(
                f"<h4>Reproducción registrada</h4><p>{e(issue['reproduction_steps'])}</p>"
            )
        parts.append("</article>")
    parts.append(
        f"<h2>Evidencias</h2><p>Capturas incluidas: {len(images)}. Omitidas o no disponibles: {omitted}.</p>"
    )
    for page, data in images:
        parts.append(
            f'<figure><figcaption>{e(page["id"])} - {e(page["url"])}</figcaption><img alt="Captura registrada" src="data:image/png;base64,{base64.b64encode(data).decode("ascii")}"></figure>'
        )
    parts.append(
        "<footer><small>BLACKBOX AI · Resultados persistidos · Sin contenido activo ni recursos externos</small></footer></main></body></html>"
    )
    return bounded("".join(parts).encode("utf-8"))


def metric_rows(stats: dict) -> list[tuple[str, object]]:
    return [
        ("Páginas analizadas", stats["pages"]),
        ("Incidencias", stats["issues"]),
        *[(f"Severidad {key}", value) for key, value in stats["by_severity"].items()],
        ("Errores HTTP", stats["http_errors"]),
        ("Errores JavaScript / consola", stats["javascript_errors"]),
        ("Enlaces rotos", stats["broken_links"]),
        ("Navegación media (ms)", stats["average_navigation_ms"]),
    ]


def pdf_report(report: dict, include_evidence: bool = True) -> bytes:
    from pathlib import Path

    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Image as PDFImage,
    )
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    font_dir = Path(reportlab.__file__).parent / "fonts"
    if "BBVera" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("BBVera", str(font_dir / "Vera.ttf")))
        pdfmetrics.registerFont(TTFont("BBVeraBold", str(font_dir / "VeraBd.ttf")))
    # Restrict to glyphs this bundled font actually supports instead of drawing boxes.
    glyphs = pdfmetrics.getFont("BBVera").face.charWidths

    def text(value):
        raw = str(value if value is not None else "Sin datos")
        return escape(
            "".join(c if ord(c) in glyphs or c == "\n" else "?" for c in raw)
        ).replace("\n", "<br/>")

    body = ParagraphStyle(
        "Body",
        fontName="BBVera",
        fontSize=9,
        leading=14,
        spaceAfter=9,
        textColor=colors.HexColor("#25334b"),
        splitLongWords=True,
    )
    heading = ParagraphStyle(
        "Heading",
        parent=body,
        fontName="BBVeraBold",
        fontSize=17,
        leading=23,
        spaceBefore=16,
        spaceAfter=12,
    )
    title = ParagraphStyle("Title", parent=heading, fontSize=29, leading=38)
    p = lambda value, style=body: Paragraph(text(value), style)
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=44,
        leftMargin=44,
        topMargin=58,
        bottomMargin=50,
        title="BLACKBOX AI - Informe de testing",
        author="BLACKBOX AI",
    )
    story = [
        Spacer(1, 60),
        p("BLACKBOX AI", title),
        p("INFORME DE TESTING", heading),
        p(report["project"]["name"], heading),
        p(report["run"]["target_url"]),
        Spacer(1, 20),
    ]
    for key, label in [
        ("id", "Ejecución"),
        ("created_at", "Fecha UTC"),
        ("status", "Estado"),
        ("duration_ms", "Duración (ms)"),
    ]:
        story.append(p(f"{label}: {report['run'][key]}"))
    story.extend(
        [
            Spacer(1, 20),
            *[p(w) for w in report["warnings"]],
            p(
                "Tipografía Unicode limitada a los caracteres de la fuente incluida; otros se muestran como ?."
            ),
            PageBreak(),
            p("Resumen ejecutivo", heading),
        ]
    )
    table = Table(
        [
            [p("Métrica"), p("Valor")],
            *[[p(label), p(value)] for label, value in metric_rows(report["summary"])],
        ],
        colWidths=[350, 157],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edfb")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#ccd6e6")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [table, p(f"Detalles omitidos: {report['omitted']}"), p("Incidencias", heading)]
    )
    if not report["issues"]:
        story.append(p("No se registraron incidencias en las páginas analizadas."))
    for issue in report["issues"]:
        story.extend(
            [
                p(issue["title"], heading),
                p(f"{issue['severity']} / {issue['type']} / {issue['id']}"),
                p(issue["url"]),
                p(issue["description"]),
                p(f"Evidencia: {issue['evidence_page_id'] or 'No disponible'}"),
            ]
        )
        if issue["reproduction_steps"]:
            story.extend([p("Reproducción registrada"), p(issue["reproduction_steps"])])
    images, omitted = evidence_images(report, include_evidence)
    story.extend(
        [
            PageBreak(),
            p("Evidencias", heading),
            p(
                f"Capturas incluidas: {len(images)}. Omitidas o no disponibles: {omitted}."
            ),
        ]
    )
    for page, data in images:
        image = PDFImage(BytesIO(data))
        ratio = min(507 / image.imageWidth, 360 / image.imageHeight)
        image.drawWidth, image.drawHeight = (
            image.imageWidth * ratio,
            image.imageHeight * ratio,
        )
        story.extend([p(page["id"]), p(page["url"]), image, Spacer(1, 18)])

    def furniture(canvas, document):
        canvas.saveState()
        canvas.setFont("BBVera", 8)
        canvas.setFillColor(colors.HexColor("#5b6f90"))
        canvas.drawString(44, A4[1] - 32, "BLACKBOX AI / INFORME DE TESTING")
        canvas.drawString(44, 28, report["run"]["id"])
        canvas.drawRightString(A4[0] - 44, 28, f"Página {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=furniture, onLaterPages=furniture)
    return bounded(output.getvalue())


def fingerprint(issue: dict) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(issue["url"])
    authority = parsed.netloc.lower().removesuffix(
        ":80" if parsed.scheme == "http" else ":443"
    )
    url = urlunsplit((parsed.scheme.lower(), authority, parsed.path or "/", "", ""))
    message = issue["title"] + " " + issue["description"]
    message = re.sub(
        r"\b[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\b|\b\d{4}-\d{2}-\d{2}(?:[T ][\d:.+Z-]+)?|\b\d+(?:\.\d+)?\s*(?:ms|milliseconds|segundos|seconds)\b",
        "<variable>",
        message,
        flags=re.IGNORECASE,
    )
    message = " ".join(message.casefold().split())
    return hashlib.sha256(
        json.dumps(
            [issue["type"].casefold(), url, message], ensure_ascii=False
        ).encode()
    ).hexdigest()


def compare(
    session: Session, project_id: str, workspace: str, base_id: str, target_id: str
) -> dict:
    scoped_project(session, project_id, workspace)
    base, target = (
        scoped_run(session, base_id, workspace),
        scoped_run(session, target_id, workspace),
    )
    if base.project_id != project_id or target.project_id != project_id:
        raise RunNotFound()
    terminal(base)
    terminal(target)
    if base.id == target.id or base.created_at >= target.created_at:
        raise HTTPException(
            422,
            "Selecciona dos ejecuciones distintas, con la base anterior al destino.",
        )
    previous, current = (
        report_data(session, base.id, workspace),
        report_data(session, target.id, workspace),
    )
    old = {fingerprint(i): i for i in previous["issues"]}
    new = {fingerprint(i): i for i in current["issues"]}
    complete = (
        base.status == target.status == RunStatus.COMPLETED
        and base.limits == target.limits
        and previous["run"]["target_url"] == current["run"]["target_url"]
        and not any(previous["omitted"].values())
        and not any(current["omitted"].values())
        and previous["summary"]["issues"] < MAX_ISSUES
        and current["summary"]["issues"] < MAX_ISSUES
        and not any(
            i["type"] in {"request_limit", "navigation", "navigation_timeout"}
            for r in (previous, current)
            for i in r["issues"]
        )
    )
    blocked = {
        i["url"]
        for i in current["issues"]
        if i["type"]
        in {"navigation", "navigation_timeout", "redirect_blocked", "request_limit"}
    }
    visited = {
        p["url"] for p in current["pages"] if p["status_code"] is not None
    } - blocked
    counts = dict.fromkeys(("NEW", "RESOLVED", "PERSISTENT", "UNCONFIRMED"), 0)
    items = []
    for key in sorted(old.keys() | new.keys()):
        if key in old and key in new:
            status = "PERSISTENT"
        elif key in new:
            status = "NEW"
        else:
            status = (
                "RESOLVED" if complete and old[key]["url"] in visited else "UNCONFIRMED"
            )
        counts[status] += 1
        items.append(
            {
                "fingerprint": key,
                "classification": status,
                "issue": new.get(key, old.get(key)),
            }
        )
    return {
        "base_run_id": base.id,
        "target_run_id": target.id,
        "counts": counts,
        "items": items,
        "heuristic": HEURISTIC,
        "partial": not complete or counts["UNCONFIRMED"] > 0,
        "warnings": [
            "UNCONFIRMED: falta cobertura o una ejecución es parcial; no se afirma resolución.",
            "NEW significa observado solo en destino; puede haber faltado cobertura en la base.",
        ],
        "omitted": {"base": previous["omitted"], "target": current["omitted"]},
    }


def analytics(
    session: Session, project_id: str, workspace: str, limit: int, offset: int
) -> dict:
    scoped_project(session, project_id, workspace)
    scope = (Run.project_id == project_id, Run.workspace_id == workspace)
    run_ids = select(Run.id).where(*scope)
    total = session.scalar(select(func.count()).select_from(Run).where(*scope)) or 0
    severities = {s.value: 0 for s in Severity}
    severities.update(
        {
            s.value: count
            for s, count in session.execute(
                select(Issue.severity, func.count())
                .where(Issue.run_id.in_(run_ids))
                .group_by(Issue.severity)
            )
        }
    )
    types = [
        {"type": clean(k, 60), "count": n}
        for k, n in session.execute(
            select(Issue.kind, func.count())
            .where(Issue.run_id.in_(run_ids))
            .group_by(Issue.kind)
            .order_by(func.count().desc(), Issue.kind)
            .limit(50)
        )
    ]
    average = session.scalar(
        select(func.avg(TestPage.load_time_ms)).where(TestPage.test_run_id.in_(run_ids))
    )
    selected = list(
        session.scalars(
            select(Run)
            .where(*scope)
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    selected_ids = [r.id for r in selected]
    # Aggregate only the requested page of runs; no ORM relationship loads.
    issue_counts = dict(
        session.execute(
            select(Issue.run_id, func.count())
            .where(Issue.run_id.in_(selected_ids))
            .group_by(Issue.run_id)
        ).all()
    )
    averages = dict(
        session.execute(
            select(TestPage.test_run_id, func.avg(TestPage.load_time_ms))
            .where(TestPage.test_run_id.in_(selected_ids))
            .group_by(TestPage.test_run_id)
        ).all()
    )
    recent = list(
        session.scalars(
            select(Run)
            .where(*scope, Run.status.not_in(ACTIVE), Run.finished_at.is_not(None))
            .order_by(Run.created_at.desc(), Run.id.desc())
            .limit(2)
        )
    )
    regression = (
        compare(session, project_id, workspace, recent[1].id, recent[0].id)
        if len(recent) == 2 and recent[1].created_at < recent[0].created_at
        else None
    )
    return {
        "total_runs": total,
        "total_issues": sum(severities.values()),
        "by_severity": severities,
        "by_type": types,
        "types_truncated": len(types) == 50,
        "average_navigation_ms": round(average, 1) if average is not None else None,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "created_at": date(r.created_at),
                "status": r.status.value,
                "issues": issue_counts.get(r.id, 0),
                "average_navigation_ms": round(averages[r.id], 1)
                if r.id in averages
                else None,
            }
            for r in selected
        ],
        "regression": {
            k: regression[k]
            for k in ("base_run_id", "target_run_id", "counts", "partial", "heuristic")
        }
        if regression
        else None,
    }
