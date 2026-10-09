// Infraestructura del Portal APM TEC / GD 360 para UN ambiente (dev | int | qa | pro).
// Se despliega en un grupo de recursos por ambiente:  rg-aptec-<ambiente>
//
// Lo que crea:
//   Key Vault ......... llaves y secretos (nada va en el código ni en el repositorio)
//   Storage ........... documentos originales e imágenes de los TDD (contenedores privados)
//   Cosmos DB ......... bases «seguridad», «apm» y «tdd2» (misma cuenta, separadas por base)
//   App Service ....... backend (FastAPI) con identidad administrada: entra a Cosmos, Storage y
//                       Key Vault SIN contraseñas
//   Static Web Apps ... frontend del Portal GD 360
//   API Management .... gateway de entrada (plan Consumo); el backend solo acepta llamadas que
//                       traen la llave del gateway
targetScope = 'resourceGroup'

@allowed(['dev', 'int', 'qa', 'pro'])
@description('Ambiente que se despliega.')
param ambiente string

param ubicacion string = resourceGroup().location

@description('Ubicación de Static Web Apps (solo acepta algunas regiones).')
@allowed(['westus2', 'centralus', 'eastus2', 'westeurope', 'eastasia'])
param ubicacionFront string = 'eastus2'

@minLength(2)
@maxLength(8)
param prefijo string = 'aptec'

@description('Correo de contacto del gateway (API Management).')
param correoGateway string

@description('ID de objeto (Entra ID) de la persona o identidad que opera el ambiente: administra Key Vault y da de alta usuarios en Cosmos.')
param operadorObjectId string

@secure()
@description('Secreto de firma de sesiones. Lo genera el pipeline; si ya existe en Key Vault se reutiliza el mismo.')
param jwtSecret string

@secure()
@description('Llave que el gateway manda al backend para que este rechace llamadas directas.')
param llaveGateway string

// ----------------------------------------------------------------------------------------------
// Perfil por ambiente: DEV e INT en planes gratis o mínimos; QA y PRO con plan que no se duerme.
var perfiles = {
  dev: { planSku: 'F1', planTier: 'Free', purga: false, replicacion: 'Standard_LRS' }
  int: { planSku: 'F1', planTier: 'Free', purga: false, replicacion: 'Standard_LRS' }
  qa: { planSku: 'F1', planTier: 'Free', purga: false, replicacion: 'Standard_LRS' }
  pro: { planSku: 'F1', planTier: 'Free', purga: true, replicacion: 'Standard_LRS' }
}
var perfil = perfiles[ambiente]
var sufijo = take(uniqueString(subscription().subscriptionId, resourceGroup().id), 5)
var base = '${prefijo}-${ambiente}'
var baseCorta = '${prefijo}${ambiente}${sufijo}'

var rolSecretosKv = '4633458b-17de-408a-b874-0445c86b69e6' // Key Vault Secrets User
var rolAdminKv = '00482a5a-887f-4fb3-b363-3b7fe8e74483' // Key Vault Administrator
var rolBlobContribuidor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // Storage Blob Data Contributor
var rolCosmosDatos = '00000000-0000-0000-0000-000000000002' // Cosmos DB Built-in Data Contributor

var etiquetas = {
  proyecto: 'portal-apm-tec'
  ambiente: ambiente
  administradoPor: 'bicep'
}

// ----------------------------------------------------------------------------------------------
// Key Vault
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('kv-${baseCorta}', 24)
  location: ubicacion
  tags: etiquetas
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    enablePurgeProtection: perfil.purga ? true : null
    publicNetworkAccess: 'Enabled'
  }
}

resource secretoJwt 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'jwt-secret'
  properties: { value: jwtSecret }
}

resource secretoGateway 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: kv
  name: 'llave-gateway'
  properties: { value: llaveGateway }
}

resource rolOperadorKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, operadorObjectId, rolAdminKv)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolAdminKv)
    principalId: operadorObjectId
  }
}

