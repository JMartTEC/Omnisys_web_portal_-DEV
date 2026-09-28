# Portal APM TEC — Gobierno de Aplicaciones VPAF

Sección **Gobierno de Aplicaciones** del Portal GD 360. Convierte documentos sueltos (arquitecturas, manuales, fichas técnicas, presentaciones, hojas de cálculo, minutas) en **activos de conocimiento IA-ready** y, al mismo tiempo, los compara contra las dos fuentes institucionales: el **APM** (inventario de aplicativos, 45 columnas por aplicativo) y el **TDD Nivel 2** (diseño técnico de cada aplicativo, con confianza C1–C4 por dato). Nada se inventa: cada valor propuesto muestra de qué parte del documento salió y una persona decide qué se escribe.

| Capa | Tecnología | Carpeta | Servicio en Render |
|---|---|---|---|
| Pantallas | HTML5 + CSS + JS sin framework (mismo estilo que GD 360) | `frontend/gobierno_de_aplicaciones/` | Las sirve `gd-rag-api` |
| Backend | Python 3.11 + FastAPI, montado en `/gobierno_de_aplicaciones` | `backend/app/gobierno_de_aplicaciones/` | Dentro de `gd-rag-api` |
| IA | Claude (API de Anthropic) o Ollama local, intercambiables | `services/ia/` | Variable `AI_MODO` |
| Base | SQLite: línea base del APM y TDD, documentos leídos y decisiones | `backend/datos/` (no se sube) | Se pierde al reiniciar en el plan *free* |

---

## 1. Estructura

```
backend/app/gobierno_de_aplicaciones/
├── main.py                        App FastAPI del portal APM (publica /assets y registra las rutas)
├── api/v1/routes.py               Pantallas (/, /paso/{n}, /conciliar, /tdd2, /docs, /config) y endpoints /api/...
├── core/
│   ├── configuracion.py           Motor de IA: modo, modelo, llave (se guarda en backend/.env, nunca completa en pantalla)
│   ├── sesion.py                  Estado del recorrido del asistente (pasos 1 a 7)
│   └── progreso_vivo.py           Avance en vivo del análisis de un documento
├── schemas/models.py              Contratos (Pydantic)
└── services/
    ├── extraccion.py              Texto, tablas, propiedades e imágenes del archivo
    ├── deteccion.py               Reglas deterministas: versión, fecha, responsable, estado, confidencialidad
    ├── metadata_validator.py      Valida y arbitra lo que propuso la IA contra la evidencia
    ├── taxonomy.py                Catálogos cerrados y niveles de confianza (Alta / Media / Requiere revisión)
    ├── identificacion.py          A qué aplicativo del APM pertenece cada documento
    ├── apm.py · campos.py         Lectura del libro de APM y sus 45 columnas reales
    ├── tdd.py · tdd_nivel2.py     Lectura y comparación del TDD Nivel 2
    ├── llenado.py                 Propuesta de llenado del APM y del TDD (pasos 5 y 6)
    ├── conciliacion.py            «Comparar APM»: varios documentos contra el APM, campo por campo
    ├── exportador.py              Salida .md (frontmatter YAML) y .json con trazabilidad
    ├── lotes.py · fuentes.py      Procesamiento de carpetas completas y de ligas
    ├── almacen.py                 Base SQLite: línea base, memoria de documentos y decisiones
    ├── ia/
    │   ├── claude_service.py      Clasificación con la API de Anthropic (también lee diagramas)
    │   └── ollama_service.py      Clasificación local, gratis y sin internet (solo texto)
    └── parsers/                   Word, PDF, PowerPoint, Excel, texto e imágenes

frontend/gobierno_de_aplicaciones/
├── _layout.html                   Barra, franja, banner y pie comunes (estilo GD 360)
├── pantallas/                     paso-1 … paso-7, conciliar, tdd2, docs (Progreso), config
└── assets/
    ├── css/comun.css              Tokens de diseño (colores y tipografía de GD 360)
    ├── js/comun.js                Utilidades, franja de pasos, indicador del motor de IA
    ├── js/pages/*.js              Lógica de cada pantalla
    ├── fuentes/ · img/            Poppins / IBM Plex y logos
    ├── manual/                    Manual de usuario en PDF (botón «Manual de usuario»)
    └── plantillas/                Plantilla vacía del TDD Nivel 2
```

## 2. Cómo trabaja

Cada documento pasa por siete pasos. Los primeros cuatro son automáticos; en los últimos decide una persona.

| Paso | Pantalla | Qué pasa |
|---|---|---|
| 1 | Origen | Se indica un documento, una liga o una carpeta completa |
| 2 | Alcance | Resumen de lo que se va a procesar (en carpeta) |
| 3 | Análisis - IA Ready | Extracción → detección determinista → clasificación con IA → validación y arbitraje |
| 4 | Revisión y Vectorización | Aplicativo identificado y ficha editable con confianza por campo |
| 5 | Llenado de APM | Las 45 columnas reales del APM contra lo que dice el documento |
| 6 | Llenado de TDD | Comparación contra el TDD Nivel 2 real del aplicativo |
| 7 | Exportación | Descarga o guarda el `.md` y el `.json` |

**Regla de oro:** el portal nunca modifica los archivos originales. Todo lo que escribe es una versión nueva del APM o del TDD, o los archivos `.md` y `.json` en la carpeta `_ia-ready`.

Cuando el APM ya tiene un valor y el documento dice otra cosa, gana el más reciente según sus fechas. Si falta alguna de las dos fechas, el campo se marca «El documento dice otra cosa · revisa» para decidirlo en «Comparar APM».

