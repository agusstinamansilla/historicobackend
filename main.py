"""
Backend en FastAPI para el dashboard de fondos + CEDEARs.

Endpoints:
  GET  /                 -> visor simple en HTML, con boton "Actualizar ahora"
  GET  /api/fondos       -> ultimo historico "publicado" (JSON)
  GET  /api/cedears      -> ultima serie "publicada" (JSON)
  POST /api/actualizar   -> trae la version MAS RECIENTE de GitHub y la
                             "publica" -- esto es lo unico que actualiza lo
                             que se muestra. Si no se aprieta, se sigue
                             viendo la misma foto de la ultima vez, aunque
                             pasen varios dias y el cron haya seguido
                             guardando en silencio.

IMPORTANTE: los datos NUNCA se cargan solos, ni al arrancar el servicio
ni en ningun redeploy -- la UNICA forma de que se actualice lo publicado
es apretando el boton "Actualizar ahora" (que llama a POST /api/actualizar).
Por eso no hace falta tocar el Auto-Deploy de Render: el resto del
dashboard puede seguir redeployando normalmente con cada cambio de codigo,
sin que eso dispare una publicacion de datos nueva aca.

Requiere: fastapi uvicorn pandas requests
"""

import os
from datetime import datetime
from io import StringIO

import pandas as pd
import requests
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

# Se puede cambiar sin tocar el codigo, via variable de entorno en Render
# (asi cada quien apunta a su propio repo sin modificar main.py)
REPO_RAW_BASE = os.environ.get(
    "REPO_RAW_BASE",
    "https://raw.githubusercontent.com/agusstinamansilla/historicobackend/main",
)
HISTORICO_FONDOS_URL = f"{REPO_RAW_BASE}/historico.csv"
HISTORICO_CEDEARS_URL = f"{REPO_RAW_BASE}/cedears_historico.csv"

estado = {
    "fondos": None,
    "cedears": None,
    "ultima_actualizacion": None,
}


def publicar():
    """Trae la version mas reciente de GitHub y la 'publica' (unico lugar
    donde estado[] cambia). Se llama al arrancar UNA vez, y despues solo
    cuando se aprieta el boton."""
    resultado = {"fondos": None, "cedears": None}

    try:
        resp = requests.get(HISTORICO_FONDOS_URL, timeout=30)
        resp.raise_for_status()
        estado["fondos"] = pd.read_csv(StringIO(resp.text))
        resultado["fondos"] = {"ok": True, "filas": len(estado["fondos"])}
    except Exception as e:
        resultado["fondos"] = {"ok": False, "error": str(e)}

    try:
        resp = requests.get(HISTORICO_CEDEARS_URL, timeout=30)
        resp.raise_for_status()
        estado["cedears"] = pd.read_csv(StringIO(resp.text))
        resultado["cedears"] = {"ok": True, "filas": len(estado["cedears"])}
    except Exception as e:
        resultado["cedears"] = {"ok": False, "error": str(e)}

    estado["ultima_actualizacion"] = datetime.now().isoformat()
    resultado["actualizado"] = estado["ultima_actualizacion"]
    return resultado


@app.post("/api/actualizar")
def actualizar():
    return publicar()


@app.get("/api/fondos")
def get_fondos():
    if estado["fondos"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Sin datos publicados todavia"}
    return {
        "datos": estado["fondos"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/api/cedears")
def get_cedears():
    if estado["cedears"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Sin datos publicados todavia"}
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
    Publicado ahora: {fondos_count} filas de fondos &middot; {cedears_count} filas de cedears<br>
    Ultima publicacion: {estado["ultima_actualizacion"] or "nunca"}<br>
    <small>El cron guarda datos nuevos todos los dias en GitHub, pero ESTO solo se actualiza al apretar el boton.</small>
  </div>
  <button onclick="actualizar()">Actualizar ahora</button>
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
