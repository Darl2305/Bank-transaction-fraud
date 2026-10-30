"""
Ingeniería de variables compartida entre el notebook y la app de Streamlit.

Tener una sola función `build_features` evita el clásico problema de
"training-serving skew": el modelo se entrena con una transformación y en
producción se le entrega otra distinta. Aquí ambos usan exactamente la misma.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Constantes del problema
# --------------------------------------------------------------------------

# Categorías de comercio presentes en el dataset (orden fijo = categorías fijas
# para LightGBM; si llega una categoría nueva se convierte en NaN y el modelo
# la trata como "desconocida" en lugar de romperse).
MERCHANT_CATEGORIES = [
    "ATM Withdrawal", "Clothing", "Crypto Exchange", "Education", "Electronics",
    "Entertainment", "Fuel", "Gaming", "Grocery", "Healthcare", "Jewelry",
    "Online Shopping", "Restaurant", "Travel", "Utilities",
]

# Hallazgo del EDA: estos tres comercios casi duplican la tasa de fraude (~8.7 %
# frente a ~4.7 % del resto). Se usa solo para explicar en la app, el modelo lo
# aprende por su cuenta a partir de `merchant_category`.
RISKY_MERCHANTS = ["Crypto Exchange", "Jewelry", "ATM Withdrawal"]

# Franja que el dataset marca como "nocturna": de 22:00 a 06:59.
NIGHT_HOURS = {22, 23, 0, 1, 2, 3, 4, 5, 6}

# Columnas mínimas que debe traer un CSV para poder ser puntuado.
REQUIRED_COLUMNS = [
    "merchant_category",
    "transaction_amount",
    "account_balance",
    "credit_score",
    "time_since_last_txn_hrs",
    "failed_attempts",
    "is_international",
    "pin_changed_recently",
]
# Además se necesita la hora: o bien `hour_of_day`, o bien `transaction_time`.

# Variables finales que ve el modelo (ver sección 4 del notebook: la selección
# se justifica con una comparación contra el set completo de 20 variables).
FEATURES = [
    "merchant_category",
    "hour_of_day",
    "is_night",
    "failed_attempts",
    "is_international",
    "pin_changed_recently",
    "log_amount",
    "amount_to_balance",
    "log_account_balance",
    "credit_score",
    "time_since_last_txn_hrs",
]

# Nombres legibles para la app (explicación de cada predicción).
FEATURE_LABELS = {
    "merchant_category": "Tipo de comercio",
    "hour_of_day": "Hora del día",
    "is_night": "Transacción nocturna",
    "failed_attempts": "Intentos fallidos",
    "is_international": "Transacción internacional",
    "pin_changed_recently": "PIN cambiado recientemente",
    "log_amount": "Monto de la transacción",
    "amount_to_balance": "Monto / saldo de la cuenta",
    "log_account_balance": "Saldo de la cuenta",
    "credit_score": "Credit score",
    "time_since_last_txn_hrs": "Horas desde la última transacción",
}


# --------------------------------------------------------------------------
# Funciones
# --------------------------------------------------------------------------

def resolve_hour(df: pd.DataFrame) -> pd.Series:
    """Devuelve la hora (0-23). Usa `hour_of_day` si existe, si no la deriva de
    `transaction_time` (formato HH:MM:SS)."""
    if "hour_of_day" in df.columns:
        return pd.to_numeric(df["hour_of_day"], errors="coerce")
    if "transaction_time" in df.columns:
        return pd.to_datetime(df["transaction_time"], format="%H:%M:%S", errors="coerce").dt.hour
    raise KeyError("Falta `hour_of_day` o `transaction_time` para calcular la hora.")


def missing_columns(df: pd.DataFrame) -> list[str]:
    """Lista de columnas obligatorias que faltan en `df`."""
    faltan = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if "hour_of_day" not in df.columns and "transaction_time" not in df.columns:
        faltan.append("hour_of_day (o transaction_time)")
    return faltan


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte transacciones crudas en la matriz que consume el modelo.

    Decisiones de diseño:
    - Los montos y saldos tienen asimetría fuerte (skew ~10 y ~6), por eso se
      usa log1p. Para árboles no es obligatorio, pero estabiliza la lectura de
      las contribuciones y permite usar también una regresión logística.
    - `amount_to_balance` captura "qué tan grande es esta compra para ESTA
      cuenta", más informativo que el monto absoluto.
    - `is_night` se deriva de la hora para que la app solo pida la hora.
    """
    hora = resolve_hour(df)
    monto = pd.to_numeric(df["transaction_amount"], errors="coerce")
    saldo = pd.to_numeric(df["account_balance"], errors="coerce")

    X = pd.DataFrame(index=df.index)
    X["merchant_category"] = pd.Categorical(df["merchant_category"], categories=MERCHANT_CATEGORIES)
    X["hour_of_day"] = hora
    X["is_night"] = hora.isin(NIGHT_HOURS).astype(int)
    X["failed_attempts"] = pd.to_numeric(df["failed_attempts"], errors="coerce")
    X["is_international"] = pd.to_numeric(df["is_international"], errors="coerce")
    X["pin_changed_recently"] = pd.to_numeric(df["pin_changed_recently"], errors="coerce")
    X["log_amount"] = np.log1p(monto)
    X["amount_to_balance"] = monto / saldo.clip(lower=1)
    X["log_account_balance"] = np.log1p(saldo)
    X["credit_score"] = pd.to_numeric(df["credit_score"], errors="coerce")
    X["time_since_last_txn_hrs"] = pd.to_numeric(df["time_since_last_txn_hrs"], errors="coerce")
    return X[FEATURES]
