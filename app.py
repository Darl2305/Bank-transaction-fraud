"""
App de Streamlit: detección de fraude en transacciones bancarias.

Qué hace
--------
1. Puntúa UNA transacción y explica por qué el modelo la considera riesgosa.
2. Puntúa un LOTE (CSV): sirve tanto para el histórico (si trae la columna
   `is_fraud` se mide el desempeño real) como para transacciones nuevas.
3. Muestra cómo rinde el modelo y permite simular el impacto económico.

El modelo se entrena en el notebook (notebooks/01_fraud_detection_crisp_dm.ipynb);
aquí solo se carga el archivo ya entrenado, por eso la app arranca en segundos.
"""
from __future__ import annotations

import json
from pathlib import Path

import altair as alt
import lightgbm as lgb
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics import average_precision_score, roc_auc_score

from src.features import (FEATURE_LABELS, FEATURES, MERCHANT_CATEGORIES, REQUIRED_COLUMNS,
                          RISKY_MERCHANTS, build_features, missing_columns)

ROOT = Path(__file__).parent
GITHUB_URL = "https://github.com/Darl2305/Bank-transaction-fraud"
MAX_FILAS = 500_000

# Paleta (la misma del notebook): azul = acento, naranja = señal de riesgo, gris = neutro.
AZUL, NARANJA, GRIS = "#2a78d6", "#eb6834", "#b9b8b1"

st.set_page_config(page_title="Detección de fraude bancario", page_icon="🛡️", layout="wide")


# --------------------------------------------------------------------------
# Carga de modelo y utilidades
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def cargar_modelo():
    booster = lgb.Booster(model_file=str(ROOT / "models" / "fraud_lgbm.txt"))
    meta = json.loads((ROOT / "models" / "metadata.json").read_text(encoding="utf-8"))
    return booster, meta


@st.cache_data(show_spinner=False)
def leer_muestra(nombre: str) -> pd.DataFrame:
    return pd.read_csv(ROOT / "data" / nombre)


booster, META = cargar_modelo()
OP = pd.DataFrame(META["puntos_operacion"]).set_index("k_pct")   # umbral, precisión, recall, lift por K
BASE = META["tasa_base_prueba"]


def puntuar(df: pd.DataFrame) -> np.ndarray:
    """Probabilidad de fraude para cada fila."""
    return booster.predict(build_features(df))


def contribuciones(df: pd.DataFrame) -> pd.DataFrame:
    """Aporte de cada variable a la predicción (valores tipo SHAP, escala log-odds)."""
    c = booster.predict(build_features(df), pred_contrib=True)
    return pd.DataFrame(c[:, :-1], columns=FEATURES, index=df.index)


def umbral_para(k_pct: int) -> float:
    return float(OP.loc[k_pct, "umbral"])


def percentil_riesgo(p: float) -> int:
    """'Top k %' de riesgo en que cae una probabilidad, según la distribución de 2024."""
    ok = OP.index[OP["umbral"] <= p]
    return int(ok.min()) if len(ok) else 100


def nivel_riesgo(p) -> np.ndarray:
    """Alto = top 5 %, Medio = top 5-20 %, Bajo = resto (umbrales calibrados en 2024)."""
    p = np.asarray(p)
    return np.where(p >= umbral_para(5), "Alto", np.where(p >= umbral_para(20), "Medio", "Bajo"))


# --------------------------------------------------------------------------
# Barra lateral: punto de operación
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Punto de operación")
    K = st.slider("Transacciones a revisar (% de mayor riesgo)", 1, 50, int(META["k_recomendado_pct"]),
                  help="Capacidad del equipo de analistas. Define a partir de qué probabilidad se genera una alerta.")
    umbral = umbral_para(K)
    st.metric("Se alerta desde una probabilidad de", f"{umbral:.1%}")
    st.metric("Fraudes capturados", f"{OP.loc[K, 'recall']:.0%}", help="Del total de fraudes, qué porcentaje queda dentro de las alertas.")
    st.metric("Aciertos por alerta", f"{OP.loc[K, 'precision']:.0%}", help="De cada 100 alertas, cuántas son fraude real.")
    st.caption(f"Medido en 2024 (datos que el modelo no vio). Sin modelo, revisar el {K} % al azar capturaría "
               f"solo el {K} % de los fraudes. Tasa base de fraude: {BASE:.1%}.")
    st.divider()
    st.caption("Proyecto de portafolio con datos **sintéticos**. No usar para decisiones reales.")
    st.link_button("Ver código en GitHub", GITHUB_URL)

