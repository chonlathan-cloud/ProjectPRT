from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/testdb"
    ENV: str = "development"
    # JWT settings (must come from environment; do not hardcode secrets)
    SECRET_KEY: str = ""  # JWT secret
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Phase 2/3 flags
    USE_MOCK_DATA: bool = True

    # CORS (local frontend dev)
    CORS_ALLOW_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

    # Google SSO
    GOOGLE_CLIENT_ID: str = ""


    GOOGLE_CLOUD_PROJECT: str = "projectprt"
    GCS_BUCKET_NAME: str = "acct-docs-dev"
    SIGNED_URL_EXPIRATION_SECONDS: int = 900
    GOOGLE_APPLICATION_CREDENTIALS: str = "service-account.json"

settings = Settings()

# Basic runtime validation (avoid hardcoding secrets)
if settings.ENV != "development" and not settings.SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment (.env) and must not be empty")
