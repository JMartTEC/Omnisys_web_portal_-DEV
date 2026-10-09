"""Guardado del contenido completo de un TDD Nivel 2 en la nube (Cosmos + Blob de mentira)."""
import hashlib
import threading
import zipfile

from app.gobierno_de_aplicaciones.services import extractor_docx
from app.gobierno_de_aplicaciones.services.contenido_tdd2 import ContenidoTdd2
from app.gobierno_de_aplicaciones.services.persistencia_cosmos import PersistenciaCosmos

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ' \
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' \
    'xmlns:v="urn:schemas-microsoft-com:vml"'
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0"
       b"\x00\x00\x00\x00IEND\xaeB`\x82")


def hacer_docx(ruta):
    doc = (f'<w:document {W}><w:body>'
           '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>5. Integraciones</w:t></w:r></w:p>'
           '<w:p><w:r><w:t>Se integra con Banner.</w:t></w:r></w:p>'
           '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Campo</w:t></w:r></w:p></w:tc>'
           '<w:tc><w:p><w:r><w:t>Valor</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
           # Word guarda el dibujo dos veces (DrawingML + respaldo VML): cuenta como UNO
           '<w:p><w:r><a:blip r:embed="rId1"/></w:r><w:r><v:imagedata r:id="rId1"/></w:r></w:p>'
           '</w:body></w:document>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="x" Target="media/image1.png"/></Relationships>')
    with zipfile.ZipFile(ruta, "w") as z:
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", rels)
        z.writestr("word/media/image1.png", PNG)


class ContenedorFalso:
    def __init__(self):
        self.docs = {}

    def read_item(self, _id, partition_key):
        return dict(self.docs[(_id, partition_key)])

    def upsert_item(self, d):
        self.docs[(d["id"], d["id_habilitador"])] = dict(d)

    def delete_item(self, _id, partition_key):
        self.docs.pop((_id, partition_key), None)

    def query_items(self, sql, parameters=None, enable_cross_partition_query=False):
        n = (parameters or [{}])[0].get("value")
        return [dict(d) for d in self.docs.values()
                if d.get("tipo") == "tdd2_contenido" and d["aplicativo"]["numero"] == n]


class BlobFalso:
    def __init__(self):
        self.subidos = {}

    def get_container_client(self, nombre):
        s = self

        class C:
            def upload_blob(self, ruta, datos, overwrite=False, content_settings=None):
                s.subidos[f"{nombre}/{ruta}"] = datos
        return C()


def persistencia(tmp_blob=True):
    p = PersistenciaCosmos.__new__(PersistenciaCosmos)
    p._tdd2, p._lock = ContenedorFalso(), threading.Lock()
    p._blob_endpoint, p._blob, p._pool, p.al_cambiar_contenido = "x", BlobFalso(), None, None
    p._servicio_blob = lambda: p._blob if tmp_blob else None
    return p


def test_extractor_cuenta_un_dibujo_una_vez(tmp_path):
    ruta = tmp_path / "7.docx"
    hacer_docx(ruta)
    cont, imgs = extractor_docx.extraer_docx(ruta)
    assert [b["tipo"] for b in cont["bloques"]] == ["titulo", "parrafo", "tabla", "imagen"]
    assert cont["bloques"][-1]["archivo"] == "image1.png" and list(imgs) == ["image1.png"]


def test_guardar_contenido_en_cosmos_y_blob(tmp_path):
    ruta = tmp_path / "7.docx"
    hacer_docx(ruta)
    huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
    p = persistencia()
    avisos = []
    p.al_cambiar_contenido = lambda: avisos.append(1)

    r = p.guardar_contenido(ruta, huella, "7", "HAB-7")
    assert r["guardado"] == f"tdd2c-{huella}" and r["imagenes"] == 1 and r["original"]
    doc = p._tdd2.docs[(f"tdd2c-{huella}", "HAB-7")]
    assert doc["tipo"] == "tdd2_contenido" and doc["aplicativo"]["numero"] == "7"
    assert doc["bloques"][-1]["blob"] == "imagenes-tdd/7/image1.png"
    assert doc["archivo_original"]["blob"] == "documentos/tdd-nivel2/7-7.docx"
    assert set(p._blob.subidos) == {"imagenes-tdd/7/image1.png", "documentos/tdd-nivel2/7-7.docx"}
    assert avisos == [1]
    # volver a guardar el mismo archivo no repite el trabajo
    assert p.guardar_contenido(ruta, huella, "7", "HAB-7")["omitido"]


def test_nueva_version_conserva_lo_de_la_ia_y_retira_la_vieja(tmp_path):
    ruta = tmp_path / "7.docx"
    hacer_docx(ruta)
    h1 = hashlib.sha256(ruta.read_bytes()).hexdigest()
    p = persistencia()
    p.guardar_contenido(ruta, h1, "7", "HAB-7")
    viejo = p._tdd2.docs[(f"tdd2c-{h1}", "HAB-7")]
    viejo["imagenes"][0]["descripcion_ia"] = "Diagrama de Banner"
    viejo["analisis_ia"] = {"modelo": "x"}
    p._tdd2.upsert_item(viejo)

    hacer_docx(ruta)
    with zipfile.ZipFile(ruta, "a") as z:           # otro archivo => otra huella
        z.writestr("word/extra.txt", "cambio")
    h2 = hashlib.sha256(ruta.read_bytes()).hexdigest()
    p.guardar_contenido(ruta, h2, "7", "HAB-7")
    assert (f"tdd2c-{h1}", "HAB-7") not in p._tdd2.docs
    nuevo = p._tdd2.docs[(f"tdd2c-{h2}", "HAB-7")]
    assert nuevo["imagenes"][0]["descripcion_ia"] == "Diagrama de Banner"
    assert nuevo["analisis_ia"] == {"modelo": "x"}


def test_archivo_que_cambio_se_omite(tmp_path):
    ruta = tmp_path / "7.docx"
    hacer_docx(ruta)
    assert persistencia().guardar_contenido(ruta, "otra-huella", "7", "H")["omitido"]


def test_miniatura_reduce_la_imagen(tmp_path, monkeypatch):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1600, 900), "white").save(buf, "PNG")
    monkeypatch.setenv("CONTENIDO_TDD2_DIR", str(tmp_path))
    (tmp_path / "contenido").mkdir()
    (tmp_path / "imagenes" / "7").mkdir(parents=True)
    (tmp_path / "imagenes" / "7" / "a.png").write_bytes(buf.getvalue())
    (tmp_path / "contenido" / "7.docx.json").write_text(
        '{"id":"tdd2c-x7","nombre":"7.docx","aplicativo":{"numero":"7"},"bloques":[],"imagenes":[]}')
    s = ContenidoTdd2(None)
    datos, tipo = s.miniatura("tdd2c-x7", "a.png")
    assert tipo == "image/png" and Image.open(io.BytesIO(datos)).width == 360
