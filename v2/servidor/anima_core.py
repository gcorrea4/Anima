"""
Anima v2 - Núcleo do servidor (sem rede MQTT): validação do payload, features,
regra de decisão, debounce, notificação e log. Tudo aqui é testável sem broker.

Segredos (token do Telegram, senha do broker) vêm SÓ de variáveis de ambiente / .env.
"""
import collections
import csv
import json
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "ia"))
from features_v2 import FEATURES, MODELO_PADRAO, N_AMOSTRAS, VERSAO_PAYLOAD, carregar_meta  # noqa: E402

BROKER_PUBLICO = "broker.hivemq.com"
# Brokers de acesso aberto conhecidos: qualquer pessoa lê e publica em qualquer tópico.
HOSTS_PUBLICOS = {"broker.hivemq.com", "test.mosquitto.org", "broker.emqx.io", "mqtt.eclipseprojects.io",
                  "public.mqtthq.com"}
ID_VALIDO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_DISPOSITIVOS_PADRAO = 20     # dispositivos distintos aceitos no modo --todos
MAX_ESTADOS_DEBOUNCE = 1000      # estados por dispositivo mantidos no debounce (descarta o mais antigo)
MAX_CHAVES_NOTIF = 16            # relógios (causa, ação) guardados por dispositivo (descarta o mais antigo)
LIMIAR_CONFIANCA_PADRAO = 0.6
TEMP_SEGURANCA_PADRAO = 39.5   # °C; com o modelo, vem do .meta.json (já com offset_coleira)


# ---------------------------------------------------------------- configuração
def carregar_env(caminho=None):
    """Lê um .env simples (CHAVE=valor) e preenche os.environ SEM sobrescrever variáveis já definidas."""
    if os.environ.get("ANIMA_SEM_DOTENV") == "1":   # testes automáticos: nunca usar segredos reais do .env
        return
    candidatos = [Path(caminho)] if caminho else [AQUI.parent / ".env", AQUI / ".env"]
    for p in candidatos:
        if p.exists():
            for linha in p.read_text(encoding="utf-8").splitlines():
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def config_mqtt(env=None):
    env = os.environ if env is None else env
    return {
        "host": env.get("ANIMA_MQTT_HOST") or BROKER_PUBLICO,
        "porta": int(env.get("ANIMA_MQTT_PORT") or 1883),
        "usuario": env.get("ANIMA_MQTT_USER") or None,
        "senha": env.get("ANIMA_MQTT_PASS") or None,
        "tls": (env.get("ANIMA_MQTT_TLS") or "0").strip().lower() in ("1", "true", "sim", "yes"),
    }


def conectar_mqtt(client_id, cfg):
    """Cria o cliente paho (compatível com 1.x e 2.x) já com usuário/senha/TLS configurados."""
    import paho.mqtt.client as mqtt
    versao = getattr(mqtt, "CallbackAPIVersion", None)
    c = mqtt.Client(versao.VERSION2, client_id=client_id) if versao else mqtt.Client(client_id=client_id)
    if cfg["usuario"]:
        c.username_pw_set(cfg["usuario"], cfg["senha"])
    if cfg["tls"]:
        c.tls_set()
    return c


def broker_publico(host):
    return str(host).strip().lower() in HOSTS_PUBLICOS


def aviso_broker_publico(cfg):
    if broker_publico(cfg["host"]):
        print(f"AVISO: {cfg['host']} é um broker PÚBLICO, sem autenticação nem TLS (qualquer um lê e publica nos "
              "tópicos). Use só dados de teste e um id de dispositivo único. Para dados reais, configure um broker próprio.")


