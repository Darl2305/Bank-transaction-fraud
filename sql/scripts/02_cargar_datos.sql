/* =====================================================================
   02 · Cargar los 7 CSV con BULK INSERT
   ANTES de ejecutar:
     1) Los 7 archivos .csv están en  D:\Portafolio\sql-server\datos\
        (si moviste la carpeta a otro lado, cambia @ruta aquí abajo).
     2) El servicio de SQL Server tiene que poder LEER esa carpeta.
        Si te sale "Access is denied / Acceso denegado", dale permiso con
        el paso indicado en el README (icacls) y vuelve a ejecutar.
   ===================================================================== */
USE FraudeBancario;
GO

SET NOCOUNT ON;
DECLARE @ruta NVARCHAR(260) = N'D:\Portafolio\sql-server\datos\';   -- termina con barra invertida
DECLARE @sql  NVARCHAR(MAX);

-- Limpia en orden inverso a las llaves foráneas (por si repites la carga)
DELETE FROM dbo.fact_transacciones_2024;
DELETE FROM dbo.agg_mensual_comercio;
DELETE FROM dbo.dim_fecha;
DELETE FROM dbo.dim_comercio;
DELETE FROM dbo.dim_pais;
DELETE FROM dbo.dim_metodo_pago;
DELETE FROM dbo.dim_dispositivo;

-- Cada archivo: primero las dimensiones, al final la tabla de hechos
DECLARE @cargas TABLE (orden INT, tabla SYSNAME, archivo NVARCHAR(100));
INSERT INTO @cargas VALUES
    (1, N'dim_fecha',               N'dim_fecha.csv'),
    (2, N'dim_comercio',            N'dim_comercio.csv'),
    (3, N'dim_pais',                N'dim_pais.csv'),
    (4, N'dim_metodo_pago',         N'dim_metodo_pago.csv'),
    (5, N'dim_dispositivo',         N'dim_dispositivo.csv'),
    (6, N'agg_mensual_comercio',    N'agg_mensual_comercio.csv'),
    (7, N'fact_transacciones_2024', N'fact_transacciones_2024.csv');

DECLARE @tabla SYSNAME, @archivo NVARCHAR(100);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT tabla, archivo FROM @cargas ORDER BY orden;
OPEN c;
FETCH NEXT FROM c INTO @tabla, @archivo;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @sql = N'BULK INSERT dbo.' + QUOTENAME(@tabla) + N'
                 FROM ''' + @ruta + @archivo + N'''
                 WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDTERMINATOR = '','',
                       CODEPAGE = ''65001'', CHECK_CONSTRAINTS, TABLOCK);';
    EXEC sys.sp_executesql @sql;
    PRINT 'Cargada: ' + @tabla;
    FETCH NEXT FROM c INTO @tabla, @archivo;
END
CLOSE c; DEALLOCATE c;
GO

-- ---------- Verificación: ¿llegaron todas las filas? ----------
SELECT 'dim_fecha' AS tabla, COUNT(*) AS filas, 1827 AS esperado FROM dbo.dim_fecha
UNION ALL SELECT 'dim_comercio',            COUNT(*), 15     FROM dbo.dim_comercio
UNION ALL SELECT 'dim_pais',                COUNT(*), 10     FROM dbo.dim_pais
UNION ALL SELECT 'dim_metodo_pago',         COUNT(*), 6      FROM dbo.dim_metodo_pago
UNION ALL SELECT 'dim_dispositivo',         COUNT(*), 5      FROM dbo.dim_dispositivo
UNION ALL SELECT 'agg_mensual_comercio',    COUNT(*), 900    FROM dbo.agg_mensual_comercio
UNION ALL SELECT 'fact_transacciones_2024', COUNT(*), 199325 FROM dbo.fact_transacciones_2024;
GO
