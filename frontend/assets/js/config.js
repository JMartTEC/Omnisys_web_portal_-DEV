// Configuración central del portal. Al migrar a Angular -> src/environments/environment.ts
(function () {
  const env = window.__GD_ENV__ || {};
  window.GD_CONFIG = {
    API_BASE_URL: (env.API_BASE_URL || "").replace(/\/$/, ""),
    API_PREFIX: "/api/v1",
    // Si no hay backend configurado se usa el modo MOCK automáticamente.
    USE_MOCK: env.USE_MOCK === true || !env.API_BASE_URL,
    ENV_NAME: env.ENV_NAME || "local",
    APP_NAME: "Portal GD 360",
    APP_SUBTITLE: "Gobierno de Datos VPAF",
    TOKEN_KEY: "gd_token",
    USER_KEY: "gd_user",
    // Gobiernos que exponen un agente RAG en el portal
    GOBIERNOS: [
      { id: "datos", nombre: "Gobierno de Datos", icono: "bi-database" },
      { id: "integracion", nombre: "Gobierno de Integración", icono: "bi-diagram-3" },
      { id: "aplicaciones", nombre: "Gobierno de Aplicaciones", icono: "bi-grid-1x2" }
    ]
  };
})();
