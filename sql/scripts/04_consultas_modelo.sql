/* =====================================================================
   04 · Evaluación del modelo con SQL Server: de la probabilidad a la decisión
   El puntaje (risk_score) viene del modelo LightGBM entrenado con 2020-2023
   y aplicado a 2024, año que no vio. Ejecuta una consulta a la vez (F5).
   ===================================================================== */
USE FraudeBancario;
GO

-- M1. Tabla de deciles: ¿el modelo ordena bien el riesgo?
--     Decil 1 = el 10 % de transacciones que el modelo considera más riesgosas.
SELECT decil_riesgo,
       COUNT(*)                                       AS transacciones,
       SUM(es_fraude)                                 AS fraudes,
       ROUND(100.0 * SUM(es_fraude) / COUNT(*), 2)    AS tasa_fraude_pct,
       ROUND(100.0 * AVG(risk_score), 2)              AS probabilidad_media_pct
FROM dbo.fact_transacciones_2024
GROUP BY decil_riesgo
ORDER BY decil_riesgo;
-- Lectura: si las dos últimas columnas se parecen, el modelo está bien calibrado.

-- M2. Curva de ganancia: % de fraudes capturados al revisar los primeros K deciles.
WITH decil AS (
    SELECT decil_riesgo,
           COUNT(*)       AS txn,
           SUM(es_fraude) AS fraudes
    FROM dbo.fact_transacciones_2024
    GROUP BY decil_riesgo
)
SELECT decil_riesgo,
       SUM(txn)     OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING)  AS txn_revisadas,
       SUM(fraudes) OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING)  AS fraudes_capturados,
       ROUND(100.0 * SUM(txn)     OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING)
                   / SUM(txn)     OVER (), 0)                              AS pct_revisado,
       ROUND(100.0 * SUM(fraudes) OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING)
                   / SUM(fraudes) OVER (), 1)                              AS pct_fraudes_capturados,
       ROUND((1.0 * SUM(fraudes) OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING) / SUM(fraudes) OVER ())
           / (1.0 * SUM(txn)     OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING) / SUM(txn)     OVER ()), 2) AS lift_acumulado
FROM decil
ORDER BY decil_riesgo;

-- M3. Simulador económico: ¿cuánto vale revisar el K % de mayor riesgo?
--     Supuesto: cada revisión cuesta 25 USD y revisar un fraude lo evita
--     (se recupera su monto). Cambia @costo por tu supuesto.
DECLARE @costo DECIMAL(10,2) = 25;
WITH decil AS (
    SELECT decil_riesgo,
           COUNT(*)                                      AS txn,
           SUM(CASE WHEN es_fraude = 1 THEN monto END)   AS monto_fraude
    FROM dbo.fact_transacciones_2024
    GROUP BY decil_riesgo
),
acum AS (
    SELECT decil_riesgo,
           SUM(txn)          OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING) AS txn_rev,
           SUM(monto_fraude) OVER (ORDER BY decil_riesgo ROWS UNBOUNDED PRECEDING) AS fraude_evitado
    FROM decil
)
SELECT decil_riesgo * 10                         AS pct_revisado,
       ROUND(fraude_evitado, 0)                  AS fraude_evitado,
       txn_rev * @costo                          AS costo_revision,
       ROUND(fraude_evitado - txn_rev * @costo, 0) AS valor_neto
FROM acum
ORDER BY decil_riesgo;

-- M4. ¿Dónde se equivoca el modelo? Fraudes que se le escaparon (falsos negativos)
--     al revisar solo el 10 % de mayor riesgo, por comercio.
SELECT c.comercio,
       SUM(f.es_fraude)                                           AS fraudes,
       SUM(CASE WHEN f.es_fraude = 1 AND f.revisar_top10 = 0 THEN 1 ELSE 0 END) AS fraudes_no_detectados,
       ROUND(100.0 * SUM(CASE WHEN f.es_fraude = 1 AND f.revisar_top10 = 0 THEN 1 ELSE 0 END)
             / SUM(f.es_fraude), 1)                               AS pct_no_detectado
FROM dbo.fact_transacciones_2024 f
JOIN dbo.dim_comercio c ON c.comercio_id = f.comercio_id
GROUP BY c.comercio
ORDER BY pct_no_detectado DESC;

-- M5. Las 10 transacciones con mayor puntaje de riesgo (lo que vería un analista).
SELECT TOP (10)
       transaction_id,
       monto,
       ROUND(risk_score, 3) AS risk_score,
       es_fraude
FROM dbo.fact_transacciones_2024
ORDER BY risk_score DESC;
