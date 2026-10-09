"""El almacen del APM respaldado en Cosmos (con un Cosmos de mentira en memoria)."""
import sqlite3

from app.gobierno_de_aplicaciones.services import almacen
from app.gobierno_de_aplicaciones.services.persistencia_cosmos import PersistenciaCosmos


class ContenedorFalso:
    def __init__(self):
        self.docs = {}

    def upsert_item(self, d):
        self.docs[(d["id"], d["id_habilitador"])] = dict(d)

    def delete_item(self, _id, partition_key):
        self.docs.pop((_id, partition_key), None)

    def query_items(self, sql, enable_cross_partition_query=False):
        return [dict(d) for d in self.docs.values()][:1 if "TOP 1" in sql else None]


def persistencia_falsa(apm=None, tdd2=None):
    p = PersistenciaCosmos.__new__(PersistenciaCosmos)
    import threading
    p._apm, p._tdd2, p._lock = apm or ContenedorFalso(), tdd2 or ContenedorFalso(), threading.Lock()
    return p


def sembrar(ruta):
    con = sqlite3.connect(ruta)
    con.execute("INSERT INTO aplicativos VALUES ('7','HAB-7','Banner',12,'t','apm.xlsx')")
    con.execute("INSERT INTO base_apm VALUES ('7','nombre','General','Nombre','Banner',1,'t')")
    con.execute("INSERT INTO base_apm VALUES ('7','rto','Continuidad','RTO','4h',0,'t')")
    con.execute("INSERT INTO base_tdd2 VALUES ('h1','r/TDD_Banner.docx','TDD_Banner.docx','7','HAB-7',1,2,50,'t')")
    con.execute("INSERT INTO base_tdd2_campos VALUES ('h1','1.1.a','1.1','Contexto','Objetivo','Cobrar','C2')")
    con.execute("INSERT INTO base_tdd2_campos VALUES ('h1','1.1.b','1.1','Contexto','Dueño','','C4')")
    con.execute("INSERT INTO documentos VALUES ('d1','x.docx','/x','archivo',10,'7','alta','ev','t',1)")
    con.execute("INSERT INTO hallazgos VALUES ('d1','rto','4h','pagina 2')")
    con.commit()
    con.close()


def tablas(ruta):
    con = sqlite3.connect(ruta)
    r = {t: sorted(map(tuple, con.execute(f"SELECT * FROM {t}")))
         for t in ("aplicativos", "base_apm", "base_tdd2", "base_tdd2_campos", "documentos", "hallazgos")}
    con.close()
    return r


def test_subir_y_volver_a_armar_desde_cosmos(tmp_path):
    p = persistencia_falsa()
    a = almacen.Almacen(tmp_path / "a", p)          # nube vacia -> nada que subir aun
    sembrar(a.ruta)
    with a._con() as con:
        p.volcar(con)
    # las dos bases quedan separadas pero ligadas
    apm = [d for d in p._apm.docs.values() if d["tipo"] == "aplicativo"][0]
    tdd2 = list(p._tdd2.docs.values())[0]
    assert apm["tdd_nivel2"][0]["id"] == tdd2["id"] and tdd2["aplicativo"]["id"] == apm["id"]
    assert tdd2["tipo"] == "tdd2" and len(tdd2["campos"]) == 2
    # una instalacion nueva, sin archivo local, queda igual leyendo de Cosmos
    b = almacen.Almacen(tmp_path / "b", p)
    assert tablas(b.ruta) == tablas(a.ruta)
    assert b.progreso_tdd2("7")[0] in ("naranja", "rojo", "verde", "gris")


def test_nube_vacia_sube_lo_local(tmp_path):
    p = persistencia_falsa()
    carpeta = tmp_path / "c"
    almacen.Almacen(carpeta, None)                  # crea el esquema sin nube
    sembrar(carpeta / "almacen.db")
    almacen.Almacen(carpeta, p)                     # primera vez con nube: sube
    assert len(p._apm.docs) >= 2 and len(p._tdd2.docs) == 1
