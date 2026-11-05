/* =====================================================================
   05 · Job de SQL Server Agent: actualizar el resumen y revisar la calidad
   Qué hace, cada noche a las 02:00:
     1) Reconstruye la tabla resumen_decil_2024 (tabla de deciles del modelo).
     2) Guarda en control_calidad una fila con las revisiones de calidad de datos
        (filas, duplicados, montos no positivos, scores fuera de rango).
   Requisito: SQL Server Agent en ejecución (ícono verde en SSMS).
   Ejecuta el script completo (F5).
   ===================================================================== */
USE FraudeBancario;
GO

-- ---------- Tablas que llena el job ----------
DROP TABLE IF EXISTS dbo.resumen_decil_2024;
CREATE TABLE dbo.resumen_decil_2024 (
    decil_riesgo          TINYINT       NOT NULL PRIMARY KEY,
    transacciones         INT           NOT NULL,
    fraudes               INT           NOT NULL,
    tasa_fraude_pct       DECIMAL(6,2)  NOT NULL,
    probabilidad_media_pct DECIMAL(6,2) NOT NULL,
    actualizado_el        DATETIME2(0)  NOT NULL
);

IF OBJECT_ID(N'dbo.control_calidad') IS NULL
    CREATE TABLE dbo.control_calidad (
        id                   INT IDENTITY(1,1) PRIMARY KEY,
        ejecutado_el         DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
        filas                INT          NOT NULL,
        ids_unicos           INT          NOT NULL,
        monto_no_positivo    INT          NOT NULL,
        score_fuera_de_rango INT          NOT NULL,
        estado               VARCHAR(10)  NOT NULL      -- OK o REVISAR
    );
GO

-- ---------- Procedimiento que ejecuta el job ----------
CREATE OR ALTER PROCEDURE dbo.sp_actualizar_resumen_fraude
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRANSACTION;

    DELETE FROM dbo.resumen_decil_2024;
    INSERT INTO dbo.resumen_decil_2024
           (decil_riesgo, transacciones, fraudes, tasa_fraude_pct, probabilidad_media_pct, actualizado_el)
    SELECT decil_riesgo,
           COUNT(*),
           SUM(es_fraude),
           ROUND(100.0 * SUM(es_fraude) / COUNT(*), 2),
           ROUND(100.0 * AVG(risk_score), 2),
           SYSDATETIME()
    FROM dbo.fact_transacciones_2024
    GROUP BY decil_riesgo;

    INSERT INTO dbo.control_calidad (filas, ids_unicos, monto_no_positivo, score_fuera_de_rango, estado)
    SELECT COUNT(*),
           COUNT(DISTINCT transaction_id),
           SUM(CASE WHEN monto <= 0 THEN 1 ELSE 0 END),
           SUM(CASE WHEN credit_score NOT BETWEEN 300 AND 850 THEN 1 ELSE 0 END),
           CASE WHEN COUNT(*) = COUNT(DISTINCT transaction_id)
                 AND SUM(CASE WHEN monto <= 0 THEN 1 ELSE 0 END) = 0
                 AND SUM(CASE WHEN credit_score NOT BETWEEN 300 AND 850 THEN 1 ELSE 0 END) = 0
                THEN 'OK' ELSE 'REVISAR' END
    FROM dbo.fact_transacciones_2024;

    COMMIT TRANSACTION;
END
GO

-- ---------- Crear el job ----------
USE msdb;
GO

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = N'Job_Actualizar_Resumen_Fraude')
    EXEC msdb.dbo.sp_delete_job @job_name = N'Job_Actualizar_Resumen_Fraude';

EXEC msdb.dbo.sp_add_job
     @job_name    = N'Job_Actualizar_Resumen_Fraude',
     @enabled     = 1,
     @description = N'Reconstruye el resumen por decil y registra controles de calidad de datos.';

EXEC msdb.dbo.sp_add_jobstep
     @job_name      = N'Job_Actualizar_Resumen_Fraude',
     @step_name     = N'Ejecutar sp_actualizar_resumen_fraude',
     @subsystem     = N'TSQL',
     @database_name = N'FraudeBancario',
     @command       = N'EXEC dbo.sp_actualizar_resumen_fraude;';

EXEC msdb.dbo.sp_add_jobschedule
     @job_name          = N'Job_Actualizar_Resumen_Fraude',
     @name              = N'Diario 02:00',
     @freq_type         = 4,        -- diario
     @freq_interval     = 1,        -- cada 1 día
     @active_start_time = 20000;    -- 02:00:00

EXEC msdb.dbo.sp_add_jobserver
     @job_name    = N'Job_Actualizar_Resumen_Fraude',
     @server_name = N'(local)';
GO

PRINT 'Job creado: Job_Actualizar_Resumen_Fraude (diario, 02:00).';
GO

/* ---------- Probarlo ahora mismo (sin esperar a las 02:00) ---------- */
EXEC msdb.dbo.sp_start_job @job_name = N'Job_Actualizar_Resumen_Fraude';
WAITFOR DELAY '00:00:05';
GO

-- ¿Se ejecutó bien? (run_status 1 = correcto)
SELECT j.name                                                   AS job,
       msdb.dbo.agent_datetime(h.run_date, h.run_time)          AS ejecutado_el,
       CASE h.run_status WHEN 1 THEN 'Correcto' WHEN 0 THEN 'Falló' ELSE 'Otro' END AS resultado,
       h.message
FROM msdb.dbo.sysjobhistory h
JOIN msdb.dbo.sysjobs j ON j.job_id = h.job_id
WHERE j.name = N'Job_Actualizar_Resumen_Fraude' AND h.step_id = 0
ORDER BY ejecutado_el DESC;

-- ¿Qué dejó el job en las tablas?
SELECT * FROM FraudeBancario.dbo.control_calidad ORDER BY id DESC;
SELECT * FROM FraudeBancario.dbo.resumen_decil_2024 ORDER BY decil_riesgo;
GO
