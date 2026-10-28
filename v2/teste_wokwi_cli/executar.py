"""
Testes do firmware v2 no simulador Wokwi via wokwi-cli.

Passos: (1) confere que wokwi/ está sincronizado, (2) compila a variante Wokwi com arduino-cli usando um ANIMA_ID
único (config_local.h só na pasta temporária de compilação), (3) copia firmware.bin/.elf e o diagram.json (GPIO 18)
para esta pasta, (4) roda os cenários de scenarios/*.yaml com wokwi-cli e confere os números do log serial.
Guia completo (instalação, variáveis, token, limites): v2/docs/wokwi_cli.md

Ferramentas (nenhum caminho fixo; tudo configurável):
  arduino-cli : --arduino-cli CAMINHO | env ANIMA_ARDUINO_CLI | <ANIMA_ARDUINO_DIR>/bin/arduino-cli | PATH
  wokwi-cli   : --wokwi-cli CAMINHO   | env WOKWI_CLI_EXE     | PATH
  pasta de dados do arduino-cli (opcional, instalação isolada com subpastas data/ user/ dl/):
                --arduino-dir PASTA   | env ANIMA_ARDUINO_DIR
Token: SOMENTE a variável de ambiente WOKWI_CLI_TOKEN (gere em https://wokwi.com/dashboard/ci). NUNCA é lido de arquivo
(nem do .env), nunca é impresso nem gravado. Para definir sem deixar no histórico do terminal:
  PowerShell:  $env:WOKWI_CLI_TOKEN = Read-Host "Token do Wokwi"
  bash:        read -rs WOKWI_CLI_TOKEN && export WOKWI_CLI_TOKEN

Uso:   python executar.py                 # tudo
       python executar.py --so-build      # só compila e prepara os arquivos (não precisa de token nem de wokwi-cli)
       python executar.py 01 03           # só os cenários cujo nome começa com 01 e 03

Limites do plano grátis (50 min/30 dias, 5 min por sessão): cada cenário usa --timeout curto.
"""
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FW = AQUI.parent / "firmware"
ID = "anima-wokwicli-" + secrets.token_hex(3)
TOKEN = ""        # definido em main(), só a partir do AMBIENTE
FERR = {}         # caminhos resolvidos em main()


def token_do_ambiente(env=None):
    """Token do Wokwi, lido SOMENTE da variável de ambiente WOKWI_CLI_TOKEN (nunca de arquivo)."""
    return (os.environ if env is None else env).get("WOKWI_CLI_TOKEN", "").strip()


def resolver_ferramentas(arduino_cli=None, wokwi_cli=None, arduino_dir=None, env=None, which=shutil.which):
    """Resolve os executáveis sem caminhos fixos. Devolve (dict, [avisos de ferramenta ausente])."""
    env = os.environ if env is None else env
    arduino_dir = arduino_dir or env.get("ANIMA_ARDUINO_DIR")
    ac = arduino_cli or env.get("ANIMA_ARDUINO_CLI")
    if not ac and arduino_dir:
        cand = Path(arduino_dir) / "bin" / ("arduino-cli.exe" if os.name == "nt" else "arduino-cli")
        ac = str(cand) if cand.exists() else None
    ac = ac or which("arduino-cli")
    wk = wokwi_cli or env.get("WOKWI_CLI_EXE") or which("wokwi-cli")
    ausentes = []
    if not ac:
        ausentes.append("arduino-cli não encontrado: instale-o e/ou use --arduino-cli, ANIMA_ARDUINO_CLI ou ANIMA_ARDUINO_DIR")
    if not wk:
        ausentes.append("wokwi-cli não encontrado: instale-o e/ou use --wokwi-cli ou WOKWI_CLI_EXE")
    return {"arduino_cli": ac, "wokwi_cli": wk, "arduino_dir": arduino_dir}, ausentes


# cenário -> timeout em ms de simulação
CENARIOS = {"01_boot_serial": 25000, "02_rede_wifi_mqtt": 45000, "03_febre_e_atuador": 30000, "04_imu_gyro_accel": 25000,
             "05_laco_com_servidor": 40000}


def limpo(texto):
    return texto.replace(TOKEN, "***") if TOKEN else texto


