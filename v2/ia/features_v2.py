"""
Anima v2 - Definição única das variáveis (features) e classes.

Usado pelo gerador de dataset, pelo treino, pelo coletor e pelo servidor, para
que o payload do firmware, o dataset e o modelo falem exatamente a mesma língua.
"""
import json
from pathlib import Path

import numpy as np

VERSAO_PAYLOAD = 2
TAXA_HZ = 25            # amostragem do firmware
JANELA_S = 2            # janela de estatísticas
N_AMOSTRAS = TAXA_HZ * JANELA_S   # 50

FEATURES = [
    "accel_mag_media", "accel_mag_std", "accel_mag_max",   # m/s²
    "gyro_mag_media", "gyro_mag_std", "gyro_mag_max",      # °/s
    "temperatura",                                         # °C (DS18B20 na coleira)
]
CLASSES = ["agitado", "febre", "normal", "parado"]
# Rótulos aceitos na coleta de dados reais = classes do modelo
ROTULOS = CLASSES

IA_DIR = Path(__file__).resolve().parent
MODELO_PADRAO = IA_DIR / "modelo_anima_rf_v2.pkl"


def estatisticas_janela(accel_mag, gyro_mag):
    """Estatísticas de uma janela, no mesmo cálculo do firmware (desvio populacional).

    Aceita arrays (..., n) e devolve dict de arrays (...,).
    """
    a = np.asarray(accel_mag, dtype=float)
    g = np.asarray(gyro_mag, dtype=float)
    return {
        "accel_mag_media": a.mean(axis=-1), "accel_mag_std": a.std(axis=-1), "accel_mag_max": a.max(axis=-1),
        "gyro_mag_media": g.mean(axis=-1), "gyro_mag_std": g.std(axis=-1), "gyro_mag_max": g.max(axis=-1),
    }


def caminho_meta(caminho_modelo):
    p = Path(caminho_modelo)
    return p.with_name(p.stem + ".meta.json")


def carregar_meta(caminho_modelo=MODELO_PADRAO):
    """Metadados salvos junto com o modelo (offset, limiar de segurança etc.). {} se não existir."""
    p = caminho_meta(caminho_modelo)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}
