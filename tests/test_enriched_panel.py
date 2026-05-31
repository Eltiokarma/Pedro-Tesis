"""
GATE 3 — enriquecimiento expuesto en panel + Monte Carlo.

  · EconomicsPanel: los campos de construcción/ramp-up/royalties/tax_lag se
    parsean y fluyen a simulate(); el NPV del panel == simulate(econ_inputs)
    (el panel es solo presentación del mismo motor → build_cash_flow).
  · Default (campos vacíos) → caso simple (NPV == simulate sin enriquecer).
  · MonteCarloPanel hereda el enriquecimiento vía econ_inputs.
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import examples_registry as reg
import simulate_engine as se
from economics_panel import EconomicsPanel, MonteCarloPanel, _parse_csv

_app = QApplication.instance() or QApplication([])


class TestParseCSV(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(_parse_csv("0.5, 0.75, 1.0"), [0.5, 0.75, 1.0])
        self.assertEqual(_parse_csv("0.6;0.4"), [0.6, 0.4])
        self.assertEqual(_parse_csv(""), [])
        self.assertEqual(_parse_csv("  "), [])
        self.assertEqual(_parse_csv("abc"), [])


class TestPanelEnriquecido(unittest.TestCase):

    def _panel(self):
        fs = reg.load_example("methanol")
        return EconomicsPanel(fs)

    def test_default_es_caso_simple(self):
        p = self._panel()
        ei = p.collect_econ_inputs()
        self.assertEqual(ei["royalties_pct"], 0.0)
        self.assertFalse(ei["tax_lag"])
        self.assertNotIn("construction_schedule", ei)
        self.assertNotIn("rampup_schedule", ei)
        p._run()
        base = se.simulate(p.fs.to_dict(), run_economics=True)["economics"]
        self.assertAlmostEqual(p.last_result["economics"]["NPV_usd"],
                               base["NPV_usd"], places=2)

    def test_enriquecido_parsea_y_coincide_con_simulate(self):
        p = self._panel()
        p.edit_constr.setText("0.6,0.4")
        p.edit_ramp.setText("0.5,0.75,1.0")
        p.spin_roy.setValue(0.05)
        p.chk_taxlag.setChecked(True)
        ei = p.collect_econ_inputs()
        self.assertEqual(ei["construction_schedule"], [0.6, 0.4])
        self.assertEqual(ei["rampup_schedule"], [0.5, 0.75, 1.0])
        self.assertEqual(ei["royalties_pct"], 0.05)
        self.assertTrue(ei["tax_lag"])
        p._run()
        # panel == simulate con los mismos inputs (mismo motor build_cash_flow)
        ref = se.simulate(p.fs.to_dict(), run_economics=True,
                          econ_inputs=ei)["economics"]
        self.assertAlmostEqual(p.last_result["economics"]["NPV_usd"],
                               ref["NPV_usd"], places=2)
        # y enriquecido != simple
        base = se.simulate(p.fs.to_dict(), run_economics=True)["economics"]
        self.assertNotAlmostEqual(ref["NPV_usd"], base["NPV_usd"], places=0)

    def test_mc_hereda_enriquecimiento(self):
        import montecarlo_headless as mh
        d = reg.load_example("methanol").to_dict()
        econ = {"rampup_schedule": [0.5, 0.75, 1.0], "royalties_pct": 0.05}
        tg = mh.list_uncertain_targets(d)
        bp = tg["products"][0]["base_price_usd_per_tm"]
        v = mh.VariableIncierta(mh.KIND_PRODUCT_PRICE, 0, "p", bp, bp, bp)
        # MC degenerado (var fija) con enriquecimiento == simulate enriquecido
        npv_mc = mh.run_monte_carlo(d, [v], econ_inputs=econ, n_runs=1)["npvs"][0]
        npv_sim = se.simulate(d, run_economics=True,
                              econ_inputs=econ)["economics"]["NPV_usd"] / 1e6
        self.assertAlmostEqual(npv_mc, npv_sim, places=6)


if __name__ == "__main__":
    unittest.main()
