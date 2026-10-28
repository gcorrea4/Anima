"""Selftest na escala do modelo (offset_coleira) e guarda contra sobrescrever o modelo oficial. Tudo em pasta temporária."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from features_v2 import MODELO_PADRAO

SERVIDOR = Path(__file__).resolve().parents[1]
IA = SERVIDOR.parent / "ia"


def _sha(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()


def _rodar(args, **kw):
    env = dict(os.environ, ANIMA_SEM_DOTENV="1", PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, *map(str, args)], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", timeout=300, **kw)


@pytest.fixture(scope="module")
def modelo_offset_menos4(tmp_path_factory):
    """Dataset sintético e modelo recalibrados com offset_coleira = -4 °C, em pasta temporária."""
    import pandas as pd
    from gerar_dataset_v2 import gerar
    from treino_v2 import treinar
    pasta = tmp_path_factory.mktemp("recalibrado")
    df, offset = gerar(n_por_classe=250, offset_coleira=-4.0)
    csv = pasta / "dataset_m4.csv"
    df.to_csv(csv, index=False)
    treinar(df, pasta, "v2", offset_coleira=-4.0, febre_min_corporal=39.5)
    return pasta, csv


# ---------------------------------------------------------------- guarda contra sobrescrita
def test_confirmar_sobrescrita_todos_os_casos(tmp_path):
    from treino_v2 import confirmar_sobrescrita
    novo, existente = tmp_path / "novo.pkl", tmp_path / "existe.pkl"
    existente.write_bytes(b"x")
    assert confirmar_sobrescrita(novo)                                             # não existe: segue
    assert confirmar_sobrescrita(existente, sim=True)                              # --sim: segue
    assert not confirmar_sobrescrita(existente, tty=False)                         # sem terminal e sem --sim: recusa
    assert confirmar_sobrescrita(existente, tty=True, entrada=lambda _: "s")       # confirmou
    assert not confirmar_sobrescrita(existente, tty=True, entrada=lambda _: "n")   # negou
    assert not confirmar_sobrescrita(existente, tty=True, entrada=lambda _: "")    # Enter = não

    def sem_stdin(_):
        raise EOFError
    assert not confirmar_sobrescrita(existente, tty=True, entrada=sem_stdin)       # stdin vazio: recusa, sem traceback


def test_treino_nao_sobrescreve_sem_confirmacao_e_sobrescreve_com_sim(modelo_offset_menos4):
    pasta, csv = modelo_offset_menos4
    pkl = pasta / "modelo_anima_rf_v2.pkl"
    antes = _sha(pkl)
    base = [IA / "treinar_modelo_v2.py", "--dataset", csv, "--offset-coleira", "-4", "--saida-dir", pasta]
    r = _rodar(base)
    assert r.returncode != 0 and "SOBRESCRITO" in r.stdout and "NÃO foi alterado" in r.stderr
    assert _sha(pkl) == antes                                                      # intacto
    r = _rodar(base + ["--sim"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert (pasta / "modelo_anima_rf_v2.meta.json").exists()


def test_modelo_oficial_nao_e_tocado_pelos_testes():
    if not MODELO_PADRAO.exists():
        pytest.skip("modelo oficial ausente")
    antes = _sha(MODELO_PADRAO)
    r = _rodar([IA / "treinar_modelo_v2.py"])           # sem --sim e sem terminal: tem que recusar
    assert r.returncode != 0
    assert _sha(MODELO_PADRAO) == antes


# ---------------------------------------------------------------- selftest na escala do modelo
def test_selftest_com_modelo_recalibrado_passa(modelo_offset_menos4):
    pasta, _ = modelo_offset_menos4
    r = _rodar([SERVIDOR / "consumidor_v2.py", "--modelo", pasta / "modelo_anima_rf_v2.pkl", "--selftest"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "offset_coleira do modelo = -4.0" in r.stdout and "limiar de segurança = 35.5" in r.stdout
    assert "FALHA" not in r.stdout


def test_selftest_com_offset_ignorado_falharia(modelo_offset_menos4, tmp_path):
    """Contraste: com o offset zerado no .meta.json (cenários na escala errada) o mesmo selftest falha."""
    import shutil
    pasta, _ = modelo_offset_menos4
    for nome in ("modelo_anima_rf_v2.pkl", "modelo_anima_rf_v2.meta.json"):
        shutil.copy(pasta / nome, tmp_path / nome)
    meta = tmp_path / "modelo_anima_rf_v2.meta.json"
    dados = json.loads(meta.read_text(encoding="utf-8"))
    dados["offset_coleira"] = 0.0
    meta.write_text(json.dumps(dados), encoding="utf-8")
    r = _rodar([SERVIDOR / "consumidor_v2.py", "--modelo", tmp_path / "modelo_anima_rf_v2.pkl", "--selftest"])
    assert r.returncode == 1 and "FALHA" in r.stdout


@pytest.mark.skipif(not MODELO_PADRAO.exists(), reason="modelo oficial ausente")
def test_selftest_com_modelo_oficial_continua_passando():
    r = _rodar([SERVIDOR / "consumidor_v2.py", "--selftest"])
    assert r.returncode == 0 and "offset_coleira do modelo = +0.0" in r.stdout