// ----------------------------------------------------------------------------------------------
// Storage (documentos e imágenes)
resource almacenamiento 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${baseCorta}', 24)
  location: ubicacion
  tags: etiquetas
  kind: 'StorageV2'
  sku: { name: perfil.replicacion }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: almacenamiento
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 14 }
  }
}

resource contenedoresBlob 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for nombre in ['documentos', 'imagenes-tdd']: {
  parent: blobs
  name: nombre
  properties: { publicAccess: 'None' }
}]

// ----------------------------------------------------------------------------------------------
// Cosmos DB: una cuenta, tres bases separadas (seguridad | apm | tdd2), llave común: id_habilitador
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: take('cosmos-${baseCorta}', 44)
  location: ubicacion
  tags: etiquetas
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [{ name: 'EnableServerless' }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: ubicacion, failoverPriority: 0, isZoneRedundant: false }]
    disableLocalAuth: true // solo identidad (Entra ID); sin llaves de la cuenta
    minimalTlsVersion: 'Tls12'
    backupPolicy: { type: 'Continuous', continuousModeProperties: { tier: 'Continuous7Days' } }
  }
}

var basesCosmos = [
  { nombre: 'seguridad', contenedor: 'usuarios', llave: '/id' }
  { nombre: 'apm', contenedor: 'habilitadores', llave: '/id_habilitador' }
  { nombre: 'tdd2', contenedor: 'documentos', llave: '/id_habilitador' }
]

resource dbsCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = [for b in basesCosmos: {
  parent: cosmos
  name: b.nombre
  properties: { resource: { id: b.nombre } }
}]

resource contenedoresCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = [for (b, i) in basesCosmos: {
  parent: dbsCosmos[i]
  name: b.contenedor
  properties: {
    resource: {
      id: b.contenedor
      partitionKey: { paths: [b.llave], kind: 'Hash' }
    }
  }
}]

resource rolCosmosOperador 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, operadorObjectId, rolCosmosDatos)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${rolCosmosDatos}'
    principalId: operadorObjectId
    scope: cosmos.id
  }
}

// ----------------------------------------------------------------------------------------------
// Front (Static Web Apps)
resource front 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'swa-${base}-${sufijo}'
  location: ubicacionFront
  tags: etiquetas
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// ----------------------------------------------------------------------------------------------
// Backend (App Service Linux + identidad administrada)
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-${base}'
  location: ubicacion
  tags: etiquetas
  kind: 'linux'
  sku: { name: perfil.planSku, tier: perfil.planTier }
  properties: { reserved: true }
}

resource backend 'Microsoft.Web/sites@2023-12-01' = {
  name: 'app-${base}-${sufijo}'
  location: ubicacion
  tags: etiquetas
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      alwaysOn: perfil.planSku != 'F1'
      healthCheckPath: '/api/v1/health'
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'ENV_NAME', value: ambiente }
        { name: 'AUTH_BACKEND', value: 'cosmos' }
        { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DB_SEGURIDAD', value: 'seguridad' }
        { name: 'COSMOS_CONTENEDOR_USUARIOS', value: 'usuarios' }
        { name: 'APM_PERSISTENCIA', value: 'cosmos' }
        { name: 'APM_DATOS_DIR', value: '/tmp/apm-datos' }
        { name: 'COSMOS_DB_APM', value: 'apm' }
        { name: 'COSMOS_CONTENEDOR_APM', value: 'habilitadores' }
        { name: 'COSMOS_DB_TDD2', value: 'tdd2' }
        { name: 'COSMOS_CONTENEDOR_TDD2', value: 'documentos' }
        { name: 'SERVIR_FRONTEND', value: '1' }
        { name: 'STORAGE_ENDPOINT', value: almacenamiento.properties.primaryEndpoints.blob }
        { name: 'COOKIE_SEGURA', value: 'true' }
        { name: 'CORS_ORIGINS', value: 'https://${front.properties.defaultHostname}' }
        { name: 'PORTAL_GD360_URL', value: 'https://${front.properties.defaultHostname}' }
        { name: 'JWT_SECRET', value: '@Microsoft.KeyVault(SecretUri=${kv.properties.vaultUri}secrets/jwt-secret/)' }
        { name: 'GATEWAY_KEY', value: '@Microsoft.KeyVault(SecretUri=${kv.properties.vaultUri}secrets/llave-gateway/)' }
      ]
    }
  }
}

