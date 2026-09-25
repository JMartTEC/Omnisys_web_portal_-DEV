"""GD 360 RAG API — arquetipo backend (FastAPI).

Local:   uvicorn app.main:app --reload --port 8000   → http://localhost:8000/docs
Render:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router
from app.core.config import get_settings
from app.services.rag.engine import RagEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = RagEngine(get_settings())
    engine.indexar_catalogo()
    app.state.engine = engine
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.APP_NAME, version="0.1.0", lifespan=lifespan,
                  description="API del portal de Gobierno de Datos VPAF: catálogo certificado, agentes RAG por gobierno e ingesta.")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix=s.API_PREFIX)

    @app.get("/", include_in_schema=False)
    def root():
        return {"app": s.APP_NAME, "docs": "/docs", "health": f"{s.API_PREFIX}/health"}

    return app


app = create_app()
