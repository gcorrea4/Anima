"""
Anima v2 - Coleta de dados rotulados a partir do MQTT (para retreino com dados reais).

Assina anima/<id>/dados e grava um CSV com timestamp, metadados da sessão e as MESMAS colunas
do dataset sintético v2 (FEATURES + classe), então pode ser concatenado e usado em ia/retreinar.py.

Uso:
  python coletar_dados.py --id <SEU_ID> --rotulo parado --animal Thor --obs "dormindo no sofá"
  python coletar_dados.py --id <SEU_ID> --rotulo normal --animal Thor --max-janelas 150
  python coletar_dados.py --selftest

Cuidados:
  * Uma sessão = um rótulo. Troque de comportamento => pare (Ctrl+C) e inicie nova sessão.
  * NUNCA provoque febre/estresse no animal para coletar dados. Use o rótulo 'febre' somente quando um
    veterinário/termômetro clínico confirmar a febre. Sem dados reais de febre, mantenha as janelas
    sintéticas de febre no retreino (ia/retreinar.py faz isso por padrão).
  * Leituras inválidas (-127, sensor_ok=false, MPU fora) são descartadas e contadas, nunca gravadas.
  * Descarte os primeiros segundos de cada sessão (--descartar-iniciais, padrão 3 janelas): a coleira ainda
    está sendo colocada e o DS18B20 ainda esquentando.
  * Broker público => dados visíveis a qualquer pessoa. Use broker próprio com dados reais.
"""
import argparse
import csv
import json
import random
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import anima_core as core
from features_v2 import FEATURES, ROTULOS

AQUI = Path(__file__).resolve().parent
PASTA_PADRAO = AQUI / "dados_reais"
COLUNAS = ["timestamp", "sessao_id", "id_dispositivo", "animal", "observacoes"] + FEATURES + ["classe", "origem"]


class Coletor:
    """Recebe payloads, valida e grava linhas. Separado do MQTT para ser testável."""

    def __init__(self, arquivo, rotulo, id_dispositivo, animal="", observacoes="", max_janelas=0,
                 descartar_iniciais=3, relogio=datetime.now):
        if rotulo not in ROTULOS:
            raise ValueError(f"rótulo inválido '{rotulo}' (use: {', '.join(ROTULOS)})")
        self.arquivo = Path(arquivo)
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.meta = dict(sessao_id=uuid.uuid4().hex[:8], id_dispositivo=id_dispositivo, animal=animal,
                         observacoes=observacoes, classe=rotulo, origem="real")
        self.max_janelas = max_janelas
        self.descartar_iniciais = descartar_iniciais
        self.relogio = relogio
        self.gravadas = 0
        self.descartadas = 0
        self.ignoradas_iniciais = 0
        novo = not self.arquivo.exists()
        self._f = open(self.arquivo, "a", newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._f, fieldnames=COLUNAS)
        if novo:
            self._w.writeheader()

    @property
    def terminou(self):
        return self.max_janelas > 0 and self.gravadas >= self.max_janelas

    def receber(self, payload):
        """Retorna True se a janela foi gravada."""
        try:
            valores = core.validar_payload(payload, id_topico=self.meta["id_dispositivo"])
        except core.PayloadDescartado as e:
            self.descartadas += 1
            print(f"  descartada ({self.descartadas}): {e}")
            return False
        if self.ignoradas_iniciais < self.descartar_iniciais:
            self.ignoradas_iniciais += 1
            return False
        linha = {"timestamp": self.relogio().isoformat(timespec="seconds"), **self.meta, **valores}
        self._w.writerow(linha)
        self._f.flush()
        self.gravadas += 1
        print(f"  [{self.gravadas}] {self.meta['classe']} temp={valores['temperatura']:.2f} "
              f"accel_std={valores['accel_mag_std']:.2f} gyro_media={valores['gyro_mag_media']:.1f}")
        return True

    def fechar(self):
        self._f.close()


def selftest():
    import tempfile
    from pandas import read_csv
    from features_v2 import FEATURES as F
    ok = True
    with tempfile.TemporaryDirectory() as d:
        c = Coletor(Path(d) / "t.csv", "parado", "teste", "Rex", "obs", descartar_iniciais=0)
        base = {"versao": 2, "id": "teste", "n_amostras": 50, "temperatura": 38.3, "sensor_ok": True, "mpu_ok": True,
                **{f: 1.0 for f in F if f != "temperatura"}}
        c.receber(base)
        c.receber({**base, "temperatura": -127.0})
        c.fechar()
        df = read_csv(Path(d) / "t.csv")
        ok = len(df) == 1 and c.descartadas == 1 and all(f in df.columns for f in F) and df.classe[0] == "parado"
    print("Selftest do coletor:", "OK" if ok else "FALHA")
    return ok


def main():
    core.carregar_env()
    ap = argparse.ArgumentParser(description="Coleta dados rotulados do Anima via MQTT")
    ap.add_argument("--id", help="id do dispositivo (anima/<id>/dados)")
    ap.add_argument("--rotulo", choices=ROTULOS, help="comportamento do animal durante a sessão")
    ap.add_argument("--animal", default="", help="nome/identificação do animal")
    ap.add_argument("--obs", default="", help="observações da sessão (local, contexto, quem segurava...)")
    ap.add_argument("--saida", default=None, help="CSV de saída (padrão: dados_reais/<data>_<rotulo>_<id>.csv)")
    ap.add_argument("--max-janelas", type=int, default=0, help="para sozinho após N janelas gravadas (0 = Ctrl+C)")
    ap.add_argument("--descartar-iniciais", type=int, default=3)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)
    if not args.id or not args.rotulo:
        ap.error("--id e --rotulo são obrigatórios")
    if not core.ID_VALIDO.match(args.id):
        ap.error("id inválido (use letras, números, '-' e '_')")

    saida = args.saida or PASTA_PADRAO / f"{datetime.now():%Y%m%d_%H%M%S}_{args.rotulo}_{args.id}.csv"
    coletor = Coletor(saida, args.rotulo, args.id, args.animal, args.obs, args.max_janelas, args.descartar_iniciais)
    cfg = core.config_mqtt()
    core.aviso_broker_publico(cfg)
    topico = f"anima/{args.id}/dados"
    cliente = core.conectar_mqtt(f"anima_coletor_{random.randint(0, 99999)}", cfg)

    def on_connect(c, userdata, flags, rc, properties=None):
        print(f"Conectado (rc={rc}). Assinando '{topico}'. Gravando em {saida}\nCtrl+C para encerrar.")
        c.subscribe(topico)

    def on_message(c, userdata, msg):
        try:
            coletor.receber(json.loads(msg.payload.decode("utf-8")))
        except (ValueError, UnicodeDecodeError):
            print("  mensagem ignorada: JSON inválido")
        if coletor.terminou:
            c.disconnect()

    cliente.on_connect, cliente.on_message = on_connect, on_message
    cliente.connect(cfg["host"], cfg["porta"], keepalive=60)
    try:
        cliente.loop_forever(retry_first_connection=True)
    except KeyboardInterrupt:
        print()
    finally:
        coletor.fechar()
        print(f"Sessão encerrada: {coletor.gravadas} janelas gravadas, {coletor.descartadas} descartadas, "
              f"{coletor.ignoradas_iniciais} iniciais ignoradas -> {saida}")


if __name__ == "__main__":
    main()
