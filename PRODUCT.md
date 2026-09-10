# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Dos audiencias confirmadas, con una jerarquía deliberada.

**Primaria — quien recibe facturas y tiene que revisarlas.** Autónomos y
gestorías pequeñas en España. La situación real: llegan facturas de
proveedores por correo, en PDF y a veces escaneadas, y hay que comprobar antes
de contabilizarlas que son facturas de verdad, que los identificadores fiscales
existen, y que los importes cuadran. Hoy eso se hace a ojo, factura a factura.
El trabajo que hacen con el producto: soltar un montón de PDF y que les diga
cuáles tienen un problema y cuál es.

**Secundaria — reclutadores técnicos evaluando al autor.** No usan el producto
para su trabajo: lo abren, lo prueban cinco minutos y juzgan el oficio. No
tienen claves de API ni ganas de configurar nada. Deciden que el proyecto es
serio o que no lo es en el primer minuto.

La interfaz principal se diseña para la audiencia primaria. La capa técnica
—banco de pruebas, reglas aplicadas, confianza por campo— vive en su propia
sección, accesible pero sin invadir el flujo de trabajo.

## Product Purpose

Extraer los datos de una factura y comprobar que la factura es correcta, en la
máquina de quien la ejecuta. Se sueltan PDF o imágenes, se leen los campos y se
pasan por reglas fiscales; sale un informe que dice qué está mal y por qué.

Éxito es que alguien reciba veinte facturas de proveedor, las suelte de golpe,
y en segundos sepa cuáles no puede contabilizar tal cual.

## Positioning

Tres cosas que un competidor no puede copiar diciendo lo mismo:

1. **No usa IA.** No hay modelo, ni clave de API, ni llamada de red, ni coste
   por documento. Los resultados son deterministas: el mismo PDF da el mismo
   informe hoy y dentro de un año. Un extractor basado en modelos no puede
   prometer eso.
2. **Los documentos no salen de la máquina.** Facturas de proveedores son datos
   fiscales de terceros. Aquí no se suben a ningún servidor porque no hay
   servidor: el binario corre en local.
3. **Comprueba el dígito de control, no el formato.** La mayoría de los
   validadores hacen `regex` sobre el NIF. Este calcula la letra del DNI, el
   dígito del CIF, el módulo 97 del VAT británico y el módulo 11 de la
   USt-IdNr alemana. Un identificador con formato correcto y control inválido
   se rechaza.

## Operating Context

- **Instalación:** `pip install` y un comando. Abre el navegador solo. Sin
  Docker, sin base de datos, sin servicio, sin registro.
- **Entrada:** PDF con capa de texto (lo habitual en facturas emitidas por
  software) y PDF escaneados o fotos, que pasan por OCR local.
- **Uso típico:** un lote de entre 1 y 50 documentos de una tacada.
- **Salida:** informe en pantalla y exportación a CSV para llevárselo a Excel
  o al programa de contabilidad.
- **Cuatro jurisdicciones, a distinta profundidad:** España, Reino Unido,
  Estados Unidos y Alemania. Todas con su formato de fecha e importe —
  `05/03/2025` es 5 de marzo en España y 3 de mayo en Estados Unidos, y el
  producto lo distingue—, pero las reglas fiscales no están al mismo nivel.
  Ver «Evidence on Hand».

## Capabilities and Constraints

**Hace:**

- Lee PDF con capa de texto y, con OCR local, escaneados e imágenes
  (`.pdf .png .jpg .jpeg .tif .tiff .bmp .webp`).
- Extrae número, fechas de emisión y vencimiento, emisor, receptor,
  identificadores fiscales, líneas de detalle, base imponible, desglose de
  impuesto, retención y total.
- Da la confianza de cada campo y la pista que lo produjo (qué etiqueta lo
  encontró), para que el usuario sepa de dónde sale cada dato.
- Aplica ~20 reglas fiscales y devuelve hallazgos con tres gravedades: error,
  aviso, información.
- Trae un banco de pruebas propio: 24 facturas y 40 casos trampa con la
  respuesta correcta conocida, para medir cuánto acierta el extractor.
- Exporta a CSV.
- Línea de comandos con la misma funcionalidad que la web.

**No hace, y no debe fingir que hace:**

- No contabiliza, no concilia, no presenta impuestos, no factura.
- No comprueba si un NIF existe de verdad en el censo de Hacienda: comprueba
  que el dígito de control es coherente. Son cosas distintas y el producto no
  las confunde.
- No detecta fraude ni falsificación.
- No guarda nada en la nube ni sincroniza entre dispositivos.

**Restricciones técnicas:**

- Python ≥ 3.10. FastAPI y uvicorn detrás; el frontend es HTML, CSS y
  JavaScript sin framework ni build. Es deliberado: se abre el fichero y se
  lee, sin `node_modules` ni compilación.
