#!/usr/bin/env python3
"""
describir_diagramas_tdd2.py
---------------------------
Deja la base de IA lista con TEXTO de cada diagrama de los TDD Nivel 2: Claude
(vision) describe cada imagen guardada en Blob y la descripcion se guarda en el
documento `tdd2_contenido` de Cosmos (imagenes[].descripcion_ia). Con eso las
preguntas del portal tambien "ven" los diagramas.

Hace falta una llave de Claude en el entorno (no se escribe en ningun archivo):

    read -s -p "Llave: " ANTHROPIC_API_KEY; export ANTHROPIC_API_KEY; echo
    export AZURE_TOKEN_CREDENTIALS=AzureCliCredential
    python3 describir_diagramas_tdd2.py \\
        --cosmos https://<cuenta>.documents.azure.com:443/ \\
        --blob   https://<cuenta>.blob.core.windows.net/ [--solo-probar] [--rehacer]

Es idempotente: salta las imagenes que ya tienen descripcion (usa --rehacer para
repetirlas). --solo-probar describe una sola imagen y NO guarda nada.
Dependencias: azure-cosmos azure-identity azure-storage-blob anthropic
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

PROMPT = """Esta imagen es un diagrama o captura de un documento de descripcion tecnica (TDD)
de un aplicativo del Tecnologico de Monterrey. Devuelve SOLO un objeto JSON valido:
{"tipo_diagrama": "arquitectura|flujo|integracion|datos|infraestructura|organigrama|captura|otro",
 "elementos": "entidades que se leen en la imagen (cajas, sistemas, areas, roles), separadas por comas",
 "flujo": "una o dos frases: que se conecta con que y en que direccion",
 "descripcion": "3 a 6 frases en espanol que permitan a alguien que solo lee el texto entender
                 lo que muestra la imagen, usando los nombres que aparecen en ella"}
Si la imagen es decorativa (logo, linea, vineta) devuelve {"decorativa": true}. No inventes
nombres que no se lean en la imagen."""

TIPOS = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
         "gif": "image/gif", "webp": "image/webp"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cosmos", required=True)
    ap.add_argument("--blob", required=True)
    ap.add_argument("--db", default="tdd2")
    ap.add_argument("--contenedor", default="documentos")
    ap.add_argument("--modelo", default=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5"))
    ap.add_argument("--rehacer", action="store_true")
    ap.add_argument("--solo-probar", action="store_true")
    a = ap.parse_args()

    llave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not llave:
        print("Falta ANTHROPIC_API_KEY en el entorno (ver el encabezado de este archivo).")
        return 2

    import anthropic
    from azure.cosmos import CosmosClient
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobServiceClient

    cred = AzureCliCredential()
    cont = CosmosClient(a.cosmos, credential=cred).get_database_client(a.db) \
        .get_container_client(a.contenedor)
    blob = BlobServiceClient(a.blob, credential=cred)
    ws = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    cli = anthropic.Anthropic(api_key=llave, max_retries=2, timeout=120,
                              default_headers={"anthropic-workspace-id": ws} if ws else None)

    docs = list(cont.query_items("SELECT * FROM c WHERE c.tipo = 'tdd2_contenido'",
                                 enable_cross_partition_query=True))
    pendientes = sum(1 for d in docs for i in d.get("imagenes") or []
                     if a.rehacer or not i.get("descripcion_ia"))
    print(f"{len(docs)} documentos, {pendientes} imagenes por describir")
    hechas = fallas = 0
    for d in sorted(docs, key=lambda x: x["nombre"]):
        cambios = False
        for im in d.get("imagenes") or []:
            if im.get("descripcion_ia") and not a.rehacer:
                continue
            ext = im["archivo"].rsplit(".", 1)[-1].lower()
            if ext not in TIPOS:
                print(f"  salto {d['nombre']}/{im['archivo']}: formato {ext} no soportado")
                continue
            ruta = im.get("blob") or f"imagenes-tdd/{d['aplicativo']['numero']}/{im['archivo']}"
            c, _, n = ruta.partition("/")
            datos = blob.get_blob_client(c, n).download_blob().readall()
            if len(datos) > 5_000_000:
                print(f"  salto {d['nombre']}/{im['archivo']}: pesa {len(datos) // 1024} KB (>5 MB)")
                continue
            try:
                r = cli.messages.create(
                    model=a.modelo, max_tokens=900,
                    messages=[{"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": TIPOS[ext],
                                                     "data": base64.b64encode(datos).decode()}},
                        {"type": "text", "text": PROMPT}]}])
                texto = "".join(b.text for b in r.content if b.type == "text").strip()
                texto = texto[texto.find("{"): texto.rfind("}") + 1]
                res = json.loads(texto)
            except Exception as exc:                          # noqa: BLE001
                fallas += 1
                print(f"  FALLO {d['nombre']}/{im['archivo']}: {type(exc).__name__}: {str(exc)[:200]}")
                if fallas >= 5 and hechas == 0:
                    print("Demasiados fallos seguidos: reviso la llave/modelo y paro.")
                    return 1
                continue
            if a.solo_probar:
                print(json.dumps(res, ensure_ascii=False, indent=2))
                return 0
            if res.get("decorativa"):
                im["descripcion_ia"] = ""
                im["decorativa"] = True
            else:
                im["descripcion_ia"] = " ".join(x for x in (
                    res.get("descripcion", ""),
                    f"Elementos: {res['elementos']}." if res.get("elementos") else "",
                    f"Flujo: {res['flujo']}" if res.get("flujo") else "") if x)
                im["tipo_diagrama_ia"] = res.get("tipo_diagrama", "")
            im["descrito_en"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            cambios = True
            hechas += 1
            print(f"  ok {d['nombre']}/{im['archivo']} ({im.get('tipo_diagrama_ia', 'decorativa')})")
        if cambios:
            d["analisis_ia"] = {"diagramas_descritos": sum(1 for i in d["imagenes"]
                                                           if i.get("descripcion_ia")),
                                "modelo": a.modelo,
                                "en": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            cont.upsert_item(d)
    print(f"\nlisto: {hechas} descritas, {fallas} con error")
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
