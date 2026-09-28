# Portal GD 360 — Gobierno de Datos VPAF

Portal con una sección por cada gobierno de la VPAF (**Datos**, **Integración** y **Aplicaciones**). Cada sección presenta qué es ese gobierno y el alcance de sus dominios o temas, e incluye **su propio agente RAG**. La información no se consulta en fichas: el usuario le pregunta al agente y este responde con información certificada, citando sus fuentes.

| Capa | Tecnología | Carpeta | Servicio en Render |
|---|---|---|---|
| Frontend | HTML5 + Bootstrap 5.3 + JS sin framework, responsivo | `frontend/` | Static Site `gd-portal` |
| Backend | Python 3.11 + FastAPI, con RAG intercambiable | `backend/` | Web Service `gd-rag-api` |
| Gobierno de Aplicaciones | Portal APM TEC (FastAPI + HTML), servido por el backend en `/gobierno_de_aplicaciones/` | `backend/app/gobierno_de_aplicaciones/` · `frontend/gobierno_de_aplicaciones/` | Dentro de `gd-rag-api` |
| Infra | Blueprint de Render | `render.yaml` | Crea y conecta los 2 servicios |

---

## 1. Estructura

```
gd-portal/
├── render.yaml                      Blueprint de Render (front + back)
├── frontend/
│   ├── index.html                   Login
│   ├── portal.html                  Inicio: buscador, presentación y acceso a las 3 secciones
│   ├── gobierno.html?id=datos       Sección (plantilla única para datos | integracion | aplicaciones):
│   │                                  introducción, pilares, introducción de dominios/temas y agente RAG
│   ├── carga.html                   Mi espacio: carga de documentos, estado de indexación, configuración del agente
│   ├── gobierno_de_aplicaciones/    Pantallas del Portal APM TEC (las sirve el backend)
│   │   ├── _layout.html             Barra, banner y pie comunes (mismo estilo que GD 360)
│   │   ├── pantallas/*.html         Pasos 1 a 7, Comparar APM, Comparar TDD Nivel 2, Progreso, Configuración
│   │   └── assets/                  css/comun.css, js/comun.js, js/pages/*.js, fuentes, img, manual (PDF), plantillas
│   ├── assets/css/theme.css         Tokens de diseño (look and feel Tec 360)
│   ├── assets/js/
│   │   ├── env.js                   Se genera en el build (API_BASE_URL, USE_MOCK)
│   │   ├── config.js                Configuración central
│   │   ├── api.js                   Cliente API: modo MOCK o backend real, con el mismo contrato
│   │   ├── auth.js                  Sesión JWT y guard de páginas
│   │   ├── layout.js                Navbar, asistente flotante y componente de chat
│   │   ├── mock-data.js             Se genera desde backend/app/data/catalogo.json
│   │   └── pages/*.js               Lógica de cada página
│   └── scripts/
│       ├── render-build.sh          Build del Static Site
│       └── sync-mock-data.sh        Sincroniza el catálogo al modo MOCK
└── backend/
    ├── app/main.py                  App FastAPI (CORS, lifespan, routers)
    ├── app/core/config.py           Variables de entorno
    ├── app/core/security.py         JWT + usuarios hardcodeados (fase MVP)
    ├── app/schemas/models.py        Contratos (Pydantic)
    ├── app/api/v1/routes.py         Endpoints
    ├── app/services/rag/
    │   ├── base.py                  Puertos: Embedder, VectorStore, LLM
    │   ├── adapters.py              Hashing/OpenAI embedder, Memory/PgVector store, Extractive/OpenAI LLM
    │   ├── ingest.py                Extracción (PDF, DOCX, XLSX, CSV, MD, TXT, JSON) y fragmentación
    │   └── engine.py                Orquestador: catálogo, agentes por gobierno, ingesta y consulta
    ├── app/data/catalogo.json       gobiernos: contenido de cada sección · conocimiento: semilla que se vectoriza
    ├── app/gobierno_de_aplicaciones/ Portal APM TEC (se monta en /gobierno_de_aplicaciones desde app/main.py)
    │   ├── main.py                  App FastAPI del portal APM
    │   ├── api/v1/routes.py         Pantallas y endpoints /api/... del portal APM
    │   ├── core/                    configuracion.py (motor de IA), sesion.py, progreso_vivo.py
    │   ├── schemas/models.py        Contratos (Pydantic)
    │   └── services/                apm, tdd, tdd_nivel2, llenado, conciliacion, almacen (SQLite)...
    │       ├── ia/                  claude_service.py, ollama_service.py
    │       └── parsers/             Word, PDF, PowerPoint, Excel, texto e imágenes
    ├── tests/test_api.py            10 pruebas de contrato
    ├── requirements.txt
    └── .env.example
```

