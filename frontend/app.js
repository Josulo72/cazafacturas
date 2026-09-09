/* Cazafacturas — interfaz.
   Sin framework y sin compilación: se abre el fichero y se lee. */

import { IDIOMAS, aplicar, fijarIdioma, idiomaActual, idiomaGuardado, t } from './i18n.js';

const API = '/api';
const $ = (sel, raiz = document) => raiz.querySelector(sel);
const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

const estado = {
  capacidades: null,
  paises: [],
  pais: '',
  lote: null,
  vistaPrevia: 'revisar',
};

const LOCALES = { ES: 'es-ES', UK: 'en-GB', US: 'en-US', DE: 'de-DE' };
const MONEDAS = { ES: 'EUR', UK: 'GBP', US: 'USD', DE: 'EUR' };

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

function importe(valor, pais = 'ES') {
  if (valor === null || valor === undefined || valor === '') return '—';
  const n = Number(valor);
  if (!Number.isFinite(n)) return esc(valor);
  return new Intl.NumberFormat(LOCALES[pais] || 'es-ES', {
    style: 'currency',
    currency: MONEDAS[pais] || 'EUR',
    minimumFractionDigits: 2,
  }).format(n);
}

function fecha(valor, pais = 'ES') {
  if (!valor) return '—';
  const d = new Date(String(valor).slice(0, 10));
  if (Number.isNaN(d.getTime())) return esc(valor);
  return new Intl.DateTimeFormat(LOCALES[pais] || 'es-ES', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  }).format(d);
}

