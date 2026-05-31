"""
GATES — cash_flow.build_cash_flow.

  1a NO-REGRESIÓN (crítico): con defaults (construcción [1.0], ramp [1.0],
     royalties 0, sin tax_lag, WC en año 0), build_cash_flow da NPV/IRR
     numéricamente idénticos a la profitability_indicators ACTUAL (CF
     constante).  Enriquecer es estrictamente aditivo.

  1b EQUIVALENCIA con el motor viejo: con ramp-up + royalties + tax_lag +
     WC@t_start (flags de equivalencia, royalties simplificado Revenue_base·pct),
     build_cash_flow reproduce flujoflujoclass.CashFlowModel.calcular
     número-a-número (mismo CF y NPV).
"""
import unittest

import equipment_costs as ec
import cash_flow as cf
import indicators as ind


ALPHA_D, ALPHA = 0.180, 0.305


def _ccop_y_dep(base):
    """CCOP (costo cash) y dep_sl como los deriva profitability_indicators."""
    tdo = base["com_d_usd_yr"] + (ALPHA - 2 * ALPHA_D) * base["fci_usd"]
    dep_sl = base["depreciable_base_usd"] / max(base["useful_life_yr"], 1)
    return tdo - dep_sl, dep_sl


class TestGate1aNoRegresion(unittest.TestCase):

    BASE = dict(revenue_usd_yr=40e6, com_d_usd_yr=22e6, fci_usd=30e6,
                depreciable_base_usd=30e6, working_capital_usd=4.5e6,
                years_op=10, useful_life_yr=10, tax_rate=0.30, disc_rate=0.10)

    def _build_default(self, base):
        ccop, dep_sl = _ccop_y_dep(base)
        return cf.build_cash_flow(
            base["fci_usd"], base["working_capital_usd"],
            revenue_usd_yr=base["revenue_usd_yr"],
            variable_opex_usd_yr=ccop, fixed_opex_usd_yr=0.0,
            dep_schedule=[dep_sl] * base["years_op"],
            tax_rate=base["tax_rate"], disc_rate=base["disc_rate"])

    def test_npv_identico(self):
        prof = ec.profitability_indicators(**self.BASE)
        r = self._build_default(self.BASE)
        self.assertAlmostEqual(r["NPV"], prof["NPV"], places=2)

    def test_irr_identico(self):
        prof = ec.profitability_indicators(**self.BASE)
        r = self._build_default(self.BASE)
        self.assertAlmostEqual(r["IRR"] * 100.0, prof["IRR %"], places=3)

    def test_varias_economias(self):
        for rev, com, fci in [(40e6, 22e6, 30e6), (60e6, 50e6, 80e6),
                              (12e6, 14e6, 20e6)]:
            base = dict(self.BASE, revenue_usd_yr=rev, com_d_usd_yr=com,
                        fci_usd=fci, depreciable_base_usd=fci)
            prof = ec.profitability_indicators(**base)
            r = self._build_default(base)
            self.assertAlmostEqual(r["NPV"], prof["NPV"], places=2,
                                   msg=f"rev={rev} com={com} fci={fci}")


class TestGate1bEquivalenciaViejo(unittest.TestCase):
    """Mismos inputs base a ambos motores → mismo CF/NPV."""

    def _old_cashflow(self):
        import flujoflujoclass as ff
        costos = {
            "Revenue": 40.0, "FCOP": 8.0, "VCOP": 15.0,
            "FCI": 30.0, "WC": 4.5,
            "FCOP_detalle": {"royalties_pct": 0.05},
        }
        sched_in = {"FC": [0], "VCOP": [0.6, 0.8, 1.0]}     # instantáneo + ramp
        schedule = ff.ReportGenerator.construir_schedule(None, sched_in, 10)
        params = {"tasa_impuesto": 0.30, "metodo_dep": 0, "periodo_dep": 10,
                  "tipo_macrs": 0, "tasa_interes": 0.10, "schedule": schedule}
        model = ff.CashFlowModel(costos, params)
        return model.calcular(), model.calcular_depreciacion()

    def test_cf_y_npv_igual_al_viejo(self):
        try:
            old, D_base = self._old_cashflow()
        except Exception as e:                       # pragma: no cover
            self.skipTest(f"flujoflujoclass no disponible: {e}")

        N = 10
        dep_sched = (list(D_base) + [0.0] * N)[:N]
        r = cf.build_cash_flow(
            30.0, 4.5,
            revenue_usd_yr=40.0, variable_opex_usd_yr=15.0,
            fixed_opex_usd_yr=8.0, dep_schedule=dep_sched,
            tax_rate=0.30, disc_rate=0.10,
            construction_schedule=(1.0,), rampup_schedule=[0.6, 0.8, 1.0],
            royalties_pct=0.05, royalties_on_base=True,   # = viejo simplificado
            tax_lag=True, wc_invest_at_t_start=True)

        self.assertEqual(len(r["CF"]), len(old["CF"]))
        for i, (a, b) in enumerate(zip(r["CF"], old["CF"])):
            self.assertAlmostEqual(a, b, places=6, msg=f"CF[{i}] difiere")
        npv_old = ind.npv(old["CF"], 0.10, old["años"])
        self.assertAlmostEqual(r["NPV"], npv_old, places=6)


if __name__ == "__main__":
    unittest.main()
