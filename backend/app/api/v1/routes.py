"""Endpoints v1. Contrato consumido por frontend/assets/js/api.js."""
from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile,
                     status)

from app.api.deps import get_engine
from app.core.config import get_settings
from app.core.security import authenticate, create_token, get_current_user, require_gobierno
from app.schemas.models import (AgenteConfig, Documento, Gobierno, LoginRequest, LoginResponse,
                                QueryRequest, QueryResponse, Usuario)
from app.services.rag.engine import RagEngine
from app.services.rag.ingest import SOPORTADOS

router = APIRouter()


# ---------------------------------------------------------------- Salud
@router.get("/health", tags=["salud"])
def health(engine: RagEngine = Depends(get_engine)):
    s = get_settings()
    return {"status": "ok", "env": s.ENV_NAME, "vector_store": s.VECTOR_STORE, "llm": s.LLM_PROVIDER,
            "embeddings": s.EMBEDDINGS_PROVIDER, "fragmentos": engine.store.count()}


# ---------------------------------------------------------------- Auth
@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(body: LoginRequest):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    return LoginResponse(access_token=create_token(user), user=user)


@router.get("/auth/me", response_model=Usuario, tags=["auth"])
def me(user: Usuario = Depends(get_current_user)):
    return user


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
