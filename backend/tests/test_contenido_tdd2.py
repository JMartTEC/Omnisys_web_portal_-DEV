"""Contenido completo de los TDD Nivel 2: lectura, busqueda y preguntas (sin Azure)."""
import json

import pytest

from app.gobierno_de_aplicaciones.services.contenido_tdd2 import ContenidoTdd2


class ContenedorFalso:
    def __init__(self, docs):
        self.docs = docs

    def query_items(self, sql, enable_cross_partition_query=False):
        return [dict(d, _etag="x") for d in self.docs]


def doc(i, nombre, bloques):
    return {"id": f"tdd2c-h{i}", "id_habilitador": f"HAB-{i}", "tipo": "tdd2_contenido",
            "nombre": nombre, "aplicativo": {"numero": str(i), "nombre": nombre[:-5]},
            "archivo_original": {"blob": None}, "bloques": bloques,
            "imagenes": [{"archivo": "image1.png", "descripcion_ia": "Diagrama con Banner y SAP"}],
            "estadisticas": {"parrafos": 1, "tablas": 1, "imagenes": 1, "caracteres": 99},
            "texto_plano": "x"}


BLOQUES_PASE = [
    {"tipo": "titulo", "texto": "Base de datos", "estilo": "Ttulo1"},
    {"tipo": "tabla", "filas": [["Campo", "Valor"], ["Motor", "PostgreSQL 15"]]},
    {"tipo": "titulo", "texto": "Integraciones", "estilo": "Ttulo1"},
    {"tipo": "parrafo", "texto": "Se integra con Banner mediante servicios REST."},
    {"tipo": "imagen", "archivo": "image1.png"},
]
BLOQUES_VTEX = [
    {"tipo": "titulo", "texto": "Hospedaje", "estilo": "Ttulo1"},
    {"tipo": "parrafo", "texto": "Plataforma comercial en la nube de VTEX."},
]


@pytest.fixture
def servicio(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONTENIDO_TDD2_DIR", raising=False)
    return ContenidoTdd2(ContenedorFalso([doc(1, "PASE.docx", BLOQUES_PASE),
                                          doc(2, "VTEX.docx", BLOQUES_VTEX)]))


def test_lista_y_documento(servicio):
    filas = servicio.listar()
    assert [f["nombre"] for f in filas] == ["PASE.docx", "VTEX.docx"]
    assert filas[0]["numero"] == "1" and filas[0]["imagenes"] == 1
    d = servicio.obtener("tdd2c-h1")
    assert len(d["bloques"]) == 5 and "texto_plano" not in d and "_etag" not in d
    assert servicio.obtener("tdd2c-nada") is None


def test_busqueda_encuentra_la_seccion_correcta(servicio):
    r = servicio.buscar("¿qué base de datos usa PASE?")
    assert r and r[0]["doc"] == "tdd2c-h1" and r[0]["seccion"] == "Base de datos"
    r = servicio.buscar("nube hospedaje")
    assert r[0]["doc"] == "tdd2c-h2"
    # la descripcion del diagrama tambien se busca
    r = servicio.buscar("SAP")
    assert r and "Diagrama con Banner y SAP" in r[0]["texto"]


def test_preguntar_sin_llave_es_extractivo(servicio):
    r = servicio.preguntar("¿con qué se integra PASE?")
    assert r["modo"] == "extractivo" and r["fuentes"][0]["doc"] == "tdd2c-h1"
    r = servicio.preguntar("zzzz qqqq")
    assert r["modo"] == "sin_resultados"


def test_imagen_valida_la_ruta(servicio):
    assert servicio.imagen("tdd2c-h1", "../x.png") is None
    assert servicio.imagen("tdd2c-nada", "image1.png") is None


def test_carpeta_local(tmp_path, monkeypatch):
    (tmp_path / "contenido").mkdir()
    (tmp_path / "imagenes" / "PASE").mkdir(parents=True)
    (tmp_path / "imagenes" / "PASE" / "image1.png").write_bytes(b"\x89PNG")
    d = doc(1, "PASE.docx", BLOQUES_PASE)
    (tmp_path / "contenido" / "PASE.docx.json").write_text(json.dumps(d), encoding="utf-8")
    monkeypatch.setenv("CONTENIDO_TDD2_DIR", str(tmp_path))
    s = ContenidoTdd2(None)
    assert s.disponible() and len(s.listar()) == 1
    datos, tipo = s.imagen("tdd2c-h1", "image1.png")
    assert datos == b"\x89PNG" and tipo == "image/png"


def test_rutas_http(monkeypatch, tmp_path):
    """Las rutas nuevas existen y responden con el contenido (sin sesion -> 401)."""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/gobierno_de_aplicaciones/api/tdd2/contenido")
    assert r.status_code in (401, 403)
