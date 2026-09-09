# Plan: banco de evaluación de facturas, como webapp local

Aplicación que se ejecuta en tu máquina, no manda nada a ningún servidor, y usa el motor de IA que ya tenga instalado quien la abre.

## Qué es y qué no es

Es un banco de pruebas con interfaz. Tú cargas facturas, la app las pasa por el motor que elijas, compara contra la respuesta correcta y te enseña dónde falla y por qué.

No es un extractor de facturas. El extractor es la excusa; lo que se enseña es el sistema de medida.

La diferencia importa para el diseño: la pantalla principal no muestra el resultado de una factura, muestra la comparación entre motores. Si al abrir la app lo primero que se ve es una factura procesada, has construido otra cosa.

## El problema del motor, resuelto

Tres motores, seleccionables desde la propia interfaz, y la app detecta cuáles están disponibles al arrancar.

**CLI local.** Claude Code o Codex ya instalados y autenticados en la máquina del usuario. La app los invoca como proceso, les pasa el documento y recoge el JSON. El usuario no introduce ninguna clave porque su sesión ya existe. Este es el motor que hace especial al proyecto.

**Clave de API.** Se pega en la interfaz, se guarda cifrada en la máquina, nunca sale de ahí ni se sube al repo. Para quien no tenga CLI instalado.

**Ollama.** Modelo local con visión. Coste cero, funciona sin conexión. La columna que le interesa a cualquiera que maneje datos que no puede mandar fuera.

La pantalla de arranque enseña los tres con un indicador: disponible, no instalado, sin configurar. Que el usuario vea en dos segundos con qué puede trabajar.

Esta arquitectura es lo primero que explicas en el README, porque es lo que nadie más tiene.

## Arquitectura

```
factura-eval/
  README.md
  LICENSE
  .gitignore                  .env, claves, datos locales
  .env.example

  backend/
    main.py                   FastAPI
    api/
      motores.py              detección y estado de los tres motores
      ejecutar.py             lanza una evaluación, devuelve progreso por SSE
      resultados.py           historial y comparativas
    nucleo/
      esquema.py              contrato de salida y validación
      motores/
        base.py               interfaz común
        cli.py                Claude Code / Codex como subproceso
        api.py                Anthropic, OpenAI, Google
        ollama.py             local
      evaluador.py            métricas
      cache.py                hash de documento + prompt + motor
    tests/

  frontend/
    index.html
    app.js                    sin framework, o React si te apetece
    estilo.css

  dataset/
    facturas/                 30 PDF sintéticos
    esperado/                 30 JSON escritos a mano
    generador.py              produce facturas nuevas
    dataset.md

  resultados/
    comparativas/
```

Un solo comando de arranque que levanta la API y abre el navegador. Si arrancarlo cuesta más de un comando, la mitad de la gente no pasa de ahí.

## Las cuatro pantallas

**1. Panel.** Lo primero que se ve. La tabla comparativa entre motores: aciertos por campo, tasa de invención, coste, segundos. Si no hay ninguna ejecución todavía, un estado vacío que invita a lanzar la primera. Nada de gráficos decorativos.

**2. Ejecución en vivo.** Aquí es donde se conecta con tu visor. Las treinta facturas como treinta nodos. Cada una cambia de estado mientras se procesa: en cola, analizando, validando, resuelta o fallada. Los fallos se quedan marcados y no desaparecen. Al terminar, la vista queda como mapa de resultados: de un vistazo ves qué documentos resisten y cuáles caen.

Esto no es adorno. Ver treinta procesos a la vez es lo que hace que detectes patrones que en una tabla no ves, del tipo todas las que fallan son las de dos páginas.

**3. Detalle de un caso.** La factura a la izquierda, la respuesta esperada y la obtenida a la derecha, campo por campo, con las diferencias marcadas. Los campos inventados en un color propio, distinto del de los fallados, porque son cosas distintas y ese es el argumento del proyecto.

**4. Dataset.** Las treinta facturas, qué prueba cada una, y el botón para generar más con el generador.

