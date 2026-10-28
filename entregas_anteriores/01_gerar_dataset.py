"""
Anima - Geração de Dataset Sintético
Entrega 2 - Disruptive Architectures: IoT, IoB e Generative IA

Este script gera um dataset sintético que simula leituras do sensor
MPU6050 (acelerômetro + giroscópio) e DS18B20 (temperatura) para três
estados comportamentais de um pet: normal, letárgico e agitado.

Justificativa da simulação (transparente no artigo):
Como o hardware físico (ESP32 + MPU6050 + DS18B20) ainda não foi
adquirido pelo grupo, os dados usados para treinar e validar o modelo
de IA nesta etapa são sintéticos, gerados com base em padrões
fisiologicamente plausíveis descritos na literatura sobre acelerometria
em animais (repouso = baixa variância de aceleração; atividade normal =
variância moderada e cadência regular; agitação = alta variância e
picos de giroscópio; letargia = quase nenhuma variação e temperatura
levemente mais baixa; possível febre = temperatura elevada).
Esses dados serão substituídos por leituras reais assim que os
componentes forem adquiridos (previsto para a Entrega 3), conforme
descrito na seção de metodologia do artigo.
"""

import numpy as np
import pandas as pd

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Cada "amostra" representa uma janela de 2 segundos de leitura do sensor
# (mesma taxa de amostragem usada no firmware do ESP32: READ_INTERVAL = 2000ms)
N_POR_CLASSE = 500

def gerar_classe(nome, n,
                  accel_mean, accel_std,
                  gyro_mean, gyro_std,
                  temp_mean, temp_std):
    """Gera N amostras para uma classe comportamental."""
    dados = {
        "accel_x": np.random.normal(accel_mean[0], accel_std, n),
        "accel_y": np.random.normal(accel_mean[1], accel_std, n),
        "accel_z": np.random.normal(accel_mean[2], accel_std, n),
        "gyro_x":  np.random.normal(gyro_mean[0], gyro_std, n),
        "gyro_y":  np.random.normal(gyro_mean[1], gyro_std, n),
        "gyro_z":  np.random.normal(gyro_mean[2], gyro_std, n),
        "temperatura": np.random.normal(temp_mean, temp_std, n),
        "classe": [nome] * n,
    }
    return pd.DataFrame(dados)

# --- Normal: movimento moderado, cadência razoavelmente regular, temp normal de cão/gato (~38.5°C) ---
df_normal = gerar_classe(
    "normal", N_POR_CLASSE,
    accel_mean=(0.3, 0.2, 9.8), accel_std=1.2,
    gyro_mean=(5, 5, 5), gyro_std=8,
    temp_mean=38.5, temp_std=0.3,
)

# --- Letárgico: pouquíssima variação de movimento (quase parado), temperatura levemente reduzida ---
df_letargico = gerar_classe(
    "letargico", N_POR_CLASSE,
    accel_mean=(0.02, 0.02, 9.81), accel_std=0.15,
    gyro_mean=(0.5, 0.5, 0.5), gyro_std=1.0,
    temp_mean=37.9, temp_std=0.25,
)

# --- Agitado: alta variância de aceleração e giroscópio (movimentos bruscos/repetidos) ---
df_agitado = gerar_classe(
    "agitado", N_POR_CLASSE,
    accel_mean=(0.5, 0.4, 9.9), accel_std=3.5,
    gyro_mean=(15, 12, 10), gyro_std=25,
    temp_mean=38.7, temp_std=0.35,
)

# --- Possível febre: movimento próximo do normal, mas temperatura elevada (>39.5°C) ---
df_febre = gerar_classe(
    "febre", N_POR_CLASSE,
    accel_mean=(0.25, 0.2, 9.8), accel_std=1.0,
    gyro_mean=(4, 4, 4), gyro_std=7,
    temp_mean=40.0, temp_std=0.4,
)

df = pd.concat([df_normal, df_letargico, df_agitado, df_febre], ignore_index=True)

# Adiciona uma feature derivada: magnitude do vetor de aceleração
# (comum em projetos de reconhecimento de atividade com IMU)
df["accel_mag"] = np.sqrt(df["accel_x"]**2 + df["accel_y"]**2 + df["accel_z"]**2)
df["gyro_mag"] = np.sqrt(df["gyro_x"]**2 + df["gyro_y"]**2 + df["gyro_z"]**2)

# Embaralha as linhas
df = df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

df.to_csv("dataset_anima_sintetico.csv", index=False)

print(f"Dataset gerado com {len(df)} amostras.")
print(df["classe"].value_counts())
print("\nPrimeiras linhas:")
print(df.head())