resource rolBackendKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, backend.id, rolSecretosKv)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolSecretosKv)
    principalId: backend.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource rolBackendBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: almacenamiento
  name: guid(almacenamiento.id, backend.id, rolBlobContribuidor)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', rolBlobContribuidor)
    principalId: backend.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource rolBackendCosmos 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmos
  name: guid(cosmos.id, backend.id, rolCosmosDatos)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${rolCosmosDatos}'
    principalId: backend.identity.principalId
    scope: cosmos.id
  }
}

// ----------------------------------------------------------------------------------------------
// Gateway (API Management, plan Consumo): entrada única hacia el backend
resource gateway 'Microsoft.ApiManagement/service@2022-08-01' = {
  name: 'apim-${base}-${sufijo}'
  location: ubicacion
  tags: etiquetas
  sku: { name: 'Consumption', capacity: 0 }
  properties: {
    publisherEmail: correoGateway
    publisherName: 'Portal APM TEC'
  }
}

resource valorLlave 'Microsoft.ApiManagement/service/namedValues@2022-08-01' = {
  parent: gateway
  name: 'llave-gateway'
  properties: {
    displayName: 'llave-gateway'
    secret: true
    value: llaveGateway
  }
}

resource apiPortal 'Microsoft.ApiManagement/service/apis@2022-08-01' = {
  parent: gateway
  name: 'portal'
  properties: {
    displayName: 'Portal APM TEC'
    path: ''
    protocols: ['https']
    serviceUrl: 'https://${backend.properties.defaultHostName}'
    subscriptionRequired: false // la autenticación la hace el portal (login con sesión)
  }
}

resource operaciones 'Microsoft.ApiManagement/service/apis/operations@2022-08-01' = [for metodo in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']: {
  parent: apiPortal
  name: 'todo-${toLower(metodo)}'
  properties: {
    displayName: 'Todo (${metodo})'
    method: metodo
    urlTemplate: '/*'
  }
}]

var plantillaPolitica = '''
<policies>
  <inbound>
    <cors allow-credentials="false">
      <allowed-origins><origin>__FRONT__</origin><origin>__GATEWAY__</origin></allowed-origins>
      <allowed-methods><method>*</method></allowed-methods>
      <allowed-headers><header>*</header></allowed-headers>
    </cors>
    <base />
    <set-header name="X-Gateway-Key" exists-action="override">
      <value>{{llave-gateway}}</value>
    </set-header>
  </inbound>
  <backend><base /></backend>
  <outbound><base /></outbound>
  <on-error><base /></on-error>
</policies>
'''

resource politicaApi 'Microsoft.ApiManagement/service/apis/policies@2022-08-01' = {
  parent: apiPortal
  name: 'policy'
  dependsOn: [valorLlave]
  properties: {
    format: 'rawxml'
    value: replace(replace(plantillaPolitica, '__FRONT__', 'https://${front.properties.defaultHostname}'), '__GATEWAY__', 'https://${gateway.name}.azure-api.net')
  }
}

// ----------------------------------------------------------------------------------------------
output urlGateway string = gateway.properties.gatewayUrl
output urlBackendDirecta string = 'https://${backend.properties.defaultHostName}'
output urlFront string = 'https://${front.properties.defaultHostname}'
output nombreBackend string = backend.name
output nombreFront string = front.name
output nombreKeyVault string = kv.name
output nombreCosmos string = cosmos.name
output endpointCosmos string = cosmos.properties.documentEndpoint
output nombreStorage string = almacenamiento.name
