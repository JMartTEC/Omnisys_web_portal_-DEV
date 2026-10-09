"""
extractor_docx.py
-----------------
Lee un .docx (TDD Nivel 2) y devuelve su CONTENIDO COMPLETO: bloques en el orden
del documento (titulos, parrafos, listas, tablas, imagenes), texto plano para
busqueda, encabezados, pies, notas y los bytes de cada imagen/diagrama.

Solo usa la biblioteca estandar: lo usan la API (al sembrar o guardar un TDD
Nivel 2) y la herramienta `tools/cargar_tdd2_contenido.py`.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
V = "urn:schemas-microsoft-com:vml"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def _w(t):
    return f"{{{W}}}{t}"


def _texto_parrafo(p) -> str:
    partes = []
    for el in p.iter():
        if el.tag == _w("t") and el.text:
            partes.append(el.text)
        elif el.tag == _w("tab"):
            partes.append("\t")
        elif el.tag in (_w("br"), _w("cr")):
            partes.append("\n")
    return "".join(partes)


def _imagenes_parrafo(p, rels: dict[str, str]) -> list[dict]:
    out = []
    for el in p.iter():
        rid = None
        if el.tag == f"{{{A}}}blip":
            rid = el.get(f"{{{R}}}embed") or el.get(f"{{{R}}}link")
        elif el.tag == f"{{{V}}}imagedata":
            rid = el.get(f"{{{R}}}id")
        if rid and rid in rels:
            # Word guarda cada dibujo dos veces (DrawingML y su respaldo VML en
            # mc:AlternateContent): se cuenta una sola vez por imagen.
            if not any(o["ref"] == rels[rid] for o in out):
                out.append({"ref": rels[rid]})
    # descripcion (alt-text) de los dibujos
    alts = [e.get("descr") or e.get("title") or "" for e in p.iter(f"{{{WP}}}docPr")]
    for img, alt in zip(out, alts + [""] * len(out)):
        if alt:
            img["alt"] = alt
    return out


def _estilo(p) -> str:
    ppr = p.find(_w("pPr"))
    if ppr is not None:
        st = ppr.find(_w("pStyle"))
        if st is not None:
            return st.get(_w("val")) or ""
    return ""


def _es_lista(p) -> bool:
    ppr = p.find(_w("pPr"))
    return ppr is not None and ppr.find(_w("numPr")) is not None


def _celda(tc) -> str:
    return "\n".join(t for t in (_texto_parrafo(p) for p in tc.iter(_w("p"))) if t.strip())


def _bloques(body, rels) -> tuple[list[dict], list[str]]:
    bloques: list[dict] = []
    imagenes: list[str] = []
    for el in body:
        if el.tag == _w("p"):
            texto = _texto_parrafo(el).rstrip()
            imgs = _imagenes_parrafo(el, rels)
            if texto.strip():
                est = _estilo(el)
                tipo = ("titulo" if re.match(r"(?i)(heading|ttulo|titulo|title)", est)
                        else "lista" if _es_lista(el) else "parrafo")
                b = {"tipo": tipo, "texto": texto}
                if est:
                    b["estilo"] = est
                bloques.append(b)
            for im in imgs:
                bloques.append({"tipo": "imagen", **im})
                imagenes.append(im["ref"])
        elif el.tag == _w("tbl"):
            filas = []
            for tr in el.findall(_w("tr")):
                filas.append([_celda(tc) for tc in tr.findall(_w("tc"))])
            if any(any(c.strip() for c in f) for f in filas):
                bloques.append({"tipo": "tabla", "filas": filas})
            # imagenes dentro de tablas
            for p in el.iter(_w("p")):
                for im in _imagenes_parrafo(p, rels):
                    bloques.append({"tipo": "imagen", **im})
                    imagenes.append(im["ref"])
        elif el.tag == _w("sdt"):
            cont = el.find(_w("sdtContent"))
            if cont is not None:
                b, i = _bloques(cont, rels)
                bloques += b
                imagenes += i
    return bloques, imagenes


def _texto_xml(z: zipfile.ZipFile, nombre: str) -> str:
    if nombre not in z.namelist():
        return ""
    raiz = ET.fromstring(z.read(nombre))
    return "\n".join(t for t in (_texto_parrafo(p) for p in raiz.iter(_w("p"))) if t.strip())


def extraer_docx(ruta: Path) -> tuple[dict, dict[str, bytes]]:
    """Devuelve (contenido, {nombre_imagen: bytes})."""
    with zipfile.ZipFile(ruta) as z:
        rels = {}
        if "word/_rels/document.xml.rels" in z.namelist():
            for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
                rels[r.get("Id")] = r.get("Target")
        raiz = ET.fromstring(z.read("word/document.xml"))
        body = raiz.find(_w("body"))
        bloques, refs = _bloques(body, rels)

        imgs: dict[str, bytes] = {}
        vistos: dict[str, str] = {}
        for ref in dict.fromkeys(refs):
            interno = ref.lstrip("/")
            interno = interno if interno.startswith("word/") else "word/" + interno
            if interno in z.namelist():
                nom = Path(interno).name
                imgs[nom] = z.read(interno)
                vistos[ref] = nom
        for b in bloques:
            if b["tipo"] == "imagen":
                b["archivo"] = vistos.get(b.pop("ref"), "")

        extra = {
            "encabezados": [t for t in (_texto_xml(z, n) for n in sorted(z.namelist())
                                        if re.match(r"word/header\d*\.xml", n)) if t],
            "pies": [t for t in (_texto_xml(z, n) for n in sorted(z.namelist())
                                 if re.match(r"word/footer\d*\.xml", n)) if t],
            "notas": [t for t in (_texto_xml(z, n) for n in ("word/footnotes.xml", "word/endnotes.xml")) if t],
        }
    plano = []
    for b in bloques:
        if b["tipo"] == "tabla":
            plano += [" | ".join(f) for f in b["filas"]]
        elif b["tipo"] == "imagen":
            plano.append(f"[imagen: {b.get('archivo') or b.get('alt', '')}]")
        else:
            plano.append(b["texto"])
    contenido = {
        "bloques": bloques,
        "texto_plano": "\n".join(plano),
        **extra,
        "estadisticas": {
            "parrafos": sum(1 for b in bloques if b["tipo"] in ("parrafo", "lista", "titulo")),
            "tablas": sum(1 for b in bloques if b["tipo"] == "tabla"),
            "imagenes": sum(1 for b in bloques if b["tipo"] == "imagen"),
            "caracteres": len("\n".join(plano)),
        },
    }
    return contenido, imgs