st.title("🛡️ Detección de fraude en transacciones bancarias")
st.write("Modelo de machine learning entrenado con 800 000 transacciones (2020-2023) y evaluado en 2024. "
         "Estima la **probabilidad de fraude** de una transacción, ya sea una del histórico o una nueva que llega hoy.")

tab1, tab2, tab3, tab4 = st.tabs(["Evaluar una transacción", "Evaluar un lote (CSV)", "Rendimiento del modelo", "Sobre el proyecto"])

# --------------------------------------------------------------------------
# Pestaña 1: una transacción
# --------------------------------------------------------------------------
PRESETS = {
    "legitima": dict(mcc="Grocery", monto=45.0, saldo=6200.0, hora=14, fallidos=0, intl=False, pin=False, score=720, horas=9.5),
    "sospechosa": dict(mcc="Crypto Exchange", monto=950.0, saldo=1800.0, hora=2, fallidos=3, intl=True, pin=True, score=560, horas=0.4),
}
for k, v in PRESETS["legitima"].items():
    st.session_state.setdefault(f"in_{k}", v)


def aplicar_preset(nombre: str):
    for k, v in PRESETS[nombre].items():
        st.session_state[f"in_{k}"] = v


with tab1:
    st.subheader("Puntúa una transacción")
    b1, b2, _ = st.columns([1, 1, 4])
    b1.button("Ejemplo normal", on_click=aplicar_preset, args=("legitima",), width="stretch")
    b2.button("Ejemplo sospechoso", on_click=aplicar_preset, args=("sospechosa",), width="stretch")

    col_in, col_out = st.columns([1, 1.15], gap="large")
    with col_in:
        a, b = st.columns(2)
        mcc = a.selectbox("Tipo de comercio", MERCHANT_CATEGORIES, key="in_mcc")
        monto = b.number_input("Monto (USD)", min_value=1.0, max_value=100000.0, step=10.0, key="in_monto")
        saldo = a.number_input("Saldo de la cuenta (USD)", min_value=100.0, max_value=1_000_000.0, step=100.0, key="in_saldo")
        hora = b.slider("Hora de la transacción", 0, 23, key="in_hora")
        fallidos = a.slider("Intentos fallidos previos", 0, 5, key="in_fallidos")
        score = b.slider("Credit score", 300, 850, key="in_score")
        horas = a.number_input("Horas desde la última transacción", min_value=0.0, max_value=200.0, step=0.5, key="in_horas")
        intl = a.checkbox("Transacción internacional", key="in_intl")
        pin = b.checkbox("PIN cambiado recientemente", key="in_pin")

    fila = pd.DataFrame([dict(merchant_category=mcc, transaction_amount=monto, account_balance=saldo, hour_of_day=hora,
                              failed_attempts=fallidos, credit_score=score, time_since_last_txn_hrs=horas,
                              is_international=int(intl), pin_changed_recently=int(pin))])
    p = float(puntuar(fila)[0])
    nivel = str(nivel_riesgo([p])[0])
    contrib = contribuciones(fila).iloc[0]

    with col_out:
        icono = {"Alto": "🔴", "Medio": "🟠", "Bajo": "🟢"}[nivel]
        m1, m2, m3 = st.columns(3)
        m1.metric("Probabilidad de fraude", f"{p:.1%}")
        m2.metric("Nivel de riesgo", f"{icono} {nivel}")
        m3.metric("Riesgo relativo", f"{p / BASE:.1f}x", help=f"Cuántas veces la probabilidad de una transacción típica (tasa base de fraude: {BASE:.1%}).")
        st.progress(min(p, 1.0))
        top = percentil_riesgo(p)
        if p >= umbral:
            st.error(f"**Genera alerta** con tu punto de operación actual (revisar el {K} % de mayor riesgo). "
                     f"Esta transacción cae dentro del {top} % de mayor riesgo de 2024.")
        else:
            st.success(f"**No genera alerta** con tu punto de operación actual (revisar el {K} % de mayor riesgo). "
                       f"Está en el {top} % de mayor riesgo de 2024.")

        valores = {
            "merchant_category": mcc, "hour_of_day": f"{hora:02d}:00", "is_night": "Sí" if fila.iloc[0].hour_of_day in (22, 23, 0, 1, 2, 3, 4, 5, 6) else "No",
            "failed_attempts": str(fallidos), "is_international": "Sí" if intl else "No", "pin_changed_recently": "Sí" if pin else "No",
            "log_amount": f"${monto:,.0f}", "amount_to_balance": f"{monto / saldo:.1%} del saldo", "log_account_balance": f"${saldo:,.0f}",
            "credit_score": str(score), "time_since_last_txn_hrs": f"{horas:g} h",
        }
        d = pd.DataFrame({"variable": [f"{FEATURE_LABELS[f]}: {valores[f]}" for f in FEATURES], "aporte": contrib.values})
        d["efecto"] = np.where(d.aporte > 0, "Aumenta el riesgo", "Reduce el riesgo")
        d = d.reindex(d.aporte.abs().sort_values(ascending=False).index).head(6)
        st.markdown("**¿Por qué?** Las 6 variables que más pesan en esta predicción")
        graf = alt.Chart(d).mark_bar(cornerRadiusEnd=3, size=18).encode(
            x=alt.X("aporte:Q", title="Aporte a la probabilidad (log-odds)", axis=alt.Axis(grid=True, gridColor="#e8e7e2")),
            y=alt.Y("variable:N", sort=alt.EncodingSortField("aporte", op="max", order="descending"), title=None,
                    axis=alt.Axis(labelLimit=340, labelOverlap=False, labelFontSize=12)),
            color=alt.Color("efecto:N", scale=alt.Scale(domain=["Aumenta el riesgo", "Reduce el riesgo"], range=[NARANJA, AZUL]),
                            legend=alt.Legend(orient="top", title=None)),
            tooltip=["variable", alt.Tooltip("aporte:Q", format="+.2f"), "efecto"],
        ).properties(height=42 * len(d))
        st.altair_chart(graf, width="stretch")
        with st.expander("¿Cómo leer este gráfico?"):
            st.write("Cada barra dice cuánto empuja esa característica la predicción hacia **más fraude** (naranja, a la derecha) "
                     "o **menos fraude** (azul, a la izquierda), respecto a una transacción promedio. Son valores tipo SHAP "
                     "calculados directamente por LightGBM. Una barra de +0.7 equivale a multiplicar por ~2 las odds de fraude. "
                     "El aporte depende del contexto: cuando ya hay otras señales de riesgo, una señal adicional suma menos que en una transacción que parte de riesgo bajo.")

