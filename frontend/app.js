/* ═══════════════════════════════════════════════════════
   Cazafacturas — Frontend Logic
   ═══════════════════════════════════════════════════════ */

const API = "/api";

let idiomaActual = "es";
let paisActual = "ES";

/* ─── Helpers ────────────────────────────────────────── */

async function fetchJSON(url, opts = {}) {
  const r = await fetch(url, { headers: { Accept: "application/json" }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

/* ─── i18n ───────────────────────────────────────────── */

function aplicarIdioma(lang) {
  idiomaActual = lang;
  localStorage.setItem("cf-idioma", lang);
  document.documentElement.lang = lang;

  $$("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    const txt = t(key, lang);
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      el.placeholder = txt;
    } else if (el.tagName === "OPTION") {
      el.textContent = txt;
    } else {
      el.textContent = txt;
    }
  });

  // update selects labels
  const labelMotor = $("label[for='select-motor']");
  if (labelMotor) labelMotor.textContent = t("motor", lang);
  const labelTrampas = $("label[for='check-trampas'] span:last-child");
  if (labelTrampas) labelTrampas.textContent = t("incluir_trampas", lang);
  const btnEjecutar = $("#btn-ejecutar .btn-texto");
  if (btnEjecutar) btnEjecutar.textContent = t("ejecutar_lote", lang);
  const labelIdioma = $("label[for='select-idioma']");
  if (labelIdioma) labelIdioma.textContent = t("idioma", lang);
  const labelPais = $("label[for='select-pais']");
  if (labelPais) labelPais.textContent = t("pais", lang);

  // re-render dataset filter labels
  $$(".dataset-filtro").forEach(btn => {
    const key = btn.getAttribute("data-i18n");
    if (key) btn.textContent = t(key, lang);
  });

  // re-render progress text
  const prog = $("#texto-progreso");
  if (prog && prog.textContent.includes("En cola") || prog.textContent.includes("Queued")) {
    actualizarProgresoTexto();
  }
}

function t(key, lang = idiomaActual) {
  return I18N[lang]?.[key] || I18N.es[key] || key;
}

function initIdioma() {
  const guardado = localStorage.getItem("cf-idioma");
  if (guardado) {
    idiomaActual = guardado;
  } else if (navigator.language.startsWith("en")) {
    idiomaActual = "en";
  }
  const select = $("#select-idioma");
  if (select) select.value = idiomaActual;
  aplicarIdioma(idiomaActual);
}

function cambiarIdioma(lang) {
  aplicarIdioma(lang);
  cargarMotores();
  cargarComparativa();
  if ($("#pantalla-dataset").classList.contains("activa")) cargarDataset();
}

/* ─── Theme ──────────────────────────────────────────── */

function initTema() {
  const guardado = localStorage.getItem("cf-tema");
  if (guardado) {
    document.documentElement.setAttribute("data-theme", guardado);
  } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
}

function toggleTema() {
  const actual = document.documentElement.getAttribute("data-theme");
  const siguiente = actual === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", siguiente);
  localStorage.setItem("cf-tema", siguiente);
}

/* ─── Navigation ─────────────────────────────────────── */

function navegarA(pantalla) {
  $$(".pantalla").forEach(p => p.classList.remove("activa"));
  $$(".nav-link").forEach(l => l.classList.remove("activa"));

  const el = $(`#pantalla-${pantalla}`);
  const link = $(`.nav-link[data-pantalla="${pantalla}"]`);
  if (el) el.classList.add("activa");
  if (link) link.classList.add("activa");

  if (pantalla === "dataset") cargarDataset();
}

/* ─── Panel: Load Motors ─────────────────────────────── */

async function cargarMotores() {
  const { motores } = await fetchJSON(`${API}/estado`);
  const select = $("#select-motor");
  select.innerHTML = "";

  const chips = $("#seccion-motores");
  chips.hidden = false;
  chips.innerHTML = "";

  motores.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = `${m.nombre} — ${m.estado}`;
    opt.disabled = m.estado !== "disponible";
    select.appendChild(opt);

    const chip = document.createElement("span");
    chip.className = `chip-motor ${m.estado === "disponible" ? "disponible" : ""}`;
    chip.textContent = m.nombre;
    chips.appendChild(chip);
  });
}

/* ─── Panel: Load Countries ──────────────────────────── */

async function cargarPaises() {
  const data = await fetchJSON(`${API}/paises`);
  const select = $("#select-pais");
  select.innerHTML = "";
  data.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.codigo;
    opt.textContent = p[idiomaActual === "en" ? "en" : "es"];
    select.appendChild(opt);
  });
  select.value = paisActual;
}

