from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unrelated env vars (e.g., database_url)
    )

    GCS_BUCKET_NAME: str
    GCS_BASE_PATH: str = "prt"
    SIGNED_URL_EXPIRATION_SECONDS: int = 900  # 15 minutes
    GOOGLE_CLOUD_PROJECT: Optional[str] = None


settings = Settings()