function fechaHora(valor) {
  if (!valor) return '—';
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return esc(valor);
  return new Intl.DateTimeFormat(LOCALES[estado.pais] || 'es-ES', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(d);
}

const porcentaje = (v) => `${(Number(v || 0) * 100).toFixed(1).replace('.0', '')} %`;

/** Un valor cualquiera, legible: las cifras con separadores del país. */
function valorLegible(v, pais = 'ES') {
  if (v === null || v === undefined) return '—';
  if (Array.isArray(v)) return v.map((x) => valorLegible(x, pais)).join(', ');
  if (typeof v === 'number') {
    return new Intl.NumberFormat(LOCALES[pais] || 'es-ES', {
      minimumFractionDigits: Number.isInteger(v) ? 0 : 2,
      maximumFractionDigits: 2,
    }).format(v);
  }
  return String(v);
}

async function pedir(ruta, opciones) {
  const r = await fetch(API + ruta, opciones);
  if (!r.ok) {
    let detalle = `${r.status}`;
    try { detalle = (await r.json()).detail || detalle; } catch (_) { /* sin cuerpo */ }
    throw new Error(detalle);
  }
  return r.json();
}

function mostrarError(mensaje) {
  const caja = $('#aviso-error');
  caja.querySelector('span')?.remove();
  caja.textContent = mensaje;
  caja.hidden = false;
  setTimeout(() => { caja.hidden = true; }, 9000);
}

/* ------------------------------------------------------------------ */
/* Preferencias                                                        */
/* ------------------------------------------------------------------ */

function leer(clave, porDefecto) {
  try { return localStorage.getItem(clave) ?? porDefecto; } catch (_) { return porDefecto; }
}
function guardar(clave, valor) {
  try { localStorage.setItem(clave, valor); } catch (_) { /* modo privado */ }
}

function aplicarTema(tema) {
  document.documentElement.dataset.tema = tema;
  const oscuro = tema === 'oscuro';
  $('#btn-tema').setAttribute('aria-pressed', String(oscuro));
  $('#btn-tema-texto').textContent = t(oscuro ? 'tema_claro' : 'tema_oscuro');
  guardar('cazafacturas:tema', tema);
}

/* ------------------------------------------------------------------ */
/* Navegación                                                          */
/* ------------------------------------------------------------------ */

function irA(vista) {
  if (vista !== 'detalle') estado.vistaPrevia = vista;
  $$('.vista').forEach((s) => s.classList.toggle('activa', s.id === `v-${vista}`));
  $$('.unhero').forEach((b) => {
    const activo = b.dataset.vista === vista;
    b.classList.toggle('activo', activo);
    if (activo) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  if (vista === 'historial') cargarHistorial();
  window.scrollTo({ top: 0, behavior: 'instant' });
}

/* ------------------------------------------------------------------ */
/* El libro                                                            */
/* ------------------------------------------------------------------ */

function marcaEstado(r) {
  if (!r.ok) return { clase: 'm-mal', icono: 'i-aspa', texto: t('ilegible'), fila: 'f-error' };
  const inf = r.informe || {};
  if (inf.n_errores) return { clase: 'm-mal', icono: 'i-aspa', texto: t('no_conforme'), fila: 'f-error' };
  if (inf.n_avisos) return { clase: 'm-aviso', icono: 'i-admiracion', texto: t('con_avisos'), fila: 'f-aviso' };
  return { clase: 'm-bien', icono: 'i-llamada', texto: t('conforme'), fila: '' };
}

function pintarLibro(lote, { animar = false } = {}) {
  estado.lote = lote;
  const cuerpo = $('#libro-cuerpo');
  const pie = $('#libro-pie');
  const resultados = lote?.resultados || [];

  $('#zona').classList.toggle('plegada', resultados.length > 0);
  $('#libro-envoltura').hidden = resultados.length === 0;
  $('#vacio-libro').hidden = resultados.length !== 0;
  $('#btn-exportar').hidden = resultados.length === 0;
  $('#btn-vaciar').hidden = resultados.length === 0;
  if (!resultados.length) { cuerpo.innerHTML = ''; pie.innerHTML = ''; return; }

  cuerpo.innerHTML = resultados.map((r, i) => {
    const f = r.factura || {};
    const inf = r.informe || {};
    const pais = inf.pais || 'ES';
    const m = marcaEstado(r);
    const malCifra = (inf.hallazgos || []).some((h) => h.campo === 'total' || h.campo === 'base_imponible');
    const impuesto = (f.iva || []).reduce((s, x) => s + Number(x.cuota || 0), 0);

    return `<tr class="${m.fila} ${animar ? 'nueva' : ''}" data-indice="${i}" tabindex="0" style="animation-delay:${Math.min(i * 28, 400)}ms">
      <td class="c-folio">${i + 1}</td>
      <td class="c-doc" title="${esc(r.nombre)}">${esc(r.nombre)}</td>
      <td>${esc(f.numero || '—')}</td>
      <td>${fecha(f.fecha_emision, pais)}</td>
      <td class="c-emisor" title="${esc(f.emisor?.nombre || '')}">${esc(f.emisor?.nombre || '—')}</td>
      <td class="c-cifra ${malCifra ? 'cifra-mal' : ''}">${importe(f.base_imponible, pais)}</td>
      <td class="c-cifra">${impuesto ? importe(impuesto, pais) : '—'}</td>
      <td class="c-cifra ${malCifra ? 'cifra-mal' : ''}">${importe(f.total, pais)}</td>
      <td class="c-estado"><span class="marca-estado ${m.clase}">
        <svg class="icono" aria-hidden="true"><use href="#${m.icono}"/></svg>${esc(m.texto)}</span></td>
    </tr>`;
  }).join('');

  // Pie de columna: la suma, y doble raya si todo el lote cuadra.
  const pais = resultados[0]?.informe?.pais || 'ES';
  const sumaBase = resultados.reduce((s, r) => s + Number(r.factura?.base_imponible || 0), 0);
  const sumaImp = resultados.reduce((s, r) => s
    + (r.factura?.iva || []).reduce((a, x) => a + Number(x.cuota || 0), 0), 0);
  const sumaTotal = resultados.reduce((s, r) => s + Number(r.factura?.total || 0), 0);
  const cuadra = resultados.every((r) => r.ok && r.informe?.valida);

  pie.innerHTML = `<tr class="${cuadra ? 'cuadra' : ''}">
    <td class="c-folio"></td>
    <td colspan="3"><span class="pie-etiqueta">${t('suma')}</span></td>
    <td class="pie-etiqueta">${resultados.length} ${resultados.length === 1 ? t('documento') : t('documentos')}</td>
    <td class="c-cifra">${importe(sumaBase, pais)}</td>
    <td class="c-cifra">${importe(sumaImp, pais)}</td>
    <td class="c-cifra">${importe(sumaTotal, pais)}</td>
    <td class="c-estado pie-etiqueta">${lote.validas}/${lote.total}</td>
  </tr>`;

  $$('#libro-cuerpo tr').forEach((tr) => {
    const abrir = () => verDetalle(Number(tr.dataset.indice));
    tr.addEventListener('click', abrir);
    tr.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrir(); }
    });
  });
}

