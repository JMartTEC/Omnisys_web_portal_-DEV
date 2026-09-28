#!/usr/bin/env sh
# Regenera assets/js/mock-data.js a partir del catálogo del backend (fuente única).
# Uso (desde la raíz del repo):  sh frontend/scripts/sync-mock-data.sh
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/backend/app/data/catalogo.json"
DST="$ROOT/frontend/assets/js/mock-data.js"
{
  echo "// GENERADO por scripts/sync-mock-data.sh desde backend/app/data/catalogo.json. No editar a mano."
  printf "window.GD_MOCK_DATA = "
  cat "$SRC"
  echo ";"
} > "$DST"
echo "mock-data.js actualizado"
