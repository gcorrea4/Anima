"""
Anima v2 - Treino do Random Forest (biblioteca usada por treinar_modelo_v2.py e retreinar.py).

Hiperparâmetros iniciais = v1 (200 árvores, profundidade 8, class_weight=balanced, seed 42),
split 80/20 estratificado por classe.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

from features_v2 import FEATURES

SEED = 42
HIPERPARAMETROS = dict(n_estimators=200, max_depth=8, random_state=SEED, class_weight="balanced")


def treinar(df, saida_dir, sufixo="v2", offset_coleira=0.0, febre_min_corporal=39.5,
            peso_real=1.0, extra_meta=None, titulo="Anima v2 (dados SINTÉTICOS)"):
    """Treina, avalia e salva modelo + relatórios. Devolve (modelo, métricas)."""
    saida_dir = Path(saida_dir)
    saida_dir.mkdir(parents=True, exist_ok=True)
    df = df.dropna(subset=FEATURES + ["classe"]).reset_index(drop=True)
    if "origem" not in df:
        df["origem"] = "sintetico"
    X, y = df[FEATURES], df["classe"]
    contagem = y.value_counts()
    if contagem.min() < 2:
        raise ValueError(f"Classe com menos de 2 amostras, impossível estratificar: {contagem.to_dict()}")

    idx_tr, idx_te = train_test_split(df.index, test_size=0.2, random_state=SEED, stratify=y)
    pesos = np.where(df.loc[idx_tr, "origem"] == "real", peso_real, 1.0)
    modelo = RandomForestClassifier(**HIPERPARAMETROS)
    modelo.fit(X.loc[idx_tr], y.loc[idx_tr], sample_weight=pesos)

    pred = modelo.predict(X.loc[idx_te])
    y_te = y.loc[idx_te]
    labels = list(modelo.classes_)
    acc = accuracy_score(y_te, pred)
    f1 = f1_score(y_te, pred, average="macro")
    rel = classification_report(y_te, pred, digits=3)
    cm = confusion_matrix(y_te, pred, labels=labels)

    linhas = [
        f"{titulo}",
        "AVISO: métricas calculadas sobre o MESMO gerador sintético do treino; medem o quão separáveis são as",
        "classes simuladas, NÃO o desempenho em animais reais.",
        "",
        f"Janelas treino/teste: {len(idx_tr)}/{len(idx_te)}  (origem: {df['origem'].value_counts().to_dict()})",
        f"Acurácia: {acc:.4f}   F1 macro: {f1:.4f}",
        f"Hiperparâmetros: {HIPERPARAMETROS}",
        "", rel,
    ]
    # métricas por origem (importante quando há dado real misturado)
    for origem in sorted(df.loc[idx_te, "origem"].unique()):
        m = (df.loc[idx_te, "origem"] == origem).values
        if m.sum() > 0:
            linhas.append(f"[origem={origem}] n={m.sum()} acurácia={accuracy_score(y_te[m], pred[m]):.4f}")
    # parado + febre (só se houver coluna movimento_base)
    if "movimento_base" in df:
        m = ((df.loc[idx_te, "classe"] == "febre") & (df.loc[idx_te, "movimento_base"] == "parado")).values
        if m.sum():
            linhas.append(f"[parado+febre] n={m.sum()} recall de febre={np.mean(pred[m] == 'febre'):.3f}")
    relatorio = "\n".join(linhas)
    (saida_dir / f"relatorio_classificacao_{sufixo}.txt").write_text(relatorio, encoding="utf-8")

    # matriz de confusão
    pd.DataFrame(cm, index=labels, columns=labels).to_csv(saida_dir / f"matriz_confusao_{sufixo}.csv")
    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=30)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Previsto"); ax.set_ylabel("Real")
    ax.set_title("Matriz de confusão (teste sintético)")
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, cm[i, j], ha="center", va="center", color="white" if cm[i, j] > cm.max() / 2 else "black")
    fig.colorbar(im); fig.tight_layout()
    fig.savefig(saida_dir / f"matriz_confusao_{sufixo}.png", dpi=130); plt.close(fig)

    # importância das variáveis
    imp = pd.Series(modelo.feature_importances_, index=FEATURES).sort_values(ascending=False)
    imp.to_csv(saida_dir / f"importancia_variaveis_{sufixo}.csv", header=["importancia"])
    fig, ax = plt.subplots(figsize=(6.5, 4))
    imp[::-1].plot.barh(ax=ax, color="#3b7dd8")
    ax.set_title("Importância das variáveis (RF v2)"); ax.set_xlabel("importância")
    fig.tight_layout(); fig.savefig(saida_dir / f"importancia_variaveis_{sufixo}.png", dpi=130); plt.close(fig)

    nome_modelo = saida_dir / f"modelo_anima_rf_{sufixo}.pkl"
    joblib.dump(modelo, nome_modelo)
    meta = {
        "versao_modelo": sufixo,
        "features": FEATURES,
        "classes": labels,
        "offset_coleira": offset_coleira,
        "temp_febre_min_coleira": round(febre_min_corporal + offset_coleira, 3),
        "temp_seguranca_coleira": round(febre_min_corporal + offset_coleira, 3),
        "hiperparametros": {k: v for k, v in HIPERPARAMETROS.items()},
        "seed": SEED,
        "treinado_em": datetime.now().isoformat(timespec="seconds"),
        "sklearn": sklearn.__version__,
        "origens": df["origem"].value_counts().to_dict(),
        "acuracia_teste": round(float(acc), 4),
        "f1_macro_teste": round(float(f1), 4),
        "aviso": "Métricas sintéticas; recalibrar offset_coleira e retreinar com dados reais.",
    }
    meta.update(extra_meta or {})
    (saida_dir / f"modelo_anima_rf_{sufixo}.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return modelo, {"acuracia": acc, "f1": f1, "relatorio": relatorio, "matriz": cm, "labels": labels}


def confirmar_sobrescrita(caminho, sim=False, tty=None, entrada=input):
    """True se pode gravar em `caminho`. Se o modelo já existe, só segue com --sim ou com confirmação interativa.

    Sem terminal interativo (scripts, CI) e sem --sim, recusa: nunca sobrescreve o modelo em silêncio.
    """
    caminho = Path(caminho)
    if sim or not caminho.exists():
        return True
    print(f"AVISO: {caminho} já existe e será SOBRESCRITO (junto com .meta.json, relatório e gráficos).")
    print("  Para não sobrescrever: --saida-dir <pasta> e/ou --sufixo <nome>. Para confirmar sem perguntar: --sim.")
    if (sys.stdin.isatty() if tty is None else tty):
        try:
            return entrada("Sobrescrever? [s/N] ").strip().lower() in ("s", "sim", "y", "yes")
        except (EOFError, KeyboardInterrupt):   # stdin vazio/fechado (no Windows o NUL se diz "terminal"): sem confirmação
            print()
    return False


def teste_parado_febre(modelo):
    """Cenário explícito pedido: animal imóvel a 40,1 °C deve ser classificado como febre."""
    x = pd.DataFrame([{
        "accel_mag_media": 9.81, "accel_mag_std": 0.05, "accel_mag_max": 9.95,
        "gyro_mag_media": 1.0, "gyro_mag_std": 0.4, "gyro_mag_max": 2.2, "temperatura": 40.1}])[FEATURES]
    probs = modelo.predict_proba(x)[0]
    classe = str(modelo.classes_[int(np.argmax(probs))])
    return classe, dict(zip(map(str, modelo.classes_), map(float, probs)))
