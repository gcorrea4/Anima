"""v2/empacotar.py: exclui segredos/logs/caches, varre o conteúdo e aborta se achar token."""
import importlib.util
import zipfile
from pathlib import Path

import pytest

V2 = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("empacotar", V2 / "empacotar.py")
empacotar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(empacotar)

TOKEN_FALSO_TELEGRAM = "123456789:" + "A" * 35          # só o formato; não é um token real
TOKEN_FALSO_WOKWI = "wok_" + "B" * 40


def montar_arvore(raiz: Path):
    """Árvore falsa de v2 com tudo o que deve e o que NÃO deve entrar."""
    arquivos = {
        "README.md": "ok", ".env.example": "TELEGRAM_BOT_TOKEN=\n", "servidor/app.py": "print(1)",
        "ia/modelo.pkl": "bin", "docs/guia.md": "texto",
        # não devem entrar:
        "servidor/.env": f"TELEGRAM_BOT_TOKEN={TOKEN_FALSO_TELEGRAM}\nWOKWI_CLI_TOKEN={TOKEN_FALSO_WOKWI}\n",
        "servidor/.env.local": "x=1", "meu_token.txt": "x", "firmware/config_local.h": "#define X 1",
        "servidor/logs/decisoes_log.csv": "a,b", "servidor/dados_reais/s.csv": "a", "servidor/__pycache__/a.pyc": "b",
        ".pytest_cache/x": "y", "teste_wokwi_cli/build/firmware.bin": "bin", "servidor/x.log": "l", "venv/lib.py": "v",
        "antigo.zip": "z",
    }
    for rel, conteudo in arquivos.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(conteudo, encoding="utf-8")
    return arquivos


def test_pacote_limpo_nao_leva_segredos_nem_lixo(tmp_path):
    origem = tmp_path / "v2"
    montar_arvore(origem)
    saida = tmp_path / "out" / "v2_para_equipe.zip"
    codigo, nomes = empacotar.empacotar(origem, saida)
    assert codigo == 0 and saida.exists()
    with zipfile.ZipFile(saida) as z:
        no_zip = set(z.namelist())
    assert no_zip == set(nomes)
    assert {"LEIA-ME_DO_PACOTE.txt", "v2/README.md", "v2/.env.example", "v2/servidor/app.py", "v2/ia/modelo.pkl",
            "v2/docs/guia.md"} <= no_zip
    proibidos = [n for n in no_zip if n.endswith(("/.env", "/.env.local", "token.txt", "config_local.h", ".pyc", ".log", ".zip"))
                 or "/logs/" in n or "/dados_reais/" in n or "/build/" in n or "__pycache__" in n or "venv/" in n]
    assert proibidos == []
    # nenhum conteúdo do zip tem padrão de token
    with zipfile.ZipFile(saida) as z:
        for n in z.namelist():
            d = z.read(n)
            assert not any(rx.search(d) for rx in empacotar.PADROES_SEGREDO.values()), n


def test_listar_nao_grava_nada(tmp_path, capsys):
    origem = tmp_path / "v2"
    montar_arvore(origem)
    saida = tmp_path / "x.zip"
    codigo, nomes = empacotar.empacotar(origem, saida, so_listar=True)
    assert codigo == 0 and not saida.exists() and "v2/README.md" in nomes
    assert "Arquivos no pacote" in capsys.readouterr().out


def test_aborta_se_token_vazar_para_um_arquivo_incluido(tmp_path, capsys):
    origem = tmp_path / "v2"
    montar_arvore(origem)
    (origem / "docs" / "guia.md").write_text(f"cole aqui {TOKEN_FALSO_TELEGRAM} e {TOKEN_FALSO_WOKWI}", encoding="utf-8")
    saida = tmp_path / "out.zip"
    codigo, nomes = empacotar.empacotar(origem, saida)
    err = capsys.readouterr().err
    assert codigo == 1 and not saida.exists() and nomes == []
    assert "docs/guia.md" in err.replace("\\", "/") and "Telegram" in err and "Wokwi" in err
    assert TOKEN_FALSO_TELEGRAM not in err and TOKEN_FALSO_WOKWI not in err          # nunca imprime o valor


def test_o_v2_real_empacotaria_sem_segredos():
    """Simulação sobre o v2 de verdade (nada é gravado): o .env real não entra e nenhum arquivo incluído tem token."""
    incluidos, excluidos = empacotar.listar(V2)
    nomes = {f.name for f in incluidos}
    assert ".env" not in nomes and ".env.example" in nomes
    assert empacotar.varrer_segredos(incluidos) == []
    rels = {str(f.relative_to(V2)).replace("\\", "/") for f in incluidos}
    assert "empacotar.py" in rels and "teste_wokwi_cli/executar.py" in rels
    assert not any("__pycache__" in r or r.startswith("teste_wokwi_cli/build") or "/logs/" in r for r in rels)
