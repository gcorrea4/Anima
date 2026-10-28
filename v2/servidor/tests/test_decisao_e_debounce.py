import json

import anima_core as core
from conftest import ModeloFalso, payload_v2


# ---------------- regra de decisão ----------------
def test_alerta_para_febre_e_agitado_com_confianca():
    assert core.decidir_janela("febre", 0.9, 38.5, 0.6, 39.5)[0] == "alerta"
    assert core.decidir_janela("agitado", 0.61, 38.5, 0.6, 39.5)[0] == "alerta"


def test_sem_alerta_com_baixa_confianca_ou_classe_comum():
    assert core.decidir_janela("febre", 0.55, 38.5, 0.6, 39.5)[0] == "nenhum"
    assert core.decidir_janela("normal", 0.99, 38.5, 0.6, 39.5)[0] == "nenhum"
    assert core.decidir_janela("parado", 0.99, 38.3, 0.6, 39.5)[0] == "nenhum"


def test_regra_de_seguranca_por_temperatura_ignora_classe_e_confianca():
    acao, motivo = core.decidir_janela("parado", 0.99, 39.6, 0.6, 39.5)
    assert acao == "alerta" and "segurança" in motivo
    assert core.decidir_janela("normal", 0.3, 39.5, 0.6, 39.5)[0] == "alerta"   # igual ao limiar também alerta
    assert core.decidir_janela("normal", 0.3, 39.4, 0.6, 39.5)[0] == "nenhum"


# ---------------- debounce ----------------
def novo(n=2, intervalo=300, letargia=0):
    t = [0.0]
    return core.Debounce(n, intervalo, letargia, relogio=lambda: t[0]), t


def test_alerta_isolado_nao_dispara():
    d, _ = novo()
    assert d.processar("c", "alerta", "x").acao == "nenhum"
    assert d.processar("c", "nenhum", "ok").acao == "nenhum"
    r = d.processar("c", "alerta", "x")          # contagem recomeçou
    assert r.acao == "nenhum" and not r.notificar


def test_n_janelas_consecutivas_confirmam_e_notificam_uma_vez():
    d, _ = novo(n=3)
    assert [d.processar("c", "alerta", "x").acao for _ in range(2)] == ["nenhum", "nenhum"]
    r = d.processar("c", "alerta", "x")
    assert r.acao == "alerta" and r.notificar and r.confirmada
    r = d.processar("c", "alerta", "x")
    assert r.acao == "alerta" and not r.notificar        # mantém o alerta, sem repetir notificação


def test_intervalo_minimo_entre_notificacoes():
    d, t = novo(n=1, intervalo=300)
    assert d.processar("c", "alerta", "x").notificar
    t[0] = 299
    assert not d.processar("c", "alerta", "x").notificar
    t[0] = 300
    assert d.processar("c", "alerta", "x").notificar


def test_escalonamento_leve_para_alerta_notifica_na_hora():
    d, t = novo(n=1, intervalo=300)
    assert d.processar("c", "alerta_leve", "x").notificar
    t[0] = 10
    assert d.processar("c", "alerta", "x").notificar


def test_dispositivos_sao_independentes():
    d, _ = novo(n=2)
    d.processar("a", "alerta", "x")
    assert d.processar("b", "alerta", "x").acao == "nenhum"
    assert d.processar("a", "alerta", "x").acao == "alerta"


def test_letargia_por_imobilidade_prolongada_opcional():
    d, _ = novo(n=1, letargia=3)
    assert d.processar("c", "nenhum", "ok", "parado").acao == "nenhum"
    assert d.processar("c", "nenhum", "ok", "parado").acao == "nenhum"
    r = d.processar("c", "nenhum", "ok", "parado")
    assert r.acao == "alerta_leve" and "letargia" in r.motivo
    d2, _ = novo(n=1, letargia=0)
    assert all(d2.processar("c", "nenhum", "ok", "parado").acao == "nenhum" for _ in range(50))


# ---------------- pipeline completo com modelo falso ----------------
def test_pipeline_debounce_notificacao_e_log(tmp_path):
    enviados = []

    class N(core.Notificador):
        def enviar(self, texto, **_kw):
            enviados.append(texto)

    t = [0.0]
    pipe = core.Pipeline(ModeloFalso("febre", 0.9), core.Debounce(2, 300, relogio=lambda: t[0]), N(),
                         core.LogDecisoes(tmp_path / "l.csv"), relogio=lambda: t[0])
    d1 = pipe.processar("c1", payload_v2(40.0))
    d2 = pipe.processar("c1", payload_v2(40.0))
    assert d1["acao"] == "nenhum" and d2["acao"] == "alerta"
    assert len(enviados) == 1 and "c1" in enviados[0]
    assert len((tmp_path / "l.csv").read_text(encoding="utf-8").splitlines()) == 3


