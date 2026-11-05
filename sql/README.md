# SQL Server · Detección de fraude bancario

Esta carpeta es la parte de base de datos del Proyecto 1. Lo que hice aquí: armar un modelo en estrella en SQL Server, cargarlo con `BULK INSERT`, escribir consultas de análisis en T-SQL y dejar un **job de SQL Server Agent** que se ejecuta solo cada noche.

Los datos son sintéticos (Kaggle): 1 millón de transacciones 2020-2024 con ~5,5 % de fraude. Aquí cargo la parte de **2024** (199 325 transacciones), que es la que el modelo no vio al entrenar.

## Cómo reproducirlo

1. Instalar SQL Server (edición Developer) y SSMS. Conectarse a `localhost` con autenticación de Windows.
2. Los 7 CSV que cargan los scripts se generan a partir de los datos del proyecto y no se suben al repo por su tamaño. Para reproducirlo, genera esos CSV y ajusta la variable `@ruta` del script 02 para que apunte a la carpeta donde los dejaste. Si SQL Server da «acceso denegado» al leer, abrir CMD como administrador y ejecutar: `icacls "<tu_ruta>" /grant "NT Service\MSSQLSERVER:(OI)(CI)R"`.
3. Ejecutar en SSMS, en este orden (F5):

| Script | Qué hace |
|---|---|
| `01_crear_base_y_tablas.sql` | Crea la base `FraudeBancario`, las 5 dimensiones, la tabla de hechos, la agregada mensual, claves e índices |
| `02_cargar_datos.sql` | Carga los CSV con `BULK INSERT` y muestra una tabla de verificación |
| `03_consultas_analisis.sql` | Siete preguntas de negocio sobre el fraude (Q1-Q7) |
| `04_consultas_modelo.sql` | Cinco consultas para evaluar el modelo (M1-M5) |
| `05_job_actualizar_resumen.sql` | Crea el job nocturno y lo prueba en el momento |

Conteos esperados después del paso 2: `dim_fecha` 1 827 · `dim_comercio` 15 · `dim_pais` 10 · `dim_metodo_pago` 6 · `dim_dispositivo` 5 · `agg_mensual_comercio` 900 · `fact_transacciones_2024` 199 325.

## Modelo

Estrella con `fact_transacciones_2024` al centro y cinco dimensiones: fecha, comercio, país, método de pago y dispositivo. La tabla `agg_mensual_comercio` guarda el total mensual por comercio.

## Qué se puede ver en los resultados

- **Fraude por franja horaria (Q4):** la franja nocturna tiene una tasa de fraude de 7,91 %, casi el doble que las otras tres (alrededor de 4 %).
- **Fraude por decil de riesgo:** el decil 1 (el de mayor riesgo) tiene 14,98 % de fraude; el decil 2, 10,32 %. El modelo ordena bien las transacciones.
- **Costo de revisión (M3):** la consulta usa `DECLARE @costo` para probar distintos costos por revisión sin tocar el resto del código.

## El job

`Job_Actualizar_Resumen_Fraude` corre todos los días a las 02:00 y ejecuta el procedimiento `sp_actualizar_resumen_fraude`, que:

1. Reconstruye `resumen_decil_2024` (transacciones, fraudes y tasa por decil).
2. Agrega una fila a `control_calidad` con cuatro revisiones: filas totales, IDs únicos, montos no positivos y credit scores fuera del rango 300-850. Si todo está bien marca `OK`; si no, `REVISAR`.

Requiere que **SQL Server Agent** esté en ejecución.

## Diferencias con SQLite

La versión de la app web (pestaña «Consultas SQL» en Streamlit) corre sobre SQLite. Al pasar a T-SQL hubo que cambiar `LIMIT` por `TOP`, quitar el `GROUP BY 1`, reemplazar `USING` por `ON` y usar `CASE` donde SQLite acepta expresiones booleanas directas.