/* ─── Panel: Comparative Table ───────────────────────── */

async function cargarComparativa() {
  const data = await fetchJSON(`${API}/comparativa`);
  const vacio = $("#contenedor-comparativa");
  const contenedor = $("#contenedor-tabla");
  const cuerpo = $("#cuerpo-comparativa");
  const invDiv = $("#contenedor-invenciones");

  if (!data.length) {
    vacio.hidden = false;
    contenedor.hidden = true;
    invDiv.innerHTML = `<p class="invenciones-vacio">${t("sin_invenciones")}</p>`;
    return;
  }

  vacio.hidden = true;
  contenedor.hidden = false;
  cuerpo.innerHTML = "";

  const allCampos = new Map();

  data.forEach(m => {
    const tr = document.createElement("tr");
    const cls = m.precision >= 0.99 ? "precision-alta" :
                m.precision >= 0.9 ? "precision-media" : "precision-baja";

    tr.innerHTML = `
      <td class="td-motor">${m.id_motor}</td>
      <td class="td-modelo">${m.modelo || "—"}</td>
      <td class="td-numero ${cls}">${(m.precision * 100).toFixed(1)}%</td>
      <td class="td-numero invencion-valor">${(m.tasa_invencion * 100).toFixed(1)}%</td>
      <td class="td-numero">${m.aciertos}</td>
      <td class="td-numero">${m.fallos}</td>
      <td class="td-numero">${m.invenciones}</td>
      <td class="td-numero">${m.segundos.toFixed(1)}s</td>
      <td class="td-numero">${m.n_casos}</td>
    `;
    cuerpo.appendChild(tr);

    for (const [campo, n] of Object.entries(m.inventa_por_campo || {})) {
      allCampos.set(campo, (allCampos.get(campo) || 0) + n);
    }
  });

  if (allCampos.size) {
    invDiv.innerHTML = "";
    const ul = document.createElement("ul");
    ul.className = "invenciones-lista";
    const sorted = [...allCampos.entries()].sort((a, b) => b[1] - a[1]);
    sorted.forEach(([campo, n]) => {
      const li = document.createElement("li");
      li.innerHTML = `<span class="n">${n}×</span> ${campo}`;
      ul.appendChild(li);
    });
    invDiv.appendChild(ul);
  } else {
    invDiv.innerHTML = `<p class="invenciones-vacio">${t("ningun_motor_invento")}</p>`;
  }
}

/* ─── Panel: Execute ─────────────────────────────────── */

