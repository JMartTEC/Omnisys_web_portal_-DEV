(function () {
  const params = new URLSearchParams(location.search);
  if (params.get("expirada")) document.getElementById("expired").classList.remove("d-none");
  // Solo se vuelve a rutas internas (nunca a direcciones externas).
  function destino() {
    const n = params.get("next");
    return n && !n.includes("//") && !/^[a-z]+:/i.test(n) ? n : "portal.html";
  }
  if (window.GD_AUTH.isLogged()) location.replace(destino());
  // Modo demostración: el aviso solo aparece cuando no hay servidor configurado.
  if (window.GD_CONFIG.USE_MOCK) { const d = document.getElementById("demoBox"); if (d) d.hidden = false; }

  const form = document.getElementById("loginForm");
  const err = document.getElementById("err");
  const btn = document.getElementById("btnLogin");
  const cambio = document.getElementById("cambioForm");
  let tempToken = null, tempActual = null;

  cambio.onsubmit = async (e) => {
    e.preventDefault();
    err.classList.add("d-none");
    const n = document.getElementById("pwNueva").value;
    if (n !== document.getElementById("pwRepetir").value) {
      err.textContent = "Las contraseñas nuevas no coinciden."; err.classList.remove("d-none"); return;
    }
    const b = document.getElementById("btnCambio"); b.disabled = true;
    try {
      const res = await fetch(window.GD_CONFIG.API_BASE_URL + window.GD_CONFIG.API_PREFIX + "/auth/cambiar-password", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + tempToken },
        body: JSON.stringify({ password_actual: tempActual, password_nueva: n })
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Error " + res.status);
      window.GD_AUTH.guardar(d);
      location.href = destino();
    } catch (ex) {
      err.textContent = ex.message; err.classList.remove("d-none");
    } finally { b.disabled = false; }
  };

  document.getElementById("togglePw").onclick = function () {
    const p = document.getElementById("password");
    p.type = p.type === "password" ? "text" : "password";
    this.innerHTML = `<i class="bi bi-eye${p.type === "password" ? "" : "-slash"}"></i>`;
  };

  form.onsubmit = async (e) => {
    e.preventDefault();
    err.classList.add("d-none");
    const u = document.getElementById("username").value.trim();
    const p = document.getElementById("password").value;
    if (!u || !p) { err.textContent = "Captura usuario y contraseña."; err.classList.remove("d-none"); return; }
    btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Validando…';
    try {
      const r = await window.GD_API.login(u, p);
      if (r.user && r.user.debe_cambiar_password) {
        // Contraseña temporal: se cambia aquí mismo (misma pantalla), sin otra pantalla de login.
        tempToken = r.access_token; tempActual = p;
        form.hidden = true; cambio.hidden = false;
        document.getElementById("pwNueva").focus();
        return;
      }
      window.GD_AUTH.guardar(r);
      location.href = destino();
    } catch (ex) {
      err.textContent = ex.message; err.classList.remove("d-none");
    } finally {
      btn.disabled = false; btn.textContent = "Ingresar";
    }
  };
})();
