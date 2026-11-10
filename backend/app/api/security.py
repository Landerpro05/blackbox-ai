import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.access import WorkspaceAccess, get_workspace_access
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
from app.schemas.security import (
    AcceptInvite,
    ChangePassword,
    Credentials,
    InviteInput,
    MemberRole,
    Register,
    WorkspaceInput,
    WorkspaceSelection,
)
from app.services.security import (
    Principal,
    aware,
    clear_cookies,
    csrf_cookie_name,
    digest,
    get_current_user,
    issue_session,
    now,
    password_operation,
    session_data,
    strong_password,
    trusted_mutation,
    usable_invite,
    write_audit,
)

router = APIRouter(prefix="/api/v1", tags=["security"])
Database = Annotated[Session, Depends(get_session)]
Identity = Annotated[Principal, Depends(get_current_user)]
Access = Annotated[WorkspaceAccess, Depends(get_workspace_access)]


def throttle(request, email=""):
    trusted_mutation(request)
    settings = get_settings()
    host = (
        "local"
        if settings.deployment_mode == "local"
        else request.client.host
        if request.client
        else "unknown"
    )
    limiter = request.app.state.rate_limiter
    limiter.check(
        ("auth_ip", host), settings.auth_attempts * 4, settings.auth_window_seconds
    )
    limiter.check(
        ("auth_identity", digest(email) if email else host),
        settings.auth_attempts,
        settings.auth_window_seconds,
    )


@router.get("/auth/capabilities")
def auth_capabilities():
    return {
        "registration": "invitation_only",
        "password_reset": False,
        "minimum_password_length": 12,
        "session_cookie": "HttpOnly; SameSite=Strict",
        "deployment_mode": get_settings().deployment_mode,
    }


@router.post("/auth/login")
def login(data: Credentials, request: Request, response: Response, session: Database):
    throttle(request, str(data.email))
    user = session.scalar(select(User).where(User.email == str(data.email)))
    encoded = user.password_hash if user else request.app.state.dummy_password_hash
    valid = password_operation(data.password.get_secret_value(), encoded)
    if not valid or user is None or not user.is_active:
        write_audit(
            session, "auth.login_failed", user.id if user else None, outcome="denied"
        )
        session.commit()
        raise HTTPException(401, "Credenciales no válidas.")
    identifier = user.id
    session.rollback()
    begin_write(session)
    user = session.scalar(
        select(User).where(
            User.id == identifier,
            User.password_hash == encoded,
            User.is_active.is_(True),
        )
    )
    if user is None:
        raise HTTPException(401, "Credenciales no válidas.")
    # Bound live sessions without storing or returning bearer credentials.
    existing = list(
        session.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .order_by(AuthSession.created_at.desc())
        )
    )
    for old in existing[4:]:
        old.revoked_at = now()
    row, csrf = issue_session(session, user, response, get_settings())
    session.flush()
    write_audit(session, "auth.login", user.id, row.active_workspace_id, row.id)
    session.commit()
    principal = Principal(
        user.id, row.id, user.email, row.active_workspace_id, row.csrf_hash
    )
    return session_data(session, principal, csrf)


@router.post("/auth/register", status_code=201)
def register(data: Register, request: Request, response: Response, session: Database):
    throttle(request, str(data.email))
    raw_password = strong_password(data.password.get_secret_value())
    # Reject invalid invitations before allocating Argon2 resources.
    usable_invite(session, data.invitation, str(data.email))
    session.rollback()
    encoded = password_operation(raw_password)
    begin_write(session)
    invitation = usable_invite(session, data.invitation, str(data.email))
    if session.scalar(select(User.id).where(User.email == str(data.email))):
        raise HTTPException(
            409,
            "No se pudo completar el registro. Usa una cuenta existente o revisa la invitación.",
        )
    user = User(email=str(data.email), password_hash=encoded)
    session.add(user)
    session.flush()
    workspace_id = invitation.workspace_id
    if workspace_id is None:
        workspace = Workspace(name=data.workspace_name)
        session.add(workspace)
        session.flush()
        workspace_id = workspace.id
    session.add(
        WorkspaceMembership(
            user_id=user.id, workspace_id=workspace_id, role=invitation.role
        )
    )
    invitation.used_at, invitation.bootstrap_slot = now(), None
    session.flush()
    row, csrf = issue_session(session, user, response, get_settings())
    session.flush()
    write_audit(session, "auth.register", user.id, workspace_id, user.id)
    session.commit()
    return session_data(
        session,
        Principal(user.id, row.id, user.email, workspace_id, row.csrf_hash),
        csrf,
    )


