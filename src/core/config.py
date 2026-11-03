# Import Pydantic's settings base so environment-backed configuration is parsed and validated when the process starts.
from pydantic_settings import BaseSettings
# Import Optional so deployment-specific settings can explicitly represent an absent value.
from typing import Optional

# Define one typed configuration contract that every API, worker, and migration process can share.
class Settings(BaseSettings):
    # Require the async PostgreSQL URL used by SQLAlchemy to open database connections.
    DATABASE_URL: str
    # Require the Azure Storage connection string used by the queue integration.
    AZURE_STORAGE_CONNECTION_STRING: str
    # Require the bearer token that authenticates outbound ClickUp API calls.
    CLICKUP_API_TOKEN: str
    # Allow an optional ClickUp team identifier because some flows can operate without it locally.
    CLICKUP_TEAM_ID: Optional[str] = None
    # Require the ClickUp list destination used when creating onboarding work.
    CLICKUP_DEFAULT_LIST_ID: str
    # Require the shared secret used to authenticate GoHighLevel webhook requests.
    GHL_WEBHOOK_SECRET: str
    # Require the separate shared secret used to authenticate ClickUp webhook requests.
    CLICKUP_WEBHOOK_SECRET: str

    # Configure how Pydantic resolves values without scattering environment parsing across services.
    class Config:
        # Load developer-local values from the repository's .env file when present.
        env_file = ".env"
        # Ignore unrelated container variables so shared Compose environments remain compatible.
        extra = "ignore"

# Build one validated settings object so all modules use the same startup-time configuration.
settings = Settings()