# --------------------------------------------------------------------------
# Pestaña 2: lote
# --------------------------------------------------------------------------
with tab2:
    st.subheader("Puntúa un lote de transacciones")
    st.write("Sirve para **las que ya están en tu base** (si el archivo trae la columna `is_fraud`, se mide qué tan bien las detecta el modelo) "
             "y para **las que están por llegar** (sin etiqueta: el modelo ordena por riesgo cuáles revisar primero).")

    origen = st.radio("Origen de los datos", ["Muestra histórica 2024 (con etiqueta)", "Muestra de transacciones nuevas (sin etiqueta)", "Subir mi propio CSV"],
                      horizontal=True)
    datos = None
    if origen.startswith("Muestra histórica"):
        datos = leer_muestra("sample_historical_2024.csv")
    elif origen.startswith("Muestra de transacciones nuevas"):
        datos = leer_muestra("sample_new_transactions.csv")
    else:
        archivo = st.file_uploader("CSV con una transacción por fila", type="csv")
        with st.expander("Columnas necesarias"):
            st.code(", ".join(REQUIRED_COLUMNS + ["hour_of_day  (o transaction_time)", "is_fraud  (opcional, para medir desempeño)",
                                                    "transaction_id  (opcional, para identificar)"]), language="text")
            st.download_button("Descargar plantilla", leer_muestra("sample_new_transactions.csv").head(5).to_csv(index=False),
                               "plantilla_transacciones.csv", "text/csv")
        if archivo is not None:
            try:
                datos = pd.read_csv(archivo, keep_default_na=False, na_values=[""], nrows=MAX_FILAS)
            except Exception as e:  # archivo ilegible
                st.error(f"No pude leer el archivo: {e}")

    if datos is not None:
        faltan = missing_columns(datos)
        if faltan:
            st.error("Al archivo le faltan estas columnas: " + ", ".join(faltan))
        else:
            n0 = len(datos)
            datos = datos.dropna(subset=[c for c in REQUIRED_COLUMNS if c in datos.columns]).copy()
            if len(datos) < n0:
                st.warning(f"Se omitieron {n0 - len(datos):,} filas con valores vacíos en columnas necesarias.")
            desconocidas = (~datos["merchant_category"].isin(MERCHANT_CATEGORIES)).sum()
            if desconocidas:
                st.warning(f"{desconocidas:,} filas tienen un tipo de comercio que el modelo no conoce; se puntúan sin esa información.")

            datos["prob_fraude"] = puntuar(datos)
            datos["nivel_riesgo"] = nivel_riesgo(datos["prob_fraude"])
            datos["alerta"] = datos["prob_fraude"] >= umbral

            n, n_alertas = len(datos), int(datos["alerta"].sum())
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Transacciones", f"{n:,}")
            k2.metric("Alertas generadas", f"{n_alertas:,}", f"{n_alertas / n:.1%} del lote", delta_color="off", delta_arrow="off")
            k3.metric("Probabilidad media", f"{datos.prob_fraude.mean():.1%}")
            k4.metric("Riesgo alto", f"{(datos.nivel_riesgo == 'Alto').sum():,}")

            if "is_fraud" in datos.columns and datos["is_fraud"].isin([0, 1]).all() and datos["is_fraud"].nunique() == 2:
                y = datos["is_fraud"].astype(int)
                tp = int((datos.alerta & (y == 1)).sum())
                st.markdown("##### Desempeño real sobre este lote")
                r1, r2, r3, r4, r5 = st.columns(5)
                r1.metric("Fraudes en el lote", f"{int(y.sum()):,}", f"{y.mean():.1%} del lote", delta_color="off", delta_arrow="off")
                r2.metric("Fraudes capturados", f"{tp:,}", f"{tp / y.sum():.0%} de los fraudes", delta_color="off", delta_arrow="off")
                r3.metric("Aciertos por alerta", f"{tp / max(n_alertas, 1):.0%}", f"{(tp / max(n_alertas, 1)) / y.mean():.1f}x el azar", delta_color="off", delta_arrow="off")
                r4.metric("ROC-AUC", f"{roc_auc_score(y, datos.prob_fraude):.3f}")
                r5.metric("PR-AUC", f"{average_precision_score(y, datos.prob_fraude):.3f}", f"azar {y.mean():.3f}", delta_color="off", delta_arrow="off")
                st.caption("La alerta usa el umbral de la barra lateral, calculado sobre 2024. Si el lote tiene otra composición, "
                           "el % de alertas puede diferir del K elegido.")

            orden = datos.sort_values("prob_fraude", ascending=False)
            cols_vista = [c for c in ["transaction_id", "merchant_category", "transaction_amount", "hour_of_day", "transaction_time",
                                      "failed_attempts", "is_international", "is_fraud"] if c in orden.columns]
            st.markdown("##### Transacciones con mayor riesgo")
            st.dataframe(orden[cols_vista + ["prob_fraude", "nivel_riesgo", "alerta"]].head(100), hide_index=True, width="stretch",
                         column_config={"prob_fraude": st.column_config.ProgressColumn("Prob. de fraude", format="percent", min_value=0, max_value=1),
                                        "nivel_riesgo": "Riesgo", "alerta": "Alerta", "transaction_amount": st.column_config.NumberColumn("Monto", format="$%.2f")})
            st.download_button("Descargar lote puntuado (CSV)", orden.to_csv(index=False), "transacciones_puntuadas.csv", "text/csv")

