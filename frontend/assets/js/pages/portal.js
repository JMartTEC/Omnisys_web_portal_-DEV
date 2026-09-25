(async function () {
  if (!window.GD_LAYOUT.init("inicio")) return;
  const { esc, gobName } = window.GD_UTIL;
  const C = window.GD_CONFIG;
  const u = window.GD_AUTH.user();

  // Buscador -> sección del gobierno elegido, con la pregunta precargada
  const sel = document.getElementById("searchGob");
  sel.innerHTML = C.GOBIERNOS.map((g) => `<option value="${g.id}" ${g.id === u.gobierno ? "selected" : ""}>${g.nombre}</option>`).join("");
  document.getElementById("searchForm").onsubmit = (e) => {
    e.preventDefault();
    const q = document.getElementById("searchInput").value.trim();
    if (q) location.href = `gobierno.html?id=${sel.value}&q=${encodeURIComponent(q)}#agente`;
  };

  document.getElementById("hello").textContent = `¡${u.nombre}, pregunta sin buscar documentos!`;
  document.getElementById("roleText").textContent =
    `Ingresaste como ${u.rol} de ${gobName(u.gobierno)}. Puedes consultar a los tres agentes y cargar información al repositorio de tu gobierno desde "Mi espacio".`;

  const card = (g) => {
    const st = g.estadisticas || {};
    const activo = st.fragmentos > 0;
    return `
    <div class="col-12 col-md-6 col-xl-4">
      <article class="gd-card">
        <div class="gd-card-media bg-dom-${g.tema}" style="height:210px">
          <i class="bi ${g.icono} gd-media-icon"></i>
          <span class="gd-badge-corner"><i class="bi bi-robot me-1"></i>Agente RAG</span>
          <span class="gd-chip-status ${activo ? "vigente" : "propuesta"}">${activo ? "Agente disponible" : "En preparación"}</span>
          <span class="gd-chip-media">${g.modo === "remoto" ? "Agente propio" : "GD 360"}</span>
        </div>
        <div class="gd-card-body">
          <h3 class="gd-card-title">${esc(g.nombre)}</h3>
          <div class="gd-card-cat">${esc(g.responsable)}</div>
          <div class="gd-reco"><div class="mb-1"><i class="bi bi-info-circle-fill me-2"></i><strong>${esc(g.lema)}</strong></div>${esc(g.descripcion)}</div>
          <div class="gd-meta-inline">
            <span><i class="bi bi-collection"></i>${g.temas.length} ${g.id === "datos" ? "dominios" : "temas"}</span>
            <span><i class="bi bi-file-earmark-text"></i>${st.documentos || 0} ${st.documentos === 1 ? "documento" : "documentos"}</span>
            <span><i class="bi bi-database"></i>${(st.fragmentos || 0).toLocaleString("es-MX")} ${st.fragmentos === 1 ? "fragmento" : "fragmentos"}</span>
          </div>
          <div class="mt-auto d-flex justify-content-between align-items-center gap-2">
            <a class="btn btn-link-gd px-0 small" href="gobierno.html?id=${g.id}#agente"><i class="bi bi-chat-dots me-1"></i>Preguntar</a>
            <a class="btn btn-gd" href="gobierno.html?id=${g.id}">Entrar a la sección</a>
          </div>
        </div>
      </article>
    </div>`;
  };

  const grid = document.getElementById("grid");
  try {
    const gobs = await window.GD_API.gobiernos();
    grid.innerHTML = gobs.map(card).join("");
  } catch (e) {
    grid.innerHTML = `<div class="alert alert-danger">No fue posible cargar las secciones: ${esc(e.message)}</div>`;
  }
})();
