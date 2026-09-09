# Design

<!-- impeccable:design-schema 1 -->

## El mundo: el libro mayor, dibujado sobre papel de plano

La interfaz es un libro de contabilidad trazado sobre papel milimetrado. No
"inspirado en": la estructura del libro **es** la estructura de la pantalla.

Por qué este mundo. El producto existe para decir si una factura cuadra, y el
libro mayor es donde se lleva medio milenio resolviendo esa pregunta. Trae
resuelto su propio vocabulario —el rayado, las columnas, la raya de totales,
la doble raya de cierre, los números rojos— que además es el que el usuario
primario ya conoce de su trabajo.

**Referencia fijada por el autor:** [illoca.unseen.co](https://illoca.unseen.co).
De ahí vienen el papel milimetrado, la tinta azul de plano, el grano, la
lámina enmarcada con marcas de registro, los rótulos diminutos en versalita y
la grotesca pesada como voz de display. Es un mundo compatible: papel técnico,
una tinta dominante, anotación al margen.

### Reglas fundacionales, por orden

1. **El rayado es la maqueta.** No hay tarjetas. Nunca. Las filas se separan
   con filetes de un píxel y las columnas con filetes verticales. Lo que
   necesita agruparse se agrupa con rayado y con aire, no metiéndolo en una
   caja con sombra.
2. **Toda cifra se alinea a la derecha y usa cifras tabulares.** Los importes
   se leen comparando columnas: los dígitos tienen que caer unos sobre otros.
   Y una columna de cifras jamás se comprime hasta cortarlas: si no cabe, el
   libro se desplaza.
3. **Tres tintas, cada una con su oficio.** Azul para lo que estructura
   —rejilla, marco, filetes de cabecera, folio, doble raya—. Negra para los
   hechos. Roja solo para lo que no cuadra: los números rojos son literalmente
   eso. El ocre queda para el aviso.
4. **El color vive en el filete, no en el fondo.** Una fila con error lleva un
   pelo rojo en el borde izquierdo y su cifra en rojo. El fondo de la fila no
   se tiñe jamás: teñirlo destruye la lectura de la tabla, y es lo que hace
   todo el sector.
5. **La doble raya cierra.** En contabilidad, la doble raya bajo un total
   significa comprobado y cerrado. Es la señal de conformidad de este producto.
   No hay verde de éxito en ninguna parte.
6. **Las dos cifras, juntas.** Cuando una regla no cuadra se enseñan la
   esperada y la encontrada en la misma línea, la esperada nítida y la
   encontrada tachada en rojo. No un mensaje que las describa: las dos cifras.

### Cómo se elevó esta dirección

Cada línea nombra la disciplina que aporta un mundo descartado en la tirada:

- **Del zine fotocopiado — el color es el papel, nunca la marca.** Ningún
  color entra en la paleta por decorar; los tres que hay tienen función.
- **De Studio Dumbar — coraje de escala.** El veredicto se compone hasta
  4,75rem contra metadatos de 10px. Sin escalones tímidos en medio.
- **Del tubo nixie — todas las alternativas presentes a la vez.** Esperado y
  encontrado conviven; el bueno se destaca y el malo se apaga, en vez de
  sustituirse.
- **De la nube irisada — el color confinado al filete.** El campo de texto se
  queda acromático y la gravedad vive en un pelo de un píxel.

## Modo

**Operate.** El visitante revisa un montón de facturas y averigua cuáles no
puede contabilizar. Escanabilidad, consistencia y densidad por encima de
expresión. El carácter vive en la precisión de los detalles.

## Marca

Anagrama en `frontend/logo.svg`: el carril de folio a la izquierda, tres
renglones escritos de longitud decreciente y, debajo, la **doble raya** de
cierre. Es un libro y es el gesto de dar por bueno, a la vez. Un solo trazo de
1,6, sin relleno, hereda `currentColor` y funciona a 16px. Va en azul de plano
y pasa a tinta al pasar el ratón por encima.

Es el mismo dibujo en el favicon, con el color quemado porque ahí no hay CSS
que lo alimente.

## Color

Tokens en `:root`, redefinidos bajo `@media (prefers-color-scheme: dark)` y
bajo `[data-tema]`, para que el interruptor gane en las dos direcciones.

| Papel claro | | |
|---|---|---|
| `--papel` | `#EDE7D7` | El pliego. Ecru cálido, no blanco. |
| `--tinta` | `#23211C` | Negro cálido: los hechos. |
| `--tinta-media` | `#55503F` | Texto secundario. |
| `--tinta-tenue` | `#7E7660` | Rótulos y metadatos. |
| `--azul` | `#1B45C8` | Tinta de plano: rejilla, marco, filetes, folio. |
| `--azul-tenue` | `#8FA3E4` | Filetes de la lámina y de los uñeros. |
| `--filete` | `#C6BEA6` | Rayado del libro. |
| `--rojo` | `#C0271C` | Números rojos. Solo lo que no cuadra. |
| `--ocre` | `#7A5A08` | Aviso. |

### De noche no se invierte el papel: se cambia de artefacto

El primer tema oscuro era una inversión del claro —el pliego a negro, la
tinta a crema— y estaba mal. El papel no se vuelve negro nunca; invertirlo da
ese barro verdoso que delata a la mitad de los temas oscuros que hay por ahí.

El negativo del papel milimetrado no es papel negro: es una **cianotipia**,
el plano copiado en azul de Prusia con las líneas en blanco. Es un objeto
real, del mismo mundo que el resto, y da un oscuro de verdad con contraste
alto en vez de un gris apagado.

| Cianotipia | | |
|---|---|---|
| `--papel` | `#0E2440` | Azul de Prusia. El baño de la copia. |
| `--tinta` | `#E9F1FB` | La línea blanca, donde el papel quedó sin velar. |
| `--azul` | `#77D2FF` | Cian: rejilla, filetes, folio, botones. |
| `--rojo` | `#FF8A7E` | Coral. El rojo puro se apaga sobre azul. |
| `--ocre` | `#FFC46B` | Ámbar para el aviso. |
| `--mesa` | `#061421` | La mesa, más oscura que la copia. |

El rojo y el ocre suben de luminosidad porque sobre azul de Prusia un rojo de
imprenta pierde contraste y deja de leerse como alarma.

**Prohibido:** verde de éxito, violeta de acento, degradados, fondos de fila
teñidos, pastillas de estado de colores.

## Materia

- **La mesa.** El fondo no es la pantalla: es un escritorio a media luz, con
  su veta. La hoja va **encima**, con sombra. Cansa mucho menos que un pliego
  a sangre y da profundidad.
- **La hoja, arrancada del libro mayor.** El canto izquierdo va rasgado; los
  otros tres, cortados a máquina. Se hace con una máscara CSS de dos capas:
  una tira de 48×800 que se repite en vertical —para que el desgarro conserve
  su escala por larga que sea la página— y un rectángulo opaco para el resto.
- **Dos roturas distintas, y no es un capricho.** La hoja de talonario de la
  presentación va troquelada: rompe fina y a paso regular, tramos de 6,5
  puntos con desviación de milímetro y medio. La del libro mayor se rasga por
  el lomo, sin troquel que la guíe: tramos irregulares de 11 a 38 puntos,
  amplitud hasta 9, y casi una de cada cinco veces una fibra que no cede a la
  primera. Medido sobre un talonario real.
- **Papel milimetrado:** retícula fina cada `--paso` (8px) y gruesa cada
  cinco. Va sobre la hoja, no sobre la mesa.
- **Grano:** una capa fija de `feTurbulence` sobre todo. Sin coste de
  repintado y sin capturar el ratón.
- **La tinta del sello.** Tres pasadas en el orden en que ocurren en el papel:
  el filo del caucho roto por desplazamiento, el reparto desigual de la tinta
  con ruido de baja frecuencia, y las calvas de caucho seco con ruido de alta.
  Dos variantes con semillas distintas: dos sellos seguidos no salen iguales,
  y el segundo sale más pobre porque nadie ha vuelto al tampón.

## Tipografía

Cuatro familias, auto-hospedadas en `frontend/fuentes/` bajo licencia SIL OFL.
La aplicación no llama a ningún servidor de fuentes: promete funcionar sin red
y lo cumple hasta ahí.

- **Courier Prime** — todo el sistema. La máquina de escribir es el
  instrumento de este mundo, no un disfraz de «técnico», y de paso el
  monoespaciado alinea las cifras solo.
- **Prata** — solo la marca y los títulos de capítulo. Romana grabada de
  membrete antiguo: abierta, de mucho contraste y poca tinta. Lleva la sombra
  desplazada del rotulista, dada con el segundo pincel.
- **Archivo** — lo que el impreso trae de fábrica: rótulos, cabeceras de
  columna, «FACTURA N.º». La imprenta y la mano no comparten voz.
- **Caveat** — lo manuscrito de la presentación.

Reglas: toda cifra lleva `tabular-nums lining-nums`; el texto corrido no pasa
de 72 caracteres; a la máquina no se le aplica tracking negativo, que se le
cierran los contornos.

## Composición

- **Uñeros.** La navegación son pestañas troqueladas en el canto del pliego.
  La activa se funde con la página comiéndose su filete inferior.
- **Columna de folio.** Carril de 48px a la izquierda con el índice de la
  fila, en azul; en rojo cuando esa fila no cuadra.
- **Ritmo de 32px** en las filas del libro; los filetes caen en esa retícula.
- **Pie de columna.** Toda tabla de cifras acaba en raya de totales y, si
  cuadra, en doble raya.
- **La zona de soltar se repliega.** En blanco ocupa la página con el rayado
  dibujado y las cabeceras esperando; con el libro escrito se encoge a un
  renglón y cede el sitio a los datos.

## Movimiento

Un único momento autorizado: **el asiento escribiéndose**. Cada fila entra
revelándose de izquierda a derecha con `clip-path` en 220ms y salida
exponencial, escalonada 28ms por fila. Es la pluma pasando por el renglón.

Todo lo demás es inmediato. La barra de progreso avanza con `transform`, no
con `width`. `prefers-reduced-motion` sustituye el revelado por presencia.

## Estados

- **Vacío:** el pliego rayado con las cabeceras ya dibujadas. No un icono de
  nube.
- **Cargando:** filete azul que avanza, con el nombre del fichero en curso.
- **Error de lectura:** la fila se escribe igual, con la causa en rojo. Un
  documento ilegible es un hecho contable, no una desaparición.
- **Sin OCR:** aviso permanente en la cabecera con el comando exacto.
- **`[hidden]` gana siempre.** Hay una regla global `[hidden]{display:none
  !important}`: ninguna clase con `display:flex` puede resucitar un elemento
  que el código decidió ocultar.

## Iconografía

SVG dibujado, trazo de 1,4-1,6, mismo peso en todos, en un `<symbol>` al
principio del documento. Ningún emoji, ningún glifo Unicode haciendo de icono.
Las marcas de estado son marcas de contable: el aspa, la llamada, la
admiración.

## Prohibiciones heredadas del suelo de calidad

Tarjetas como estructura de página · tarjetas anidadas · antetítulos ·
numeración de secciones 01/02/03 · texto con degradado · cristal esmerilado
decorativo · `border-left` de color de más de 1px · sombras duras sin
desenfoque · monoespaciada como disfraz de técnico · fuente del sistema como
voz de display · animar `width` o `height`.