# --------------------------------------------------------------------------
# Pestaña 3: rendimiento
# --------------------------------------------------------------------------
with tab3:
    st.subheader("¿Qué tan bien funciona?")
    mt, ml = META["metricas_prueba"], META["metricas_regresion_logistica"]
    st.caption(f"Resultados sobre 2024 ({META['n_prueba']:,} transacciones que el modelo nunca vio). Entrenado con {META['entrenado_con']}.")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("ROC-AUC", f"{mt['ROC-AUC']:.3f}", f"+{mt['ROC-AUC'] - ml['ROC-AUC']:.3f} vs. reg. logística", delta_color="off", delta_arrow="off")
    q2.metric("PR-AUC", f"{mt['PR-AUC']:.3f}", f"{mt['PR-AUC'] / BASE:.1f}x el azar ({BASE:.3f})", delta_color="off", delta_arrow="off")
    q3.metric(f"Fraudes capturados (top {META['k_recomendado_pct']} %)", f"{OP.loc[META['k_recomendado_pct'], 'recall']:.0%}")
    q4.metric("Calibración (Brier)", f"{mt['Brier']:.4f}")

    st.info("**Lectura honesta de los resultados.** Es un dataset sintético donde el fraude depende de unas pocas reglas (intentos fallidos, "
            "operaciones internacionales, horario nocturno, comercios de riesgo, cambio de PIN) más mucho ruido aleatorio. Por eso el techo de "
            "desempeño es moderado (ROC-AUC ≈ 0.73) y el modelo no puede acercarse a 99 %. Una métrica mucho más alta sobre estos datos sería señal de "
            "fuga de información, no de un mejor modelo.")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Fraudes capturados según cuánto se revisa**")
        curva = OP.reset_index()
        linea = alt.Chart(curva).mark_line(color=AZUL, strokeWidth=3).encode(
            x=alt.X("k_pct:Q", title="% de transacciones revisadas (de mayor a menor riesgo)"),
            y=alt.Y("recall:Q", title="% de fraudes capturados", axis=alt.Axis(format="%")),
            tooltip=[alt.Tooltip("k_pct:Q", title="Revisadas (%)"), alt.Tooltip("recall:Q", title="Fraudes capturados", format=".0%"),
                     alt.Tooltip("precision:Q", title="Aciertos por alerta", format=".1%")])
        azar = alt.Chart(pd.DataFrame({"x": [0, 100], "y": [0, 1]})).mark_line(color=GRIS, strokeDash=[4, 4]).encode(x="x:Q", y="y:Q")
        punto = alt.Chart(OP.loc[[K]].reset_index()).mark_point(color=AZUL, size=140, filled=True, stroke="white", strokeWidth=2).encode(x="k_pct:Q", y="recall:Q")
        st.altair_chart((azar + linea + punto).properties(height=320), width="stretch")
        st.caption("La línea gris punteada es el azar. El punto marca tu punto de operación actual.")
    with g2:
        st.markdown("**Variables que más pesan**")
        imp = pd.DataFrame(META["importancia"])
        barras = alt.Chart(imp).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
            x=alt.X("valor:Q", title="Contribución media absoluta"), y=alt.Y("etiqueta:N", sort="-x", title=None, axis=alt.Axis(labelLimit=260)),
            tooltip=["etiqueta", alt.Tooltip("valor:Q", format=".3f")])
        st.altair_chart(barras.properties(height=320), width="stretch")

    st.markdown("**Simulador de impacto económico**")
    s1, s2 = st.columns(2)
    costo = s1.number_input("Costo de revisar una alerta (USD)", min_value=0.0, value=25.0, step=5.0,
                            help="Supuesto: tiempo del analista + fricción con el cliente.")
    perdida = s2.number_input("Pérdida media por fraude no detectado (USD)", min_value=0.0, value=float(round(META["monto_medio_fraude"])), step=10.0,
                              help="Por defecto, el monto medio de las transacciones fraudulentas de 2024.")
    sim = OP.reset_index()
    sim["valor_neto"] = 1000 * (sim["recall"] * BASE * perdida - sim["k_pct"] / 100 * costo)
    k_opt = int(sim.loc[sim.valor_neto.idxmax(), "k_pct"])
    tope = max(60, k_opt + 10)
    cv = alt.Chart(sim[sim.k_pct <= tope]).mark_line(color=AZUL, strokeWidth=3).encode(
        x=alt.X("k_pct:Q", title="% de transacciones revisadas"), y=alt.Y("valor_neto:Q", title="Valor neto (USD por 1 000 transacciones)"),
        tooltip=[alt.Tooltip("k_pct:Q", title="Revisadas (%)"), alt.Tooltip("valor_neto:Q", title="Valor neto", format="$,.0f")])
    cero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=GRIS).encode(y="y:Q")
    pto = alt.Chart(sim[sim.k_pct == k_opt]).mark_point(color=AZUL, size=140, filled=True, stroke="white", strokeWidth=2).encode(x="k_pct:Q", y="valor_neto:Q")
    st.altair_chart((cero + cv + pto).properties(height=260), width="stretch")
    mejor = sim[sim.k_pct == k_opt].iloc[0]
    st.caption(f"Con estos supuestos conviene revisar el **{k_opt} %** de las transacciones, con un valor neto aproximado de "
               f"**${mejor.valor_neto:,.0f} por cada 1 000 transacciones**. Cambia los supuestos para ver cómo se mueve el óptimo.")

    st.markdown("**Robustez en el tiempo (backtesting)**")
    bt = pd.DataFrame(META["backtest"]).rename(columns={"entrena": "Entrena con", "prueba": "Prueba en", "pr_auc": "PR-AUC", "roc_auc": "ROC-AUC",
                                                         "recall_top10": "Fraudes capturados (top 10 %)", "tasa_base": "Tasa base"})
    st.dataframe(bt.style.format({"PR-AUC": "{:.3f}", "ROC-AUC": "{:.3f}", "Fraudes capturados (top 10 %)": "{:.1%}", "Tasa base": "{:.2%}"}),
                 hide_index=True, width="stretch")

    st.markdown("**Curvas y calibración (2024)**")
    i1, i2 = st.columns([2, 1])
    i1.image(str(ROOT / "reports" / "figures" / "06_curvas_roc_pr.png"))
    i2.image(str(ROOT / "reports" / "figures" / "07_calibracion.png"))

