"""
Anima v2 - Retreino combinando dataset sintético + dados REAIS coletados.

Os CSVs reais vêm de servidor/coletar_dados.py (mesmas colunas de FEATURES + 'classe').

Uso:
  python retreinar.py --real ../servidor/dados_reais/*.csv
  python retreinar.py --real sessao1.csv sessao2.csv --peso-real 5 --offset-coleira -4 --sufixo v2_real

Pontos de atenção:
  * Se o sensor da coleira mede pele/ambiente, a escala de temperatura real difere da sintética.
    Gere o sintético com o offset certo: python gerar_dataset_v2.py --offset-coleira X, e informe o mesmo X aqui.
  * --so-real treina apenas com os dados reais (recomendado quando houver dados suficientes de todas as classes).
  * Métricas são reportadas por origem; as de origem=real são as que importam, e só valem se o conjunto
    real for grande e vier de VÁRIOS animais/sessões (o split aqui é aleatório por janela, então janelas
    vizinhas da mesma sessão vazam entre treino e teste e inflam a métrica).
  * Salva com outro sufixo (padrão v2_real): NÃO sobrescreve o modelo sintético v2.
"""
import argparse
import glob
import sys
from pathlib import Path

import pandas as pd

from features_v2 import FEATURES, ROTULOS
from gerar_dataset_v2 import carregar_params
from treino_v2 import confirmar_sobrescrita, treinar

AQUI = Path(__file__).resolve().parent


def carregar_reais(padroes):
    arquivos = []
    for p in padroes:
        achados = glob.glob(p)
        arquivos += achados if achados else [p]
    partes = []
    for a in arquivos:
        if not Path(a).exists():
            sys.exit(f"Arquivo não encontrado: {a}")
        d = pd.read_csv(a)
        faltam = [c for c in FEATURES + ["classe"] if c not in d.columns]
        if faltam:
            sys.exit(f"{a}: colunas ausentes {faltam}")
        d["origem"] = "real"
        d["arquivo_origem"] = Path(a).name
        partes.append(d)
    real = pd.concat(partes, ignore_index=True)
    invalidas = set(real["classe"].unique()) - set(ROTULOS)
    if invalidas:
        sys.exit(f"Rótulos desconhecidos nos dados reais: {invalidas}")
    return real


def main():
    ap = argparse.ArgumentParser(description="Retreina o RF v2 com sintético + real")
    ap.add_argument("--real", nargs="+", required=True, help="CSV(s) de coletar_dados.py (aceita curingas)")
    ap.add_argument("--sintetico", default=str(AQUI / "dataset_anima_sintetico_v2.csv"))
    ap.add_argument("--so-real", action="store_true", help="ignora o sintético")
    ap.add_argument("--peso-real", type=float, default=3.0, help="peso das amostras reais no treino (padrão 3)")
    ap.add_argument("--offset-coleira", type=float, default=None,
                    help="offset de temperatura do sintético (mesmo valor usado em gerar_dataset_v2.py)")
    ap.add_argument("--sufixo", default="v2_real")
    ap.add_argument("--saida-dir", default=str(AQUI), help="onde salvar modelo e relatórios (padrão: esta pasta)")
    ap.add_argument("--sim", action="store_true", help="confirma a sobrescrita de um modelo já existente, sem perguntar")
    args = ap.parse_args()
    if args.sufixo == "v2" and not confirmar_sobrescrita(Path(args.saida_dir) / "modelo_anima_rf_v2.pkl", args.sim):
        sys.exit("Cancelado: o modelo OFICIAL (sufixo v2) NÃO foi alterado. Use outro --sufixo ou --saida-dir.")

    params = carregar_params()
    offset = params["offset_coleira"] if args.offset_coleira is None else args.offset_coleira
    real = carregar_reais(args.real)
    print("Janelas reais por classe:\n", real["classe"].value_counts().to_string())
    partes = [real]
    if not args.so_real:
        sint = pd.read_csv(args.sintetico)
        partes.append(sint)
        print(f"Janelas sintéticas: {len(sint)}")
    df = pd.concat(partes, ignore_index=True)
    faltantes = set(ROTULOS) - set(df["classe"].unique())
    if faltantes:
        sys.exit(f"Classes sem nenhuma amostra: {sorted(faltantes)}")

    modelo, m = treinar(df, args.saida_dir, args.sufixo, offset, params["febre_min_corporal"], peso_real=args.peso_real,
                        extra_meta={"peso_real": args.peso_real, "so_real": args.so_real},
                        titulo=f"Anima {args.sufixo} (sintético + real)")
    print(m["relatorio"])
    print(f"\nModelo salvo em {Path(args.saida_dir) / ('modelo_anima_rf_' + args.sufixo + '.pkl')} (+ .meta.json).")
    print("Use no servidor com:  python consumidor_v2.py --modelo", Path(args.saida_dir) / f"modelo_anima_rf_{args.sufixo}.pkl")


if __name__ == "__main__":
    main()
