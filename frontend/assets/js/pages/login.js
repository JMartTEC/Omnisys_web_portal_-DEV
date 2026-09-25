(function () {
  const params = new URLSearchParams(location.search);
  if (params.get("expirada")) document.getElementById("expired").classList.remove("d-none");
  if (window.GD_AUTH.isLogged()) location.replace(params.get("next") || "portal.html");

  const form = document.getElementById("loginForm");
  const err = document.getElementById("err");
  const btn = document.getElementById("btnLogin");

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
      await window.GD_AUTH.login(u, p);
      const next = params.get("next");
      location.href = next && !next.includes("//") ? next : "portal.html";
    } catch (ex) {
      err.textContent = ex.message; err.classList.remove("d-none");
    } finally {
      btn.disabled = false; btn.textContent = "Ingresar";
    }
  };
})();