def validar_modo_assinatura(id_dispositivo, todos, aceito_risco_publico, host):
    """Decide se o servidor pode iniciar. Devolve uma mensagem de erro (str) ou None se está tudo certo.

    * Sem --id e sem --todos: recusa (o padrão antigo, assinar anima/+/dados, não existe mais).
    * --todos num broker público exige --aceito-risco-publico: o servidor processaria dados de terceiros,
      publicaria decisões em tópicos alheios e qualquer pessoa poderia forjar payloads e disparar notificações.
    """
    if id_dispositivo and todos:
        return "use --id <dispositivo> OU --todos, não os dois."
    if not id_dispositivo and not todos:
        return ("informe --id <dispositivo> (recomendado) ou --todos para assinar anima/+/dados. "
                "Sem um deles o servidor não inicia.")
    if id_dispositivo and not ID_VALIDO.match(id_dispositivo):
        return "id inválido: use só letras, números, '-' e '_' (até 64 caracteres)."
    if todos and broker_publico(host) and not aceito_risco_publico:
        return (f"--todos em um broker público ({host}) é perigoso: o servidor processaria dados de TERCEIROS, publicaria "
                "decisões em tópicos de outras pessoas e qualquer um poderia forjar payloads para disparar notificações no seu "
                "Telegram. Use --id <seu id>, um broker próprio com senha, ou confirme o risco com --aceito-risco-publico.")
    return None


class ControleDispositivos:
    """Limita quantos dispositivos DISTINTOS o servidor aceita (modo --todos). Novos além do limite são ignorados."""

    def __init__(self, maximo=MAX_DISPOSITIVOS_PADRAO, permitido=None):
        self.maximo = max(1, int(maximo))
        self.permitido = permitido          # id único (modo --id) ou None
        self.aceitos = []
        self.ignorados = 0

    def aceita(self, dispositivo):
        if self.permitido is not None:
            return dispositivo == self.permitido
        if dispositivo in self.aceitos:
            return True
        if len(self.aceitos) >= self.maximo:
            self.ignorados += 1
            return False
        self.aceitos.append(dispositivo)
        return True


# ---------------------------------------------------------------- payload / features
class PayloadDescartado(ValueError):
    """Payload inválido ou leitura que deve ser descartada (mensagem explica o motivo)."""


def validar_payload(payload, id_topico=None):
    """Valida o payload v2 do firmware e devolve dict {feature: float}. Levanta PayloadDescartado.

    Com `id_topico`, exige que o campo "id" do payload seja igual ao id do tópico em que chegou
    (evita que uma mensagem publicada no tópico de A se passe por B).
    """
    if not isinstance(payload, dict):
        raise PayloadDescartado("payload não é um objeto JSON")
    if id_topico is not None and payload.get("id") != id_topico:
        visto = str(payload.get("id"))[:40]
        raise PayloadDescartado(f"id do payload ({visto!r}) difere do id do tópico ({id_topico!r}) - ignorado")
    if payload.get("versao") != VERSAO_PAYLOAD:
        raise PayloadDescartado(f"versao do payload != {VERSAO_PAYLOAD} ({payload.get('versao')!r})")
    if payload.get("mpu_ok") is False:
        raise PayloadDescartado("mpu_ok=false (MPU6050 indisponível no dispositivo)")
    if payload.get("sensor_ok") is False:
        raise PayloadDescartado("sensor_ok=false (DS18B20 sem leitura válida na janela)")
    temp = payload.get("temperatura")
    if temp is None:
        raise PayloadDescartado("temperatura ausente/nula")
    try:
        temp_f = float(temp)
    except (TypeError, ValueError):
        raise PayloadDescartado(f"temperatura inválida: {temp!r}")
    if temp_f <= -100:
        raise PayloadDescartado("temperatura = -127 °C (DS18B20 desconectado?) - leitura descartada")
    n = payload.get("n_amostras")
    if n is not None and (not isinstance(n, (int, float)) or n < N_AMOSTRAS * 0.5):
        raise PayloadDescartado(f"janela incompleta (n_amostras={n}, esperado ~{N_AMOSTRAS})")
    valores = {}
    for f in FEATURES:
        if f not in payload:
            raise PayloadDescartado(f"campo ausente: {f}")
        try:
            v = float(payload[f])
        except (TypeError, ValueError):
            raise PayloadDescartado(f"campo {f} não numérico: {payload[f]!r}")
        if not math.isfinite(v):
            raise PayloadDescartado(f"campo {f} não finito")
        valores[f] = v
    return valores