## 2. Usuarios de prueba (hardcodeados)

Están definidos en `backend/app/core/security.py` y en `frontend/assets/js/api.js` (modo MOCK).

| Usuario | Contraseña | Gobierno | Rol |
|---|---|---|---|
| gd.admin | GobDatos2026! | Datos | admin (puede cargar en cualquier gobierno) |
| gi.editor | GobInteg2026! | Integración | editor |
| ga.editor | GobApps2026! | Aplicaciones | editor |

> En la fase 2 se reemplazan por el IdP institucional (NAM / eDirectory con OIDC). El frontend no cambia porque sigue recibiendo un Bearer token.

## 3. Ejecutar en local

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000        # Swagger: http://localhost:8000/docs
pytest -q                                         # 10 pruebas

# Frontend (en otra terminal)
cd frontend
python -m http.server 8080                        # http://localhost:8080  (modo MOCK por defecto)
# Para conectarlo al backend local:
API_BASE_URL=http://localhost:8000 sh scripts/render-build.sh
```

El modo MOCK permite revisar el look and feel sin backend. Si no hay `API_BASE_URL`, el portal cae en MOCK de forma automática y muestra la etiqueta **MODO DEMO** en la barra superior.

### Gobierno de Aplicaciones en local

Con el backend arriba, el Portal APM TEC queda en **http://localhost:8000/gobierno_de_aplicaciones/**. El botón «Entrar al portal del APM» de la tercera tarjeta (y el menú «Gobierno de Aplicaciones») lo abre en una pestaña nueva usando `API_BASE_URL`.

Para correr todo en **un solo servidor** (sin el `http.server` del frontend):

```bash
cd backend
SERVIR_FRONTEND=1 uvicorn app.main:app --port 8000   # GD 360 en /, APM en /gobierno_de_aplicaciones/
```

En ese modo el backend genera `assets/js/env.js` apuntando al mismo servidor (no hace falta el build del frontend).

## 4. Contrato de la API (`/api/v1`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado, proveedor de LLM/embeddings y número de fragmentos |
| POST | `/auth/login` | `{username, password}` → `{access_token, user}` |
| GET | `/auth/me` | Usuario del token |
| GET | `/gobiernos` | Las 3 secciones con sus estadísticas (documentos, fragmentos) |
| GET | `/gobiernos/{id}` | Contenido de la sección: introducción, pilares, dominios/temas, preguntas sugeridas |
| PUT | `/gobiernos/{id}/agente` | `{modo: local\|remoto, url}`: conecta el agente propio de un gobierno |
| POST | `/rag/query` | `{pregunta, gobierno, dominio?, top_k}` → `{respuesta, fuentes[], agente, modo, latencia_ms}` |
| GET | `/ingesta/documentos?gobierno=` | Documentos y su estado (procesando / indexado / error) |
| POST | `/ingesta/documentos` | multipart: `archivo, gobierno, dominio, clasificacion` → 202; se indexa en segundo plano |
| DELETE | `/ingesta/documentos/{id}` | Borra el documento y sus fragmentos del índice |

> Ya no hay endpoints de fichas de dominio. El detalle de los dominios (entidades, atributos, reglas) solo se obtiene al preguntarle al agente.

### Editar el contenido de las secciones

Los textos de cada sección están en `backend/app/data/catalogo.json → gobiernos[]`: `lema`, `introduccion`, `pilares`, `titulo_temas`, `intro_temas`, `temas` y `preguntas`. Después de editarlos, ejecuta `sh frontend/scripts/sync-mock-data.sh` para que el modo MOCK muestre lo mismo.

### Cómo se integran Gobierno de Integración y Gobierno de Aplicaciones

Cada equipo tiene dos opciones:

1. **Agente local.** Sube sus documentos desde *Mi espacio → Cargar conocimiento*. Quedan indexados en el repositorio del portal, en una partición separada por gobierno.
2. **Agente remoto.** Publica su propio servicio RAG con el mismo contrato `POST /api/v1/rag/query` y lo registra en *Mi espacio → Configurar agente*. El backend le delega la consulta y le envía los encabezados `X-GD-User` y `X-GD-Gobierno`.

Puedes clonar esta carpeta `backend/` como arquetipo del agente de cada equipo.

### Seguridad aplicada

- Solo un **admin**, o un miembro del mismo gobierno, puede cargar, borrar o configurar el agente de ese gobierno (403 en otro caso).
- Los fragmentos **Confidencial** o **Confidencial (PII)** solo se recuperan para el gobierno propietario o para un admin (ITIGID09).
- El prompt del LLM obliga a responder solo con el contexto y prohíbe mostrar datos personales de individuos.

### Gobierno de Aplicaciones (Portal APM TEC)

Clasifica documentos (arquitecturas, manuales, fichas técnicas) en activos IA-ready, llena el **APM** (inventario de aplicativos) y el **TDD Nivel 2** con revisión humana y exporta `.md` y `.json`. Pantallas: pasos 1 a 7, «Comparar APM», «Comparar TDD Nivel 2», «Progreso de APM y TDD» y «Configuración API key». El manual de usuario está en `frontend/gobierno_de_aplicaciones/assets/manual/`. La documentación completa de esta sección (estructura, pasos, API y variables) está en [`backend/app/gobierno_de_aplicaciones/README.md`](backend/app/gobierno_de_aplicaciones/README.md).

| Variable (servicio `gd-rag-api`) | Para qué |
|---|---|
| `AI_MODO` | `claude` (API de Anthropic) o `local` (Ollama). En el blueprint: `claude` |
| `ANTHROPIC_API_KEY` | **No se guarda en Render ni en el repo**: cada usuario la captura en «Configuración API key» |
| `FRONTEND_HOST` | La inyecta el blueprint; el botón «Portal GD 360» del APM regresa a `https://<host>/portal.html` |
| `PORTAL_GD360_URL` | Opcional: URL del portal principal si no se usa `FRONTEND_HOST` |
| `SERVIR_FRONTEND` | `1` para servir también el frontend de GD 360 desde el backend (un solo servicio) |

