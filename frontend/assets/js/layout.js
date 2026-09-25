// Layout compartido: navbar, anuncio, asistente flotante, footer y componente de chat.
// Angular -> HeaderComponent, AssistantTabComponent, ChatComponent (standalone).
(function () {
  const C = window.GD_CONFIG;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const initials = (n) => (n || "?").split(/\s+/).map((w) => w[0]).slice(0, 2).join("").toUpperCase();
  const gobName = (id) => (C.GOBIERNOS.find((g) => g.id === id) || { nombre: id }).nombre;
  window.GD_UTIL = { esc, md, initials, gobName };

  function header(active) {
    const u = window.GD_AUTH.user() || {};
    const link = (href, key, label) => `<li class="nav-item"><a class="nav-link ${active === key ? "active" : ""}" href="${href}">${label}</a></li>`;
    return `
    <nav class="navbar navbar-expand-xl gd-navbar sticky-top py-2">
      <div class="container-fluid px-3 px-lg-4">
        <a class="navbar-brand me-xl-4" href="portal.html">${C.APP_NAME}<small>${C.APP_SUBTITLE}</small></a>
        <button class="navbar-toggler border-0" type="button" data-bs-toggle="collapse" data-bs-target="#gdNav" aria-label="Menú"><i class="bi bi-list fs-2"></i></button>
        <div class="collapse navbar-collapse" id="gdNav">
          <ul class="navbar-nav me-auto">
            ${link("portal.html", "inicio", "Inicio")}
            ${C.GOBIERNOS.map((g) => link("gobierno.html?id=" + g.id, g.id, g.nombre)).join("")}
            ${link("carga.html", "espacio", "Mi espacio")}
          </ul>
          <div class="d-flex align-items-center gap-2 gap-lg-3 py-2 py-xl-0">
            ${C.USE_MOCK ? '<span class="gd-mock-badge" title="Datos de ejemplo, sin backend">MODO DEMO</span>' : ""}
            <button class="gd-icon-btn" title="Notificaciones"><i class="bi bi-bell-fill"></i><span class="gd-dot">2</span></button>
            <div class="dropdown">
              <button class="btn p-0 border-0 d-flex align-items-center gap-2" data-bs-toggle="dropdown" aria-expanded="false">
                <span class="gd-avatar">${initials(u.nombre)}</span>
                <span class="d-none d-xl-inline text-start small lh-sm"><span class="fw-500 d-block">${esc(u.nombre)}</span><span class="text-muted-gd">${esc(gobName(u.gobierno))}</span></span>
              </button>
              <ul class="dropdown-menu dropdown-menu-end shadow border-0 rounded-4 p-2">
                <li class="px-3 py-2 small"><div class="fw-600">${esc(u.username)}</div><div class="text-muted-gd">${esc(gobName(u.gobierno))} · ${esc(u.rol)}</div></li>
                <li><hr class="dropdown-divider"></li>
                <li><a class="dropdown-item rounded-3" href="carga.html"><i class="bi bi-cloud-arrow-up me-2"></i>Cargar conocimiento</a></li>
                <li><button class="dropdown-item rounded-3" id="gdLogout"><i class="bi bi-box-arrow-right me-2"></i>Cerrar sesión</button></li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </nav>
    <div class="gd-announce" id="gdAnnounce">Portal en fase MVP: cada gobierno cuenta con su propio agente que responde con información certificada y cita sus fuentes.
      <button class="btn-close" aria-label="Cerrar" onclick="document.getElementById('gdAnnounce').remove()"></button></div>`;
  }

  function footer() {
    return `<footer class="gd-footer mt-5 py-4"><div class="container-fluid px-3 px-lg-4 d-flex flex-wrap justify-content-between gap-2">
      <span>Gobierno de Datos VPAF · Tecnológico de Monterrey</span>
      <span>Ambiente: ${esc(C.ENV_NAME)} · ${C.USE_MOCK ? "datos de ejemplo" : "API " + esc(C.API_BASE_URL)}</span></div></footer>`;
  }

  function assistant() {
    return `
    <button class="gd-assistant-tab" data-bs-toggle="offcanvas" data-bs-target="#gdAssistant" aria-controls="gdAssistant"><span>Asistente<br>GD 360</span></button>
    <div class="offcanvas offcanvas-end" tabindex="-1" id="gdAssistant" style="width:min(440px,100vw)">
      <div class="offcanvas-header border-bottom">
        <div><h5 class="offcanvas-title fw-600 mb-0">Asistente GD 360</h5><small class="text-muted-gd">Respuestas con fuentes certificadas</small></div>
        <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Cerrar"></button>
      </div>
      <div class="offcanvas-body p-0" id="gdAssistantBody"></div>
    </div>`;
  }

  // ---------------------------------------------------------------- Chat
  function mountChat(el, opts = {}) {
    const state = { gobierno: opts.gobierno || "datos", dominio: opts.dominio || "" };
    const gobOpts = C.GOBIERNOS.map((g) => `<option value="${g.id}" ${g.id === state.gobierno ? "selected" : ""}>${g.nombre}</option>`).join("");
    el.innerHTML = `
      <div class="gd-chat">
        ${opts.hideSelector ? "" : `<div class="px-3 pt-3"><select class="form-select form-select-sm" data-role="gob" aria-label="Agente">${gobOpts}</select></div>`}
        <div class="gd-chat-log" data-role="log">
          <div class="gd-msg bot">${esc(opts.saludo || "Hola, soy el asistente de gobierno. Hazme tu pregunta y te respondo con información certificada y sus fuentes.")}</div>
          <div class="d-flex flex-wrap gap-2" data-role="sugg"></div>
        </div>
        <form class="gd-chat-input d-flex gap-2" data-role="form">
          <input class="form-control" data-role="q" placeholder="Escribe tu pregunta…" autocomplete="off" required>
          <button class="btn btn-gd px-3" aria-label="Enviar"><i class="bi bi-send-fill"></i></button>
        </form>
      </div>`;
    const $ = (r) => el.querySelector(`[data-role="${r}"]`);
    const log = $("log");
    const sugg = opts.suggestions || ["¿Cuál es el identificador golden de una persona?", "¿Qué datos se piden post compra?", "¿Qué habilitador es sistema de registro de la oferta?"];
    $("sugg").innerHTML = sugg.map((s) => `<button type="button" class="btn btn-gd-ghost btn-sm gd-suggest">${esc(s)}</button>`).join("");
    $("sugg").querySelectorAll("button").forEach((b) => b.onclick = () => ask(b.textContent));
    if ($("gob")) $("gob").onchange = (e) => { state.gobierno = e.target.value; };

    async function ask(q) {
      q = q.trim(); if (!q) return;
      const s = $("sugg"); if (s) s.style.display = "none";
      log.insertAdjacentHTML("beforeend", `<div class="gd-msg user">${esc(q)}</div>`);
      const typing = document.createElement("div");
      typing.className = "gd-msg bot gd-typing"; typing.innerHTML = "<span></span><span></span><span></span>";
      log.appendChild(typing); log.scrollTop = log.scrollHeight;
      try {
        const r = await window.GD_API.query({ pregunta: q, gobierno: state.gobierno, dominio: state.dominio || null, top_k: 4 });
        typing.remove();
        const src = (r.fuentes || []).map((f) => `<span class="gd-tag">${esc(f.titulo)} · ${f.score}</span>`).join("");
        log.insertAdjacentHTML("beforeend", `<div class="gd-msg bot">${md(r.respuesta)}${src ? `<div class="gd-src"><i class="bi bi-journal-check me-1"></i>Fuentes:<br>${src}</div>` : ""}</div>`);
        opts.onAnswer && opts.onAnswer(r);
      } catch (e) {
        typing.remove();
        log.insertAdjacentHTML("beforeend", `<div class="gd-msg bot text-danger">No fue posible consultar al agente: ${esc(e.message)}</div>`);
      }
      log.scrollTop = log.scrollHeight;
    }
    $("form").onsubmit = (e) => { e.preventDefault(); const i = $("q"); ask(i.value); i.value = ""; };
    return { ask, setGobierno: (g) => { state.gobierno = g; if ($("gob")) $("gob").value = g; } };
  }

  // ---------------------------------------------------------------- Init
  window.GD_LAYOUT = {
    mountChat,
    init(active, opts = {}) {
      if (!window.GD_AUTH.guard()) return false;
      document.getElementById("app-header").innerHTML = header(active);
      const f = document.getElementById("app-footer"); if (f) f.innerHTML = footer();
      if (!opts.noAssistant) {
        document.body.insertAdjacentHTML("beforeend", assistant());
        const body = document.getElementById("gdAssistantBody");
        const u = window.GD_AUTH.user();
        window.GD_LAYOUT.assistant = mountChat(body, { gobierno: opts.gobierno || u.gobierno, dominio: opts.dominio, suggestions: opts.suggestions });
      }
      document.getElementById("gdLogout").onclick = () => window.GD_AUTH.logout();
      return true;
    }
  };
})();
