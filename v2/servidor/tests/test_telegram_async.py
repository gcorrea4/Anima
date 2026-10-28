"""Telegram em segundo plano, regra de intervalo por causa, alerta_leve e padrão real de 300 s. Sem rede."""
import csv
import threading
import time

import anima_core as core
from conftest import ModeloFalso, payload_v2

TOKEN = "123456:TOKEN-SECRETO-DE-TESTE"


class Resp:
    def __init__(self, code=200, desc=""):
        self.status_code, self._d = code, desc

    def json(self):
        return {"description": self._d}


class PostControlado:
    """http_post falso: bloqueia até liberar() (simula Telegram lento) e guarda o que foi enviado."""

    def __init__(self, atraso_max=8.0, resposta=None, erro=None):
        self.liberado = threading.Event()
        self.atraso_max, self.resposta, self.erro = atraso_max, resposta or Resp(), erro
        self.textos, self.iniciou = [], threading.Event()

    def __call__(self, url, data, timeout):
        self.iniciou.set()
        self.liberado.wait(self.atraso_max)    # "8 s de atraso", mas o teste libera antes
        if self.erro:
            raise self.erro
        self.textos.append(data["text"])
        return self.resposta

    def liberar(self):
        self.liberado.set()


def novo_async(post, tmp_path, fila=20):
    log = core.LogDecisoes(tmp_path / "log.csv")
    nota = core.Notificador(TOKEN, "42", http_post=post)
    return core.NotificadorAssincrono(nota, log, tamanho_fila=fila), log


