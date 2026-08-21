"""
Descarga la serie historica COMPLETA de un set fijo de CEDEARs/ETFs desde
Yahoo Finance (yfinance), pensado para correr en GitHub Actions (no en
Render, donde Yahoo suele bloquear los pedidos).

Guarda todo en cedears_historico.csv (columnas: ticker, fecha, open, high, low, close)
Siempre pisa la serie entera de cada ticker (por los dividendos que ajustan
retroactivamente los precios).

Requiere: pip install pandas yfinance
"""

from pathlib import Path
import pandas as pd
import yfinance as yf

TICKERS = ["VIG", "GLD", "SPY", "QQQ", "IBIT", "TQQQ"]
OUTPUT_CSV = Path("cedears_historico.csv")


def descargar_ticker(ticker: str) -> pd.DataFrame:
    try:
        df = yf.download(ticker, period="max", interval="1d", auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        print(f"  ERROR {ticker}: {e}")
        return pd.DataFrame()

    if df.empty:
        print(f"  AVISO: Yahoo devolvio vacio para {ticker}")
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


def main():
    print("Descargando serie completa de CEDEARs/ETFs desde Yahoo Finance...")
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
