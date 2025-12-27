from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve repo root: .../ProjectPRT/app/core/settings.py -> parents[2] == repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    ENV: str = "development"

    # Database (Phase 4 will use this)
    DATABASE_URL: str = ""

    # JWT (do not hardcode secrets; set via .env)
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
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

    # GCS / storage
    GOOGLE_CLOUD_PROJECT: str = ""
    GCS_BUCKET_NAME: str = ""
    SIGNED_URL_EXPIRATION_SECONDS: int = 900
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # Admin bootstrap
    BOOTSTRAP_ADMIN_SUB: str = ""


settings = Settings()
