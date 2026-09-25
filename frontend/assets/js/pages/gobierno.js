// Sección de un gobierno: introducción, pilares, introducción de sus dominios/temas y su agente RAG.
// Angular -> GobiernoPageComponent (ruta /gobierno/:id).
(async function () {
  const params = new URLSearchParams(location.search);
  const id = params.get("id") || "datos";
  if (!window.GD_LAYOUT.init(id, { noAssistant: true })) return;
  const { esc } = window.GD_UTIL;
  const view = document.getElementById("view");

  let g;
  try { g = await window.GD_API.gobierno(id); }
  catch (e) {
    view.innerHTML = `<div class="gd-empty"><i class="bi bi-search fs-1 d-block mb-2"></i>No encontramos la sección "${esc(id)}". <a href="portal.html">Volver al inicio</a></div>`;
    return;
  }
  document.title = g.nombre + " · Portal GD 360";
  const st = g.estadisticas || {};
  const esDatos = g.id === "datos";
  const etiquetaEstado = { vigente: "Definición vigente", propuesta: "Propuesta GD", "en carga": "En carga" };
  const claseEstado = { vigente: "vigente", propuesta: "propuesta", "en carga": "propuesta" };
  const puedeCargar = window.GD_AUTH.canUpload(g.id);

  const meta = [
    { i: "bi-person-badge", l: "Responsable", v: g.responsable },
    { i: "bi-robot", l: "Agente", v: g.modo === "remoto" ? "Agente propio del equipo" : "Repositorio GD 360" },
    { i: "bi-collection", l: esDatos ? "Dominios" : "Temas", v: `${g.temas.length} ${esDatos ? "dominios" : "temas"}` },
    { i: "bi-file-earmark-text", l: "Documentos", v: `${st.documentos || 0} ${st.documentos === 1 ? "cargado" : "cargados"}` },
    { i: "bi-database", l: "Conocimiento", v: `${(st.fragmentos || 0).toLocaleString("es-MX")} fragmentos` }
  ];

  view.innerHTML = `
    <nav class="gd-breadcrumb mb-4 d-flex flex-wrap" aria-label="breadcrumb">
      <a href="portal.html">Inicio</a><span>${esc(g.nombre)}</span>
    </nav>

    <!-- Encabezado de la sección -->
    <section class="row g-4 mb-5">
      <div class="col-lg-6">
        <div class="gd-detail-media bg-dom-${g.tema}">
          <i class="bi ${g.icono} gd-media-icon"></i>
          <span class="gd-badge-corner fs-6"><i class="bi bi-robot me-1"></i>Agente RAG</span>
          <span class="gd-chip-media">${esc(g.nombre)}</span>
        </div>
      </div>
      <div class="col-lg-6">
        <h1 class="fw-600 mb-1" style="font-size:2rem">${esc(g.nombre)}</h1>
        <div class="gd-code mb-3">${esc(g.lema)}</div>
        <p class="text-muted-gd mb-4" style="line-height:1.75">${esc(g.introduccion)}</p>
        <div class="gd-panel">
          <div class="d-flex justify-content-between align-items-baseline mb-1">
            <span class="fs-5 fw-600">Agente</span>
            <span class="fs-6 fw-500">${st.fragmentos > 0 ? '<i class="bi bi-circle-fill text-success small me-1"></i>Disponible' : '<i class="bi bi-circle-fill text-warning small me-1"></i>En preparación'}</span>
          </div>
          <div class="text-end small text-muted-gd mb-3">Responde con información certificada y cita sus fuentes</div>
          <div class="d-flex justify-content-end flex-wrap gap-2">
            ${puedeCargar ? '<a class="btn btn-link-gd" href="carga.html">Cargar información</a>' : ""}
            <a class="btn btn-gd" href="#agente"><i class="bi bi-chat-dots me-2"></i>Preguntar al agente</a>
          </div>
        </div>
      </div>
    </section>

    <div class="gd-meta-strip mb-5">${meta.map((m) => `
      <div class="gd-meta-item"><i class="bi ${m.i}"></i><div><div class="lbl">${m.l}</div><div class="val">${esc(m.v)}</div></div></div>`).join("")}
    </div>

    <!-- Qué es -->
    <section class="mb-5">
      <h2 class="section-title mb-2">¿Qué es el ${esc(g.nombre)}?</h2>
      <p class="section-sub mb-4" style="max-width:900px">${esc(g.descripcion)}</p>
      <div class="row g-4">${g.pilares.map((p) => `
        <div class="col-12 col-sm-6 col-xl-3"><div class="gd-pilar">
          <div class="gd-pilar-ico"><i class="bi ${p.icono}"></i></div>
          <div class="fw-600 mb-1">${esc(p.titulo)}</div>
          <div class="small text-muted-gd">${esc(p.texto)}</div>
        </div></div>`).join("")}
      </div>
    </section>

    <!-- Introducción de dominios / temas (sin fichas: se consultan vía agente) -->
    <section class="mb-5">
      <h2 class="section-title mb-2">${esc(g.titulo_temas)}</h2>
      <p class="section-sub mb-4" style="max-width:900px">${esc(g.intro_temas)}</p>
      <div class="row g-3">${g.temas.map((t) => `
        <div class="col-12 col-md-6 col-xl-4"><div class="gd-tile">
          <div class="gd-tile-ico bg-dom-${g.tema}"><i class="bi ${t.icono}"></i></div>
          <div class="flex-grow-1 min-w-0">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-1"><span class="fw-600">${esc(t.nombre)}</span>
              <span class="gd-state ${claseEstado[t.estado] || "propuesta"}">${etiquetaEstado[t.estado] || esc(t.estado)}</span></div>
            <div class="small text-muted-gd mb-2">${esc(t.descripcion)}</div>
            <button class="btn btn-link-gd p-0 small" data-ask="${esc(t.nombre)}"><i class="bi bi-chat-dots me-1"></i>Preguntar al agente</button>
          </div>
        </div></div>`).join("")}
      </div>
    </section>

    <!-- Agente -->
    <section id="agente" class="mb-4" style="scroll-margin-top:90px">
      <div class="gd-banner mb-4 py-4">
        <h3 class="mb-1 fs-4">Agente · ${esc(g.nombre)}</h3>
        <div class="opacity-75 small">Pregunta en lenguaje natural. El agente busca en el repositorio de ${esc(g.nombre)} y responde citando sus fuentes.</div>
      </div>
      <div class="row g-4">
        <div class="col-lg-8"><div class="gd-panel p-0 overflow-hidden" style="height:min(600px,75vh)" id="chat"></div></div>
        <div class="col-lg-4">
          <div class="gd-panel">
            <div class="d-flex justify-content-between align-items-center mb-3"><span class="fw-600">Fuentes de la respuesta</span><i class="bi bi-journal-check"></i></div>
            <div id="sources" class="small text-muted-gd">Aún no hay consultas.</div>
          </div>
        </div>
      </div>
    </section>`;

  const chat = window.GD_LAYOUT.mountChat(document.getElementById("chat"), {
    gobierno: g.id, hideSelector: true, suggestions: g.preguntas,
    saludo: `Hola, soy el agente de ${g.nombre}. ¿Qué te gustaría saber?`,
    onAnswer: (r) => {
      const s = document.getElementById("sources");
      s.innerHTML = (r.fuentes || []).length ? r.fuentes.map((f, i) => `
        <div class="mb-3 pb-3 ${i < r.fuentes.length - 1 ? "border-bottom" : ""}">
          <div class="d-flex justify-content-between gap-2 mb-1"><span class="fw-500 text-body">${esc(f.titulo)}</span><span class="gd-tag">${f.score}</span></div>
          <div class="progress gd-progress mb-2" style="height:6px"><div class="progress-bar" style="width:${Math.min(100, f.score * 100)}%"></div></div>
          <div>${esc(f.fragmento)}</div></div>`).join("")
        : "El agente no encontró fragmentos relevantes.";
    }
  });

  const irAlAgente = (q) => {
    document.getElementById("agente").scrollIntoView({ behavior: "smooth" });
    if (q) chat.ask(q);
  };
  view.querySelectorAll("[data-ask]").forEach((b) => b.onclick = () =>
    irAlAgente(esDatos ? `¿Qué es el dominio ${b.dataset.ask} y qué información contiene?` : `¿Qué información hay sobre ${b.dataset.ask}?`));

  if (params.get("q")) irAlAgente(params.get("q"));
  else if (location.hash === "#agente") setTimeout(() => irAlAgente(), 100);
})();
