/* =====================================================================
   03 · Análisis exploratorio (EDA) con SQL Server: ¿dónde está el fraude?
   Cada consulta responde una pregunta de negocio. Selecciona UNA consulta
   (de su comentario hasta su punto y coma) y pulsa F5 para ejecutarla.
   ===================================================================== */
USE FraudeBancario;
GO

-- Q1. ¿Cuántas transacciones hay y qué tan frecuente es el fraude por año?
SELECT anio,
       SUM(transacciones)                                  AS transacciones,
       SUM(fraudes)                                        AS fraudes,
       ROUND(100.0 * SUM(fraudes) / SUM(transacciones), 2) AS tasa_fraude_pct,
       ROUND(SUM(monto_fraude), 0)                         AS monto_fraude
FROM dbo.agg_mensual_comercio
GROUP BY anio
ORDER BY anio;

-- Q2. ¿Qué comercios tienen más fraude? Ranking y comparación con el promedio (lift).
WITH por_comercio AS (
    SELECT comercio,
           SUM(transacciones) AS txn,
           SUM(fraudes)       AS fraudes,
           1.0 * SUM(fraudes) / SUM(transacciones) AS tasa
    FROM dbo.agg_mensual_comercio
    GROUP BY comercio
),
promedio AS (
    SELECT 1.0 * SUM(fraudes) / SUM(transacciones) AS tasa_global
    FROM dbo.agg_mensual_comercio
)
SELECT RANK() OVER (ORDER BY c.tasa DESC)   AS ranking,
       c.comercio,
       c.txn,
       c.fraudes,
       ROUND(100 * c.tasa, 2)               AS tasa_fraude_pct,
       ROUND(c.tasa / g.tasa_global, 2)     AS lift_vs_promedio
FROM por_comercio c CROSS JOIN promedio g
ORDER BY ranking;

-- Q3. Evolución mensual con media móvil de 3 meses y variación contra el mes anterior.
WITH mensual AS (
    SELECT anio_mes,
           SUM(transacciones) AS txn,
           SUM(fraudes)       AS fraudes,
           100.0 * SUM(fraudes) / SUM(transacciones) AS tasa_pct
    FROM dbo.agg_mensual_comercio
    GROUP BY anio_mes
)
SELECT TOP (24)
       anio_mes,
       txn,
       fraudes,
       ROUND(tasa_pct, 2)                                                     AS tasa_pct,
       ROUND(AVG(tasa_pct) OVER (ORDER BY anio_mes
                                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS media_movil_3m,
       ROUND(tasa_pct - LAG(tasa_pct) OVER (ORDER BY anio_mes), 2)            AS cambio_vs_mes_anterior
FROM mensual
ORDER BY anio_mes;

-- Q4. ¿A qué hora ocurre el fraude? Tasa por franja del día (2024).
--     La franja nocturna es la del propio dataset: de 22:00 a 06:59.
SELECT x.franja,
       COUNT(*)                                    AS transacciones,
       SUM(f.es_fraude)                            AS fraudes,
       ROUND(100.0 * SUM(f.es_fraude) / COUNT(*), 2) AS tasa_fraude_pct
FROM dbo.fact_transacciones_2024 f
CROSS APPLY (SELECT CASE
                 WHEN f.hora >= 22 OR f.hora <= 6 THEN '1. Nocturna (22-6)'
                 WHEN f.hora BETWEEN 7  AND 11    THEN '2. Mañana (7-11)'
                 WHEN f.hora BETWEEN 12 AND 17    THEN '3. Tarde (12-17)'
                 ELSE                                  '4. Noche temprana (18-21)'
             END AS franja) AS x
GROUP BY x.franja
ORDER BY x.franja;

-- Q5. Banderas de riesgo: ¿qué pasa cuando se acumulan? (2024)
--     Una "bandera" es una señal sospechosa. Son las mismas cinco del notebook:
--     2+ intentos fallidos, internacional, nocturna, comercio de riesgo y PIN cambiado.
WITH banderas AS (
    SELECT f.es_fraude,
           ( CASE WHEN f.intentos_fallidos >= 2 THEN 1 ELSE 0 END
           + f.es_internacional
           + f.pin_cambiado
           + f.es_nocturna
           + c.es_comercio_riesgoso ) AS n_banderas
    FROM dbo.fact_transacciones_2024 f
    JOIN dbo.dim_comercio c ON c.comercio_id = f.comercio_id
)
SELECT n_banderas,
       COUNT(*)                                      AS transacciones,
       SUM(es_fraude)                                AS fraudes,
       ROUND(100.0 * SUM(es_fraude) / COUNT(*), 2)   AS tasa_fraude_pct
FROM banderas
GROUP BY n_banderas
ORDER BY n_banderas;

-- Q6. Fraude por comercio, método de pago y dispositivo en una sola vista (JOIN a las dimensiones).
SELECT TOP (10)
       c.comercio, p.metodo_pago, d.dispositivo,
       COUNT(*)                                      AS transacciones,
       SUM(f.es_fraude)                              AS fraudes,
       ROUND(100.0 * SUM(f.es_fraude) / COUNT(*), 2) AS tasa_fraude_pct
FROM dbo.fact_transacciones_2024 f
JOIN dbo.dim_comercio    c ON c.comercio_id    = f.comercio_id
JOIN dbo.dim_metodo_pago p ON p.pago_id        = f.pago_id
JOIN dbo.dim_dispositivo d ON d.dispositivo_id = f.dispositivo_id
GROUP BY c.comercio, p.metodo_pago, d.dispositivo
HAVING COUNT(*) >= 300              -- evita conclusiones con muestras pequeñas
ORDER BY tasa_fraude_pct DESC;

-- Q7. Revisión de calidad de datos: nulos, duplicados y rangos raros.
SELECT COUNT(*)                                                       AS filas,
       COUNT(DISTINCT transaction_id)                                 AS ids_unicos,
       SUM(CASE WHEN monto IS NULL THEN 1 ELSE 0 END)                 AS monto_nulo,
       SUM(CASE WHEN monto <= 0 THEN 1 ELSE 0 END)                    AS monto_no_positivo,
       SUM(CASE WHEN credit_score NOT BETWEEN 300 AND 850 THEN 1 ELSE 0 END) AS score_fuera_de_rango,
       MIN(fecha_key) AS fecha_min, MAX(fecha_key)                    AS fecha_max
FROM dbo.fact_transacciones_2024;