def montar_features(valores):
    """dict de features -> DataFrame de 1 linha na ordem que o modelo espera."""
    return pd.DataFrame([[valores[f] for f in FEATURES]], columns=FEATURES)


def classificar(modelo, valores):
    """Devolve (classe, confianca, {classe: prob})."""
    probs = modelo.predict_proba(montar_features(valores))[0]
    i = int(np.argmax(probs))
    return str(modelo.classes_[i]), float(probs[i]), {str(c): float(p) for c, p in zip(modelo.classes_, probs)}


# ---------------------------------------------------------------- regra de decisão
def decidir_janela(classe, confianca, temperatura, limiar_confianca=LIMIAR_CONFIANCA_PADRAO,
                   temp_seguranca=TEMP_SEGURANCA_PADRAO):
    """Decisão BRUTA de uma janela (antes do debounce): (acao, motivo).

    acao ∈ {"alerta", "alerta_leve", "nenhum"}. A regra de segurança por temperatura vale
    independentemente da classe e da confiança do modelo.
    """
    if temp_seguranca is not None and temperatura >= temp_seguranca:
        return "alerta", f"temperatura alta ({temperatura:.1f} °C >= {temp_seguranca:.1f} °C, regra de segurança)"
    if classe in ("febre", "agitado") and confianca >= limiar_confianca:
        return "alerta", f"classe {classe} (confiança {confianca:.0%})"
    return "nenhum", "comportamento dentro do esperado"


def causa_do_alerta(classe, temperatura, temp_seguranca=TEMP_SEGURANCA_PADRAO):
    """Causa usada para limitar notificações repetidas: temperatura alta (regra de segurança OU classe febre) ou a classe."""
    if classe == "febre" or (temp_seguranca is not None and temperatura >= temp_seguranca):
        return "temperatura_alta"
    return classe


# ---------------------------------------------------------------- debounce
@dataclass
class _Estado:
    ultima_acao: str = "nenhum"
    contagem: int = 0
    parado_seguidas: int = 0
    ultima_notif: dict = field(default_factory=dict)


@dataclass
class ResultadoDebounce:
    acao: str          # ação FINAL (publicada ao dispositivo)
    notificar: bool    # enviar notificação (Telegram) agora?
    motivo: str
    confirmada: bool


class Debounce:
    """Exige N janelas consecutivas com a mesma ação antes de alertar e limita notificações repetidas.

    - Uma janela "nenhum" no meio zera a contagem (alerta isolado nunca dispara).
    - Notificações: no máximo uma por (dispositivo, causa, ação) a cada `intervalo_notif_s`. A mesma
      causa repetida fica limitada; uma causa DIFERENTE (ex.: febre logo depois de agitação) ou uma ação
      diferente (alerta_leve -> alerta) notifica na hora, com relógios independentes.
      Causa = "temperatura_alta" (regra de segurança ou classe febre), "agitado", "letargia"...
      Sem causa informada, usa a classe prevista.
    - `parado_letargia` > 0: após tantas janelas "parado" seguidas gera alerta_leve (imobilidade
      prolongada, possível letargia). 0 = desligado (padrão: precisa ser calibrado com dados reais).
    """

    def __init__(self, n_consecutivas=2, intervalo_notif_s=300.0, parado_letargia=0,
                 relogio: Callable[[], float] = time.time, max_estados=MAX_ESTADOS_DEBOUNCE):
        self.n = max(1, int(n_consecutivas))
        self.intervalo = float(intervalo_notif_s)
        self.parado_letargia = int(parado_letargia)
        self.relogio = relogio
        self.max_estados = max(1, int(max_estados))
        self._est = collections.OrderedDict()   # estado por dispositivo, do menos para o mais recente

    def processar(self, dispositivo, acao_bruta, motivo, classe=None, causa=None):
        st = self._est.get(dispositivo)
        if st is None:
            st = self._est[dispositivo] = _Estado()
            while len(self._est) > self.max_estados:      # estado limitado: descarta o dispositivo mais antigo
                self._est.popitem(last=False)
        else:
            self._est.move_to_end(dispositivo)
        st.parado_seguidas = st.parado_seguidas + 1 if classe == "parado" else 0
        if (acao_bruta == "nenhum" and self.parado_letargia > 0
                and st.parado_seguidas >= self.parado_letargia):
            acao_bruta, motivo = "alerta_leve", f"imobilidade prolongada ({st.parado_seguidas} janelas) - possível letargia"
            causa = "letargia"
        causa = causa or classe

        if acao_bruta == st.ultima_acao:
            st.contagem += 1
        else:
            st.ultima_acao, st.contagem = acao_bruta, 1
        if acao_bruta == "nenhum":
            return ResultadoDebounce("nenhum", False, motivo, True)

        if st.contagem < self.n:
            return ResultadoDebounce("nenhum", False,
                                     f"aguardando confirmação ({st.contagem}/{self.n}): {motivo}", False)
        agora = self.relogio()
        chave = (causa, acao_bruta)
        ultimo = st.ultima_notif.get(chave)
        notificar = ultimo is None or (agora - ultimo) >= self.intervalo
        if notificar:
            st.ultima_notif.pop(chave, None)
            st.ultima_notif[chave] = agora
            while len(st.ultima_notif) > MAX_CHAVES_NOTIF:   # descarta o relógio mais antigo
                st.ultima_notif.pop(next(iter(st.ultima_notif)))
        return ResultadoDebounce(acao_bruta, notificar, motivo, True)


