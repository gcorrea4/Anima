"""
Anima v2 - Consumidor MQTT: classifica, decide e PUBLICA a decisão para a coleira.

Fluxo: anima/<id>/dados -> validação -> Random Forest v2 -> regra (confiança >= 0,6 + segurança por
temperatura) -> debounce (N janelas consecutivas) -> publica em anima/<id>/decisao
-> notificação (Telegram, se configurado) -> log CSV.

Uso:
  python consumidor_v2.py --selftest          # sem rede
  python consumidor_v2.py --id <seu-id>       # UM dispositivo (obrigatório, a menos que use --todos)
  python consumidor_v2.py --todos             # assina anima/+/dados (broker próprio/local)
  python consumidor_v2.py --todos --aceito-risco-publico   # --todos em broker público: só se você aceita o risco

Segurança: sem --id/--todos o servidor NÃO inicia. Em broker público (ex.: broker.hivemq.com) --todos é recusado
sem --aceito-risco-publico, porque processaria dados de terceiros, publicaria decisões em tópicos alheios e permitiria
que qualquer pessoa forjasse payloads para disparar notificações. O campo "id" do payload precisa ser igual ao id do
tópico; --todos aceita no máximo --max-dispositivos dispositivos distintos (os demais são ignorados).

Configuração por variáveis de ambiente / .env (veja ../.env.example):
  ANIMA_MQTT_HOST, ANIMA_MQTT_PORT, ANIMA_MQTT_USER, ANIMA_MQTT_PASS, ANIMA_MQTT_TLS,
  ANIMA_TELEGRAM_TOKEN, ANIMA_TELEGRAM_CHAT_ID,
  ANIMA_JANELAS_CONSECUTIVAS (2), ANIMA_INTERVALO_NOTIF_S (300), ANIMA_LIMIAR_CONFIANCA (0.6),
  ANIMA_PARADO_LETARGIA_JANELAS (0 = desligado)

AVISO: o broker padrão (broker.hivemq.com) é PÚBLICO. Não use com dados reais.
"""
import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import joblib

import anima_core as core
from features_v2 import MODELO_PADRAO, carregar_meta

AQUI = Path(__file__).resolve().parent
LOG_PADRAO = AQUI / "logs" / "decisoes_log.csv"


def carregar_modelo(caminho):
    if not Path(caminho).exists():
        sys.exit(f"Modelo não encontrado em '{caminho}'. Rode ia/gerar_dataset_v2.py e ia/treinar_modelo_v2.py.")
    return joblib.load(caminho)


def _float_env(nome, padrao):
    return float(os.environ.get(nome) or padrao)


# ---------------------------------------------------------------- selftest (sem rede)
def _payload(temp, movimento="parado", **extra):
    base = {
        "parado": (9.81, 0.05, 9.95, 1.0, 0.4, 2.2),
        "normal": (9.9, 1.0, 13.0, 25.0, 14.0, 70.0),
        "agitado": (11.2, 3.5, 30.0, 100.0, 75.0, 400.0),
    }[movimento]
    p = {"versao": 2, "id": "teste", "n_amostras": 50, "temperatura": temp, "sensor_ok": True, "mpu_ok": True}
    p.update(dict(zip(["accel_mag_media", "accel_mag_std", "accel_mag_max",
                       "gyro_mag_media", "gyro_mag_std", "gyro_mag_max"], base)))
    p.update(extra)
    return p


