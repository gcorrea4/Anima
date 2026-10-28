"""
Gera a pasta wokwi/ a partir do firmware real, para manter UMA única fonte de código.

  sketch.ino  = cópia de anima_esp32_v2/anima_esp32_v2.ino
  config.h    = cópia de anima_esp32_v2/config.h com "#define ANIMA_WOKWI" no topo
                (Wi-Fi "Wokwi-GUEST", canal 6, sem senha)
  diagram.json = o da Entrega 2 com buzzer/LED em esp:18 em vez de esp:5 (o original não é alterado)
  libraries.txt = cópia de libraries_wokwi.txt (fonte própria da v2: versões fixadas + Adafruit BusIO)

Uso:  python gerar_wokwi.py          # regenera
      python gerar_wokwi.py --check  # só verifica se está sincronizado (usado nos testes)

No Wokwi: crie/abra o projeto, e cole/importe os 4 arquivos da pasta wokwi/.
"""
import argparse
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FONTE = AQUI / "anima_esp32_v2"
DESTINO = AQUI / "wokwi"
RAIZ_ENTREGA2 = AQUI / "base_entrega2"  # cópias somente leitura do diagram.json e libraries.txt da Entrega 2

CABECALHO_WOKWI = "#define ANIMA_WOKWI 1   // GERADO por gerar_wokwi.py - não edite este arquivo\n"


def ler(caminho):
    """Lê preservando as quebras de linha originais (sem normalizar CRLF/LF)."""
    with open(caminho, encoding="utf-8", newline="") as f:
        return f.read()


def diagrama_v2():
    """diagram.json da Entrega 2 (NÃO alterado) com o buzzer/LED movidos do GPIO 5 (strapping) para o GPIO 18."""
    d = ler(RAIZ_ENTREGA2 / "diagram.json")
    assert d.count('"esp:5"') == 2, "diagram.json da Entrega 2 mudou: revise a troca de pino"
    return d.replace('"esp:5"', '"esp:18"')


def conteudos():
    return {
        "sketch.ino": ler(FONTE / "anima_esp32_v2.ino"),
        "config.h": CABECALHO_WOKWI + ler(FONTE / "config.h"),
        "diagram.json": diagrama_v2(),
        "libraries.txt": ler(AQUI / "libraries_wokwi.txt"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    esperado = conteudos()
    if args.check:
        ruins = [n for n, c in esperado.items()
                 if not (DESTINO / n).exists() or ler(DESTINO / n) != c]
        if ruins:
            print("Fora de sincronia:", ", ".join(ruins), "-> rode gerar_wokwi.py")
            sys.exit(1)
        print("wokwi/ sincronizado.")
        return
    DESTINO.mkdir(exist_ok=True)
    for nome, conteudo in esperado.items():
        (DESTINO / nome).write_text(conteudo, encoding="utf-8", newline="\n")
        print("gerado", DESTINO / nome)


if __name__ == "__main__":
    main()
