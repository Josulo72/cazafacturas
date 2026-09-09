/* Guion de los bocetos. Fuera del HTML porque la política de contenido
   no admite scripts en línea, y esa política es deliberada. */

const escenas = { a: document.getElementById('escena-a'), b: document.getElementById('escena-b') };
const botones = [...document.querySelectorAll('[data-boceto]')];
const duracion = document.getElementById('duracion');

/* Cada trazo necesita saber lo que mide para revelarse: se lo preguntamos
   al propio SVG en vez de calcularlo a ojo. */
function medirTrazos(raiz) {
  raiz.querySelectorAll('path.traza').forEach((p) => {
    p.style.setProperty('--largo', Math.ceil(p.getTotalLength()) + 1);
  });
}

function reproducir(cual) {
  Object.entries(escenas).forEach(([k, el]) => el.classList.toggle('activa', k === cual));
  botones.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.boceto === cual)));

  const escena = escenas[cual];
  // Clonar reinicia todas las animaciones de golpe, sin tocarlas una a una.
  const copia = escena.querySelector('svg').cloneNode(true);
  escena.querySelector('svg').replaceWith(copia);
  medirTrazos(copia);
  // El clonado reinicia las animaciones CSS, pero el reloj de SMIL va
  // aparte: hay que devolverlo al principio a mano.
  if (typeof copia.setCurrentTime === 'function') copia.setCurrentTime(0);

  let fin = 0;
  copia.querySelectorAll('[style*="--esp"]').forEach((el) => {
    const esp = parseFloat(getComputedStyle(el).getPropertyValue('--esp')) || 0;
    const dur = parseFloat(getComputedStyle(el).getPropertyValue('--dur')) || 0.5;
    fin = Math.max(fin, esp + dur);
  });
  duracion.textContent = `duración ≈ ${fin.toFixed(1)} s`;
}

botones.forEach((b) => b.addEventListener('click', () => reproducir(b.dataset.boceto)));
document.getElementById('repetir').addEventListener('click', () => {
  reproducir(botones.find((b) => b.getAttribute('aria-pressed') === 'true').dataset.boceto);
});

reproducir('a');
