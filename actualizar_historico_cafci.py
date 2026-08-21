"""
Actualiza el historico de VCP (Valor de Cuotaparte) de un conjunto fijo de FCI,
bajando todos los dias la planilla publica de CAFCI y agregando las filas nuevas
a un archivo historico.csv (formato largo: fondo, fecha, vcp).

Pensado para correr una vez por dia (por ejemplo via GitHub Actions con un
cron job), y que el historico.csv resultante alimente un dashboard aparte.

FUENTE DE DATOS
------------------------------------------------
https://api.pub.cafci.org.ar/pb_get
Es la "descarga de la ultima planilla diaria" que ofrece CAFCI en su home
(https://www.cafci.org.ar/), publica y sin necesidad de login. Trae la info
del ultimo dia habil para TODOS los fondos del mercado.

Estructura del archivo (confirmada por la usuaria):
    Columna A: nombre del fondo + clase (ej. "Gainvest Renta Fija Dolares - Clase A")
    Columna E: fecha
    Columna F: valor de cuotaparte (VCP)

Como la fuente no esta documentada oficialmente, si CAFCI cambia el formato
el script puede necesitar un ajuste. Por eso, si un fondo esperado no aparece
en la planilla del dia, se imprime un aviso en vez de fallar en silencio.

Requisitos:
    pip install pandas openpyxl requests
"""

import re
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

# ------------------------------------------------------------------
# CONFIGURACION
# ------------------------------------------------------------------

PLANILLA_URL = "https://api.pub.cafci.org.ar/pb_get"

# Nombres exactos tal como aparecen en la planilla de CAFCI (columna A)
FONDOS_DE_INTERES = [
    "Fima Premium - Clase A",
    "Gainvest FF - Clase A",
    "Gainvest Global I - Clase A",
    "Gainvest Renta Fija Dolares - Clase A",
    "Galileo Ahorro Plus - Clase A",
    "Galileo Event Driven - Clase A",
    "Galileo Income - Clase B",
    "Galileo Fixed Income - Clase B",
    "Galileo Multi Strategy - Clase A",
    "Parakeet MM Investments Fund - Clase B",
]

# Columnas en la planilla (0-indexado): A=0, E=4, F=5
COL_NOMBRE = 0
COL_FECHA = 4
COL_VCP = 5

HISTORICO_CSV = Path("historico.csv")  # se crea/actualiza en la carpeta del repo

# Si la planilla no tiene fila de encabezados fija, dejamos header=None y
# buscamos las filas por contenido en vez de por posicion de header.
LEER_SIN_HEADER = True


# ------------------------------------------------------------------
# FUNCIONES
# ------------------------------------------------------------------

def normalizar(texto: str) -> str:
    """Baja a minuscula, saca tildes y espacios de mas, para poder comparar
    nombres de fondos aunque haya pequenas diferencias de formato."""
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = texto.lower().strip()
    texto = re.sub(r"\s+", " ", texto)
    return texto


def descargar_planilla() -> pd.DataFrame:
    resp = requests.get(PLANILLA_URL, timeout=30)
    resp.raise_for_status()

    tmp_path = Path("planilla_diaria_temp.xlsx")
    tmp_path.write_bytes(resp.content)

    if LEER_SIN_HEADER:
        df = pd.read_excel(tmp_path, header=None)
    else:
        df = pd.read_excel(tmp_path)

    tmp_path.unlink(missing_ok=True)
    return df


def extraer_fondos_de_interes(df: pd.DataFrame) -> pd.DataFrame:
    objetivo_normalizado = {normalizar(n): n for n in FONDOS_DE_INTERES}

    filas = []
    encontrados = set()

    for _, row in df.iterrows():
        nombre_crudo = row[COL_NOMBRE]
        nombre_norm = normalizar(nombre_crudo)
        if nombre_norm in objetivo_normalizado:
            nombre_original = objetivo_normalizado[nombre_norm]
            filas.append({
                "fondo": nombre_original,
                "fecha": row[COL_FECHA],
                "vcp": row[COL_VCP] / 1000,
            })
            encontrados.add(nombre_original)

    faltantes = set(FONDOS_DE_INTERES) - encontrados
    if faltantes:
        print("AVISO: no se encontraron estos fondos en la planilla de hoy:")
        for f in sorted(faltantes):
            print(f"  - {f}")
        print("(puede ser que ese fondo no haya operado ese dia, o que el "
              "nombre en la planilla cambio un poco - revisar manualmente)")

    return pd.DataFrame(filas)


def actualizar_historico(nuevas_filas: pd.DataFrame):
    if nuevas_filas.empty:
        print("No se encontraron filas de los fondos de interes en la planilla de hoy. No se actualiza nada.")
        return

    nuevas_filas["fecha"] = pd.to_datetime(nuevas_filas["fecha"], format="mixed", dayfirst=True).dt.date

    if HISTORICO_CSV.exists():
        historico = pd.read_csv(HISTORICO_CSV, parse_dates=["fecha"])
        historico["fecha"] = historico["fecha"].dt.date
    else:
        historico = pd.DataFrame(columns=["fondo", "fecha", "vcp"])

    combinado = pd.concat([historico, nuevas_filas], ignore_index=True)
    combinado = combinado.drop_duplicates(subset=["fondo", "fecha"], keep="last")
    combinado = combinado.sort_values(["fondo", "fecha"])

    combinado["vcp"] = combinado["vcp"].round(6)
    combinado.to_csv(HISTORICO_CSV, index=False)

    agregadas = len(combinado) - len(historico)
    print(f"Historico actualizado: {HISTORICO_CSV} ({agregadas} fila(s) nueva(s), {len(combinado)} en total)")


if __name__ == "__main__":
    print(f"Corriendo actualizacion - {datetime.now().isoformat()}")
    df_planilla = descargar_planilla()
    print(f"Planilla descargada: {len(df_planilla)} filas totales")

    df_interes = extraer_fondos_de_interes(df_planilla)
    print(f"Fondos de interes encontrados hoy: {len(df_interes)}")
    print("Fechas encontradas:", df_interes["fecha"].unique())

    actualizar_historico(df_interes)
