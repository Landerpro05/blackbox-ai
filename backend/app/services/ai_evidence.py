"""Small, redacted snapshots; never images, filesystem contents or raw prompts."""

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Run
from app.repositories.runs import ACTIVE, scoped_run
from app.services import reporting

MAX_CONTEXT_BYTES = 12000
MAX_CONTEXT_ISSUES = 20
MAX_CONTEXT_PAGES = 10
PROMPT_VERSION = "intelligence-v1"
INJECTION = re.compile(
    r"ignore.{0,40}(?:instructions|previous)|system.?prompt|developer.?message|exfiltrat|reveal.{0,30}(?:secret|key)|ignora.{0,40}instrucciones|instrucciones.{0,30}sistema",
    re.IGNORECASE,
)
DANGEROUS = re.compile(
    r"\b(?:subprocess|child_process|powershell|cmd\.exe|os\.system|eval\s*\(|exec\s*\(|shell\s*=|rm\s+-[rf]|Remove-Item|Invoke-Expression|curl\s|wget\s)",
    re.IGNORECASE,
)


def safe_text(value: str, secret: str = "", limit: int = 600) -> str:
    if secret:
        value = value.replace(secret, "[REDACTADO]")
    return reporting.clean(value, limit)


def collect(
    session: Session,
    run_id: str,
    workspace: str,
    include_history: bool,
    secret: str = "",
) -> dict:
    document = reporting.report_data(session, run_id, workspace)
    run = scoped_run(session, run_id, workspace)
    issues = []
    quarantined = 0
    for issue in document["issues"][:MAX_CONTEXT_ISSUES]:
        message = safe_text(issue["description"], secret)
        title = safe_text(issue["title"], secret, 200)
        suspicious = bool(
            INJECTION.search(message + title) or DANGEROUS.search(message + title)
        )
        if suspicious:
            message, title = (
                "Contenido omitido: instrucciones o comandos no confiables en la evidencia.",
                "Mensaje no confiable omitido",
            )
            quarantined += 1
        issues.append(
            {
                "id": "issue:" + issue["id"],
                "type": safe_text(issue["type"], secret, 60),
                "severity": issue["severity"],
                "title": title,
                "message": message,
                "url": safe_text(issue["url"], secret, 2048),
                "screenshot_page_id": issue["evidence_page_id"],
                "quarantined": suspicious,
            }
        )
    pages = [
        {
            "id": "page:" + p["id"],
            "url": safe_text(p["url"], secret, 2048),
            "status_code": p["status_code"],
            "load_time_ms": p["load_time_ms"],
            "screenshot_available": p["evidence_available"],
        }
        for p in document["pages"][:MAX_CONTEXT_PAGES]
    ]
    history = None
    if include_history:
        previous = session.scalar(
            select(Run)
            .where(
                Run.project_id == run.project_id,
                Run.workspace_id == workspace,
                Run.created_at < run.created_at,
                Run.status.not_in(ACTIVE),
                Run.finished_at.is_not(None),
            )
            .order_by(Run.created_at.desc(), Run.id)
            .limit(1)
        )
        if previous:
            comparison = reporting.compare(
                session, run.project_id, workspace, previous.id, run.id
            )
            history = {
                "id": "history:" + previous.id,
                "base_run_id": previous.id,
                "counts": comparison["counts"],
                "partial": comparison["partial"],
                "heuristic": True,
            }
    snapshot = {
        "run_id": run.id,
        "run_status": run.status.value,
        "target_url": safe_text(document["run"]["target_url"], secret, 2048),
        "summary": {
            key: document["summary"][key]
            for key in (
                "pages",
                "issues",
                "by_severity",
                "http_errors",
                "javascript_errors",
                "broken_links",
                "average_navigation_ms",
            )
        },
        "issues": issues,
        "pages": pages,
        "history": history,
        "groups": [],
        "omitted_issues": document["summary"]["issues"] - len(issues),
        "omitted_pages": document["summary"]["pages"] - len(pages),
        "quarantined_messages": quarantined,
    }
    # Leave room for deterministic grouping without ever exceeding the byte budget.
    while (
        len(json.dumps(snapshot, ensure_ascii=False).encode())
        > MAX_CONTEXT_BYTES - 1800
    ):
        if len(snapshot["issues"]) > 1:
            snapshot["issues"].pop()
            snapshot["omitted_issues"] += 1
        elif snapshot["pages"]:
            snapshot["pages"].pop()
            snapshot["omitted_pages"] += 1
        else:
            break
    groups = {}
    for issue in snapshot["issues"]:
        key = reporting.fingerprint(
            {
                "type": issue["type"],
                "url": issue["url"],
                "title": issue["title"],
                "description": issue["message"],
            }
        )
        groups.setdefault(key, []).append(issue["id"])
    snapshot["groups"] = [
        {
            "fingerprint": key,
            "evidence_ids": ids,
            "count": len(ids),
            "source": "deterministic",
        }
        for key, ids in groups.items()
    ]
    # A hash entry per distinct issue is bounded but can still use the reserved space.
    while (
        len(json.dumps(snapshot, ensure_ascii=False).encode()) > MAX_CONTEXT_BYTES
        and snapshot["issues"]
    ):
        removed = snapshot["issues"].pop()["id"]
        snapshot["omitted_issues"] += 1
        for group in snapshot["groups"]:
            if removed in group["evidence_ids"]:
                group["evidence_ids"].remove(removed)
                group["count"] -= 1
        snapshot["groups"] = [group for group in snapshot["groups"] if group["count"]]
    return snapshot
