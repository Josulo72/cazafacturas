# Cazafacturas

**Cazafacturas** es un banco de evaluación de facturas. Cargas facturas (o usas las sintéticas incluidas), eliges el motor de IA que ya tengas instalado (Claude Code, Codex, API remota u Ollama local), y la app compara la extracción contra la respuesta correcta — campo por campo — y te muestra **precisión**, **tasa de invención** y **coste/tiempo**.

No es un extractor de facturas. El extractor es la excusa; lo que se mide y enseña es el **sistema de medida**: cuánto acierta cada modelo, cuánto se inventa y en qué campos.

---

## Por qué este nombre

Porque el argumento central del proyecto es la **invención**: cuando un modelo devuelve un campo que no existe en el documento (o rellena algo que estaba en blanco), eso no es un fallo — es una **invención**. Y la invención es más peligrosa que el fallo en contabilidad/fiscalidad. Cazafacturas mide y colorea la invención por separado, y te dice exactamente en qué campos ocurre.

---

## Arquitectura: tres motores, un panel

La app detecta al arrancar cuáles están disponibles y los muestra con indicador: **disponible / no instalado / sin configurar**.

| Motor | Cómo funciona | Claves / Coste |
|-------|---------------|----------------|
| **CLI local** | Invoca `claude` o `codex` ya autenticados en tu terminal como subproceso. Pasa el JSON y recoge la respuesta. | **Coste 0 adicional** (usa tu suscripción). Modelo por defecto: `sonnet` (evita Fable). |
| **Clave API** | Pegas tu clave en la interfaz (se guarda cifrada localmente, nunca sale de tu máquina). | Anthropic / OpenAI / Google. Pagas por uso. |
| **Ollama local** | Modelo con visión 100% local, sin conexión. | Gratis, privado. Requiere GPU/CPU y modelo descargado (`ollama pull llava`). |

---

## Lo que se mide (y por qué importa)

- **Precisión por campo**: % de campos correctos sobre los esperados + fallados (excluye invenciones del denominador).
- **Tasa de invención**: % de campos que el modelo **inventa** (devuelve sin que estén en el original, o rellena estando en blanco). **Es la métrica principal** — inventar en una factura es fraude potencial.
- **Coste y segundos** por ejecución.
- **Caché por hash** (documento + motor + modelo + idioma + versión de prompt): no pagas dos veces lo mismo.

---

## Países e idiomas soportados (v0.4)

| País | Código | Moneda | ID fiscal | Impuesto | Idiomas |
|------|--------|--------|-----------|----------|---------|
| España | ES | € | NIF | IVA | ES / EN |
| Reino Unido | UK | £ | VAT Reg No | VAT | ES / EN |
| Estados Unidos | US | $ | EIN / Tax ID | Sales Tax | ES / EN |
| Alemania | DE | € | USt-IdNr. | Umsatzsteuer | ES / EN |

El **idioma** se elige en la UI (ES/EN) y afecta a:
- Interfaz completa
- Prompt que se envía al motor
- Mensajes de consola

El **país** filtra el dataset y adapta el contrato de extracción (formatos de fecha, NIF, tasas de impuesto).

---

## Dataset incluido

- **24 facturas normales** (6 por país × 4 países): generadas sintéticamente, variando productos, importes, retenciones, tipos de factura.
- **40 casos trampa** (10 por país): albarán que no es factura, factura sin ID fiscal, sin número, fecha futura, totales que no cuadran, base que no suma, sin desglose de impuesto, receptor = emisor, línea con cantidad 0, cuota de impuesto errónea.
- **Generador**: `python -m dataset.generador` regenera todo; `python -m dataset.generar_trampas` regenera trampas. Semilla fija = resultados deterministas.

---

## Instalación (pip-installable)

```bash
# Clonar
git clone https://github.com/tu-usuario/cazafacturas.git
cd cazafacturas

# Instalar en modo editable (incluye frontend y dataset)
pip install -e .

# Ver motores disponibles
cazafacturas --listar

# Lanzar webapp y abrir navegador
cazafacturas
# o explícito:
cazafacturas --host 127.0.0.1 --port 8765
```

**Requisitos**: Python ≥ 3.10, Claude Code o Codex instalados y autenticados (para motor CLI), u Ollama con modelo de visión (`ollama pull llava:7b`).

---

## Uso por consola (CLI)

```bash
# Validar el pipeline con motor "oráculo" (devuelve lo esperado → precisión 100%)
python -m cli --listar
python -m cli                    # motor oráculo
python -m cli --motor cli        # motor CLI (Claude Code / Codex)
python -m cli --motor ollama     # motor local
python -m cli --trampas          # incluye casos trampa
python -m cli --idioma en        # prompt y mensajes en inglés
python -m cli --motor cli --modelo sonnet --trampas --idioma en
```

Salida por caso: precisión, invención, aciertos/fallos/invenciones, y al final resumen global.

---

## Estructura del repo