def build():
    r = subprocess.run([sys.executable, str(FW / "gerar_wokwi.py"), "--check"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    print(r.stdout.strip())
    if r.returncode:
        sys.exit("wokwi/ fora de sincronia")
    tmp = Path(tempfile.mkdtemp(prefix="anima_wokwicli_")) / "sketch"
    tmp.mkdir()
    for n in ("sketch.ino", "config.h"):
        shutil.copy(FW / "wokwi" / n, tmp / n)
    (tmp / "config_local.h").write_text(f'#define ANIMA_ID "{ID}"\n', encoding="utf-8")
    env = dict(os.environ)
    if FERR.get("arduino_dir"):     # instalação isolada do arduino-cli (subpastas data/ user/ dl/)
        base = Path(FERR["arduino_dir"])
        env.update(ARDUINO_DIRECTORIES_DATA=str(base / "data"), ARDUINO_DIRECTORIES_USER=str(base / "user"),
                   ARDUINO_DIRECTORIES_DOWNLOADS=str(base / "dl"))
    saida = tmp.parent / "build"
    r = subprocess.run([str(FERR["arduino_cli"]), "compile", "--fqbn", "esp32:esp32:esp32",
                        "--build-path", str(saida), str(tmp)], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    print("\n".join(l for l in r.stdout.splitlines() if l.startswith(("Sketch", "Global"))))
    if r.returncode:
        sys.exit("compilação falhou:\n" + r.stdout[-2000:] + r.stderr[-2000:])
    (AQUI / "build").mkdir(exist_ok=True)
    shutil.copy(saida / "sketch.ino.merged.bin", AQUI / "build" / "firmware.bin")
    shutil.copy(saida / "sketch.ino.elf", AQUI / "build" / "firmware.elf")
    shutil.copy(FW / "wokwi" / "diagram.json", AQUI / "diagram.json")
    print(f"Firmware compilado com ANIMA_ID={ID} e copiado para build/.")


def linhas_json(caminho):
    out = []
    for l in Path(caminho).read_text(encoding="utf-8", errors="replace").splitlines():
        i = l.find("{")
        if i >= 0 and '"versao":2' in l:
            try:
                out.append(json.loads(l[i:]))
            except ValueError:
                pass
    return out


def conferir(nome, log):
    """Confere números no log serial. Devolve lista de (descrição, ok)."""
    js = linhas_json(log)
    if not js:
        return [("há payload JSON no log", False)]
    u = js[-1]
    res = [("payload tem versao=2 e id do teste", u.get("versao") == 2 and u.get("id") == ID)]
    if nome.startswith("01"):
        res += [("n_amostras entre 40 e 55 (≈25 Hz × 2 s)", 40 <= u["n_amostras"] <= 55),
                ("accel_mag_media ≈ 9,81 m/s² (±0,3)", abs(u["accel_mag_media"] - 9.81) < 0.3),
                ("accel_mag_std < 0,3", u["accel_mag_std"] < 0.3),
                ("gyro_mag_media < 2 °/s", u["gyro_mag_media"] < 2),
                ("temperatura ≈ 38,5 (±0,2)", u["temperatura"] is not None and abs(u["temperatura"] - 38.5) < 0.2)]
    if nome.startswith("04"):
        res += [("accel_mag_media ≈ 19,6 m/s² (2 g, ±0,6)", abs(u["accel_mag_media"] - 19.62) < 0.6),
                ("gyro_mag_media ≈ 100 °/s (±4; unidade °/s, não rad/s)", abs(u["gyro_mag_media"] - 100) < 4)]
    return res


def assinante():
    """Escuta anima/<ID>/dados no broker REAL durante o cenário de rede (prova que o MQTT do Wokwi chegou lá)."""
    import paho.mqtt.client as mqtt
    v = getattr(mqtt, "CallbackAPIVersion", None)
    c = mqtt.Client(v.VERSION2, client_id="wokwicli-ouvinte-" + secrets.token_hex(3)) if v else mqtt.Client()
    msgs = []
    c.on_message = lambda cl, u, m: msgs.append(m.payload)
    c.on_connect = lambda cl, *a: cl.subscribe(f"anima/{ID}/dados")
    c.connect("broker.hivemq.com", 1883, keepalive=30)
    c.loop_start()
    return c, msgs


def rodar(nome, timeout):
    log = AQUI / "build" / f"{nome}.serial.log"
    cmd = [str(FERR["wokwi_cli"]), str(AQUI), "--scenario", str(AQUI / "scenarios" / f"{nome}.yaml"), "--timeout", str(timeout),
           "--serial-log-file", str(log), "--timeout-exit-code", "42"]
    ouvinte = msgs = None
    servidor = None
    if nome.startswith("05"):   # servidor real em paralelo, só para este id, no broker público
        senv = {k: v for k, v in os.environ.items() if not k.startswith(("ANIMA_MQTT", "ANIMA_TELEGRAM", "TELEGRAM_"))}
        senv.update(PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", ANIMA_SEM_DOTENV="1")   # sem Telegram real
        slog = AQUI / "build" / "servidor_05.csv"
        slog.unlink(missing_ok=True)
        servidor = subprocess.Popen([sys.executable, str(AQUI.parent / "servidor" / "consumidor_v2.py"), "--id", ID,
                                     "--log", str(slog)], env=senv, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
        saida_srv = []
        threading.Thread(target=lambda: [saida_srv.append(l) for l in servidor.stdout], daemon=True).start()
        fim = time.time() + 60
        while time.time() < fim and not any("Assinando" in l for l in saida_srv):
            time.sleep(0.2)
        time.sleep(2)
    if nome.startswith("02"):
        ouvinte, msgs = assinante()
        time.sleep(1.5)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
    dur = time.time() - t0
    if servidor:
        servidor.terminate()
    if ouvinte:
        time.sleep(2)
        ouvinte.loop_stop()
    print(f"\n=== {nome} (exit={r.returncode}, {dur:.0f} s de relógio) ===")
    print(limpo((r.stdout + r.stderr)[-1500:]))
    checks = conferir(nome, log) if r.returncode == 0 and log.exists() else []
    if servidor:
        texto = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        linhas_srv = (AQUI / "build" / "servidor_05.csv").read_text(encoding="utf-8").splitlines() if (AQUI / "build" / "servidor_05.csv").exists() else []
        checks += [("ESP32 recebeu decisão 'nenhum' do servidor", '"acao": "nenhum"' in texto),
                   ("ESP32 recebeu decisão 'alerta' do servidor", '"acao": "alerta"' in texto),
                   (f"servidor registrou janelas do Wokwi no log CSV ({max(len(linhas_srv) - 1, 0)} linhas)", len(linhas_srv) > 3)]
    if msgs is not None:
        checks.append((f"broker real recebeu payloads do Wokwi em anima/{ID}/dados (n={len(msgs)})", len(msgs) >= 1))
    for d, ok in checks:
        print(("  OK    " if ok else "  FALHA ") + d)
    return r.returncode == 0 and all(ok for _, ok in checks)


def criar_parser():
    ap = argparse.ArgumentParser(description="Cenários do firmware v2 no Wokwi via wokwi-cli (guia: v2/docs/wokwi_cli.md)")
    ap.add_argument("prefixos", nargs="*", help="prefixos dos cenários (ex.: 01 05); vazio = todos")
    ap.add_argument("--so-build", action="store_true", help="só compila e prepara build/ (sem token, sem wokwi-cli)")
    ap.add_argument("--arduino-cli", default=None, help="caminho do arduino-cli (ou env ANIMA_ARDUINO_CLI; senão, PATH)")
    ap.add_argument("--wokwi-cli", default=None, help="caminho do wokwi-cli (ou env WOKWI_CLI_EXE; senão, PATH)")
    ap.add_argument("--arduino-dir", default=None,
                    help="instalação isolada do arduino-cli com subpastas data/ user/ dl/ (ou env ANIMA_ARDUINO_DIR)")
    return ap


def main():
    global TOKEN, FERR
    args = criar_parser().parse_args()
    FERR, ausentes = resolver_ferramentas(args.arduino_cli, args.wokwi_cli, args.arduino_dir)
    exigidas = [a for a in ausentes if a.startswith("arduino-cli") or (not args.so_build and a.startswith("wokwi-cli"))]
    if exigidas:
        sys.exit("ERRO: " + "\nERRO: ".join(exigidas))
    if not args.so_build:
        TOKEN = token_do_ambiente()
        if not TOKEN:
            sys.exit("ERRO: WOKWI_CLI_TOKEN não está no ambiente. Gere o token em https://wokwi.com/dashboard/ci e defina a variável "
                     "(nunca em arquivo):\n  PowerShell:  $env:WOKWI_CLI_TOKEN = Read-Host \"Token do Wokwi\"\n"
                     "  bash:        read -rs WOKWI_CLI_TOKEN && export WOKWI_CLI_TOKEN")
    build()
    if args.so_build:
        return
    escolhidos = {n: t for n, t in CENARIOS.items() if not args.prefixos or n[:2] in [p[:2] for p in args.prefixos]}
    resultados = {n: rodar(n, t) for n, t in escolhidos.items()}
    print("\nResumo:")
    for n, ok in resultados.items():
        print(f"  {n:24s} {'passou' if ok else 'FALHOU'}")
    sys.exit(0 if all(resultados.values()) else 1)


if __name__ == "__main__":
    main()