# ---------------- notificador ----------------
def test_notificador_sem_variaveis_so_imprime(capsys):
    chamadas = []
    n = core.Notificador(None, None, http_post=lambda *a, **k: chamadas.append(1))
    assert n.enviar("oi") is False and not chamadas
    assert "oi" in capsys.readouterr().out


def test_notificador_telegram_chama_api():
    visto = {}

    class R:
        status_code = 200

    def post(url, data, timeout):
        visto.update(url=url, data=data)
        return R()

    assert core.Notificador("TOK", "123", http_post=post).enviar("alerta!") is True
    assert visto["url"] == "https://api.telegram.org/botTOK/sendMessage"
    assert visto["data"] == {"chat_id": "123", "text": "alerta!"}


def test_notificador_nao_vaza_token_em_erro(capsys):
    def post(*a, **k):
        raise RuntimeError("falha em https://api.telegram.org/botSEGREDO/sendMessage")

    assert core.Notificador("SEGREDO", "1", http_post=post).enviar("x") is False
    assert "SEGREDO" not in capsys.readouterr().out.replace("[NOTIFICAÇÃO] x", "")


def test_config_mqtt_do_ambiente():
    cfg = core.config_mqtt({"ANIMA_MQTT_HOST": "b.exemplo", "ANIMA_MQTT_PORT": "8883",
                            "ANIMA_MQTT_USER": "u", "ANIMA_MQTT_PASS": "p", "ANIMA_MQTT_TLS": "1"})
    assert cfg == {"host": "b.exemplo", "porta": 8883, "usuario": "u", "senha": "p", "tls": True}
    assert core.config_mqtt({})["host"] == "broker.hivemq.com"


# ---------------- status do Telegram no log (sem expor o token) ----------------
def _resp(codigo, descricao=""):
    class R:
        status_code = codigo
        def json(self):
            return {"ok": False, "description": descricao}
    return R()


def test_notificador_status_em_cada_situacao():
    n = core.Notificador(None, None)
    n.enviar("x"); assert n.ultimo_status == "desativado"
    n = core.Notificador("TOKSECRETO", "1", http_post=lambda *a, **k: _resp(200))
    n.enviar("x"); assert n.ultimo_status == "enviado"
    n = core.Notificador("TOKSECRETO", "1", http_post=lambda *a, **k: _resp(401, "Unauthorized"))
    assert n.enviar("x") is False and n.ultimo_status == "erro: HTTP 401 Unauthorized"
    n = core.Notificador("TOKSECRETO", "1", http_post=lambda *a, **k: _resp(400, "Bad Request: chat not found"))
    n.enviar("x"); assert "chat not found" in n.ultimo_status

    def cai(*a, **k):
        raise ConnectionError("falha em https://api.telegram.org/botTOKSECRETO/sendMessage")
    n = core.Notificador("TOKSECRETO", "1", http_post=cai)
    assert n.enviar("x") is False
    assert n.ultimo_status == "erro: ConnectionError" and "TOKSECRETO" not in n.ultimo_status


def test_log_registra_erro_do_telegram_e_servidor_continua(tmp_path, capsys):
    n = core.Notificador("TOKSECRETO", "1", http_post=lambda *a, **k: _resp(401, "Unauthorized"))
    pipe = core.Pipeline(ModeloFalso("febre", 0.9), core.Debounce(1, 0), n, core.LogDecisoes(tmp_path / "l.csv"))
    d1 = pipe.processar("c1", payload_v2(40.0))
    d2 = pipe.processar("c1", payload_v2(38.5))      # continua classificando depois do erro
    assert d1["acao"] == "alerta" and d2 is not None
    texto = (tmp_path / "l.csv").read_text(encoding="utf-8")
    assert "erro: HTTP 401 Unauthorized" in texto and "TOKSECRETO" not in texto
    assert "TOKSECRETO" not in capsys.readouterr().out


def test_texto_da_notificacao_tem_todos_os_campos():
    t = core.texto_notificacao("coleira-x", "alerta", "febre", 0.93, 40.1, "motivo y", "2026-10-20 07:54:06")
    for trecho in ("coleira-x", "alerta", "febre", "93%", "40.1 °C", "motivo y", "2026-10-20 07:54:06"):
        assert trecho in t


def test_nomes_de_variavel_do_telegram():
    n = core.Notificador.do_ambiente({"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "9"})
    assert n.telegram_ativo
    assert core.Notificador.do_ambiente({"ANIMA_TELEGRAM_TOKEN": "t", "ANIMA_TELEGRAM_CHAT_ID": "9"}).telegram_ativo
    assert not core.Notificador.do_ambiente({}).telegram_ativo