/* ------------------------------------------------------------------ */
/* Detalle de un documento                                             */
/* ------------------------------------------------------------------ */

const ORIGENES = {
  capa_texto: 'origen_capa_texto', ocr: 'origen_ocr',
  mixto: 'origen_mixto', vacio: 'origen_vacio', json: 'origen_json',
};

function bloqueConfianza(valor) {
  const pct = Number(valor || 0);
  const baja = pct < 0.7;
  return `<span class="confianza ${baja ? 'confianza-baja' : ''}">
    <span class="confianza-cifra">${porcentaje(pct)}</span>
    <span class="confianza-regla" style="--nivel:${(pct * 100).toFixed(0)}%"></span>
  </span>`;
}

function verDetalle(indice) {
  const r = estado.lote?.resultados?.[indice];
  if (!r) return;
  const f = r.factura || {};
  const inf = r.informe || {};
  const pais = inf.pais || 'ES';
  const doc = r.documento || {};
  const hallazgos = inf.hallazgos || [];
  const errores = hallazgos.filter((h) => h.gravedad === 'error');

  const bien = r.ok && inf.valida;
  const total = 20; // comprobaciones que aplica el validador

  let html = `
  <div class="veredicto ${bien ? '' : 'veredicto-mal'}">
    <div class="sello ${bien ? '' : 'sello-mal'}">
      <p class="veredicto-palabra">${bien ? t('veredicto_bien') : t('veredicto_mal')}</p>
    </div>
    <div>
      <p class="veredicto-fichero">${esc(r.nombre)}</p>
      <p class="veredicto-pie">${bien
        ? t('veredicto_bien_pie', { n: total })
        : t(errores.length === 1 ? 'veredicto_mal_pie_uno' : 'veredicto_mal_pie',
             { n: errores.length })}</p>
    </div>
  </div>`;

  if (!r.ok) {
    html += `<p class="aviso-sistema aviso-error">${esc(r.error)}</p>`;
    $('#detalle-cuerpo').innerHTML = html;
    irA('detalle');
    return;
  }

  // Trazabilidad
  html += `<section class="seccion">
    <h3 class="seccion-titulo">${t('trazabilidad')}</h3>
    <dl class="trazas">
      <div class="traza"><dt>${t('tz_origen')}</dt><dd>${t(ORIGENES[doc.origen] || 'origen_vacio')}</dd></div>
      <div class="traza"><dt>${t('tz_paginas')}</dt><dd>${doc.paginas ?? '—'}</dd></div>
      <div class="traza"><dt>${t('tz_confianza')}</dt><dd>${porcentaje(doc.confianza)}</dd></div>
      <div class="traza"><dt>${t('tz_pais')}</dt><dd>${esc(pais)}</dd></div>
      <div class="traza"><dt>${t('tz_tiempo')}</dt><dd>${Number(r.segundos || 0).toFixed(2)} s</dd></div>
    </dl>
  </section>`;

  // Hallazgos: lo primero que importa cuando algo va mal.
  html += `<section class="seccion">
    <h3 class="seccion-titulo">${t('hallazgos')}</h3>`;
  if (!hallazgos.length) {
    html += `<p class="glosa">${t('sin_hallazgos')}</p>`;
  } else {
    html += hallazgos.map((h) => {
      const clase = h.gravedad === 'error' ? '' : `hallazgo-${h.gravedad}`;
      const etiqueta = t(`gravedad_${h.gravedad}`);
      const hayContraste = h.esperado !== null && h.esperado !== undefined;
      return `<div class="hallazgo ${clase}">
        <div class="hallazgo-cabeza">
          <span class="hallazgo-grav">${etiqueta}</span>
          <span class="hallazgo-campo">${esc(h.campo)}</span>
        </div>
        <p class="hallazgo-texto">${esc(h.mensaje)}</p>
        ${hayContraste ? `<div class="contraste">
          <span class="contraste-par"><span class="contraste-et">${t('esperado')}</span>
            <span class="contraste-bien">${esc(valorLegible(h.esperado, pais))}</span></span>
          <span class="contraste-par"><span class="contraste-et">${t('encontrado')}</span>
            <span class="contraste-mal">${esc(valorLegible(h.encontrado, pais))}</span></span>
        </div>` : ''}
      </div>`;
    }).join('');
  }
  html += `</section>`;

  // Campos leídos, con confianza y procedencia
  const campos = r.extraccion?.campos || {};
  if (Object.keys(campos).length) {
    html += `<section class="seccion">
      <h3 class="seccion-titulo">${t('campos_leidos')}</h3>
      <table class="tabla"><thead><tr>
        <th>${t('col_campo')}</th><th>${t('col_valor')}</th>
        <th class="c-cifra">${t('col_confianza')}</th><th>${t('col_pista')}</th>
      </tr></thead><tbody>
      ${Object.entries(campos).map(([nombre, c]) => `<tr>
        <td>${esc(nombre.replace(/_/g, ' '))}</td>
        <td>${esc(valorLegible(c.valor, pais))}</td>
        <td class="c-cifra">${bloqueConfianza(c.confianza)}</td>
        <td class="pista">${esc(c.pista)}</td>
      </tr>`).join('')}
      </tbody></table>
    </section>`;
  }

  // Líneas de detalle, con su pie de columna
  if ((f.lineas || []).length) {
    const suma = f.lineas.reduce((s, l) => s + Number(l.importe || 0), 0);
    const cuadraBase = Math.abs(suma - Number(f.base_imponible || 0)) <= 0.02;
    html += `<section class="seccion">
      <h3 class="seccion-titulo">${t('lineas_detalle')}</h3>
      <table class="tabla"><thead><tr>
        <th>${t('col_concepto')}</th>
        <th class="c-cifra">${t('col_cantidad')}</th>
        <th class="c-cifra">${t('col_precio')}</th>
        <th class="c-cifra">${t('col_importe')}</th>
      </tr></thead><tbody>
      ${f.lineas.map((l) => `<tr>
        <td>${esc(l.descripcion)}</td>
        <td class="c-cifra">${Number(l.cantidad ?? 0).toLocaleString(LOCALES[pais])}</td>
        <td class="c-cifra">${importe(l.precio_unitario, pais)}</td>
        <td class="c-cifra">${importe(l.importe, pais)}</td>
      </tr>`).join('')}
      </tbody>
      <tfoot><tr class="${cuadraBase ? 'cuadra' : ''}">
        <td colspan="3"><span class="pie-etiqueta">${t('col_base')}</span></td>
        <td class="c-cifra ${cuadraBase ? '' : 'cifra-mal'}">${importe(f.base_imponible, pais)}</td>
      </tr></tfoot>
      </table>
    </section>`;
  }

  $('#detalle-cuerpo').innerHTML = html;
  irA('detalle');
}

