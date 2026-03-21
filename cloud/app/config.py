from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Force-load .env into os.environ before pydantic reads settings.
# Path is resolved relative to this file so it works regardless of CWD.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=False)

# AWS/container defaults. Production deploys should override these via env.
_DEFAULT_DB_URL = "postgresql+psycopg2://hivemind:hivemind@postgres:5432/hivemind"
_DEFAULT_VECTOR_DB_URL = "http://qdrant:6333"


class Settings(BaseSettings):

    # Default user passwords (used when seeding the database for the first time)
    DEFAULT_ADMIN_PASSWORD: str = "hivemind-admin-2024"
    DEFAULT_CLIENT_PASSWORD: str = "hivemind-client-2024"

    # API Keys
    ANTHROPIC_API_KEY: str | None = None

    # Database
    DATABASE_URL: str = _DEFAULT_DB_URL
    VECTOR_DB_URL: str = _DEFAULT_VECTOR_DB_URL

    # Storage
    HIVEMIND_DATA_DIR: str | None = None  # Writable runtime state: logs, API key, settings
    S3_CREDENTIALS: str | None = None
    AWS_REGION: str | None = None
    S3_BUCKET: str | None = None
    HIVEMIND_UPLOADS_DIR: str | None = None  # Local file storage path (defaults to cloud/uploads/)

    # Auth
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60

    # RAG
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    RAG_CHUNK_MIN_TOKENS: int = 500
    RAG_CHUNK_MAX_TOKENS: int = 800
    RAG_CHUNK_OVERLAP: int = 80
    RAG_TOP_K: int = 8
    RAG_SIMILARITY_THRESHOLD: float = 0.0

    # Server
    AUTO_CREATE_TABLES: bool = True
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    # CORS - comma-separated list of allowed origins.
    # Default includes Tauri desktop origins and localhost dev servers.
    # Set to "*" to allow all origins (NOT recommended for production).
    CORS_ORIGINS: str = "tauri://localhost,https://tauri.localhost,http://localhost:1420,http://localhost:5173,http://localhost:3000"


settings = Settings()
