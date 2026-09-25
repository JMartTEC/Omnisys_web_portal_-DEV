"""Configuración por variables de entorno (Render -> Environment)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "GD 360 RAG API"
    ENV_NAME: str = "local"
    API_PREFIX: str = "/api/v1"

    # Seguridad
    JWT_SECRET: str = "solo-desarrollo-cambiar-en-render-0123456789"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    # Lista separada por comas. En Render: https://gd-portal.onrender.com
    CORS_ORIGINS: str = "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8080"

    # RAG
    EMBEDDINGS_PROVIDER: str = "hashing"   # hashing | openai
    EMBEDDINGS_MODEL: str = "text-embedding-3-small"
    EMBEDDINGS_DIM: int = 768
    VECTOR_STORE: str = "memory"           # memory | pgvector (pendiente)
    DATABASE_URL: str = ""                 # para pgvector
    LLM_PROVIDER: str = "extractive"       # extractive | openai
    LLM_BASE_URL: str = "https://api.openai.com/v1"  # cualquier API compatible (Azure OpenAI, vLLM, etc.)
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    CHUNK_SIZE: int = 900
    CHUNK_OVERLAP: int = 150
    MIN_SCORE: float = 0.08
    REMOTE_AGENT_TIMEOUT: float = 30.0

    # Ingesta
    MAX_UPLOAD_MB: int = 20
    CATALOGO_PATH: Path = BASE_DIR / "data" / "catalogo.json"

    # Inyectado por render.yaml (fromService.property=host) con el host del Static Site
    FRONTEND_HOST: str = ""

    @property
    def cors_list(self) -> list[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if self.FRONTEND_HOST:
            origins.append(f"https://{self.FRONTEND_HOST}")
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
