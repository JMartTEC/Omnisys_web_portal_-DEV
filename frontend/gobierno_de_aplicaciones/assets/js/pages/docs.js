/* =========================================================================
   docs.js -- "APM y TDD" (documentos de referencia)
   ========================================================================= */

function puntosProgreso(colores) {
  const lista = colores && colores.length ? colores : ["gris", "gris", "gris", "gris", "gris", "gris"];
  return `<span class="puntos-progreso">${
    lista.map((c) => `<span class="p-progreso p-${esc(c)}"></span>`).join("")
  }</span>`;
}

function pintarDocsReferencia(d) {
  if (!d) {
    $("resumen-docs-apm").textContent = "No se pudo cargar la referencia.";
    return;
  }
  const lista = d.habilitadores || [];
  $("resumen-docs-apm").textContent = lista.length
    ? `${lista.length} habilitador${lista.length === 1 ? "" : "es"} sembrado${lista.length === 1 ? "" : "s"} como referencia.`
    : "Todavía no se ha sembrado ningún habilitador (sube el libro de APM en "
      + "Inicio, o cárgalo a mano en «Comparar APM y TDD»).";

  const cuadroApm = $("cuadro-apm-referencia");
  if (d.apm_nombre) {
    $("nombre-apm-referencia").textContent = d.apm_nombre;
    cuadroApm.hidden = false;
  } else {
    cuadroApm.hidden = true;
  }

  $("titulo-habilitadores").hidden = lista.length === 0;
  $("buscador-docs").hidden = lista.length === 0;
  $("lista-docs-aplicativos").innerHTML = lista.length
    ? lista.map((h) => `
      <div class="cuadro-referencia" data-busqueda="${esc(normalizarBusqueda(
          `${h.habilitador || ""} ${h.id_habilitador || ""} ${h.tdd_nombre || ""}`))}">
        <span class="cuadro-referencia-etiqueta">Habilitador</span>
        <b class="cuadro-referencia-nombre">${esc(h.habilitador || h.id_habilitador || "—")}</b>
        <span class="cuadro-referencia-etiqueta cuadro-referencia-tdd-etiqueta">TDD</span>
        ${h.tdd_nombre
          ? `<span class="cuadro-referencia-tdd">${esc(h.tdd_nombre)}</span>`
          : `<span class="cuadro-referencia-tdd cuadro-referencia-pendiente">Sin TDD todavía</span>`}
        ${puntosProgreso(h.progreso)}
      </div>`).join("")
    : "";
}

/* Buscador: filtra las tarjetas por habilitador, ID o nombre del TDD, sin
   distinguir mayúsculas ni acentos. */
function normalizarBusqueda(t) {
  return String(t || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

$("buscar-docs").addEventListener("input", () => {
  const q = normalizarBusqueda($("buscar-docs").value.trim());
  const tarjetas = [...document.querySelectorAll("#lista-docs-aplicativos .cuadro-referencia")];
  let visibles = 0;
  tarjetas.forEach((t) => {
    const si = !q || t.dataset.busqueda.includes(q);
    t.hidden = !si;
    if (si) visibles += 1;
  });
  $("conteo-docs").textContent = q
    ? (visibles ? `${visibles} de ${tarjetas.length}` : "Ningún habilitador coincide con la búsqueda.")
    : "";
});

cargarDocsReferencia().then(pintarDocsReferencia).catch(() => {
  mostrarError("docs", "No se pudo cargar la referencia.");
});
