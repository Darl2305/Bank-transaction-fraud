/* =====================================================================
   01 · Crear la base de datos y las tablas (esquema en estrella)
   Motor: SQL Server (T-SQL). Ejecutar completo en SSMS (F5).

   Tablas:
     fact_transacciones_2024  199 325 filas: todas las transacciones de 2024,
                              con el puntaje de riesgo del modelo LightGBM
                              (año que el modelo no vio al entrenar)
     agg_mensual_comercio     900 filas: resumen mes x comercio de 2020-2024
     dim_*                    tablas de apoyo (fecha, comercio, país, pago, dispositivo)
   Las marcas (es_fraude, es_nocturna...) son TINYINT 0/1 para poder sumarlas.
   ===================================================================== */

IF DB_ID(N'FraudeBancario') IS NULL
    CREATE DATABASE FraudeBancario;
GO

USE FraudeBancario;
GO

-- Si vuelves a correr el script, empieza limpio
DROP TABLE IF EXISTS dbo.fact_transacciones_2024;
DROP TABLE IF EXISTS dbo.agg_mensual_comercio;
DROP TABLE IF EXISTS dbo.dim_fecha;
DROP TABLE IF EXISTS dbo.dim_comercio;
DROP TABLE IF EXISTS dbo.dim_pais;
DROP TABLE IF EXISTS dbo.dim_metodo_pago;
DROP TABLE IF EXISTS dbo.dim_dispositivo;
GO

-- ---------- Dimensiones ----------
CREATE TABLE dbo.dim_fecha (
    fecha_key        INT          NOT NULL PRIMARY KEY,   -- 20240131
    fecha            DATE         NOT NULL,
    anio             SMALLINT     NOT NULL,
    trimestre        TINYINT      NOT NULL,
    mes_num          TINYINT      NOT NULL,
    mes              NVARCHAR(15) NOT NULL,
    anio_mes         CHAR(7)      NOT NULL,                -- 2024-01
    dia_semana       NVARCHAR(15) NOT NULL,
    es_fin_de_semana TINYINT      NOT NULL
);

CREATE TABLE dbo.dim_comercio (
    comercio_id          INT         NOT NULL PRIMARY KEY,
    comercio             VARCHAR(40) NOT NULL UNIQUE,
    es_comercio_riesgoso TINYINT     NOT NULL              -- Crypto, Joyería y Cajero
);

CREATE TABLE dbo.dim_pais (
    pais_id INT         NOT NULL PRIMARY KEY,
    pais    VARCHAR(40) NOT NULL
);

CREATE TABLE dbo.dim_metodo_pago (
    pago_id     INT         NOT NULL PRIMARY KEY,
    metodo_pago VARCHAR(40) NOT NULL
);

CREATE TABLE dbo.dim_dispositivo (
    dispositivo_id INT         NOT NULL PRIMARY KEY,
    dispositivo    VARCHAR(40) NOT NULL
);

-- ---------- Tabla de hechos ----------
CREATE TABLE dbo.fact_transacciones_2024 (
    transaction_id          VARCHAR(20)   NOT NULL PRIMARY KEY,
    customer_id             VARCHAR(20)   NOT NULL,
    fecha_key               INT           NOT NULL REFERENCES dbo.dim_fecha(fecha_key),
    hora                    TINYINT       NOT NULL,
    comercio_id             INT           NOT NULL REFERENCES dbo.dim_comercio(comercio_id),
    pais_id                 INT           NOT NULL REFERENCES dbo.dim_pais(pais_id),
    pago_id                 INT           NOT NULL REFERENCES dbo.dim_metodo_pago(pago_id),
    dispositivo_id          INT           NOT NULL REFERENCES dbo.dim_dispositivo(dispositivo_id),
    es_nocturna             TINYINT       NOT NULL,
    edad_cliente            TINYINT       NOT NULL,
    credit_score            SMALLINT      NOT NULL,
    antiguedad_cuenta_anios DECIMAL(5,1)  NOT NULL,
    saldo_cuenta            DECIMAL(14,2) NOT NULL,
    monto                   DECIMAL(12,2) NOT NULL,
    txn_previas             INT           NOT NULL,
    frecuencia_mensual      INT           NOT NULL,
    distancia_casa_km       DECIMAL(10,1) NOT NULL,
    horas_desde_ultima_txn  DECIMAL(10,2) NOT NULL,
    es_internacional        TINYINT       NOT NULL,
    intentos_fallidos       TINYINT       NOT NULL,
    pin_cambiado            TINYINT       NOT NULL,
    es_fraude               TINYINT       NOT NULL,        -- 1 = fraude confirmado
    tipo_fraude             VARCHAR(20)   NOT NULL,        -- solo se conoce cuando hubo fraude: NO se usa para predecir
    risk_score              DECIMAL(9,6)  NOT NULL,        -- probabilidad de fraude según el modelo (LightGBM)
    decil_riesgo            TINYINT       NOT NULL,        -- 1 = 10 % de transacciones con mayor riesgo
    revisar_top10           TINYINT       NOT NULL         -- 1 = cae en el 10 % que se revisaría
);

CREATE INDEX ix_fact_decil   ON dbo.fact_transacciones_2024 (decil_riesgo) INCLUDE (es_fraude, monto, risk_score);
CREATE INDEX ix_fact_comercio ON dbo.fact_transacciones_2024 (comercio_id) INCLUDE (es_fraude);

-- ---------- Tabla agregada (2020-2024) ----------
CREATE TABLE dbo.agg_mensual_comercio (
    anio_mes      CHAR(7)       NOT NULL,
    comercio      VARCHAR(40)   NOT NULL REFERENCES dbo.dim_comercio(comercio),
    transacciones INT           NOT NULL,
    fraudes       INT           NOT NULL,
    monto_total   DECIMAL(14,2) NOT NULL,
    monto_fraude  DECIMAL(14,2) NOT NULL,
    anio          SMALLINT      NOT NULL,
    fecha_mes     DATE          NOT NULL,
    CONSTRAINT pk_agg PRIMARY KEY (anio_mes, comercio)
);
GO

PRINT 'Base FraudeBancario y tablas creadas.';
GO
