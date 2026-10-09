"""Endpoints v1. Contrato consumido por frontend/assets/js/api.js."""
from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response,
                     UploadFile, status)

from app.api.deps import get_engine
from app.core.config import get_settings, leer_version
from app.core.security import (authenticate, create_token, get_current_user, require_admin,
                               require_gobierno, usuario_actual_sin_restricciones)
from app.core.usuarios import (crear_usuario, get_almacen, hash_password, normalizar,
                               validar_password_nueva, verificar_password)
from app.schemas.models import (AgenteConfig, CambiarPasswordRequest, Documento, Gobierno,
                                LoginRequest, LoginResponse, NuevoUsuarioRequest, QueryRequest,
                                QueryResponse, Usuario, UsuarioCreado)
from app.services.rag.engine import RagEngine
from app.services.rag.ingest import SOPORTADOS

router = APIRouter()


# ---------------------------------------------------------------- Salud
@router.get("/health", tags=["salud"])
def health(engine: RagEngine = Depends(get_engine)):
    s = get_settings()
    return {"status": "ok", "version": leer_version(), "env": s.ENV_NAME, "vector_store": s.VECTOR_STORE, "llm": s.LLM_PROVIDER,
            "embeddings": s.EMBEDDINGS_PROVIDER, "fragmentos": engine.store.count()}


@router.get("/version", tags=["salud"])
def version():
    """Qué versión del portal corre en este ambiente."""
    return {"version": leer_version(), "env": get_settings().ENV_NAME}


# ---------------------------------------------------------------- Auth
def _poner_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(s.SESION_COOKIE, token, max_age=s.JWT_EXPIRE_MINUTES * 60, httponly=True,
                        secure=s.COOKIE_SEGURA, samesite="lax", path="/")


@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(body: LoginRequest, response: Response):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    token = create_token(user)
    _poner_cookie(response, token)
    return LoginResponse(access_token=token, user=user)


@router.post("/auth/logout", tags=["auth"])
def logout(response: Response):
    response.delete_cookie(get_settings().SESION_COOKIE, path="/")
    return {"ok": True}


@router.get("/auth/me", response_model=Usuario, tags=["auth"])
def me(user: Usuario = Depends(usuario_actual_sin_restricciones)):
    return user


@router.post("/auth/cambiar-password", response_model=LoginResponse, tags=["auth"])
def cambiar_password(body: CambiarPasswordRequest, response: Response,
                     user: Usuario = Depends(usuario_actual_sin_restricciones)):
    almacen = get_almacen()
    reg = almacen.obtener(user.username)
    if not reg or not verificar_password(body.password_actual, reg["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La contraseña actual no es correcta.")
    motivo = validar_password_nueva(body.password_nueva)
    if motivo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, motivo)
    if body.password_nueva == body.password_actual:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La contraseña nueva debe ser distinta.")
    from app.core.usuarios import _ahora
    reg.update(password_hash=hash_password(body.password_nueva), debe_cambiar_password=False,
               password_cambiada_en=_ahora())
    almacen.guardar(reg)
    nuevo = Usuario(username=reg["username"], nombre=reg["nombre"], gobierno=reg["gobierno"],
                    rol=reg["rol"], debe_cambiar_password=False)
    token = create_token(nuevo)
    _poner_cookie(response, token)
    return LoginResponse(access_token=token, user=nuevo)


# ---------------------------------------------------------------- Administración de usuarios
@router.get("/usuarios", response_model=list[Usuario], tags=["usuarios"])
def listar_usuarios(_: Usuario = Depends(require_admin)):
    return [Usuario(username=u["username"], nombre=u["nombre"], gobierno=u["gobierno"], rol=u["rol"],
                    debe_cambiar_password=bool(u.get("debe_cambiar_password")))
            for u in sorted(get_almacen().listar(), key=lambda x: x["username"])]


