"""
Backend en FastAPI para el dashboard de fondos + CEDEARs.

Endpoints:
  GET  /                 -> visor simple en HTML, con boton "Actualizar ahora"
  GET  /api/fondos       -> ultimo historico de los fondos (JSON)
  GET  /api/cedears      -> ultima serie completa de CEDEARs/ETFs (JSON)
  POST /api/actualizar   -> dispara la actualizacion (fondos + cedears)

FONDOS: se leen de un archivo LOCAL "historico.csv" que tiene que estar
subido en la raiz de este mismo repo (al lado de main.py). No se conecta
a ningun GitHub externo -- quien deploye este backend controla sus propios
datos subiendo su propia version de historico.csv.

CEDEARS: se descarga la serie COMPLETA de cada ticker desde Yahoo Finance
cada vez que se aprieta "Actualizar" (se pisa entera, por los dividendos).

Requiere: fastapi uvicorn pandas yfinance
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf
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

# Archivo local con el historico de fondos (subilo junto a main.py en el repo)
HISTORICO_CSV_LOCAL = Path("historico.csv")

TICKERS_CEDEARS = os.environ.get("TICKERS_CEDEARS", "VIG,GLD,SPY,QQQ,IBIT,TQQQ").split(",")

estado = {
    "fondos": None,
    "cedears": None,
    "ultima_actualizacion": None,
}


def descargar_ticker_yahoo(ticker: str):
    """Devuelve (dataframe, error). Si error no es None, dataframe es None."""
    try:
        df = yf.download(
            ticker, period="max", interval="1d", auto_adjust=True,
            progress=False, threads=False,
        )
        if df.empty:
            return None, "yfinance devolvio un dataframe vacio (posible bloqueo de Yahoo a IPs de datacenter, o ticker invalido)"

        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = [c[0] for c in df.columns]

        df = df[["Open", "High", "Low", "Close"]].copy()
        df = df.reset_index()
        df.columns = ["fecha", "open", "high", "low", "close"]
        df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%Y-%m-%d")
        df["ticker"] = ticker
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].round(4)
        return df[["ticker", "fecha", "open", "high", "low", "close"]], None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


@app.post("/api/actualizar")
def actualizar():
    resultado = {"fondos": None, "cedears": None}

    # --- Fondos: leer el archivo local (subido en el repo) ---
    try:
        if not HISTORICO_CSV_LOCAL.exists():
            resultado["fondos"] = {"ok": False, "error": f"No se encontro {HISTORICO_CSV_LOCAL} en el repo. Subilo junto a main.py."}
        else:
            df_fondos = pd.read_csv(HISTORICO_CSV_LOCAL)
            estado["fondos"] = df_fondos
            resultado["fondos"] = {"ok": True, "filas": len(df_fondos)}
    except Exception as e:
        resultado["fondos"] = {"ok": False, "error": str(e)}

    # --- CEDEARs: descargar serie completa de cada ticker desde Yahoo ---
    partes = []
    errores_por_ticker = {}
    for ticker in TICKERS_CEDEARS:
        ticker = ticker.strip()
        df_t, err = descargar_ticker_yahoo(ticker)
        if err:
            errores_por_ticker[ticker] = err
        else:
            partes.append(df_t)

    if partes:
        estado["cedears"] = pd.concat(partes, ignore_index=True)

    resultado["cedears"] = {
        "ok": len(partes) > 0,
        "filas": len(estado["cedears"]) if estado["cedears"] is not None else 0,
        "tickers_ok": [p["ticker"].iloc[0] for p in partes],
        "tickers_fallidos": errores_por_ticker,
    }

    estado["ultima_actualizacion"] = datetime.now().isoformat()
    resultado["actualizado"] = estado["ultima_actualizacion"]
    return resultado


@app.get("/api/fondos")
def get_fondos():
    if estado["fondos"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Todavia no se aprieta 'Actualizar'"}
    return {
        "datos": estado["fondos"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/api/cedears")
def get_cedears():
    if estado["cedears"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Todavia no se aprieta 'Actualizar'"}
    return {
        "datos": estado["cedears"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/", response_class=HTMLResponse)
def visor():
    fondos_count = len(estado["fondos"]) if estado["fondos"] is not None else 0
    cedears_count = len(estado["cedears"]) if estado["cedears"] is not None else 0
    archivo_local_existe = HISTORICO_CSV_LOCAL.exists()
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
    .aviso {{ color: {"#3DE8A0" if archivo_local_existe else "#FF7A68"}; }}
  </style>
</head>
<body>
  <h1>Backend fondos + cedears</h1>
  <div class="card">
    Archivo historico.csv en el repo: <span class="aviso">{"encontrado" if archivo_local_existe else "NO ENCONTRADO -- subilo junto a main.py"}</span><br>
    Estado actual: fondos = {fondos_count} filas, cedears = {cedears_count} filas<br>
    Ultima actualizacion: {estado["ultima_actualizacion"] or "nunca"}
  </div>
  <button onclick="actualizar()">Actualizar ahora</button>
  <div id="resultado"></div>
  <p>Endpoints: <a href="/api/fondos">/api/fondos</a> &middot; <a href="/api/cedears">/api/cedears</a> &middot; <a href="/docs">/docs</a></p>
  <script>
    async function actualizar() {{
      document.getElementById('resultado').textContent = 'Actualizando... puede tardar unos segundos';
      const r = await fetch('/api/actualizar', {{ method: 'POST' }});
      const j = await r.json();
      document.getElementById('resultado').textContent = JSON.stringify(j, null, 2);
    }}
  </script>
</body>
</html>
"""