Los datos del portal APM (base SQLite, referencias del APM y de los TDD) viven en `backend/datos/` y no se suben al repositorio. En el plan *free* de Render se pierden en cada reinicio: después de un despliegue hay que volver a cargar el APM y los TDD de referencia.

## 5. Componentes RAG intercambiables (variables de entorno)

| Variable | Default (sin servicios externos) | Producción |
|---|---|---|
| `EMBEDDINGS_PROVIDER` | `hashing` (determinista, sin costo) | `openai` (cualquier endpoint `/v1/embeddings` compatible) |
| `VECTOR_STORE` | `memory` (se pierde al reiniciar) | `pgvector` (Render PostgreSQL; DDL en `adapters.py`) |
| `LLM_PROVIDER` | `extractive` (devuelve fragmentos, sin alucinación) | `openai` (OpenAI, Azure OpenAI, vLLM…) |

Para agregar otro proveedor (Vertex, Bedrock, Qdrant, Azure AI Search) basta con implementar la interfaz correspondiente de `base.py` y registrarla en `engine.py`.

## 6. Despliegue en Render

1. Sube el repositorio a GitHub o GitLab.
2. En Render: **New → Blueprint** y selecciona el repo. Render lee `render.yaml` y crea:
   - `gd-rag-api` (Python): `pip install -r requirements.txt` y `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. El `JWT_SECRET` se genera solo y CORS se configura con el host del portal (`FRONTEND_HOST`).
   - `gd-portal` (Static): `sh scripts/render-build.sh` escribe `assets/js/env.js` con `https://<host de gd-rag-api>`.
3. Si quieres publicar solo el look and feel, pon `USE_MOCK=true` en `gd-portal`.
4. El Portal APM TEC (Gobierno de Aplicaciones) queda en `https://<host de gd-rag-api>/gobierno_de_aplicaciones/`; el portal lo abre desde la tercera tarjeta.

Notas del plan *free*: el backend se duerme después de 15 min sin tráfico (el primer request tarda unos 30–50 s) y el índice en memoria se reconstruye con el catálogo en cada arranque. Los documentos cargados necesitan `VECTOR_STORE=pgvector` para persistir.

## 7. Migración a Angular

**Render sí soporta Angular.** Un Static Site puede compilarlo, o puedes subir el precompilado:

```yaml
  - type: web
    name: gd-portal
    runtime: static
    rootDir: frontend-angular
    buildCommand: npm ci && npm run build        # o vacío si subes el dist/ ya compilado
    staticPublishPath: dist/gd-portal/browser
    routes:
      - type: rewrite                            # necesario para el router de Angular (SPA)
        source: /*
        destination: /index.html
```

La versión HTML ya está separada para que el paso sea directo:

| HTML actual | Angular |
|---|---|
| `theme.css` | `src/styles.scss` + Bootstrap por npm |
| `env.js` / `config.js` | `src/environments/environment.ts` |
| `api.js` | `core/services/api.service.ts` (HttpClient) + `auth.interceptor.ts` |
| `auth.js` → `guard()` | `core/guards/auth.guard.ts` |
| `layout.js` → header / asistente / chat | `HeaderComponent`, `AssistantTabComponent`, `ChatComponent` |
| `portal.html`, `gobierno.html?id=`, `carga.html`, `index.html` | Rutas `/`, `/gobierno/:id`, `/mi-espacio`, `/login` |

Los contratos (`schemas/models.py`) se trasladan a interfaces TypeScript sin cambios.
