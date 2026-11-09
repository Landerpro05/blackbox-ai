from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.core.database import Base, build_engine
from app import models  # noqa: F401 — registers all models

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

engine = build_engine(get_settings().database_url)
try:
    if context.is_offline_mode():
        context.configure(
            url=engine.url,
            target_metadata=Base.metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=Base.metadata,
                render_as_batch=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
finally:
    engine.dispose()
