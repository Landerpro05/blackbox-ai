"""Trusted local operator commands. No HTTP bypass and no automatic ownership."""

import argparse
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import begin_write, build_engine, session_factory
from app.models import AIAnalysis, Project, Run
from app.models.security import User, Workspace, WorkspaceMembership
from app.services.security import bootstrap_invitation, write_audit


def adopt_legacy(session, email, confirm):
    begin_write(session)
    user = session.scalar(
        select(User).where(
            User.email == email.strip().casefold(), User.is_active.is_(True)
        )
    )
    if not confirm or user is None:
        raise ValueError("La adopción requiere usuario activo y --confirm-adoption.")
    if session.scalar(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == "local")
    ):
        raise ValueError(
            "El workspace histórico ya tiene miembros; usa su administración autenticada."
        )
    active_run = session.scalar(
        select(Run.id).where(Run.workspace_id == "local", Run.active_slot == 1).limit(1)
    )
    active_ai = session.scalar(
        select(AIAnalysis.id)
        .where(AIAnalysis.workspace_id == "local", AIAnalysis.active_slot == 1)
        .limit(1)
    )
    if active_run or active_ai:
        raise ValueError(
            "Espera a que terminen las tareas antes de adoptar el histórico."
        )
    if session.scalar(select(func.count()).select_from(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)) >= 20:
        raise ValueError("El usuario ya tiene 20 membresías; elige otro usuario autorizado para adoptar el histórico.")
    session.add(
        WorkspaceMembership(user_id=user.id, workspace_id="local", role="owner")
    )
    workspace = session.get(Workspace, "local")
    if workspace.name == "Histórico sin asociar":
        workspace.name = "Workspace histórico"
    write_audit(session, "workspace.legacy_adopted", user.id, "local", "local")
    session.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Operaciones de administrador local BLACKBOX AI"
    )
    parser.add_argument(
        "command", choices=["registration-code", "legacy-status", "adopt-legacy"]
    )
    parser.add_argument("--email")
    parser.add_argument("--confirm-adoption", action="store_true")
    args = parser.parse_args(argv)
    engine = build_engine(get_settings().database_url)
    try:
        with session_factory(engine)() as session:
            if args.command == "registration-code":
                # Explicit secret issuance to the operator's terminal, never a log.
                print(bootstrap_invitation(session))
            elif args.command == "legacy-status":
                print(
                    {
                        "projects": session.scalar(
                            select(func.count())
                            .select_from(Project)
                            .where(Project.workspace_id == "local")
                        ),
                        "members": session.scalar(
                            select(func.count())
                            .select_from(WorkspaceMembership)
                            .where(WorkspaceMembership.workspace_id == "local")
                        ),
                    }
                )
            else:
                if not args.email:
                    parser.error("Indica --email del usuario que adoptará los datos.")
                adopt_legacy(session, args.email, args.confirm_adoption)
                print("Workspace histórico asociado explícitamente.")
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
