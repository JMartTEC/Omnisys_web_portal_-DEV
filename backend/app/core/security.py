"""Autenticación JWT con usuarios guardados cifrados (ver core/usuarios.py).

No hay usuarios ni contraseñas en el código. La sesión viaja de dos formas, que
valen igual: cabecera «Authorization: Bearer» (portal GD 360) o cookie HttpOnly
(Portal APM TEC, cuyas pantallas son páginas completas).
TODO (fase 2): validar tokens de Microsoft Entra ID en `get_current_user`.
"""
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.usuarios import get_almacen, verificar_password
from app.schemas.models import Usuario

_bearer = HTTPBearer(auto_error=False)
_fallos: dict[str, list[float]] = {}
_lock = threading.Lock()


def _bloqueado(username: str) -> bool:
    s = get_settings()
    ventana = time.time() - s.BLOQUEO_LOGIN_MINUTOS * 60
    with _lock:
        intentos = [t for t in _fallos.get(username, []) if t > ventana]
        _fallos[username] = intentos
        return len(intentos) >= s.MAX_INTENTOS_LOGIN


def _registrar_fallo(username: str) -> None:
    with _lock:
        _fallos.setdefault(username, []).append(time.time())


def authenticate(username: str, password: str) -> Usuario | None:
    u = (username or "").strip().lower()
    if _bloqueado(u):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            "Demasiados intentos. Espera unos minutos e inténtalo de nuevo.")
    reg = get_almacen().obtener(u)
    # Se verifica siempre contra algún hash para no revelar si el usuario existe por tiempo.
    hash_guardado = (reg or {}).get("password_hash") or "scrypt$16384$8$1$AAAAAAAAAAAAAAAAAAAAAA==$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    ok = verificar_password(password or "", hash_guardado)
    if not reg or not reg.get("activo", True) or not ok:
        _registrar_fallo(u)
        return None
    with _lock:
        _fallos.pop(u, None)
    return _a_usuario(reg)


def _a_usuario(reg: dict) -> Usuario:
    return Usuario(username=reg["username"], nombre=reg["nombre"], gobierno=reg["gobierno"],
                   rol=reg["rol"], debe_cambiar_password=bool(reg.get("debe_cambiar_password")))


def create_token(user: Usuario) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username, "nombre": user.nombre, "gobierno": user.gobierno, "rol": user.rol,
        "dcp": user.debe_cambiar_password,
        "iat": now, "exp": now + timedelta(minutes=s.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def decodificar(token: str) -> Usuario:
    s = get_settings()
    try:
        p = jwt.decode(token, s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM])
        return Usuario(username=p["sub"], nombre=p["nombre"], gobierno=p["gobierno"],
                       rol=p["rol"], debe_cambiar_password=bool(p.get("dcp")))
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")


def token_de_request(request: Request, cred: HTTPAuthorizationCredentials | None) -> str | None:
    if cred is not None:
        return cred.credentials
    return request.cookies.get(get_settings().SESION_COOKIE)


def usuario_actual_sin_restricciones(request: Request,
                                     cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Usuario:
    """Usuario autenticado aunque todavía deba cambiar su contraseña temporal."""
    token = token_de_request(request, cred)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    return decodificar(token)


def get_current_user(user: Usuario = Depends(usuario_actual_sin_restricciones)) -> Usuario:
    if user.debe_cambiar_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Debes cambiar tu contraseña temporal antes de continuar.")
    return user


def require_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    if user.rol != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador puede hacer esto.")
    return user


def require_gobierno(user: Usuario, gobierno: str) -> None:
    """Solo admin o miembros del gobierno pueden escribir en su repositorio."""
    if user.rol != "admin" and user.gobierno != gobierno:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Sin permisos sobre el gobierno '{gobierno}'")
