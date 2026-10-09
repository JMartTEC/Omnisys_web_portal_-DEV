"""
contenido_tdd2.py
-----------------
Lectura del CONTENIDO COMPLETO de los TDD Nivel 2 (texto, tablas y diagramas) y
la base de IA que se apoya en el.

Donde vive el contenido
    Cosmos  tdd2/documentos, documentos tipo "tdd2_contenido" (id tdd2c-<huella>):
            bloques en orden, texto plano, referencias a imagenes, analisis_ia.
    Blob    imagenes-tdd/<numero>/<imagen>             los diagramas
            documentos/tdd-nivel2/<numero>-<nombre>    el .docx original
    Los carga `tools/cargar_tdd2_contenido.py`.

Variables de entorno
    COSMOS_ENDPOINT / COSMOS_KEY    las mismas de la persistencia (llave opcional)
    STORAGE_ENDPOINT                https://<cuenta>.blob.core.windows.net/
    CONTENIDO_TDD2_DIR              (opcional) carpeta local con el paquete que
                                    genera `cargar_tdd2_contenido.py extraer`
                                    (contenido/*.json + imagenes/): sirve para
                                    trabajar sin Azure.

La base de IA (preguntar)
    1. Parte el contenido en fragmentos por seccion (titulo + lo que sigue).
    2. Busca los fragmentos mas parecidos a la pregunta (puntaje tipo TF-IDF,
       sin acentos). No necesita llave ni servicio de pago.
    3. Si hay ANTHROPIC_API_KEY, se los entrega a Claude para que redacte la
       respuesta SOLO con ese material y citando de que TDD salio. Sin llave,
       devuelve los fragmentos tal cual (respuesta extractiva).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any

log = logging.getLogger("apm.contenido_tdd2")

_TTL = 600           # segundos que se conserva el contenido en memoria
_MAX_FRAGMENTO = 1800
_MAX_CONTEXTO = 14000


def _sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t or "")
                   if unicodedata.category(c) != "Mn").lower()


_PALABRAS_VACIAS = set("""
de la el los las un una unos unas y o en a por para con sin del al que se su sus es son
como cual cuales cuando donde esta este estos estas lo le les mas menos muy ya no si
hay ser tiene tienen tener hace hacen sobre entre desde hasta segun the of and to
""".split())


def _terminos(t: str) -> list[str]:
    return [p for p in re.findall(r"[a-z0-9_]{2,}", _sin_acentos(t))
            if p not in _PALABRAS_VACIAS]


def _texto_bloque(b: dict) -> str:
    tipo = b.get("tipo")
    if tipo in ("titulo", "parrafo"):
        return b.get("texto", "")
    if tipo == "lista":
        items = b.get("items") or ([b["texto"]] if b.get("texto") else [])
        return "\n".join(f"- {i}" for i in items)
    if tipo == "tabla":
        filas = b.get("filas") or []
        return "\n".join(" | ".join(c for c in fila if c) for fila in filas)
    return ""


class ContenidoTdd2:
    def __init__(self, contenedor_cosmos=None):
        self._cont = contenedor_cosmos
        self._lock = threading.Lock()
        self._docs: dict[str, dict] | None = None
        self._cargado = 0.0
        self._fragmentos: list[dict] = []
        self._idf: dict[str, float] = {}
        self._blob = None
        self._minis: dict[tuple[str, str], tuple[bytes, str]] = {}

    def invalidar(self) -> None:
        """Marca el contenido en memoria como viejo (se vuelve a leer al pedirlo)."""
        with self._lock:
            self._docs = None
            self._minis.clear()

    # ------------------------------------------------------------------
    # origen de los datos
    # ------------------------------------------------------------------

    @staticmethod
    def _carpeta_local() -> Path | None:
        d = os.environ.get("CONTENIDO_TDD2_DIR", "").strip()
        return Path(d) if d else None

    def disponible(self) -> bool:
        return self._cont is not None or self._carpeta_local() is not None

    def _leer_todo(self) -> dict[str, dict]:
        carpeta = self._carpeta_local()
        docs: dict[str, dict] = {}
        if carpeta and (carpeta / "contenido").is_dir():
            for f in sorted((carpeta / "contenido").glob("*.json")):
                d = json.loads(f.read_text(encoding="utf-8"))
                d.setdefault("id", "tdd2c-" + (d.get("sha256") or f.stem)[:16])
                d.setdefault("tipo", "tdd2_contenido")
                d.setdefault("aplicativo", {})
                d.setdefault("archivo_original", {})
                docs[d["id"]] = d
            return docs
        if self._cont is None:
            return docs
        # El contenido solo guarda el numero del aplicativo; el nombre vive en el
        # documento "tdd2" ligado (la otra cara del enlace APM <-> TDD Nivel 2).
        nombres: dict[str, str] = {}
        try:
            for t in self._cont.query_items(
                    "SELECT c.numero, c.aplicativo FROM c WHERE c.tipo = 'tdd2'",
                    enable_cross_partition_query=True):
                nombres[str(t.get("numero"))] = (t.get("aplicativo") or {}).get("nombre", "")
        except Exception:                           # noqa: BLE001
            log.warning("contenido TDD2: no se pudieron leer los nombres de aplicativo")
        for d in self._cont.query_items(
                "SELECT * FROM c WHERE c.tipo = 'tdd2_contenido'",
                enable_cross_partition_query=True):
            d = {k: v for k, v in d.items() if not k.startswith("_")}
            ap = d.setdefault("aplicativo", {})
            if not ap.get("nombre"):
                ap["nombre"] = nombres.get(str(ap.get("numero")), "")
            docs[d["id"]] = d
        return docs

    def _asegurar(self) -> dict[str, dict]:
        with self._lock:
            if self._docs is None or time.time() - self._cargado > _TTL:
                self._docs = self._leer_todo()
                self._cargado = time.time()
                self._indexar()
                log.info("contenido TDD2: %s documentos, %s fragmentos",
                         len(self._docs), len(self._fragmentos))
            return self._docs

    def recargar(self) -> int:
        with self._lock:
            self._docs = None
        return len(self._asegurar())

    # ------------------------------------------------------------------
    # lectura
    # ------------------------------------------------------------------

    @staticmethod
    def _resumen(d: dict) -> dict:
        ap = d.get("aplicativo") or {}
        est = d.get("estadisticas") or {}
        orig = d.get("archivo_original") or {}
        return {
            "id": d["id"], "nombre": d.get("nombre", ""),
            "numero": ap.get("numero", ""), "id_habilitador": ap.get("id_habilitador", ""),
            "aplicativo": ap.get("nombre", ""),
            "parrafos": est.get("parrafos", 0), "tablas": est.get("tablas", 0),
            "imagenes": len(d.get("imagenes") or []),
            "caracteres": est.get("caracteres", 0),
            "tiene_original": bool(orig.get("blob")) and bool(orig.get("subido", True)),
            "tiene_analisis_ia": bool(d.get("analisis_ia")),
        }

    def listar(self) -> list[dict]:
        docs = self._asegurar()
        filas = [self._resumen(d) for d in docs.values()]
        filas.sort(key=lambda r: (r["nombre"] or "").lower())
        return filas

    def obtener(self, id_doc: str) -> dict | None:
        d = self._asegurar().get(id_doc)
        if d is None:
            return None
        salida = dict(d)
        salida.pop("texto_plano", None)       # el visor usa los bloques
        return salida

    # ------------------------------------------------------------------
    # Blob (imagenes y originales)
    # ------------------------------------------------------------------

    def _servicio_blob(self):
        if self._blob is None:
            endpoint = os.environ.get("STORAGE_ENDPOINT", "").strip()
            if not endpoint:
                raise RuntimeError("Falta STORAGE_ENDPOINT.")
            from azure.storage.blob import BlobServiceClient
            from azure.identity import DefaultAzureCredential
            self._blob = BlobServiceClient(endpoint, credential=DefaultAzureCredential())
        return self._blob

    @staticmethod
    def _tipo_imagen(nombre: str) -> str:
        ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "svg": "image/svg+xml", "bmp": "image/bmp",
                "emf": "image/emf", "wmf": "image/wmf", "webp": "image/webp"
                }.get(ext, "application/octet-stream")

    def imagen(self, id_doc: str, archivo: str) -> tuple[bytes, str] | None:
        d = self._asegurar().get(id_doc)
        if d is None or "/" in archivo or "\\" in archivo or ".." in archivo:
            return None
        carpeta = self._carpeta_local()
        numero = (d.get("aplicativo") or {}).get("numero", "")
        if carpeta:
            for ruta in ((carpeta / "imagenes" / Path(d.get("nombre", "")).stem / archivo),
                         (carpeta / "imagenes" / str(numero) / archivo)):
                if ruta.is_file():
                    return ruta.read_bytes(), self._tipo_imagen(archivo)
            return None
        meta = next((i for i in d.get("imagenes") or [] if i.get("archivo") == archivo), None)
        if meta is None:
            return None
        ruta_blob = meta.get("blob") or f"imagenes-tdd/{numero}/{archivo}"
        contenedor, _, nombre = ruta_blob.partition("/")
        datos = self._servicio_blob().get_blob_client(contenedor, nombre).download_blob().readall()
        return datos, self._tipo_imagen(archivo)

    def miniatura(self, id_doc: str, archivo: str, ancho: int = 360) -> tuple[bytes, str] | None:
        """La imagen reducida a `ancho` px (PNG), guardada en memoria."""
        clave = (id_doc, archivo)
        if clave in self._minis:
            return self._minis[clave]
        r = self.imagen(id_doc, archivo)
        if r is None:
            return None
        datos, tipo = r
        try:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(datos))
            img.thumbnail((ancho, ancho * 2))
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")
            sal = io.BytesIO()
            img.save(sal, "PNG", optimize=True)
            r = (sal.getvalue(), "image/png")
        except Exception:                               # noqa: BLE001
            r = (datos, tipo)                           # sin Pillow: la imagen tal cual
        if len(self._minis) > 400:
            self._minis.clear()
        self._minis[clave] = r
        return r

    def original(self, id_doc: str) -> tuple[Any, str, int | None] | None:
        """(iterador de bytes, nombre de descarga, tamano) del .docx original."""
        d = self._asegurar().get(id_doc)
        if d is None:
            return None
        orig = d.get("archivo_original") or {}
        ruta_blob = orig.get("blob") or ""
        if not ruta_blob or orig.get("subido") is False:
            return None
        contenedor, _, nombre = ruta_blob.partition("/")
        bc = self._servicio_blob().get_blob_client(contenedor, nombre)
        try:
            props = bc.get_blob_properties()
        except Exception:                       # el original todavia no esta en Blob
            return None
        flujo = bc.download_blob().chunks()
        return flujo, d.get("nombre", "tdd.docx"), props.size

    # ------------------------------------------------------------------
    # busqueda y preguntas
    # ------------------------------------------------------------------

    def _indexar(self) -> None:
        frags: list[dict] = []
        for d in (self._docs or {}).values():
            ap = d.get("aplicativo") or {}
            actual = {"titulo": "Inicio del documento", "texto": []}

            def cerrar():
                texto = "\n".join(t for t in actual["texto"] if t).strip()
                if not texto:
                    return
                for i in range(0, len(texto), _MAX_FRAGMENTO):
                    frags.append({"doc": d["id"], "nombre": d.get("nombre", ""),
                                  "numero": ap.get("numero", ""),
                                  "aplicativo": ap.get("nombre", ""),
                                  "seccion": actual["titulo"],
                                  "texto": texto[i:i + _MAX_FRAGMENTO]})

            for b in d.get("bloques") or []:
                if b.get("tipo") == "titulo":
                    cerrar()
                    actual = {"titulo": b.get("texto", ""), "texto": []}
                elif b.get("tipo") == "imagen":
                    meta = next((i for i in d.get("imagenes") or []
                                 if i.get("archivo") == b.get("archivo")), {})
                    if meta.get("descripcion_ia"):
                        actual["texto"].append(f"[Diagrama {b.get('archivo')}] "
                                               f"{meta['descripcion_ia']}")
                else:
                    actual["texto"].append(_texto_bloque(b))
            cerrar()

        df: dict[str, int] = {}
        for f in frags:
            f["tf"] = {}
            for t in _terminos(f["seccion"] + " " + f["texto"]):
                f["tf"][t] = f["tf"].get(t, 0) + 1
            f["sec_t"] = set(_terminos(f["seccion"] + " " + f["nombre"]))
            for t in f["tf"]:
                df[t] = df.get(t, 0) + 1
        n = max(len(frags), 1)
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self._fragmentos = frags

    def buscar(self, consulta: str, k: int = 6, id_doc: str = "") -> list[dict]:
        self._asegurar()
        q = _terminos(consulta)
        if not q:
            return []
        puntajes = []
        for f in self._fragmentos:
            if id_doc and f["doc"] != id_doc:
                continue
            p = 0.0
            for t in q:
                tf = f["tf"].get(t, 0)
                if tf:
                    p += (1 + math.log(tf)) * self._idf.get(t, 1.0)
                if t in f["sec_t"]:
                    p += 1.5 * self._idf.get(t, 1.0)
            if p > 0:
                puntajes.append((p, f))
        puntajes.sort(key=lambda x: -x[0])
        salida = []
        for p, f in puntajes[:k]:
            salida.append({k2: v for k2, v in f.items() if k2 not in ("tf", "sec_t")}
                          | {"puntaje": round(p, 2)})
        return salida

    def preguntar(self, pregunta: str, id_doc: str = "") -> dict:
        frags = self.buscar(pregunta, k=6, id_doc=id_doc)
        if not frags:
            return {"ok": True, "modo": "sin_resultados", "respuesta":
                    "No encontre nada parecido en el contenido de los TDD Nivel 2. "
                    "Prueba con otras palabras (nombre del aplicativo, una seccion, "
                    "un sistema o un campo).", "fuentes": []}
        fuentes = [{"doc": f["doc"], "nombre": f["nombre"], "numero": f["numero"],
                    "aplicativo": f["aplicativo"], "seccion": f["seccion"],
                    "texto": f["texto"][:600]} for f in frags]

        llave = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not llave:
            return {"ok": True, "modo": "extractivo",
                    "respuesta": "Estos son los fragmentos mas cercanos a tu pregunta "
                                 "(sin llave de Claude no se redacta una respuesta).",
                    "fuentes": fuentes}

        contexto, usado = [], 0
        for i, f in enumerate(frags, 1):
            bloque = (f"[{i}] TDD «{f['nombre']}» (aplicativo {f['numero']} "
                      f"{f['aplicativo']}), seccion «{f['seccion']}»:\n{f['texto']}")
            if usado + len(bloque) > _MAX_CONTEXTO:
                break
            contexto.append(bloque)
            usado += len(bloque)
        try:
            import anthropic
            cabeceras = ({"anthropic-workspace-id": os.environ["ANTHROPIC_WORKSPACE_ID"].strip()}
                         if os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip() else None)
            cliente = anthropic.Anthropic(api_key=llave, default_headers=cabeceras,
                                          max_retries=1, timeout=60)
            r = cliente.messages.create(
                model=(os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-5").strip(),
                max_tokens=1200,
                system=("Respondes preguntas sobre los TDD Nivel 2 (descripcion tecnica de "
                        "aplicativos) del Tecnologico de Monterrey usando EXCLUSIVAMENTE los "
                        "fragmentos numerados que recibes. Si no alcanzan para responder, "
                        "dilo. Cita los fragmentos como [1], [2]. Responde en espanol, claro "
                        "y breve."),
                messages=[{"role": "user", "content":
                           "Fragmentos:\n\n" + "\n\n".join(contexto)
                           + f"\n\nPregunta: {pregunta}"}])
            texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            return {"ok": True, "modo": "claude", "respuesta": texto.strip(),
                    "fuentes": fuentes}
        except Exception as exc:                # noqa: BLE001
            log.warning("preguntar: Claude no respondio (%s: %s)", type(exc).__name__, exc)
            return {"ok": True, "modo": "extractivo",
                    "respuesta": "Claude no respondio ("
                                 f"{type(exc).__name__}); estos son los fragmentos mas "
                                 "cercanos a tu pregunta.",
                    "fuentes": fuentes}

    def estado_ia(self) -> dict:
        docs = self._asegurar()
        imgs = [i for d in docs.values() for i in d.get("imagenes") or []]
        return {
            "documentos": len(docs),
            "fragmentos": len(self._fragmentos),
            "imagenes": len(imgs),
            "imagenes_descritas": sum(1 for i in imgs if i.get("descripcion_ia")),
            "claude_listo": bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip()),
        }