def selftest(modelo, temp_seguranca, offset=0.0):
    """Cenários na escala do modelo: todas as temperaturas válidas recebem `offset` (offset_coleira do .meta.json)."""
    relogio = [1000.0]
    enviados = []

    class NotifFalso(core.Notificador):
        def enviar(self, texto, **_kw):
            enviados.append(texto)
            return True

    pipe = core.Pipeline(modelo, core.Debounce(2, 300, relogio=lambda: relogio[0]), NotifFalso(),
                         temp_seguranca=temp_seguranca, relogio=lambda: relogio[0])
    falhas = []

    def verifica(cond, msg):
        print(("  OK    " if cond else "  FALHA ") + msg)
        if not cond:
            falhas.append(msg)

    def T(x):          # temperatura de cenário (escala corporal) -> escala da coleira do modelo
        return None if x is None else x + offset

    print(f"Selftest v2 (sem rede) | offset_coleira do modelo = {offset:+.1f} °C | limiar de segurança = {temp_seguranca:.1f} °C")
    d = pipe.processar("t1", _payload(T(38.3)))
    verifica(d and d["acao"] == "nenhum" and d["classe"] == "parado", "parado a 38,3 °C (+offset) -> sem alerta")
    d = pipe.processar("t1", _payload(T(40.1)))
    verifica(d["classe"] == "febre" and d["acao"] == "nenhum", "parado + 40,1 °C: classe febre, 1ª janela só aguarda (debounce)")
    d = pipe.processar("t1", _payload(T(40.1)))
    verifica(d["acao"] == "alerta" and len(enviados) == 1, "2ª janela consecutiva -> ALERTA + 1 notificação")
    d = pipe.processar("t1", _payload(T(40.1)))
    verifica(d["acao"] == "alerta" and len(enviados) == 1, "alerta mantido, sem notificação repetida (intervalo mínimo)")
    relogio[0] += 301
    pipe.processar("t1", _payload(T(40.1)))
    verifica(len(enviados) == 2, "após o intervalo mínimo, nova notificação")
    verifica(pipe.processar("t1", _payload(-127.0)) is None, "temperatura -127 descartada")
    verifica(pipe.processar("t1", _payload(None, sensor_ok=False)) is None, "sensor_ok=false descartada")
    d = pipe.processar("t2", _payload(T(40.5), "agitado"))
    d = pipe.processar("t2", _payload(T(38.5), "normal"))
    verifica(d["acao"] == "nenhum", "leitura isolada de alerta não dispara (contagem zerada)")
    estrito = core.Pipeline(modelo, core.Debounce(2, 300, relogio=lambda: relogio[0]), NotifFalso(),
                            temp_seguranca=temp_seguranca, relogio=lambda: relogio[0], exigir_id=True)
    verifica(estrito.processar("t9", _payload(T(38.5), "normal", id="outro")) is None,
             "payload com id diferente do id do tópico é ignorado")
    verifica(estrito.processar("t9", _payload(T(38.5), "normal", id="t9")) is not None,
             "payload com id igual ao do tópico é aceito")
    print("OK: tudo certo." if not falhas else f"{len(falhas)} FALHA(S).")
    return not falhas


# ---------------------------------------------------------------- MQTT
def executar(args, modelo, temp_seguranca):
    cfg = core.config_mqtt()
    core.aviso_broker_publico(cfg)
    log = core.LogDecisoes(args.log)
    # Telegram em segundo plano: a decisão publicada nunca espera a API do Telegram
    notificador = core.NotificadorAssincrono(core.Notificador.do_ambiente(), log, tamanho_fila=args.fila_telegram)
    pipe = core.Pipeline(
        modelo,
        core.Debounce(args.janelas, args.intervalo_notif, args.parado_letargia),
        notificador,
        log,
        limiar_confianca=args.limiar_confianca,
        temp_seguranca=temp_seguranca,
        exigir_id=True,       # payload["id"] precisa ser igual ao id do tópico
    )
    controle = core.ControleDispositivos(args.max_dispositivos, permitido=args.id)
    filtro = f"anima/{args.id}/dados" if args.id else "anima/+/dados"
    cliente = core.conectar_mqtt(f"anima_servidor_{random.randint(0, 99999)}", cfg)

    def on_connect(c, userdata, flags, rc, properties=None):
        print(f"Conectado a {cfg['host']}:{cfg['porta']} (rc={rc}). Assinando '{filtro}'...")
        c.subscribe(filtro)

    def on_message(c, userdata, msg):
        partes = msg.topic.split("/")
        dispositivo = partes[1] if len(partes) == 3 else ""
        if not core.ID_VALIDO.match(dispositivo):
            print(f"mensagem ignorada: tópico inesperado '{msg.topic}'")
            return
        if not controle.aceita(dispositivo):
            if controle.permitido is None and (controle.ignorados == 1 or controle.ignorados % 100 == 0):
                print(f"AVISO: limite de {controle.maximo} dispositivos atingido; mensagens de novos ids são ignoradas "
                      f"({controle.ignorados} até agora).")
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            print(f"[{dispositivo}] mensagem ignorada: JSON inválido")
            return
        decisao = pipe.processar(dispositivo, payload)
        if decisao is not None and not args.nao_publicar:
            c.publish(f"anima/{dispositivo}/decisao", json.dumps(decisao, ensure_ascii=False))

    cliente.on_connect = on_connect
    cliente.on_message = on_message
    print(f"Telegram: {'ATIVO' if pipe.notificador.telegram_ativo else 'não configurado (só terminal)'} | "
          f"janelas consecutivas={args.janelas} | intervalo notif={args.intervalo_notif:.0f}s | "
          f"limiar confiança={args.limiar_confianca} | temp. segurança={temp_seguranca:.1f} °C")
    cliente.connect(cfg["host"], cfg["porta"], keepalive=60)
    try:
        cliente.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        print("\nEncerrando...")
    finally:
        cliente.disconnect()
        perdidas = notificador.encerrar(timeout=5.0)   # esvazia a fila do Telegram por até 5 s; o resto é descartado e registrado
        print(f"Encerrado. Telegram: {notificador.enviados} enviadas, {notificador.erros} com erro, "
              f"{notificador.descartados} descartadas ({perdidas} no encerramento).")


