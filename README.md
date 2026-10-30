# Detección de fraude bancario

Modelo de machine learning para identificar transacciones fraudulentas, desarrollado con la metodología CRISP-DM y desplegado en una app de Streamlit.

> Este README es una versión técnica provisional. La versión narrativa del proyecto se escribe aparte.

## Estructura

```
├── app.py                         # App de Streamlit
├── notebooks/
│   └── 01_fraud_detection_crisp_dm.ipynb   # Proyecto completo (CRISP-DM)
├── src/features.py                # Ingeniería de variables (compartida por notebook y app)
├── models/
│   ├── fraud_lgbm.txt             # Modelo LightGBM entrenado
│   └── metadata.json              # Métricas, umbrales y variables
├── data/                          # Muestras pequeñas para probar la app
├── reports/figures/               # Gráficos del análisis
└── requirements.txt
```

## Ejecutar la app

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Reproducir el entrenamiento

1. Descarga `bank_fraud.csv` de [Kaggle](https://www.kaggle.com/datasets/nafiulislam490/bank-transaction-fraud-detection-dataset) y colócalo en `data/`.
2. `pip install -r requirements-dev.txt`
3. Ejecuta `notebooks/01_fraud_detection_crisp_dm.ipynb`. Al final regenera `models/` y las muestras de `data/`.

## Datos

Dataset sintético de 1 000 000 de transacciones (2020-2024) con 5.5 % de fraude.
