"""Contratos de la API. Son el acuerdo con el frontend y con los agentes remotos
de Gobierno de Integración y Gobierno de Aplicaciones."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Usuario(BaseModel):
    username: str
    nombre: str
    gobierno: str
    rol: Literal["admin", "editor", "lector"]
    debe_cambiar_password: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class CambiarPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


class NuevoUsuarioRequest(BaseModel):
    username: str
    nombre: str
    gobierno: str = "aplicaciones"
    rol: Literal["admin", "editor", "lector"] = "editor"


class UsuarioCreado(BaseModel):
    usuario: Usuario
    password_temporal: str  # se muestra una sola vez


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Usuario


class Pilar(BaseModel):
    icono: str
    titulo: str
    texto: str


class Tema(BaseModel):
    """Tema de la sección (en Gobierno de Datos: los dominios). Solo introducción, sin ficha técnica."""
    id: str
    nombre: str
    icono: str = "bi-bookmark"
    estado: str = "vigente"
    descripcion: str = ""


class Gobierno(BaseModel):
    """Sección del portal + configuración de su agente RAG."""
    id: str
    nombre: str
    descripcion: str = ""
    responsable: str = ""
    icono: str = "bi-robot"
    tema: int = 1
    modo: Literal["local", "remoto"] = "local"
    url: str | None = None
    lema: str = ""
    introduccion: str = ""
    pilares: list[Pilar] = []
    titulo_temas: str = "Temas"
    intro_temas: str = ""
    temas: list[Tema] = []
    preguntas: list[str] = []
    estadisticas: dict[str, int] = {}


class AgenteConfig(BaseModel):
    modo: Literal["local", "remoto"]
    url: str | None = None


# ---------------------------------------------------------------- RAG
class QueryRequest(BaseModel):
    pregunta: str = Field(min_length=2, max_length=2000)
    gobierno: str = "datos"
    dominio: str | None = None
    top_k: int = Field(default=4, ge=1, le=20)


class Fuente(BaseModel):
    titulo: str
    dominio: str
    fragmento: str
    score: float
    documento: str | None = None


class QueryResponse(BaseModel):
    respuesta: str
    fuentes: list[Fuente] = []
    agente: str
    modo: str
    latencia_ms: int | None = None


# ---------------------------------------------------------------- Ingesta
class Documento(BaseModel):
    id: str
    nombre: str
    gobierno: str
    dominio: str
    clasificacion: str
    estado: Literal["procesando", "indexado", "error"] = "procesando"
    fragmentos: int = 0
    tamano_kb: int = 0
    cargado_por: str | None = None
    fecha: datetime
    error: str | None = None