# --------------------------------------------------------------------------
# Pestaña 4: sobre el proyecto
# --------------------------------------------------------------------------
with tab4:
    st.subheader("Cómo se construyó (CRISP-DM)")
    st.markdown(f"""
1. **Comprensión del negocio.** Detectar fraude en 1 millón de transacciones (2020-2024, 5.5 % de fraude) y decidir cuáles revisar con una capacidad limitada de analistas.
2. **Comprensión de los datos.** EDA, controles de calidad y hallazgos clave: el fraude se concentra en intentos fallidos ≥ 2, operaciones internacionales, horario nocturno y comercios de riesgo ({", ".join(RISKY_MERCHANTS)}). Se detectó y excluyó una variable con fuga de información (`fraud_type`).
3. **Preparación.** Selección de 11 variables (mismo rendimiento que usar las 20), transformaciones logarítmicas y partición **temporal**: entrenamiento 2020-2022, validación 2023, prueba 2024.
4. **Modelado.** Comparación contra una regla de negocio, regresión logística, Random Forest, XGBoost y LightGBM. Evalué balanceo de clases (no mejoró y descalibra las probabilidades) y ajusté hiperparámetros con búsqueda aleatoria.
5. **Evaluación.** PR-AUC, ROC-AUC, calibración, curva de ganancia, valor económico, backtesting por año y análisis de errores por tipo de fraude.
6. **Despliegue.** Esta aplicación.
""")
    st.subheader("Limitaciones")
    st.markdown("""
- Los datos son **sintéticos**: la ciudad no coincide con el país del cliente y todos los tipos de fraude se comportan igual. Con datos reales esperaría más señal (historial del cliente, dispositivo, geolocalización) y diferencias entre tipos de fraude.
- El modelo **puntúa** transacciones; no pronostica cuántas habrá. La tasa de fraude se mantuvo estable en los 5 años.
- El costo de revisión y la pérdida por fraude del simulador son supuestos que cada negocio debe fijar.
- En producción habría que monitorear deriva de datos y reentrenar periódicamente.
""")
    st.link_button("Código, notebook y documentación en GitHub", GITHUB_URL)
