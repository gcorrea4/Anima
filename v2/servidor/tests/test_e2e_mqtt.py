"""
Ponta a ponta SEM hardware e SEM internet: mini-broker local + consumidor_v2.py / coletar_dados.py
rodando como processos reais + um "dispositivo simulado" publicando payloads no formato do firmware.
(Não testa o firmware em si nem a rede Wi-Fi.)
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import payload_v2
from features_v2 import MODELO_PADRAO
from mini_broker import MiniBroker

SERVIDOR = Path(__file__).resolve().parents[1]


def _cliente(broker, nome):
    import paho.mqtt.client as mqtt
    v = getattr(mqtt, "CallbackAPIVersion", None)
    c = mqtt.Client(v.VERSION2, client_id=nome) if v else mqtt.Client(client_id=nome)
    c.connect("127.0.0.1", broker.port)
    c.loop_start()
    return c


def _esperar(cond, timeout=30):
    fim = time.time() + timeout
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture()
def broker():
    b = MiniBroker().start()
    yield b
    b.stop()


def _env(broker, tmp_path):
    env = dict(os.environ, ANIMA_MQTT_HOST="127.0.0.1", ANIMA_MQTT_PORT=str(broker.port),
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    for k in ("ANIMA_MQTT_USER", "ANIMA_MQTT_PASS", "ANIMA_MQTT_TLS", "ANIMA_TELEGRAM_TOKEN", "ANIMA_TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    env["ANIMA_SEM_DOTENV"] = "1"   # não carregar o .env real (evita mandar mensagens de teste ao Telegram)
    return env


@pytest.mark.skipif(not MODELO_PADRAO.exists(), reason="modelo v2 ausente")
def test_servidor_publica_decisao_para_dispositivo(broker, tmp_path):
    log = tmp_path / "log.csv"
    proc = subprocess.Popen([sys.executable, str(SERVIDOR / "consumidor_v2.py"), "--todos", "--log", str(log)],
                            env=_env(broker, tmp_path), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8")
    saida = []
    threading.Thread(target=lambda: [saida.append(l) for l in proc.stdout], daemon=True).start()
    try:
        assert _esperar(lambda: "anima/+/dados" in broker.filtros_ativos, 120), "servidor não assinou: " + "".join(saida)
        dispositivo = _cliente(broker, "dispositivo_simulado")
        decisoes = []
        ouvinte = _cliente(broker, "ouvinte")
        ouvinte.on_message = lambda c, u, m: decisoes.append(json.loads(m.payload))
        ouvinte.subscribe("anima/coleira-e2e/decisao")
        assert _esperar(lambda: "anima/coleira-e2e/decisao" in broker.filtros_ativos)

        def pub(p):
            dispositivo.publish("anima/coleira-e2e/dados", json.dumps(dict(p, id="coleira-e2e")))

        pub(payload_v2(38.3, "parado"))                       # normal, parado
        assert _esperar(lambda: len(decisoes) == 1)
        assert decisoes[0]["acao"] == "nenhum" and decisoes[0]["classe"] == "parado"

        pub(payload_v2(40.1, "parado"))                       # 1ª janela de febre: debounce
        assert _esperar(lambda: len(decisoes) == 2)
        assert decisoes[1]["acao"] == "nenhum" and decisoes[1]["classe"] == "febre"

        pub(payload_v2(40.1, "parado"))                       # 2ª janela consecutiva: alerta
        assert _esperar(lambda: len(decisoes) == 3)
        assert decisoes[2]["acao"] == "alerta"

        pub(payload_v2(-127.0, "parado"))                     # sensor desconectado: sem decisão
        pub(payload_v2(38.4, "normal"))
        assert _esperar(lambda: len(decisoes) == 4)
        assert decisoes[3]["acao"] == "nenhum" and decisoes[3]["classe"] == "normal"
        assert len(decisoes) == 4

        # log CSV com todas as janelas (incl. a descartada)
        assert _esperar(lambda: log.exists() and len(log.read_text(encoding="utf-8").splitlines()) >= 6)
        texto = log.read_text(encoding="utf-8")
        assert "descartada" in texto and "alerta" in texto
        dispositivo.loop_stop(); ouvinte.loop_stop()
    finally:
        proc.terminate()
        proc.wait(5)
        proc.stdout.close()


def test_coletor_grava_csv_compativel_com_dataset(broker, tmp_path):
    import pandas as pd
    from features_v2 import FEATURES
    saida = tmp_path / "sessao.csv"
    proc = subprocess.Popen(
        [sys.executable, str(SERVIDOR / "coletar_dados.py"), "--id", "coleira-e2e", "--rotulo", "normal",
         "--animal", "Rex", "--obs", "teste e2e", "--saida", str(saida), "--max-janelas", "3",
         "--descartar-iniciais", "1"],
        env=_env(broker, tmp_path), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    try:
        assert _esperar(lambda: "anima/coleira-e2e/dados" in broker.filtros_ativos, 120)
        disp = _cliente(broker, "disp2")
        for t in (38.5, 38.6, 38.4, 38.5, -127.0, 38.7, 38.5):
            disp.publish("anima/coleira-e2e/dados", json.dumps(payload_v2(t, "normal", id="coleira-e2e")))
            time.sleep(0.05)
        proc.wait(timeout=60)
        disp.loop_stop()
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.wait(10)
        proc.stdout.close()
    df = pd.read_csv(saida)
    assert len(df) == 3
    assert all(c in df.columns for c in FEATURES + ["classe", "timestamp"])
    assert set(df["classe"]) == {"normal"} and set(df["animal"]) == {"Rex"}
    assert (df["temperatura"] > 0).all()
