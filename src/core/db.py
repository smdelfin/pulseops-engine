# Import SQLAlchemy's async engine and session factory primitives for non-blocking PostgreSQL access.
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# Import the declarative base factory that registers ORM models in shared metadata.
from sqlalchemy.orm import declarative_base
# Import validated configuration so the database layer has one authoritative connection URL.
from src.core.config import settings

# Copy the configured URL into a local constant used to create the engine.
DATABASE_URL = settings.DATABASE_URL
# Fail during startup if the URL would select a synchronous or non-PostgreSQL driver.
if not DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError("DATABASE_URL must use the postgresql+asyncpg driver")

# Create the process-wide async engine, whose pool reuses database connections across requests.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
# Create a factory that gives each request or job an independently managed AsyncSession.
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

# Create the metadata registry Alembic and SQLAlchemy use to discover mapped tables.
Base = declarative_base()

# Expose a FastAPI-compatible dependency that controls session lifetime at the request boundary.
async def get_db():
    # Open a session for the caller and close it deterministically when request handling ends.
    async with SessionLocal() as session:
        yield session