- El OCR (`rapidocr-onnxruntime`) es opcional. Sin él la aplicación funciona
  con PDF de texto y lo dice claramente en la interfaz; nunca falla en
  silencio.
- Los datos se guardan en disco, en el directorio del usuario. Sin base de
  datos.

**Terminología del dominio, que la interfaz respeta:** factura, albarán,
presupuesto, proforma; base imponible, cuota, retención, IRPF; NIF, CIF, NIE.
No se traducen a "documento" ni a "importe neto" para simplificar.

## Brand Commitments

- **Nombre:** Cazafacturas. Confirmado, no se toca.
- **Idiomas:** español e inglés, ambos completos. El español es el original;
  el dominio es fiscal español y los términos nacen en castellano.
- **Voz:** directa y sin adornos. Un hallazgo se explica en una frase que
  diga qué pasa y por qué importa, no un código de error. "Esto no es una
  factura: es un albarán. No sirve como justificante para deducir el
  impuesto." Nada de tono comercial ni de exclamaciones.
- **Licencia:** MIT.
- **Repositorio:** github.com/Josulo72/cazafacturas

## Evidence on Hand

Todo esto es real y verificable en el repositorio; nada de ello debe
inventarse ni inflarse en ninguna superficie:

- **Banco externo:** 23 facturas en PDF de 15 maquetaciones de terceros,
  con datos ficticios y la verdad escrita en `dataset/externo/manifest.json`.
  Medido el 10 de septiembre de 2026: 153 de 153 campos bien leídos, 15 de 15
  facturas correctas conformes, 8 de 8 defectuosas cazadas cada una por su
  motivo, ninguna en «No legible». Se reproduce con `python cli.py --externo`.

  **Qué mide y qué no, y esto no se puede omitir en ninguna superficie.**
  El extractor se corrigió con esas 23 facturas delante: es un conjunto de
  desarrollo, no uno reservado. Demuestra que lee quince maquetaciones ajenas,
  no que lea cualquiera. El OCR no está medido: las 23 llevan capa de texto.

- **Banco interno:** 24 facturas y 50 casos trampa en cuatro países,
  generados por el propio repositorio con una sola maquetación. Sirve para
  detectar regresiones y nada más. El «100 % de precisión campo a campo» que
  se sacaba de aquí está retirado: el banco externo lo desmintió en el primer
  pase, con 15 de 15 facturas buenas marcadas como no conformes. Ninguna
  superficie puede volver a usar esa cifra.

- **Profundidad desigual por jurisdicción.** España está modelada en serio
  (DNI, NIE, CIF con dígito de control por tipo de sociedad, tipos de IVA
  vigentes, retención). Reino Unido y Alemania llevan comprobación de
  identificador y tipos de IVA. Estados Unidos solo valida el EIN: el sales
  tax varía por estado y no se comprueba. Ninguna superficie debe presentar
  los cuatro países como equivalentes.
- **125 tests automáticos** en verde, incluidos los de seguridad y los de
  propiedades con Hypothesis. `backend/tests/`
- **74 PDF de muestra** generados, para que cualquiera pruebe la aplicación sin
  enseñar facturas propias. `dataset/pdf/`

No hay clientes, ni testimonios, ni cifras de uso, ni prensa, ni despliegue en
producción. Ninguna superficie puede sugerir que los haya.

## Product Principles

1. **Determinista antes que listo.** Ante la duda entre acertar más y ser
   reproducible, gana reproducible. Un resultado que cambia solo no sirve para
   contabilizar.
2. **Decir de dónde sale cada dato.** Todo campo extraído lleva su confianza y
   la etiqueta que lo encontró. El usuario tiene que poder desconfiar con
   fundamento y corregir.
3. **Un hallazgo explica, no codifica.** Cada regla incumplida se cuenta en
   castellano llano, con el valor esperado y el encontrado al lado.
4. **Degradar avisando, nunca en silencio.** Si falta el OCR, si una página no
   tiene texto, si un campo no se ha encontrado, se dice. Un hueco silencioso
   es peor que un error visible.
5. **Que arranque sin pedir nada.** Ni claves, ni cuentas, ni configuración.
   Quien lo instala tiene que poder usarlo en el primer minuto.

## Accessibility & Inclusion

- La gravedad de un hallazgo nunca se comunica solo por color: error, aviso e
  información llevan además texto y forma propia. Hay usuarios daltónicos y
  hay quien imprime el informe en blanco y negro.
- Los importes y los identificadores fiscales se muestran en cifras tabulares
  y alineados, porque se leen comparando columnas.
- Arrastrar y soltar siempre tiene su alternativa por teclado y con selector
  de ficheros: el arrastre no puede ser el único camino.