@router.get("/auth/session")
def current(
    request: Request, response: Response, identity: Identity, session: Database
):
    csrf = request.cookies.get(csrf_cookie_name(get_settings()), "")
    if not 32 <= len(csrf) <= 128 or not secrets.compare_digest(
        digest(csrf), identity.csrf_hash
    ):
        csrf = secrets.token_urlsafe(32)
        session.get(AuthSession, identity.session_id).csrf_hash = digest(csrf)
        response.set_cookie(
            csrf_cookie_name(get_settings()),
            csrf,
            httponly=False,
            secure=get_settings().deployment_mode == "https",
            samesite="strict",
            path="/",
            max_age=get_settings().session_hours * 3600,
        )
        session.commit()
    return session_data(session, identity, csrf)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, identity: Identity, session: Database):
    session.get(AuthSession, identity.session_id).revoked_at = now()
    write_audit(
        session,
        "auth.logout",
        identity.user_id,
        identity.workspace_id,
        identity.session_id,
    )
    session.commit()
    clear_cookies(response, get_settings())


@router.post("/auth/password", status_code=204)
def change_password(
    data: ChangePassword,
    response: Response,
    identity: Identity,
    session: Database,
    request: Request,
):
    request.app.state.rate_limiter.check(("password", identity.user_id), 5, 900)
    user = session.get(User, identity.user_id)
    encoded = user.password_hash
    if not password_operation(data.current_password.get_secret_value(), encoded):
        raise HTTPException(403, "No se pudo confirmar la contraseña actual.")
    replacement = password_operation(
        strong_password(data.new_password.get_secret_value())
    )
    session.rollback()
    begin_write(session)
    user = session.scalar(
        select(User).where(User.id == identity.user_id, User.password_hash == encoded)
    )
    if user is None:
        raise HTTPException(409, "La cuenta cambió; vuelve a iniciar sesión.")
    user.password_hash = replacement
    session.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id)
        .values(revoked_at=now())
    )
    write_audit(
        session, "auth.password_changed", user.id, identity.workspace_id, user.id
    )
    session.commit()
    clear_cookies(response, get_settings())


@router.get("/auth/sessions")
def sessions(identity: Identity, session: Database):
    rows = session.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == identity.user_id)
        .order_by(AuthSession.created_at.desc())
        .limit(20)
    )
    return {
        "items": [
            {
                "id": row.id,
                "current": row.id == identity.session_id,
                "created_at": aware(row.created_at),
                "expires_at": aware(row.expires_at),
                "last_seen_at": aware(row.last_seen_at),
                "revoked": row.revoked_at is not None,
            }
            for row in rows
        ]
    }


@router.delete("/auth/sessions/{session_id}", status_code=204)
def revoke(session_id: UUID, identity: Identity, session: Database, response: Response):
    row = session.scalar(
        select(AuthSession).where(
            AuthSession.id == str(session_id), AuthSession.user_id == identity.user_id
        )
    )
    if row is None:
        raise HTTPException(404, "Sesión no disponible.")
    row.revoked_at = now()
    write_audit(
        session, "auth.session_revoked", identity.user_id, identity.workspace_id, row.id
    )
    session.commit()
    if row.id == identity.session_id:
        clear_cookies(response, get_settings())


@router.post("/auth/workspace")
def select_workspace(data: WorkspaceSelection, identity: Identity, session: Database):
    if session.get(WorkspaceMembership, (identity.user_id, data.workspace_id)) is None:
        raise HTTPException(404, "Workspace no disponible.")
    session.get(
        AuthSession, identity.session_id
    ).active_workspace_id = data.workspace_id
    session.commit()
    return {"workspace_id": data.workspace_id}


@router.post("/workspaces", status_code=201)
def create_workspace(data: WorkspaceInput, identity: Identity, session: Database):
    begin_write(session)
    count = session.scalar(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == identity.user_id)
    )
    if count >= 20:
        raise HTTPException(
            422, "Se alcanzó el límite local de 20 membresías por usuario."
        )
    row = Workspace(name=data.name)
    session.add(row)
    session.flush()
    session.add(
        WorkspaceMembership(user_id=identity.user_id, workspace_id=row.id, role="owner")
    )
    write_audit(session, "workspace.created", identity.user_id, row.id, row.id)
    session.commit()
    return {"id": row.id, "name": row.name, "role": "owner"}


def owner(access):
    if access.role != "owner":
        raise HTTPException(403, "Esta operación requiere el rol owner.")


def locked_owner(session, access):
    owner(access)
    begin_write(session)
    caller = session.get(
        WorkspaceMembership,
        (access.user_id, access.workspace_id),
        populate_existing=True,
    )
    if caller is None or caller.role != "owner":
        raise HTTPException(403, "La membresía cambió. Actualiza tu sesión.")


def same_workspace(identifier, access):
    if identifier != access.workspace_id:
        raise HTTPException(404, "Workspace no disponible.")


@router.patch("/workspaces/{workspace_id}")
def rename(workspace_id: str, data: WorkspaceInput, access: Access, session: Database):
    same_workspace(workspace_id, access)
    locked_owner(session, access)
    row = session.get(Workspace, workspace_id)
    row.name = data.name
    write_audit(
        session, "workspace.updated", access.user_id, workspace_id, workspace_id
    )
    session.commit()
    return {"id": row.id, "name": row.name}


