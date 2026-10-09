"""Da de alta los usuarios del portal con contraseña temporal.

Uso (desde la carpeta backend/):
    python -m tools.provision_usuarios usuarios.txt --admin correo.del.admin@dominio.mx

  usuarios.txt  un correo por línea (se ignoran repetidos y líneas vacías o con #)
  --admin       el único usuario con rol admin; los demás quedan como «editor»
  --restablecer vuelve a generar la contraseña temporal de los que ya existen

Las contraseñas temporales se IMPRIMEN UNA SOLA VEZ en pantalla: no se guardan en
ningún archivo ni en el repositorio. Cada usuario debe cambiarla al primer ingreso.
El destino lo marca AUTH_BACKEND (archivo | cosmos), igual que el portal.
"""
import argparse
import sys
from pathlib import Path

from app.core.usuarios import crear_usuario, get_almacen, normalizar


def nombre_desde_correo(correo: str) -> str:
    local = correo.split("@")[0]
    if local.startswith("t-"):
        local = local[2:]
    return local.replace(".", " ").replace("_", " ").title()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivo", help="txt con un correo por línea")
    ap.add_argument("--admin", required=True, help="correo del único administrador")
    ap.add_argument("--gobierno", default="aplicaciones")
    ap.add_argument("--restablecer", action="store_true")
    a = ap.parse_args(argv)

    correos, vistos = [], set()
    for linea in Path(a.archivo).read_text(encoding="utf-8").splitlines():
        c = normalizar(linea)
        if c and not c.startswith("#") and c not in vistos:
            vistos.add(c)
            correos.append(c)
    admin = normalizar(a.admin)
    if admin not in vistos:
        print(f"El administrador {admin} no está en la lista.", file=sys.stderr)
        return 2

    almacen = get_almacen()
    print(f"{'Usuario':42} {'Rol':8} Contraseña temporal")
    print("-" * 80)
    for c in correos:
        if almacen.obtener(c) and not a.restablecer:
            print(f"{c:42} {'--':8} (ya existía; no se cambió)")
            continue
        rol = "admin" if c == admin else "editor"
        _, pw = crear_usuario(almacen, c, nombre_desde_correo(c), a.gobierno, rol)
        print(f"{c:42} {rol:8} {pw}")
    print("\nGuárdalas ahora: no se vuelven a mostrar. Cada usuario las cambia al primer ingreso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