def criar_parser():
    ap = argparse.ArgumentParser(description="Servidor Anima v2 (MQTT + IA + decisão + Telegram)")
    ap.add_argument("--modelo", default=str(MODELO_PADRAO))
    ap.add_argument("--id", default=None, help="id do dispositivo a atender (obrigatório, a menos que use --todos)")
    ap.add_argument("--todos", action="store_true",
                    help="assina anima/+/dados (todos os dispositivos). Em broker PÚBLICO exige --aceito-risco-publico")
    ap.add_argument("--aceito-risco-publico", action="store_true",
                    help="confirma que você entende o risco de --todos em broker público (dados de terceiros, payloads forjados)")
    ap.add_argument("--max-dispositivos", type=int, default=core.MAX_DISPOSITIVOS_PADRAO,
                    help=f"máximo de dispositivos distintos no modo --todos (padrão {core.MAX_DISPOSITIVOS_PADRAO})")
    ap.add_argument("--janelas", type=int, default=int(_float_env("ANIMA_JANELAS_CONSECUTIVAS", 2)),
                    help="janelas consecutivas necessárias antes de alertar (padrão 2)")
    ap.add_argument("--intervalo-notif", type=float, default=_float_env("ANIMA_INTERVALO_NOTIF_S", 300),
                    help="segundos mínimos entre notificações repetidas (padrão 300)")
    ap.add_argument("--limiar-confianca", type=float, default=_float_env("ANIMA_LIMIAR_CONFIANCA", 0.6))
    ap.add_argument("--parado-letargia", type=int, default=int(_float_env("ANIMA_PARADO_LETARGIA_JANELAS", 0)),
                    help="janelas 'parado' seguidas para alerta leve de possível letargia (0 = desligado)")
    ap.add_argument("--temp-seguranca", type=float, default=None,
                    help="limiar de segurança em °C (padrão: o do .meta.json do modelo, já com offset_coleira)")
    ap.add_argument("--fila-telegram", type=int, default=20,
                    help="tamanho máximo da fila de notificações; cheia => descarta a mais antiga (padrão 20)")
    ap.add_argument("--log", default=str(LOG_PADRAO))
    ap.add_argument("--nao-publicar", action="store_true", help="não publica decisões (só observa)")
    ap.add_argument("--selftest", action="store_true", help="testa o fluxo completo sem rede")
    return ap


def main():
    core.carregar_env()
    args = criar_parser().parse_args()

    modelo = carregar_modelo(args.modelo)
    temp_seg = args.temp_seguranca if args.temp_seguranca is not None else core.parametros_do_modelo(args.modelo)
    if args.selftest:
        offset = float(carregar_meta(args.modelo).get("offset_coleira", 0.0))
        sys.exit(0 if selftest(modelo, temp_seg, offset) else 1)
    erro = core.validar_modo_assinatura(args.id, args.todos, args.aceito_risco_publico, core.config_mqtt()["host"])
    if erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(2)
    executar(args, modelo, temp_seg)


if __name__ == "__main__":
    main()