@router.get("/workspaces/{workspace_id}/members")
def members(
    workspace_id: str,
    access: Access,
    session: Database,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    same_workspace(workspace_id, access)
    rows = session.execute(
        select(User, WorkspaceMembership)
        .join(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(WorkspaceMembership.created_at, User.id)
        .limit(50)
        .offset(offset)
    ).all()
    return {
        "items": [
            {
                "user_id": user.id,
                "email": user.email,
                "role": membership.role,
                "created_at": aware(membership.created_at),
            }
            for user, membership in rows
        ],
        "total": session.scalar(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(WorkspaceMembership.workspace_id == workspace_id)
        )
        or 0,
        "offset": offset,
        "limit": 50,
    }


def require_member_change(session, access, user_id, role=None):
    locked_owner(session, access)
    row = session.get(
        WorkspaceMembership, (user_id, access.workspace_id), populate_existing=True
    )
    if row is None:
        raise HTTPException(404, "Miembro no disponible.")
    if row.role == "owner" and role != "owner":
        owners = session.scalar(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(
                WorkspaceMembership.workspace_id == access.workspace_id,
                WorkspaceMembership.role == "owner",
            )
        )
        if owners <= 1:
            raise HTTPException(409, "El workspace debe conservar al menos un owner.")
    return row


@router.patch("/workspaces/{workspace_id}/members/{user_id}")
def role_change(
    workspace_id: str,
    user_id: UUID,
    data: MemberRole,
    access: Access,
    session: Database,
):
    same_workspace(workspace_id, access)
    row = require_member_change(session, access, str(user_id), data.role)
    row.role = data.role
    write_audit(
        session, "workspace.role_changed", access.user_id, workspace_id, str(user_id)
    )
    session.commit()
    return {"user_id": row.user_id, "role": row.role}


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
def remove_member(workspace_id: str, user_id: UUID, access: Access, session: Database):
    same_workspace(workspace_id, access)
    row = require_member_change(session, access, str(user_id))
    session.delete(row)
    write_audit(
        session, "workspace.member_removed", access.user_id, workspace_id, str(user_id)
    )
    session.commit()


@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def invite(workspace_id: str, data: InviteInput, access: Access, session: Database):
    same_workspace(workspace_id, access)
    locked_owner(session, access)
    token = secrets.token_urlsafe(32)
    row = RegistrationInvite(
        token_hash=digest(token),
        email=str(data.email),
        workspace_id=workspace_id,
        role=data.role,
        expires_at=now() + timedelta(hours=24),
    )
    session.add(row)
    session.flush()
    write_audit(
        session, "workspace.invitation_created", access.user_id, workspace_id, row.id
    )
    session.commit()
    return {"id": row.id, "invitation": token, "expires_at": aware(row.expires_at)}


@router.post("/auth/invitations/accept", status_code=204)
def accept(data: AcceptInvite, identity: Identity, session: Database):
    begin_write(session)
    row = usable_invite(session, data.invitation, identity.email)
    if row.workspace_id is None:
        raise HTTPException(403, "Invitación no disponible.")
    if session.get(WorkspaceMembership, (identity.user_id, row.workspace_id)):
        raise HTTPException(409, "Ya perteneces a este workspace.")
    if session.scalar(select(func.count()).select_from(WorkspaceMembership).where(WorkspaceMembership.user_id == identity.user_id)) >= 20:
        raise HTTPException(422, "Se alcanzó el límite local de 20 membresías por usuario.")
    session.add(
        WorkspaceMembership(
            user_id=identity.user_id, workspace_id=row.workspace_id, role=row.role
        )
    )
    row.used_at = now()
    write_audit(
        session,
        "workspace.invitation_accepted",
        identity.user_id,
        row.workspace_id,
        identity.user_id,
    )
    session.commit()


@router.get("/workspaces/{workspace_id}/audit")
def audit(
    workspace_id: str,
    access: Access,
    session: Database,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    same_workspace(workspace_id, access)
    if access.role not in {"owner", "admin"}:
        raise HTTPException(403, "Consultar auditoría requiere owner o admin.")
    scope = or_(
        AuditEvent.workspace_id == workspace_id,
        and_(AuditEvent.workspace_id.is_(None), AuditEvent.user_id == access.user_id),
    )
    rows = session.scalars(
        select(AuditEvent)
        .where(scope)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
        .limit(50)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": row.id,
                "event_type": row.event_type,
                "user_id": row.user_id,
                "workspace_id": row.workspace_id,
                "resource_id": row.resource_id,
                "outcome": row.outcome,
                "created_at": aware(row.created_at),
            }
            for row in rows
        ],
        "total": session.scalar(
            select(func.count()).select_from(AuditEvent).where(scope)
        )
        or 0,
        "offset": offset,
        "limit": 50,
    }
