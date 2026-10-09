"""Almacén de usuarios del portal.

Ninguna contraseña vive en el código: aquí solo hay el mecanismo para guardarlas
cifradas (hash scrypt con sal) y dos lugares donde guardarlas, elegidos por la
variable de entorno AUTH_BACKEND:

  archivo  -> un JSON local (AUTH_ARCHIVO_PATH). Solo para desarrollo en la compu;
              el archivo está fuera de git (ver .gitignore).
  cosmos   -> la base «seguridad», contenedor «usuarios», en Azure Cosmos DB.
              Se entra con identidad administrada (sin llaves) o, si se define
              COSMOS_KEY (que llega desde Key Vault), con esa llave.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import string
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

_N, _R, _P = 2**14, 8, 1
_ALFABETO = string.ascii_letters + string.digits + "!#$%*+-=?@_"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(sal).decode(), base64.b64encode(h).decode())


def verificar_password(password: str, guardado: str) -> bool:
    try:
        esquema, n, r, p, sal_b64, h_b64 = guardado.split("$")
        if esquema != "scrypt":
            return False
        sal, esperado = base64.b64decode(sal_b64), base64.b64decode(h_b64)
        h = hashlib.scrypt(password.encode("utf-8"), salt=sal, n=int(n), r=int(r),
                           p=int(p), dklen=len(esperado))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(h, esperado)


def generar_password_temporal(largo: int = 16) -> str:
    """Contraseña aleatoria con minúscula, mayúscula, número y símbolo."""
    while True:
        pw = "".join(secrets.choice(_ALFABETO) for _ in range(largo))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!#$%*+-=?@_" for c in pw)):
            return pw


def validar_password_nueva(pw: str) -> str | None:
    """Devuelve el motivo si no cumple, o None si es válida."""
    if len(pw) < 12:
        return "La contraseña debe tener al menos 12 caracteres."
    if not (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
            and any(c.isdigit() for c in pw)):
        return "Debe llevar mayúscula, minúscula y número."
    return None


def normalizar(username: str) -> str:
    return (username or "").strip().lower()


class AlmacenUsuarios(Protocol):
    def obtener(self, username: str) -> dict | None: ...
    def guardar(self, usuario: dict) -> None: ...
    def listar(self) -> list[dict]: ...


class AlmacenArchivo:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self._lock = threading.Lock()

    def _leer(self) -> dict:
        if not self.ruta.exists():
            return {}
        return json.loads(self.ruta.read_text(encoding="utf-8") or "{}")

    def obtener(self, username):
        with self._lock:
            return self._leer().get(normalizar(username))

    def guardar(self, usuario):
        with self._lock:
            datos = self._leer()
            datos[normalizar(usuario["username"])] = usuario
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
            self.ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

    def listar(self):
        with self._lock:
            return list(self._leer().values())


class AlmacenCosmos:
    def __init__(self, endpoint: str, base: str, contenedor: str, llave: str = ""):
        from azure.cosmos import CosmosClient
        if llave:
            credencial = llave
        else:
            from azure.identity import DefaultAzureCredential
            credencial = DefaultAzureCredential()
        self._cont = CosmosClient(endpoint, credential=credencial) \
            .get_database_client(base).get_container_client(contenedor)

    def obtener(self, username):
        u = normalizar(username)
        try:
            doc = self._cont.read_item(item=u, partition_key=u)
        except Exception:  # noqa: BLE001 - no existe
            return None
        return {k: v for k, v in doc.items() if not k.startswith("_")}

    def guardar(self, usuario):
        doc = dict(usuario)
        doc["id"] = normalizar(usuario["username"])
        self._cont.upsert_item(doc)

    def listar(self):
        docs = self._cont.query_items("SELECT * FROM c", enable_cross_partition_query=True)
        return [{k: v for k, v in d.items() if not k.startswith("_")} for d in docs]


@lru_cache
def get_almacen() -> AlmacenUsuarios:
    s = get_settings()
    if s.AUTH_BACKEND == "cosmos":
        if not s.COSMOS_ENDPOINT:
            raise RuntimeError("AUTH_BACKEND=cosmos requiere COSMOS_ENDPOINT")
        return AlmacenCosmos(s.COSMOS_ENDPOINT, s.COSMOS_DB_SEGURIDAD,
                             s.COSMOS_CONTENEDOR_USUARIOS, s.COSMOS_KEY)
    return AlmacenArchivo(Path(s.AUTH_ARCHIVO_PATH))


def crear_usuario(almacen: AlmacenUsuarios, username: str, nombre: str, gobierno: str,
                  rol: str, password: str | None = None) -> tuple[dict, str]:
    """Crea (o reemplaza) un usuario con contraseña temporal. Devuelve (registro, password)."""
    pw = password or generar_password_temporal()
    registro = {
        "username": normalizar(username), "nombre": nombre, "gobierno": gobierno, "rol": rol,
        "password_hash": hash_password(pw), "debe_cambiar_password": True, "activo": True,
        "creado_en": _ahora(), "password_cambiada_en": None,
    }
    almacen.guardar(registro)
    return registro, pw
