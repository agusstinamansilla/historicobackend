"""
Backend en FastAPI para el dashboard de fondos + CEDEARs.

Endpoints:
  GET  /                 -> visor simple en HTML, con boton "Actualizar ahora"
  GET  /api/fondos       -> historico de los fondos (JSON)
  GET  /api/cedears      -> historico de CEDEARs/ETFs (JSON)
  POST /api/actualizar   -> fuerza una relectura de los CSV locales (por si
                             se subio una version nueva a mano)

FONDOS y CEDEARS se leen de archivos LOCALES (historico.csv y
cedears_historico.csv) que tienen que estar en la raiz de este mismo repo.

Esos 2 archivos se actualizan SOLOS todos los dias, via GitHub Actions
(ver .github/workflows/actualizar_diario.yml), que hace commit + push al
repo. Como Render esta configurado para redeployar en cada push, cada
actualizacion diaria dispara un redeploy automatico -- y como esta app
carga los CSV al arrancar (ver evento de "startup" mas abajo), los datos
quedan al dia sin que nadie tenga que apretar nada.

El boton "Actualizar ahora" sigue disponible por si se quiere forzar una
relectura sin esperar al proximo redeploy (por ejemplo, si se subio un
archivo a mano).

Requiere: fastapi uvicorn pandas
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

app = FastAPI(title="Backend fondos + cedears")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HISTORICO_FONDOS = Path("historico.csv")
HISTORICO_CEDEARS = Path("cedears_historico.csv")

estado = {
    "fondos": None,
    "cedears": None,
    "ultima_actualizacion": None,
}


def cargar_datos():
    resultado = {"fondos": None, "cedears": None}

    if HISTORICO_FONDOS.exists():
        try:
            estado["fondos"] = pd.read_csv(HISTORICO_FONDOS)
            resultado["fondos"] = {"ok": True, "filas": len(estado["fondos"])}
        except Exception as e:
            resultado["fondos"] = {"ok": False, "error": str(e)}
    else:
        resultado["fondos"] = {"ok": False, "error": f"No se encontro {HISTORICO_FONDOS}"}

    if HISTORICO_CEDEARS.exists():
        try:
            estado["cedears"] = pd.read_csv(HISTORICO_CEDEARS)
            resultado["cedears"] = {"ok": True, "filas": len(estado["cedears"])}
        except Exception as e:
            resultado["cedears"] = {"ok": False, "error": str(e)}
    else:
        resultado["cedears"] = {"ok": False, "error": f"No se encontro {HISTORICO_CEDEARS}"}

    estado["ultima_actualizacion"] = datetime.now().isoformat()
    resultado["actualizado"] = estado["ultima_actualizacion"]
    return resultado


@app.on_event("startup")
def cargar_al_arrancar():
    cargar_datos()


@app.post("/api/actualizar")
def actualizar():
    return cargar_datos()


@app.get("/api/fondos")
def get_fondos():
    if estado["fondos"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Sin datos cargados"}
    return {
        "datos": estado["fondos"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/api/cedears")
def get_cedears():
    if estado["cedears"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Sin datos cargados"}
    return {
        "datos": estado["cedears"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/", response_class=HTMLResponse)
def visor():
    fondos_count = len(estado["fondos"]) if estado["fondos"] is not None else 0
    cedears_count = len(estado["cedears"]) if estado["cedears"] is not None else 0
    return f"""
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Backend fondos + cedears</title>
  <style>
    body {{ font-family: Arial, sans-serif; background:#0b1f1c; color:#eafdf6; padding:32px; }}
    h1 {{ font-size: 20px; }}
    .card {{ background:#12312b; border-radius:10px; padding:16px; margin:12px 0; }}
    button {{ background:#3de8a0; border:none; padding:10px 18px; border-radius:8px; cursor:pointer; font-weight:bold; font-size:14px; }}
    #resultado {{ white-space: pre-wrap; font-family: monospace; font-size:12px; margin-top:16px; }}
    a {{ color:#3de8a0; }}
  </style>
</head>
<body>
  <h1>Backend fondos + cedears</h1>
  <div class="card">
    Fondos: {fondos_count} filas &middot; CEDEARs: {cedears_count} filas<br>
    Ultima carga: {estado["ultima_actualizacion"] or "nunca"}<br>
    <small>Se actualiza solo todos los dias a las 9am (GitHub Actions). Este boton solo fuerza una relectura manual.</small>
  </div>
  <button onclick="actualizar()">Forzar relectura ahora</button>
  <div id="resultado"></div>
  <p>Endpoints: <a href="/api/fondos">/api/fondos</a> &middot; <a href="/api/cedears">/api/cedears</a> &middot; <a href="/docs">/docs</a></p>
  <script>
    async function actualizar() {{
      document.getElementById('resultado').textContent = 'Actualizando...';
      const r = await fetch('/api/actualizar', {{ method: 'POST' }});
      const j = await r.json();
      document.getElementById('resultado').textContent = JSON.stringify(j, null, 2);
    }}
  </script>
</body>
</html>
"""
