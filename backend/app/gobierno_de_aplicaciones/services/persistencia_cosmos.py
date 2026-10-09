"""
persistencia_cosmos.py
----------------------
Respaldo durable del almacen del Portal APM en Azure Cosmos DB.

El almacen (`almacen.py`) sigue trabajando sobre SQLite -- es rapido, es lo que
ya esta probado y concentra todo el SQL en un solo lugar. Lo que cambia es de
DONDE se llena y A DONDE se copia: Cosmos es la fuente durable.

    arranque   Cosmos -> SQLite (hidratar)    la base local se arma desde la nube
    escritura  SQLite -> Cosmos (volcar)      cada cambio queda guardado en la nube

Dos bases de Cosmos, separadas (decision del proyecto):

    apm   / habilitadores   aplicativos (con sus 45 campos), TDD V3, documentos
                            leidos (+ hallazgos), decisiones, escrituras, referencias
    tdd2  / documentos      TDD Nivel 2 (con cada campo y su confianza C1-C4)

La llave de particion de los dos contenedores es /id_habilitador, asi que cada
documento lleva ese campo (un valor vacio se guarda como "sin-id").

Sin llave, entra con la identidad administrada del App Service (o con la sesion
de `az login` en una maquina de trabajo).
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .extractor_docx import extraer_docx

log = logging.getLogger("apm.persistencia")

SIN_ID = "sin-id"


def _pk(valor: Any) -> str:
    v = ("" if valor is None else str(valor)).strip()
    return v or SIN_ID


def _de_pk(valor: str) -> str:
    return "" if valor == SIN_ID else valor


def _limpio(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


_TIPOS_APM = {"aplicativo", "tdd", "documento", "decision", "escritura", "referencia"}


class PersistenciaCosmos:
    def __init__(self, endpoint: str, llave: str = "",
                 db_apm: str = "apm", cont_apm: str = "habilitadores",
                 db_tdd2: str = "tdd2", cont_tdd2: str = "documentos",
                 blob_endpoint: str = ""):
        from azure.cosmos import CosmosClient
        if llave:
            cred: Any = llave
        else:
            from azure.identity import DefaultAzureCredential
            cred = DefaultAzureCredential()
        cliente = CosmosClient(endpoint, credential=cred)
        self._apm = cliente.get_database_client(db_apm).get_container_client(cont_apm)
        self._tdd2 = cliente.get_database_client(db_tdd2).get_container_client(cont_tdd2)
        self._lock = threading.Lock()
        # Contenido completo de los TDD Nivel 2 (texto, tablas, diagramas): se
        # guarda en segundo plano y de uno en uno, para no frenar la peticion
        # que sembro o guardo el TDD.
        self._blob_endpoint = blob_endpoint
        self._blob = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="contenido-tdd2")
        self.al_cambiar_contenido = None      # callable sin argumentos (invalida cache)

    @property
    def contenedor_tdd2(self):
        """Contenedor tdd2/documentos (lo usa el visor del contenido de los TDD)."""
        return self._tdd2

    # ------------------------------------------------------------------
    # Cosmos -> SQLite
    # ------------------------------------------------------------------

    def hay_datos(self) -> bool:
        for cont in (self._apm, self._tdd2):
            for _ in cont.query_items("SELECT TOP 1 c.id FROM c",
                                      enable_cross_partition_query=True):
                return True
        return False

    def hidratar(self, con) -> dict:
        """Reemplaza el contenido de las tablas locales con lo guardado en Cosmos."""
        docs_apm = [_limpio(d) for d in self._apm.query_items(
            "SELECT * FROM c", enable_cross_partition_query=True)]
        # solo los documentos "tdd2" (el contenido completo vive aparte, en
        # documentos tipo "tdd2_contenido", y se lee bajo demanda)
        docs_tdd2 = [_limpio(d) for d in self._tdd2.query_items(
            "SELECT * FROM c WHERE c.tipo = 'tdd2'", enable_cross_partition_query=True)]

        tablas = ("aplicativos", "base_apm", "base_tdd", "base_tdd_celdas",
                  "documentos", "hallazgos", "decisiones", "escrituras",
                  "referencia", "base_tdd2", "base_tdd2_campos")
        for t in tablas:
            con.execute(f"DELETE FROM {t}")

        for d in docs_apm:
            tipo = d.get("tipo")
            if tipo == "aplicativo":
                con.execute("INSERT OR REPLACE INTO aplicativos VALUES (?,?,?,?,?,?)",
                            (d["numero"], _de_pk(d["id_habilitador"]), d["nombre"],
                             d["fila"], d["sembrado_en"], d["origen"]))
                con.executemany(
                    "INSERT OR REPLACE INTO base_apm VALUES (?,?,?,?,?,?,?)",
                    [(d["numero"], c["clave"], c["grupo"], c["etiqueta"], c["valor"],
                      c["escribible"], c["sembrado_en"]) for c in d["campos"]])
            elif tipo == "tdd":
                con.execute(
                    "INSERT OR REPLACE INTO base_tdd VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (d["huella"], d["ruta"], d["nombre"], d["numero"],
                     _de_pk(d["id_habilitador"]), d["tablas"], d["celdas_llenas"],
                     d["celdas_totales"], d["completitud"], d["faltantes"],
                     d["sembrado_en"]))
                con.executemany(
                    "INSERT OR REPLACE INTO base_tdd_celdas VALUES (?,?,?,?,?,?)",
                    [(d["huella"], c["tabla"], c["fila"], c["columna"],
                      c["etiqueta"], c["texto"]) for c in d["celdas"]])
            elif tipo == "documento":
                con.execute(
                    "INSERT OR REPLACE INTO documentos VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (d["huella"], d["nombre"], d["origen"], d["tipo_origen"],
                     d["bytes"], d["numero"], d["senal"], d["evidencia"],
                     d["leido_en"], d["veces_visto"]))
                con.executemany(
                    "INSERT OR REPLACE INTO hallazgos VALUES (?,?,?,?)",
                    [(d["huella"], h["clave"], h["valor"], h["evidencia"])
                     for h in d["hallazgos"]])
            elif tipo == "decision":
                con.execute(
                    "INSERT OR REPLACE INTO decisiones VALUES (?,?,?,?,?,?)",
                    (d["numero"], d["clave"], d["valor"], d["estado"],
                     d["candidatos"], d["decidido_en"]))
            elif tipo == "escritura":
                con.execute(
                    "INSERT OR REPLACE INTO escrituras VALUES (?,?,?,?,?,?,?,?)",
                    (d["fila_id"], d["tipo_escritura"], d["numero"], d["origen"],
                     d["destino"], d["celdas"], d["detalle"], d["escrito_en"]))
            elif tipo == "referencia":
                con.execute(
                    "INSERT OR REPLACE INTO referencia VALUES (?,?,?,?,?,?)",
                    (d["tipo_ref"], d["numero"], d["ruta_estable"],
                     d["origen_actual"], d["creado_en"], d["actualizado_en"]))

        for d in docs_tdd2:
            if d.get("tipo") != "tdd2":
                continue
            con.execute(
                "INSERT OR REPLACE INTO base_tdd2 VALUES (?,?,?,?,?,?,?,?,?)",
                (d["huella"], d["ruta"], d["nombre"], d["numero"],
                 _de_pk(d["id_habilitador"]), d["campos_llenos"],
                 d["campos_totales"], d["completitud"], d["sembrado_en"]))
            con.executemany(
                "INSERT OR REPLACE INTO base_tdd2_campos VALUES (?,?,?,?,?,?,?)",
                [(d["huella"], c["llave"], c["seccion"], c["seccion_titulo"],
                  c["campo"], c["valor"], c["confianza"]) for c in d["campos"]])
        return {"docs_apm": len(docs_apm), "docs_tdd2": len(docs_tdd2)}

    # ------------------------------------------------------------------
    # SQLite -> Cosmos
    # ------------------------------------------------------------------

    @staticmethod
    def _filas(con, sql: str, *args) -> list[dict]:
        return [dict(r) for r in con.execute(sql, args)]

    def _construir(self, con) -> tuple[list[dict], list[dict]]:
        apm_docs: list[dict] = []
        tdd2_docs: list[dict] = []
        id_de = {r["numero"]: r["id_habilitador"]
                 for r in self._filas(con, "SELECT numero, id_habilitador FROM aplicativos")}

        # Las dos bases son separadas pero se ven entre si: comparten el numero
        # de aplicativo y el id de habilitador, y cada lado lleva una referencia
        # al otro (el aplicativo apunta a sus TDD Nivel 2; el TDD Nivel 2 apunta
        # a su aplicativo). Asi el portal, al encontrar algo, sabe en que base
        # guardarlo y puede mostrar las dos vistas juntas.
        nombre_de = {r["numero"]: r["nombre"]
                     for r in self._filas(con, "SELECT numero, nombre FROM aplicativos")}
        tdd2_de: dict[str, list[dict]] = {}
        for t in self._filas(con, "SELECT huella, numero, nombre, completitud, "
                                  "campos_llenos, campos_totales, sembrado_en FROM base_tdd2"):
            tdd2_de.setdefault(t["numero"], []).append(
                {"huella": t["huella"], "base": "tdd2", "id": f"tdd2-{t['huella']}",
                 "nombre": t["nombre"], "completitud": t["completitud"],
                 "campos_llenos": t["campos_llenos"],
                 "campos_totales": t["campos_totales"],
                 "sembrado_en": t["sembrado_en"]})

        for a in self._filas(con, "SELECT * FROM aplicativos"):
            campos = self._filas(
                con, "SELECT clave, grupo, etiqueta, valor, escribible, sembrado_en "
                     "FROM base_apm WHERE numero = ? ORDER BY rowid", a["numero"])
            apm_docs.append({
                "id": f"app-{a['numero']}", "tipo": "aplicativo",
                "id_habilitador": _pk(a["id_habilitador"]), "numero": a["numero"],
                "nombre": a["nombre"], "fila": a["fila"],
                "sembrado_en": a["sembrado_en"], "origen": a["origen"],
                "tdd_nivel2": tdd2_de.get(a["numero"], []),
                "campos": campos})

        for t in self._filas(con, "SELECT * FROM base_tdd"):
            celdas = self._filas(
                con, "SELECT tabla, fila, columna, etiqueta, texto "
                     "FROM base_tdd_celdas WHERE huella = ? ORDER BY rowid", t["huella"])
            apm_docs.append({**t, "id": f"tdd-{t['huella']}", "tipo": "tdd",
                             "id_habilitador": _pk(t["id_habilitador"]),
                             "celdas": celdas})

        for d in self._filas(con, "SELECT * FROM documentos"):
            hall = self._filas(
                con, "SELECT clave, valor, evidencia FROM hallazgos WHERE huella = ? "
                     "ORDER BY rowid", d["huella"])
            apm_docs.append({**d, "id": f"doc-{d['huella']}", "tipo": "documento",
                             "id_habilitador": _pk(id_de.get(d["numero"], "")),
                             "hallazgos": hall})

        for d in self._filas(con, "SELECT * FROM decisiones"):
            apm_docs.append({**d, "id": f"dec-{d['numero']}-{d['clave']}",
                             "tipo": "decision",
                             "id_habilitador": _pk(id_de.get(d["numero"], ""))})

        for e in self._filas(con, "SELECT * FROM escrituras"):
            e = dict(e)
            fila_id = e.pop("id")
            tipo_esc = e.pop("tipo")
            apm_docs.append({**e, "id": f"esc-{fila_id}", "tipo": "escritura",
                             "fila_id": fila_id, "tipo_escritura": tipo_esc,
                             "id_habilitador": _pk(id_de.get(e["numero"], ""))})

        for r in self._filas(con, "SELECT * FROM referencia"):
            r = dict(r)
            tipo_ref = r.pop("tipo")
            apm_docs.append({**r, "id": f"ref-{tipo_ref}-{r['numero']}",
                             "tipo": "referencia", "tipo_ref": tipo_ref,
                             "id_habilitador": _pk(id_de.get(r["numero"], ""))})

        for t in self._filas(con, "SELECT * FROM base_tdd2"):
            campos = self._filas(
                con, "SELECT llave, seccion, seccion_titulo, campo, valor, confianza "
                     "FROM base_tdd2_campos WHERE huella = ? ORDER BY rowid", t["huella"])
            tdd2_docs.append({**t, "id": f"tdd2-{t['huella']}", "tipo": "tdd2",
                              "id_habilitador": _pk(t["id_habilitador"]),
                              "aplicativo": {"base": "apm", "id": f"app-{t['numero']}",
                                             "numero": t["numero"],
                                             "nombre": nombre_de.get(t["numero"], "")},
                              "campos": campos})
        return apm_docs, tdd2_docs

    def _sincronizar(self, cont, nuevos: list[dict], tipos: set[str]) -> int:
        """Upsert de `nuevos` y borrado de los sobrantes de esos mismos `tipos`.

        Los documentos de otros tipos (p. ej. el contenido completo de los TDD)
        no se tocan: los escribe la carga de contenido, no el almacen.
        """
        ids_nuevos = {d["id"] for d in nuevos}
        for d in nuevos:
            cont.upsert_item(d)
        sobran = [(d["id"], d["id_habilitador"]) for d in cont.query_items(
            "SELECT c.id, c.id_habilitador, c.tipo FROM c", enable_cross_partition_query=True)
            if d["id"] not in ids_nuevos and d.get("tipo") in tipos]
        for _id, pk in sobran:
            cont.delete_item(_id, partition_key=pk)
        return len(nuevos)

    # ------------------------------------------------------------------
    # Contenido completo de un TDD Nivel 2 -> Cosmos (+ Blob)
    # ------------------------------------------------------------------

    def _servicio_blob(self):
        if not self._blob_endpoint:
            return None
        if self._blob is None:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient
            self._blob = BlobServiceClient(self._blob_endpoint,
                                           credential=DefaultAzureCredential())
        return self._blob

    def guardar_contenido_async(self, ruta, huella: str, numero: str,
                                id_habilitador: str) -> None:
        """Pone en la cola el guardado del contenido completo de este TDD Nivel 2."""
        pool = getattr(self, "_pool", None)
        if pool is not None:
            pool.submit(self._guardar_contenido_seguro, str(ruta), huella,
                        numero, id_habilitador)

    def _guardar_contenido_seguro(self, ruta, huella, numero, id_habilitador) -> None:
        try:
            r = self.guardar_contenido(ruta, huella, numero, id_habilitador)
            log.info("contenido TDD2 #%s: %s", numero, r)
        except Exception:                              # noqa: BLE001
            log.exception("no se pudo guardar el contenido del TDD Nivel 2 #%s", numero)

    @staticmethod
    def _tipo_imagen(nombre: str) -> str:
        ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "svg": "image/svg+xml", "emf": "image/x-emf",
                "wmf": "image/x-wmf"}.get(ext, "application/octet-stream")

    def guardar_contenido(self, ruta, huella: str, numero: str,
                          id_habilitador: str) -> dict:
        """Extrae el contenido completo del .docx y lo deja en Cosmos
        (tdd2/documentos, tipo "tdd2_contenido"); los diagramas y el original
        van a Blob. Es idempotente: si ese mismo archivo ya esta guardado con su
        original, no hace nada. Conserva lo que la IA ya hubiera descrito."""
        import hashlib
        ruta = Path(ruta)
        if not ruta.is_file():
            return {"omitido": "el archivo ya no existe"}
        datos = ruta.read_bytes()
        if hashlib.sha256(datos).hexdigest() != huella:
            return {"omitido": "el archivo cambio; lo procesa la siembra mas reciente"}

        pk = _pk(id_habilitador)
        doc_id = f"tdd2c-{huella}"
        blob = self._servicio_blob()
        try:
            previo = self._tdd2.read_item(doc_id, partition_key=pk)
        except Exception:                              # noqa: BLE001
            previo = None
        if previo and ((previo.get("archivo_original") or {}).get("blob") or blob is None):
            return {"omitido": "ya estaba guardado"}

        contenido, imgs = extraer_docx(ruta)
        nombre = ruta.name

        original = None
        if blob is not None:
            from azure.storage.blob import ContentSettings
            c_img = blob.get_container_client("imagenes-tdd")
            for n, b in imgs.items():
                c_img.upload_blob(f"{numero}/{n}", b, overwrite=True,
                                  content_settings=ContentSettings(
                                      content_type=self._tipo_imagen(n)))
            c_doc = blob.get_container_client("documentos")
            ruta_blob = f"tdd-nivel2/{numero}-{nombre}"
            c_doc.upload_blob(ruta_blob, datos, overwrite=True, content_settings=ContentSettings(
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
            original = f"documentos/{ruta_blob}"

        imagenes = [{"archivo": n, "bytes": len(b),
                     **({"blob": f"imagenes-tdd/{numero}/{n}"} if blob is not None else {})}
                    for n, b in imgs.items()]
        if blob is not None:
            for b in contenido["bloques"]:
                if b["tipo"] == "imagen" and b.get("archivo"):
                    b["blob"] = f"imagenes-tdd/{numero}/{b['archivo']}"

        # Versiones anteriores del TDD de este aplicativo: se conservan las
        # descripciones de diagramas y el analisis de la IA, y se retiran.
        anteriores = list(self._tdd2.query_items(
            "SELECT * FROM c WHERE c.tipo = 'tdd2_contenido' AND c.aplicativo.numero = @n",
            parameters=[{"name": "@n", "value": numero}],
            enable_cross_partition_query=True))
        analisis = None
        for a in anteriores:
            analisis = analisis or a.get("analisis_ia")
            por_archivo = {i["archivo"]: i for i in a.get("imagenes") or []}
            for im in imagenes:
                viejo = por_archivo.get(im["archivo"])
                if viejo and viejo.get("bytes") == im["bytes"]:
                    for k in ("descripcion_ia", "tipo_diagrama_ia", "descrito_en", "decorativa"):
                        if viejo.get(k) is not None and k not in im:
                            im[k] = viejo[k]

        doc = {
            "id": doc_id, "id_habilitador": pk, "tipo": "tdd2_contenido",
            "huella": huella, "nombre": nombre,
            "aplicativo": {"numero": numero, "id_habilitador": pk},
            "tdd2_id": f"tdd2-{huella}",
            "archivo_original": {"blob": original, "bytes": len(datos), "sha256": huella},
            "bloques": contenido["bloques"], "texto_plano": contenido["texto_plano"],
            "encabezados": contenido["encabezados"], "pies": contenido["pies"],
            "notas": contenido["notas"], "imagenes": imagenes,
            "estadisticas": contenido["estadisticas"], "analisis_ia": analisis,
            "guardado_en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        import json
        if len(json.dumps(doc, ensure_ascii=False).encode("utf-8")) > 1_900_000:
            doc["texto_plano"] = doc["texto_plano"][:200_000]
        with self._lock:
            self._tdd2.upsert_item(doc)
            for a in anteriores:
                if a["id"] != doc_id:
                    self._tdd2.delete_item(a["id"], partition_key=a["id_habilitador"])
        if self.al_cambiar_contenido:
            try:
                self.al_cambiar_contenido()
            except Exception:                          # noqa: BLE001
                pass
        return {"guardado": doc_id, "bloques": len(doc["bloques"]),
                "imagenes": len(imagenes), "original": bool(original)}

    def volcar(self, con) -> dict:
        """Deja Cosmos igual que las tablas locales (inserta, actualiza y borra)."""
        with self._lock:
            apm_docs, tdd2_docs = self._construir(con)
            n1 = self._sincronizar(self._apm, apm_docs, {d.get("tipo") for d in apm_docs} | _TIPOS_APM)
            n2 = self._sincronizar(self._tdd2, tdd2_docs, {"tdd2"})
        log.info("cosmos: %d documentos APM y %d TDD Nivel 2 guardados", n1, n2)
        return {"docs_apm": n1, "docs_tdd2": n2}
