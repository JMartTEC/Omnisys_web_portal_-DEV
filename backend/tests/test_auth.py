"""Login, cambio de contraseña temporal, administración de usuarios y protección del Portal APM."""
import secrets

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.main import app

from .conftest import PASSWORDS

ADMIN = "admin@prueba.mx"
EDITOR = "editor.apps@prueba.mx"


@pytest.fixture()
def client():
    security._fallos.clear()
    with TestClient(app) as c:
        yield c


def login(c, user, pw=None):
    return c.post("/api/v1/auth/login", json={"username": user, "password": pw or PASSWORDS[user]})


def test_no_hay_usuarios_ni_contrasenas_en_el_codigo():
    import pathlib
    fuente = (pathlib.Path(security.__file__)).read_text(encoding="utf-8")
    assert "HARDCODED" not in fuente and "GobDatos" not in fuente


def test_login_correcto_y_cookie(client):
    r = login(client, ADMIN)
    assert r.status_code == 200 and r.json()["user"]["rol"] == "admin"
    assert "httponly" in r.headers["set-cookie"].lower()


def test_login_no_distingue_usuario_inexistente(client):
    a = client.post("/api/v1/auth/login", json={"username": "nadie@prueba.mx", "password": "x"})
    b = client.post("/api/v1/auth/login", json={"username": ADMIN, "password": "x"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_bloqueo_por_intentos(client):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"username": EDITOR, "password": "mal"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": EDITOR, "password": "mal"}).status_code == 429
    assert login(client, EDITOR).status_code == 429  # ni la correcta pasa mientras dura el bloqueo


def test_solo_admin_administra_usuarios(client):
    h_ed = {"Authorization": "Bearer " + login(client, EDITOR).json()["access_token"]}
    assert client.get("/api/v1/usuarios", headers=h_ed).status_code == 403
    h_ad = {"Authorization": "Bearer " + login(client, ADMIN).json()["access_token"]}
    assert client.get("/api/v1/usuarios", headers=h_ad).status_code == 200


def test_alta_cambio_de_password_temporal(client):
    h_ad = {"Authorization": "Bearer " + login(client, ADMIN).json()["access_token"]}
    r = client.post("/api/v1/usuarios", headers=h_ad,
                    json={"username": "nuevo@prueba.mx", "nombre": "Nuevo", "gobierno": "aplicaciones", "rol": "editor"})
    assert r.status_code == 201
    temporal = r.json()["password_temporal"]
    assert len(temporal) >= 16

    r = login(client, "nuevo@prueba.mx", temporal)
    assert r.status_code == 200 and r.json()["user"]["debe_cambiar_password"] is True
    h = {"Authorization": "Bearer " + r.json()["access_token"]}
    # con contraseña temporal no se puede usar el portal...
    assert client.get("/api/v1/gobiernos", headers=h).status_code == 403
    # ...ni cambiarla por una débil o igual
    assert client.post("/api/v1/auth/cambiar-password", headers=h,
                       json={"password_actual": temporal, "password_nueva": "corta"}).status_code == 422
    assert client.post("/api/v1/auth/cambiar-password", headers=h,
                       json={"password_actual": temporal, "password_nueva": temporal}).status_code == 422
    nueva = secrets.token_urlsafe(14) + "aA1"
    r = client.post("/api/v1/auth/cambiar-password", headers=h,
                    json={"password_actual": temporal, "password_nueva": nueva})
    assert r.status_code == 200 and r.json()["user"]["debe_cambiar_password"] is False
    h2 = {"Authorization": "Bearer " + r.json()["access_token"]}
    assert client.get("/api/v1/gobiernos", headers=h2).status_code == 200
    assert login(client, "nuevo@prueba.mx", temporal).status_code == 401  # la temporal ya no sirve


def test_portal_apm_exige_sesion(client):
    base = "/gobierno_de_aplicaciones"
    # páginas -> redirigen al login; API -> 401
    r = client.get(base + "/", follow_redirects=False)
    assert r.status_code == 302 and "/gobierno_de_aplicaciones/login" in r.headers["location"]
    assert client.get(base + "/api/docs-referencia").status_code == 401
    assert client.get(base + "/api/referencia/descargar?tipo=apm").status_code == 401
    # libres: login y assets
    assert client.get(base + "/login").status_code == 200
    assert client.get(base + "/assets/js/pages/login.js").status_code == 200
    # con sesión (cookie) ya entra
    assert login(client, ADMIN).status_code == 200
    assert client.get(base + "/api/docs-referencia").status_code == 200
    assert client.get(base + "/", follow_redirects=False).status_code == 200


def test_un_solo_login_redirige_al_portal_gd360(client, monkeypatch):
    """Con SERVIR_FRONTEND=1 el login del APM desaparece: todo lleva a /index.html."""
    monkeypatch.setenv("SERVIR_FRONTEND", "1")
    base = "/gobierno_de_aplicaciones"
    r = client.get(base + "/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/index.html?next=")
    assert "gobierno_de_aplicaciones" in r.headers["location"]
    r = client.get(base + "/login?next=%2Fpantallas%2Fx", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/index.html?next=")
    assert "pantallas" in r.headers["location"]


def test_health_sigue_publico(client):
    assert client.get("/api/v1/health").status_code == 200


def test_backend_solo_acepta_llamadas_del_gateway(client):
    from app.core.config import get_settings
    s = get_settings()
    s.GATEWAY_KEY = secrets.token_urlsafe(24)
    try:
        assert client.post("/api/v1/auth/login", json={"username": ADMIN, "password": "x"}).status_code == 403
        assert client.get("/api/v1/health").status_code == 200  # la salud queda libre para Azure
        r = client.post("/api/v1/auth/login", json={"username": ADMIN, "password": PASSWORDS[ADMIN]},
                        headers={"X-Gateway-Key": s.GATEWAY_KEY})
        assert r.status_code == 200
    finally:
        s.GATEWAY_KEY = ""
