"""GD 360 RAG API — arquetipo backend (FastAPI).

Local:   uvicorn app.main:app --reload --port 8000   → http://localhost:8000/docs
Render:  uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.v1.routes import router
from app.core.config import get_settings, leer_version
from app.services.rag.engine import RagEngine
# Gobierno de Aplicaciones: el Portal APM TEC es su propia app FastAPI y se monta
# en /gobierno_de_aplicaciones (backend en app/gobierno_de_aplicaciones/, pantallas
# en frontend/gobierno_de_aplicaciones/).
from app.core.proteccion import ProteccionAPM, SoloDesdeGateway
from app.gobierno_de_aplicaciones.main import app as apm_app

PREFIJO_APM = "/gobierno_de_aplicaciones"
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
# SERVIR_FRONTEND=1: un solo servidor sirve tambien el frontend de GD 360 en "/"
# (sin Static Site aparte). Por omision queda como en el blueprint: dos servicios.
SERVIR_FRONTEND = os.getenv("SERVIR_FRONTEND", "").strip().lower() in ("1", "true", "si", "sí")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = RagEngine(get_settings())
    engine.indexar_catalogo()
    app.state.engine = engine
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.APP_NAME, version=leer_version(), lifespan=lifespan,
                  description="API del portal de Gobierno de Datos VPAF: catálogo certificado, agentes RAG por gobierno e ingesta.")
    app.add_middleware(SoloDesdeGateway)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_list, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    app.include_router(router, prefix=s.API_PREFIX)

    # --- Gobierno de Aplicaciones (Portal APM TEC) ---
    @app.get(PREFIJO_APM, include_in_schema=False)
    def apm_sin_diagonal():
        return RedirectResponse(PREFIJO_APM + "/")

    # Todo el Portal APM exige sesión (excepto su pantalla de login y /assets).
    apm_app.add_middleware(ProteccionAPM)
    app.mount(PREFIJO_APM, apm_app, name="gobierno_de_aplicaciones")

    if SERVIR_FRONTEND and FRONTEND_DIR.is_dir():
        # Con un solo servidor la API vive en el mismo origen: env.js se arma aqui
        # (en el Static Site lo genera scripts/render-build.sh).
        @app.get("/assets/js/env.js", include_in_schema=False)
        def env_js():
            return Response(
                "window.__GD_ENV__ = { API_BASE_URL: window.location.origin, "
                f'USE_MOCK: false, ENV_NAME: "{s.ENV_NAME}" }};\n',
                media_type="application/javascript",
                headers={"Cache-Control": "no-cache"})

        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="gd360")
    else:
        @app.get("/", include_in_schema=False)
        def root():
            return {"app": s.APP_NAME, "docs": "/docs", "health": f"{s.API_PREFIX}/health",
                    "gobierno_de_aplicaciones": PREFIJO_APM + "/"}

    return app


app = create_app()
