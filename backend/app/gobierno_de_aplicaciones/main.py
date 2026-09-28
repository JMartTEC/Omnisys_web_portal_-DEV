"""Punto de entrada del Portal APM TEC.

Arma la aplicacion FastAPI: carga el .env, publica los archivos del frontend
en /assets y registra las rutas de api/v1. Toda la logica vive en services/;
las rutas y pantallas, en api/v1/routes.py.

Se monta en /gobierno_de_aplicaciones desde backend/app/main.py (Portal GD 360).
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from .api.v1.routes import FRONTEND_DIR, router  # noqa: E402

app = FastAPI(
    title="TEC | Clasificador de Activos IA-Ready v2",
    docs_url="/api/docs",  # "/docs" es la pantalla de referencia APM y TDD
)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.include_router(router)
