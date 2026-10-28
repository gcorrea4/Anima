"""Validação ESTÁTICA do teste_wokwi_cli/executar.py (o wokwi-cli NÃO é executado aqui): portabilidade e token só do ambiente."""
import ast
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

DIR = Path(__file__).resolve().parents[2] / "teste_wokwi_cli"
ARQ = DIR / "executar.py"
spec = importlib.util.spec_from_file_location("executar_wokwi", ARQ)
ex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ex)

TOKEN_FALSO = "wok_" + "C" * 40


def _strings(arvore):
    return [n.value for n in ast.walk(arvore) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_sem_caminhos_absolutos_nem_usuario_fixo():
    arvore = ast.parse(ARQ.read_text(encoding="utf-8"))
    for s in _strings(arvore):
        assert not re.match(r"^[A-Za-z]:[\\/]", s), f"caminho absoluto de Windows: {s[:60]}"
        assert "Users\\" not in s and "Users/" not in s, s[:60]
        assert "Gabriel" not in s, s[:60]
    assert "Gabriel" not in ARQ.read_text(encoding="utf-8")


def test_token_vem_so_do_ambiente_e_nunca_de_arquivo():
    codigo = ARQ.read_text(encoding="utf-8")
    arvore = ast.parse(codigo)
    # o código não procura "WOKWI_CLI_TOKEN=" em arquivo nem abre .env
    for s in _strings(arvore):
        if s.startswith("WOKWI_CLI_TOKEN="):
            pytest.fail("o código parece ler o token de um arquivo")
    # a função do token não lê arquivo nenhum
    fn = next(n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == "token_do_ambiente")
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr in ("read_text", "read_bytes", "open") for n in ast.walk(fn))
    # e o módulo não menciona um arquivo .env (fora de comentários/docstring; "os.environ" não conta)
    corpo = "\n".join(l for l in codigo.splitlines() if not l.lstrip().startswith("#"))
    sem_docstring = re.sub(r'""".*?"""', "", corpo, flags=re.S)
    assert not re.search(r"\.env(?!iron)", sem_docstring)
    assert ex.token_do_ambiente({"WOKWI_CLI_TOKEN": f"  {TOKEN_FALSO}  "}) == TOKEN_FALSO
    assert ex.token_do_ambiente({}) == ""
    assert TOKEN_FALSO not in codigo


def test_nenhum_token_em_arquivos_do_teste_wokwi_cli():
    rx = re.compile(rb"\bwok_[A-Za-z0-9]{20,}")
    for f in DIR.rglob("*"):
        if f.is_file() and "build" not in f.parts:
            assert not rx.search(f.read_bytes()), f"padrão de token em {f.name}"


def test_resolver_ferramentas_precedencia_e_ausencia(tmp_path):
    assert ex.resolver_ferramentas(env={}, which=lambda n: None)[1]            # nada achado: 2 avisos
    ferr, ausentes = ex.resolver_ferramentas(env={}, which=lambda n: f"/bin/{n}")   # só PATH
    assert ferr["arduino_cli"] == "/bin/arduino-cli" and ferr["wokwi_cli"] == "/bin/wokwi-cli" and ausentes == []
    ferr, _ = ex.resolver_ferramentas(env={"ANIMA_ARDUINO_CLI": "/env/ac", "WOKWI_CLI_EXE": "/env/wk"}, which=lambda n: "/path")
    assert (ferr["arduino_cli"], ferr["wokwi_cli"]) == ("/env/ac", "/env/wk")      # ambiente vence o PATH
    ferr, _ = ex.resolver_ferramentas("/arg/ac", "/arg/wk", env={"ANIMA_ARDUINO_CLI": "/env/ac"}, which=lambda n: "/path")
    assert (ferr["arduino_cli"], ferr["wokwi_cli"]) == ("/arg/ac", "/arg/wk")      # argumento vence tudo
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    exe = bin_ / ("arduino-cli.exe" if os.name == "nt" else "arduino-cli")
    exe.write_text("x")
    ferr, _ = ex.resolver_ferramentas(arduino_dir=str(tmp_path), env={}, which=lambda n: None)
    assert ferr["arduino_cli"] == str(exe) and ferr["arduino_dir"] == str(tmp_path)  # instalação isolada por pasta


def _rodar(args, env_extra=None, sem_token=True):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if sem_token:
        env.pop("WOKWI_CLI_TOKEN", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(ARQ), *args], env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_help_funciona_sem_token_nem_ferramentas():
    r = _rodar(["--help"])
    assert r.returncode == 0 and "--arduino-cli" in r.stdout and "--wokwi-cli" in r.stdout and "--arduino-dir" in r.stdout


def test_sem_token_recusa_antes_de_compilar_e_sem_vazar_nada():
    r = _rodar(["--arduino-cli", sys.executable, "--wokwi-cli", sys.executable, "01"])
    assert r.returncode != 0 and "WOKWI_CLI_TOKEN não está no ambiente" in r.stderr
    assert "Read-Host" in r.stderr                                      # ensina a definir sem deixar no histórico
    assert "Sketch uses" not in r.stdout                                # nada foi compilado


def test_sem_ferramentas_explica_como_configurar():
    r = _rodar(["--so-build"], env_extra={"PATH": str(DIR)})              # PATH sem arduino-cli
    assert r.returncode != 0 and "arduino-cli não encontrado" in r.stderr and "ANIMA_ARDUINO_CLI" in r.stderr


def test_cenarios_yaml_sao_validos_e_cobrem_o_gpio_18():
    yaml = pytest.importorskip("yaml")
    nomes = set()
    for f in sorted((DIR / "scenarios").glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert d["version"] == 1 and d["steps"], f.name
        nomes.add(f.stem)
    assert nomes == set(ex.CENARIOS)                                    # todo cenário do executor existe como arquivo
    pinos = re.findall(r"name: (\d+)", (DIR / "scenarios" / "03_febre_e_atuador.yaml").read_text(encoding="utf-8"))
    assert pinos and set(pinos) == {"18"}
