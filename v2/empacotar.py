"""
Anima v2 - Gera o pacote da equipe (v2_para_equipe.zip) SEM segredos.

  python v2/empacotar.py                    # gera ../v2_para_equipe.zip (ao lado da pasta v2) e lista os arquivos
  python v2/empacotar.py --saida meu.zip    # outro destino
  python v2/empacotar.py --listar           # só lista o que entraria (nada é gravado)

Exclui: .env e .env.* (menos .env.example), qualquer arquivo com "token" no nome, config_local.h, logs, dados reais coletados,
caches (__pycache__, .pytest_cache), build/, venvs e arquivos .pyc/.log/.zip. Antes de gravar, VARRE o conteúdo dos arquivos que
vão entrar procurando padrões de token (Telegram, Wokwi); se achar algum, aborta (código 1), apaga o zip parcial e mostra só os
caminhos, nunca os valores.
"""
import argparse
import fnmatch
import re
import sys
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent

EXCLUIR_DIRS = {"__pycache__", ".pytest_cache", "logs", "dados_reais", "build", ".git", ".idea", "venv", ".venv", "node_modules"}
EXCLUIR_ARQ = [".env", ".env.*", "*token*", "config_local.h", "*.pyc", "*.log", "decisoes*.csv", "*.zip", "~$*"]
MANTER = {".env.example"}      # modelo sem valores
PADROES_SEGREDO = {
    "token do Telegram": re.compile(rb"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b"),
    "token do Wokwi": re.compile(rb"\bwok_[A-Za-z0-9]{20,}"),
}
LEIA_ME = """Anima v2 - pacote para a equipe
================================
Conteúdo: pasta v2/ (firmware, ia, servidor, docs, teste_wokwi_cli). Autossuficiente.

SEM SEGREDOS: não há .env, token, log, cache nem binários de build. Para usar o Telegram:
  copie v2/.env.example para v2/servidor/.env e preencha TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID (veja v2/docs/passo_a_passo.md).
O token do Wokwi (WOKWI_CLI_TOKEN) vai SOMENTE em variável de ambiente, nunca em arquivo (veja v2/docs/wokwi_cli.md).

Começo rápido:  pip install -r v2/servidor/requirements-dev.txt
                cd v2/servidor && python consumidor_v2.py --selftest && python -m pytest tests -q
Leia v2/README.md e v2/docs/relatorio_testes.md (o que foi testado e o que NÃO foi).
"""


def excluido(caminho: Path, origem: Path):
    rel = caminho.relative_to(origem)
    if set(rel.parts[:-1]) & EXCLUIR_DIRS:
        return True
    if caminho.name in MANTER:
        return False
    return any(fnmatch.fnmatch(caminho.name.lower(), pad.lower()) for pad in EXCLUIR_ARQ)


def listar(origem: Path):
    todos = sorted(f for f in origem.rglob("*") if f.is_file())
    incluidos = [f for f in todos if not excluido(f, origem)]
    excluidos = [f for f in todos if excluido(f, origem)]
    return incluidos, excluidos


def varrer_segredos(arquivos):
    """Devolve [(caminho, tipo)] dos arquivos cujo CONTEÚDO tem padrão de token. Nunca devolve o valor."""
    achados = []
    for f in arquivos:
        dados = f.read_bytes()
        for tipo, rx in PADROES_SEGREDO.items():
            if rx.search(dados):
                achados.append((f, tipo))
    return achados


def empacotar(origem: Path, saida: Path | None, so_listar=False):
    """Retorna (código de saída, lista de nomes no zip)."""
    incluidos, excluidos = listar(origem)
    achados = varrer_segredos(incluidos)
    if achados:
        for f, tipo in achados:
            print(f"ABORTADO: padrão de {tipo} em {f.relative_to(origem)} (valor omitido). Remova do arquivo e rode de novo.",
                  file=sys.stderr)
        return 1, []
    nomes = ["LEIA-ME_DO_PACOTE.txt"] + [f"{origem.name}/{f.relative_to(origem).as_posix()}" for f in incluidos]
    if not so_listar:
        saida.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("LEIA-ME_DO_PACOTE.txt", LEIA_ME)
            for f in incluidos:
                z.write(f, f"{origem.name}/{f.relative_to(origem).as_posix()}")
        # conferência final no zip já gravado
        with zipfile.ZipFile(saida) as z:
            ruins = [n for n in z.namelist()
                     if n.split("/")[-1].lower() == ".env" or "token" in n.lower() or "__pycache__" in n
                     or "/logs/" in n or "/build/" in n or n.endswith((".pyc", ".log"))]
        if ruins:
            saida.unlink(missing_ok=True)
            print("ABORTADO: o zip continha arquivos proibidos:", ruins, file=sys.stderr)
            return 1, []
    print(f"{'(simulação) ' if so_listar else ''}{len(nomes)} arquivos no pacote, {len(excluidos)} excluídos")
    print("excluídos:", ", ".join(str(f.relative_to(origem)).replace('\\', '/') for f in excluidos) or "nenhum")
    print("\nArquivos no pacote:")
    for n in nomes:
        print("  ", n)
    if not so_listar:
        print(f"\nGerado: {saida} ({saida.stat().st_size / 1024:.0f} KiB)")
    return 0, nomes


def main():
    ap = argparse.ArgumentParser(description="Gera v2_para_equipe.zip sem segredos")
    ap.add_argument("--origem", default=str(AQUI), help="pasta v2 a empacotar (padrão: a pasta deste script)")
    ap.add_argument("--saida", default=None, help="zip de saída (padrão: <pai de v2>/v2_para_equipe.zip)")
    ap.add_argument("--listar", action="store_true", help="só lista o que entraria; não grava nada")
    args = ap.parse_args()
    origem = Path(args.origem).resolve()
    saida = Path(args.saida) if args.saida else origem.parent / "v2_para_equipe.zip"
    codigo, _ = empacotar(origem, saida, so_listar=args.listar)
    sys.exit(codigo)


if __name__ == "__main__":
    main()