/* ------------------------------------------------------------------ */
/* Subida y análisis                                                   */
/* ------------------------------------------------------------------ */

function seguirTrabajo(idTrabajo, { riel, texto }, alTerminar) {
  const fuente = new EventSource(`${API}/trabajos/${idTrabajo}/stream`);

  fuente.onmessage = (ev) => {
    const d = JSON.parse(ev.data);
    const pct = d.total ? (d.pos / d.total) * 100 : 0;
    riel.style.transform = `scaleX(${pct / 100})`;
    texto.textContent = d.actual
      ? `${d.pos}/${d.total} · ${d.actual}`
      : `${t('en_cola')}…`;
  };

  fuente.addEventListener('fin', async (ev) => {
    fuente.close();
    const d = JSON.parse(ev.data);
    riel.style.transform = 'scaleX(1)';
    try {
      alTerminar(await pedir(`/historial/${d.id_lote}`));
    } catch (e) { mostrarError(e.message); }
  });

  fuente.addEventListener('error', (ev) => {
    fuente.close();
    let mensaje = t('error_red');
    try { mensaje = JSON.parse(ev.data)?.estado || mensaje; } catch (_) { /* sin cuerpo */ }
    mostrarError(mensaje);
    alTerminar(null);
  });
}

async function analizar(ficheros) {
  if (!ficheros.length) return;
  const caps = estado.capacidades;
  if (ficheros.length > caps.max_ficheros) {
    mostrarError(t('demasiados', { n: caps.max_ficheros }));
    return;
  }
  for (const f of ficheros) {
    const ext = `.${f.name.split('.').pop().toLowerCase()}`;
    if (!caps.formatos.includes(ext)) { mostrarError(`«${f.name}» ${t('formato_no')}`); return; }
    if (f.size > caps.max_mb * 1024 * 1024) {
      mostrarError(`«${f.name}» ${t('muy_grande', { n: caps.max_mb })}`); return;
    }
  }

  const cuerpo = new FormData();
  ficheros.forEach((f) => cuerpo.append('ficheros', f, f.name));
  if (estado.pais) cuerpo.append('pais', estado.pais);

  $('#progreso').hidden = false;
  $('#progreso-pluma').style.transform = 'scaleX(0)';
  $('#progreso-texto').textContent = `${t('en_cola')}…`;
  $('#btn-elegir').disabled = true;
  $('#btn-muestras').disabled = true;

  try {
    const { id_trabajo: id } = await pedir('/analizar', { method: 'POST', body: cuerpo });
    seguirTrabajo(id, { riel: $('#progreso-pluma'), texto: $('#progreso-texto') }, (lote) => {
      $('#btn-elegir').disabled = false;
      $('#btn-muestras').disabled = false;
      setTimeout(() => { $('#progreso').hidden = true; }, 400);
      if (lote) pintarLibro(lote, { animar: true });
    });
  } catch (e) {
    mostrarError(e.message);
    $('#progreso').hidden = true;
    $('#btn-elegir').disabled = false;
    $('#btn-muestras').disabled = false;
  }
}

