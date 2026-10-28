"""
Anima - Visualização dos Resultados
Entrega 2 - Disruptive Architectures: IoT, IoB e Generative IA

Gera os gráficos reais a partir do modelo treinado:
  1. Matriz de confusão
  2. Importância das features
  3. Dispersão das classes (accel_mag x gyro_mag) - mostra separabilidade
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Paleta neutra, acessível (mesma cor por classe em todos os gráficos)
PALETTE = {
    "normal": "#4C78A8",
    "letargico": "#F58518",
    "agitado": "#E45756",
    "febre": "#54A24B",
}

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#444444",
    "axes.labelcolor": "#222222",
    "text.color": "#222222",
    "xtick.color": "#444444",
    "ytick.color": "#444444",
    "font.size": 11,
})

# ---------- 1. Matriz de confusão ----------
cm = np.load("confusion_matrix.npy")
with open("labels.txt") as f:
    labels = f.read().splitlines()

fig, ax = plt.subplots(figsize=(6, 5))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
            xticklabels=labels, yticklabels=labels, ax=ax, cbar=False,
            linewidths=0.5, linecolor="white")
ax.set_xlabel("Classe prevista pelo modelo")
ax.set_ylabel("Classe real")
ax.set_title("Matriz de Confusão — Modelo Anima (Random Forest)")
plt.tight_layout()
plt.savefig("grafico_matriz_confusao.png", dpi=150)
plt.close()

# ---------- 2. Importância das features ----------
imp = pd.read_csv("feature_importances.csv", index_col=0).squeeze("columns")
imp = imp.sort_values(ascending=True)

fig, ax = plt.subplots(figsize=(7, 4.5))
ax.barh(imp.index, imp.values, color="#4C78A8")
ax.set_xlabel("Importância relativa")
ax.set_title("Importância das Variáveis no Modelo")
for i, v in enumerate(imp.values):
    ax.text(v + 0.005, i, f"{v:.3f}", va="center", fontsize=9)
plt.tight_layout()
plt.savefig("grafico_feature_importance.png", dpi=150)
plt.close()

# ---------- 3. Dispersão das classes ----------
df = pd.read_csv("dataset_anima_sintetico.csv")

fig, ax = plt.subplots(figsize=(7, 5.5))
for classe, cor in PALETTE.items():
    subset = df[df["classe"] == classe]
    ax.scatter(subset["gyro_mag"], subset["temperatura"],
               label=classe, color=cor, alpha=0.55, s=18, edgecolors="none")
ax.set_xlabel("Magnitude do giroscópio (gyro_mag)")
ax.set_ylabel("Temperatura corporal (°C)")
ax.set_title("Separação das Classes no Dataset Sintético")
ax.legend(title="Classe", frameon=False)
plt.tight_layout()
plt.savefig("grafico_dispersao_classes.png", dpi=150)
plt.close()

print("Gráficos gerados:")
print(" - grafico_matriz_confusao.png")
print(" - grafico_feature_importance.png")
print(" - grafico_dispersao_classes.png")
