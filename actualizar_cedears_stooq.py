"""
Descarga la serie historica COMPLETA de un set fijo de CEDEARs/ETFs desde
STOOQ (no Yahoo Finance), porque Yahoo suele bloquear pedidos que vienen
de servidores en la nube (Render, GitHub Actions, etc.) y Stooq no.

Guarda todo en cedears_historico.csv (columnas: ticker, fecha, open, high, low, close)
Siempre pisa la serie entera de cada ticker (por los dividendos que ajustan
retroactivamente los precios).

Requiere: pip install pandas requests
"""

from pathlib import Path
import pandas as pd
import requests
from io import StringIO

TICKERS = ["VIG", "GLD", "SPY", "QQQ", "IBIT", "TQQQ"]
OUTPUT_CSV = Path("cedears_historico.csv")

STOOQ_URL = "https://stooq.com/q/d/l/?s={ticker}.US&i=d"


def descargar_ticker(ticker: str) -> pd.DataFrame:
    url = STOOQ_URL.format(ticker=ticker.lower())
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()

    texto = resp.text.strip()
    if not texto or texto.startswith("<"):
        print(f"  AVISO: Stooq no devolvio datos validos para {ticker}")
        return pd.DataFrame()

    df = pd.read_csv(StringIO(texto))
    if df.empty or "Date" not in df.columns:
        print(f"  AVISO: respuesta vacia o con formato inesperado para {ticker}")
        return pd.DataFrame()

    df = df.rename(columns={
        "Date": "fecha", "Open": "open", "High": "high",
        "Low": "low", "Close": "close",
    })
    df["ticker"] = ticker
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].round(4)
    return df[["ticker", "fecha", "open", "high", "low", "close"]]


def main():
    print("Descargando serie completa de CEDEARs/ETFs desde Stooq...")
    partes = []
    for ticker in TICKERS:
        print(f"  {ticker}...")
        df = descargar_ticker(ticker)
        if not df.empty:
            partes.append(df)
            print(f"    {len(df)} filas, {df['fecha'].min()} a {df['fecha'].max()}")

    if not partes:
        print("ERROR: no se pudo descargar ningun ticker.")
        return

    combinado = pd.concat(partes, ignore_index=True)
    combinado.to_csv(OUTPUT_CSV, index=False)
    print(f"\nGuardado: {OUTPUT_CSV} ({len(combinado)} filas totales)")


if __name__ == "__main__":
    main()
