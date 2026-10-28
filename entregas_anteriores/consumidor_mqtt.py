"""
Anima - Consumidor MQTT com classificação por IA
Entrega 2 - Disruptive Architectures: IoT, IoB e Generative IA

Assina o tópico em que o ESP32 (real ou simulado no Wokwi) publica as
leituras, monta o vetor de 9 variáveis, consulta o modelo Random Forest
treinado e imprime a classe prevista, as probabilidades e a ação que o
sistema tomaria (mesmas regras da Tabela 1 do artigo).

Uso:
  python consumidor_mqtt.py --selftest      # testa o modelo sem rede
  python consumidor_mqtt.py                 # escuta o broker e classifica
  python consumidor_mqtt.py --publicar-decisao   # também publica em anima/decisao

Dependências: pip install paho-mqtt scikit-learn pandas numpy joblib
"""

import argparse
import json
import random
import sys
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message=".*version.*when using version.*")

BROKER = "broker.hivemq.com"
PORTA = 1883
TOPICO_DADOS = "anima/dados"        # mesmo tópico do firmware (anima_esp32.ino)
TOPICO_DECISAO = "anima/decisao"    # opcional: decisão da IA (o firmware ainda não assina)
LIMIAR_CONFIANCA = 0.6              # mesma regra da Tabela 1 do artigo

CAMPOS = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z", "temperatura"]
FEATURES = CAMPOS + ["accel_mag", "gyro_mag"]

# Mesmos 3 cenários do artigo (seção 13.3)
CENARIOS_SELFTEST = {
    "letargico (esperado)": {"accel_x": 0.01, "accel_y": 0.03, "accel_z": 9.79,
                             "gyro_x": 0.4, "gyro_y": 0.6, "gyro_z": 0.3, "temperatura": 37.85},
    "normal (esperado)": {"accel_x": 0.35, "accel_y": 0.18, "accel_z": 9.75,
                          "gyro_x": 6, "gyro_y": 4, "gyro_z": 5, "temperatura": 38.6},
    "febre (esperado)": {"accel_x": 0.28, "accel_y": 0.22, "accel_z": 9.78,
                         "gyro_x": 4, "gyro_y": 3, "gyro_z": 4, "temperatura": 40.1},
}


def montar_features(payload):
    """Converte o payload JSON do ESP32 no vetor de 9 variáveis do modelo."""
    v = [float(payload[c]) for c in CAMPOS]
    accel_mag = float(np.linalg.norm(v[0:3]))
    gyro_mag = float(np.linalg.norm(v[3:6]))
    return pd.DataFrame([v + [accel_mag, gyro_mag]], columns=FEATURES)


def decidir_acao(classe, confianca):
    """Regras de decisão (Tabela 1 do artigo)."""
    if classe in ("agitado", "febre") and confianca > LIMIAR_CONFIANCA:
        return "ALERTA: buzzer local + notificação no app"
    if classe == "letargico" and confianca > LIMIAR_CONFIANCA:
        return "ALERTA LEVE: notificação no app"
    return "sem alerta"


def classificar(payload, modelo):
    """Retorna (classe, dict de probabilidades, ação). Levanta ValueError se o payload for inválido."""
    faltando = [c for c in CAMPOS if c not in payload]
    if faltando:
        raise ValueError(f"campos ausentes: {faltando}")
    # DS18B20 desconectado devolve -127 °C: não é leitura válida (limitação do firmware, seção 13.2)
    if float(payload["temperatura"]) <= -100:
        raise ValueError("temperatura = -127 °C (sensor DS18B20 desconectado?) - leitura descartada")
    X = montar_features(payload)
    probs = modelo.predict_proba(X)[0]
    i = int(np.argmax(probs))
    classe = str(modelo.classes_[i])
    return classe, {str(c): float(p) for c, p in zip(modelo.classes_, probs)}, decidir_acao(classe, float(probs[i]))


def carregar_modelo(caminho):
    if not Path(caminho).exists():
        sys.exit(f"Modelo não encontrado em '{caminho}'. Use --modelo para indicar o .pkl.")
    return joblib.load(caminho)


def selftest(modelo):
    print("Selftest do modelo (sem rede):")
    for nome, payload in CENARIOS_SELFTEST.items():
        classe, probs, acao = classificar(payload, modelo)
        print(f"  {nome:22s} -> {classe:10s} conf={max(probs.values()):.2f} | {acao}")


def executar(modelo, publicar_decisao):
    import paho.mqtt.client as mqtt

    # paho-mqtt 2.x exige a versão da API de callbacks; a 1.x não tem esse atributo
    versao = getattr(mqtt, "CallbackAPIVersion", None)
    client_id = f"anima_consumidor_{random.randint(0, 99999)}"
    cliente = mqtt.Client(versao.VERSION2, client_id=client_id) if versao else mqtt.Client(client_id=client_id)

    def on_connect(c, userdata, flags, rc, properties=None):
        print(f"Conectado ao broker {BROKER} (rc={rc}). Assinando '{TOPICO_DADOS}'...")
        c.subscribe(TOPICO_DADOS)

    def on_message(c, userdata, msg):
        hora = time.strftime("%H:%M:%S")
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            classe, probs, acao = classificar(payload, modelo)
        except (ValueError, KeyError, TypeError) as erro:
            print(f"[{hora}] mensagem ignorada: {erro}")
            return
        resumo = " ".join(f"{k}={v:.2f}" for k, v in probs.items())
        print(f"[{hora}] gyro=({payload['gyro_x']:.1f},{payload['gyro_y']:.1f},{payload['gyro_z']:.1f}) °/s "
              f"temp={payload['temperatura']:.2f} °C -> {classe.upper()} | {resumo} | {acao}")
        if publicar_decisao:
            c.publish(TOPICO_DECISAO, json.dumps({"classe": classe, "probabilidades": probs, "acao": acao}))

    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.connect(BROKER, PORTA, keepalive=60)
    try:
        cliente.loop_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Consumidor MQTT do Anima com classificação por IA")
    ap.add_argument("--modelo", default=str(Path(__file__).with_name("modelo_anima_rf.pkl")))
    ap.add_argument("--selftest", action="store_true", help="testa o modelo com 3 cenários, sem rede")
    ap.add_argument("--publicar-decisao", action="store_true", help=f"publica a decisão em '{TOPICO_DECISAO}'")
    args = ap.parse_args()

    modelo = carregar_modelo(args.modelo)
    if args.selftest:
        selftest(modelo)
    else:
        executar(modelo, args.publicar_decisao)