## Diseño

Que no parezca ni una herramienta de desarrollador ni un panel corporativo. Dos referencias que sí funcionan: un instrumento de laboratorio y una hoja de resultados de imprenta.

**Color.** Fondo claro, de papel, no blanco puro ni gris azulado de dashboard. Un tono de tinta oscuro para el texto. Tres colores funcionales y solo tres: uno para acierto, uno para fallo, uno para invención. Que la invención tenga color propio y llamativo es una decisión de producto, no estética: es lo que quieres que mire la gente.

**Tipografía.** Una con carácter para titulares y cifras grandes, una monoespaciada para datos, JSON y códigos. Dos familias, ninguna más.

**Densidad.** Las cifras grandes, muy grandes. Un 94,2% ocupando media pantalla comunica más que doce indicadores pequeños. El resto del texto pequeño y tranquilo.

**Movimiento.** Solo donde informa: la transición de estado de un nodo mientras procesa. Cero animaciones de entrada, cero deslizamientos. Una app que se mueve sola parece una demo.

**Vacíos.** Márgenes generosos. La tentación es llenar la pantalla porque hay datos; resístela.

Modo claro y oscuro, y que respete la preferencia del sistema.

## Lo que sigue valiendo del plan anterior

Todo esto no cambia y es lo que da valor al proyecto:

- Las tres métricas, con la tasa de invención como argumento principal
- Los diez casos trampa, incluidos el albarán que no es factura y la factura sin CIF
- Las reglas de qué cuenta como acierto, escritas antes de medir nada
- Facturas sintéticas generadas por ti, ninguna real, y el generador dentro del repo
- Determinismo: temperatura a cero, versión del modelo registrada, variación medida y publicada
- Caché por hash para no pagar dos veces lo mismo
- .gitignore desde el primer commit
- El README con la tabla de resultados arriba del todo

## Plan por fases

**Fase 1. El núcleo, sin interfaz.** Esquema con validación, generador de facturas, quince casos con su esperado a mano, evaluador y tests. Se ejecuta por consola. Aquí no hay nada bonito y es la fase que determina si el proyecto vale algo.

**Fase 2. Los motores.** La interfaz común y los tres adaptadores. El del CLI es el más delicado: hay que invocar el proceso, pasarle el documento, obtener JSON limpio y controlar los tiempos de espera. Empieza por este, que es el que puede tumbar el plan; si no funciona, mejor saberlo antes de dibujar nada.

**Fase 3. API y panel.** FastAPI con los cuatro grupos de rutas, progreso en tiempo real, y la pantalla del panel con la tabla. Fea pero funcionando.

**Fase 4. La vista en vivo y el detalle.** Aquí entra el trabajo visual y tu visor. Es la fase que hace que alguien enseñe la app a otra persona.

**Fase 5. Los quince casos restantes, el README y publicar.**

## Las tres advertencias

**Esto ya no son tres tardes.** Son entre dos y tres semanas de ratos. Asúmelo antes de empezar, porque un repo público a medias resta.

**El riesgo real es que se te convierta en producto.** Vas a querer añadir subida de carpetas, exportación, cuentas de usuario. No lo hagas. Cada cosa que añadas retrasa la publicación, y el proyecto solo te sirve publicado. Escribe la lista de fuera de alcance el primer día y no la toques.

**El orden importa y es contraintuitivo.** La interfaz bonita al final. Si empiezas por el diseño acabarás con una aplicación preciosa que mide mal, y el que la mire con criterio lo va a ver en dos minutos. Al revés no pasa: un núcleo sólido con interfaz fea se arregla en una tarde.

## Cuando esté publicado

Un vídeo de treinta segundos de la vista en vivo procesando las treinta facturas, con la tabla de resultados al final. Sin voz, sin explicación.

Y una frase: monté un banco de pruebas para ver cuánto se inventan los modelos leyendo facturas españolas. Funciona con la suscripción que ya tengas instalada, sin claves y sin mandar nada fuera.

Eso lo enseña cualquiera que lo vea.
