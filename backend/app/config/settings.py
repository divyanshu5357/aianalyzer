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

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


settings = Settings()
# Reload settings from .env