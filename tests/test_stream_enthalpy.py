"""
tests/test_stream_enthalpy.py — entalpía térmica de corrientes (Patch B).
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import stream_enthalpy as se
import flowsheet_model as fm


class TestSpecificEnthalpy(unittest.TestCase):
    def test_ref_liquido_25C_es_cero(self):
        h = se.specific_enthalpy_kJ_kg({"water": 1.0}, 25.0, "liquid")
        self.assertAlmostEqual(h, 0.0, delta=1.0)

    def test_liquido_caliente_positivo(self):
        h = se.specific_enthalpy_kJ_kg({"water": 1.0}, 80.0, "liquid")
        # agua Cp≈4.18 → ~230 kJ/kg a 55 K sobre ref
        self.assertGreater(h, 150.0)
        self.assertLess(h, 320.0)

    def test_vapor_incluye_latente(self):
        h_liq = se.specific_enthalpy_kJ_kg({"water": 1.0}, 100.0, "liquid")
        h_vap = se.specific_enthalpy_kJ_kg({"water": 1.0}, 100.0, "vapor")
        self.assertGreater(h_vap - h_liq, 500.0)   # ΔH_vap del agua ~2257

    def test_dos_fases_interpola(self):
        h_liq = se.specific_enthalpy_kJ_kg({"water": 1.0}, 100.0, "liquid")
        h_2ph = se.specific_enthalpy_kJ_kg({"water": 1.0}, 100.0, "two_phase", 0.5)
        h_vap = se.specific_enthalpy_kJ_kg({"water": 1.0}, 100.0, "vapor")
        self.assertTrue(h_liq < h_2ph < h_vap)


class TestBlockDeltaH(unittest.TestCase):
    def test_delta_h_signo_y_magnitud(self):
        # un "cooler": entra caliente, sale frío → ΔH < 0
        s_in = fm.Stream(id=1, name="in", src=0, dst=1, mass_flow=1000.0,
                         phase="liquid", composition={"water": 1.0},
                         main_component="water")
        s_in.temperature = 90.0
        s_out = fm.Stream(id=2, name="out", src=1, dst=0, mass_flow=1000.0,
                          phase="liquid", composition={"water": 1.0},
                          main_component="water")
        s_out.temperature = 40.0
        dH = se.block_delta_h_kW([s_in], [s_out])
        self.assertLess(dH, 0.0)
        # H_in y H_out individuales finitos y H_in > H_out
        self.assertGreater(se.stream_enthalpy_kW(s_in), se.stream_enthalpy_kW(s_out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
