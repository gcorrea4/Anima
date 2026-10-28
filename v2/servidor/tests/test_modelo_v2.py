"""Testes com o modelo v2 real (sintético). Pulados se o .pkl não existir."""
import anima_core as core
from conftest import payload_v2
from features_v2 import carregar_meta, MODELO_PADRAO


def test_parado_com_40_1_graus_e_febre(modelo_real):
    classe, conf, probs = core.classificar(modelo_real, core.validar_payload(payload_v2(40.1, "parado")))
    assert classe == "febre"
    assert conf > 0.6


def test_parado_com_40_1_graus_gera_alerta_apos_debounce(modelo_real):
    pipe = core.Pipeline(modelo_real, core.Debounce(2, 300), temp_seguranca=39.5)
    pipe.processar("c", payload_v2(40.1, "parado"))
    assert pipe.processar("c", payload_v2(40.1, "parado"))["acao"] == "alerta"


def test_cenarios_basicos(modelo_real):
    def cls(t, mov):
        return core.classificar(modelo_real, core.validar_payload(payload_v2(t, mov)))[0]
    assert cls(38.3, "parado") == "parado"
    assert cls(38.5, "normal") == "normal"
    assert cls(38.8, "agitado") == "agitado"


def test_meta_do_modelo():
    m = carregar_meta(MODELO_PADRAO)
    if not m:
        return
    assert m["features"] and m["seed"] == 42 and "temp_seguranca_coleira" in m
