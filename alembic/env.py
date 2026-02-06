"""
Alembic environment configuration.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import all models to ensure they're registered with Base.metadata
from app.models.base import Base
from app.models import (
    Tenant,
    User,
    CostNature,
    Supplier,
    Contract,
    ContractRate,
    RateCatalog,
    Trip,
    TripDay,
    TripPaxConfig,
    Formula,
    Condition,
    Item,
    ItemSeason,
    Booking,
    PaymentSchedule,
    AIAlert,
    AuditLog,
)
from app.config import get_settings

settings = get_settings()

# this is the Alembic Config object
config = context.config

# Override sqlalchemy.url with our settings (use sync driver for migrations)
sync_url = settings.database_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
