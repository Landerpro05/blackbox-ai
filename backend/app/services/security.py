import hashlib
import secrets
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import begin_write, get_session
from app.models.security import (
    AuditEvent,
    AuthSession,
    RegistrationInvite,
    User,
    Workspace,
    WorkspaceMembership,
)

PASSWORDS = PasswordHash((Argon2Hasher(time_cost=3, memory_cost=65536, parallelism=1),))
HASH_SLOTS = threading.BoundedSemaphore(2)


def now():
    return datetime.now(UTC)


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def digest(value: str):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def password_operation(password, encoded=None):
    if not HASH_SLOTS.acquire(blocking=False):
        raise HTTPException(
            429,
            "Autenticación ocupada. Inténtalo más tarde.",
            headers={"Retry-After": "5"},
        )
    try:
        return (
            PASSWORDS.hash(password)
            if encoded is None
            else PASSWORDS.verify(password, encoded)
        )
    finally:
        HASH_SLOTS.release()


def strong_password(value):
    if not 15 <= len(value) <= 128:
        raise HTTPException(422, "Utiliza una contraseña de 15 a 128 caracteres.")
    return value


class LocalLimiter:
    """Bounded per-process sliding windows; never trusts forwarding headers."""

    def __init__(self):
        self.windows = OrderedDict()
        self.lock = threading.Lock()

    def check(self, key, maximum, seconds):
        stamp = time.monotonic()
        with self.lock:
            history = self.windows.pop(key, deque())
            while history and history[0] <= stamp - seconds:
                history.popleft()
            denied = len(history) >= maximum
            if not denied:
                history.append(stamp)
            self.windows[key] = history
            while len(self.windows) > 4096:
                self.windows.popitem(last=False)
            if denied:
                raise HTTPException(
                    429,
                    "Demasiados intentos. Espera antes de continuar.",
                    headers={"Retry-After": str(seconds)},
                )


def write_audit(
    session, event, user=None, workspace=None, resource=None, outcome="success"
):
    session.add(
        AuditEvent(
            event_type=event,
            user_id=user,
            workspace_id=workspace,
            resource_id=resource,
            outcome=outcome,
        )
    )


def audit_request(request, event, resource=None, outcome="success"):
    principal = request.state.principal
    with request.app.state.session_factory.begin() as session:
        write_audit(
            session,
            event,
            principal.user_id,
            getattr(request.state, "workspace_id", None),
            resource,
            outcome,
        )


def cookie_name(settings):
    return (
        "__Host-blackbox_session"
        if settings.deployment_mode == "https"
        else "blackbox_session"
    )


def csrf_cookie_name(settings):
    return (
        "__Host-blackbox_csrf"
        if settings.deployment_mode == "https"
        else "blackbox_csrf"
    )


def set_cookies(response, token, csrf, settings):
    options = {
        "secure": settings.deployment_mode == "https",
        "samesite": "strict",
        "path": "/",
        "max_age": settings.session_hours * 3600,
    }
    response.set_cookie(cookie_name(settings), token, httponly=True, **options)
    response.set_cookie(csrf_cookie_name(settings), csrf, httponly=False, **options)


def clear_cookies(response, settings):
    for name in (cookie_name(settings), csrf_cookie_name(settings)):
        response.delete_cookie(
            name,
            path="/",
            secure=settings.deployment_mode == "https",
            samesite="strict",
        )


@dataclass(frozen=True)
class Principal:
    user_id: str
    session_id: str
    email: str
    workspace_id: str | None
    csrf_hash: str


def trusted_mutation(request):
    settings = get_settings()
    if (
        request.headers.get("origin")
        not in [*settings.cors_origins, str(request.base_url).rstrip("/")]
        or request.headers.get("x-blackbox-request") != "1"
    ):
        raise HTTPException(403, "Origen o protección CSRF no válidos.")
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(415, "Usa contenido JSON para esta operación.")


def get_current_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> Principal:
    cached = getattr(request.state, "principal", None)
    if cached:
        return cached
    settings = get_settings()
    raw = request.cookies.get(cookie_name(settings), "")
    if not 32 <= len(raw) <= 128:
        raise HTTPException(401, "Inicia sesión para continuar.")
    row = session.scalar(
        select(AuthSession).where(AuthSession.token_hash == digest(raw))
    )
    stamp = now()
    if (
        row is None
        or row.revoked_at
        or aware(row.expires_at) <= stamp
        or aware(row.last_seen_at) + timedelta(minutes=settings.session_idle_minutes)
        <= stamp
    ):
        raise HTTPException(401, "La sesión ha expirado o ha sido revocada.")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "La sesión no está disponible.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        trusted_mutation(request)
        csrf = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get(csrf_cookie_name(settings), "")
        if (
            not 32 <= len(csrf) <= 128
            or not secrets.compare_digest(csrf, cookie)
            or not secrets.compare_digest(digest(csrf), row.csrf_hash)
        ):
            raise HTTPException(403, "Token CSRF no válido.")
    # Throttle writes for polling. Absolute expiry never slides.
    if stamp - aware(row.last_seen_at) >= timedelta(minutes=1):
        row.last_seen_at = stamp
        session.commit()
    principal = Principal(
        user.id, row.id, user.email, row.active_workspace_id, row.csrf_hash
    )
    request.state.principal = principal
    return principal


def issue_session(session, user, response, settings):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    membership = session.scalar(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(WorkspaceMembership.created_at, WorkspaceMembership.workspace_id)
        .limit(1)
    )
    row = AuthSession(
        user_id=user.id,
        token_hash=digest(token),
        csrf_hash=digest(csrf),
        active_workspace_id=membership.workspace_id if membership else None,
        expires_at=now() + timedelta(hours=settings.session_hours),
    )
    session.add(row)
    set_cookies(response, token, csrf, settings)
    return row, csrf


def bootstrap_invitation(session):
    begin_write(session)
    if session.scalar(select(func.count()).select_from(User)):
        raise ValueError("El bootstrap solo está disponible antes del primer usuario.")
    session.execute(
        delete(RegistrationInvite).where(RegistrationInvite.bootstrap_slot == 1)
    )
    raw = secrets.token_urlsafe(32)
    row = RegistrationInvite(
        token_hash=digest(raw),
        role="owner",
        bootstrap_slot=1,
        expires_at=now() + timedelta(minutes=15),
    )
    session.add(row)
    write_audit(session, "registration.bootstrap_issued")
    session.commit()
    return raw


def usable_invite(session, token, email):
    row = session.scalar(
        select(RegistrationInvite).where(RegistrationInvite.token_hash == digest(token))
    )
    if (
        row is None
        or row.used_at
        or aware(row.expires_at) <= now()
        or (row.email is not None and row.email != email)
    ):
        raise HTTPException(403, "Invitación no válida o no disponible.")
    if row.workspace_id is None and session.scalar(
        select(func.count()).select_from(User)
    ):
        raise HTTPException(403, "El bootstrap ya no está disponible.")
    return row


def session_data(session, principal, csrf=None):
    rows = session.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == principal.user_id)
        .order_by(Workspace.created_at, Workspace.id)
    ).all()
    auth_session = session.get(AuthSession, principal.session_id)
    return {
        "user": {"id": principal.user_id, "email": principal.email},
        "active_workspace_id": auth_session.active_workspace_id,
        "expires_at": aware(auth_session.expires_at).isoformat(),
        "csrf_token": csrf,
        "workspaces": [
            {"id": workspace.id, "name": workspace.name, "role": role}
            for workspace, role in rows
        ],
    }