async function cargarMuestras() {
  try {
    const muestras = await pedir('/muestras');
    if (!muestras.length) { mostrarError(t('error_red')); return; }
    // Una mezcla honesta y repartida: una factura por país y tres trampas
    // de tipos distintos. Coger las primeras de la lista daría cuatro
    // albaranes alemanes y no enseñaría nada.
    const porGrupo = new Map();
    muestras.filter((m) => !m.es_trampa).forEach((m) => {
      const cola = porGrupo.get(m.grupo) || [];
      cola.push(m);
      porGrupo.set(m.grupo, cola);
    });
    const normales = [...porGrupo.values()].flatMap((cola) => cola.slice(0, 1));

    const familia = (nombre) => nombre.replace(/_(es|uk|us|de)?_?documento\.pdf$/, '');
    const vistas = new Set();
    const trampas = [];
    for (const m of muestras.filter((x) => x.es_trampa)) {
      const f = familia(m.nombre);
      if (vistas.has(f)) continue;
      vistas.add(f);
      trampas.push(m);
      if (trampas.length === 4) break;
    }
    const elegidas = [...normales, ...trampas];

    $('#btn-muestras').disabled = true;
    const ficheros = await Promise.all(elegidas.map(async (m) => {
      const r = await fetch(m.url);
      return new File([await r.blob()], m.nombre, { type: 'application/pdf' });
    }));
    await analizar(ficheros);
  } catch (e) {
    mostrarError(e.message);
    $('#btn-muestras').disabled = false;
  }
}

