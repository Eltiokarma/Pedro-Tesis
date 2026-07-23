"""Auditoría con libros — Frente E: rigor de libro en el resto del
catálogo (bombas, válvulas, HX, compresores).

Método CASOS_LIBRO: cada checkpoint recomputa la identidad del libro A
MANO dentro del test (fórmula transcripta del libro, no leída del
repo).

1. Bomba — velocidad específica N_s = N·√Q[gpm]/H[ft]^0.75 y la
   clasificación de rodete de Perry 8ª fig. 10-32 (radial / mixto /
   axial).
2. Válvula — C_v de Crane TP-410 ec. 3-16: por DEFINICIÓN, 1 gpm de
   agua (SG≈1) con 1 psi de caída ⇒ C_v ≈ 1.
3. HX — factor F de Bowman (1940): la implementación del repo contra
   la fórmula cerrada publicada (transcripta acá), en puntos R≠1 y el
   límite F(P→0)=1.
4. Compresor — k = Cp/(Cp−R) del aire a 25 °C vs el 1.400 publicado
   (Cengel, tabla A-2); valida la capa Cp que alimenta el diseño.
"""
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest


# ── 1. Bomba: N_s y rodete (Perry fig. 10-32) ─────────────────────────
def test_ns_identidad_y_rodete():
    import equipment_design as ed
    ps = ed.pump_sizing(m_kg_s=10.0, dp_bar=3.0, rho_kg_m3=997.0,
                        eta_hyd=0.75)
    assert ps is not None and ps["Ns_us"] is not None
    # identidad recomputada a mano (US customary)
    Q_gpm = ps["Q_m3_h"] * 4.40287
    H_ft = ps["head_m"] / 0.3048
    Ns_mano = 3550.0 * math.sqrt(Q_gpm) / (H_ft ** 0.75)
    assert ps["Ns_us"] == pytest.approx(Ns_mano, rel=1e-9)
    # 36 m³/h contra 30.7 m: bomba de proceso clásica → rodete radial
    assert ps["impeller_type"] == "radial", ps


def test_ns_clasificacion_perry():
    """Los cortes de Perry fig. 10-32 en sus tres ramas: head muy alto
    con caudal chico cae bajo Ns=500 (territorio de desplazamiento
    positivo/multietapa), proceso típico → radial, head bajo con caudal
    enorme → axial."""
    import equipment_design as ed
    pd_case = ed.pump_sizing(m_kg_s=2.0, dp_bar=8.0, rho_kg_m3=997.0)
    assert pd_case["Ns_us"] < 500, pd_case["Ns_us"]
    assert "desplazamiento positivo" in pd_case["impeller_type"]
    radial = ed.pump_sizing(m_kg_s=10.0, dp_bar=3.0, rho_kg_m3=997.0)
    assert 500 <= radial["Ns_us"] < 4000, radial["Ns_us"]
    assert radial["impeller_type"] == "radial"
    axial = ed.pump_sizing(m_kg_s=400.0, dp_bar=0.15, rho_kg_m3=997.0)
    assert axial["Ns_us"] > 9000, axial["Ns_us"]
    assert "axial" in axial["impeller_type"]


# ── 2. Válvula: C_v de Crane ──────────────────────────────────────────
def test_cv_definicion_crane():
    """1 gpm de agua con ΔP = 1 psi ⇒ C_v = √SG ≈ 1 (definición)."""
    from types import SimpleNamespace
    from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
    import pressure_drop as pd
    import inspector_evidence as ev

    T_C = 25.0
    rho = pd._density_kg_m3({"water": 1.0}, T_C + 273.15, "liquid")
    # caudal masa para EXACTAMENTE 1 gpm con esa densidad
    Q_m3_h = 1.0 / 4.40287
    m_kg_s = Q_m3_h / 3600.0 * rho
    m_tm_y = m_kg_s * SEC_PER_YEAR / TM_TO_KG
    feed = SimpleNamespace(mass_flow=m_tm_y, temperature=T_C,
                           phase="liquid", composition={"water": 1.0},
                           main_component="water")
    dp_bar = 1.0 / 14.5038                     # 1 psi
    cv = ev._valve_cv_liquid(feed, P_in_bar=2.0, P_out_bar=2.0 - dp_bar)
    SG = rho / 999.0
    assert cv == pytest.approx(math.sqrt(SG), rel=1e-6)
    assert cv == pytest.approx(1.0, abs=0.01)  # agua ≈ referencia Crane
    # gas o sin caída → None (la identidad es de servicio líquido)
    feed.phase = "gas"
    assert ev._valve_cv_liquid(feed, 2.0, 1.9) is None
    feed.phase = "liquid"
    assert ev._valve_cv_liquid(feed, 2.0, 2.0) is None


# ── 3. HX: factor F de Bowman vs fórmula publicada ────────────────────
def _f_bowman_libro(R, P):
    """Bowman, Mueller & Nagle (1940), 1 carcasa / 2n pasos de tubo —
    transcripción independiente de la fórmula del libro (R ≠ 1)."""
    S = math.sqrt(R * R + 1.0)
    num = S * math.log((1.0 - P) / (1.0 - P * R))
    den = (R - 1.0) * math.log(
        (2.0 - P * (R + 1.0 - S)) / (2.0 - P * (R + 1.0 + S)))
    return num / den


def test_factor_f_vs_bowman_publicado():
    import heat_exchanger_rigorous as hxr
    for R, P in ((2.0, 0.30), (0.5, 0.60), (3.0, 0.20)):
        f_repo = hxr.f_correction_factor(R, P, n_shell=1)
        if isinstance(f_repo, tuple):
            f_repo = f_repo[0]
        assert f_repo == pytest.approx(_f_bowman_libro(R, P), rel=1e-9), \
            f"(R={R}, P={P})"
        assert f_repo <= 1.0 + 1e-12          # F nunca supera 1
    # límite físico: sin cambio de T en el frío, F = 1
    f0 = hxr.f_correction_factor(1.7, 0.0, n_shell=1)
    if isinstance(f0, tuple):
        f0 = f0[0]
    assert f0 == pytest.approx(1.0)


# ── 4. Compresor: k del aire vs Cengel ────────────────────────────────
def test_k_aire_vs_cengel():
    """k = Cp/(Cp − R) del aire a 25 °C = 1.400 (Cengel tabla A-2).
    Valida la capa Cp de thermo_db que alimenta el diseño isentrópico
    (T_out = T·[1+((P2/P1)^((k−1)/k)−1)/η], caso 6 de CASOS_LIBRO)."""
    import thermo_db as td
    R_GAS = 8.314462618
    cp = td.get("air").cp_J_mol_K(298.15, "gas")
    assert cp is not None
    k = cp / (cp - R_GAS)
    assert k == pytest.approx(1.400, abs=0.01), f"k_aire={k:.4f}"
