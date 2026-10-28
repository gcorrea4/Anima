"""
Anima v2 - Compara o modelo v1 (Entrega 2) com o v2 em cenários explícitos.

IMPORTANTE: as métricas dos dois modelos vêm de datasets sintéticos DIFERENTES
(v1: leitura instantânea; v2: estatísticas de janela) e de geradores diferentes,
então NÃO são comparáveis entre si. A comparação justa possível sem dados reais é
o comportamento nos mesmos cenários físicos, especialmente "parado + febre".

Gera ../docs/comparacao_v1_v2.md. Só LÊ os arquivos da Entrega 2 (não altera nada).
"""
import warnings
from pathlib import Path

import joblib
import pandas as pd

from features_v2 import FEATURES
from treino_v2 import teste_parado_febre

warnings.filterwarnings("ignore")
AQUI = Path(__file__).resolve().parent
RAIZ = AQUI / "v1_referencia"   # cópias do modelo v1 e do relatório da Entrega 2
FEATURES_V1 = ["accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z", "temperatura", "accel_mag", "gyro_mag"]

# cenário: (descrição, leitura instantânea para a v1, estatísticas de janela para a v2)
def v1(ax, ay, az, gx, gy, gz, t):
    import math
    return dict(accel_x=ax, accel_y=ay, accel_z=az, gyro_x=gx, gyro_y=gy, gyro_z=gz, temperatura=t,
                accel_mag=math.sqrt(ax**2 + ay**2 + az**2), gyro_mag=math.sqrt(gx**2 + gy**2 + gz**2))

def v2(am, asd, amax, gm, gsd, gmax, t):
    return dict(accel_mag_media=am, accel_mag_std=asd, accel_mag_max=amax,
                gyro_mag_media=gm, gyro_mag_std=gsd, gyro_mag_max=gmax, temperatura=t)

CENARIOS = [
    ("Parado, temperatura normal (38,3 °C)", v1(0.01, 0.03, 9.79, 0.4, 0.6, 0.3, 38.3), v2(9.81, 0.05, 9.95, 1.0, 0.4, 2.2, 38.3)),
    ("Movimento normal (38,6 °C)", v1(0.35, 0.18, 9.75, 6, 4, 5, 38.6), v2(9.9, 1.0, 13.0, 25, 14, 70, 38.6)),
    ("Agitado (38,8 °C)", v1(0.5, 0.4, 9.9, 15, 12, 10, 38.8), v2(11.2, 3.5, 30, 100, 75, 400, 38.8)),
    ("Movimento normal + febre (40,1 °C)", v1(0.28, 0.22, 9.78, 4, 3, 4, 40.1), v2(9.9, 1.0, 13.0, 25, 14, 70, 40.1)),
    ("PARADO + FEBRE (40,1 °C)", v1(0.01, 0.03, 9.79, 0.4, 0.6, 0.3, 40.1), v2(9.81, 0.05, 9.95, 1.0, 0.4, 2.2, 40.1)),
]


def fmt(probs):
    return ", ".join(f"{k}={v:.0%}" for k, v in sorted(probs.items(), key=lambda kv: -kv[1]) if v >= 0.01)


def main():
    m1 = joblib.load(RAIZ / "modelo_anima_rf.pkl")
    m2 = joblib.load(AQUI / "modelo_anima_rf_v2.pkl")
    linhas = []
    for nome, x1, x2 in CENARIOS:
        p1 = m1.predict_proba(pd.DataFrame([x1])[FEATURES_V1])[0]
        p2 = m2.predict_proba(pd.DataFrame([x2])[FEATURES])[0]
        d1 = dict(zip(map(str, m1.classes_), p1))
        d2 = dict(zip(map(str, m2.classes_), p2))
        linhas.append((nome, max(d1, key=d1.get), fmt(d1), max(d2, key=d2.get), fmt(d2)))

    rel1 = (RAIZ / "classification_report.txt").read_text(encoding="utf-8").splitlines()
    acc1 = rel1[0].split(":")[1].strip()
    rel2 = (AQUI / "relatorio_classificacao_v2.txt").read_text(encoding="utf-8")
    acc2 = [l for l in rel2.splitlines() if l.startswith("Acurácia")][0]

    md = ["# Comparação modelo v1 × v2", "",
          "> **Todos os números abaixo vêm de dados sintéticos.** Nada foi validado em hardware nem em animais reais.",
          "> As métricas de v1 e v2 usam datasets diferentes (leitura instantânea × estatísticas de janela) e",
          "> **não são comparáveis diretamente**; a tabela de cenários é a comparação mais honesta disponível.", "",
          "| | v1 (Entrega 2) | v2 |", "|---|---|---|",
          "| Entrada | 1 leitura instantânea (9 variáveis) | janela de 2 s a 25 Hz: média/desvio/máx de accel_mag e gyro_mag + temperatura (7 variáveis) |",
          "| Classes | normal, letargico, agitado, febre | parado, normal, agitado, febre |",
          f"| Acurácia no teste sintético | {acc1} | {acc2.split(':')[1].split()[0]} |",
          "| Hiperparâmetros | RF 200 árvores, prof. 8, seed 42 | iguais |", "",
          "## Cenários explícitos", "",
          "| Cenário | v1: classe | v1: probabilidades | v2: classe | v2: probabilidades |", "|---|---|---|---|---|"]
    for nome, c1, p1, c2, p2 in linhas:
        md.append(f"| {nome} | {c1} | {p1} | {c2} | {p2} |")
    classe, probs = teste_parado_febre(m2)
    md += ["", f"Teste explícito v2 (parado + 40,1 °C): **{classe}** ({fmt(probs)}).", "",
           "## Observações", "",
           "- Os cenários da v2 são valores escolhidos à mão, coerentes com o gerador sintético; não são medições.",
           "- Para a v1 cada cenário é UMA leitura instantânea escolhida por mim (ex.: 'agitado' com giroscópio de ~15 °/s, que o v1 vê como normal). Uma única leitura de um animal agitado pode cair em qualquer ponto; isso ilustra a fragilidade da leitura instantânea, mas não prova que o v1 erra em geral.",
           "- A v1 não tinha a combinação *parado + febre* no treino; veja a linha correspondente acima para o comportamento real do pkl da v1.",
           "- A v2 separa febre quase só pela temperatura por construção do gerador (classes truncadas em 39,5 °C). Com dados reais, esse limite será nebuloso.",
           "- A confusão remanescente da v2 é entre *parado* e *normal*, causada pelas janelas 'mistas' do gerador (mudança de comportamento no meio da janela).",
           "- O modelo v1 e os arquivos da Entrega 2 não foram alterados."]
    destino = AQUI.parent / "docs" / "comparacao_v1_v2.md"
    destino.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print("\nGravado em", destino)


if __name__ == "__main__":
    main()
