"""
Teste contra o broker PÚBLICO REAL (broker.hivemq.com:1883), só com dados sintéticos de teste.

* ID de dispositivo único e aleatório (anima-teste-xxxxxx); o servidor assina SOMENTE esse id (nunca o curinga anima/+/dados).
* O servidor conecta ao broker real passando por um proxy TCP local, que o script pode derrubar para testar a reconexão.
* Sem Telegram. Sem autenticação e sem TLS (o broker público é aberto: qualquer pessoa poderia ler/publicar nesses tópicos).

Uso:  python tests/teste_broker_publico.py        (sai com 1 se algo divergir)
"""
import csv
import json
import os
import secrets
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SERVIDOR = AQUI.parent
sys.path[:0] = [str(AQUI), str(SERVIDOR), str(SERVIDOR.parent / "ia")]
from cenarios_e2e import ROTEIRO  # noqa: E402  (mesmos cenários do teste local)
from conftest import payload_v2  # noqa: E402

BROKER, PORTA = "broker.hivemq.com", 1883
ID = "anima-teste-" + secrets.token_hex(3)


class ProxyTCP:
    """Repassa TCP para o broker real; cortar() derruba todas as conexões ativas (simula queda de rede)."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.porta = self.srv.getsockname()[1]
        self.pares = []
        self.conexoes = 0
        threading.Thread(target=self._aceitar, daemon=True).start()

    def _aceitar(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            try:
                s = socket.create_connection((BROKER, PORTA), timeout=10)
            except OSError:
                c.close()
                continue
            self.conexoes += 1
            self.pares.append((c, s))
            for a, b in ((c, s), (s, c)):
                threading.Thread(target=self._copiar, args=(a, b), daemon=True).start()

    @staticmethod
    def _copiar(a, b):
        try:
            while (d := a.recv(4096)):
                b.sendall(d)
        except OSError:
            pass
        for x in (a, b):
            try:
                x.close()
            except OSError:
                pass

    def cortar(self):
        for c, s in self.pares:
            for x in (c, s):
                try:
                    x.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                x.close()
        self.pares.clear()


def cliente(nome):
    import paho.mqtt.client as mqtt
    v = getattr(mqtt, "CallbackAPIVersion", None)
    c = mqtt.Client(v.VERSION2, client_id=f"{nome}-{secrets.token_hex(3)}") if v else mqtt.Client(client_id=nome)
    c.connect(BROKER, PORTA, keepalive=30)
    c.loop_start()
    return c


def esperar(cond, t=30):
    fim = time.time() + t
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.02)
    return False


def main():
    print(f"Broker: {BROKER}:{PORTA} (PÚBLICO, sem auth, sem TLS) | id de teste: {ID}")
    proxy = ProxyTCP()
    tmp = Path(tempfile.mkdtemp(prefix="anima_pub_"))
    log = tmp / "decisoes.csv"
    env = dict(os.environ, ANIMA_MQTT_HOST="127.0.0.1", ANIMA_MQTT_PORT=str(proxy.porta),
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    for k in ("ANIMA_MQTT_USER", "ANIMA_MQTT_PASS", "ANIMA_MQTT_TLS", "ANIMA_TELEGRAM_TOKEN", "ANIMA_TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    env["ANIMA_SEM_DOTENV"] = "1"   # não carregar o .env real (evita mandar mensagens de teste ao Telegram)
    proc = subprocess.Popen([sys.executable, str(SERVIDOR / "consumidor_v2.py"), "--id", ID, "--log", str(log),
                             "--intervalo-notif", "3"], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    saida = []
    threading.Thread(target=lambda: [saida.append(l) for l in proc.stdout], daemon=True).start()
    conta = lambda trecho: sum(trecho in l for l in saida)

    linhas, lat, falhas = [], [], 0
    t_publica = {}
    try:
        assert esperar(lambda: conta("Assinando") >= 1, 120), "servidor não conectou: " + "".join(saida[-5:])
        disp, ouv = cliente("disp"), cliente("ouv")
        decisoes = []
        ouv.on_message = lambda c, u, m: decisoes.append((time.time(), m.topic, json.loads(m.payload)))
        ouv.subscribe(f"anima/{ID}/decisao", qos=1)
        time.sleep(2.0)   # dá tempo ao SUBACK/assinatura do servidor no broker real

        for nome, payload, cls_esp, acao_esp in ROTEIRO:
            n0 = len(decisoes)
            t0 = time.time()
            disp.publish(f"anima/{ID}/dados", json.dumps(dict(payload, id=ID)), qos=1)
            if cls_esp is None:
                time.sleep(2.0)
                ok = len(decisoes) == n0
                linhas.append((nome, "(sem decisão)", "(sem decisão)" if ok else "publicou decisão", "-", ok))
            else:
                got = esperar(lambda: len(decisoes) > n0, 10)
                if got:
                    t1, topico, d = decisoes[n0]
                    ms = (t1 - t0) * 1000
                    lat.append(ms)
                    ok = d["classe"] == cls_esp and d["acao"] == acao_esp and topico == f"anima/{ID}/decisao"
                    linhas.append((nome, f"{cls_esp}/{acao_esp}", f"{d['classe']}/{d['acao']} ({d['confianca']})", f"{ms:.0f} ms", ok))
                else:
                    ok = False
                    linhas.append((nome, f"{cls_esp}/{acao_esp}", "TIMEOUT sem decisão", "-", False))
            falhas += not ok

        # intervalo mínimo (3 s): espera o intervalo vencer, 1ª janela notifica, 2ª imediata não, 3ª após 3,2 s notifica
        pub = lambda: disp.publish(f"anima/{ID}/dados", json.dumps(payload_v2(40.1, "parado", id=ID)), qos=1)
        time.sleep(3.2)
        base = conta("[NOTIFICAÇÃO]")
        pub(); time.sleep(1.0)
        n_primeira = conta("[NOTIFICAÇÃO]") - base
        pub(); time.sleep(1.0)
        n_dentro = conta("[NOTIFICAÇÃO]") - base - n_primeira
        time.sleep(3.2)
        pub(); time.sleep(1.0)
        n_apos = conta("[NOTIFICAÇÃO]") - base - n_primeira - n_dentro
        for nome, esp, obt in (("alerta, intervalo vencido: notifica", "1 notificação", n_primeira),
                               ("alerta repetido dentro de 3 s: não notifica", "0 notificações", n_dentro),
                               ("alerta após 3,2 s: notifica de novo", "1 notificação", n_apos)):
            ok = str(obt) == esp.split()[0]
            linhas.append((nome, esp, str(obt), "-", ok))
            falhas += not ok

        # ---- reconexão: derruba a conexão TCP do servidor ----
        conexoes_antes = proxy.conexoes
        conectados_antes = conta("Conectado a")
        t_corte = time.time()
        proxy.cortar()
        ok_rec = esperar(lambda: conta("Conectado a") > conectados_antes, 60)
        t_rec = time.time() - t_corte
        linhas.append(("RECONEXÃO: servidor reconecta após queda", "reconecta", f"{'reconectou' if ok_rec else 'NÃO reconectou'}", f"{t_rec:.1f} s", ok_rec))
        falhas += not ok_rec
        if ok_rec:
            time.sleep(2.0)
            n0 = len(decisoes)
            t0 = time.time()
            disp.publish(f"anima/{ID}/dados", json.dumps(payload_v2(38.5, "normal", id=ID)), qos=1)
            got = esperar(lambda: len(decisoes) > n0, 10)
            d = decisoes[n0][2] if got else {}
            ok = got and d.get("classe") == "normal" and d.get("acao") == "nenhum"
            linhas.append(("RECONEXÃO: volta a processar", "normal/nenhum", f"{d.get('classe')}/{d.get('acao')}" if got else "TIMEOUT",
                           f"{(decisoes[n0][0] - t0) * 1000:.0f} ms" if got else "-", ok))
            falhas += not ok

        # ---- log CSV ----
        time.sleep(0.5)
        with open(log, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        descartadas = sum(r["acao_bruta"] == "descartada" for r in rows)
        finais = [r["acao_final"] for r in rows if r["acao_bruta"] != "descartada"]
        okl = descartadas == 3 and all(r["dispositivo"] == ID for r in rows) and finais.count("alerta") >= 4
        linhas.append(("log CSV: linhas / descartadas / dispositivo", "≥17 / 3 / id de teste",
                       f"{len(rows)} / {descartadas} / {'ok' if all(r['dispositivo'] == ID for r in rows) else 'ERRADO'}", "-", okl))
        falhas += not okl
        disp.loop_stop(); ouv.loop_stop()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        proc.stdout.close()

    print(f"\n{'Cenário':46s} | {'Esperado':22s} | {'Obtido':32s} | {'Latência':9s} | OK")
    print("-" * 130)
    for n, e, o, ms, ok in linhas:
        print(f"{n:46s} | {e:22s} | {o:32s} | {ms:9s} | {'sim' if ok else 'NÃO'}")
    if lat:
        print(f"\nLatência ida e volta (dispositivo→broker real→servidor→broker real→ouvinte), n={len(lat)}: "
              f"mín {min(lat):.0f} ms | mediana {statistics.median(lat):.0f} ms | máx {max(lat):.0f} ms")
    print(f"Conexões TCP do servidor ao broker (via proxy): {proxy.conexoes}")
    print(f"Log CSV: {log}")
    print(f"{len(linhas) - falhas}/{len(linhas)} verificações ok")
    if falhas:
        print("--- últimas linhas do servidor ---\n" + "".join(saida[-12:]))
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