async function ejecutarLote() {
  const select = $("#select-motor");
  const btn = $("#btn-ejecutar");
  const trampas = $("#check-trampas").checked;
  const idMotor = select.value;
  if (!idMotor) return;

  btn.disabled = true;
  btn.querySelector(".btn-texto").textContent = t("ejecutando");

  const prog = $("#seccion-progreso");
  prog.hidden = false;
  $("#barra-relleno").style.width = "0%";
  actualizarProgresoTexto("en_cola");

  // Preparar vista de ejecución
  navegarA("ejecucion");
  $("#ejecucion-meta").hidden = false;
  $("#nodos-vacia").hidden = true;
  $("#nodos-grid").hidden = false;
  $("#nodos-grid").innerHTML = "";
  $("#ejecucion-subtitle").textContent = `${t("motor")}: ${idMotor} | ${t("pais")}: ${paisActual} | ${t("idioma")}: ${idiomaActual.toUpperCase()}`;

  try {
    const { id_ejecucion } = await fetchJSON(`${API}/ejecutar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_motor: idMotor, trampas, idioma: idiomaActual })
    });

    // Cargar dataset para crear nodos
    const casos = await fetchJSON(`${API}/dataset?trampas=${trampas}&pais=${paisActual}`);
    const grid = $("#nodos-grid");
    grid.innerHTML = "";
    const nodos = {};

    casos.forEach(caso => {
      const nodo = document.createElement("div");
      nodo.className = "nodo";
      nodo.dataset.estado = "en_cola";
      nodo.dataset.id = caso.id;
      nodo.innerHTML = `
        <span class="nodo-id">${caso.id}</span>
        <span class="nodo-estado">${t("en_cola")}</span>
      `;
      nodo.addEventListener("click", () => verDetalle(caso, idMotor));
      grid.appendChild(nodo);
      nodos[caso.id] = nodo;
    });

    let aciertos = 0, fallos = 0, invenciones = 0;

    const es = new EventSource(`${API}/ejecutar/${id_ejecucion}/stream`);
    es.onmessage = e => {
      const est = JSON.parse(e.data);
      actualizarProgreso(est, nodos);

      if (est.caso && nodos[est.caso]) {
        const nodo = nodos[est.caso];
        if (est.estado === "analizando") {
          nodo.dataset.estado = "analizando";
          nodo.querySelector(".nodo-estado").textContent = t("analizando");
        } else if (est.estado === "resuelta") {
          nodo.dataset.estado = "resuelta";
          nodo.querySelector(".nodo-estado").textContent = t("resuelta");
          aciertos++;
          actualizarMeta(est, aciertos, fallos, invenciones);
        } else if (est.estado === "fallada") {
          nodo.dataset.estado = "fallada";
          nodo.querySelector(".nodo-estado").textContent = t("fallada");
          fallos++;
          actualizarMeta(est, aciertos, fallos, invenciones);
        }
      }
    };

    es.addEventListener("fin", async () => {
      es.close();
      btn.disabled = false;
      btn.querySelector(".btn-texto").textContent = t("ejecutar_lote");
      prog.hidden = true;
      $("#ejecucion-subtitle").textContent = t("terminada");
      await cargarComparativa();
    });

    es.addEventListener("error", () => {
      es.close();
      btn.disabled = false;
      btn.querySelector(".btn-texto").textContent = t("ejecutar_lote");
      prog.hidden = true;
    });
  } catch (e) {
    alert(t("error") + ": " + e.message);
    btn.disabled = false;
    btn.querySelector(".btn-texto").textContent = t("ejecutar_lote");
    prog.hidden = true;
  }
}

function actualizarProgreso(est, nodos) {
  if (est.total) {
    const pct = Math.round((est.pos / est.total) * 100);
    $("#barra-relleno").style.width = pct + "%";
  }
  actualizarProgresoTexto(est.estado, est);
}

function actualizarProgresoTexto(estado, est) {
  const txt = $("#texto-progreso");
  const map = {
    "en_cola": t("en_cola"),
    "analizando": est && est.caso ? `${t("analizando")} ${est.caso} (${est.pos}/${est.total})` : t("analizando"),
    "resuelta": est && est.caso ? `${t("resuelta")} ${est.caso}` : t("resuelta"),
    "fallada": est && est.caso ? `${t("fallada")} ${est.caso}` : t("fallada"),
    "terminada": t("terminada"),
  };
  if (estado?.startsWith("error")) {
    txt.textContent = `${t("error")}: ${estado.slice(6)}`;
  } else {
    txt.textContent = map[estado] || "";
  }
}

function actualizarMeta(est, aciertos, fallos, invenciones) {
  if (est.total) {
    $("#meta-progreso").textContent = `${est.pos}/${est.total}`;
  }
  $("#meta-aciertos").textContent = aciertos;
  $("#meta-fallos").textContent = fallos;
  $("#meta-invenciones").textContent = invenciones;
}

/* ─── Detail View ────────────────────────────────────── */

async function verDetalle(caso, idMotor) {
  navegarA("detalle");

  $("#detalle-titulo").textContent = caso.id;
  $("#detalle-sub").textContent = caso.es_trampa ? t("caso_trampa") : t("caso_normal");

  // Documento original
  const docLimpio = {};
  for (const [k, v] of Object.entries(caso.documento)) {
    if (!k.startsWith("_")) docLimpio[k] = v;
  }
  $("#detalle-documento").textContent = JSON.stringify(docLimpio, null, 2);

  // Esperado
  const espLimpio = {};
  for (const [k, v] of Object.entries(caso.esperado)) {
    if (!k.startsWith("_")) espLimpio[k] = v;
  }
  $("#detalle-esperado").textContent = JSON.stringify(espLimpio, null, 2);

  // Intentar obtener resultado reciente
  try {
    const resultados = await fetchJSON(`${API}/resultados`);
    const reciente = resultados.find(r => r.id_motor === idMotor);
    if (reciente) {
      const detalle = await fetchJSON(`${API}/resultados/${reciente.id_ejecucion}`);
      const rCaso = detalle.resultados?.find(r => r.factura === caso.id);
      if (rCaso) {
        $("#detalle-obtenido").textContent = JSON.stringify(rCaso, null, 2);
        renderizarCampos(rCaso.campos || []);
        return;
      }
    }
  } catch (e) { /* ignore */ }

  $("#detalle-obtenido").textContent = "// " + t("sin_resultado");
  $("#detalle-campos").innerHTML = `<p style="color: var(--tinta-tenue); font-size: 0.85rem;">${t("sin_resultado")}</p>`;
}

function renderizarCampos(campos) {
  const lista = $("#detalle-campos");
  lista.innerHTML = "";

  if (!campos.length) {
    lista.innerHTML = '<p style="color: var(--tinta-tenue); font-size: 0.85rem;">Sin campos para mostrar.</p>';
    return;
  }

  const estadoLabels = {
    acierto: t("estado_acierto"),
    fallo: t("estado_fallo"),
    invencion: t("estado_invencion"),
  };

  campos.forEach(c => {
    const fila = document.createElement("div");
    fila.className = "campo-fila";
    fila.dataset.estado = c.estado;

    const estadoLabel = estadoLabels[c.estado] || c.estado;
    const estadoCls = `estado-${c.estado}`;

    fila.innerHTML = `
      <span class="campo-nombre">${c.campo}</span>
      <span class="campo-esperado">${formatoValor(c.esperado)}</span>
      <span class="campo-obtenido">${formatoValor(c.obtenido)}</span>
      <span class="campo-estado ${estadoCls}">${estadoLabel}</span>
    `;
    lista.appendChild(fila);
  });
}

function formatoValor(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/* ─── Dataset ────────────────────────────────────────── */

let datasetCache = [];
let datasetFiltro = "todos";

async function cargarDataset() {
  try {
    datasetCache = await fetchJSON(`${API}/dataset?trampas=true&pais=${paisActual}`);
    renderizarDataset();
  } catch (e) {
    console.error("Error cargando dataset:", e);
  }
}

function renderizarDataset() {
  const grid = $("#dataset-grid");
  grid.innerHTML = "";

  const filtrados = datasetFiltro === "todos" ? datasetCache :
                    datasetFiltro === "trampas" ? datasetCache.filter(c => c.es_trampa) :
                    datasetCache.filter(c => !c.es_trampa);

  filtrados.forEach(caso => {
    const carta = document.createElement("div");
    carta.className = "dataset-carta";

    const tipo = caso.documento?.tipo_documento || "factura";
    const resumen = JSON.stringify(caso.documento, null, 0).slice(0, 120);

    carta.innerHTML = `
      <div class="dataset-carta-id">
        ${caso.id}
        ${caso.es_trampa ? '<span class="dataset-carta-trampa">Trampa</span>' : ''}
      </div>
      <div class="dataset-carta-tipo">${tipo}</div>
      <div class="dataset-carta-body">${resumen}...</div>
    `;

    carta.addEventListener("click", () => {
      verDetalleDirecto(caso);
    });

    grid.appendChild(carta);
  });
}

function verDetalleDirecto(caso) {
  navegarA("detalle");

  $("#detalle-titulo").textContent = caso.id;
  $("#detalle-sub").textContent = caso.es_trampa ? t("caso_trampa") : t("caso_normal");

  const docLimpio = {};
  for (const [k, v] of Object.entries(caso.documento)) {
    if (!k.startsWith("_")) docLimpio[k] = v;
  }
  $("#detalle-documento").textContent = JSON.stringify(docLimpio, null, 2);

  const espLimpio = {};
  for (const [k, v] of Object.entries(caso.esperado)) {
    if (!k.startsWith("_")) espLimpio[k] = v;
  }
  $("#detalle-esperado").textContent = JSON.stringify(espLimpio, null, 2);
  $("#detalle-obtenido").textContent = "// " + t("sin_resultado");
  $("#detalle-campos").innerHTML = `<p style="color: var(--tinta-tenue); font-size: 0.85rem;">${t("sin_resultado")}</p>`;
}

/* ─── Events ─────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", () => {
  initTema();
  initIdioma();

  // Navigation
  $$(".nav-link").forEach(link => {
    link.addEventListener("click", () => navegarA(link.dataset.pantalla));
  });

  // Theme toggle
  $("#btn-tema").addEventListener("click", toggleTema);

  // Language selector
  $("#select-idioma").addEventListener("change", e => cambiarIdioma(e.target.value));

  // Country selector
  $("#select-pais").addEventListener("change", async e => {
    paisActual = e.target.value;
    await cargarMotores();
    await cargarComparativa();
    if ($("#pantalla-dataset").classList.contains("activa")) await cargarDataset();
  });

  // Execute
  $("#btn-ejecutar").addEventListener("click", ejecutarLote);

  // Dataset filters
  $$(".dataset-filtro").forEach(btn => {
    btn.addEventListener("click", () => {
      $$(".dataset-filtro").forEach(b => b.classList.remove("activo"));
      btn.classList.add("activo");
      datasetFiltro = btn.dataset.filtro;
      renderizarDataset();
    });
  });

  // Back button
  $("#btn-volver-ejecucion").addEventListener("click", () => navegarA("ejecucion"));

  // Initial load
  cargarPaises();
  cargarMotores();
  cargarComparativa();
});