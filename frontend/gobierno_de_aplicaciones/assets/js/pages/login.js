/* login.js -- pantalla de inicio de sesión del Portal APM TEC.
   Habla con la misma API del portal (/api/v1/auth/*). La sesión queda en una
   cookie HttpOnly que pone el servidor; aquí no se guarda ninguna contraseña. */
(function () {
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const PREFIJO = "/gobierno_de_aplicaciones";
  const AUTH = "/api/v1/auth";

  // Solo se vuelve a rutas internas del portal, nunca a direcciones externas.
  function destino() {
    const n = params.get("next") || "/";
    return PREFIJO + (n.startsWith("/") && !n.startsWith("//") ? n : "/");
  }

  function mostrarError(texto) { $("error").textContent = texto || ""; }

  function irACambio(actual) {
    $("form-login").hidden = true;
    $("form-cambio").hidden = false;
    if (actual) $("actual").value = actual;
    ($("actual").value ? $("nueva") : $("actual")).focus();
  }

  async function enviar(url, cuerpo) {
    const r = await fetch(url, { method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
    let datos = {};
    try { datos = await r.json(); } catch (e) { /* sin cuerpo */ }
    if (!r.ok) throw new Error(typeof datos.detail === "string" ? datos.detail : "Error " + r.status);
    return datos;
  }

  $("form-login").addEventListener("submit", async (e) => {
    e.preventDefault(); mostrarError("");
    const boton = e.target.querySelector("button"); boton.disabled = true;
    try {
      const r = await enviar(AUTH + "/login",
        { username: $("usuario").value.trim(), password: $("password").value });
      if (r.user && r.user.debe_cambiar_password) { irACambio($("password").value); return; }
      location.replace(destino());
    } catch (err) { mostrarError(err.message); } finally { boton.disabled = false; }
  });

  $("form-cambio").addEventListener("submit", async (e) => {
    e.preventDefault(); mostrarError("");
    if ($("nueva").value !== $("repetir").value) { mostrarError("Las contraseñas nuevas no coinciden."); return; }
    const boton = e.target.querySelector("button"); boton.disabled = true;
    try {
      await enviar(AUTH + "/cambiar-password",
        { password_actual: $("actual").value, password_nueva: $("nueva").value });
      location.replace(destino());
    } catch (err) { mostrarError(err.message); } finally { boton.disabled = false; }
  });

  if (params.get("cambiar") === "1") irACambio("");
  else $("usuario").focus();
})();