```
cazafacturas/
├── pyproject.toml          # empaquetado + entry point `cazafacturas`
├── LICENSE                 # MIT
├── README.md
├── .gitignore
├── cli.py                  # CLI de evaluación
├── backend/
│   ├── main.py             # FastAPI + `main()` arranca webapp
│   ├── api/                # endpoints: motores, ejecutar, resultados, países
│   ├── nucleo/
│   │   ├── esquema.py      # contrato Factura (Pydantic) con país
│   │   ├── evaluador.py    # métricas: precisión, invención, normalización por país
│   │   ├── cache.py        # caché por hash (doc + motor + modelo + idioma)
│   │   ├── dataset.py      # carga multipaís + trampas
│   │   ├── paises.py       # config ES/UK/US/DE
│   │   ├── motores/
│   │   │   ├── base.py     # interfaz común
│   │   │   ├── cli.py      # subproceso claude/codex
│   │   │   ├── api.py      # Anthropic / OpenAI / Google
│   │   │   ├── ollama.py   # HTTP local
│   │   │   └── prompt.py   # prompt bilingüe parametrizado por país
│   │   └── almacen.py      # persistencia de ejecuciones
│   └── tests/
├── dataset/
│   ├── generador.py        # 6 facturas/país + trampas
│   ├── generar_trampas.py
│   ├── ES/ UK/ US/ DE/     # facturas/esperado por país
│   └── trampas/            # 10 trampas × 4 países
├── frontend/
│   ├── index.html          # 4 pantallas + i18n
│   ├── estilo.css          # design system premium (papel/tinta, 3 colores)
│   ├── app.js              # lógica completa (SSE, nodos, detalle)
│   └── i18n.js             # diccionario ES/EN
└── resultados/             # ejecuciones + cache (gitignored)
```

---

## Cuatro pantallas

1. **Panel** — Tabla comparativa entre motores (precisión, invención, aciertos, fallos, tiempo, casos) + lista de campos más inventados.
2. **Ejecución en vivo** — Grid de nodos (una factura = un nodo). Cada nodo cambia de estado en tiempo real: *En cola → Analizando → OK / Falló*. Click → Detalle.
3. **Detalle** — Documento original | Respuesta esperada | Respuesta obtenida + tabla campo a campo (OK / Fallo / Invención con colores dedicados).
4. **Dataset** — Cartas navegables por país, filtro (todos / normales / trampas), click → Detalle.

---

## Diseño

- **Tipografía**: Cormorant Garamond (display) + JetBrains Mono (datos/código).
- **Paleta**: Fondo papel (#faf8f3 / #121010 dark), tinta cálida. Tres colores funcionales y **solo tres**: *Acierto* (verde), *Fallo* (rojo-naranja), *Invención* (rosa fuerte) — la invención tiene color propio y llamativo porque **es lo que quieres que mire la gente**.
- **Dark mode** automático (respete `prefers-color-scheme`) + toggle manual.
- **Responsive** hasta móvil.
- **Accesibilidad**: foco visible, contraste ≥ 4.5:1, semántica HTML.

---

## Variables de entorno opcionales

| Variable | Qué hace |
|----------|----------|
| `MOTOR_CLI_DEFAULT` | `claude` o `codex` (por defecto `claude`) |
| `MOTOR_CLI_MODEL` | Modelo CLI (por defecto `sonnet`) |
| `ANTHROPIC_API_KEY` | Clave API Anthropic |
| `OPENAI_API_KEY` | Clave API OpenAI |
| `GOOGLE_API_KEY` | Clave API Google |
| `OLLAMA_URL` | URL Ollama (por defecto `http://localhost:11434`) |
| `OLLAMA_MODEL` | Modelo Ollama (por defecto primero disponible) |
| `CAZAFACTURAS_HOME` | Directorio de datos (ejecuciones + cache). Por defecto `./resultados` en repo, o `~/.cazafacturas` si instalado vía pip. |
| `HOST` / `PORT` | Para `cazafacturas` CLI (por defecto `127.0.0.1:8765`) |

---

## Tests

```bash
python -m pytest backend/tests -v
# 13 tests: esquema (validaciones), evaluador (precisión, invención, normalización fechas/NIF, markdown, JSON inválido)
```

---

## Licencia

MIT — libre para usar, modificar, distribuir. Ver `LICENSE`.

---

## Estado del proyecto

- **Fase 1**: Núcleo (esquema, evaluador, dataset, generador, cache) ✅
- **Fase 2**: Tres motores (CLI, API, Ollama) con interfaz común ✅
- **Fase 3**: FastAPI + Panel web comparativo ✅
- **Fase 4**: Vista en vivo (nodos SSE), Detalle campo a campo, Dataset navegable ✅
- **Fase 5**: i18n ES/EN, 4 países, empaquetado pip, README, publicación ✅

---

## Fuera de alcance (no se añadirá)

Subida de carpetas, exportación a Excel/CSV, cuentas de usuario, multiusuario, dashboard histórico, alertas, webhooks. Cada cosa añadida retrasa la publicación; el proyecto solo sirve **publicado y usable**.

---

## Créditos

Diseñado y construido por Jorge. Motor CLI usa la sesión autenticada de **Claude Code** (Anthropic) o **Codex** (OpenAI). Prompt y métricas originales. Dataset sintético generado ad-hoc — cero datos reales.