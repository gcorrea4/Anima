"""
Anima v2 - Gerador de dataset SINTÉTICO com estatísticas de janela.

Em vez de sortear direto as estatísticas, simula o sinal bruto a 25 Hz (50 amostras
por janela de 2 s) e calcula média/desvio/máximo com a mesma função do firmware.
Classes: parado, normal, agitado, febre. A febre aparece com os três níveis de
movimento (inclusive "parado + febre", que faltava na v1).

ATENÇÃO: tudo aqui é sintético e foi escolhido à mão. Acurácia alta neste dataset
NÃO significa desempenho em animais reais. A temperatura de cada classe é
configurável em params_sinteticos.json (offset_coleira: o DS18B20 na coleira mede
pele/ambiente, não a temperatura corporal) e precisa ser recalibrada com dados reais.

Uso:
  python gerar_dataset_v2.py
  python gerar_dataset_v2.py --offset-coleira -4.0 --n-por-classe 800
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from features_v2 import FEATURES, N_AMOSTRAS, TAXA_HZ, estatisticas_janela

AQUI = Path(__file__).resolve().parent
SEED = 42
NIVEIS = ["parado", "normal", "agitado"]
G = 9.81


def carregar_params(caminho=None):
    return json.loads(Path(caminho or AQUI / "params_sinteticos.json").read_text(encoding="utf-8"))


def _sinal_dinamico(rng, n_jan, rms, freq_lo, freq_hi, prob_pico, limite, n=N_AMOSTRAS):
    """Sinal 3 eixos (n_jan, 3, n) com rms por janela dado, soma de senoides + ruído + picos."""
    t = np.arange(n) / TAXA_HZ
    k = 3
    freqs = rng.uniform(freq_lo, freq_hi, size=(n_jan, 3, k))
    fases = rng.uniform(0, 2 * np.pi, size=(n_jan, 3, k))
    base = np.sin(2 * np.pi * freqs[..., None] * t + fases[..., None]).sum(axis=2) * np.sqrt(2.0 / k)
    pesos = np.abs(rng.normal(size=(n_jan, 3)))
    pesos /= np.linalg.norm(pesos, axis=1, keepdims=True)
    sinal = base * (rms[:, None, None] * pesos[..., None])
    if prob_pico > 0:   # movimentos bruscos
        picos = (rng.random((n_jan, 3, n)) < prob_pico) * rng.normal(0, 2 * rms[:, None, None], (n_jan, 3, n))
        sinal = sinal + picos
    return np.clip(sinal, -limite, limite)


def _simular_nivel(rng, n_jan, nivel, p):
    """Devolve (accel_mag, gyro_mag) com shape (n_jan, N_AMOSTRAS) para um nível de movimento."""
    m = p["movimento"][nivel]
    rms_a = rng.lognormal(np.log(m["accel_rms"]), m["accel_sigma"], n_jan)
    rms_g = rng.lognormal(np.log(m["gyro_rms"]), m["gyro_sigma"], n_jan)
    dyn_a = _sinal_dinamico(rng, n_jan, rms_a, *m["freq_hz"], m["prob_pico"], 70.0)
    dyn_g = _sinal_dinamico(rng, n_jan, rms_g, *m["freq_hz"], m["prob_pico"], 500.0)
    # gravidade com orientação aleatória da coleira + ruído do sensor
    v = rng.normal(size=(n_jan, 3))
    grav = G * v / np.linalg.norm(v, axis=1, keepdims=True)
    acc = grav[..., None] + dyn_a + rng.normal(0, 0.04, dyn_a.shape)
    # viés do giroscópio (MPU6050 sem calibração tem alguns °/s de offset)
    vies = rng.normal(0, 1.5, size=(n_jan, 3, 1))
    gyr = vies + dyn_g + rng.normal(0, 0.3, dyn_g.shape)
    return np.linalg.norm(acc, axis=1), np.linalg.norm(gyr, axis=1)


def _simular_janelas(rng, nivel, n_jan, p):
    """Janelas de um nível, com uma fração 'mista' (muda de comportamento no meio)."""
    a, g = _simular_nivel(rng, n_jan, nivel, p)
    mistas = rng.random(n_jan) < p["prob_janela_mista"]
    if mistas.any():
        outro = [x for x in NIVEIS if x != nivel]
        nivel_b = rng.choice(outro)
        ab, gb = _simular_nivel(rng, n_jan, nivel_b, p)
        corte = rng.integers(10, 40, size=n_jan)
        mascara = (np.arange(N_AMOSTRAS)[None, :] >= corte[:, None]) & mistas[:, None]
        a = np.where(mascara, ab, a)
        g = np.where(mascara, gb, g)
    return a, g


def _temperaturas(rng, classe, n, p, offset):
    media, desvio = p["temperatura_corporal"][classe]
    febre_min, margem = p["febre_min_corporal"], p["margem_nao_febre"]
    t = rng.normal(media, desvio, n)
    for _ in range(100):   # amostragem por rejeição (trunca nas bordas da classe)
        ruim = (t < febre_min) if classe == "febre" else (t >= febre_min - margem)
        if not ruim.any():
            break
        t[ruim] = rng.normal(media, desvio, ruim.sum())
    t = np.clip(t, febre_min if classe == "febre" else -np.inf,
                np.inf if classe == "febre" else febre_min - margem - 1e-6)
    t = t + offset + rng.normal(0, p["ruido_temperatura_coleira"], n)
    return t


def gerar(n_por_classe=600, offset_coleira=None, params=None, seed=SEED):
    p = params or carregar_params()
    offset = p["offset_coleira"] if offset_coleira is None else offset_coleira
    rng = np.random.default_rng(seed)
    partes = []
    for classe in ["parado", "normal", "agitado", "febre"]:
        if classe == "febre":
            mix = p["mix_movimento_febre"]
            niveis = rng.choice(list(mix), size=n_por_classe, p=list(mix.values()))
        else:
            niveis = np.array([classe] * n_por_classe)
        a_mag = np.zeros((n_por_classe, N_AMOSTRAS))
        g_mag = np.zeros((n_por_classe, N_AMOSTRAS))
        for nivel in NIVEIS:
            idx = np.where(niveis == nivel)[0]
            if len(idx):
                a_mag[idx], g_mag[idx] = _simular_janelas(rng, nivel, len(idx), p)
        df = pd.DataFrame(estatisticas_janela(a_mag, g_mag))
        df["temperatura"] = _temperaturas(rng, classe, n_por_classe, p, offset)
        df["classe"] = classe
        df["movimento_base"] = niveis   # só para análise; NÃO é variável do modelo
        df["origem"] = "sintetico"
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    return df[FEATURES + ["classe", "movimento_base", "origem"]], offset


def main():
    ap = argparse.ArgumentParser(description="Gera o dataset sintético v2 (estatísticas de janela)")
    ap.add_argument("--n-por-classe", type=int, default=600)
    ap.add_argument("--offset-coleira", type=float, default=None,
                    help="°C somados às temperaturas (sobrescreve params_sinteticos.json)")
    ap.add_argument("--params", default=None, help="JSON de parâmetros (padrão: params_sinteticos.json)")
    ap.add_argument("--saida", default=str(AQUI / "dataset_anima_sintetico_v2.csv"))
    args = ap.parse_args()

    df, offset = gerar(args.n_por_classe, args.offset_coleira, carregar_params(args.params))
    df.to_csv(args.saida, index=False)
    print(f"Dataset v2 gerado: {len(df)} janelas, offset_coleira={offset:+.2f} °C -> {args.saida}")
    print(df["classe"].value_counts().to_string())
    print("\nFebre por nível de movimento:")
    print(df[df.classe == "febre"]["movimento_base"].value_counts().to_string())
    print("\nTemperatura por classe (média ± desvio):")
    print(df.groupby("classe")["temperatura"].agg(["mean", "std"]).round(2).to_string())


if __name__ == "__main__":
    main()
