/* La portada: dos actos y una puerta.
   No hay biblioteca de animación. Los trazos se revelan con
   stroke-dashoffset, que es literalmente la punta del boli avanzando, y el
   guion se lleva desde aquí porque cada acto tiene que esperar al anterior. */

const $ = (sel) => document.querySelector(sel);

/* Cuánto dura cada acto. Se calcula del propio SVG, no se escribe a mano:
   si mañana muevo un retardo, el guion se entera solo. */
function duracion(escena) {
  let fin = 0;
  escena.querySelectorAll('[style*="--esp"]').forEach((el) => {
    const esp = parseFloat(getComputedStyle(el).getPropertyValue('--esp')) || 0;
    const dur = parseFloat(getComputedStyle(el).getPropertyValue('--dur')) || 0.5;
    fin = Math.max(fin, esp + dur);
  });
  return (fin + 1.1) * 1000;   // un respiro antes de pasar página
}

/* Cada trazo necesita saber lo que mide para poder revelarse. Se lo
   preguntamos al SVG en vez de calcularlo a ojo. */
function medir(raiz) {
  raiz.querySelectorAll('path.traza').forEach((p) => {
    p.style.setProperty('--largo', Math.ceil(p.getTotalLength()) + 1);
  });
}

const actos = [$('#acto-1'), $('#acto-2')];
const final = $('#acto-final');
const saltar = $('#saltar');

let temporizadores = [];
const cancelar = () => { temporizadores.forEach(clearTimeout); temporizadores = []; };
const esperar = (ms, fn) => temporizadores.push(setTimeout(fn, ms));

function mostrar(el, visible) {
  el.classList.toggle('en-escena', visible);
  el.setAttribute('aria-hidden', String(!visible));
}

/* Reiniciar un acto: clonar el SVG reinicia las animaciones CSS de golpe.
   El reloj de SMIL va aparte y hay que devolverlo al principio a mano. */
function reiniciar(acto) {
  const viejo = acto.querySelector('svg');
  const nuevo = viejo.cloneNode(true);
  viejo.replaceWith(nuevo);
  medir(nuevo);
  if (typeof nuevo.setCurrentTime === 'function') nuevo.setCurrentTime(0);
  return nuevo;
}

function alFinal({ animado = true } = {}) {
  cancelar();
  actos.forEach((a) => mostrar(a, false));
  mostrar(final, true);
  final.classList.toggle('sin-entrada', !animado);
  saltar.hidden = true;
  document.body.classList.add('terminado');
  try { localStorage.setItem('cazafacturas:portada-vista', '1'); } catch (_) { /* modo privado */ }
  $('#entrar')?.focus?.();
}

function representar() {
  cancelar();
  document.body.classList.remove('terminado');
  final.classList.remove('sin-entrada');
  mostrar(final, false);
  saltar.hidden = false;

  const svg1 = reiniciar(actos[0]);
  mostrar(actos[0], true);
  mostrar(actos[1], false);

  const d1 = duracion(svg1);
  esperar(d1, () => {
    // La hoja se retira y entra la siguiente del talonario.
    actos[0].classList.add('se-retira');
    const svg2 = reiniciar(actos[1]);
    esperar(420, () => {
      mostrar(actos[0], false);
      actos[0].classList.remove('se-retira');
      mostrar(actos[1], true);
      esperar(duracion(svg2), () => alFinal());
    });
  });
}

// --- Entradas del usuario -------------------------------------------------

saltar.addEventListener('click', () => alFinal({ animado: false }));
$('#repetir').addEventListener('click', representar);

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !saltar.hidden) alFinal({ animado: false });
});

// --- Arranque -------------------------------------------------------------

const reducido = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let yaVista = false;
try { yaVista = localStorage.getItem('cazafacturas:portada-vista') === '1'; } catch (_) { /* modo privado */ }

// Quien ya la ha visto entra directo. Nadie quiere la misma función dos veces,
// y «Volver a ver» sigue ahí para quien la quiera.
if (reducido || yaVista) alFinal({ animado: false });
else representar();
