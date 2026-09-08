from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Organization Agent"
    app_env: str = "development"
    debug: bool = True

    database_url: str

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gemini_enabled: bool = False
    gemini_cooldown_seconds: int = 300

    allow_data_reset: bool = False

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j_password"
    neo4j_database: str = "neo4j"
    neo4j_enabled: bool = True

    # Object Storage Settings (R2 / S3 / Local fallback)
    storage_provider: str = "local"
    storage_endpoint_url: str | None = None
    storage_bucket: str = "ai-agent-datasets"
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    storage_region: str = "auto"
    storage_public_url: str | None = None
    storage_retention_days: int = 30
    storage_delete_after_ingestion: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


settings = Settings()
# Reload settings from .env