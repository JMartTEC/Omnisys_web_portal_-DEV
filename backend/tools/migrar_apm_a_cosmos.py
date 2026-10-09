"""Sube la base del Portal APM (almacen.db, SQLite) a las bases de Cosmos DB.

    apm   / habilitadores   APM (67 aplicativos), TDD V3, documentos leidos, decisiones
    tdd2  / documentos      TDD Nivel 2 (con cada campo y su confianza)

Las dos quedan separadas pero ligadas por el numero de aplicativo. Se puede
correr las veces que haga falta: deja Cosmos igual que el archivo.

Uso (con `az login` hecho y rol de datos en Cosmos):
    python migrar_apm_a_cosmos.py --db almacen.db --endpoint https://<cuenta>.documents.azure.com:443/
"""
import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _cargar_persistencia():
    for ruta in (AQUI / "persistencia_cosmos.py",
                 AQUI.parent / "app" / "gobierno_de_aplicaciones" / "services" / "persistencia_cosmos.py"):
        if ruta.exists():
            spec = importlib.util.spec_from_file_location("persistencia_cosmos", ruta)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    sys.exit("No encuentro persistencia_cosmos.py")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--endpoint", required=True)
    ap.add_argument("--llave", default="", help="vacio = az login / identidad administrada")
    a = ap.parse_args()
    mod = _cargar_persistencia()
    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    p = mod.PersistenciaCosmos(a.endpoint, a.llave)
    r = p.volcar(con)
    print(f"Listo: {r['docs_apm']} documentos en la base apm y {r['docs_tdd2']} en la base tdd2.")


if __name__ == "__main__":
    main()
