import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

from .conftest import PASSWORDS


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


ADMIN = "admin@prueba.mx"
EDITOR_INTEG = "editor.integracion@prueba.mx"


def token(client, user=ADMIN):
    r = client.post("/api/v1/auth/login", json={"username": user, "password": PASSWORDS[user]})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["fragmentos"] > 0


def test_login_invalido(client):
    assert client.post("/api/v1/auth/login", json={"username": ADMIN, "password": "x"}).status_code == 401


def test_requiere_token(client):
    assert client.get("/api/v1/gobiernos").status_code == 401


def test_secciones_de_gobierno(client):
    h = token(client)
    lista = client.get("/api/v1/gobiernos", headers=h).json()
    assert [g["id"] for g in lista] == ["datos", "integracion", "aplicaciones"]
    datos = client.get("/api/v1/gobiernos/datos", headers=h).json()
    assert datos["introduccion"] and len(datos["pilares"]) == 4
    assert {t["id"] for t in datos["temas"]} >= {"persona", "oferta", "ied"}
    assert datos["estadisticas"]["fragmentos"] > 0


def test_sin_fichas_de_dominio(client):
    h = token(client)
    assert client.get("/api/v1/activos", headers=h).status_code == 404


def test_query_con_fuentes(client):
    h = token(client)
    r = client.post("/api/v1/rag/query", headers=h, json={"pregunta": "¿Qué es el registro golden de la persona?", "gobierno": "datos"})
    body = r.json()
    assert r.status_code == 200
    assert body["fuentes"] and body["fuentes"][0]["dominio"] == "persona"


def test_ingesta_y_consulta(client):
    h = token(client, EDITOR_INTEG)
    contenido = ("Integración INT-042: Pulsar publica el evento de credencialización hacia Cypherlearning "
                 "mediante API REST cada vez que MDM confirma la identidad.").encode()
    r = client.post("/api/v1/ingesta/documentos", headers=h,
                    data={"gobierno": "integracion", "dominio": "inventario-integraciones", "clasificacion": "Interna"},
                    files={"archivo": ("inventario.txt", contenido, "text/plain")})
    assert r.status_code == 202, r.text
    doc_id = r.json()["id"]
    for _ in range(20):
        docs = client.get("/api/v1/ingesta/documentos?gobierno=integracion", headers=h).json()
        if next(d for d in docs if d["id"] == doc_id)["estado"] == "indexado":
            break
        time.sleep(0.1)
    q = client.post("/api/v1/rag/query", headers=h, json={"pregunta": "evento de credencialización Cypherlearning", "gobierno": "integracion"}).json()
    assert any(f["documento"] == "inventario.txt" for f in q["fuentes"])
    assert client.delete(f"/api/v1/ingesta/documentos/{doc_id}", headers=h).status_code == 200


def test_editor_no_carga_en_otro_gobierno(client):
    h = token(client, EDITOR_INTEG)
    r = client.post("/api/v1/ingesta/documentos", headers=h,
                    data={"gobierno": "datos", "dominio": "persona"},
                    files={"archivo": ("x.txt", b"hola mundo de datos", "text/plain")})
    assert r.status_code == 403


def test_formato_no_soportado(client):
    h = token(client)
    r = client.post("/api/v1/ingesta/documentos", headers=h, data={"gobierno": "datos", "dominio": "persona"},
                    files={"archivo": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_configurar_agente_remoto(client):
    h = token(client, "editor.apps@prueba.mx")
    r = client.put("/api/v1/gobiernos/aplicaciones/agente", headers=h, json={"modo": "remoto", "url": "https://ga-agent.example.com/"})
    assert r.status_code == 200 and r.json()["url"] == "https://ga-agent.example.com"
    assert client.put("/api/v1/gobiernos/datos/agente", headers=h, json={"modo": "local"}).status_code == 403
    client.put("/api/v1/gobiernos/aplicaciones/agente", headers=h, json={"modo": "local"})
