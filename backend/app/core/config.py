"""Configuración por variables de entorno (Render -> Environment)."""
import logging
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def leer_version() -> str:
    """Versión del portal (MAYOR.MENOR.PARCHE). Vive en backend/app/VERSION y la sube el pipeline."""
    try:
        return (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "GD 360 RAG API"
    ENV_NAME: str = "local"
    API_PREFIX: str = "/api/v1"

    # Seguridad. JWT_SECRET no tiene valor por omisión: en cualquier ambiente que no
    # sea "local" debe venir del entorno (en Azure, de Key Vault).
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480
    # Usuarios: archivo (solo desarrollo local) | cosmos (Azure, base "seguridad")
    AUTH_BACKEND: str = "archivo"
    AUTH_ARCHIVO_PATH: Path = BASE_DIR.parent / "datos_locales" / "usuarios.json"
    COSMOS_ENDPOINT: str = ""
    COSMOS_KEY: str = ""                  # vacío = identidad administrada
    COSMOS_DB_SEGURIDAD: str = "seguridad"
    COSMOS_CONTENEDOR_USUARIOS: str = "usuarios"
    COOKIE_SEGURA: bool = True            # solo HTTPS; en local se pone false
    SESION_COOKIE: str = "gd_sesion"
    # Llave que manda el gateway (API Management). Si está definida, el backend rechaza
    # toda llamada directa que no la traiga (salvo /api/v1/health). En Azure viene de Key Vault.
    GATEWAY_KEY: str = ""
    MAX_INTENTOS_LOGIN: int = 5
    BLOQUEO_LOGIN_MINUTOS: int = 15
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

    # Capturado a mano en Render -> Environment (sync:false en render.yaml) con el
    # dominio COMPLETO del portal, ej: gd-portal-qv63.onrender.com (sin https://).
    FRONTEND_HOST: str = ""

    @property
    def cors_list(self) -> list[str]:
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        host = self.FRONTEND_HOST.strip()
        if host:
            if "." not in host:
                # Host incompleto (p.ej. un fromService/property:host de Render, que
                # entrega el nombre interno sin ".onrender.com") -- CORS no funcionaria,
                # mejor avisar fuerte en el log que fallar en silencio en el navegador.
                log.warning(
                    "FRONTEND_HOST=%r no parece un dominio completo; CORS del portal "
                    "puede fallar. Revisa Render -> gd-rag-api -> Environment.", host,
                )
            origins.append(f"https://{host}")
        return origins


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.JWT_SECRET:
        if s.ENV_NAME == "local":
            import secrets
            s.JWT_SECRET = secrets.token_urlsafe(48)
            log.warning("JWT_SECRET vacío en ambiente local: se generó uno temporal "
                        "(las sesiones se pierden al reiniciar).")
        else:
            raise RuntimeError("JWT_SECRET es obligatorio fuera del ambiente local "
                               "(en Azure se lee de Key Vault).")
    return s
