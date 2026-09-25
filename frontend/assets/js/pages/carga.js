(async function () {
  if (!window.GD_LAYOUT.init("espacio")) return;
  const { esc, gobName } = window.GD_UTIL;
  const C = window.GD_CONFIG;
  const u = window.GD_AUTH.user();
  const isAdmin = u.rol === "admin";
  const gobs = isAdmin ? C.GOBIERNOS : C.GOBIERNOS.filter((g) => g.id === u.gobierno);
  const opt = (list, sel) => list.map((g) => `<option value="${g.id}" ${g.id === sel ? "selected" : ""}>${esc(g.nombre)}</option>`).join("");

  document.getElementById("bannerHello").textContent = `¡${u.nombre}, alimenta el conocimiento de ${gobName(u.gobierno)}!`;

  let agentes = [];
  try { agentes = await window.GD_API.gobiernos(); } catch (e) { /* sin secciones */ }

  // ---------------- Carga
  const upGob = document.getElementById("upGob"), upDom = document.getElementById("upDom");
  upGob.innerHTML = opt(gobs, u.gobierno);
  upGob.disabled = !isAdmin;
  const fillDom = () => {
    const temas = (agentes.find((g) => g.id === upGob.value) || {}).temas || [];
    upDom.innerHTML = '<option value="general">General</option>' + temas.map((t) => `<option value="${t.id}">${esc(t.nombre)}</option>`).join("");
  };
  upGob.onchange = fillDom; fillDom();

  const file = document.getElementById("upFile"), drop = document.getElementById("drop");
  const setName = () => document.getElementById("fileName").textContent = file.files[0] ? `${file.files[0].name} · ${Math.round(file.files[0].size / 1024)} KB` : "";
  file.onchange = setName;
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) { file.files = e.dataTransfer.files; setName(); } });
  document.getElementById("upReset").onclick = () => setTimeout(setName, 0);

  document.getElementById("upForm").onsubmit = async (e) => {
    e.preventDefault();
    const err = document.getElementById("upErr"); err.classList.add("d-none");
    const f = file.files[0];
    if (!f) { err.textContent = "Selecciona un archivo."; err.classList.remove("d-none"); return; }
    if (f.size > 20 * 1024 * 1024) { err.textContent = "El archivo supera 20 MB."; err.classList.remove("d-none"); return; }
    const fd = new FormData();
    fd.append("archivo", f); fd.append("gobierno", upGob.value); fd.append("dominio", upDom.value);
    fd.append("clasificacion", document.getElementById("upCls").value);
    const btn = document.getElementById("upBtn");
    btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Cargando…';
    try {
      await window.GD_API.subirDocumento(fd);
      document.getElementById("upForm").reset(); setName();
      await loadDocs();
      bootstrap.Tab.getOrCreateInstance(document.querySelector('[data-bs-target="#s-docs"]')).show();
      setTimeout(loadDocs, 3300);
    } catch (ex) { err.textContent = ex.message; err.classList.remove("d-none"); }
    finally { btn.disabled = false; btn.innerHTML = '<i class="bi bi-upload me-2"></i>Cargar e indexar'; }
  };

  // ---------------- Documentos
  const docGob = document.getElementById("docGob");
  docGob.innerHTML = (isAdmin ? '<option value="">Todos los gobiernos</option>' : "") + opt(gobs, isAdmin ? "" : u.gobierno);
  docGob.onchange = loadDocs;
  const ext = (n) => (n.split(".").pop() || "").toLowerCase();
  const color = { pdf: "#c0392b", docx: "#2b5797", xlsx: "#1e7145", csv: "#1e7145", md: "#444", txt: "#666", json: "#8e44ad" };

  async function loadDocs() {
    const list = document.getElementById("docList");
    try {
      const docs = await window.GD_API.documentos(docGob.value);
      const idx = docs.filter((d) => d.estado === "indexado").length;
      const pct = docs.length ? Math.round((idx / docs.length) * 100) : 0;
      document.getElementById("progBar").style.width = pct + "%";
      document.getElementById("progPct").textContent = pct + "%";
      document.getElementById("progTxt").textContent = `${idx} de ${docs.length} documentos indexados · ${docs.reduce((s, d) => s + d.fragmentos, 0)} fragmentos`;
      list.innerHTML = docs.length ? docs.map((d) => `
        <div class="gd-list-item">
          <div class="gd-file-ico" style="background:${color[ext(d.nombre)] || "#555"}">${ext(d.nombre).toUpperCase()}</div>
          <div class="flex-grow-1 min-w-0">
            <div class="fw-500 text-truncate">${esc(d.nombre)}</div>
            <div class="small text-muted-gd mb-2">${esc(gobName(d.gobierno))} · ${esc(d.dominio)} · ${esc(d.clasificacion)} · ${d.tamano_kb} KB · ${esc(d.cargado_por || "")}</div>
            <div class="d-flex align-items-center gap-3"><div class="progress gd-progress flex-grow-1" style="height:8px"><div class="progress-bar ${d.estado === "procesando" ? "progress-bar-striped progress-bar-animated" : d.estado === "error" ? "bg-danger" : ""}" style="width:${d.estado === "indexado" ? 100 : d.estado === "error" ? 100 : 45}%"></div></div>
            <span class="small text-nowrap">${d.estado === "indexado" ? d.fragmentos + (d.fragmentos === 1 ? " fragmento" : " fragmentos") : esc(d.estado)}</span></div>
          </div>
          ${window.GD_AUTH.canUpload(d.gobierno) ? `<button class="btn btn-link-gd" title="Eliminar" data-del="${d.id}"><i class="bi bi-trash3"></i></button>` : ""}
        </div>`).join("") : '<div class="gd-empty">Aún no hay documentos cargados.</div>';
      list.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
        if (!confirm("¿Eliminar el documento y sus fragmentos del índice?")) return;
        await window.GD_API.eliminarDocumento(b.dataset.del); loadDocs();
      });
    } catch (e) { list.innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
  }
  loadDocs();

  // ---------------- Agente
  const agGob = document.getElementById("agGob");
  agGob.innerHTML = opt(gobs, u.gobierno); agGob.disabled = !isAdmin;
  const fillAg = () => {
    const g = agentes.find((x) => x.id === agGob.value) || {};
    document.getElementById("agModo").value = g.modo || "local";
    document.getElementById("agUrl").value = g.url || "";
    document.getElementById("agUrl").disabled = document.getElementById("agModo").value !== "remoto";
  };
  agGob.onchange = fillAg;
  document.getElementById("agModo").onchange = (e) => { document.getElementById("agUrl").disabled = e.target.value !== "remoto"; };
  fillAg();
  document.getElementById("agForm").onsubmit = async (e) => {
    e.preventDefault();
    const modo = document.getElementById("agModo").value, url = document.getElementById("agUrl").value.trim();
    if (modo === "remoto" && !/^https?:\/\//.test(url)) { alert("Captura una URL válida (https://…)"); return; }
    await window.GD_API.actualizarAgente(agGob.value, { modo, url: modo === "remoto" ? url : null });
    const ok = document.getElementById("agOk"); ok.classList.remove("d-none"); setTimeout(() => ok.classList.add("d-none"), 2500);
  };
})();
