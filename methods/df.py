import pandas as pd
import os
from datetime import datetime

COLUMN_TYPES = {
    "file": str,
    "Tipo": str,
    "Numero": str,
    "Empresa": str,
    "Fecha_Documento": datetime,
    "Moneda": str,
    "Concepto": str,
    "Subtotal": float,
    "IVA_minimo_10": float,
    "IVA_basico_22": float,
    "Total": float,
}

def save_to_xlsx(results):
    rows = []
    for r in results:
        row = {"file": r["file"]}
        if r["data"] is not None:
            # agregar campos esperados aunque falten en r["data"]
            for key in COLUMN_TYPES.keys():
                if key != "file":
                    row[key] = r["data"].get(key, None)
        rows.append(row)

    df = pd.DataFrame(rows)

    # Forzar tipos
    for col, col_type in COLUMN_TYPES.items():
        if col in df.columns:
            if col_type in [int, float]:
                # Convierte a numérico, transforma valores inválidos en NaN
                df[col] = pd.to_numeric(df[col], errors='coerce')
            elif col_type == datetime:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
            else:
                # Para strings u otros tipos
                df[col] = df[col].astype(col_type, copy=False)


    # Carpeta Descargas del usuario
    home = os.path.expanduser("~")
    downloads = os.path.join(home, "Downloads")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"inv_reading_output_{timestamp}.xlsx"
    filepath = os.path.join(downloads, filename)

    df.to_excel(filepath, index=False)

    os.startfile(filepath)