/* ------------------------------------------------------------------ */
/* Banco de pruebas                                                    */
/* ------------------------------------------------------------------ */

async function lanzarBanco() {
  const trampas = $('#chk-trampas').checked;
  $('#btn-banco').disabled = true;
  $('#progreso-banco').hidden = false;
  $('#progreso-banco-pluma').style.transform = 'scaleX(0)';
  $('#progreso-banco-texto').textContent = `${t('en_cola')}…`;

  try {
    const { id_trabajo: id } = await pedir(`/banco?trampas=${trampas}`, { method: 'POST' });
    seguirTrabajo(id, {
      riel: $('#progreso-banco-pluma'),
      texto: $('#progreso-banco-texto'),
    }, (lote) => {
      $('#btn-banco').disabled = false;
      setTimeout(() => { $('#progreso-banco').hidden = true; }, 400);
      if (lote) pintarBanco(lote);
    });
  } catch (e) {
    mostrarError(e.message);
    $('#btn-banco').disabled = false;
    $('#progreso-banco').hidden = true;
  }
}

function pintarBanco(lote) {
  const conEsperado = lote.resultados.filter((r) => r.puntuacion);
  const trampas = lote.resultados.filter((r) => !r.puntuacion);
  const cazadas = trampas.filter((r) => (r.informe?.hallazgos || []).length).length;
  const conformes = conEsperado.filter((r) => r.informe?.valida).length;

  const falloPrecision = lote.precision_media !== null && lote.precision_media < 1;
  const falloConformes = conformes < conEsperado.length;
  const falloTrampas = cazadas < trampas.length;

  let html = `<div class="marcador">
    <div class="marcador-celda ${falloPrecision ? 'marcador-mal' : ''}">
      <div class="marcador-et">${t('banco_precision')}</div>
      <div class="marcador-cifra">${lote.precision_media === null ? '—' : porcentaje(lote.precision_media)}</div>
    </div>
    <div class="marcador-celda ${falloConformes ? 'marcador-mal' : ''}">
      <div class="marcador-et">${t('banco_validas')}</div>
      <div class="marcador-cifra">${conformes}/${conEsperado.length}</div>
    </div>
    <div class="marcador-celda ${falloTrampas ? 'marcador-mal' : ''}">
      <div class="marcador-et">${t('banco_trampas')}</div>
      <div class="marcador-cifra">${cazadas}/${trampas.length}</div>
    </div>
    <div class="marcador-celda">
      <div class="marcador-et">${t('banco_tiempo')}</div>
      <div class="marcador-cifra">${Number(lote.segundos).toFixed(1)}<span style="font-size:1rem"> s</span></div>
    </div>
  </div>`;

  html += `<div class="libro-envoltura"><table class="tabla"><thead><tr>
    <th class="c-folio">${t('col_folio')}</th>
    <th>${t('col_caso')}</th>
    <th>${t('col_veredicto')}</th>
    <th class="c-cifra">${t('col_precision')}</th>
  </tr></thead><tbody>
  ${lote.resultados.map((r, i) => {
    const esTrampa = !r.puntuacion;
    const hallazgos = (r.informe?.hallazgos || []).length;
    const bien = esTrampa ? hallazgos > 0 : r.informe?.valida;
    const m = bien
      ? { c: 'm-bien', i: 'i-llamada' }
      : { c: 'm-mal', i: 'i-aspa' };
    const veredicto = esTrampa
      ? t(hallazgos > 0 ? 'trampa_cazada' : 'trampa_escapada')
      : t(r.informe?.valida ? 'conforme' : 'no_conforme');
    return `<tr class="${bien ? '' : 'f-error'}">
      <td class="c-folio">${i + 1}</td>
      <td class="c-doc">${esc(r.nombre)}</td>
      <td><span class="marca-estado ${m.c}">
        <svg class="icono" aria-hidden="true"><use href="#${m.i}"/></svg>${esc(veredicto)}</span></td>
      <td class="c-cifra">${r.puntuacion ? porcentaje(r.puntuacion.precision) : '—'}</td>
    </tr>`;
  }).join('')}
  </tbody></table></div>`;

  $('#banco-cuerpo').innerHTML = html;
}

