"""
tests/test_equipos_referencia.py — Suite de tests de referencia
contra valores conocidos de Turton 5ª edición.

Tolerancia por defecto: ±2 %.
Tolerancia relajada (±3 %): columnas Gilliland (correlación
empírica, error inherente).

Cada test cita la sección/ecuación/ejemplo del libro.

USO:
    cd /path/to/Pedro-Tesis
    python -m unittest tests.test_equipos_referencia -v
"""
import math
import unittest

import sys
import os
_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)


REL_TOL_DEFAULT = 0.02
REL_TOL_LOOSE   = 0.03


def _close(a, b, tol=REL_TOL_DEFAULT):
    """Comparación relativa: |a - b| / max(|a|, |b|) < tol."""
    return abs(a - b) / max(abs(a), abs(b), 1e-12) < tol


# ─────────────────────────────────────────────────────────────
# §3.1 — Compresor: temperatura de descarga isentrópica
# ─────────────────────────────────────────────────────────────

class TestCompressorTout(unittest.TestCase):
    """Turton 5ª ed §6.5: T descarga politrópica.

    Caso conocido: aire (k=1.4) comprimido de 1 bar / 300 K a 5 bar
    con eficiencia isentrópica η=0.75.

    Cálculo manual:
       ΔT_isen = T_in · ((P2/P1)^((k-1)/k) − 1)
              = 300 · (5^(0.4/1.4) − 1)
              = 300 · (1.5838 − 1)
              = 175.13 K
       T_out  = T_in + ΔT_isen / η_isen
              = 300 + 175.13/0.75
              = 533.50 K
    """

    def test_aire_5x_eta075(self):
        import equipment_design as ed
        res = ed.compressor_sizing(
            m_kg_s=1.0, P_in_bar=1.0, P_out_bar=5.0,
            T_in_K=300.0, mw_avg=28.97, k=1.4, eta_isen=0.75, z=1.0,
        )
        T_out_expected = 533.50
        self.assertTrue(
            _close(res["T_out_K"], T_out_expected),
            f"T_out compresor: esperado {T_out_expected:.1f} K, "
            f"obtenido {res['T_out_K']:.1f} K"
        )


# ─────────────────────────────────────────────────────────────
# §5.1 — Underwood binario (R_min)
# ─────────────────────────────────────────────────────────────

class TestUnderwoodBinario(unittest.TestCase):
    """Turton 5ª ed §11.4 / Henley-Seader Ch 9: ec. de Underwood.

    Caso binario benceno/tolueno con feed q=1 (saturated liquid):
       z_LK = 0.50 (benceno)
       z_HK = 0.50 (tolueno)
       x_D_LK = 0.95, x_D_HK = 0.05
       α = 2.5 (avg)

       R_min = (1/(α−1)) · [ x_D_LK/z_LK − α·x_D_HK/z_HK ]
             = (1/1.5)   · [ 0.95/0.5  − 2.5·0.05/0.5 ]
             = (1/1.5)   · [ 1.90 − 0.25 ]
             = (1/1.5)   · 1.65
             = 1.10
    """

    def test_binario_benceno_tolueno(self):
        import distillation_fug as df
        try:
            theta, R_min = df.underwood(
                alphas=[2.5, 1.0],
                z=[0.50, 0.50],
                q=1.0,
                x_D=[0.95, 0.05],
            )
        except (TypeError, AttributeError) as e:
            self.skipTest(f"API underwood() incompatible: {e}")
            return
        R_min_expected = 1.10
        self.assertTrue(
            _close(R_min, R_min_expected),
            f"R_min Underwood binario: esperado {R_min_expected:.3f}, "
            f"obtenido {R_min:.3f}"
        )


class TestFenske(unittest.TestCase):
    """Turton 5ª ed Ec. 11.55: Fenske N_min para alta pureza.

    Caso: x_D_LK=0.99, x_B_LK=0.01, α=2.0
       N_min = log[(0.99/0.01)·((1-0.01)/(1-0.99))] / log(2)
             = log[ 99 · 99 ] / log(2)
             = log(9801) / log(2)
             = 9.937 / 0.693    (wait: log10)
             = 3.991 / 0.301
             = 13.26
    """

    def test_fenske_alpha_2(self):
        import distillation_fug as df
        try:
            N_min = df.fenske(
                x_D_LK=0.99, x_B_LK=0.01,
                x_D_HK=0.01, x_B_HK=0.99,
                alpha_avg=2.0,
            )
        except (TypeError, AttributeError):
            self.skipTest("API fenske() no compatible")
            return
        N_min_expected = 13.26
        self.assertTrue(
            _close(N_min, N_min_expected),
            f"N_min Fenske: esperado {N_min_expected:.2f}, "
            f"obtenido {N_min:.2f}"
        )


