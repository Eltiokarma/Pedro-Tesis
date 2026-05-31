"""
GATES — montecarlo_headless (PORT-NUEVO sobre simulate()).

  1. Sampler idéntico: mismo seed → muestras idénticas bit a bit al
     montecarlo.py viejo (la estadística de sampling se portó verbatim).
  2. NPV base: run_monte_carlo sin incertidumbre == simulate() base.
  3. PORT-NUEVO sanity: distribución monótona (P10≤P50≤P90), sensibilidad
     monótona (precio producto ↑ → NPV ↑), tornado coherente, engine='simulate'
     (documenta que NO es 1:1 con el MC viejo).
  5. Aislamiento: montecarlo_headless no importa Tk/flujoflujoclass/ana_qt.

(Gate 4 — no-regresión suite/gate_examples/gate_simulate — se corre aparte.)
"""
import os
import sys
import subprocess
import unittest

import numpy as np

import examples_registry as reg
import simulate_engine as se
import montecarlo_headless as mh


def _old_mc_importable():
    try:
        import montecarlo   # noqa: F401  (pulls flujoflujoclass)
        return True
    except Exception:
        return False


class TestSamplerIdentico(unittest.TestCase):
    """Gate 1."""

    def _specs(self, mod):
        return [
            mod.VariableIncierta(mod.KIND_PRODUCT_PRICE, 0, "p", 80, 100, 130,
                                 mod.DIST_TRIANGULAR),
            mod.VariableIncierta(mod.KIND_RAW_MATERIAL_PRICE, 0, "rm", 40, 50, 60,
                                 mod.DIST_NORMAL),
            mod.VariableIncierta(mod.KIND_ISBL, 0, "isbl", 8e6, 1e7, 1.3e7,
                                 mod.DIST_UNIFORM),
        ]

    @unittest.skipUnless(_old_mc_importable(), "montecarlo viejo no importable")
    def test_independiente_bit_identico(self):
        import montecarlo as old
        s_new = mh._muestrear_correlacionado(self._specs(mh), 500, None, 12345)
        s_old = old._muestrear_correlacionado(self._specs(old), 500, None, 12345)
        np.testing.assert_array_equal(s_new, s_old)

    @unittest.skipUnless(_old_mc_importable(), "montecarlo viejo no importable")
    def test_correlacionado_bit_identico(self):
        import montecarlo as old
        corr = {(0, 1): 0.6, (0, 2): -0.3}
        s_new = mh._muestrear_correlacionado(self._specs(mh), 500, corr, 7)
        s_old = old._muestrear_correlacionado(self._specs(old), 500, corr, 7)
        np.testing.assert_array_equal(s_new, s_old)


class TestNPVBase(unittest.TestCase):
    """Gate 2: el MC es simulate() repetido."""

    def test_sin_incertidumbre_igual_a_simulate(self):
        for clave in ("methanol", "industrial"):
            d = reg.load_example(clave).to_dict()
            base = se.simulate(d, run_economics=True)["economics"]["NPV_usd"] / 1e6
            r = mh.run_monte_carlo(d, [], n_runs=1)
            self.assertAlmostEqual(r["npvs"][0], base, places=6,
                                   msg=f"{clave}: MC base != simulate base")

    def test_vars_fijas_en_base_dan_simulate(self):
        d = reg.load_example("methanol").to_dict()
        base = se.simulate(d, run_economics=True)["economics"]["NPV_usd"] / 1e6
        tg = mh.list_uncertain_targets(d)
        p0 = tg["products"][0]
        bp = p0["base_price_usd_per_tm"]
        v = mh.VariableIncierta(mh.KIND_PRODUCT_PRICE, p0["index"], p0["name"],
                                bp, bp, bp)   # degenerada
        r = mh.run_monte_carlo(d, [v], n_runs=5, seed=1)
        for npv in r["npvs"]:
            self.assertAlmostEqual(npv, base, places=6)


class TestPortNuevoSanity(unittest.TestCase):
    """Gate 3."""

    def _var_prod(self, d, lo=0.8, mode=1.0, hi=1.2):
        tg = mh.list_uncertain_targets(d)
        p0 = tg["products"][0]
        bp = p0["base_price_usd_per_tm"]
        return mh.VariableIncierta(mh.KIND_PRODUCT_PRICE, p0["index"], p0["name"],
                                   bp * lo, bp * mode, bp * hi)

    def test_distribucion_monotona(self):
        d = reg.load_example("methanol").to_dict()
        r = mh.run_monte_carlo(d, [self._var_prod(d)], n_runs=300, seed=11)
        s = r["stats"]
        self.assertEqual(s["n"], 300)
        self.assertLessEqual(s["npv_p10"], s["npv_p50"])
        self.assertLessEqual(s["npv_p50"], s["npv_p90"])
        self.assertGreaterEqual(s["p_npv_neg"], 0.0)
        self.assertLessEqual(s["p_npv_neg"], 1.0)
        self.assertEqual(r["engine"], "simulate")

    def test_sensibilidad_monotona(self):
        # precio producto más alto ⇒ NPV mayor
        d = reg.load_example("methanol").to_dict()
        tg = mh.list_uncertain_targets(d)
        p0 = tg["products"][0]; bp = p0["base_price_usd_per_tm"]
        lo = mh.VariableIncierta(mh.KIND_PRODUCT_PRICE, 0, "p",
                                 bp * 0.7, bp * 0.7, bp * 0.7)
        hi = mh.VariableIncierta(mh.KIND_PRODUCT_PRICE, 0, "p",
                                 bp * 1.3, bp * 1.3, bp * 1.3)
        npv_lo = mh.run_monte_carlo(d, [lo], n_runs=1)["npvs"][0]
        npv_hi = mh.run_monte_carlo(d, [hi], n_runs=1)["npvs"][0]
        self.assertGreater(npv_hi, npv_lo)

    def test_tornado_coherente(self):
        d = reg.load_example("methanol").to_dict()
        tg = mh.list_uncertain_targets(d)
        variables = [self._var_prod(d)]
        if tg["raw_materials"]:
            rm = tg["raw_materials"][0]; bp = rm["base_price_usd_per_tm"]
            variables.append(mh.VariableIncierta(
                mh.KIND_RAW_MATERIAL_PRICE, rm["index"], rm["name"],
                bp * 0.8, bp, bp * 1.2))
        tor = mh.run_tornado(d, variables)
        self.assertEqual(len(tor), len(variables))
        swings = [t["swing"] for t in tor]
        self.assertEqual(swings, sorted(swings, reverse=True))   # ordenado desc
        for t in tor:
            self.assertGreaterEqual(t["swing"], 0.0)
            self.assertIn("npv_base", t)
            self.assertTrue(np.isfinite(t["npv_base"]))


class TestAislamiento(unittest.TestCase):
    """Gate 5."""

    def test_no_importa_legacy_ni_qt(self):
        code = (
            "import sys; import montecarlo_headless; "
            "bad=[m for m in sys.modules if m in ('flujoflujoclass','tkinter',"
            "'ana_qt','montecarlo') or m.startswith('PySide6')]; "
            "sys.exit(1 if bad else 0)")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, "-c", code], cwd=root,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0,
                         "montecarlo_headless arrastró Tk/flujoflujoclass/ana_qt")


if __name__ == "__main__":
    unittest.main()
