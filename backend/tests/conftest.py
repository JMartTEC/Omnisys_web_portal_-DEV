"""Configuración de pruebas: usuarios temporales en un archivo propio de la prueba.
Las contraseñas se generan al azar en cada corrida; no hay ninguna fija en el código."""
import os
import secrets
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="portal_tests_"))
os.environ.update({
    "ENV_NAME": "local",
    "AUTH_BACKEND": "archivo",
    "AUTH_ARCHIVO_PATH": str(_TMP / "usuarios.json"),
    "JWT_SECRET": secrets.token_urlsafe(48),
    "COOKIE_SEGURA": "false",
    "MAX_INTENTOS_LOGIN": "5",
})

import pytest  # noqa: E402

from app.core.usuarios import crear_usuario, get_almacen  # noqa: E402

PASSWORDS: dict[str, str] = {}
USUARIOS = [
    ("admin@prueba.mx", "Admin Prueba", "datos", "admin"),
    ("editor.integracion@prueba.mx", "Editor Integración", "integracion", "editor"),
    ("editor.apps@prueba.mx", "Editor Aplicaciones", "aplicaciones", "editor"),
]


@pytest.fixture(scope="session", autouse=True)
def usuarios_de_prueba():
    almacen = get_almacen()
    for username, nombre, gobierno, rol in USUARIOS:
        pw = secrets.token_urlsafe(18) + "aA1"
        reg, _ = crear_usuario(almacen, username, nombre, gobierno, rol, password=pw)
        reg["debe_cambiar_password"] = False  # para las pruebas de API normales
        almacen.guardar(reg)
        PASSWORDS[username] = pw
    yield