## 3. Ejecutar en local

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
SERVIR_FRONTEND=1 uvicorn app.main:app --reload --port 8000
# Portal GD 360:            http://localhost:8000/
# Gobierno de Aplicaciones: http://localhost:8000/gobierno_de_aplicaciones/
# Swagger del portal APM:   http://localhost:8000/gobierno_de_aplicaciones/api/docs
```

Antes de la primera clasificación hay que **sembrar la base**: en «Comparar APM» abre el libro del APM y pulsa «Sembrar la base con APM y TDD»; en «Comparar TDD Nivel 2» sube los TDD Nivel 2 de referencia.

## 4. Contrato de la API (`/gobierno_de_aplicaciones/api`)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/analyze` · `/analyze-ruta` | Clasifica un archivo subido o una ruta / URL |
| POST | `/analizar-vivo` · `/analizar-vivo/subir` | Igual, en segundo plano; el avance se consulta en `GET /analizar-vivo/{id}` |
| POST | `/explorar` | Vista previa del alcance de una carpeta (no clasifica) |
| POST | `/lote` | Procesa una carpeta en segundo plano; `GET /lote/{id}` da el avance y `POST /lote/{id}/cancelar` lo detiene |
| POST | `/exportar` | Escribe el `.md` y el `.json` del activo revisado |
| POST | `/llenado/aplicar` | Aplica la propuesta de llenado y devuelve el antes y después |
| POST | `/llenado/nueva-version-apm` · `/llenado/nueva-version-tdd` | Escribe una versión nueva del APM o del TDD con los campos que estaban vacíos |
| POST | `/vincular-manual` | Compara un documento contra el aplicativo que elige la persona |
| POST | `/apm/abrir` | Abre el libro del APM: columnas, cuáles se pueden escribir y avisos |
| POST | `/almacen/sembrar` | Carga en la base lo que dicen hoy el APM y los TDD |
| GET | `/almacen/resumen` | Aplicativos, documentos leídos y decisiones guardadas |
| POST | `/almacen/reporte` · `/almacen/exportar` | Reporte de avance por aplicativo; exportación a JSON y CSV |
| POST | `/conciliar/subir` · `/conciliar/fuentes` | «Comparar APM»: sube e identifica los documentos fuente |
| POST | `/conciliar/aplicativo` · `/conciliar/guardar-apm` | Propuestas campo por campo y versión nueva del APM |
| POST | `/tdd2/sembrar` · `/tdd2/sembrar-subidos` | Registra los TDD Nivel 2 de referencia |
| POST | `/tdd2/comparar` · `/tdd2/guardar` | Compara un TDD Nivel 2 contra su referencia y guarda la versión nueva |
| GET | `/tdd2/referencia` · `/docs-referencia` | Aplicativos con TDD Nivel 2 y su progreso |
| GET / POST | `/config` | Estado del motor de IA / guarda la configuración |
| POST | `/config/probar` · `/config/borrar-llave` | Prueba la conexión con el motor / borra la llave guardada |
| GET | `/descargar` | Descarga una versión nueva de APM o TDD escrita por el portal |

> Las pantallas se sirven en `/gobierno_de_aplicaciones/`, `/paso/{n}`, `/conciliar`, `/tdd2`, `/docs` y `/config`.

## 5. Motor de IA (variables de entorno)

| Variable | Default | Uso |
|---|---|---|
| `AI_MODO` | automático | `claude` (API de Anthropic, más preciso y convierte diagramas a texto) o `local` (Ollama, gratis y sin internet) |
| `ANTHROPIC_API_KEY` | — | **No se guarda en Render ni en el repositorio**: cada usuario la captura en «Configuración API key» |
| `ANTHROPIC_MODEL` · `ANTHROPIC_WORKSPACE_ID` | `claude-sonnet-5` · — | Modelo y workspace de la API |
| `OLLAMA_HOST` · `OLLAMA_MODEL` · `OLLAMA_MAX_CHARS` | `http://127.0.0.1:11434` · `qwen3:8b` · `18000` | Modo local |
| `PORTAL_MODO_SEGURO` | encendido en Render | Solo acepta archivos subidos, no rutas del servidor |
| `FRONTEND_HOST` · `PORTAL_GD360_URL` | — | A dónde regresa el botón «Portal GD 360» |

El indicador de la franja gris muestra el estado del motor: **rojo** sin configurar o sin conexión, **naranja** comprobando y **verde** en línea.

## 6. Despliegue en Render

El portal APM viaja dentro del backend de GD 360, así que no necesita un servicio propio:

- **Blueprint de Aaron (`render.yaml`):** queda en `https://<host de gd-rag-api>/gobierno_de_aplicaciones/` y el portal GD 360 lo abre desde la tercera tarjeta.
- **Un solo servicio:** Build `pip install -r backend/requirements.txt`, Start `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT` y `SERVIR_FRONTEND=1`.

Notas del plan *free*: la base (`backend/datos/`) se borra en cada reinicio o despliegue; después hay que volver a sembrar el APM y los TDD de referencia. Para conservarla se necesita un disco persistente.

## 7. Manual de usuario

El manual para usuarios finales está en `frontend/gobierno_de_aplicaciones/assets/manual/Manual_de_usuario_Portal_APM_TEC.pdf` y se abre desde el botón «Manual de usuario» de la barra.

---

Desarrollado por **Omnisys S.A. de C.V.** para el Tecnológico de Monterrey.
