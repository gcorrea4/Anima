import sys
from pathlib import Path

import pytest

SERVIDOR = Path(__file__).resolve().parents[1]
IA = SERVIDOR.parent / "ia"
for p in (SERVIDOR, IA, Path(__file__).resolve().parent):
    sys.path.insert(0, str(p))

from features_v2 import MODELO_PADRAO  # noqa: E402


def payload_v2(temp=38.5, movimento="normal", **extra):
    base = {
        "parado": (9.81, 0.05, 9.95, 1.0, 0.4, 2.2),
        "normal": (9.9, 1.0, 13.0, 25.0, 14.0, 70.0),
        "agitado": (11.2, 3.5, 30.0, 100.0, 75.0, 400.0),
    }[movimento]
    p = {"versao": 2, "id": "teste", "n_amostras": 50, "temperatura": temp, "sensor_ok": True, "mpu_ok": True}
    p.update(dict(zip(["accel_mag_media", "accel_mag_std", "accel_mag_max",
                       "gyro_mag_media", "gyro_mag_std", "gyro_mag_max"], base)))
    p.update(extra)
    return p


@pytest.fixture(scope="session")
def modelo_real():
    if not MODELO_PADRAO.exists():
        pytest.skip("modelo_anima_rf_v2.pkl não encontrado (rode ia/treinar_modelo_v2.py)")
    import joblib
    return joblib.load(MODELO_PADRAO)


class ModeloFalso:
    """Modelo determinístico para testar regras sem depender do Random Forest."""
    classes_ = ["agitado", "febre", "normal", "parado"]

    def __init__(self, classe="normal", conf=0.9):
        self.classe, self.conf = classe, conf

    def predict_proba(self, X):
        resto = (1 - self.conf) / 3
        return [[self.conf if c == self.classe else resto for c in self.classes_]]
