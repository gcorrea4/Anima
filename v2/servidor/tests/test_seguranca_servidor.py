"""Segurança do servidor: --id/--todos, broker público, id do payload, limite de dispositivos e estado limitado."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import anima_core as core
from conftest import payload_v2
from features_v2 import MODELO_PADRAO
from mini_broker import MiniBroker

SERVIDOR = Path(__file__).resolve().parents[1]
PUBLICO = "broker.hivemq.com"
LOCAL = "127.0.0.1"


# ---------------------------------------------------------------- modo de assinatura
def test_sem_id_e_sem_todos_nao_inicia():
    erro = core.validar_modo_assinatura(None, False, False, LOCAL)
    assert erro and "--id" in erro
    assert core.validar_modo_assinatura(None, False, False, PUBLICO)


def test_id_e_todos_juntos_sao_recusados():
    assert "OU" in core.validar_modo_assinatura("a", True, False, LOCAL)


def test_todos_em_broker_publico_exige_confirmacao_explicita():
    erro = core.validar_modo_assinatura(None, True, False, PUBLICO)
    assert erro and "--aceito-risco-publico" in erro and "TERCEIROS" in erro
    assert core.validar_modo_assinatura(None, True, True, PUBLICO) is None          # com a confirmação, passa
    for host in ("test.mosquitto.org", "broker.emqx.io", "BROKER.HIVEMQ.COM "):    # outros públicos / caixa / espaço
        assert core.validar_modo_assinatura(None, True, False, host)


def test_todos_em_broker_local_e_id_em_qualquer_broker_sao_permitidos():
    assert core.validar_modo_assinatura(None, True, False, LOCAL) is None
    assert core.validar_modo_assinatura("anima-teste-1", False, False, PUBLICO) is None   # --id no público: só avisa
    assert core.validar_modo_assinatura("id inválido!", False, False, LOCAL)


def test_cli_sem_id_recusa_com_codigo_2():
    env = dict(os.environ, ANIMA_SEM_DOTENV="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, str(SERVIDOR / "consumidor_v2.py")], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 2 and "informe --id" in r.stderr
    env["ANIMA_MQTT_HOST"] = PUBLICO
    r = subprocess.run([sys.executable, str(SERVIDOR / "consumidor_v2.py"), "--todos"], env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 2 and "--aceito-risco-publico" in r.stderr


def test_aviso_de_broker_publico(capsys):
    core.aviso_broker_publico({"host": PUBLICO})
    assert "PÚBLICO" in capsys.readouterr().out
    core.aviso_broker_publico({"host": LOCAL})
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------- id do payload x id do tópico
def test_payload_com_id_diferente_do_topico_e_ignorado():
    ok = core.validar_payload(payload_v2(38.5, "normal", id="c1"), id_topico="c1")
    assert "temperatura" in ok
    with pytest.raises(core.PayloadDescartado, match="difere do id do tópico"):
        core.validar_payload(payload_v2(38.5, "normal", id="outro"), id_topico="c1")


def test_payload_sem_id_e_recusado_quando_o_id_e_exigido():
    p = payload_v2(38.5, "normal")
    del p["id"]
    with pytest.raises(core.PayloadDescartado):
        core.validar_payload(p, id_topico="c1")
    core.validar_payload(p)           # sem exigência (uso interno/testes unitários): aceito


def test_id_gigante_ou_estranho_no_payload_nao_estoura_a_mensagem():
    with pytest.raises(core.PayloadDescartado) as e:
        core.validar_payload(payload_v2(38.5, "normal", id="x" * 5000), id_topico="c1")
    assert len(str(e.value)) < 200


def test_pipeline_estrito_descarta_e_registra(tmp_path):
    from conftest import ModeloFalso
    log = core.LogDecisoes(tmp_path / "l.csv")
    pipe = core.Pipeline(ModeloFalso("febre", 0.9), log=log, exigir_id=True)
    assert pipe.processar("c1", payload_v2(40.1, id="forjado")) is None
    assert pipe.processar("c1", payload_v2(40.1, id="c1")) is not None
    linhas = (tmp_path / "l.csv").read_text(encoding="utf-8")
    assert "descartada" in linhas and "difere do id do tópico" in linhas


# ---------------------------------------------------------------- limites de dispositivos e de estado
def test_controle_limita_dispositivos_distintos():
    c = core.ControleDispositivos(maximo=2)
    assert c.aceita("a") and c.aceita("b") and c.aceita("a")
    assert not c.aceita("c") and not c.aceita("d")
    assert c.aceita("b") and c.ignorados == 2


def test_controle_modo_id_so_aceita_o_proprio_id():
    c = core.ControleDispositivos(maximo=5, permitido="meu-id")
    assert c.aceita("meu-id") and not c.aceita("alheio")


def test_debounce_descarta_o_estado_mais_antigo():
    t = [0.0]
    d = core.Debounce(1, 300, relogio=lambda: t[0], max_estados=3)
    for i in range(5):
        d.processar(f"disp{i}", "alerta", "x", "febre", causa="temperatura_alta")
    assert list(d._est) == ["disp2", "disp3", "disp4"]                  # os 2 mais antigos saíram
    d.processar("disp2", "alerta", "x", "febre", causa="temperatura_alta")   # uso recente protege da remoção
    d.processar("disp9", "alerta", "x", "febre", causa="temperatura_alta")
    assert "disp2" in d._est and "disp3" not in d._est


def test_debounce_limita_relogios_por_dispositivo():
    t = [0.0]
    d = core.Debounce(1, 0, relogio=lambda: t[0])
    for i in range(core.MAX_CHAVES_NOTIF + 10):
        d.processar("c", "alerta", "x", f"classe{i}", causa=f"causa{i}")
    assert len(d._est["c"].ultima_notif) == core.MAX_CHAVES_NOTIF


# ---------------------------------------------------------------- ponta a ponta (mini-broker local)
@pytest.mark.skipif(not MODELO_PADRAO.exists(), reason="modelo v2 ausente")
def test_e2e_todos_com_limite_e_id_forjado(tmp_path):
    import paho.mqtt.client as mqtt
    broker = MiniBroker().start()
    env = dict(os.environ, ANIMA_MQTT_HOST=LOCAL, ANIMA_MQTT_PORT=str(broker.port), PYTHONIOENCODING="utf-8",
               PYTHONUNBUFFERED="1", ANIMA_SEM_DOTENV="1")
    for k in ("ANIMA_MQTT_USER", "ANIMA_MQTT_PASS", "ANIMA_MQTT_TLS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, str(SERVIDOR / "consumidor_v2.py"), "--todos", "--max-dispositivos", "2",
                             "--log", str(tmp_path / "l.csv")], env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    saida = []
    leitor = threading.Thread(target=lambda: [saida.append(l) for l in proc.stdout], daemon=True)
    leitor.start()

    def cliente(nome):
        v = getattr(mqtt, "CallbackAPIVersion", None)
        c = mqtt.Client(v.VERSION2, client_id=nome) if v else mqtt.Client(client_id=nome)
        c.connect(LOCAL, broker.port)
        c.loop_start()
        return c

    def esperar(cond, t=120):
        fim = time.time() + t
        while time.time() < fim:
            if cond():
                return True
            time.sleep(0.05)
        return False

    try:
        assert esperar(lambda: "anima/+/dados" in broker.filtros_ativos), "".join(saida)
        disp, ouv = cliente("d"), cliente("o")
        decisoes = []
        ouv.on_message = lambda c, u, m: decisoes.append(m.topic)
        ouv.subscribe("anima/+/decisao")
        assert esperar(lambda: "anima/+/decisao" in broker.filtros_ativos)

        def pub(topico_id, payload_id):
            n = len(decisoes)
            disp.publish(f"anima/{topico_id}/dados", json.dumps(payload_v2(38.5, "normal", id=payload_id)))
            return esperar(lambda: len(decisoes) > n, 3)

        assert pub("a", "a"), "1º dispositivo deveria ser atendido"
        assert pub("b", "b"), "2º dispositivo deveria ser atendido"
        assert not pub("c", "c"), "3º dispositivo está além do limite (2): deve ser ignorado"
        assert not pub("a", "forjado"), "id do payload diferente do tópico: deve ser ignorado"
        assert pub("a", "a"), "o dispositivo já aceito continua sendo atendido"
        assert "anima/c/decisao" not in decisoes and decisoes.count("anima/a/decisao") == 2
        assert esperar(lambda: any("limite de 2 dispositivos" in l for l in saida), 5)
        disp.loop_stop(); ouv.loop_stop()
    finally:
        proc.terminate()
        proc.wait(10)
        proc.stdout.close()
        leitor.join(2)
        broker.stop()
