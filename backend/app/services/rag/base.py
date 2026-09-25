"""Puertos (interfaces) del motor RAG.

Arquitectura hexagonal: el API solo conoce estas abstracciones. Cambiar de proveedor
(OpenAI, Azure OpenAI, Vertex, Bedrock) o de base vectorial (pgvector, Chroma, Qdrant,
Azure AI Search) es agregar un adaptador y cambiar una variable de entorno.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Chunk:
    id: str
    texto: str
    titulo: str
    gobierno: str
    dominio: str
    clasificacion: str = "Interna"
    documento_id: str | None = None
    documento: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Hit:
    chunk: Chunk
    score: float


class Embedder(ABC):
    @abstractmethod
    def embed(self, textos: list[str]) -> list[list[float]]: ...


class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[Chunk], vectores: list[list[float]]) -> None: ...

    @abstractmethod
    def search(self, vector: list[float], top_k: int, filtros: dict) -> list[Hit]: ...

    @abstractmethod
    def delete_documento(self, documento_id: str) -> int: ...

    @abstractmethod
    def count(self, gobierno: str | None = None) -> int: ...


class LLM(ABC):
    @abstractmethod
    async def generar(self, pregunta: str, contexto: list[Hit]) -> str: ...
