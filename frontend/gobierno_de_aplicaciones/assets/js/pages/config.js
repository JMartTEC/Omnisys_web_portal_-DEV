/* =========================================================================
   config.js -- "Configuración del proveedor"
   La API key se escribe aquí pero NUNCA regresa del servidor: al recargar,
   el campo queda vacío con un marcador de que sí hay llave guardada.
   ========================================================================= */

function pintarConfig(c) {
  $("cfg-modo").innerHTML = c.modos.map((m) =>
    `<option value="${esc(m.valor)}"${m.valor === c.ai_modo ? " selected" : ""}>${esc(m.etiqueta)}</option>`).join("");

  $("cfg-modelo-claude").innerHTML = c.modelos_claude.map((m) =>
    `<option${m === c.anthropic_model ? " selected" : ""}>${esc(m)}</option>`).join("");

  $("cfg-workspace").value = c.anthropic_workspace_id || "";
  $("cfg-modelo-ollama").value = c.ollama_model || "";
  $("cfg-host").value = c.ollama_host || "";
  $("cfg-maxchars").value = c.ollama_max_chars || "";
  $("ruta-env").textContent = c.ruta_env || ".env";

  $("cfg-key").value = "";
  const marca = $("estado-llave");
  if (c.tiene_llave) {
    marca.textContent = `guardada · ${c.llave_enmascarada}`;
    marca.className = "etiqueta ok-chip";
    $("cfg-key").placeholder = "Déjalo vacío para conservar la actual";
  } else {
    marca.textContent = "sin llave";
    marca.className = "etiqueta aviso-chip";
    $("cfg-key").placeholder = "sk-ant-api03-...";
  }

  $("cfg-modelo-gemini").innerHTML = (c.modelos_gemini || []).map((m) =>
    `<option${m === c.gemini_model ? " selected" : ""}>${esc(m)}</option>`).join("");

  $("cfg-key-gemini").value = "";
  const marcaGemini = $("estado-llave-gemini");
  if (c.tiene_llave_gemini) {
    marcaGemini.textContent = `guardada · ${c.llave_gemini_enmascarada}`;
    marcaGemini.className = "etiqueta ok-chip";
    $("cfg-key-gemini").placeholder = "Déjalo vacío para conservar la actual";
  } else {
    marcaGemini.textContent = "sin llave";
    marcaGemini.className = "etiqueta aviso-chip";
    $("cfg-key-gemini").placeholder = "AIza...";
  }

  alternarGrupos();
}

function alternarGrupos() {
  const modo = $("cfg-modo").value;
  const auto = modo === "";
  const usaClaude = modo === "claude" || auto;
  const usaGemini = modo === "gemini" || auto;
  const usaLocal = modo === "local" || auto;
  $("grupo-claude").classList.toggle("apagado", !usaClaude);
  $("grupo-gemini").classList.toggle("apagado", !usaGemini);
  $("grupo-ollama").classList.toggle("apagado", !usaLocal);
}

$("cfg-modo").addEventListener("change", alternarGrupos);

function mensajeConfig(texto, esError) {
  $("config-ok").hidden = esError || !texto;
  $("config-error").hidden = !esError || !texto;
  ($(esError ? "config-error" : "config-ok")).textContent = texto || "";
}

function cuerpoConfig() {
  return {
    ai_modo: $("cfg-modo").value,
    anthropic_api_key: $("cfg-key").value,
    anthropic_workspace_id: $("cfg-workspace").value,
    anthropic_model: $("cfg-modelo-claude").value,
    gemini_api_key: $("cfg-key-gemini").value,
    gemini_model: $("cfg-modelo-gemini").value,
    ollama_model: $("cfg-modelo-ollama").value,
    ollama_host: $("cfg-host").value,
    ollama_max_chars: $("cfg-maxchars").value,
  };
}

$("btn-guardar-config").addEventListener("click", async () => {
  mensajeConfig("", false);
  const btn = $("btn-guardar-config");
  btn.disabled = true;
  try {
    const r = await pedir("/gobierno_de_aplicaciones/api/config", json(cuerpoConfig()));
    guardarEstadoIA(null);
    Estado.set("avisoInicio", r.cambios.length
      ? `Configuracion guardada. Proveedor activo: ${r.proveedor_activo}.`
      : "Sin cambios que guardar.");
    location.href = "/gobierno_de_aplicaciones/";
  } catch (e) {
    mensajeConfig(e.message, true);
    btn.disabled = false;
  }
});

$("btn-probar-config").addEventListener("click", async () => {
  mensajeConfig("Probando…", false);
  const btn = $("btn-probar-config");
  btn.disabled = true;
  try {
    const r = await pedir("/gobierno_de_aplicaciones/api/config/probar", json({ proveedor: $("cfg-modo").value }));
    mensajeConfig(`${r.ok ? "✓" : "✗"} ${r.mensaje}`, !r.ok);
    guardarEstadoIA(null);
  } catch (e) {
    mensajeConfig(e.message, true);
  } finally {
    btn.disabled = false;
  }
});

$("btn-borrar-llave").addEventListener("click", async () => {
  mensajeConfig("", false);
  try {
    const r = await pedir("/gobierno_de_aplicaciones/api/config/borrar-llave", { method: "POST" });
    pintarConfig(r.estado);
    guardarEstadoIA(null);
    mensajeConfig("La llave se eliminó del .env.", false);
  } catch (e) {
    mensajeConfig(e.message, true);
  }
});

$("btn-borrar-llave-gemini").addEventListener("click", async () => {
  mensajeConfig("", false);
  try {
    const r = await pedir("/gobierno_de_aplicaciones/api/config/borrar-llave-gemini", { method: "POST" });
    pintarConfig(r.estado);
    guardarEstadoIA(null);
    mensajeConfig("La llave de Gemini se eliminó del .env.", false);
  } catch (e) {
    mensajeConfig(e.message, true);
  }
});

(async () => {
  try {
    pintarConfig(await pedir("/gobierno_de_aplicaciones/api/config"));
  } catch (e) {
    mensajeConfig(e.message, true);
  }
})();
