"""
tests/test_units_system.py — sistema global de unidades (Patch C).

Cubre conversiones, presets, y que la exportación refleje las unidades
activas.  Restaura el estado global en tearDown para no contaminar otros
tests (el estado de funits es módulo-level).
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_units as fu


class _UnitsBase(unittest.TestCase):
    def setUp(self):
        self._saved = fu.active()

    def tearDown(self):
        for q, u in self._saved.items():
            fu.set_quantity(q, u)


class TestConversions(_UnitsBase):
    def test_temp(self):
        self.assertAlmostEqual(fu.conv_temp(100, "K"), 373.15, places=2)
        self.assertAlmostEqual(fu.conv_temp(100, "°F"), 212.0, places=1)
        self.assertAlmostEqual(fu.conv_temp(0, "°C"), 0.0, places=6)

    def test_pressure(self):
        self.assertAlmostEqual(fu.conv_pressure(1, "kPa"), 100.0, places=3)
        self.assertAlmostEqual(fu.conv_pressure(1, "psi"), 14.5038, places=3)
        self.assertAlmostEqual(fu.conv_pressure(1, "atm"), 0.98692, places=4)

    def test_energy(self):
        self.assertAlmostEqual(fu.conv_energy(1000, "MW"), 1.0, places=6)
        self.assertAlmostEqual(fu.conv_energy(1000, "hp"), 1341.02, places=0)

    def test_flow_wrapper(self):
        # tm/año → kg/h
        v = fu.conv_flow(8760.0, "kg/h")     # 8760 tm/yr = 1000 kg/h
        self.assertAlmostEqual(v, 1000.0, places=1)


class TestPresets(_UnitsBase):
    def test_set_and_current_system(self):
        fu.set_system("SI estricto")
        self.assertEqual(fu.active_unit("temp"), "K")
        self.assertEqual(fu.active_unit("flow"), "kg/s")
        self.assertEqual(fu.current_system(), "SI estricto")

    def test_default_is_model(self):
        fu.set_system("Modelo (tm/año)")
        self.assertEqual(fu.current_system(), "Modelo (tm/año)")
        self.assertEqual(fu.active_unit("flow"), "tm/año")


class TestExportReflectsUnits(_UnitsBase):
    def test_stream_rows_use_active_units(self):
        import flowsheet_model as fm
        import flowsheet_export as fe
        fs = fm.Flowsheet()
        s = fm.Stream(id=1, name="S1", src=0, dst=0, mass_flow=8760.0,
                      phase="liquid", composition={"water": 1.0},
                      main_component="water")
        s.temperature = 100.0
        s.pressure_bar = 2.0
        fs.streams[1] = s
        fu.set_system("Imperial (US)")
        rows = fe.collect_stream_rows(fs)
        r = rows[0]
        self.assertIn("Mass [lb/h]", r)
        self.assertIn("T [°F]", r)
        self.assertIn("P [psi]", r)
        self.assertAlmostEqual(r["T [°F]"], 212.0, places=1)      # 100°C
        self.assertAlmostEqual(r["P [psi]"], 29.0076, places=2)   # 2 bar


if __name__ == "__main__":
    unittest.main(verbosity=2)
