"""
Anima - Exemplo de Inferência (uso do modelo em "produção")
Entrega 2 - Disruptive Architectures: IoT, IoB e Generative IA

Demonstra como o modelo treinado seria usado no fluxo real do sistema:
o ESP32 publica uma leitura via MQTT (payload JSON) -> um serviço
consumidor (ex: script Python rodando em um servidor/Raspberry Pi)
recebe a mensagem, monta o vetor de features, chama o modelo e decide
se deve disparar um alerta.

Este script simula esse consumidor, usando 3 leituras de exemplo
(uma de cada situação) para mostrar a entrada, a saída do modelo, e a
ação que o sistema tomaria em cada caso.
"""

import numpy as np
import joblib

FEATURES = ["accel_x", "accel_y", "accel_z",
            "gyro_x", "gyro_y", "gyro_z",
            "temperatura", "accel_mag", "gyro_mag"]

modelo = joblib.load("modelo_anima_rf.pkl")

# Simula 3 mensagens MQTT recebidas do ESP32 (payload JSON já decodificado)
mensagens_exemplo = [
    {
        "descricao": "Pet parado a maior parte do tempo (possível letargia)",
        "payload": {"accel_x": 0.01, "accel_y": 0.03, "accel_z": 9.79,
                    "gyro_x": 0.4, "gyro_y": 0.6, "gyro_z": 0.3,
                    "temperatura": 37.85},
    },
    {
        "descricao": "Pet brincando normalmente",
        "payload": {"accel_x": 0.35, "accel_y": 0.18, "accel_z": 9.75,
                    "gyro_x": 6, "gyro_y": 4, "gyro_z": 5,
                    "temperatura": 38.6},
    },
    {
        "descricao": "Temperatura elevada, movimento próximo do normal (possível febre)",
        "payload": {"accel_x": 0.28, "accel_y": 0.22, "accel_z": 9.78,
                    "gyro_x": 4, "gyro_y": 3, "gyro_z": 4,
                    "temperatura": 40.1},
    },
]

def montar_features(payload):
    import pandas as pd
    accel_mag = np.sqrt(payload["accel_x"]**2 + payload["accel_y"]**2 + payload["accel_z"]**2)
    gyro_mag = np.sqrt(payload["gyro_x"]**2 + payload["gyro_y"]**2 + payload["gyro_z"]**2)
    vetor = [payload[f] for f in FEATURES[:7]] + [accel_mag, gyro_mag]
    return pd.DataFrame([vetor], columns=FEATURES)

def decidir_acao(classe_prevista, probabilidades, labels):
    prob_max = max(probabilidades)
    if classe_prevista in ("agitado", "febre") and prob_max > 0.6:
        return f"ALERTA disparado (buzzer local + notificação no app) — confiança {prob_max:.0%}"
    elif classe_prevista == "letargico" and prob_max > 0.6:
        return f"ALERTA leve disparado (notificação no app) — confiança {prob_max:.0%}"
    else:
        return f"Sem alerta — comportamento dentro do esperado (confiança {prob_max:.0%})"

print("=" * 70)
print("SIMULAÇÃO: modelo Anima recebendo dados via MQTT e decidindo alertas")
print("=" * 70)

for msg in mensagens_exemplo:
    X_novo = montar_features(msg["payload"])
    classe = modelo.predict(X_novo)[0]
    probs = modelo.predict_proba(X_novo)[0]
    labels = modelo.classes_

    print(f"\nCenário: {msg['descricao']}")
    print(f"Payload recebido: {msg['payload']}")
    print(f"Classe prevista pelo modelo: {classe}")
    print(f"Probabilidades: " + ", ".join(f"{l}={p:.2f}" for l, p in zip(labels, probs)))
    print(f"Ação do sistema: {decidir_acao(classe, probs, labels)}")
