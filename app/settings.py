from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra='ignore')

    DATABASE_URL: str = "postgresql://user:password@localhost:5432/testdb"
    ENV: str = "development"
    SECRET_KEY: str = "super-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    GOOGLE_CLOUD_PROJECT: str = "projectprt"
    GCS_BUCKET_NAME: str = "acct-docs-dev"
    SIGNED_URL_EXPIRATION_SECONDS: int = 900
    GOOGLE_APPLICATION_CREDENTIALS: str = "service-account.json"

settings = Settings()
