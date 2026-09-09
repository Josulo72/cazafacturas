/* Cadenas de la interfaz. El español es el original: el dominio es fiscal
   español y los términos nacen en castellano. El inglés traduce el concepto,
   no la palabra (una "base imponible" no es una "taxable base"). */

export const IDIOMAS = { es: 'Español', en: 'English' };

const es = {
  producto: 'Cazafacturas',
  lema: 'Extrae y comprueba facturas en tu máquina. Sin IA, sin red, sin claves.',

  // Uñeros
  revisar: 'Revisar',
  banco: 'Banco de pruebas',
  historial: 'Historial',

  // Controles de cabecera
  idioma: 'Idioma',
  pais: 'País',
  pais_auto: 'Detectar',
  tema_claro: 'Papel claro',
  tema_oscuro: 'Papel oscuro',

  // Pantalla de revisión
  revisar_titulo: 'Libro de revisión',
  revisar_sub: 'Cada documento se asienta en un renglón. Lo que no cuadra sale en rojo.',
  soltar_aqui: 'Suelta aquí las facturas',
  soltar_detalle: 'PDF, escaneados o fotos. Nada sale de este ordenador.',
  elegir_ficheros: 'Elegir ficheros',
  probar_muestras: 'Probar con facturas de muestra',
  anotacion_local: 'Ningún documento sale de esta máquina',
  vaciar: 'Vaciar el libro',
  exportar: 'Exportar CSV',

  // Columnas del libro
  col_folio: 'Folio',
  col_documento: 'Documento',
  col_numero: 'Nº factura',
  col_fecha: 'Fecha',
  col_emisor: 'Emisor',
  col_base: 'Base imponible',
  col_impuesto: 'Impuesto',
  col_total: 'Total',
  col_estado: 'Estado',
  col_campo: 'Campo',
  col_valor: 'Valor leído',
  col_confianza: 'Confianza',
  col_pista: 'De dónde sale',
  col_concepto: 'Concepto',
  col_cantidad: 'Cantidad',
  col_precio: 'Precio unitario',
  col_importe: 'Importe',
  col_caso: 'Caso',
  col_veredicto: 'Veredicto',
  col_precision: 'Precisión',

  suma: 'Suma',
  documentos: 'documentos',
  documento: 'documento',

  // Estados
  conforme: 'Conforme',
  no_conforme: 'No conforme',
  con_avisos: 'Con avisos',
  ilegible: 'Ilegible',
  analizando: 'Analizando',
  en_cola: 'En cola',

  // Detalle
  volver: 'Volver al libro',
  veredicto_bien: 'CONFORME',
  veredicto_mal: 'NO CONFORME',
  veredicto_bien_pie: 'Supera las {n} comprobaciones fiscales.',
  veredicto_mal_pie: '{n} de las comprobaciones fiscales no se cumplen.',
  veredicto_mal_pie_uno: 'Una de las comprobaciones fiscales no se cumple.',
  trazabilidad: 'Trazabilidad',
  tz_fichero: 'Fichero',
  tz_origen: 'Origen del texto',
  tz_paginas: 'Páginas',
  tz_confianza: 'Confianza de lectura',
  tz_tiempo: 'Tiempo',
  tz_pais: 'Jurisdicción',
  origen_capa_texto: 'Capa de texto del PDF',
  origen_ocr: 'OCR local',
  origen_mixto: 'Mixto: texto y OCR',
  origen_vacio: 'Sin texto legible',
  origen_json: 'Documento estructurado',
  campos_leidos: 'Campos leídos',
  hallazgos: 'Comprobaciones que no se cumplen',
  sin_hallazgos: 'Las comprobaciones se cumplen todas.',
  lineas_detalle: 'Líneas de detalle',
  esperado: 'Esperaba',
  encontrado: 'Encontró',
  gravedad_error: 'Error',
  gravedad_aviso: 'Aviso',
  gravedad_info: 'Nota',

  // Banco
  banco_titulo: 'Banco de pruebas',
  banco_sub: 'El extractor contra facturas cuyo resultado correcto se conoce de antemano. Mide este código, no un modelo ajeno.',
  banco_lanzar: 'Pasar el banco',
  banco_incluir: 'Incluir casos trampa',
  banco_precision: 'Precisión de extracción',
  banco_validas: 'Facturas conformes',
  banco_trampas: 'Trampas cazadas',
  trampa_cazada: 'Cazada',
  trampa_escapada: 'Se escapó',
  banco_tiempo: 'Tiempo total',
  banco_explica: 'Las facturas normales deben salir conformes; los casos trampa deben ser cazados. Cualquier otra cosa es un fallo del extractor.',

  // Historial
  historial_titulo: 'Historial',
  historial_sub: 'Los lotes analizados, guardados en tu disco.',
  hist_fecha: 'Fecha',
  hist_origen: 'Origen',
  hist_docs: 'Documentos',
  hist_conformes: 'Conformes',
  hist_errores: 'Con errores',
  origen_subida: 'Subida',
  origen_banco: 'Banco',
  borrar: 'Borrar',

  // Vacíos y avisos
  vacio_libro: 'El libro está en blanco.',
  vacio_libro_sub: 'Suelta facturas para asentar el primer renglón.',
  vacio_historial: 'Todavía no has analizado ningún lote.',
  sin_ocr: 'OCR no instalado: los PDF escaneados y las fotos no se pueden leer. Instálalo con',
  formato_no: 'no es un formato admitido.',
  demasiados: 'Máximo {n} ficheros por lote.',
  muy_grande: 'pesa más de {n} MB.',
  error_red: 'No se ha podido contactar con el servidor.',
  hecho_por: 'Hecho por',
};