/* ------------------------------------------------------------------ */
/* Historial                                                           */
/* ------------------------------------------------------------------ */

async function cargarHistorial() {
  try {
    const lotes = await pedir('/historial');
    const caja = $('#historial-cuerpo');
    if (!lotes.length) {
      caja.innerHTML = `<div class="vacio"><p class="vacio-titulo">${t('vacio_historial')}</p></div>`;
      return;
    }
    caja.innerHTML = `<div class="libro-envoltura"><table class="tabla"><thead><tr>
      <th class="c-folio">${t('col_folio')}</th>
      <th>${t('hist_fecha')}</th>
      <th>${t('hist_origen')}</th>
      <th class="c-cifra">${t('hist_docs')}</th>
      <th class="c-cifra">${t('hist_conformes')}</th>
      <th class="c-cifra">${t('hist_errores')}</th>
      <th></th>
    </tr></thead><tbody>
    ${lotes.map((l, i) => `<tr data-lote="${esc(l.id)}" tabindex="0" class="${l.con_errores ? 'f-error' : ''}">
      <td class="c-folio">${i + 1}</td>
      <td>${fechaHora(l.fecha)}</td>
      <td>${t(l.origen === 'banco' ? 'origen_banco' : 'origen_subida')}</td>
      <td class="c-cifra">${l.total}</td>
      <td class="c-cifra">${l.validas}</td>
      <td class="c-cifra ${l.con_errores ? 'cifra-mal' : ''}">${l.con_errores}</td>
      <td class="c-cifra"><button class="boton boton-tenue" type="button" data-borrar="${esc(l.id)}">
        <svg class="icono" aria-hidden="true"><use href="#i-papelera"/></svg>
        <span class="oculto-visual">${t('borrar')}</span></button></td>
    </tr>`).join('')}
    </tbody></table></div>`;

    $$('#historial-cuerpo tr[data-lote]').forEach((tr) => {
      const abrir = async () => {
        try {
          pintarLibro(await pedir(`/historial/${tr.dataset.lote}`));
          irA('revisar');
        } catch (e) { mostrarError(e.message); }
      };
      tr.addEventListener('click', (e) => {
        if (e.target.closest('[data-borrar]')) return;
        abrir();
      });
      tr.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); abrir(); }
      });
    });

    $$('#historial-cuerpo [data-borrar]').forEach((b) => {
      b.addEventListener('click', async (e) => {
        e.stopPropagation();
        try {
          await pedir(`/historial/${b.dataset.borrar}`, { method: 'DELETE' });
          cargarHistorial();
        } catch (err) { mostrarError(err.message); }
      });
    });
  } catch (e) { mostrarError(e.message); }
}

/* ------------------------------------------------------------------ */
/* Arranque                                                            */
/* ------------------------------------------------------------------ */

