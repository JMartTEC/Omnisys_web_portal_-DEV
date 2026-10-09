"""Extrae el CONTENIDO COMPLETO de los TDD Nivel 2 (.docx) y lo guarda en la nube.

Dos pasos (se pueden correr en maquinas distintas):

  1) extraer  -> lee los .docx y escribe un paquete local:
        <salida>/contenido/<nombre>.json     texto, tablas, orden de bloques y referencias a imagenes
        <salida>/imagenes/<nombre>/<img>     cada diagrama/imagen incrustada
     No necesita red ni dependencias (solo la biblioteca estandar).

  2) subir    -> toma ese paquete y lo deja en Azure:
        Blob  `imagenes-tdd`/<nombre>/<img>   las imagenes/diagramas
        Blob  `documentos`/tdd-nivel2/<nombre>.docx   los originales (si se pasa --originales)
        Cosmos tdd2/documentos: un documento tipo "tdd2_contenido" por TDD, ligado
        al aplicativo del APM (numero / id_habilitador) igual que el documento "tdd2".

Uso:
  python cargar_tdd2_contenido.py extraer --docx CARPETA --salida paquete
  python cargar_tdd2_contenido.py subir --salida paquete --cosmos URL --blob URL [--originales CARPETA]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import importlib.util

_ESP = importlib.util.spec_from_file_location(
    "extractor_docx", Path(__file__).resolve().parent.parent
    / "app" / "gobierno_de_aplicaciones" / "services" / "extractor_docx.py")
_MOD = importlib.util.module_from_spec(_ESP)
_ESP.loader.exec_module(_MOD)
extraer_docx = _MOD.extraer_docx


# ----------------------------------------------------------------------
def cmd_extraer(a):
    carpeta = Path(a.docx)
    salida = Path(a.salida)
    (salida / "contenido").mkdir(parents=True, exist_ok=True)
    docs = sorted(p for p in carpeta.glob("*.docx") if not p.name.startswith("~$"))
    tot_img = 0
    for p in docs:
        cont, imgs = extraer_docx(p)
        cont["nombre"] = p.name
        cont["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        cont["bytes_original"] = p.stat().st_size
        cont["imagenes"] = [{"archivo": n, "bytes": len(b)} for n, b in imgs.items()]
        (salida / "contenido" / f"{p.name}.json").write_text(
            json.dumps(cont, ensure_ascii=False), encoding="utf-8")
        if imgs:
            d = salida / "imagenes" / p.stem
            d.mkdir(parents=True, exist_ok=True)
            for n, b in imgs.items():
                (d / n).write_bytes(b)
        tot_img += len(imgs)
        e = cont["estadisticas"]
        print(f"{p.name:40s} parrafos={e['parrafos']:4d} tablas={e['tablas']:3d} "
              f"imagenes={e['imagenes']:3d} chars={e['caracteres']}")
    print(f"\n{len(docs)} documentos, {tot_img} imagenes -> {salida}")


def cmd_subir(a):
    from azure.cosmos import CosmosClient
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient, ContentSettings

    cred = AzureCliCredential()
    cos = CosmosClient(a.cosmos, credential=cred)
    cont_tdd2 = cos.get_database_client(a.db_tdd2).get_container_client(a.cont_tdd2)
    if a.llave_blob:
        blob = BlobServiceClient(a.blob, credential=a.llave_blob)
    else:
        blob = BlobServiceClient(a.blob, credential=cred)
    c_img = blob.get_container_client("imagenes-tdd")
    c_doc = blob.get_container_client("documentos")

    existentes = {d["nombre"]: d for d in cont_tdd2.query_items(
        "SELECT c.id, c.huella, c.nombre, c.numero, c.id_habilitador, c.campos_llenos, "
        "c.campos_totales FROM c WHERE c.tipo = 'tdd2'", enable_cross_partition_query=True)}
    print(f"{len(existentes)} documentos tdd2 en Cosmos")

    salida = Path(a.salida)
    originales = Path(a.originales) if a.originales else None
    ok = sin = 0
    for js in sorted((salida / "contenido").glob("*.json")):
        c = json.loads(js.read_text(encoding="utf-8"))
        nombre = c["nombre"]
        base = existentes.get(nombre)
        if not base:
            print(f"  SIN MATCH en tdd2: {nombre}")
            sin += 1
            continue
        stem = Path(nombre).stem
        # imagenes -> Blob
        for im in c["imagenes"]:
            ruta = salida / "imagenes" / stem / im["archivo"]
            ext = ruta.suffix.lower().lstrip(".") or "png"
            tipo = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "gif": "image/gif", "emf": "image/x-emf", "wmf": "image/x-wmf",
                    "svg": "image/svg+xml"}.get(ext, "application/octet-stream")
            ruta_blob = f"{base['numero']}/{im['archivo']}"
            c_img.upload_blob(ruta_blob, ruta.read_bytes(), overwrite=True,
                              content_settings=ContentSettings(content_type=tipo))
            im["blob"] = f"imagenes-tdd/{ruta_blob}"
        for b in c["bloques"]:
            if b["tipo"] == "imagen" and b.get("archivo"):
                b["blob"] = f"imagenes-tdd/{base['numero']}/{b['archivo']}"
        # original -> Blob
        original = None
        if originales and (originales / nombre).exists():
            ruta_blob = f"tdd-nivel2/{base['numero']}-{nombre}"
            with open(originales / nombre, "rb") as f:
                c_doc.upload_blob(ruta_blob, f, overwrite=True, content_settings=ContentSettings(
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
            original = f"documentos/{ruta_blob}"
        # Si el contenido ya estaba cargado, se conserva lo que agregaron otros
        # procesos (analisis y descripciones de la IA, el original ya subido):
        # volver a correr la carga NO debe borrarlos.
        previo = None
        try:
            previo = cont_tdd2.read_item(f"tdd2c-{base['huella']}",
                                         partition_key=base["id_habilitador"])
        except Exception:
            previo = None
        analisis_previo = previo.get("analisis_ia") if previo else None
        if previo:
            desc = {i["archivo"]: i for i in previo.get("imagenes") or []}
            for im in c["imagenes"]:
                for k in ("descripcion_ia", "tipo_diagrama_ia", "descrito_en"):
                    if desc.get(im["archivo"], {}).get(k):
                        im[k] = desc[im["archivo"]][k]
            if original is None:
                original = (previo.get("archivo_original") or {}).get("blob")
        doc = {
            "id": f"tdd2c-{base['huella']}",
            "id_habilitador": base["id_habilitador"],
            "tipo": "tdd2_contenido",
            "huella": base["huella"],
            "nombre": nombre,
            "aplicativo": {"numero": base["numero"], "id_habilitador": base["id_habilitador"]},
            "tdd2_id": base["id"],
            "archivo_original": {"blob": original, "bytes": c["bytes_original"], "sha256": c["sha256"]},
            "bloques": c["bloques"],
            "texto_plano": c["texto_plano"],
            "encabezados": c["encabezados"], "pies": c["pies"], "notas": c["notas"],
            "imagenes": c["imagenes"],
            "estadisticas": c["estadisticas"],
            "analisis_ia": analisis_previo,
        }
        peso = len(json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        if peso > 1_900_000:
            print(f"  {nombre}: {peso} bytes, se recorta texto_plano")
            doc["texto_plano"] = doc["texto_plano"][:200_000]
        cont_tdd2.upsert_item(doc)
        # el documento tdd2 apunta a su contenido
        ok += 1
        print(f"  ok {nombre} ({peso // 1024} KB, {len(c['imagenes'])} imagenes)")
    print(f"\nlisto: {ok} guardados, {sin} sin match")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extraer")
    e.add_argument("--docx", required=True)
    e.add_argument("--salida", required=True)
    s = sub.add_parser("subir")
    s.add_argument("--salida", required=True)
    s.add_argument("--cosmos", required=True)
    s.add_argument("--blob", required=True)
    s.add_argument("--llave-blob", default="")
    s.add_argument("--originales", default="")
    s.add_argument("--db-tdd2", default="tdd2")
    s.add_argument("--cont-tdd2", default="documentos")
    a = ap.parse_args()
    {"extraer": cmd_extraer, "subir": cmd_subir}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
