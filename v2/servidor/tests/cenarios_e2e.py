"""
Roteiro ponta a ponta (script, não pytest): mini-broker local + consumidor_v2.py real + dispositivo
SIMULADO em Python publicando payloads v2 (não é o firmware). Imprime a tabela cenário → esperado → obtido.

Uso:  python tests/cenarios_e2e.py
Sai com código 1 se algum cenário divergir.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SERVIDOR = AQUI.parent
sys.path[:0] = [str(AQUI), str(SERVIDOR), str(SERVIDOR.parent / "ia")]
from conftest import payload_v2  # noqa: E402
from mini_broker import MiniBroker  # noqa: E402

ID = "coleira-sim"
# (nome, payload ou None p/ pausa, classe esperada, ação esperada, observação)
ROTEIRO = [
    ("parado 38,3 °C", payload_v2(38.3, "parado"), "parado", "nenhum"),
    ("normal 38,5 °C", payload_v2(38.5, "normal"), "normal", "nenhum"),
    ("agitado 38,8 °C (1ª janela)", payload_v2(38.8, "agitado"), "agitado", "nenhum"),
    ("agitado 38,8 °C (2ª consecutiva)", payload_v2(38.8, "agitado"), "agitado", "alerta"),
    ("normal 38,5 °C (volta ao normal)", payload_v2(38.5, "normal"), "normal", "nenhum"),
    ("febre c/ movimento 40,0 °C (1ª)", payload_v2(40.0, "normal"), "febre", "nenhum"),
    ("febre c/ movimento 40,0 °C (2ª)", payload_v2(40.0, "normal"), "febre", "alerta"),
    ("normal 38,5 °C (reseta)", payload_v2(38.5, "normal"), "normal", "nenhum"),
    ("PARADO + FEBRE 40,1 °C (1ª)", payload_v2(40.1, "parado"), "febre", "nenhum"),
    ("PARADO + FEBRE 40,1 °C (2ª)", payload_v2(40.1, "parado"), "febre", "alerta"),
    ("PARADO + FEBRE 40,1 °C (3ª, mantém)", payload_v2(40.1, "parado"), "febre", "alerta"),
    ("DS18B20 = -127 (descartada)", payload_v2(-127.0, "parado"), None, None),
    ("sensor_ok=false (descartada)", payload_v2(None, "parado", sensor_ok=False), None, None),
    ("mpu_ok=false (descartada)", {"versao": 2, "id": ID, "n_amostras": 0, "temperatura": 38.4,
                                   "sensor_ok": True, "mpu_ok": False}, None, None),
]


def cliente(broker, nome):
    import paho.mqtt.client as mqtt
    v = getattr(mqtt, "CallbackAPIVersion", None)
    c = mqtt.Client(v.VERSION2, client_id=nome) if v else mqtt.Client(client_id=nome)
    c.connect("127.0.0.1", broker.port)
    c.loop_start()
    return c


def esperar(cond, t=30):
    fim = time.time() + t
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.03)
    return False


def main():
    broker = MiniBroker().start()
    tmp = Path(tempfile.mkdtemp(prefix="anima_e2e_"))
    log = tmp / "decisoes.csv"
    env = dict(os.environ, ANIMA_MQTT_HOST="127.0.0.1", ANIMA_MQTT_PORT=str(broker.port),
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    for k in ("ANIMA_MQTT_USER", "ANIMA_MQTT_PASS", "ANIMA_MQTT_TLS", "ANIMA_TELEGRAM_TOKEN", "ANIMA_TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    env["ANIMA_SEM_DOTENV"] = "1"   # não carregar o .env real (evita mandar mensagens de teste ao Telegram)
    # intervalo de notificação curto (3 s) para exercitar o "intervalo mínimo" em tempo real
    proc = subprocess.Popen([sys.executable, str(SERVIDOR / "consumidor_v2.py"), "--id", ID, "--log", str(log),
                             "--intervalo-notif", "3"], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    saida = []
    import threading
    threading.Thread(target=lambda: [saida.append(l) for l in proc.stdout], daemon=True).start()
    falhas = 0
    linhas = []
    try:
        assert esperar(lambda: f"anima/{ID}/dados" in broker.filtros_ativos, 120), "servidor não assinou"
        disp, ouv = cliente(broker, "disp"), cliente(broker, "ouv")
        decisoes = []
        ouv.on_message = lambda c, u, m: decisoes.append((m.topic, json.loads(m.payload)))
        ouv.subscribe(f"anima/{ID}/decisao")
        assert esperar(lambda: f"anima/{ID}/decisao" in broker.filtros_ativos)

        for nome, payload, cls_esp, acao_esp in ROTEIRO:
            n0 = len(decisoes)
            disp.publish(f"anima/{ID}/dados", json.dumps(dict(payload, id=ID)))
            if cls_esp is None:   # esperado: NENHUMA decisão publicada
                time.sleep(0.4)
                ok = len(decisoes) == n0
                linhas.append((nome, "(sem decisão)", "(sem decisão)" if ok else f"publicou {decisoes[-1][1]}", ok))
            else:
                got = esperar(lambda: len(decisoes) > n0, 5)
                d = decisoes[-1][1] if got else {}
                ok = got and d.get("classe") == cls_esp and d.get("acao") == acao_esp \
                    and decisoes[-1][0] == f"anima/{ID}/decisao"
                linhas.append((nome, f"{cls_esp}/{acao_esp}", f"{d.get('classe')}/{d.get('acao')} ({d.get('confianca')})", ok))
            falhas += 0 if ok else 1

        # intervalo mínimo: com --intervalo-notif 3, contamos notificações no stdout do servidor
        time.sleep(0.3)
        notifs_antes = sum("[NOTIFICAÇÃO]" in l for l in saida)
        disp.publish(f"anima/{ID}/dados", json.dumps(payload_v2(40.1, "parado", id=ID)))
        time.sleep(0.5)
        notifs_sem_espera = sum("[NOTIFICAÇÃO]" in l for l in saida) - notifs_antes
        time.sleep(3.2)
        disp.publish(f"anima/{ID}/dados", json.dumps(payload_v2(40.1, "parado", id=ID)))
        time.sleep(0.5)
        notifs_depois = sum("[NOTIFICAÇÃO]" in l for l in saida) - notifs_antes - notifs_sem_espera
        ok1 = notifs_sem_espera == 0
        ok2 = notifs_depois == 1
        linhas.append(("alerta mantido dentro do intervalo (3 s)", "0 notificações", f"{notifs_sem_espera}", ok1))
        linhas.append(("alerta mantido após o intervalo (3 s)", "1 notificação", f"{notifs_depois}", ok2))
        falhas += (not ok1) + (not ok2)
        total_notifs = sum("[NOTIFICAÇÃO]" in l for l in saida)

        # log CSV
        import csv
        time.sleep(0.3)
        with open(log, encoding="utf-8") as f:
            linhas_log = list(csv.DictReader(f))
        descartadas = sum(r["acao_bruta"] == "descartada" for r in linhas_log)
        notificou = sum(int(r["notificou"] or 0) for r in linhas_log)
        okl = descartadas == 3 and notificou == total_notifs == 3
        linhas.append(("log CSV: descartadas / notificações", "3 / 3*", f"{descartadas} / {notificou} (stdout: {total_notifs})", okl))
        falhas += not okl
        disp.loop_stop(); ouv.loop_stop()
    finally:
        proc.terminate()
        proc.wait(5)
        proc.stdout.close()
        broker.stop()

    print(f"{'Cenário':44s} | {'Esperado':22s} | {'Obtido':44s} | OK")
    print("-" * 125)
    for n, e, o, ok in linhas:
        print(f"{n:44s} | {e:22s} | {o:44s} | {'sim' if ok else 'NÃO'}")
    print("* 3 notificações: agitado, febre (outra CAUSA: notifica na hora) e a do fim, após o intervalo. O parado+febre logo depois\n"
          "  da febre (mesma causa, dentro de 3 s) foi suprimido: o intervalo vale por (dispositivo, causa, ação).")
    print(f"\nLog CSV: {log}")
    print(f"{len(linhas) - falhas}/{len(linhas)} verificações ok")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
