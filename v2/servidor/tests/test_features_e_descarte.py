import pytest

import anima_core as core
from conftest import payload_v2
from features_v2 import FEATURES, estatisticas_janela


def test_montagem_de_features_ordem_e_valores():
    v = core.validar_payload(payload_v2(38.7, "agitado"))
    X = core.montar_features(v)
    assert list(X.columns) == FEATURES
    assert X.shape == (1, 7)
    assert X["temperatura"][0] == 38.7
    assert X["accel_mag_std"][0] == 3.5


def test_estatisticas_de_janela_como_no_firmware():
    import numpy as np
    a = np.array([9.8, 9.9, 9.7, 10.2])
    g = np.array([0.0, 2.0, 4.0, 6.0])
    e = estatisticas_janela(a, g)
    assert e["accel_mag_media"] == pytest.approx(9.9)
    assert e["accel_mag_std"] == pytest.approx(a.std())      # populacional (ddof=0), igual ao firmware
    assert e["gyro_mag_max"] == 6.0


@pytest.mark.parametrize("mudanca, trecho", [
    ({"temperatura": -127.0}, "-127"),
    ({"temperatura": -127}, "-127"),
    ({"temperatura": None}, "temperatura"),
    ({"sensor_ok": False, "temperatura": None}, "sensor_ok"),
    ({"mpu_ok": False}, "mpu_ok"),
    ({"versao": 1}, "versao"),
    ({"n_amostras": 5}, "incompleta"),
    ({"temperatura": "abc"}, "inválida"),
])
def test_leituras_descartadas(mudanca, trecho):
    with pytest.raises(core.PayloadDescartado) as e:
        core.validar_payload(payload_v2(**mudanca))
    assert trecho in str(e.value)


def test_campo_ausente_e_nao_finito():
    p = payload_v2()
    del p["gyro_mag_std"]
    with pytest.raises(core.PayloadDescartado, match="ausente"):
        core.validar_payload(p)
    with pytest.raises(core.PayloadDescartado):
        core.validar_payload(payload_v2(accel_mag_media=float("nan")))
    with pytest.raises(core.PayloadDescartado):
        core.validar_payload([1, 2, 3])


def test_pipeline_nao_classifica_nem_loga_como_decisao_quando_descarta(tmp_path):
    from conftest import ModeloFalso
    log = core.LogDecisoes(tmp_path / "log.csv")
    pipe = core.Pipeline(ModeloFalso("febre"), log=log)
    assert pipe.processar("c1", payload_v2(-127.0)) is None
    linhas = (tmp_path / "log.csv").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2 and "descartada" in linhas[1]
