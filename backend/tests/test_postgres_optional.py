"""Optional auth-table contract, never a claim of full PostgreSQL support."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from app.core.database import begin_write
from app.models.security import AuthSession, User, Workspace, WorkspaceMembership
from app.services.security import digest, now
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema


def test_optional_postgres_auth_schema_contract():
    configured = os.environ.get("BLACKBOX_TEST_POSTGRES_URL")
    if not configured:
        pytest.skip(
            "PostgreSQL de pruebas no configurado; compatibilidad completa no verificada."
        )
    pytest.importorskip(
        "psycopg",
        reason="Instala el driver opcional en el entorno de pruebas PostgreSQL.",
    )
    url = make_url(configured)
    if (
        url.get_backend_name() != "postgresql"
        or url.host not in {"127.0.0.1", "::1"}
        or not (url.database or "").startswith("blackbox_test")
    ):
        pytest.fail(
            "La integración opcional requiere PostgreSQL loopback y base dedicada blackbox_test*."
        )
    from auth_support import synthetic_hash

    engine = create_engine(
        url.set(drivername="postgresql+psycopg"),
        hide_parameters=True,
        pool_size=1,
        max_overflow=0,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.connect() as raw:
            transaction = raw.begin()
            try:
                schema = "blackbox_test_" + uuid4().hex
                raw.execute(CreateSchema(schema))
                connection = raw.execution_options(schema_translate_map={None: schema})
                for model in [User, Workspace, WorkspaceMembership, AuthSession]:
                    model.__table__.create(connection)
                with Session(
                    bind=connection, join_transaction_mode="create_savepoint"
                ) as session:
                    begin_write(session)
                    user = User(
                        email="postgres-fixture@example.com",
                        password_hash=synthetic_hash(),
                    )
                    workspace = Workspace(name="Contrato PostgreSQL")
                    session.add_all([user, workspace])
                    session.flush()
                    session.add(
                        WorkspaceMembership(
                            user_id=user.id, workspace_id=workspace.id, role="owner"
                        )
                    )
                    session.add(
                        AuthSession(
                            user_id=user.id,
                            token_hash=digest("synthetic-session"),
                            csrf_hash=digest("synthetic-csrf"),
                            active_workspace_id=workspace.id,
                            expires_at=now() + timedelta(hours=1),
                        )
                    )
                    session.flush()
                    assert session.scalar(select(WorkspaceMembership.role)) == "owner"
                    with pytest.raises(IntegrityError), session.begin_nested():
                        session.get(
                            WorkspaceMembership, (user.id, workspace.id)
                        ).role = "invalid"
                        session.flush()
                    session.commit()
            finally:
                transaction.rollback()  # PostgreSQL rolls back the temporary schema too.
    finally:
        engine.dispose()
