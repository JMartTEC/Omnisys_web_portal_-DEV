#!/usr/bin/env bash
# Prepara Azure y GitHub para que los pipelines puedan desplegar cada ambiente.
# Se corre UNA vez (es repetible: no duplica nada y NO regenera secretos ya creados).
#
# Requisitos: az (con "az login" hecho) y gh (con "gh auth login" hecho), en una terminal Bash.
#   az login --tenant <tu-tenant>        gh auth login
#
# Uso:
#   bash infra/scripts/configurar-identidad-pipeline.sh [repo] [region] [ambientes]
#   ejemplo: bash infra/scripts/configurar-identidad-pipeline.sh JMartTEC/Omnisys_web_portal_-DEV centralus "dev int qa pro"
#
# Qué hace:
#   1. Crea (si no existen) los grupos de recursos rg-aptec-<ambiente>.
#   2. Crea UNA identidad para los pipelines (app registration "gh-aptec-pipelines") con credencial
#      federada por ambiente: GitHub entra a Azure sin contraseñas.
#   3. Le da permisos SOLO sobre cada grupo de recursos (Contributor + User Access Administrator,
#      este último para que Bicep pueda asignar roles a la identidad del backend).
#   4. Crea los GitHub Environments y guarda variables y secretos. Los secretos (firma de sesión y
#      llave del gateway) se generan al azar y van directo a GitHub: NO se imprimen ni se guardan.
set -euo pipefail

REPO="${1:-JMartTEC/Omnisys_web_portal_-DEV}"
REGION="${2:-centralus}"
AMBIENTES="${3:-dev int qa pro}"
NOMBRE_APP="gh-aptec-pipelines"

command -v az >/dev/null || { echo "Falta Azure CLI (az)"; exit 1; }
command -v gh >/dev/null || { echo "Falta GitHub CLI (gh)"; exit 1; }
az account show >/dev/null 2>&1 || { echo "Corre primero: az login"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Corre primero: gh auth login"; exit 1; }

SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
OPERADOR_ID=$(az ad signed-in-user show --query id -o tsv)
echo "Suscripción: $SUB_ID  |  Repo: $REPO  |  Región: $REGION"

# 1) Proveedores de recursos que usa la plantilla (idempotente)
for p in Microsoft.KeyVault Microsoft.Storage Microsoft.DocumentDB Microsoft.Web Microsoft.ApiManagement Microsoft.Insights; do
  az provider register --namespace "$p" --wait >/dev/null
done

# 2) Identidad de los pipelines
APP_ID=$(az ad app list --display-name "$NOMBRE_APP" --query "[0].appId" -o tsv)
if [ -z "$APP_ID" ]; then
  APP_ID=$(az ad app create --display-name "$NOMBRE_APP" --query appId -o tsv)
  echo "Identidad creada."
fi
az ad sp show --id "$APP_ID" >/dev/null 2>&1 || az ad sp create --id "$APP_ID" >/dev/null
SP_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)

for AMB in $AMBIENTES; do
  GRUPO="rg-aptec-$AMB"
  echo "== $AMB =="
  az group create -n "$GRUPO" -l "$REGION" --tags proyecto=aptec ambiente="$AMB" >/dev/null
  ALCANCE="/subscriptions/$SUB_ID/resourceGroups/$GRUPO"

  # Credencial federada: solo el Environment de ESE ambiente puede entrar
  CRED="gh-$AMB"
  if [ -z "$(az ad app federated-credential list --id "$APP_ID" --query "[?name=='$CRED'].name" -o tsv)" ]; then
    az ad app federated-credential create --id "$APP_ID" --parameters "{
      \"name\": \"$CRED\",
      \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"repo:$REPO:environment:$AMB\",
      \"audiences\": [\"api://AzureADTokenExchange\"]}" >/dev/null
  fi

  # Permisos solo sobre el grupo de recursos del ambiente
  for ROL in "Contributor" "User Access Administrator"; do
    az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
      --role "$ROL" --scope "$ALCANCE" >/dev/null 2>&1 || true
  done

  # GitHub Environment + variables
  gh api -X PUT "repos/$REPO/environments/$AMB" >/dev/null
  gh variable set AZURE_CLIENT_ID --env "$AMB" --repo "$REPO" --body "$APP_ID"
  gh variable set AZURE_TENANT_ID --env "$AMB" --repo "$REPO" --body "$TENANT_ID"
  gh variable set AZURE_SUBSCRIPTION_ID --env "$AMB" --repo "$REPO" --body "$SUB_ID"
  gh variable set OPERADOR_OBJECT_ID --env "$AMB" --repo "$REPO" --body "$OPERADOR_ID"

  # Secretos: se generan solo si no existen (regenerarlos cerraría todas las sesiones)
  EXISTENTES=$(gh secret list --env "$AMB" --repo "$REPO" --json name -q '.[].name')
  for S in JWT_SECRET_NUEVO LLAVE_GATEWAY_NUEVA; do
    if ! echo "$EXISTENTES" | grep -qx "$S"; then
      openssl rand -base64 48 | tr -d '\n' | gh secret set "$S" --env "$AMB" --repo "$REPO"
    fi
  done
done

cat <<FIN

Listo. Falta (a mano, en GitHub > Settings > Environments):
  - En qa y pro: activar "Required reviewers" (tú) para que pidan aprobación antes de desplegar.
  - En pro: limitar "Deployment branches" a la rama main.
Después: sube el código a las ramas develop / int / release / main y los pipelines despliegan.
FIN
