from backend.main import app
from fastapi.testclient import TestClient
from pathlib import Path

c = TestClient(app)
ok = True
fails = []

def check(name, cond, detail=""):
    global ok
    if cond:
        print(f"  OK   {name}")
    else:
        ok = False
        fails.append(name)
        print(f"  FAIL {name} {detail}")

print("=== ENDPOINTS ===")
r = c.get("/")
check("GET /", r.status_code == 200)
r2 = c.get("/static/estilo.css")
check("GET /static/estilo.css", r2.status_code == 200)
r3 = c.get("/static/app.js")
check("GET /static/app.js", r3.status_code == 200)
r4 = c.get("/static/i18n.js")
check("GET /static/i18n.js", r4.status_code == 200)

r = c.get("/api/estado")
check("GET /api/estado", r.status_code == 200)
mot = r.json()["motores"]
check("5 motores", len(mot) == 5, str(len(mot)))
check("cli disponible", any(m["id"] == "cli" and m["estado"] == "disponible" for m in mot))
check("cada motor con id/nombre/estado", all("id" in m and "nombre" in m and "estado" in m for m in mot))

r = c.get("/api/dataset")
check("GET /api/dataset", r.status_code == 200, str(r.status_code))
r = c.get("/api/dataset?trampas=true")
todos = r.json()
check("GET /api/dataset?trampas=true", r.status_code == 200, str(len(todos)))
# con 4 países x 6 facturas + 4 países x 10 trampas
norm = [x for x in todos if not x["es_trampa"]]
trampas = [x for x in todos if x["es_trampa"]]
check("normales 24", len(norm) == 24, str(len(norm)))
check("trampas 40", len(trampas) == 40, str(len(trampas)))
paises = set(x["esperado"].get("pais", "ES") for x in todos)
check("4 paises en dataset", len(paises) == 4, str(paises))

r = c.get("/api/dataset?pais=UK")
uk = r.json()
check("GET /api/dataset?pais=UK", r.status_code == 200 and len(uk) == 16, str(len(uk)))

r = c.get("/api/paises")
check("GET /api/paises", r.status_code == 200 and len(r.json()) == 4, str(len(r.json())))

r = c.get("/api/comparativa")
check("GET /api/comparativa", r.status_code == 200)
r = c.get("/api/resultados")
check("GET /api/resultados", r.status_code == 200)

print("\n=== HTML IDs ===")
html = c.get("/").text
ids = ["nav","btn-tema","select-motor","check-trampas","btn-ejecutar",
       "seccion-progreso","barra-relleno","texto-progreso","seccion-motores",
       "contenedor-comparativa","contenedor-tabla","cuerpo-comparativa",
       "contenedor-invenciones",
       "pantalla-panel","pantalla-ejecucion","pantalla-detalle","pantalla-dataset",
       "ejecucion-subtitle","ejecucion-meta","meta-progreso","meta-aciertos","meta-fallos","meta-invenciones",
       "nodos-vacia","nodos-grid",
       "detalle-titulo","detalle-sub","detalle-documento","detalle-esperado","detalle-obtenido","detalle-campos",
       "btn-volver-ejecucion","dataset-grid",
       "select-idioma","select-pais"]
for i in ids:
    check(f"id #{i}", f'id="{i}"' in html)

print("\n=== CSS ===")
css = r2.text
for tok in [":root","--papel","--tinta","--acierto","--fallo","--invencion",'[data-theme="dark"]',"@media"]:
    check(f"css {tok}", tok in css)
check("css .pantalla.activa", ".pantalla.activa" in css)
check("css braces balance", css.count("{") == css.count("}"))

print("\n=== JS ===")
js = r3.text
for fn in ["navegarA","cargarMotores","cargarComparativa","ejecutarLote","cargarDataset","verDetalle","renderizarCampos",".addEventListener","EventSource","localStorage","aplicarIdioma","cambiarIdioma"]:
    check(f"js {fn}", fn in js)
check("js parens balance", js.count("(") == js.count(")"))
check("js braces balance", js.count("{") == js.count("}"))

print("\n=== i18n.js ===")
i18n = r4.text
check("i18n dict ES/EN", "I18N" in i18n and '"es"' in i18n and '"en"' in i18n)

print("\n=== TESTS ===")
import subprocess, sys
p = subprocess.run([sys.executable, "-m", "pytest", "backend/tests", "-q"], capture_output=True, text=True)
check("tests pasan", p.returncode == 0, p.stdout[-200:] + p.stderr[-200:])

print("\n=== VEREDICTO ===")
if ok:
    print("TODOS OK — app terminada")
else:
    print(f"{len(fails)} FALLOS: {fails}")