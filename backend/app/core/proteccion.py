"""Protege el Portal APM TEC (montado en /gobierno_de_aplicaciones).

Todo lo que cuelga de esa ruta exige sesión salvo la pantalla de login, los
archivos estáticos (/assets) y el favicon. Sin sesión: las páginas redirigen al
login y las llamadas a /api responden 401. Con contraseña temporal sin cambiar
solo se deja usar el login (donde se cambia).
"""
import os
from urllib.parse import quote

from starlette.responses import JSONResponse, RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

PREFIJO = "/gobierno_de_aplicaciones"


def _login_unico() -> bool:
    return os.getenv("SERVIR_FRONTEND", "").strip().lower() in ("1", "true", "si", "sí")


LIBRES = ("/login", "/assets/", "/favicon.ico")


class ProteccionAPM:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        ruta = scope.get("path", "")
        # Montado en PREFIJO, Starlette deja en `path` la ruta completa y en
        # `root_path` el prefijo; se normaliza para comparar siempre sin prefijo.
        interna = ruta[len(PREFIJO):] if ruta.startswith(PREFIJO) else ruta
        # Un solo login: si este servidor también sirve el Portal GD 360, esa es la
        # única pantalla de entrada; el login propio del APM solo redirige hacia allá.
        if _login_unico() and interna.rstrip("/") == "/login" and scope.get("method") == "GET":
            qs = scope.get("query_string", b"").decode()
            nxt = ""
            for par in qs.split("&"):
                if par.startswith("next="):
                    nxt = par[5:]
            destino = "/index.html" + (f"?next={quote(PREFIJO, safe='/')}{nxt}" if nxt else "")
            return await RedirectResponse(destino, status_code=302)(scope, receive, send)
        if any(interna == l.rstrip("/") or interna.startswith(l) for l in LIBRES):
            return await self.app(scope, receive, send)

        from app.core.security import decodificar
        s = get_settings()
        cabeceras = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        token = None
        auth = cabeceras.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        else:
            for par in cabeceras.get("cookie", "").split(";"):
                nombre, _, valor = par.strip().partition("=")
                if nombre == s.SESION_COOKIE:
                    token = valor
        usuario = None
        if token:
            try:
                usuario = decodificar(token)
            except Exception:  # noqa: BLE001 - token inválido o vencido
                usuario = None

        if usuario is not None and not usuario.debe_cambiar_password:
            scope["usuario"] = usuario
            return await self.app(scope, receive, send)

        es_api = interna.startswith("/api/")
        if es_api:
            detalle = ("Debes cambiar tu contraseña temporal." if usuario else "No autenticado")
            respuesta = JSONResponse({"detail": detalle}, status_code=401)
        else:
            if _login_unico():
                destino = "/index.html?next=" + quote(PREFIJO + (interna or "/"), safe="/")
            else:
                destino = f"{PREFIJO}/login?next={quote(interna or '/', safe='/')}"
                if usuario is not None:
                    destino += "&cambiar=1"
            respuesta = RedirectResponse(destino, status_code=302)
        return await respuesta(scope, receive, send)


class SoloDesdeGateway:
    """Si GATEWAY_KEY está definida, solo deja pasar llamadas que traigan la cabecera
    X-Gateway-Key correcta: así el backend no se puede usar saltándose el gateway."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        llave = get_settings().GATEWAY_KEY
        if scope["type"] != "http" or not llave or scope.get("path", "") == "/api/v1/health":
            return await self.app(scope, receive, send)
        import hmac
        recibida = ""
        for k, v in scope.get("headers", []):
            if k.decode().lower() == "x-gateway-key":
                recibida = v.decode()
        if hmac.compare_digest(recibida.encode(), llave.encode()):
            return await self.app(scope, receive, send)
        respuesta = JSONResponse({"detail": "Acceso directo no permitido: usa el gateway."}, status_code=403)
        return await respuesta(scope, receive, send)
