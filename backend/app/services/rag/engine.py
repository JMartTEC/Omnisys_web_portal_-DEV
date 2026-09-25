"""Orquestador RAG: catálogo, registro de agentes por gobierno, ingesta y consulta."""
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx

from app.core.config import Settings
from app.schemas.models import (AgenteConfig, Documento, Fuente, Gobierno, QueryRequest,
                                QueryResponse, Usuario)
from app.services.rag.adapters import (ExtractiveLLM, HashingEmbedder, MemoryVectorStore,
                                       OpenAICompatibleLLM, OpenAIEmbedder, PgVectorStore)
from app.services.rag.base import Chunk
from app.services.rag.ingest import extraer_texto, fragmentar

log = logging.getLogger("gd.rag")


class RagEngine:
    def __init__(self, s: Settings):
        self.s = s
        self.embedder = (OpenAIEmbedder(s.LLM_BASE_URL, s.LLM_API_KEY, s.EMBEDDINGS_MODEL)
                         if s.EMBEDDINGS_PROVIDER == "openai" else HashingEmbedder(s.EMBEDDINGS_DIM))
        self.store = PgVectorStore(s.DATABASE_URL) if s.VECTOR_STORE == "pgvector" else MemoryVectorStore()
        self.llm = (OpenAICompatibleLLM(s.LLM_BASE_URL, s.LLM_API_KEY, s.LLM_MODEL)
                    if s.LLM_PROVIDER == "openai" else ExtractiveLLM())
        data = json.loads(s.CATALOGO_PATH.read_text(encoding="utf-8"))
        self.gobiernos: dict[str, Gobierno] = {g["id"]: Gobierno(**g) for g in data["gobiernos"]}
        # Conocimiento semilla: se vectoriza para el agente, no se expone como ficha
        self.conocimiento: list[dict] = data["conocimiento"]
        self.documentos: dict[str, Documento] = {}

    # ------------------------------------------------------------ Catálogo
    def indexar_catalogo(self) -> int:
        """Vectoriza el catálogo certificado para que el agente pueda citarlo."""
        chunks: list[Chunk] = []
        for a in self.conocimiento:
            base = dict(gobierno=a["gobierno"], dominio=a["id"], clasificacion="Interna", documento=a["nombre"])
            chunks.append(Chunk(id=f"{a['id']}-desc", titulo=f"{a['nombre']} — descripción",
                                texto=a["descripcion"].replace("**", "") + " " + a["resumen"], **base))
            for i, e in enumerate(a["entidades"]):
                chunks.append(Chunk(id=f"{a['id']}-ent-{i}", titulo=f"{a['nombre']} · {e['nombre']}",
                                    texto=f"Entidad {e['nombre']} ({e['tipo']}): {e['descripcion']}", **base))
            for i, d in enumerate(a["diccionario"]):
                chunks.append(Chunk(id=f"{a['id']}-dic-{i}", titulo=f"{a['nombre']} · Diccionario",
                                    texto=f"{d['entidad']}.{d['atributo']} {d['tipo']}({d['longitud']}) {d['llave']}: "
                                          f"{d['descripcion']} Fuente: {d['fuente']}.", **base))
            for i, g in enumerate(a["glosario"]):
                chunks.append(Chunk(id=f"{a['id']}-glo-{i}", titulo=f"{a['nombre']} · Glosario",
                                    texto=f"{g['termino']}: {g['definicion']}", **base))
            for i, h in enumerate(a["habilitadores"]):
                chunks.append(Chunk(id=f"{a['id']}-hab-{i}", titulo=f"{a['nombre']} · Habilitadores",
                                    texto=f"{h['nombre']} ({h['crud']}): {h['descripcion']}", **base))
        self.store.add(chunks, self.embedder.embed([f"{c.titulo}. {c.texto}" for c in chunks]))
        log.info("Catálogo indexado: %s fragmentos", len(chunks))
        return len(chunks)

    def con_estadisticas(self, g: Gobierno) -> Gobierno:
        docs = [d for d in self.documentos.values() if d.gobierno == g.id]
        g.estadisticas = {
            "documentos": len(docs),
            "indexados": sum(1 for d in docs if d.estado == "indexado"),
            "fragmentos": self.store.count(g.id),
        }
        return g

    # ------------------------------------------------------------ Agentes
    def configurar_agente(self, gobierno: str, cfg: AgenteConfig) -> Gobierno:
        g = self.gobiernos[gobierno]
        g.modo, g.url = cfg.modo, (cfg.url.rstrip("/") if cfg.url else None)
        return g

    async def consultar(self, req: QueryRequest, user: Usuario) -> QueryResponse:
        t0 = time.perf_counter()
        g = self.gobiernos.get(req.gobierno)
        if g is None:
            raise KeyError(req.gobierno)
        if g.modo == "remoto" and g.url:
            resp = await self._consultar_remoto(g, req, user)
        else:
            resp = await self._consultar_local(req, user)
        resp.latencia_ms = int((time.perf_counter() - t0) * 1000)
        return resp

    async def _consultar_local(self, req: QueryRequest, user: Usuario) -> QueryResponse:
        filtros = {
            "gobierno": req.gobierno,
            "dominio": req.dominio,
            # Confidencial solo para el gobierno propietario o admin (ITIGID09)
            "excluir_confidencial": user.rol != "admin" and user.gobierno != req.gobierno,
        }
        vec = self.embedder.embed([req.pregunta])[0]
        hits = [h for h in self.store.search(vec, req.top_k, filtros) if h.score >= self.s.MIN_SCORE]
        respuesta = await self.llm.generar(req.pregunta, hits)
        return QueryResponse(
            respuesta=respuesta, agente=req.gobierno, modo=f"local/{self.s.LLM_PROVIDER}",
            fuentes=[Fuente(titulo=h.chunk.titulo, dominio=h.chunk.dominio, fragmento=h.chunk.texto[:500],
                            score=round(h.score, 2), documento=h.chunk.documento) for h in hits],
        )

    async def _consultar_remoto(self, g: Gobierno, req: QueryRequest, user: Usuario) -> QueryResponse:
        """Delegación al agente propio de otro gobierno (mismo contrato)."""
        async with httpx.AsyncClient(timeout=self.s.REMOTE_AGENT_TIMEOUT) as cli:
            r = await cli.post(f"{g.url}/api/v1/rag/query", json=req.model_dump(),
                               headers={"X-GD-User": user.username, "X-GD-Gobierno": user.gobierno})
            r.raise_for_status()
            data = r.json()
        data.setdefault("agente", g.id)
        data["modo"] = "remoto"
        return QueryResponse(**data)

    # ------------------------------------------------------------ Ingesta
    def registrar_documento(self, nombre: str, gobierno: str, dominio: str, clasificacion: str,
                            tamano: int, user: Usuario) -> Documento:
        doc = Documento(id=f"doc-{uuid.uuid4().hex[:10]}", nombre=nombre, gobierno=gobierno, dominio=dominio,
                        clasificacion=clasificacion, tamano_kb=max(1, tamano // 1024),
                        cargado_por=user.username, fecha=datetime.now(timezone.utc))
        self.documentos[doc.id] = doc
        return doc

    def procesar_documento(self, doc_id: str, contenido: bytes) -> None:
        """Pipeline: extracción → fragmentación → embeddings → índice. Corre en background."""
        doc = self.documentos[doc_id]
        try:
            texto = extraer_texto(doc.nombre, contenido)
            partes = fragmentar(texto, self.s.CHUNK_SIZE, self.s.CHUNK_OVERLAP)
            if not partes:
                raise ValueError("El documento no contiene texto extraíble")
            chunks = [Chunk(id=f"{doc.id}-{i}", texto=p, titulo=f"{doc.nombre} · parte {i + 1}",
                            gobierno=doc.gobierno, dominio=doc.dominio, clasificacion=doc.clasificacion,
                            documento_id=doc.id, documento=doc.nombre) for i, p in enumerate(partes)]
            for i in range(0, len(chunks), 64):  # lotes para proveedores con límite
                lote = chunks[i:i + 64]
                self.store.add(lote, self.embedder.embed([c.texto for c in lote]))
            doc.fragmentos, doc.estado = len(chunks), "indexado"
        except Exception as e:  # noqa: BLE001
            log.exception("Error procesando %s", doc.nombre)
            doc.estado, doc.error = "error", str(e)

    def eliminar_documento(self, doc_id: str) -> None:
        self.store.delete_documento(doc_id)
        self.documentos.pop(doc_id, None)