const en = {
  producto: 'Cazafacturas',
  lema: 'Extract and check invoices on your own machine. No AI, no network, no keys.',

  revisar: 'Review',
  banco: 'Test bench',
  historial: 'History',

  idioma: 'Language',
  pais: 'Country',
  pais_auto: 'Detect',
  tema_claro: 'Light paper',
  tema_oscuro: 'Dark paper',

  revisar_titulo: 'Review ledger',
  revisar_sub: 'Every document gets a line. Whatever fails to balance shows in red.',
  soltar_aqui: 'Drop invoices here',
  soltar_detalle: 'PDFs, scans or photos. Nothing leaves this computer.',
  elegir_ficheros: 'Choose files',
  probar_muestras: 'Try the sample invoices',
  anotacion_local: 'No document leaves this machine',
  vaciar: 'Clear the ledger',
  exportar: 'Export CSV',

  col_folio: 'Folio',
  col_documento: 'Document',
  col_numero: 'Invoice no.',
  col_fecha: 'Date',
  col_emisor: 'Issuer',
  col_base: 'Net amount',
  col_impuesto: 'Tax',
  col_total: 'Total',
  col_estado: 'Status',
  col_campo: 'Field',
  col_valor: 'Value read',
  col_confianza: 'Confidence',
  col_pista: 'Where it came from',
  col_concepto: 'Description',
  col_cantidad: 'Qty',
  col_precio: 'Unit price',
  col_importe: 'Amount',
  col_caso: 'Case',
  col_veredicto: 'Verdict',
  col_precision: 'Accuracy',

  suma: 'Total',
  documentos: 'documents',
  documento: 'document',

  conforme: 'Clean',
  no_conforme: 'Failed',
  con_avisos: 'With warnings',
  ilegible: 'Unreadable',
  analizando: 'Reading',
  en_cola: 'Queued',

  volver: 'Back to the ledger',
  veredicto_bien: 'CLEAN',
  veredicto_mal: 'FAILED',
  veredicto_bien_pie: 'Passes all {n} tax checks.',
  veredicto_mal_pie: '{n} tax checks do not hold.',
  veredicto_mal_pie_uno: 'One tax check does not hold.',
  trazabilidad: 'Provenance',
  tz_fichero: 'File',
  tz_origen: 'Text source',
  tz_paginas: 'Pages',
  tz_confianza: 'Reading confidence',
  tz_tiempo: 'Time',
  tz_pais: 'Jurisdiction',
  origen_capa_texto: 'PDF text layer',
  origen_ocr: 'Local OCR',
  origen_mixto: 'Mixed: text and OCR',
  origen_vacio: 'No readable text',
  origen_json: 'Structured document',
  campos_leidos: 'Fields read',
  hallazgos: 'Checks that do not hold',
  sin_hallazgos: 'Every check holds.',
  lineas_detalle: 'Line items',
  esperado: 'Expected',
  encontrado: 'Found',
  gravedad_error: 'Error',
  gravedad_aviso: 'Warning',
  gravedad_info: 'Note',

  banco_titulo: 'Test bench',
  banco_sub: 'The extractor against invoices whose correct answer is known in advance. It measures this code, not somebody else’s model.',
  banco_lanzar: 'Run the bench',
  banco_incluir: 'Include trap cases',
  banco_precision: 'Extraction accuracy',
  banco_validas: 'Clean invoices',
  banco_trampas: 'Traps caught',
  trampa_cazada: 'Caught',
  trampa_escapada: 'Slipped through',
  banco_tiempo: 'Total time',
  banco_explica: 'Normal invoices must come out clean; trap cases must be caught. Anything else is a defect in the extractor.',

  historial_titulo: 'History',
  historial_sub: 'Analysed batches, stored on your disk.',
  hist_fecha: 'Date',
  hist_origen: 'Source',
  hist_docs: 'Documents',
  hist_conformes: 'Clean',
  hist_errores: 'Failed',
  origen_subida: 'Upload',
  origen_banco: 'Bench',
  borrar: 'Delete',

  vacio_libro: 'The ledger is blank.',
  vacio_libro_sub: 'Drop invoices to write the first line.',
  vacio_historial: 'You have not analysed any batch yet.',
  sin_ocr: 'OCR not installed: scanned PDFs and photos cannot be read. Install it with',
  formato_no: 'is not a supported format.',
  demasiados: 'At most {n} files per batch.',
  muy_grande: 'is larger than {n} MB.',
  error_red: 'Could not reach the server.',
  hecho_por: 'Built by',
};

