// Cliente de API. Mismo contrato para modo MOCK y backend real (FastAPI).
// Al migrar a Angular -> src/app/core/services/api.service.ts (HttpClient + interceptor JWT).
(function () {
  const C = window.GD_CONFIG;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------------ HTTP real
  async function http(method, path, body, isForm) {
    const headers = {};
    const token = localStorageSafe.get(C.TOKEN_KEY);
    if (token) headers["Authorization"] = "Bearer " + token;
    if (body && !isForm) headers["Content-Type"] = "application/json";
    const res = await fetch(C.API_BASE_URL + C.API_PREFIX + path, {
      method, headers, body: body ? (isForm ? body : JSON.stringify(body)) : undefined
    });
    if (res.status === 401 && !path.startsWith("/auth/login")) {
      window.GD_AUTH && window.GD_AUTH.logout(true);
      throw new Error("Sesión expirada");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("Error " + res.status));
    return data;
  }

  // ------------------------------------------------------------------ MOCK
  // Modo demostración (sin backend): usuarios de muestra SIN contraseña real; acepta cualquiera.
  // Los usuarios reales viven cifrados en la base de seguridad del servidor.
  const MOCK_USERS = [
    { username: "demo.datos", nombre: "Demo Datos", gobierno: "datos", rol: "admin" },
    { username: "demo.integracion", nombre: "Demo Integración", gobierno: "integracion", rol: "editor" },
    { username: "demo.aplicaciones", nombre: "Demo Aplicaciones", gobierno: "aplicaciones", rol: "editor" }
  ];
  const DB = () => window.GD_MOCK_DATA;
  let mockDocs = [
    { id: "doc-001", nombre: "Rector_Dominio_Persona_APROBADO.docx", gobierno: "datos", dominio: "persona", clasificacion: "Confidencial", estado: "indexado", fragmentos: 142, tamano_kb: 812, cargado_por: "demo.datos", fecha: "2026-09-18T10:12:00" },
    { id: "doc-002", nombre: "E02_Diccionario_Persona_V05.3.xlsx", gobierno: "datos", dominio: "persona", clasificacion: "Confidencial", estado: "indexado", fragmentos: 96, tamano_kb: 245, cargado_por: "demo.datos", fecha: "2026-09-18T10:15:00" },
    { id: "doc-003", nombre: "DEDIND001_Inventario_Integraciones_v9.xlsx", gobierno: "integracion", dominio: "inventario-integraciones", clasificacion: "Interna", estado: "procesando", fragmentos: 0, tamano_kb: 530, cargado_por: "demo.integracion", fecha: "2026-09-24T17:40:00" }
  ];

  function tokenize(t) {
    return (t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .split(/[^a-z0-9_]+/).filter((w) => w.length > 2);
  }
  function corpus(gobierno, dominio) {
    const out = [];
    DB().conocimiento.filter((a) => (!gobierno || a.gobierno === gobierno) && (!dominio || a.id === dominio)).forEach((a) => {
      out.push({ titulo: a.nombre + " — descripción", dominio: a.id, texto: a.descripcion.replace(/\*\*/g, "") + " " + a.resumen });
      a.entidades.forEach((e) => out.push({ titulo: a.nombre + " · " + e.nombre, dominio: a.id, texto: `Entidad ${e.nombre} (${e.tipo}): ${e.descripcion}` }));
      a.diccionario.forEach((d) => out.push({ titulo: a.nombre + " · Diccionario", dominio: a.id, texto: `${d.entidad}.${d.atributo} ${d.tipo}(${d.longitud}) ${d.llave || ""}: ${d.descripcion} Fuente: ${d.fuente}.` }));
      a.glosario.forEach((g) => out.push({ titulo: a.nombre + " · Glosario", dominio: a.id, texto: `${g.termino}: ${g.definicion}` }));
      a.habilitadores.forEach((h) => out.push({ titulo: a.nombre + " · Habilitadores", dominio: a.id, texto: `${h.nombre} (${h.crud}): ${h.descripcion}` }));
    });
    return out;
  }
  function mockQuery(req) {
    const q = tokenize(req.pregunta);
    const scored = corpus(req.gobierno, req.dominio).map((c) => {
      const t = tokenize(c.texto + " " + c.titulo);
      const hits = q.reduce((s, w) => s + (t.some((x) => x.startsWith(w.slice(0, 5))) ? 1 : 0), 0);
      return { ...c, score: q.length ? hits / q.length : 0 };
    }).filter((c) => c.score > 0).sort((a, b) => b.score - a.score).slice(0, req.top_k || 4);
    const gob = DB().gobiernos.find((g) => g.id === req.gobierno);
    if (!scored.length) {
      return { respuesta: `No encontré información certificada sobre eso en ${gob ? gob.nombre : "el repositorio"}. Intenta con el nombre de un dominio, entidad o atributo.`, fuentes: [], agente: req.gobierno, modo: "mock" };
    }
    const resp = "Con base en la información certificada:\n\n" + scored.map((s) => "• " + s.texto).join("\n");
    return {
      respuesta: resp,
      fuentes: scored.map((s) => ({ titulo: s.titulo, dominio: s.dominio, fragmento: s.texto, score: Math.round(s.score * 100) / 100 })),
      agente: req.gobierno, modo: "mock"
    };
  }

  function conStats(g) {
    const docs = mockDocs.filter((d) => d.gobierno === g.id);
    return { ...g, estadisticas: {
      documentos: docs.length,
      indexados: docs.filter((d) => d.estado === "indexado").length,
      fragmentos: corpus(g.id).length + docs.reduce((s, d) => s + d.fragmentos, 0)
    } };
  }

  const mock = {
    async login(username, password) {
      await sleep(400);
      const u = MOCK_USERS.find((x) => x.username === username);
      if (!u || !password) throw new Error("Usuario o contraseña incorrectos");
      const user = { ...u };
      return { access_token: "mock." + btoa(username) + "." + Date.now(), token_type: "bearer", user };
    },
    async gobiernos() { await sleep(150); return DB().gobiernos.map(conStats); },
    async gobierno(id) {
      await sleep(150);
      const g = DB().gobiernos.find((x) => x.id === id);
      if (!g) throw new Error("Gobierno no encontrado");
      return conStats(g);
    },
    async query(req) { await sleep(700 + Math.random() * 500); return mockQuery(req); },
    async documentos(gobierno) { await sleep(200); return mockDocs.filter((d) => !gobierno || d.gobierno === gobierno); },
    async subirDocumento(form) {
      await sleep(900);
      const f = form.get("archivo");
      const doc = { id: "doc-" + Date.now(), nombre: f.name, gobierno: form.get("gobierno"), dominio: form.get("dominio"), clasificacion: form.get("clasificacion"), estado: "procesando", fragmentos: 0, tamano_kb: Math.max(1, Math.round(f.size / 1024)), cargado_por: (window.GD_AUTH.user() || {}).username, fecha: new Date().toISOString() };
      mockDocs = [doc, ...mockDocs];
      setTimeout(() => { doc.estado = "indexado"; doc.fragmentos = Math.max(3, Math.round(doc.tamano_kb / 6)); }, 3000);
      return doc;
    },
    async eliminarDocumento(id) { await sleep(200); mockDocs = mockDocs.filter((d) => d.id !== id); return { ok: true }; },
    async actualizarAgente(id, cfg) {
      await sleep(300);
      const g = DB().gobiernos.find((x) => x.id === id);
      Object.assign(g, cfg);
      return g;
    }
  };

  const real = {
    login: (username, password) => http("POST", "/auth/login", { username, password }),
    gobiernos: () => http("GET", "/gobiernos"),
    gobierno: (id) => http("GET", "/gobiernos/" + encodeURIComponent(id)),
    query: (req) => http("POST", "/rag/query", req),
    documentos: (g) => http("GET", "/ingesta/documentos" + (g ? "?gobierno=" + g : "")),
    subirDocumento: (form) => http("POST", "/ingesta/documentos", form, true),
    eliminarDocumento: (id) => http("DELETE", "/ingesta/documentos/" + id),
    actualizarAgente: (id, cfg) => http("PUT", "/gobiernos/" + id + "/agente", cfg)
  };

  window.GD_API = C.USE_MOCK ? mock : real;
})();

// Acceso a localStorage tolerante a navegadores con almacenamiento bloqueado.
window.localStorageSafe = {
  _mem: {},
  get(k) { try { return window.localStorage.getItem(k); } catch (e) { return this._mem[k] || null; } },
  set(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { this._mem[k] = v; } },
  del(k) { try { window.localStorage.removeItem(k); } catch (e) { delete this._mem[k]; } }
};
