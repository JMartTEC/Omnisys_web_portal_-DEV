using '../main.bicep'

param ambiente = 'pro'
param ubicacionFront = 'centralus'
param correoGateway = 'juan.samperio@omnisysmx.com'
// Los tres siguientes los pasa el pipeline (no se escriben aquí):
//   operadorObjectId, jwtSecret, llaveGateway
param operadorObjectId = readEnvironmentVariable('OPERADOR_OBJECT_ID')
param jwtSecret = readEnvironmentVariable('JWT_SECRET_NUEVO')
param llaveGateway = readEnvironmentVariable('LLAVE_GATEWAY_NUEVA')
