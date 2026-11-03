# Import BaseSettings from pydantic_settings to define a configuration schema that validates environment variables at runtime.
from pydantic_settings import BaseSettings
# Import Optional from typing to handle configuration keys that are not mandatory for all environments.
from typing import Optional

# Define the application's configuration schema using a class-based approach for structured settings.
class Settings(BaseSettings):
    # The primary connection string for the PostgreSQL database, injected via Docker or .env files.
    DATABASE_URL: str
    # The connection string for Azure Storage, required for both Blob and Queue interactions.
    AZURE_STORAGE_CONNECTION_STRING: str
    # The OAuth2 token used to authenticate all requests to the ClickUp API.
    CLICKUP_API_TOKEN: str
    # The specific team identifier in ClickUp, allowing for multi-tenant organizational targeting.
    CLICKUP_TEAM_ID: Optional[str] = None
    # The ID for the default list where new students will be provisioned as tasks.
    CLICKUP_DEFAULT_LIST_ID: str
    # A secret key for validating incoming GoHighLevel webhook signatures.
    GHL_WEBHOOK_SECRET: str
    # A separate secret key for validating incoming ClickUp webhook signatures.
    CLICKUP_WEBHOOK_SECRET: str

    # Internal configuration class to manage how Pydantic discovers these values.
    class Config:
        # Automatically attempt to read variables from a .env file in the project root.
        env_file = ".env"
        # Ignore extra environment variables that are not defined in this class to prevent errors.
        extra = "ignore"

# Instantiate a singleton settings object to be imported by all service modules.
settings = Settings()