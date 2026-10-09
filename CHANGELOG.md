# Historial de cambios del Portal APM TEC / GD 360

El portal usa numeración MAYOR.MENOR.PARCHE (por ejemplo 1.2.3):
MAYOR cuando algo deja de ser compatible, MENOR cuando se agrega una función, PARCHE cuando se corrige un error.
La versión vive en `backend/app/VERSION`, se publica en `/api/v1/version` y cada versión liberada lleva su etiqueta de git (`v1.0.0`).

## 1.1.0
- Los datos del Portal APM se guardan en Cosmos DB (bases APM y TDD Nivel 2 separadas y ligadas por aplicativo).
- Pantalla «Contenido TDD Nivel 2»: texto, tablas, campos con su confianza y diagramas en miniatura (se amplían con flechas), con descarga del documento original.
- Al sembrar o guardar un TDD Nivel 2 se guarda también su contenido completo y sus diagramas (Cosmos y Blob), en segundo plano.
- Preguntas sobre el contenido de los TDD: fragmentos más cercanos; con llave de Claude, respuesta redactada con ellos.

## 1.0.0
- Login con usuarios en base de datos (contraseñas temporales con cambio obligatorio en el primer ingreso) y un solo administrador.
- Portal de Gobierno de Aplicaciones protegido por sesión.
- Despliegue en Azure por ambiente (DEV, INT, QA y PRO) con gateway, backend, front, Key Vault, Cosmos DB y Storage.
- Pipelines de integración y despliegue.
