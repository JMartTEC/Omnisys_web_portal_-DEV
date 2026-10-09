#!/usr/bin/env bash
# Da de alta los usuarios del portal en la base Cosmos de UN ambiente.
# Las contraseñas temporales se imprimen UNA sola vez en esta consola (no se guardan en ningún archivo).
#
# Uso:  bash infra/scripts/crear-usuarios.sh <ambiente> <archivo-con-correos> <correo-admin>
#   ej: bash infra/scripts/crear-usuarios.sh dev usuarios.txt t-juansamperio@itesm.mx
# Requiere: az login (con rol de datos en Cosmos: lo da Bicep al operador) y Python 3.11.
set -euo pipefail
AMB="${1:?ambiente (dev|int|qa|pro)}"; ARCHIVO="${2:?archivo de correos}"; ADMIN="${3:?correo del administrador}"
ARCHIVO="$(realpath "$ARCHIVO")"
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
ENDPOINT=$(az deployment group show -g "rg-aptec-$AMB" -n "infra-$AMB" --query properties.outputs.endpointCosmos.value -o tsv)
cd "$RAIZ/backend"
AUTH_BACKEND=cosmos COSMOS_ENDPOINT="$ENDPOINT" ENV_NAME="$AMB" JWT_SECRET=solo-para-este-script \
  python -m tools.provision_usuarios "$ARCHIVO" --admin "$ADMIN" --gobierno aplicaciones
