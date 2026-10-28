"""Verificações ESTÁTICAS do firmware (não substitui compilar nem testar no Wokwi/hardware)."""
import re
import subprocess
import sys
from pathlib import Path

FW = Path(__file__).resolve().parents[2] / "firmware"
INO = (FW / "anima_esp32_v2" / "anima_esp32_v2.ino").read_text(encoding="utf-8")
CFG = (FW / "anima_esp32_v2" / "config.h").read_text(encoding="utf-8")


def test_wokwi_sincronizado_com_a_fonte():
    r = subprocess.run([sys.executable, str(FW / "gerar_wokwi.py"), "--check"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    assert r.returncode == 0, r.stdout + r.stderr


def test_wokwi_usa_wifi_guest_canal_6():
    cfg = (FW / "wokwi" / "config.h").read_text(encoding="utf-8")
    assert cfg.startswith("#define ANIMA_WOKWI")
    assert '"Wokwi-GUEST"' in cfg and "WIFI_CANAL_PADRAO    6" in cfg


def test_contrato_do_payload_e_topicos():
    for campo in ["versao", "n_amostras", "accel_mag_media", "accel_mag_std", "accel_mag_max",
                  "gyro_mag_media", "gyro_mag_std", "gyro_mag_max", "temperatura", "sensor_ok", "mpu_ok"]:
        assert f'\\"{campo}\\"' in INO, campo
    assert '"anima/%s/dados"' in INO and '"anima/%s/decisao"' in INO
    assert "57.2958" in INO
    assert "alerta_leve" in INO and "setCallback" in INO and "subscribe(topicoDecisao)" in INO


def test_robustez_presente():
    assert "t > -100.0f" in INO                      # descarta -127
    assert "setWaitForConversion(false)" in INO      # DS18B20 não bloqueante
    assert "mpuProximaTentativa" in INO              # reinit do MPU
    assert "wifiBackoff" in INO and "mqttBackoff" in INO
    assert "delay(" not in INO                       # loop sem delay
    assert "LIMIAR_TEMP_LOCAL_C" in INO and "39.5f" in CFG


def test_tudo_configuravel_em_config_h():
    for macro in ["WIFI_SSID", "WIFI_SENHA", "MQTT_BROKER", "MQTT_PORTA", "ANIMA_ID",
                  "TAXA_AMOSTRAGEM_HZ", "JANELA_MS"]:
        assert macro in CFG
    assert "ANIMA_ID" in INO and 'strcpy(id, "coleira01")' not in INO
    assert "#define ANIMA_ID" not in INO   # o id é definido só no config.h


def test_atuador_em_pino_seguro_gpio18():
    assert "#define PINO_ATUADOR  18" in CFG
    d = (FW / "wokwi" / "diagram.json").read_text(encoding="utf-8")
    assert '"esp:18"' in d and '"esp:5"' not in d
    original = (FW / "base_entrega2" / "diagram.json").read_text(encoding="utf-8")
    assert '"esp:5"' in original      # diagram.json da Entrega 2 continua intacto


def test_sem_segredos_no_firmware():
    assert "config_local.h" in CFG
    assert "SENHA_DA_SUA_REDE" in CFG   # só placeholder


def test_libraries_wokwi_com_versoes_fixas_e_cobrem_os_includes():
    linhas = [l.strip() for l in (FW / "wokwi" / "libraries.txt").read_text(encoding="utf-8").splitlines()
              if l.strip() and not l.strip().startswith("#")]
    nomes = {l.split("@")[0]: l.split("@")[1] if "@" in l else None for l in linhas}
    assert all(v and re.fullmatch(r"\d+\.\d+\.\d+", v) for v in nomes.values()), f"versão não fixada: {nomes}"
    # cada #include do .ino de uma biblioteca externa tem a sua biblioteca no libraries.txt (+ BusIO, dependência do MPU6050)
    mapa = {"PubSubClient.h": "PubSubClient", "Adafruit_MPU6050.h": "Adafruit MPU6050", "Adafruit_Sensor.h": "Adafruit Unified Sensor",
            "OneWire.h": "OneWire", "DallasTemperature.h": "DallasTemperature"}
    incluidos = set(re.findall(r"#include <([^>]+)>", INO))
    for header, lib in mapa.items():
        assert header in incluidos and lib in nomes, (header, lib)
    assert "Adafruit BusIO" in nomes
    assert nomes["Adafruit MPU6050"] == "2.2.9" and nomes["PubSubClient"] == "2.8.0"      # versões da compilação local
    # a cópia da Entrega 2 continua sem versões e intocada
    base = (FW / "base_entrega2" / "libraries.txt").read_text(encoding="utf-8")
    assert "@" not in base and "BusIO" not in base
