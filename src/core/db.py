# Import core SQLAlchemy tools for asynchronous database interactions and session management.
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# Import declarative_base to define models that map directly to database tables.
from sqlalchemy.orm import declarative_base
# Import the settings singleton to access the environment-provided database URL.
from src.core.config import settings

# Assign the database connection string from the configuration object.
DATABASE_URL = settings.DATABASE_URL
# Validate that the database driver is correct for asynchronous PostgreSQL interactions.
if not DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError("DATABASE_URL must use the postgresql+asyncpg driver")

# Initialize the asynchronous engine with connection pooling and auto-reconnect settings.
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
# Create a session factory to produce scoped asynchronous sessions for each request context.
SessionLocal = async_sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)

# Registry for all SQLAlchemy models.
Base = declarative_base()

# Dependency injection function for FastAPI to provide a database session per request.
async def get_db():
    # Yield a session context manager to ensure automatic cleanup after the request completes.
    async with SessionLocal() as session:
        yield session