function montarSelectores() {
  const selIdioma = $('#sel-idioma');
  selIdioma.innerHTML = Object.entries(IDIOMAS)
    .map(([c, n]) => `<option value="${c}">${n}</option>`).join('');
  selIdioma.value = idiomaActual();

  const selPais = $('#sel-pais');
  selPais.innerHTML = `<option value="">${t('pais_auto')}</option>`
    + estado.paises.map((p) => `<option value="${p.codigo}">${esc(idiomaActual() === 'es' ? p.es : p.en)}</option>`).join('');
  selPais.value = estado.pais;
}

function retraducir() {
  aplicar();
  montarSelectores();
  aplicarTema(document.documentElement.dataset.tema);
  if (estado.lote) pintarLibro(estado.lote);
  if ($('#v-historial').classList.contains('activa')) cargarHistorial();
}

async function arrancar() {
  fijarIdioma(idiomaGuardado());
  aplicarTema(leer('cazafacturas:tema', 'claro'));
  aplicar();

  try {
    const [caps, paises] = await Promise.all([pedir('/capacidades'), pedir('/paises')]);
    estado.capacidades = caps;
    estado.paises = paises;
    estado.pais = leer('cazafacturas:pais', '');

    $('#aviso-ocr').hidden = caps.escaneados;
    $('#pie-version').textContent = `v${caps.version}`;
    $('#pie-capacidades').textContent = caps.escaneados
      ? `PDF · OCR · ${caps.formatos.length} formatos`
      : 'Solo PDF con texto';
  } catch (e) {
    mostrarError(t('error_red'));
    estado.capacidades = { formatos: ['.pdf'], max_ficheros: 50, max_mb: 25, escaneados: false };
  }

  montarSelectores();
  pintarLibro(null);

  // --- Eventos ---
  $('#sel-idioma').addEventListener('change', (e) => { fijarIdioma(e.target.value); retraducir(); });
  $('#sel-pais').addEventListener('change', (e) => {
    estado.pais = e.target.value;
    guardar('cazafacturas:pais', estado.pais);
  });
  $('#btn-tema').addEventListener('click', () => {
    aplicarTema(document.documentElement.dataset.tema === 'oscuro' ? 'claro' : 'oscuro');
  });

  $$('.unhero').forEach((b) => b.addEventListener('click', () => irA(b.dataset.vista)));
  $('#btn-volver').addEventListener('click', () => irA(estado.vistaPrevia));

  const entrada = $('#entrada-fichero');
  const zona = $('#zona');
  const abrirSelector = () => entrada.click();

  $('#btn-elegir').addEventListener('click', (e) => { e.stopPropagation(); abrirSelector(); });
  $('#btn-muestras').addEventListener('click', (e) => { e.stopPropagation(); cargarMuestras(); });
  zona.addEventListener('click', abrirSelector);
  zona.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); abrirSelector(); }
  });
  entrada.addEventListener('change', () => {
    analizar([...entrada.files]);
    entrada.value = '';
  });

  ['dragenter', 'dragover'].forEach((ev) => zona.addEventListener(ev, (e) => {
    e.preventDefault(); zona.classList.add('encima');
  }));
  ['dragleave', 'drop'].forEach((ev) => zona.addEventListener(ev, (e) => {
    e.preventDefault();
    if (ev === 'dragleave' && zona.contains(e.relatedTarget)) return;
    zona.classList.remove('encima');
  }));
  zona.addEventListener('drop', (e) => analizar([...e.dataTransfer.files]));

  $('#btn-exportar').addEventListener('click', () => {
    if (estado.lote) window.location.href = `${API}/historial/${estado.lote.id}/csv`;
  });
  $('#btn-vaciar').addEventListener('click', () => pintarLibro(null));
  $('#btn-banco').addEventListener('click', lanzarBanco);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && $('#v-detalle').classList.contains('activa')) irA(estado.vistaPrevia);
  });
}

arrancar();
