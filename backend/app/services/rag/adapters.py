"""Adaptadores por defecto: funcionan sin servicios externos (ideal para Render free)
y adaptadores productivos listos para activarse por variables de entorno."""
import hashlib
import math
import re
import threading
import unicodedata

import httpx

from app.services.rag.base import LLM, Chunk, Embedder, Hit, VectorStore

_STOP = set("""de la el los las y o a en un una por para con del al que se su sus es son como lo le
este esta estos estas cual cuales qué cuál cómo donde dónde the and of to in""".split())


def normalizar(texto: str) -> list[str]:
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return [w for w in re.split(r"[^a-z0-9_]+", t) if len(w) > 2 and w not in _STOP]


# ---------------------------------------------------------------- Embeddings
class HashingEmbedder(Embedder):
    """Bag-of-words con hashing trick + prefijos (tolerante a plurales/variantes).
    Determinista y sin dependencias. Sustituir por OpenAIEmbedder en producción."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def _vec(self, texto: str) -> list[float]:
        v = [0.0] * self.dim
        for w in normalizar(texto):
            for tok, peso in ((w, 1.0), (w[:5], 0.6)):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                v[h % self.dim] += peso if (h >> 8) & 1 else -peso
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed(self, textos: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in textos]


class OpenAIEmbedder(Embedder):
    """Cualquier endpoint compatible con /v1/embeddings (OpenAI, Azure OpenAI, vLLM…)."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.url, self.key, self.model = base_url.rstrip("/"), api_key, model

    def embed(self, textos: list[str]) -> list[list[float]]:
        r = httpx.post(f"{self.url}/embeddings", headers={"Authorization": f"Bearer {self.key}"},
                       json={"model": self.model, "input": textos}, timeout=60)
        r.raise_for_status()
        return [d["embedding"] for d in r.json()["data"]]


# ---------------------------------------------------------------- Vector store
class MemoryVectorStore(VectorStore):
    """Índice en memoria con similitud coseno. Se pierde al reiniciar el servicio:
    en Render usar VECTOR_STORE=pgvector (PostgreSQL + extensión vector)."""

    def __init__(self):
        self._rows: list[tuple[Chunk, list[float]]] = []
        self._lock = threading.Lock()

    def add(self, chunks, vectores):
        with self._lock:
            self._rows.extend(zip(chunks, vectores))

    def search(self, vector, top_k, filtros):
        def ok(c: Chunk) -> bool:
            if filtros.get("gobierno") and c.gobierno != filtros["gobierno"]:
                return False
            if filtros.get("dominio") and c.dominio != filtros["dominio"]:
                return False
            if filtros.get("excluir_confidencial") and c.clasificacion.lower().startswith("confidencial"):
                return False
            return True

        with self._lock:
            hits = [Hit(c, sum(a * b for a, b in zip(vector, v))) for c, v in self._rows if ok(c)]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]

    def delete_documento(self, documento_id):
        with self._lock:
            antes = len(self._rows)
            self._rows = [r for r in self._rows if r[0].documento_id != documento_id]
            return antes - len(self._rows)

    def count(self, gobierno=None):
        return sum(1 for c, _ in self._rows if not gobierno or c.gobierno == gobierno)


class PgVectorStore(VectorStore):  # pragma: no cover - plantilla
    """Plantilla para PostgreSQL + pgvector (Render PostgreSQL soporta la extensión `vector`).

    DDL sugerido:
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE rag_chunk (
          id TEXT PRIMARY KEY, documento_id TEXT, gobierno TEXT, dominio TEXT,
          clasificacion TEXT, titulo TEXT, texto TEXT, metadata JSONB,
          embedding vector(768));
        CREATE INDEX ON rag_chunk USING hnsw (embedding vector_cosine_ops);
    Búsqueda: ORDER BY embedding <=> :vector LIMIT :k  (score = 1 - distancia)
    """

    def __init__(self, dsn: str):
        raise NotImplementedError("Implementar con psycopg + pgvector en la fase de integración")

    def add(self, chunks, vectores): ...
    def search(self, vector, top_k, filtros): ...
    def delete_documento(self, documento_id): ...
    def count(self, gobierno=None): ...


# ---------------------------------------------------------------- LLM
class ExtractiveLLM(LLM):
    """Sin modelo generativo: responde con los fragmentos más relevantes.
    Garantiza cero alucinación mientras se habilita el LLM institucional."""

    async def generar(self, pregunta, contexto):
        if not contexto:
            return "No encontré información certificada que responda tu pregunta."
        partes = [f"• {h.chunk.texto.strip()[:450]}" for h in contexto]
        return "Con base en la información certificada:\n\n" + "\n".join(partes)


class OpenAICompatibleLLM(LLM):
    SYSTEM = (
        "Eres el asistente de Gobierno de Datos de la VPAF del Tec de Monterrey. Responde en español, "
        "de forma concisa, usando EXCLUSIVAMENTE el contexto proporcionado. Si el contexto no contiene "
        "la respuesta, dilo explícitamente. Cita las fuentes entre corchetes [n]. Nunca muestres datos "
        "personales de individuos."
    )

    def __init__(self, base_url: str, api_key: str, model: str):
        self.url, self.key, self.model = base_url.rstrip("/"), api_key, model

    async def generar(self, pregunta, contexto):
        ctx = "\n\n".join(f"[{i + 1}] ({h.chunk.titulo}) {h.chunk.texto}" for i, h in enumerate(contexto))
        async with httpx.AsyncClient(timeout=60) as cli:
            r = await cli.post(
                f"{self.url}/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={"model": self.model, "temperature": 0.1, "messages": [
                    {"role": "system", "content": self.SYSTEM},
                    {"role": "user", "content": f"Contexto:\n{ctx}\n\nPregunta: {pregunta}"},
                ]},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
