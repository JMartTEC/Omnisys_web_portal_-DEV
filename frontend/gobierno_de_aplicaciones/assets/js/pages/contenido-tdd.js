/* =========================================================================
   contenido-tdd.js -- visor del contenido completo de los TDD Nivel 2
   y preguntas sobre ellos (Cosmos tdd2/documentos + Blob imagenes-tdd).
   ========================================================================= */

const RUTA_CT = "/gobierno_de_aplicaciones/api/tdd2/contenido";
let ctDocs = [];
let ctActual = "";

const ctNorm = (t) => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function ctError(m) {
  const el = $("ct-error");
  el.textContent = m || "";
  el.hidden = !m;
}

function pintarLista() {
  const f = ctNorm($("ct-filtro").value);
  const filas = ctDocs.filter((d) =>
    !f || ctNorm(`${d.nombre} ${d.aplicativo} ${d.numero} ${d.id_habilitador}`).includes(f));
  $("ct-total").textContent = `${filas.length} de ${ctDocs.length} TDD Nivel 2`;
  $("ct-lista").innerHTML = filas.map((d) => `
    <button type="button" class="ct-item${d.id === ctActual ? " activo" : ""}" data-id="${esc(d.id)}">
      <b>${esc(d.aplicativo || d.nombre.replace(/\.docx$/i, ""))}</b>
      <span>${esc(d.nombre)} · Aplicativo ${esc(d.numero || "—")} ·
        ${d.tablas} tablas${d.imagenes ? ` · ${d.imagenes} diagramas` : ""}</span>
    </button>`).join("") || `<p class="nota" style="padding:12px">Sin resultados.</p>`;
}

