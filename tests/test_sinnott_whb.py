"""
tests/test_sinnott_whb.py — Waste Heat Boilers del catálogo Sinnott.

Cubre las entradas nuevas "Heat exch. — WHB packaged"/"field erected"
(Sinnott & Towler 6th ed, Tabla 6.6), la correlación C_e = a + b·S^n con
conversión GBP2010→USD y escalado CEPCI, y la auxiliar de autoselección
de subtipo.
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import equipment_costs as ec
import equipment_sizing as es


class TestSinnottWHBCost(unittest.TestCase):
    def test_packaged_cost_in_range(self):
        # Packaged a 50 000 kg/h:
        #   C_e = 4600 + 62·50000^0.8 ≈ 360 700 GBP 2010
        #   USD 2010 = ·1.5458 ≈ 557 600
        #   USD 2026 = ·(797.9/550.8) ≈ 807 700
        pc = ec.purchased_cost("Heat exch. — WHB packaged", 50_000, 2026)
        self.assertTrue(800_000 <= pc["Cp_target"] <= 900_000,
                        f"Cp_target={pc['Cp_target']:.0f}")

    def test_field_erected_cost_verified(self):
        # Field erected a 100 000 kg/h:
        #   C_e = -90000 + 93·100000^0.8 = 840 000 GBP 2010
        #   USD 2010 = ·1.5458 ≈ 1 298 500
        #   USD 2026 = ·(797.9/550.8) ≈ 1 881 000
        # NOTA: la estimación previa de 1.0–1.2M era baja; la curva
        # field-erected (93·S^0.8) es empinada.  Valor verificado ≈1.88M.
        pc = ec.purchased_cost("Heat exch. — WHB field erected", 100_000, 2026)
        self.assertTrue(1_800_000 <= pc["Cp_target"] <= 1_950_000,
                        f"Cp_target={pc['Cp_target']:.0f}")

    def test_sinnott_formula_matches(self):
        # La función pura sinnott_purchased_cost coincide con purchased_cost.
        sp = ec.EQUIPMENT_DATA["Heat exch. — WHB packaged"]
        direct = ec.sinnott_purchased_cost(sp["a"], sp["b"], sp["n"], 50_000, 2026)
        via_pc = ec.purchased_cost("Heat exch. — WHB packaged", 50_000, 2026)
        self.assertAlmostEqual(direct, via_pc["Cp_target"], delta=1.0)


class TestSinnottHandFactor(unittest.TestCase):
    def test_packaged_cbm_uses_hand(self):
        # WHB packaged usa Hand factor 3.5 (Sinnott §6.3.3), NO el F_BM
        # Turton (~3.47).  CBM = Cp · 3.5 ≈ 807 699 × 3.5 ≈ 2 827 000.
        r = ec.bare_module_cost("Heat exch. — WHB packaged", 50_000,
                                P_op_bar=30, year_target=2026)
        self.assertEqual(r["FBM"], 3.5)
        self.assertAlmostEqual(r["CBM"], r["Cp_target"] * 3.5, delta=1.0)
        self.assertTrue(2_800_000 <= r["CBM"] <= 2_850_000,
                        f"CBM={r['CBM']:.0f}")

    def test_field_erected_cbm_uses_hand_4(self):
        # Field erected (boiler estructural) usa Hand factor 4.0.
        r = ec.bare_module_cost("Heat exch. — WHB field erected", 100_000,
                                P_op_bar=40, year_target=2026)
        self.assertEqual(r["FBM"], 4.0)
        self.assertAlmostEqual(r["CBM"], r["Cp_target"] * 4.0, delta=1.0)

    def test_turton_entry_still_uses_fbm(self):
        # Una entry Turton NO debe quedar pegada al Hand factor.
        r = ec.bare_module_cost("Heat exch. — fixed tube", 100,
                                P_op_bar=1, year_target=2026)
        self.assertNotIn("install_method", r)
        self.assertNotEqual(r["FBM"], 3.5)


class TestWHBSubtypeAutoselect(unittest.TestCase):
    def test_autoselect_subtype(self):
        self.assertEqual(es.autoselect_whb_subtype(30_000),
                         "Heat exch. — WHB packaged")
        self.assertEqual(es.autoselect_whb_subtype(80_000),
                         "Heat exch. — WHB field erected")
        # frontera: 50 000 → Packaged (≤)
        self.assertEqual(es.autoselect_whb_subtype(50_000),
                         "Heat exch. — WHB packaged")


class TestWHBSubscaleGuard(unittest.TestCase):
    def _subscale_fs(self, duty_kw):
        import flowsheet_model as fm
        fs = fm.Flowsheet()
        b = fm.Block(id=fs.new_id(), name="E-WHB",
                     eq_type="Heat exch. — WHB packaged", S=0.0)
        b.duty = duty_kw
        b.duty_locked = True
        fs.blocks[b.id] = b
        src, dst = fs.new_id(), fs.new_id()
        for name, s_, d_, T in (("hot-in", src, b.id, 500.0),
                                 ("hot-out", b.id, dst, 300.0)):
            sid = fs.new_id()
            st = fm.Stream(id=sid, name=name, src=s_, dst=d_,
                           mass_flow=10000.0, temperature=T,
                           phase="gas", role="internal")
            st.mass_flow_locked = True
            st.temperature_locked = True
            fs.streams[sid] = st
        return fs, b

    def test_size_whb_subscale_warning(self):
        import warnings
        import equipment_sizing as es
        # duty -111 kW @ T_avg 400 (HP, ΔH 1700, η 0.85) → ~200 kg/h,
        # muy por debajo del floor 5 000 kg/h del WHB packaged.
        fs, b = self._subscale_fs(-111.0)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            S = es.size_whb(b, fs)
        self.assertTrue(any("sub-escala" in str(x.message) for x in w),
                        f"no se emitió warning de sub-escala: {[str(x.message) for x in w]}")
        self.assertEqual(S, 5_000.0)                       # clamp al floor
        self.assertTrue(b._whb_diagnostics["scale_mismatch"])
        self.assertLess(b._whb_diagnostics["steam_rate_kg_h"], 5_000.0)

    def test_size_whb_in_range_no_warning(self):
        import warnings
        import equipment_sizing as es
        # duty -25 000 kW → ~38 000 kg/h, dentro del rango → sin warning.
        fs, b = self._subscale_fs(-25_000.0)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            S = es.size_whb(b, fs)
        self.assertFalse(any("sub-escala" in str(x.message) for x in w))
        self.assertGreater(S, 5_000.0)
        self.assertFalse(b._whb_diagnostics["scale_mismatch"])


class TestCatalogAuditability(unittest.TestCase):
    def test_every_entry_has_source_and_correlation(self):
        for name, spec in ec.EQUIPMENT_DATA.items():
            self.assertIn("source", spec, f"{name} sin source")
            self.assertIn("correlation", spec, f"{name} sin correlation")
        # WHB declarados como Sinnott; un Turton cualquiera como Turton
        self.assertEqual(
            ec.EQUIPMENT_DATA["Heat exch. — WHB packaged"]["source"],
            "Sinnott_2019_Table_6.6")
        self.assertEqual(
            ec.EQUIPMENT_DATA["Heat exch. — fixed tube"]["correlation"],
            "turton")


if __name__ == "__main__":
    unittest.main(verbosity=2)
