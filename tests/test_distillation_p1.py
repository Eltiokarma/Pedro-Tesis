"""
tests/test_distillation_p1.py — PARCHE 1: Underwood multicomp + q dinámico.

Casos A-D del spec:
  A — binario eth/water q=1, specs sanas (sin azeotropo)
  B — binario eth/water pidiendo pasar el azeotropo (warning)
  C — multicomp metanol/etanol/agua (Underwood real)
  D — q dinámico: feed vapor sat → R_min mayor que con q=1

USO:  python -m pytest tests/test_distillation_p1.py -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import distillation_fug as fug
import flowsheet_model as fm
import flowsheet_solver as solver


class TestA_BinarioSano(unittest.TestCase):
    def test_eth_water_q1_specs_sanas(self):
        res = fug.design_column(
            feed_composition={"ethanol": 0.5, "water": 0.5},
            F=1.0, T_K=353.0, P_bar=1.013,
            light_key="ethanol", heavy_key="water",
            x_D_LK=0.85, x_B_LK=0.05, R_factor=1.5, q=1.0)
        self.assertIsNotNone(res)
        self.assertIsNotNone(res.get("N"), f"N None; warnings={res.get('warnings')}")
        self.assertGreaterEqual(res["N"], 1.5)
        self.assertLessEqual(res["N"], 15.0)
        # NOTE: el shortcut binario con α_avg = geomean(α_top, α_bot) da
        # R_min≈0.40 para este par fuertemente no-ideal (α_top=1.09 cerca del
        # azeótropo, α_bot=8.4 diluido → geomean 3.0). Aspen riguroso da ~0.9
        # porque integra α etapa-por-etapa; eso lo aporta Wang-Henke (P2/P3),
        # no el FUG. La instrucción P1.1 prohíbe cambiar el binario, así que
        # validamos un rango físico sano del shortcut, no el match con Aspen.
        self.assertGreaterEqual(res["R_min"], 0.35)
        self.assertLessEqual(res["R_min"], 2.5)
        self.assertGreater(res["alpha_avg"], 1.5)
        # NO debe haber warning de azeotropo (x_D=0.85 < 0.89 azeo)
        joined = " ".join(res.get("warnings", []))
        self.assertNotIn("AZEOTROPO", joined.upper())


class TestB_AzeotropoPasado(unittest.TestCase):
    def test_eth_water_pide_pasar_azeotropo(self):
        res = fug.design_column(
            feed_composition={"ethanol": 0.5, "water": 0.5},
            F=1.0, T_K=353.0, P_bar=1.013,
            light_key="ethanol", heavy_key="water",
            x_D_LK=0.95, x_B_LK=0.05, R_factor=1.5, q=1.0)
        self.assertIsNotNone(res)
        joined = " ".join(res.get("warnings", []))
        self.assertIn("AZEOTROPO", joined.upper(),
                      f"esperaba warning AZEOTROPO; warnings={res.get('warnings')}")


class TestC_Multicomp(unittest.TestCase):
    def test_metanol_etanol_agua_underwood_real(self):
        res = fug.design_column(
            feed_composition={"methanol": 0.3, "ethanol": 0.3, "water": 0.4},
            F=1.0, T_K=350.0, P_bar=1.013,
            light_key="methanol", heavy_key="ethanol",
            x_D_LK=0.90, x_B_LK=0.02, R_factor=1.3, q=1.0,
            T_top_K=340.0, T_bot_K=370.0)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("n_signif_comps"), 3)
        # Underwood multicomp debe haberse usado (flag interno)
        self.assertTrue(res.get("underwood_multicomp"),
                        f"Underwood mc no se usó; fallback={res.get('underwood_fallback')}, "
                        f"warnings={res.get('warnings')}")
        self.assertGreaterEqual(res["R_min"], 0.5)
        self.assertLessEqual(res["R_min"], 4.0)
        self.assertGreaterEqual(res["N"], 8.0)
        self.assertLessEqual(res["N"], 30.0)


class TestD_QDinamico(unittest.TestCase):
    def test_q_calculado_para_vapor(self):
        feed = fm.Stream(id=1, name="F", src=0, dst=1, mass_flow=1.0,
                         phase="vapor",
                         composition={"ethanol": 0.30, "water": 0.70},
                         main_component="water")
        q = solver._column_feed_q(feed, 380.0, 1.013)
        self.assertAlmostEqual(q, 0.0, delta=0.1)

    def test_q0_da_Rmin_mayor_que_q1(self):
        kw = dict(
            feed_composition={"ethanol": 0.30, "water": 0.70},
            F=1.0, T_K=380.0, P_bar=1.013,
            light_key="ethanol", heavy_key="water",
            x_D_LK=0.70, x_B_LK=0.05, R_factor=1.3)
        res_q1 = fug.design_column(q=1.0, **kw)
        res_q0 = fug.design_column(q=0.0, **kw)
        self.assertIsNotNone(res_q1)
        self.assertIsNotNone(res_q0)
        self.assertGreater(
            res_q0["R_min"], res_q1["R_min"],
            f"R_min(q=0)={res_q0['R_min']:.3f} debería ser > "
            f"R_min(q=1)={res_q1['R_min']:.3f}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