function pintarBloque(b, id) {
  if (b.tipo === "titulo") {
    const nivel = /1/.test(b.estilo || "") ? 1 : 2;
    return nivel === 1
      ? `<h3 class="ct-t1">${esc(b.texto)}</h3>` : `<h4 class="ct-t2">${esc(b.texto)}</h4>`;
  }
  if (b.tipo === "parrafo") return `<p class="ct-p">${esc(b.texto)}</p>`;
  if (b.tipo === "lista") {
    const items = b.items || (b.texto ? [b.texto] : []);
    return `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
  }
  if (b.tipo === "tabla") {
    const filas = b.filas || [];
    if (!filas.length) return "";
    const [cab, ...resto] = filas;
    return `<div class="ct-tabla-caja"><table class="ct-tabla">
      <thead><tr>${cab.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${resto.map((f) => `<tr>${f.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody>
    </table></div>`;
  }
  if (b.tipo === "imagen" && b.archivo) {
    const n = ctGaleria.findIndex((g) => g.archivo === b.archivo);
    return `<a class="ct-img-mini" data-ampliar="${n}" title="Ampliar">
      <img src="${ctUrlImagen(id, b.archivo, true)}" alt="Diagrama ${esc(b.archivo)}" loading="lazy">
      <small>${esc(b.archivo)}</small></a>`;
  }
  return "";
}

let ctDocActual = {};
let ctGaleria = [];   // diagramas del TDD abierto, sin repetir (para ampliar con flechas)
let ctPosZoom = 0;

const ctUrlImagen = (id, archivo, mini) =>
  `${RUTA_CT}/${encodeURIComponent(id)}/imagen/${encodeURIComponent(archivo)}${mini ? "?mini=1" : ""}`;


function armarGaleria(d) {
  // Los diagramas se listan una sola vez aunque el documento los repita, cada
  // uno con la seccion del TDD en la que aparece por primera vez.
  const vistos = new Map();
  let seccion = "";
  for (const b of d.bloques || []) {
    if (b.tipo === "titulo") seccion = b.texto;
    else if (b.tipo === "imagen" && b.archivo && !vistos.has(b.archivo)) {
      vistos.set(b.archivo, { archivo: b.archivo, seccion });
    }
  }
  const descr = Object.fromEntries((d.imagenes || []).map((i) => [i.archivo, i.descripcion_ia || ""]));
  return [...vistos.values()].map((g) => ({ ...g, descripcion: descr[g.archivo] || "" }));
}

function pintarGaleria(id) {
  if (!ctGaleria.length) return `<p class="nota">Este TDD no tiene diagramas.</p>`;
  return `<div class="ct-galeria">${ctGaleria.map((g, n) => `
    <button type="button" class="ct-mini" data-ampliar="${n}" title="${esc(g.seccion)}">
      <div class="cuadro"><img src="${ctUrlImagen(id, g.archivo, true)}" alt="Diagrama ${esc(g.archivo)}" loading="lazy"></div>
      <span>${esc(g.seccion || g.archivo)}</span></button>`).join("")}</div>`;
}

function pintarCampos(campos) {
  if (!campos.length) {
    return `<p class="nota">Los campos de este TDD Nivel 2 todavía no están en la base.</p>`;
  }
  const grupos = new Map();
  for (const c of campos) {
    const k = c.seccion_titulo || c.seccion || "Sin sección";
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(c);
  }
  const llenos = campos.filter((c) => (c.valor || "").trim()).length;
  return `
    <div class="ct-campos-barra">
      <input type="text" id="ct-filtro-campos" spellcheck="false" placeholder="Buscar en los campos…">
      <span class="nota" id="ct-campos-total">${llenos} de ${campos.length} campos con dato</span>
    </div>
    ${[...grupos].map(([sec, lista]) => `
      <details class="ct-sec" open>
        <summary>${esc(sec)}<small>${lista.filter((c) => (c.valor || "").trim()).length}/${lista.length}</small></summary>
        <div class="ct-tabla-caja"><table class="ct-tabla">
          <thead><tr><th style="width:30%">Campo</th><th>Valor</th><th style="width:70px">Confianza</th></tr></thead>
          <tbody>${lista.map((c) => `
            <tr data-b="${esc(ctNorm(`${c.campo} ${c.valor}`))}">
              <td>${esc(c.campo)}</td>
              <td>${(c.valor || "").trim() ? esc(c.valor) : '<span class="ct-vacio">sin dato</span>'}</td>
              <td>${c.confianza ? `<span class="ct-conf">${esc(c.confianza)}</span>` : ""}</td>
            </tr>`).join("")}</tbody></table></div>
      </details>`).join("")}`;
}

async function abrirDoc(id, seccion) {
  ctActual = id;
  pintarLista();
  const caja = $("ct-doc");
  caja.innerHTML = `<p class="nota">Cargando…</p>`;
  ctError("");
  try {
    const { documento: d, campos = [] } = await pedir(`${RUTA_CT}/${encodeURIComponent(id)}`);
    ctDocActual = d;
    ctGaleria = armarGaleria(d);
    const r = ctDocs.find((x) => x.id === id) || {};
    const cuerpo = (d.bloques || []).map((b) => pintarBloque(b, id)).join("");
    caja.innerHTML = `
      <h1 class="ct-nombre">${esc(r.aplicativo || `Aplicativo ${r.numero || d.nombre}`)}</h1>
      <div class="ct-meta">
        <span>Archivo: ${esc(d.nombre)}</span>
        <span>Aplicativo ${esc((d.aplicativo || {}).numero || "—")}</span>
        <span>${(d.estadisticas || {}).tablas || 0} tablas · ${ctGaleria.length} diagramas ·
              ${((d.estadisticas || {}).caracteres || 0).toLocaleString("es-MX")} caracteres</span>
      </div>
      <div class="ct-acciones">
        ${(d.archivo_original || {}).blob
          ? `<a class="btn btn-sec" href="${RUTA_CT}/${encodeURIComponent(id)}/original">Descargar el .docx original</a>`
          : `<span class="nota">El .docx original todavía no está en el almacenamiento.</span>`}
      </div>
      <h3 class="ct-h" id="ct-h-diagramas">Diagramas <small>${ctGaleria.length} · toca uno para ampliarlo</small></h3>
      ${pintarGaleria(id)}
      <h3 class="ct-h">Campos del TDD Nivel 2 <small>con su confianza</small></h3>
      ${pintarCampos(campos)}
      <h3 class="ct-h">Documento completo <small>texto, tablas y diagramas en el orden original</small></h3>
      <details class="ct-sec" id="ct-completo" ${seccion ? "open" : ""}>
        <summary>Mostrar / ocultar el documento</summary>
        <div style="padding:4px 14px 14px">${cuerpo || `<p class="nota">Este documento no tiene contenido.</p>`}</div>
      </details>`;
    if (seccion) {
      const t = [...caja.querySelectorAll("h3.ct-t1,h4.ct-t2")].find((h) => h.textContent.trim() === seccion.trim());
      (t || caja).scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      caja.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  } catch (e) {
    caja.innerHTML = "";
    ctError(e.message);
  }
}

/* ---------- ampliar un diagrama (con flechas) ---------- */
function ampliar(n) {
  if (!ctGaleria.length) return;
  ctPosZoom = (n + ctGaleria.length) % ctGaleria.length;
  const g = ctGaleria[ctPosZoom];
  let z = document.querySelector(".ct-zoom");
  if (!z) {
    z = document.createElement("div");
    z.className = "ct-zoom";
    z.innerHTML = `<button class="nav ant" type="button" aria-label="Anterior">&#8249;</button>
      <img alt=""><div class="pie"></div>
      <button class="nav sig" type="button" aria-label="Siguiente">&#8250;</button>`;
    z.addEventListener("click", (ev) => {
      if (ev.target.closest(".ant")) { ev.stopPropagation(); ampliar(ctPosZoom - 1); }
      else if (ev.target.closest(".sig")) { ev.stopPropagation(); ampliar(ctPosZoom + 1); }
      else z.remove();
    });
    document.body.appendChild(z);
  }
  z.querySelector("img").src = ctUrlImagen(ctActual, g.archivo, false);
  z.querySelector(".pie").textContent =
    `${ctPosZoom + 1} de ${ctGaleria.length} · ${g.seccion || g.archivo}${g.descripcion ? " — " + g.descripcion : ""}`;
}

async function preguntar() {
  const q = $("ct-pregunta").value.trim();
  if (q.length < 3) return;
  const btn = $("ct-btn-preguntar");
  btn.disabled = true;
  btn.textContent = "Buscando…";
  ctError("");
  try {
    const r = await pedir(`${RUTA_CT}/preguntar`, json({ pregunta: q }));
    const fuentes = (r.fuentes || []).map((f) => `
      <div class="ct-fuente">
        <b>${esc(f.aplicativo || f.nombre)}</b> · ${esc(f.seccion)} ·
        <a data-id="${esc(f.doc)}" data-sec="${esc(f.seccion)}">abrir en el documento</a>
        <div>${esc(f.texto)}</div>
      </div>`).join("");
    const caja = $("ct-respuesta");
    caja.innerHTML = `<div class="ct-resp">${esc(r.respuesta)}</div>
      ${fuentes ? `<h4>Fuentes</h4>${fuentes}` : ""}`;
    caja.hidden = false;
  } catch (e) {
    ctError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Preguntar";
  }
}

(async function iniciar() {
  try {
    const r = await pedir(RUTA_CT);
    ctDocs = r.documentos || [];
    const ia = r.ia || {};
    const sello = $("ct-sello-ia");
    sello.textContent = ia.claude_listo ? "Respuestas con Claude" : "Respuestas sin Claude (fragmentos)";
    sello.hidden = false;
    $("ct-nota-ia").textContent = ia.claude_listo
      ? "Claude redacta la respuesta usando solo los fragmentos encontrados en los TDD."
      : "Todavía no hay llave de Claude: se muestran los fragmentos más cercanos a tu pregunta. "
        + "Al guardar la llave en «Configuración API key», las respuestas se redactan con Claude.";
    pintarLista();
  } catch (e) {
    $("ct-total").textContent = "";
    ctError(e.message);
  }
  $("ct-filtro").addEventListener("input", pintarLista);
  $("ct-lista").addEventListener("click", (ev) => {
    const b = ev.target.closest(".ct-item");
    if (b) abrirDoc(b.dataset.id);
  });
  $("ct-btn-preguntar").addEventListener("click", preguntar);
  $("ct-pregunta").addEventListener("keydown", (ev) => { if (ev.key === "Enter") preguntar(); });
  $("ct-respuesta").addEventListener("click", (ev) => {
    const a = ev.target.closest("a[data-id]");
    if (a) abrirDoc(a.dataset.id, a.dataset.sec);
  });
  $("ct-doc").addEventListener("click", (ev) => {
    const a = ev.target.closest("[data-ampliar]");
    if (a) ampliar(Number(a.dataset.ampliar));
  });
  $("ct-doc").addEventListener("input", (ev) => {
    if (ev.target.id !== "ct-filtro-campos") return;
    const f = ctNorm(ev.target.value);
    $("ct-doc").querySelectorAll("tr[data-b]").forEach((tr) => { tr.hidden = !!f && !tr.dataset.b.includes(f); });
  });
  document.addEventListener("keydown", (ev) => {
    if (!document.querySelector(".ct-zoom")) return;
    if (ev.key === "Escape") document.querySelector(".ct-zoom").remove();
    else if (ev.key === "ArrowLeft") ampliar(ctPosZoom - 1);
    else if (ev.key === "ArrowRight") ampliar(ctPosZoom + 1);
  });
})();