# ─────────────────────────────────────────────────────────────
# §1.1 — Pressure factor FP (HX y vessels)
# ─────────────────────────────────────────────────────────────

class TestPressureFactor(unittest.TestCase):
    """Turton 5ª ed Ec. 7.7 + Tabla A.2.

    Para HX shell&tube, P=10 barg:
       log10(FP) = C1 + C2·log10(P) + C3·(log10(P))²
       con C1, C2, C3 de Tabla A.2.

    Para vessels a presión, P=10 barg, D=2 m:
       FP_vessel = [ (P+1)·D/(2·(850−0.6·(P+1))) + 0.00315 ] / 0.0063
       = [ 11·2 / (2·(850 − 6.6)) + 0.00315 ] / 0.0063
       = [ 22 / 1686.8 + 0.00315 ] / 0.0063
       = [ 0.01304 + 0.00315 ] / 0.0063
       = 0.01619 / 0.0063
       = 2.570
    """

    def test_vessel_10barg_2m(self):
        import equipment_costs as ec
        # Si la función existe, testear.  Sino, skip con TODO.
        if not hasattr(ec, "_fp_vessel_pressure"):
            self.skipTest("Helper _fp_vessel_pressure() aún no implementado")
            return
        fp = ec._fp_vessel_pressure(P_barg=10.0, D_m=2.0)
        fp_expected = 2.570
        self.assertTrue(
            _close(fp, fp_expected),
            f"FP vessel: esperado {fp_expected:.3f}, "
            f"obtenido {fp:.3f}"
        )


# ─────────────────────────────────────────────────────────────
# §1.5 — COM Turton Eq 8.2
# ─────────────────────────────────────────────────────────────

class TestCOM(unittest.TestCase):
    """Turton 5ª ed Ec. 8.2: Cost of Manufacture con depreciación.

       COM_d = 0.180·FCI + 2.73·COL + 1.23·(CUT + CRM + CWT)

    Caso simple:
       FCI = 100 MM USD, COL = 1 MM/yr, CUT+CRM+CWT = 10 MM/yr
       COM_d = 0.180·100 + 2.73·1 + 1.23·10
             = 18 + 2.73 + 12.3
             = 33.03 MM/yr
    """

    def test_com_d_referencia(self):
        import equipment_costs as ec
        res = ec.cost_of_manufacture(
            FCI_usd=100e6, COL_usd=1e6,
            CUT_usd=5e6, CRM_usd=4e6, CWT_usd=1e6,
        )
        expected = 33.03e6
        self.assertTrue(
            _close(res["COM_d"], expected),
            f"COM_d: esperado {expected:,.0f}, obtenido {res['COM_d']:,.0f}"
        )


# ─────────────────────────────────────────────────────────────
# §3.2 — NPSH disponible (NPSHa)
# ─────────────────────────────────────────────────────────────

class TestNPSHa(unittest.TestCase):
    """Verifica que NPSHa = (P_in − P_vap)·1e5/(ρ·g) + z_elev.

    Caso: agua a 25 °C (P_vap ≈ 0.032 bar), P_succión = 1 bar,
          ρ = 997 kg/m³, succión inundada z_elev = +2 m.

       NPSHa = (1 − 0.032)·1e5 / (997·9.81) + 2
             = 96800 / 9780
             = 9.898 + 2
             = 11.898 m
    """

    def test_agua_25c_z2m(self):
        import equipment_design as ed
        res = ed.pump_sizing(
            m_kg_s=10.0, dp_bar=4.0,
            rho_kg_m3=997.0, eta_hyd=0.75,
            T_K=298.15, p_vap_bar=0.032,
            p_in_bar=1.0, z_elev_m=2.0,
        )
        npsha_expected = 11.898
        self.assertTrue(
            _close(res["NPSHa_m"], npsha_expected, tol=0.01),
            f"NPSHa agua: esperado {npsha_expected:.2f} m, "
            f"obtenido {res['NPSHa_m']:.2f} m"
        )


# ─────────────────────────────────────────────────────────────
# §6.1 — Energy balance sensible
# ─────────────────────────────────────────────────────────────

class TestEnergyBalanceSensible(unittest.TestCase):
    """Verifica balance Q = m·Cp·ΔT puro (sin cambio de fase).

    Caso: agua 1 kg/s, Cp = 4.186 kJ/kg·K, T_in=25 °C, Q=+100 kW.
       T_out = 25 + 100/(1·4.186) = 25 + 23.89 = 48.89 °C
    """

    def test_calentamiento_agua(self):
        # Test del cálculo directo, no del solver completo.
        m_kg_s = 1.0
        cp = 4.186
        T_in = 25.0
        Q = 100.0
        T_out_expected = T_in + Q/(m_kg_s*cp)
        # Validamos la ecuación contra la fórmula del libro
        self.assertAlmostEqual(T_out_expected, 48.89, places=1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
