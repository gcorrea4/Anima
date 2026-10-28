"""
Anima - Treinamento do Modelo de Classificação
Entrega 2 - Disruptive Architectures: IoT, IoB e Generative IA

Treina um modelo Random Forest para classificar o estado comportamental
do pet (normal / letargico / agitado / febre) a partir das leituras do
MPU6050 (acelerômetro + giroscópio) e DS18B20 (temperatura).

Entradas do modelo (features):
  accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z, temperatura,
  accel_mag, gyro_mag (magnitudes derivadas)

Saída do modelo:
  Uma das 4 classes: normal, letargico, agitado, febre

Algoritmo escolhido: Random Forest
Justificativa: bom desempenho com poucas features numéricas, robusto a
outliers, não exige normalização dos dados, é interpretável (permite
extrair a importância de cada feature) e é leve o suficiente para
rodar embarcado em um servidor simples ou até via TinyML simplificado
no futuro, sem exigir GPU.
"""

import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix, f1_score
)

RANDOM_SEED = 42

# 1. Carrega o dataset sintético gerado na etapa anterior
df = pd.read_csv("dataset_anima_sintetico.csv")

FEATURES = ["accel_x", "accel_y", "accel_z",
            "gyro_x", "gyro_y", "gyro_z",
            "temperatura", "accel_mag", "gyro_mag"]
TARGET = "classe"

X = df[FEATURES]
y = df[TARGET]

# 2. Divide em treino (80%) e teste (20%), estratificado por classe
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
)

print(f"Amostras de treino: {len(X_train)}")
print(f"Amostras de teste:  {len(X_test)}")

# 3. Treina o modelo
modelo = RandomForestClassifier(
    n_estimators=200,
    max_depth=8,
    random_state=RANDOM_SEED,
    class_weight="balanced",
)
modelo.fit(X_train, y_train)

# 4. Avalia no conjunto de teste (dados que o modelo nunca viu)
y_pred = modelo.predict(X_test)

acuracia = accuracy_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred, average="macro")

print(f"\nAcurácia no conjunto de teste: {acuracia:.4f} ({acuracia*100:.2f}%)")
print(f"F1-score (macro): {f1:.4f}")
print("\nRelatório de classificação:")
report = classification_report(y_test, y_pred)
print(report)

# 5. Matriz de confusão (salva para gerar gráfico depois)
labels = sorted(y.unique())
cm = confusion_matrix(y_test, y_pred, labels=labels)
np.save("confusion_matrix.npy", cm)
with open("labels.txt", "w") as f:
    f.write("\n".join(labels))

# 6. Importância das features (explicabilidade do modelo)
importancias = pd.Series(modelo.feature_importances_, index=FEATURES).sort_values(ascending=False)
print("\nImportância das features:")
print(importancias)
importancias.to_csv("feature_importances.csv")

# 7. Salva o relatório de classificação em texto
with open("classification_report.txt", "w") as f:
    f.write(f"Acuracia: {acuracia:.4f}\n")
    f.write(f"F1-score (macro): {f1:.4f}\n\n")
    f.write(report)

# 8. Salva o modelo treinado para uso futuro (ex: servidor que recebe dados via MQTT)
joblib.dump(modelo, "modelo_anima_rf.pkl")

print("\nModelo salvo em modelo_anima_rf.pkl")
print("Matriz de confusão salva em confusion_matrix.npy")
