"""Autenticación JWT con usuarios hardcodeados (fase MVP).

TODO (fase 2): reemplazar HARDCODED_USERS por el IdP institucional (NAM / eDirectory vía OIDC)
y validar el token emitido por el IdP en `get_current_user`.
"""
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.schemas.models import Usuario

# Mismos usuarios que frontend/assets/js/api.js (modo MOCK). SOLO para esta fase.
HARDCODED_USERS: dict[str, dict] = {
    "gd.admin": {"password": "GobDatos2026!", "nombre": "Administrador GD", "gobierno": "datos", "rol": "admin"},
    "gi.editor": {"password": "GobInteg2026!", "nombre": "Editor Integración", "gobierno": "integracion", "rol": "editor"},
    "ga.editor": {"password": "GobApps2026!", "nombre": "Editor Aplicaciones", "gobierno": "aplicaciones", "rol": "editor"},
}

_bearer = HTTPBearer(auto_error=False)


def authenticate(username: str, password: str) -> Usuario | None:
    u = HARDCODED_USERS.get(username)
    if not u or not hmac.compare_digest(u["password"], password):
        return None
    return Usuario(username=username, nombre=u["nombre"], gobierno=u["gobierno"], rol=u["rol"])


def create_token(user: Usuario) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.username, "nombre": user.nombre, "gobierno": user.gobierno, "rol": user.rol,
        "iat": now, "exp": now + timedelta(minutes=s.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Usuario:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    s = get_settings()
    try:
        p = jwt.decode(cred.credentials, s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado")
    return Usuario(username=p["sub"], nombre=p["nombre"], gobierno=p["gobierno"], rol=p["rol"])


def require_gobierno(user: Usuario, gobierno: str) -> None:
    """Solo admin o miembros del gobierno pueden escribir en su repositorio."""
    if user.rol != "admin" and user.gobierno != gobierno:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Sin permisos sobre el gobierno '{gobierno}'")
