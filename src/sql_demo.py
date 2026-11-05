"""Conexión segura a la base SQLite del proyecto (pestaña «Consultas SQL» de la app)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "fraude_bancario.db"
MAX_FILAS = 1000        # tope de filas que se muestran
MAX_SEGUNDOS = 10       # tiempo máximo por consulta

# Preguntas de negocio listas para ejecutar (el usuario puede editarlas)
CONSULTAS = {
    "1. ¿Cómo evoluciona el fraude por año?": """SELECT anio,
       SUM(transacciones)                                  AS transacciones,
       SUM(fraudes)                                        AS fraudes,
       ROUND(100.0 * SUM(fraudes) / SUM(transacciones), 2) AS tasa_fraude_pct
FROM agg_mensual_comercio
GROUP BY anio
ORDER BY anio;""",

    "2. ¿Qué comercios tienen más fraude?": """SELECT comercio,
       SUM(transacciones)                                  AS transacciones,
       SUM(fraudes)                                        AS fraudes,
       ROUND(100.0 * SUM(fraudes) / SUM(transacciones), 2) AS tasa_fraude_pct
FROM agg_mensual_comercio
GROUP BY comercio
ORDER BY tasa_fraude_pct DESC;""",

    "3. ¿A qué hora ocurre el fraude? (2024)": """SELECT CASE
           WHEN hora >= 22 OR hora <= 6 THEN '1. Nocturna (22-6)'
           WHEN hora BETWEEN 7  AND 11  THEN '2. Mañana (7-11)'
           WHEN hora BETWEEN 12 AND 17  THEN '3. Tarde (12-17)'
           ELSE                              '4. Noche temprana (18-21)'
       END                                         AS franja,
       COUNT(*)                                    AS transacciones,
       SUM(es_fraude)                              AS fraudes,
       ROUND(100.0 * SUM(es_fraude) / COUNT(*), 2) AS tasa_fraude_pct
FROM fact_transacciones_2024
GROUP BY 1
ORDER BY 1;""",

    "4. ¿Qué pasa cuando se acumulan señales de riesgo? (2024)": """WITH banderas AS (
    SELECT f.es_fraude,
           ( (f.intentos_fallidos >= 2)
           + (f.es_internacional  = 1)
           + (f.pin_cambiado      = 1)
           + (f.es_nocturna       = 1)
           + (c.es_comercio_riesgoso = 1) ) AS n_banderas
    FROM fact_transacciones_2024 f
    JOIN dim_comercio c USING (comercio_id)
)
SELECT n_banderas,
       COUNT(*)                                    AS transacciones,
       SUM(es_fraude)                              AS fraudes,
       ROUND(100.0 * SUM(es_fraude) / COUNT(*), 2) AS tasa_fraude_pct
FROM banderas
GROUP BY n_banderas
ORDER BY n_banderas;""",

    "5. ¿El modelo ordena bien el riesgo? (deciles)": """SELECT decil_riesgo,
       COUNT(*)                                       AS transacciones,
       SUM(es_fraude)                                 AS fraudes,
       ROUND(100.0 * SUM(es_fraude) / COUNT(*), 2)    AS tasa_fraude_pct,
       ROUND(100.0 * AVG(risk_score), 2)              AS probabilidad_media_pct
FROM fact_transacciones_2024
GROUP BY decil_riesgo
ORDER BY decil_riesgo;""",

    "6. ¿Cuánto fraude se captura revisando menos? (curva de ganancia)": """WITH decil AS (
    SELECT decil_riesgo,
           COUNT(*)       AS txn,
           SUM(es_fraude) AS fraudes
    FROM fact_transacciones_2024
    GROUP BY decil_riesgo
)
SELECT decil_riesgo,
       ROUND(100.0 * SUM(txn)     OVER w / SUM(txn)     OVER (), 0)  AS pct_revisado,
       ROUND(100.0 * SUM(fraudes) OVER w / SUM(fraudes) OVER (), 1)  AS pct_fraudes_capturados
FROM decil
WINDOW w AS (ORDER BY decil_riesgo)
ORDER BY decil_riesgo;""",
}


def _conectar() -> sqlite3.Connection:
    """Abre la base en modo solo lectura: nadie puede modificar ni borrar datos."""
    return sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)


def validar(sql: str) -> str | None:
    """Devuelve un mensaje de error si la consulta no es de solo lectura; None si está bien."""
    limpia = sql.strip().rstrip(";").strip()
    if not limpia:
        return "Escribe una consulta."
    if ";" in limpia:
        return "Ejecuta una sola consulta a la vez."
    if limpia.split()[0].upper() not in ("SELECT", "WITH"):
        return "Solo se permiten consultas SELECT (o WITH ... SELECT)."
    return None


def ejecutar(sql: str) -> tuple[pd.DataFrame, float, bool]:
    """Ejecuta la consulta. Devuelve (resultado, segundos, ¿se recortó por MAX_FILAS?)."""
    con = _conectar()
    inicio = time.perf_counter()
    # Corta la consulta si tarda más de MAX_SEGUNDOS (por ejemplo, un JOIN sin condición)
    con.set_progress_handler(lambda: 1 if time.perf_counter() - inicio > MAX_SEGUNDOS else 0, 100_000)
    try:
        cur = con.execute(sql)
        columnas = [c[0] for c in cur.description]
        filas = cur.fetchmany(MAX_FILAS + 1)
    finally:
        con.close()
    recortado = len(filas) > MAX_FILAS
    df = pd.DataFrame(filas[:MAX_FILAS], columns=columnas)
    return df, time.perf_counter() - inicio, recortado


def esquema() -> dict[str, list[str]]:
    """Tablas y columnas de la base, para mostrarlas como ayuda."""
    con = _conectar()
    try:
        tablas = [t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {t: [f"{c[1]} ({c[2] or '—'})" for c in con.execute(f"PRAGMA table_info({t})")] for t in tablas}
    finally:
        con.close()
