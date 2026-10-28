"""Encerramento limpo do consumidor_v2 (Ctrl+C simulado com _thread.interrupt_main num processo filho)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from features_v2 import MODELO_PADRAO
from mini_broker import MiniBroker

SERVIDOR = Path(__file__).resolve().parents[1]

CODIGO = r"""
import sys, threading, _thread
sys.path[:0] = [r"{servidor}", r"{ia}"]
import consumidor_v2 as c
args = c.criar_parser().parse_args(["--id", "coleira-enc", "--log", r"{log}"])
modelo = c.carregar_modelo(args.modelo)
threading.Timer(4.0, _thread.interrupt_main).start()    # "Ctrl+C" depois de 4 s
c.executar(args, modelo, 39.5)
"""


@pytest.mark.skipif(not MODELO_PADRAO.exists(), reason="modelo v2 ausente")
def test_ctrl_c_encerra_limpo(tmp_path):
    broker = MiniBroker().start()
    env = dict(os.environ, ANIMA_MQTT_HOST="127.0.0.1", ANIMA_MQTT_PORT=str(broker.port), PYTHONIOENCODING="utf-8")
    for k in ("ANIMA_MQTT_USER", "ANIMA_MQTT_PASS", "ANIMA_MQTT_TLS", "ANIMA_TELEGRAM_TOKEN", "ANIMA_TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    env["ANIMA_SEM_DOTENV"] = "1"   # não carregar o .env real (evita mandar mensagens de teste ao Telegram)
    codigo = CODIGO.format(servidor=SERVIDOR, ia=SERVIDOR.parent / "ia", log=tmp_path / "l.csv")
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, "-c", codigo], env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
    finally:
        broker.stop()
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Encerrando..." in r.stdout and "Encerrado. Telegram:" in r.stdout
    assert "Traceback" not in r.stderr
