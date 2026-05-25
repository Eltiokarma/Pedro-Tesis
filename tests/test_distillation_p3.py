"""
tests/test_distillation_p3.py — PARCHE 3: cond/reb como etapas de equilibrio
con balance propio (+ modo spec de pureza objetivo).

Casos G-I del spec:
  G — conservación de masa por componente + x_0 = destilado reportado.
  H — pureza imposible (más allá del azeótropo, N insuficiente): el solver
      NO miente — converged=False o warning de inalcanzable.
  I — balance de energía global: F·H_F + Q_reb + Q_cond = D·H_D + B·H_B.

USO:  python -m pytest tests/test_distillation_p3.py -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import distillation_wanghenke as wh


def _solve_E(max_iter=80):
    return wh.wang_henke(
        ["ethanol", "water"], [0.12, 0.88], F=10.0, T_feed_K=370.0,
        P_bar=1.013, N=20, feed_stage=10, D_over_F=0.10, R=3.5, max_iter=max_iter)


class TestG_ConservacionMasa(unittest.TestCase):
    def test_balance_por_componente(self):
        r = _solve_E()
        self.assertTrue(r["converged"])
        F, z = 10.0, [0.12, 0.88]
        D, B = r["D"], r["B"]
        x_D = r["x_profile"][0]      # etapa 0 = condensador → destilado
        x_B = r["x_profile"][-1]     # etapa N-1 = reboiler → fondo
        for i in range(2):
            resid = abs(F * z[i] - D * x_D[i] - B * x_B[i]) / (F * z[i])
            self.assertLess(resid, 0.001, f"comp {i}: balance {resid*100:.3f}% > 0.1%")

    def test_x0_es_el_destilado_reportado(self):
        # x_0[i] (etapa 0) debe ser EXACTAMENTE el destilado, no un input fijo
        r = _solve_E()
        D = r["D"]
        for i in range(2):
            self.assertAlmostEqual(r["x_profile"][0][i], r["D_comp"][i] / D, places=6)


class TestH_PurezaImposible(unittest.TestCase):
    def test_pide_pasar_azeotropo_con_N_insuficiente(self):
        # N=8 insuficiente + x_D_LK=0.95 (más allá del azeótropo ~0.894)
        r = wh.wang_henke(
            ["ethanol", "water"], [0.12, 0.88], F=10.0, T_feed_K=370.0,
            P_bar=1.013, N=8, feed_stage=4, D_over_F=0.10, R=3.5, max_iter=60,
            spec={"LK": 0, "x_D_LK": 0.95})
        self.assertIsNotNone(r)
        joined = " ".join(r.get("warnings", [])).upper()
        impossible = (not r["converged"]) or \
            ("AZEOTROPO" in joined) or ("INALCANZABLE" in joined)
        self.assertTrue(impossible,
                        "el solver reportó convergencia con pureza imposible "
                        f"(x_top={r['x_profile'][0][0]:.3f}, conv={r['converged']})")
        # y NO debe afirmar que alcanzó la pureza pedida
        self.assertLess(r["x_profile"][0][0], 0.90)


class TestI_BalanceEnergiaGlobal(unittest.TestCase):
    def test_cierre_global(self):
        r = _solve_E()
        self.assertTrue(r["converged"])
        comps = ["ethanol", "water"]
        D, B = r["D"], r["B"]
        F, z = 10.0, [0.12, 0.88]
        H_F = wh._enthalpy_liquid(comps, z, 370.0)
        H_D = wh._enthalpy_liquid(comps, r["x_profile"][0], r["T_profile"][0])
        H_B = wh._enthalpy_liquid(comps, r["x_profile"][-1], r["T_profile"][-1])
        # todo en kW: F·H[J/mol]·1e-3 = kW ; Q ya en kW
        lhs = F * H_F / 1000.0 + r["Q_reb_kW"] + r["Q_cond_kW"]
        rhs = (D * H_D + B * H_B) / 1000.0
        resid = abs(lhs - rhs) / abs(r["Q_reb_kW"])
        self.assertLess(resid, 0.05, f"residuo balance energía {resid*100:.1f}% > 5%")


if __name__ == "__main__":
    unittest.main(verbosity=2)
