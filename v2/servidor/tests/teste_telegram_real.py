"""
Envio REAL ao Telegram (usa v2/servidor/.env) com mini-broker local e dispositivo simulado.

* O servidor roda como processo real e carrega o .env sozinho. Este script nunca imprime o token
  (toda saída do servidor passa por um filtro que o mascara).
* Sequência: parado+febre (x2) -> normal -> agitado (x2) -> normal -> febre com movimento (x2).
  Com --intervalo-notif 0 cada episódio gera uma notificação (3 no total).
* Modos de falha (--falha): token_invalido | chat_errado | sem_internet. Em cada um o servidor deve continuar
  classificando e registrar o erro (sem o token) na coluna 'telegram' do log CSV.

Uso:  python tests/teste_telegram_real.py [--falha token_invalido|chat_errado|sem_internet]
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SERVIDOR = AQUI.parent
sys.path[:0] = [str(AQUI), str(SERVIDOR), str(SERVIDOR.parent / "ia")]
from conftest import payload_v2  # noqa: E402
from mini_broker import MiniBroker  # noqa: E402

ID = "anima-telegram-teste"
SEQ = [("parado+febre 40,1 °C (1ª)", payload_v2(40.1, "parado")), ("parado+febre 40,1 °C (2ª)", payload_v2(40.1, "parado")),
       ("normal 38,5 °C", payload_v2(38.5, "normal")),
       ("agitado 38,8 °C (1ª)", payload_v2(38.8, "agitado")), ("agitado 38,8 °C (2ª)", payload_v2(38.8, "agitado")),
       ("normal 38,5 °C", payload_v2(38.5, "normal")),
       ("febre c/ movimento 40,0 °C (1ª)", payload_v2(40.0, "normal")), ("febre c/ movimento 40,0 °C (2ª)", payload_v2(40.0, "normal"))]


def ler_segredos():
    d = {}
    f = SERVIDOR / ".env"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if "=" in l and not l.startswith("#"):
                k, v = l.split("=", 1)
                d[k.strip()] = v.strip()
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--falha", choices=["token_invalido", "chat_errado", "sem_internet"])
    args = ap.parse_args()
    seg = ler_segredos()
    token, chat = seg.get("TELEGRAM_BOT_TOKEN", ""), seg.get("TELEGRAM_CHAT_ID", "")
    mascara = lambda t: t.replace(token, "***TOKEN***") if token else t

    broker = MiniBroker().start()
    log = Path(tempfile.mkdtemp(prefix="anima_tg_")) / "decisoes.csv"
    env = dict(os.environ, ANIMA_MQTT_HOST="127.0.0.1", ANIMA_MQTT_PORT=str(broker.port),
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    # variáveis de falha sobrescrevem o .env (carregar_env usa setdefault)
    if args.falha == "token_invalido":
        env["TELEGRAM_BOT_TOKEN"] = "123456789:" + "A" * 35
    elif args.falha == "chat_errado":
        env["TELEGRAM_CHAT_ID"] = "111111111"
    elif args.falha == "sem_internet":
        # proxy HTTPS inexistente derruba toda chamada externa do requests (o MQTT local não usa HTTP)
        env.update(HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9", NO_PROXY="")
    proc = subprocess.Popen([sys.executable, str(SERVIDOR / "consumidor_v2.py"), "--id", ID, "--log", str(log),
                             "--intervalo-notif", "0"], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    saida = []
    threading.Thread(target=lambda: [saida.append(mascara(l)) for l in proc.stdout], daemon=True).start()
    try:
        import paho.mqtt.client as mqtt
        fim = time.time() + 120
        while f"anima/{ID}/dados" not in broker.filtros_ativos and time.time() < fim:
            time.sleep(0.1)
        assert f"anima/{ID}/dados" in broker.filtros_ativos, "servidor não assinou:\n" + "".join(saida[-6:])
        v = getattr(mqtt, "CallbackAPIVersion", None)
        disp = mqtt.Client(v.VERSION2, client_id="disp-tg") if v else mqtt.Client(client_id="disp-tg")
        disp.connect("127.0.0.1", broker.port); disp.loop_start()
        decisoes = []
        ouv = mqtt.Client(v.VERSION2, client_id="ouv-tg") if v else mqtt.Client(client_id="ouv-tg")
        ouv.on_message = lambda c, u, m: decisoes.append(json.loads(m.payload))
        ouv.connect("127.0.0.1", broker.port); ouv.loop_start(); ouv.subscribe(f"anima/{ID}/decisao")
        time.sleep(0.5)
        for nome, p in SEQ:
            n0 = len(decisoes)
            disp.publish(f"anima/{ID}/dados", json.dumps(dict(p, id=ID)))
            fim = time.time() + 40   # a chamada ao Telegram pode levar alguns segundos
            while len(decisoes) == n0 and time.time() < fim:
                time.sleep(0.05)
        disp.loop_stop(); ouv.loop_stop()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        broker.stop()

    texto = "".join(saida)
    print(f"Modo: {args.falha or 'REAL (token e chat do .env)'}")
    print(f"Decisões publicadas pelo servidor: {len(decisoes)}/{len(SEQ)} -> {[d['acao'] for d in decisoes]}")
    with open(log, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print("\nLog CSV (classe | acao_final | notificou | telegram):")
    for r in rows:
        print(f"  {r['classe']:9s} | {r['acao_final']:7s} | {r['notificou']} | {r['telegram']}")
    print("\nMensagens de notificação como saíram do servidor:")
    for bloco in re.findall(r"\[NOTIFICAÇÃO\] (.*?)(?=\n\[20|\n  \(|\Z)", texto, flags=re.S):
        print("  ---\n  " + bloco.strip().replace("\n", "\n  "))
    erros = [l.strip() for l in saida if l.strip().startswith("(")]
    if erros:
        print("\nErros de Telegram vistos no terminal:", *erros, sep="\n  ")
    vazou = bool(token) and token in "".join(saida) + log.read_text(encoding="utf-8")
    print("\nToken presente na saída/log do servidor:", "SIM (FALHA!)" if vazou else "não")
    ok = len(decisoes) == len(SEQ) and not vazou
    print("RESULTADO:", "servidor classificou todas as janelas" if ok else "PROBLEMA")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
