#!/usr/bin/env sh
# Build del Static Site en Render. Genera assets/js/env.js con las variables del servicio.
#   API_BASE_URL  URL completa del backend (https://gd-rag-api.onrender.com)
#   API_HOST      alternativa inyectada por render.yaml (fromService.property=host)
#   USE_MOCK      "true" para publicar sin backend
set -e
cd "$(dirname "$0")/.."

BASE="${API_BASE_URL:-}"
if [ -z "$BASE" ] && [ -n "${API_HOST:-}" ]; then
  BASE="https://${API_HOST}"
fi
MOCK="${USE_MOCK:-false}"
if [ -z "$BASE" ]; then MOCK="true"; fi

cat > assets/js/env.js <<EOF
// Generado en build: $(date -u +%Y-%m-%dT%H:%M:%SZ)
window.__GD_ENV__ = {
  API_BASE_URL: "${BASE}",
  USE_MOCK: ${MOCK},
  ENV_NAME: "${ENV_NAME:-render}"
};
EOF
echo "env.js -> API_BASE_URL=${BASE} USE_MOCK=${MOCK}"