# ---------------------------------------------------------------- notificação / log
class Notificador:
    """Telegram via API HTTP (requests). Sem token/chat id, só imprime no terminal."""

    def __init__(self, token=None, chat_id=None, http_post=None):
        self.token, self.chat_id = token, chat_id
        self._post = http_post
        self.ultimo_status = ""   # "enviado" | "desativado" | "erro: ..." (nunca contém o token)

    @classmethod
    def do_ambiente(cls, env=None):
        env = os.environ if env is None else env
        token = env.get("TELEGRAM_BOT_TOKEN") or env.get("ANIMA_TELEGRAM_TOKEN") or None
        chat = env.get("TELEGRAM_CHAT_ID") or env.get("ANIMA_TELEGRAM_CHAT_ID") or None
        return cls(token, chat)

    @property
    def telegram_ativo(self):
        return bool(self.token and self.chat_id)

    def enviar(self, texto, imprimir=True, **_contexto):
        """Envio SÍNCRONO (bloqueia até ~10 s numa falha lenta). O servidor usa NotificadorAssincrono por cima."""
        if imprimir:
            print(f"[NOTIFICAÇÃO] {texto}")
        if not self.telegram_ativo:
            self.ultimo_status = "desativado"
            return False
        try:
            post = self._post
            if post is None:
                import requests
                post = requests.post
            r = post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                     data={"chat_id": self.chat_id, "text": texto}, timeout=(4, 6))
            if r.status_code != 200:
                # a descrição da API ("Unauthorized", "Bad Request: chat not found") não contém o token
                try:
                    desc = str(r.json().get("description", ""))[:80]
                except Exception:   # noqa: BLE001
                    desc = ""
                self.ultimo_status = f"erro: HTTP {r.status_code} {desc}".strip()
                print(f"  (Telegram recusou: {self.ultimo_status[6:]})")   # nunca imprime a URL: ela contém o token
                return False
            self.ultimo_status = "enviado"
            return True
        except Exception as e:   # noqa: BLE001 - nunca derruba o servidor por falha de notificação
            self.ultimo_status = f"erro: {type(e).__name__}"   # sem str(e): pode conter a URL/token
            print(f"  (falha ao falar com o Telegram: {type(e).__name__})")
            return False


COLUNAS_LOG = ["timestamp", "dispositivo", "classe", "confianca", "temperatura", "acao_bruta",
               "acao_final", "motivo", "notificou", "telegram", "probabilidades"]


