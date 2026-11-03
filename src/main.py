# Import the built‑in logging module to capture runtime events for the application launch.
import logging
# Import the FastAPI app instance that holds all route and middleware definitions.
from src.api.webhooks import app
# Import the SQLAlchemy engine that encapsulates the database connection details.
from src.core.db import engine

# Create a logger specific to this module to isolate startup logs from other components.
logger = logging.getLogger(__name__)

# Register an asynchronous startup event with FastAPI so that initialization logic runs before the first request.
@app.on_event("startup")
async def startup():
    # Log a friendly message that the engine is starting up for observability.
    logger.info("Starting up PulseOps-Engine...")
    # Inform operators that database migrations should be applied via Alembic and not by running this file.
    logger.info("Database schema must be managed by Alembic before startup.")