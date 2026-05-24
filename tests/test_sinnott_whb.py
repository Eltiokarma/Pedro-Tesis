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


class TestWHBSubtypeAutoselect(unittest.TestCase):
    def test_autoselect_subtype(self):
        self.assertEqual(es.autoselect_whb_subtype(30_000),
                         "Heat exch. — WHB packaged")
        self.assertEqual(es.autoselect_whb_subtype(80_000),
                         "Heat exch. — WHB field erected")
        # frontera: 50 000 → Packaged (≤)
        self.assertEqual(es.autoselect_whb_subtype(50_000),
                         "Heat exch. — WHB packaged")


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