class LogDecisoes:
    """CSV de decisões. Thread-safe (a thread do Telegram também grava o resultado dos envios)."""

    def __init__(self, caminho):
        self.caminho = Path(caminho) if caminho else None
        self._lock = threading.Lock()
        if self.caminho:
            self.caminho.parent.mkdir(parents=True, exist_ok=True)

    def registrar(self, **campos):
        if not self.caminho:
            return
        with self._lock:
            novo = not self.caminho.exists()
            with open(self.caminho, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=COLUNAS_LOG)
                if novo:
                    w.writeheader()
                w.writerow({c: campos.get(c, "") for c in COLUNAS_LOG})

    def registrar_envio(self, dispositivo, acao, status, detalhe=""):
        """Uma linha por envio ao Telegram: acao_bruta='envio_telegram', telegram=enviado|erro: ...|descartado: ..."""
        self.registrar(timestamp=time.strftime("%Y-%m-%d %H:%M:%S"), dispositivo=dispositivo,
                       acao_bruta="envio_telegram", acao_final=acao, telegram=status, motivo=detalhe)


class NotificadorAssincrono:
    """Envia as notificações numa thread em segundo plano: enviar() NUNCA bloqueia o chamador.

    * Fila limitada (`tamanho_fila`); cheia => descarta a MAIS ANTIGA (e registra 'descartado: fila cheia').
    * O timeout curto do HTTP (4 s conexão + 6 s leitura) fica no Notificador interno.
    * O resultado de cada envio (enviado / erro: ... / descartado: ...) vai para o log, sem expor o token.
    * encerrar(timeout): tenta esvaziar a fila até o prazo; o que sobrar é descartado e registrado.
    """

    def __init__(self, notificador, log=None, tamanho_fila=20):
        self.notificador = notificador
        self.log = log or LogDecisoes(None)
        self.tamanho_fila = max(1, int(tamanho_fila))
        self._fila = collections.deque()
        self._cv = threading.Condition()
        self._parar = False
        self._prazo = None
        self.enviados = self.erros = self.descartados = 0
        self.ultimo_status = ""
        self._thread = threading.Thread(target=self._loop, name="anima-telegram", daemon=True)
        self._thread.start()

    @property
    def telegram_ativo(self):
        return self.notificador.telegram_ativo

    def enviar(self, texto, dispositivo="", acao="", **_contexto):
        print(f"[NOTIFICAÇÃO] {texto}")
        if not self.telegram_ativo:
            self.ultimo_status = "desativado"
            return False
        with self._cv:
            if self._parar:
                self.ultimo_status = "descartado: encerrando"
                self._contar_descarte(dispositivo, acao, "encerrando")
                return False
            if len(self._fila) >= self.tamanho_fila:
                _, disp_v, acao_v, _ = self._fila.popleft()
                self._contar_descarte(disp_v, acao_v, "fila cheia (mais antigo removido)")
            self._fila.append((texto, dispositivo, acao, time.time()))
            self._cv.notify()
        self.ultimo_status = "enfileirado"
        return True

    def _contar_descarte(self, dispositivo, acao, motivo):
        self.descartados += 1
        self.log.registrar_envio(dispositivo, acao, f"descartado: {motivo}")

    def _loop(self):
        while True:
            with self._cv:
                while not self._fila and not self._parar:
                    self._cv.wait()
                if not self._fila or (self._parar and time.time() >= self._prazo):
                    return
                texto, dispositivo, acao, t0 = self._fila.popleft()
            self.notificador.enviar(texto, imprimir=False)
            status = self.notificador.ultimo_status
            if status == "enviado":
                self.enviados += 1
            else:
                self.erros += 1
            self.log.registrar_envio(dispositivo, acao, status, f"{time.time() - t0:.1f} s desde a decisão")

    def encerrar(self, timeout=5.0):
        """Para a thread. Devolve quantas notificações foram descartadas por não caberem no prazo."""
        with self._cv:
            self._parar = True
            self._prazo = time.time() + timeout
            self._cv.notify_all()
        self._thread.join(timeout + 0.5)
        with self._cv:
            restantes = list(self._fila)
            self._fila.clear()
        for _, dispositivo, acao, _ in restantes:
            self._contar_descarte(dispositivo, acao, "encerramento antes do envio")
        return len(restantes)