const TABLAS = { es, en };

let actual = 'es';

export function fijarIdioma(codigo) {
  actual = TABLAS[codigo] ? codigo : 'es';
  document.documentElement.lang = actual;
  try { localStorage.setItem('cazafacturas:idioma', actual); } catch (_) { /* modo privado */ }
}

export function idiomaActual() {
  return actual;
}

export function idiomaGuardado() {
  try {
    const guardado = localStorage.getItem('cazafacturas:idioma');
    if (TABLAS[guardado]) return guardado;
  } catch (_) { /* modo privado */ }
  const navegador = (navigator.language || 'es').slice(0, 2);
  return TABLAS[navegador] ? navegador : 'es';
}

/** Traduce. Admite sustituciones: t('demasiados', { n: 50 }). */
export function t(clave, valores) {
  let texto = TABLAS[actual][clave] ?? TABLAS.es[clave] ?? clave;
  if (valores) {
    for (const [k, v] of Object.entries(valores)) {
      texto = texto.replaceAll(`{${k}}`, String(v));
    }
  }
  return texto;
}

/** Rellena todo lo que lleve data-t en el documento. */
export function aplicar(raiz = document) {
  raiz.querySelectorAll('[data-t]').forEach((el) => {
    el.textContent = t(el.dataset.t);
  });
  raiz.querySelectorAll('[data-t-attr]').forEach((el) => {
    const [attr, clave] = el.dataset.tAttr.split(':');
    el.setAttribute(attr, t(clave));
  });
}
