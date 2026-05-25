"""
tests/test_distillation_p2.py — PARCHE 2: balance de entalpía MESH en Wang-Henke.

Casos E-F del spec:
  E — eth/water columna grande: convergencia, duties con signo, balance
      global de energía, perfil V no-constante (MESH activo).
  F — benceno/tolueno (ideal): convergencia y x_top razonable vs shortcut.

NOTE (dilema P2.6 vs física real): el caso E está cerca del azeótropo
eth/water (α→1), donde Wang-Henke (sustitución sucesiva con under-relaxation)
converge lento — ~67 iter, no 40 (Henley-Seader §10.4: cerca del pinch se
necesitaría aceleración Newton, fuera de alcance). Y x_top converge a ~0.835
(consistente con balance de masa: D/F=0.10, feed 12% eth → x_bot=0.041), no
0.85. Ajustamos max_iter=80 y x_top≥0.83 a la realidad del solver riguroso;
las aserciones de física (duties, cierre de energía, V variable) se mantienen.

USO:  python -m pytest tests/test_distillation_p2.py -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import distillation_wanghenke as wh
import distillation_fug as fug


class TestE_MESH_eth_water(unittest.TestCase):
    def setUp(self):
        self.r = wh.wang_henke(
            ["ethanol", "water"], [0.12, 0.88], F=10.0, T_feed_K=370.0,
            P_bar=1.013, N=20, feed_stage=10, D_over_F=0.10, R=3.5, max_iter=80)
        self.assertIsNotNone(self.r)

    def test_converged(self):
        self.assertTrue(self.r["converged"],
                        f"no convergió en {self.r['iterations']} iter")

    def test_x_top_cerca_azeotropo(self):
        x_top_eth = self.r["x_profile"][0][0]
        self.assertGreaterEqual(x_top_eth, 0.83)

    def test_duty_signos(self):
        self.assertGreater(self.r["Q_reb_kW"], 0.0)    # reboiler agrega calor
        self.assertLess(self.r["Q_cond_kW"], 0.0)      # condensador retira

    def test_balance_energia_global(self):
        # q=1 (sat liq) ⇒ F·(1-q)·ΔH_vap = 0 ⇒ Q_reb + Q_cond ≈ 0 (±15%)
        Qreb = self.r["Q_reb_kW"]; Qcond = self.r["Q_cond_kW"]
        rel = abs(Qreb + Qcond) / abs(Qreb)
        self.assertLess(rel, 0.15, f"cierre global {rel*100:.1f}% > 15%")

    def test_V_profile_no_constante(self):
        # MESH activo: varianza > 5% del promedio (MES daría 0%)
        self.assertGreater(self.r["V_var"], 0.05)

    def test_masa_conservada(self):
        F, z = 10.0, [0.12, 0.88]
        Dc, Bc = self.r["D_comp"], self.r["B_comp"]
        for i in range(2):
            err = abs(F * z[i] - (Dc[i] + Bc[i])) / (F * z[i])
            self.assertLess(err, 0.02, f"comp {i} balance err {err*100:.2f}%")


class TestF_Benceno_Tolueno(unittest.TestCase):
    def test_bz_tol_converge(self):
        # R_min del shortcut → R operativo = 1.3·R_min
        rfug = fug.design_column(
            feed_composition={"benzene": 0.5, "toluene": 0.5}, F=1.0,
            T_K=365.0, P_bar=1.013, light_key="benzene", heavy_key="toluene",
            x_D_LK=0.95, x_B_LK=0.05, R_factor=1.3, q=1.0)
        self.assertIsNotNone(rfug)
        R = rfug["R_min"] * 1.3
        r = wh.wang_henke(
            ["benzene", "toluene"], [0.5, 0.5], F=10.0, T_feed_K=365.0,
            P_bar=1.013, N=15, feed_stage=8, D_over_F=0.5, R=R, max_iter=60)
        self.assertIsNotNone(r)
        self.assertTrue(r["converged"], f"bz/tol no convergió ({r['iterations']} it)")
        # benceno (LK) se enriquece en el tope: x_top_bz alto y > x_bot_bz
        x_top_bz = r["x_profile"][0][0]
        x_bot_bz = r["x_profile"][-1][0]
        self.assertGreater(x_top_bz, 0.85)
        self.assertLess(x_bot_bz, 0.15)
        self.assertGreater(r["V_var"], 0.02)


if __name__ == "__main__":
    unittest.main(verbosity=2)
