"""
Backend en FastAPI para el dashboard de fondos + CEDEARs.

Endpoints:
  GET  /api/fondos     -> ultimo historico "publicado" de los 10 fondos (JSON)
  GET  /api/cedears    -> ultima serie completa de CEDEARs/ETFs (JSON)
  POST /api/actualizar -> dispara la actualizacion:
       1) trae el historico.csv mas reciente desde GitHub (lo que el cron
          diario viene guardando en silencio) y lo "publica"
       2) descarga la serie COMPLETA de los CEDEARs desde Yahoo Finance
          (se pisa entera cada vez, por los dividendos)

Los datos publicados quedan en memoria (no en disco), asi que sobreviven
mientras el servicio este corriendo, pero se pierden si Render reinicia
el servicio por inactividad (plan free). Si eso es un problema, avisame
y lo cambiamos a un Render Disk persistente.

Requiere: fastapi uvicorn pandas requests yfinance
"""

from datetime import datetime
from io import StringIO

import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Backend fondos + cedears")

# Permite que el dashboard (en Vercel, otro dominio) llame a este backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # en produccion, mejor restringir al dominio exacto de Vercel
    allow_methods=["*"],
    allow_headers=["*"],
)

HISTORICO_CSV_URL = "https://raw.githubusercontent.com/agusstinamansilla/fondos-dashboard/main/historico.csv"

TICKERS_CEDEARS = ["VIG", "GLD", "SPY", "QQQ", "IBIT", "TQQQ"]

# Estado en memoria: se llena cuando se llama POST /api/actualizar
estado = {
    "fondos": None,          # DataFrame
    "cedears": None,         # DataFrame
    "ultima_actualizacion": None,
}


def descargar_ticker_yahoo(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="max", interval="1d", auto_adjust=True, progress=False)
    if df.empty:
        return pd.DataFrame()
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = [c[0] for c in df.columns]
    df = df[["Open", "High", "Low", "Close"]].copy()
    df = df.reset_index()
    df.columns = ["fecha", "open", "high", "low", "close"]
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%Y-%m-%d")
    df["ticker"] = ticker
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].round(4)
    return df[["ticker", "fecha", "open", "high", "low", "close"]]


@app.post("/api/actualizar")
def actualizar():
    # 1. Traer el historico.csv mas reciente desde GitHub (lo que el cron
    #    diario viene acumulando en silencio) y "publicarlo"
    resp = requests.get(HISTORICO_CSV_URL, timeout=30)
    if not resp.ok:
        raise HTTPException(status_code=502, detail=f"No se pudo bajar historico.csv de GitHub ({resp.status_code})")
    df_fondos = pd.read_csv(StringIO(resp.text))
    estado["fondos"] = df_fondos

    # 2. Descargar la serie COMPLETA de cada CEDEAR/ETF desde Yahoo
    partes = []
    fallidos = []
    for ticker in TICKERS_CEDEARS:
        df_t = descargar_ticker_yahoo(ticker)
        if df_t.empty:
            fallidos.append(ticker)
        else:
            partes.append(df_t)

    if partes:
        estado["cedears"] = pd.concat(partes, ignore_index=True)
    elif estado["cedears"] is None:
        estado["cedears"] = pd.DataFrame(columns=["ticker", "fecha", "open", "high", "low", "close"])

    estado["ultima_actualizacion"] = datetime.now().isoformat()

    return {
        "ok": True,
        "fondos_filas": len(df_fondos),
        "cedears_filas": len(estado["cedears"]),
        "cedears_fallidos": fallidos,
        "actualizado": estado["ultima_actualizacion"],
    }


@app.get("/api/fondos")
def get_fondos():
    if estado["fondos"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Todavia no se corrio ninguna actualizacion"}
    return {
        "datos": estado["fondos"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/api/cedears")
def get_cedears():
    if estado["cedears"] is None:
        return {"datos": [], "ultima_actualizacion": None, "aviso": "Todavia no se corrio ninguna actualizacion"}
    return {
        "datos": estado["cedears"].to_dict(orient="records"),
        "ultima_actualizacion": estado["ultima_actualizacion"],
    }


@app.get("/")
def salud():
    return {"status": "ok", "ultima_actualizacion": estado["ultima_actualizacion"]}