def texto_notificacao(dispositivo, acao, classe, confianca, temperatura, motivo, horario=""):
    titulo = "🚨 ALERTA" if acao == "alerta" else "⚠ Alerta leve"
    efeito = "buzzer/LED acionados na coleira" if acao == "alerta" else "aviso leve na coleira"
    linhas = [f"{titulo} - Anima",
              f"Dispositivo: {dispositivo}",
              f"Ação: {acao} ({efeito})",
              f"Classe: {classe} (confiança {confianca:.0%})",
              f"Temperatura da coleira: {temperatura:.1f} °C",
              f"Motivo: {motivo}"]
    if horario:
        linhas.append(f"Horário: {horario}")
    return "\n".join(linhas)


# ---------------------------------------------------------------- pipeline
class Pipeline:
    """payload -> validação -> modelo -> regra -> debounce -> notificação/log -> decisão a publicar."""

    def __init__(self, modelo, debounce=None, notificador=None, log=None,
                 limiar_confianca=LIMIAR_CONFIANCA_PADRAO, temp_seguranca=TEMP_SEGURANCA_PADRAO,
                 relogio=time.time, exigir_id=False):
        self.exigir_id = exigir_id    # True no servidor: payload["id"] precisa ser igual ao id do tópico
        self.modelo = modelo
        self.debounce = debounce or Debounce(relogio=relogio)
        self.notificador = notificador or Notificador()
        self.log = log or LogDecisoes(None)
        self.limiar_confianca = limiar_confianca
        self.temp_seguranca = temp_seguranca
        self.relogio = relogio

    def processar(self, dispositivo, payload):
        """Devolve o dict da decisão a publicar, ou None se a leitura foi descartada."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.relogio()))
        try:
            valores = validar_payload(payload, id_topico=dispositivo if self.exigir_id else None)
        except PayloadDescartado as e:
            print(f"[{ts}] {dispositivo}: leitura descartada - {e}")
            self.log.registrar(timestamp=ts, dispositivo=dispositivo, acao_bruta="descartada",
                               acao_final="", motivo=str(e))
            return None
        classe, conf, probs = classificar(self.modelo, valores)
        temp = valores["temperatura"]
        bruta, motivo = decidir_janela(classe, conf, temp, self.limiar_confianca, self.temp_seguranca)
        r = self.debounce.processar(dispositivo, bruta, motivo, classe,
                                    causa=causa_do_alerta(classe, temp, self.temp_seguranca))
        status_tg = ""
        if r.notificar:   # só enfileira: a decisão abaixo NUNCA espera o Telegram
            self.notificador.enviar(texto_notificacao(dispositivo, r.acao, classe, conf, temp, r.motivo, ts),
                                    dispositivo=dispositivo, acao=r.acao)
            status_tg = getattr(self.notificador, "ultimo_status", "")
        self.log.registrar(timestamp=ts, dispositivo=dispositivo, classe=classe, confianca=f"{conf:.3f}",
                           temperatura=f"{temp:.2f}", acao_bruta=bruta, acao_final=r.acao, motivo=r.motivo,
                           notificou=int(r.notificar), telegram=status_tg, probabilidades=json.dumps(probs))
        resumo = " ".join(f"{k}={v:.2f}" for k, v in probs.items())
        print(f"[{ts}] {dispositivo}: {classe.upper()} ({conf:.0%}) temp={temp:.2f} °C | {resumo} "
              f"| bruta={bruta} final={r.acao}")
        return {"acao": r.acao, "classe": classe, "confianca": round(conf, 3), "motivo": r.motivo, "ts": ts}


def parametros_do_modelo(caminho_modelo):
    """Limiar de segurança vindo do .meta.json do modelo (já com offset_coleira)."""
    return carregar_meta(caminho_modelo).get("temp_seguranca_coleira", TEMP_SEGURANCA_PADRAO)
