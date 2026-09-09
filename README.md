# Cazafacturas

Extrae los datos de una factura y comprueba que la factura es correcta.
En tu máquina. **Sin IA, sin red y sin claves de API.**

Sueltas PDF o fotos, y te dice cuáles no puedes contabilizar y por qué.

---

## Por qué no usa IA

Porque para esto no hace falta, y usarla cuesta tres cosas que un programa de
contabilidad no se puede permitir:

| | Con modelo | Cazafacturas |
|---|---|---|
| **Reproducibilidad** | La misma factura puede dar dos respuestas distintas | El mismo PDF da el mismo informe hoy y dentro de un año |
| **Privacidad** | El documento sale de la máquina | No hay servidor al que salir |
| **Coste** | Por documento | Cero |
| **Arranque** | Clave de API, cuenta, facturación | `pip install` y un comando |

Un NIF no se adivina: se calcula. Que la base imponible cuadre con la suma de
las líneas no es una opinión: es una resta. Todo lo que hace este programa
tiene una respuesta correcta y comprobable, así que la calcula.

## Qué comprueba

**Identificadores fiscales, con dígito de control, no con una expresión
regular.** Un identificador con formato válido y control inválido se rechaza:

- España — letra del DNI y del NIE, dígito de control del CIF (numérico o
  letra según el tipo de sociedad)
- Reino Unido — VAT de 9 cifras, módulo 97
- Alemania — USt-IdNr., módulo 11
- Estados Unidos — EIN, con la lista de prefijos que el IRS no asigna

**Aritmética, línea a línea:** `cantidad × precio = importe` · suma de líneas =
base imponible · `base × tipo = cuota` · `base + cuotas − retención = total`.
Con dos céntimos de tolerancia, que eso es redondeo y no un error.

**Coherencia del documento:** vencimiento posterior a la emisión, factura con
número, emisor distinto del receptor, cantidades mayores que cero, tipos de
impuesto vigentes en el país que corresponde —el 19 % es correcto en Alemania
y no existe en España—.

**Y si no es una factura, lo dice.** Un albarán, un presupuesto o una proforma
se identifican y se rechazan con una frase, en vez de listar los quince campos
de factura que les faltan.

## Cuánto acierta, y qué significa esa cifra

Sobre el banco de pruebas del propio proyecto: 24 facturas y 40 casos trampa
en cuatro países, con la respuesta correcta escrita de antemano.

| | |
|---|---|
| Facturas PDF extraídas | 24 / 24 |
| Precisión campo a campo | 100 % |
| Casos trampa detectados | 50 / 50 |
| Tiempo de los 24 documentos | 1,8 s |

```bash
python cli.py --banco
```

### Ahora la letra pequeña, que importa más que la cifra

**Ese 100 % no significa que sepa leer la factura de tu proveedor.** Los PDF
del banco los genera este mismo repositorio: `dataset/render_pdf.py` escribe
las etiquetas y `backend/nucleo/extractor.py` las busca. Es circular. Lo que
esa cifra demuestra es que la cadena es **coherente consigo misma** y que no
se rompe al cambiarla —para eso sirve, y para eso está la línea base—, no que
acierte en el mundo real.

Frente a facturas de proveedores de verdad, con sus maquetas raras, sus
logotipos y sus tablas a tres columnas, el número será bastante más bajo.
Todavía no lo he medido, y hasta que lo mida no voy a fingir que lo sé.

**El OCR tampoco está medido.** Los 74 documentos del banco llevan capa de
texto. La lectura de escaneados funciona y está instalada, pero ningún número
de esta tabla la ejercita.

**Las cuatro jurisdicciones no están al mismo nivel.** España está modelada en
serio: DNI, NIE, CIF con su dígito de control según el tipo de sociedad,
tipos de IVA vigentes, retención de IRPF. Reino Unido y Alemania llevan la
comprobación del identificador —módulo 97 y módulo 11— y sus tipos de IVA.
Estados Unidos solo valida el EIN: el *sales tax* varía por estado y aquí no
se comprueba.

Lo pongo por delante porque un revisor con oficio lo ve en treinta segundos,
y prefiero decirlo yo.

## Instalación

Clona y ejecuta el instalador. Monta un entorno propio en `.venv`, así que no
toca el Python del sistema ni le cambia versiones a nada que ya tengas.

**Windows**

```powershell
powershell -ExecutionPolicy Bypass -File instalar.ps1
```

**macOS y Linux**

```bash
sh instalar.sh
```

El instalador comprueba la versión de Python, monta el entorno, instala,
genera las 74 facturas de muestra, **pasa el diagnóstico** y deja un
lanzador. Se puede volver a ejecutar las veces que haga falta.

Después:

```bash
./cazafacturas
```

En Windows, doble clic en `Cazafacturas.cmd`. Abre el navegador solo.

<details>
<summary>A mano, sin instalador</summary>

```bash
python -m venv .venv
.venv/bin/pip install -e ".[ocr,muestras]"
.venv/bin/python -m dataset.render_pdf
.venv/bin/cazafacturas
```

`[ocr]` añade la lectura de escaneados y fotos; son modelos que vienen dentro
del paquete, **no hace falta Tesseract ni ningún binario del sistema**.
`[muestras]` genera las facturas de ejemplo. Sin los extras, la aplicación
funciona con PDF que llevan capa de texto y lo dice en pantalla.

`requirements.lock` tiene las versiones exactas con las que se midió la línea
base, por si hace falta reproducir una medida vieja.

</details>

Requiere Python 3.10 o superior. La raíz es la presentación; la aplicación
está en `/app`.