@router.post("/usuarios", response_model=UsuarioCreado, status_code=201, tags=["usuarios"])
def alta_usuario(body: NuevoUsuarioRequest, _: Usuario = Depends(require_admin)):
    almacen = get_almacen()
    if almacen.obtener(body.username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese usuario ya existe.")
    reg, pw = crear_usuario(almacen, body.username, body.nombre, body.gobierno, body.rol)
    return UsuarioCreado(usuario=Usuario(username=reg["username"], nombre=reg["nombre"],
                                         gobierno=reg["gobierno"], rol=reg["rol"],
                                         debe_cambiar_password=True), password_temporal=pw)


@router.post("/usuarios/{username}/restablecer-password", response_model=UsuarioCreado, tags=["usuarios"])
def restablecer_password(username: str, _: Usuario = Depends(require_admin)):
    almacen = get_almacen()
    previo = almacen.obtener(username)
    if not previo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    reg, pw = crear_usuario(almacen, normalizar(username), previo["nombre"], previo["gobierno"], previo["rol"])
    return UsuarioCreado(usuario=Usuario(username=reg["username"], nombre=reg["nombre"],
                                         gobierno=reg["gobierno"], rol=reg["rol"],
                                         debe_cambiar_password=True), password_temporal=pw)


# ---------------------------------------------------------------- Gobiernos / agentes
@router.get("/gobiernos", response_model=list[Gobierno], tags=["gobiernos"])
def gobiernos(engine: RagEngine = Depends(get_engine), _: Usuario = Depends(get_current_user)):
    return [engine.con_estadisticas(g) for g in engine.gobiernos.values()]


@router.get("/gobiernos/{gobierno}", response_model=Gobierno, tags=["gobiernos"])
def gobierno(gobierno: str, engine: RagEngine = Depends(get_engine), _: Usuario = Depends(get_current_user)):
    g = engine.gobiernos.get(gobierno)
    if not g:
        raise HTTPException(404, "Gobierno no encontrado")
    return engine.con_estadisticas(g)


@router.put("/gobiernos/{gobierno}/agente", response_model=Gobierno, tags=["gobiernos"])
def configurar_agente(gobierno: str, cfg: AgenteConfig, engine: RagEngine = Depends(get_engine),
                      user: Usuario = Depends(get_current_user)):
    if gobierno not in engine.gobiernos:
        raise HTTPException(404, "Gobierno no encontrado")
    require_gobierno(user, gobierno)
    if cfg.modo == "remoto" and not (cfg.url or "").startswith(("http://", "https://")):
        raise HTTPException(422, "URL del agente remoto inválida")
    return engine.configurar_agente(gobierno, cfg)


# ---------------------------------------------------------------- RAG
@router.post("/rag/query", response_model=QueryResponse, tags=["rag"])
async def query(req: QueryRequest, engine: RagEngine = Depends(get_engine), user: Usuario = Depends(get_current_user)):
    try:
        return await engine.consultar(req, user)
    except KeyError:
        raise HTTPException(404, f"Gobierno '{req.gobierno}' no registrado")
    except Exception as e:  # noqa: BLE001 - agente remoto o LLM caído
        raise HTTPException(502, f"El agente no respondió: {e}")


# ---------------------------------------------------------------- Ingesta
@router.get("/ingesta/documentos", response_model=list[Documento], tags=["ingesta"])
def documentos(gobierno: str | None = None, engine: RagEngine = Depends(get_engine),
               _: Usuario = Depends(get_current_user)):
    docs = [d for d in engine.documentos.values() if not gobierno or d.gobierno == gobierno]
    return sorted(docs, key=lambda d: d.fecha, reverse=True)


@router.post("/ingesta/documentos", response_model=Documento, status_code=202, tags=["ingesta"])
async def subir(background: BackgroundTasks, archivo: UploadFile = File(...), gobierno: str = Form(...),
                dominio: str = Form(...), clasificacion: str = Form("Interna"),
                engine: RagEngine = Depends(get_engine), user: Usuario = Depends(get_current_user)):
    s = get_settings()
    if gobierno not in engine.gobiernos:
        raise HTTPException(404, "Gobierno no encontrado")
    require_gobierno(user, gobierno)
    ext = (archivo.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in SOPORTADOS:
        raise HTTPException(415, f"Formato no soportado. Usa: {', '.join(sorted(SOPORTADOS))}")
    contenido = await archivo.read()
    if len(contenido) > s.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera {s.MAX_UPLOAD_MB} MB")
    doc = engine.registrar_documento(archivo.filename, gobierno, dominio, clasificacion, len(contenido), user)
    background.add_task(engine.procesar_documento, doc.id, contenido)
    return doc


@router.delete("/ingesta/documentos/{doc_id}", tags=["ingesta"])
def eliminar(doc_id: str, engine: RagEngine = Depends(get_engine), user: Usuario = Depends(get_current_user)):
    doc = engine.documentos.get(doc_id)
    if not doc:
        raise HTTPException(404, "Documento no encontrado")
    require_gobierno(user, doc.gobierno)
    engine.eliminar_documento(doc_id)
    return {"ok": True}
