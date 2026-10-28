"""
Anima v2 - Treina o Random Forest v2 com o dataset sintético.

Uso:
  python treinar_modelo_v2.py                 # usa dataset_anima_sintetico_v2.csv
  python treinar_modelo_v2.py --offset-coleira -4  # só registra o offset no meta (o dataset deve ter sido gerado com o mesmo)

Saídas (nesta pasta): modelo_anima_rf_v2.pkl, modelo_anima_rf_v2.meta.json,
relatorio_classificacao_v2.txt, matriz_confusao_v2.png/.csv, importancia_variaveis_v2.png/.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from gerar_dataset_v2 import carregar_params
from treino_v2 import confirmar_sobrescrita, teste_parado_febre, treinar

AQUI = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(AQUI / "dataset_anima_sintetico_v2.csv"))
    ap.add_argument("--offset-coleira", type=float, default=None,
                    help="offset usado ao gerar o dataset (padrão: o de params_sinteticos.json)")
    ap.add_argument("--saida-dir", default=str(AQUI), help="pasta de saída (padrão: ia/, onde fica o modelo OFICIAL)")
    ap.add_argument("--sufixo", default="v2", help="sufixo do arquivo: modelo_anima_rf_<sufixo>.pkl (padrão v2 = oficial)")
    ap.add_argument("--sim", action="store_true", help="confirma a sobrescrita de um modelo já existente, sem perguntar")
    args = ap.parse_args()
    destino = Path(args.saida_dir) / f"modelo_anima_rf_{args.sufixo}.pkl"
    if not confirmar_sobrescrita(destino, args.sim):
        sys.exit("Cancelado: o modelo existente NÃO foi alterado.")

    params = carregar_params()
    offset = params["offset_coleira"] if args.offset_coleira is None else args.offset_coleira
    df = pd.read_csv(args.dataset)
    modelo, m = treinar(df, args.saida_dir, args.sufixo, offset, params["febre_min_corporal"])
    print(m["relatorio"])

    classe, probs = teste_parado_febre(modelo)
    print("\nTeste explícito (parado + 40,1 °C):", classe, {k: round(v, 3) for k, v in probs.items()})
    if offset != 0:
        print("(com offset_coleira != 0 este cenário usa a escala corporal; ajuste a temperatura de teste)")
    elif classe != "febre":
        sys.exit("FALHOU: parado + 40,1 °C não foi classificado como febre")
    print("\nModelo salvo em", destino)


if __name__ == "__main__":
    main()
