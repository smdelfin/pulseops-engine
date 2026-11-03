import asyncio
# Runtime: Provides the event loop for async operations.
# Architecture: Needed for running async migration logic.
# Summary: Imports Python's asyncio module.
from logging.config import fileConfig
# Runtime: Loads logging configuration from file.
# Architecture: Allows custom loggers to be set via alembic.cfg.
# Summary: Imports fileConfig to read logging settings.

from alembic import context
# Runtime: Alembic migration context used to configure and run migrations.
# Architecture: Central interface for Alembic migrations.
# Summary: Imports context from Alembic.
from sqlalchemy import pool
# Runtime: SQLAlchemy connection pool abstractions.
# Architecture: Pool classes used when creating engines.
# Summary: Imports pool for engine configuration.
from sqlalchemy.ext.asyncio import async_engine_from_config
# Runtime: Creates async SQLAlchemy engine from config.
# Architecture: Enables asynchronous migrations.
# Summary: Imports coroutine engine builder for Alembic.

from src.core.config import settings
# Runtime: Loads application settings, including DATABASE_URL.
# Architecture: Keeps DB connection info centralized.
# Summary: Imports settings for DB URL.
from src.core.db import Base
# Runtime: Declarative base for SQLAlchemy models.
# Architecture: Provides metadata for Alembic.
# Summary: Imports Base.
from src.models.student import Student  # noqa: F401
# Runtime: Imports Student model so its tables are known.
# Architecture: Ensures model classes are registered with metadata.
# Summary: Imports Student for metadata discovery.


config = context.config
# Runtime: Retrieves Alembic configuration object.
# Architecture: Holds config values like script location.
# Summary: Assigns Alembic config to a variable.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
    # Runtime: Loads the logging configuration from the Alembic .ini file.
    # Architecture: Allows customizable logging during migrations.
    # Summary: Reads logging settings if config file exists.

target_metadata = Base.metadata
# Runtime: Provides table metadata for Alembic.
# Architecture: Base.metadata contains all model table definitions.
# Summary: Sets target_metadata used by migrations.



def run_migrations_offline() -> None:
    # Runtime: Configures Alembic to generate SQL scripts without a DB connection.
    # Architecture: Uses literal_binds to embed values directly in statements.
    # Summary: Prepares offline migration run.
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
        # Runtime: Executes migration commands, writing SQL to stdout.
        # Architecture: Supports migration scripts on systems without direct DB access.
        # Summary: Runs offline migrations.



def do_run_migrations(connection) -> None:
    # Runtime: Receives an SQLAlchemy connection to run migrations against.
    # Architecture: Keeps actual migration steps in a separate function.
    # Summary: Configures Alembic with the live connection.
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
        # Runtime: Executes the migration commands on the live database.
        # Architecture: Ensures changes are applied atomically.
        # Summary: Runs migrations within a transaction.



async def run_migrations_online() -> None:
    # Runtime: Builds an async SQLAlchemy engine from config.
    # Architecture: Enables async migration scripts compatible with async DB drivers.
    # Summary: Creates async engine for database connection.
    connectable = async_engine_from_config(
        {},
        url=settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        # Runtime: Synchronously runs migration within async context.
        # Architecture: Uses run_sync to bridge sync Alembic code.
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
    # Runtime: Cleans up connection pool after migration.
    # Architecture: Prevents resource leaks.
    # Summary: Executes online migrations and disposes engine.



if context.is_offline_mode():
    # Runtime: Checks if Alembic is configured to run offline.
    # Architecture: Decides between offline and online migration paths.
    # Summary: Determines migration execution mode.
    run_migrations_offline()
else:
    # Runtime: If not offline, run migrations using asyncio loop.
    # Architecture: Handles async database connections.
    # Summary: Starts online migration execution.
    asyncio.run(run_migrations_online())
