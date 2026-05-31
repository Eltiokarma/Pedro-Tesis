"""
GATE 2a/2b — profitability_indicators con vector CF.

  2a  Lineal (default) == comportamiento histórico: con dep_method ausente o
      'straight_line', NPV/IRR/CF idénticos al cálculo lineal de referencia
      (closed-form constante).  Ni un centavo de diferencia.

  2b  MACRS correcto: NPV con MACRS reproduce el cálculo A MANO (vector dep
      conocido → tax-shield año a año → NPV vía descuento) y es MAYOR que el
      lineal (depreciación acelerada reduce tax temprano).
"""
import unittest

import equipment_costs as ec
import depreciation as dep
import indicators as ind


# Caso sintético con economía positiva (para IRR/payback finitos).
BASE = dict(
    revenue_usd_yr=40e6,
    com_d_usd_yr=22e6,
    fci_usd=30e6,
    depreciable_base_usd=30e6,
    working_capital_usd=4.5e6,
    years_op=10, useful_life_yr=10,
    tax_rate=0.30, disc_rate=0.10,
)


def _ref_linear_npv_irr(p):
    """Reproduce la rama lineal histórica (closed-form constante)."""
    alpha_d, alpha = 0.180, 0.305
    tdo = p["com_d_usd_yr"] + (alpha - 2 * alpha_d) * p["fci_usd"]
    depn = p["depreciable_base_usd"] / max(p["useful_life_yr"], 1)
    taxable = p["revenue_usd_yr"] - tdo
    tax = max(0.0, taxable) * p["tax_rate"]
    net = taxable - tax
    cf = net + depn
    capex0 = p["fci_usd"] + p["working_capital_usd"]
    npv = -capex0
    for yr in range(1, p["years_op"] + 1):
        cf_yr = cf + (p["working_capital_usd"] if yr == p["years_op"] else 0.0)
        npv += cf_yr / (1.0 + p["disc_rate"]) ** yr
    return npv, cf


class TestLinealIdentidad(unittest.TestCase):

    def test_default_es_lineal(self):
        prof = ec.profitability_indicators(**BASE)
        npv_ref, cf_ref = _ref_linear_npv_irr(BASE)
        self.assertEqual(prof["NPV"], npv_ref)          # bit-identical
        self.assertEqual(prof["Cash flow"], cf_ref)
        self.assertEqual(prof["dep_method"], "straight_line")

    def test_explicit_straight_line_igual_a_default(self):
        a = ec.profitability_indicators(**BASE)
        b = ec.profitability_indicators(dep_method="straight_line", **BASE)
        self.assertEqual(a["NPV"], b["NPV"])
        self.assertEqual(a["IRR %"], b["IRR %"])


class TestMacrsCorrecto(unittest.TestCase):

    def _manual_macrs_npv(self, p, macrs_class):
        alpha_d, alpha = 0.180, 0.305
        tdo = p["com_d_usd_yr"] + (alpha - 2 * alpha_d) * p["fci_usd"]
        dep_sl = p["depreciable_base_usd"] / max(p["useful_life_yr"], 1)
        ebitda = p["revenue_usd_yr"] - tdo + dep_sl
        sched = dep.depreciation_schedule(
            p["depreciable_base_usd"], method="macrs", macrs_class=macrs_class)
        dep_vec = (sched + [0.0] * p["years_op"])[:p["years_op"]]
        cf_years = []
        for d_t in dep_vec:
            taxable_t = ebitda - d_t
            tax_t = max(0.0, taxable_t) * p["tax_rate"]
            cf_years.append((taxable_t - tax_t) + d_t)
        capex0 = p["fci_usd"] + p["working_capital_usd"]
        cf_vector = [-capex0] + cf_years
        cf_vector[-1] += p["working_capital_usd"]
        return ind.npv(cf_vector, p["disc_rate"])

    def test_macrs_reproduce_calculo_a_mano(self):
        for clase in (5, 7, 15):
            prof = ec.profitability_indicators(
                dep_method="macrs", macrs_class=clase, **BASE)
            npv_manual = self._manual_macrs_npv(BASE, clase)
            self.assertAlmostEqual(prof["NPV"], npv_manual, delta=1.0,
                                   msg=f"MACRS{clase} NPV != a mano")

    def test_macrs_rapido_mayor_que_lineal(self):
        # MACRS 5 y 7 son MÁS rápidos que el lineal a useful_life=10 años
        # → más tax-shield temprano → NPV mayor.  (MACRS15 reparte en 16
        # años: más lento que el lineal-10 y truncado al horizonte → NPV
        # menor; ver test_macrs_monotonia.)
        npv_lin = ec.profitability_indicators(**BASE)["NPV"]
        for clase in (5, 7):
            npv_macrs = ec.profitability_indicators(
                dep_method="macrs", macrs_class=clase, **BASE)["NPV"]
            self.assertGreater(
                npv_macrs, npv_lin,
                f"MACRS{clase} debería dar NPV mayor que lineal "
                f"(macrs={npv_macrs:.0f} vs lin={npv_lin:.0f})")

    def test_macrs_monotonia(self):
        # Cuanto más acelerada la clase, mayor el NPV: 5 > 7 > 15.
        n5  = ec.profitability_indicators(dep_method="macrs", macrs_class=5,
                                          **BASE)["NPV"]
        n7  = ec.profitability_indicators(dep_method="macrs", macrs_class=7,
                                          **BASE)["NPV"]
        n15 = ec.profitability_indicators(dep_method="macrs", macrs_class=15,
                                          **BASE)["NPV"]
        self.assertGreater(n5, n7)
        self.assertGreater(n7, n15)


if __name__ == "__main__":
    unittest.main()