## Comprobar que sigue bien

```bash
python cli.py --doctor
```

Revisa la instalación y **vuelve a medir el banco contra la línea base
commiteada**. Si un cambio baja la precisión, dice qué campos han empezado a
fallar; si se escapa un caso trampa, lo nombra. Devuelve 1 cuando algo ha
empeorado, así que sirve de puerta en integración continua y no solo para
mirarlo.

## La interfaz

El proyecto se ve como lo que hace. Al entrar hay una presentación de treinta
segundos —saltable, y que no se repite en visitas posteriores— en la que una
factura se levanta a bolígrafo sobre una hoja de talonario y se sella
**CONFORME**; después entra la hoja siguiente del mismo taco, que resulta ser
un albarán, y se sella **NO CONFORME**.

La aplicación es un libro mayor: el rayado es la maqueta y no hay una sola
tarjeta. Las cifras van tabulares y alineadas a la derecha, porque se leen
comparando columnas. Lo que no cuadra sale en rojo con un filete de un píxel
en el borde de la fila —el fondo no se tiñe nunca, que eso destroza la lectura
de una tabla—. Y un lote que cuadra cierra con **doble raya**, que en
contabilidad significa comprobado: no hay verde de éxito en ninguna parte.

Todo se dibuja en el navegador. Las texturas —el papel de plano, el grano, el
desgarro del canto, la tinta desigual del sello— son SVG y CSS, sin una sola
imagen. Las dos roturas son distintas y están medidas sobre un talonario de
verdad: la hoja de talonario va troquelada y rompe fina y regular; la del
libro mayor se rasga por el lomo, sin guía, y sale basta e irregular.

Las fuentes se sirven desde el propio repositorio. La aplicación promete
funcionar sin conexión y lo cumple hasta ahí.

## Cómo se usa

Arrastras los ficheros a la ventana. Cada documento se asienta en un renglón
del libro, con su número, su fecha, su emisor y sus importes; lo que no cuadra
sale en rojo. Pulsando en una fila se abre el detalle: el veredicto, de dónde
salió cada campo y con qué confianza, y cada comprobación incumplida con el
valor esperado al lado del encontrado.

Si no quieres enseñar tus facturas, hay **74 PDF de muestra** incluidos:
«Probar con facturas de muestra» los carga.

Formatos: `.pdf` `.png` `.jpg` `.jpeg` `.tif` `.tiff` `.bmp` `.webp`.
Idiomas: español e inglés. Jurisdicciones: España, Reino Unido, Estados Unidos
y Alemania.

## Línea de comandos

```bash
python cli.py factura.pdf otra.pdf
```

```bash
python cli.py --banco -v
```

```bash
python cli.py --csv salida.csv "facturas/*.pdf"
```

`--capacidades` dice qué sabe hacer tu instalación. `--json` vuelca el
resultado crudo. `--pais ES|UK|US|DE` fuerza la jurisdicción en vez de
detectarla.

## Cómo funciona por dentro

```
fichero → lectura → extractor → validador → informe
```

| Módulo | Qué hace |
|---|---|
| [`lectura.py`](backend/nucleo/lectura.py) | PDF con capa de texto vía `pdfplumber`; escaneado se rasteriza y va a OCR local; imagen directa a OCR. Devuelve el texto con la posición de cada palabra. |
| [`extractor.py`](backend/nucleo/extractor.py) | Busca la etiqueta y lee lo que hay a su derecha o debajo, en cuatro idiomas. Usa la geometría para separar columnas: emisor y cliente van en paralelo y no pueden mezclarse. Resuelve `1.234,56` y `1,234.56`, y sabe que `05/03` es 5 de marzo en España y 3 de mayo en Estados Unidos. |
| [`validador.py`](backend/nucleo/validador.py) | Las reglas fiscales. No lanza excepciones: una factura con errores es el caso interesante, así que cada regla incumplida sale como un hallazgo con su explicación. |
| [`analizador.py`](backend/nucleo/analizador.py) | Orquesta la cadena y, cuando hay respuesta correcta conocida, puntúa. |

Cada campo extraído lleva su confianza y la pista que lo produjo —qué etiqueta
lo encontró—, para que puedas desconfiar con fundamento.

**Los documentos no salen de tu ordenador.** No hay telemetría, no hay
llamadas externas, ni siquiera para las fuentes: están dentro del repositorio.

## Desarrollo

```bash
pip install -e ".[dev]"
```

```bash
pytest
```

120 tests, en cuatro familias:

| | |
|---|---|
| Reglas fiscales | cada regla con su caso, y el dataset entero como red |
| Extracción | campo a campo contra el esperado, sobre PDF y no sobre diccionarios |
| Seguridad | cada test reproduce el ataque que la defensa evita |
| Propiedades | Hypothesis busca el contraejemplo en el parser de importes, el de fechas y los dígitos de control |

Regenerar el dataset y sus PDF:

```bash
python -m dataset.generador && python -m dataset.generar_trampas && python -m dataset.render_pdf
```

Los generadores son deterministas —semillas 42 y 7—, así que el dataset
regenerado es idéntico. Los identificadores fiscales son inventados pero
**válidos**: el dígito de control se calcula. Si no, el propio validador
rechazaría su dataset.

## Lo que no hace

No contabiliza, no concilia, no presenta impuestos y no emite facturas.

No comprueba si un NIF existe en el censo de Hacienda: comprueba que su dígito
de control es coherente. Son cosas distintas y el programa no las confunde.

No detecta fraude ni falsificación.

## Autoría

Hecho por [LatidosIA.com](https://latidosia.com).

## Licencia

MIT.