def linhas_log(tmp_path):
    with open(tmp_path / "log.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def envios(tmp_path):
    return [r["telegram"] for r in linhas_log(tmp_path) if r["acao_bruta"] == "envio_telegram"]


def pipeline(tmp_path, post, classe="febre", fila=20, **kw):
    n, log = novo_async(post, tmp_path, fila)
    t = [0.0]
    deb = kw.pop("debounce", None) or core.Debounce(1, 300, relogio=lambda: t[0])
    pipe = core.Pipeline(ModeloFalso(classe, 0.9), deb, n, log, relogio=lambda: t[0], **kw)
    return pipe, n, t


# ---------------------------------------------------------------- Telegram lento
def test_telegram_lento_nao_atrasa_a_decisao(tmp_path, capsys):
    post = PostControlado()                                   # trava como um Telegram de 8 s
    pipe, n, t = pipeline(tmp_path, post, debounce=core.Debounce(1, 0, relogio=lambda: 0.0))
    inicio = time.time()
    decisoes = [pipe.processar("c1", payload_v2(40.1)) for _ in range(6)]   # 6 alertas, intervalo 0 => 6 notificações
    gasto = time.time() - inicio
    assert all(d["acao"] == "alerta" for d in decisoes)       # decisões publicáveis na hora
    assert gasto < 1.5, f"decisões esperaram o Telegram ({gasto:.1f} s)"
    assert post.iniciou.wait(2)                               # a thread já está presa no 1º envio
    post.liberar()
    n.encerrar(5)
    assert n.enviados == 6 and len(post.textos) == 6
    assert envios(tmp_path).count("enviado") == 6


# ---------------------------------------------------------------- erros (sem expor o token)
def test_telegram_com_erro_registra_e_nao_vaza_token(tmp_path, capsys):
    post = PostControlado(erro=RuntimeError(f"falha em https://api.telegram.org/bot{TOKEN}/sendMessage"))
    post.liberar()
    pipe, n, _ = pipeline(tmp_path, post)
    d = pipe.processar("c1", payload_v2(40.1))
    assert d["acao"] == "alerta"
    n.encerrar(5)
    assert envios(tmp_path) == ["erro: RuntimeError"]
    assert n.erros == 1 and n.enviados == 0
    assert TOKEN not in (tmp_path / "log.csv").read_text(encoding="utf-8")
    assert TOKEN not in capsys.readouterr().out


def test_telegram_http_401_registra_erro(tmp_path):
    post = PostControlado(resposta=Resp(401, "Unauthorized"))
    post.liberar()
    pipe, n, _ = pipeline(tmp_path, post)
    pipe.processar("c1", payload_v2(40.1))
    n.encerrar(5)
    assert envios(tmp_path) == ["erro: HTTP 401 Unauthorized"]
    assert TOKEN not in (tmp_path / "log.csv").read_text(encoding="utf-8")


def test_sem_credenciais_nao_enfileira_e_registra_desativado(tmp_path):
    log = core.LogDecisoes(tmp_path / "log.csv")
    n = core.NotificadorAssincrono(core.Notificador(None, None), log)
    pipe = core.Pipeline(ModeloFalso("febre", 0.9), core.Debounce(1, 300), n, log)
    pipe.processar("c1", payload_v2(40.1))
    n.encerrar(1)
    assert [r["telegram"] for r in linhas_log(tmp_path) if r["acao_bruta"] != "envio_telegram"] == ["desativado"]


# ---------------------------------------------------------------- fila cheia
def test_fila_cheia_descarta_o_mais_antigo(tmp_path):
    post = PostControlado()
    n, _ = novo_async(post, tmp_path, fila=2)
    n.enviar("msg-1", dispositivo="c1", acao="alerta")
    assert post.iniciou.wait(2)                               # msg-1 está "em voo", presa no Telegram lento
    for i in (2, 3, 4, 5):
        n.enviar(f"msg-{i}", dispositivo="c1", acao="alerta")
    assert n.descartados == 2                                 # msg-2 e msg-3 foram removidas (as mais antigas da fila)
    post.liberar()
    n.encerrar(5)
    assert post.textos == ["msg-1", "msg-4", "msg-5"]         # sobraram as mais novas
    assert envios(tmp_path).count("descartado: fila cheia (mais antigo removido)") == 2
    assert envios(tmp_path).count("enviado") == 3


# ---------------------------------------------------------------- encerramento limpo
def test_encerramento_esvazia_a_fila_quando_da_tempo(tmp_path):
    post = PostControlado()
    post.liberar()
    n, _ = novo_async(post, tmp_path)
    for i in range(5):
        n.enviar(f"m{i}", dispositivo="c1", acao="alerta")
    assert n.encerrar(5) == 0
    assert post.textos == [f"m{i}" for i in range(5)]


def test_encerramento_com_telegram_travado_respeita_o_prazo(tmp_path):
    post = PostControlado(atraso_max=8.0)
    n, _ = novo_async(post, tmp_path)
    for i in range(4):
        n.enviar(f"m{i}", dispositivo="c1", acao="alerta")
    assert post.iniciou.wait(2)
    t0 = time.time()
    restantes = n.encerrar(timeout=0.5)
    assert time.time() - t0 < 2.5                            # não espera os 8 s
    assert restantes == 3                                    # 1 em voo, 3 descartados
    assert any("encerramento" in e for e in envios(tmp_path))
    n.enviar("depois", dispositivo="c1", acao="alerta")      # após encerrar: descarta, não trava nem lança
    assert n.ultimo_status.startswith("descartado")
    post.liberar()


# ---------------------------------------------------------------- alerta_leve e intervalo mínimo
def test_alerta_leve_chega_ao_telegram(tmp_path):
    post = PostControlado()
    post.liberar()
    t = [0.0]
    deb = core.Debounce(1, 300, parado_letargia=3, relogio=lambda: t[0])
    pipe, n, _ = pipeline(tmp_path, post, classe="parado", debounce=deb)
    acoes = [pipe.processar("c1", payload_v2(38.3, "parado"))["acao"] for _ in range(3)]
    n.encerrar(5)
    assert acoes == ["nenhum", "nenhum", "alerta_leve"]
    assert len(post.textos) == 1
    assert "Alerta leve" in post.textos[0] and "letargia" in post.textos[0] and "aviso leve" in post.textos[0]


def test_intervalo_minimo_configuravel_e_padrao_300():
    assert core.Debounce().intervalo == 300.0
    import consumidor_v2
    import os
    antigo = os.environ.pop("ANIMA_INTERVALO_NOTIF_S", None)
    try:
        assert consumidor_v2.criar_parser().parse_args([]).intervalo_notif == 300
    finally:
        if antigo is not None:
            os.environ["ANIMA_INTERVALO_NOTIF_S"] = antigo


def test_mesma_causa_repetida_e_limitada_pelo_intervalo(tmp_path):
    post = PostControlado()
    post.liberar()
    pipe, n, t = pipeline(tmp_path, post, debounce=None)
    pipe.debounce = core.Debounce(1, 2.0, relogio=lambda: t[0])   # intervalo curto só no teste
    for _ in range(3):                                            # 3 alertas de febre em 0 s: 1 notificação
        pipe.processar("c1", payload_v2(40.1))
    t[0] = 1.9
    pipe.processar("c1", payload_v2(40.1))                        # ainda dentro dos 2,0 s
    t[0] = 2.0
    pipe.processar("c1", payload_v2(40.1))                        # venceu: nova notificação
    n.encerrar(5)
    assert len(post.textos) == 2


def test_febre_logo_depois_de_agitacao_notifica_de_novo(tmp_path):
    post = PostControlado()
    post.liberar()
    pipe, n, t = pipeline(tmp_path, post, classe="agitado")
    pipe.processar("c1", payload_v2(38.8, "agitado"))             # causa: agitado
    pipe.modelo = ModeloFalso("febre", 0.9)
    pipe.processar("c1", payload_v2(40.0, "normal"))              # causa: temperatura_alta, no mesmo segundo
    pipe.processar("c1", payload_v2(40.0, "normal"))              # mesma causa repetida: limitada
    pipe.modelo = ModeloFalso("agitado", 0.9)
    pipe.processar("c1", payload_v2(38.8, "agitado"))             # agitação de novo, dentro do intervalo: limitada
    n.encerrar(5)
    assert len(post.textos) == 2
    assert "agitado" in post.textos[0] and "febre" in post.textos[1]


def test_debounce_chave_por_causa_e_acao():
    t = [0.0]
    d = core.Debounce(1, 300, relogio=lambda: t[0])
    assert d.processar("c", "alerta", "x", "agitado", causa="agitado").notificar
    assert d.processar("c", "alerta", "x", "febre", causa="temperatura_alta").notificar
    assert not d.processar("c", "alerta", "x", "agitado", causa="agitado").notificar
    assert d.processar("c", "alerta_leve", "x", "parado", causa="agitado").notificar   # outra ação, mesma causa
    assert core.causa_do_alerta("febre", 38.0) == "temperatura_alta"
    assert core.causa_do_alerta("normal", 40.0, 39.5) == "temperatura_alta"
    assert core.causa_do_alerta("agitado", 38.5, 39.5) == "agitado"


def test_carregar_env_respeita_isolamento_dos_testes(tmp_path, monkeypatch):
    """Regressão: testes automáticos não podem carregar o .env real (mandaria mensagens de teste ao Telegram de verdade)."""
    arq = tmp_path / ".env"
    arq.write_text("TELEGRAM_BOT_TOKEN=abc:valor-de-teste\nTELEGRAM_CHAT_ID=1\n", encoding="utf-8")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("ANIMA_SEM_DOTENV", "1")
    core.carregar_env(arq)
    import os
    assert "TELEGRAM_BOT_TOKEN" not in os.environ
    monkeypatch.delenv("ANIMA_SEM_DOTENV")
    core.carregar_env(arq)                    # sem o isolamento, carrega normalmente
    assert os.environ.get("TELEGRAM_BOT_TOKEN") == "abc:valor-de-teste"
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN"); monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
