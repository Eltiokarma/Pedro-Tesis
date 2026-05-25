"""
tests/test_utility_streams.py — corriente de servicio HX materializada (Patch D).

equipment_auxiliaries crea las corrientes utility (cooling water / steam
shell-side) del HX pero las deja en mass_flow=0; el solver ahora las
dimensiona desde el duty (size_utility_streams).
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_model as fm
import flowsheet_solver as fsv
import equipment_auxiliaries as aux


def _hx_flowsheet(duty, eq_type="Heat exch. — floating head", comp="ethanol"):
    fs = fm.Flowsheet()
    hid = fs.new_id()
    hx = fm.Block(id=hid, name="E-1", eq_type=eq_type, S=50.0)
    hx.duty = float(duty); hx.duty_locked = True
    fs.blocks[hid] = hx
    i1 = fs.new_id()
    s = fm.Stream(id=i1, name="P-in", src=0, dst=hid, mass_flow=100000,
                  phase="liquid", composition={comp: 1.0}, main_component=comp)
    s.temperature = 90.0
    for a in ("mass_flow_locked", "temperature_locked", "composition_locked"):
        setattr(s, a, True)
    fs.streams[i1] = s
    i2 = fs.new_id()
    s2 = fm.Stream(id=i2, name="P-out", src=hid, dst=0, mass_flow=100000,
                   phase="liquid", composition={comp: 1.0}, main_component=comp)
    s2.temperature = 40.0
    fs.streams[i2] = s2
    aux.instantiate_auxiliaries(fs, hx)
    return fs, hx


def _util_streams(fs):
    return [s for s in fs.streams.values()
            if getattr(s, "auto_aux", False) and (s.role or "") == "utility"]


class TestUtilityStreamSizing(unittest.TestCase):
    def test_cooler_utility_sized_and_resolved(self):
        fs, hx = _hx_flowsheet(-2000.0)
        res = fsv.solve(fs)
        us = _util_streams(fs)
        self.assertTrue(us, "no se crearon corrientes utility auto_aux")
        for s in us:
            self.assertGreater(s.mass_flow, 0.0,
                               f"{s.name} quedó en mass_flow=0 (no dimensionada)")
        # ya no deben quedar como 'unresolved' (T de frontera asignada)
        self.assertEqual(len(res.unresolved_streams or []), 0)
        self.assertEqual(len(res.mass_balance_errors or []), 0)
        self.assertTrue(res.success)

    def test_flow_scales_with_duty(self):
        fs1, _ = _hx_flowsheet(-1000.0); fsv.solve(fs1)
        fs2, _ = _hx_flowsheet(-2000.0); fsv.solve(fs2)
        m1 = _util_streams(fs1)[0].mass_flow
        m2 = _util_streams(fs2)[0].mass_flow
        # el doble de duty → ~el doble de utility
        self.assertAlmostEqual(m2 / m1, 2.0, delta=0.05)

    def test_respeta_mass_flow_locked(self):
        fs, hx = _hx_flowsheet(-2000.0)
        us = _util_streams(fs)
        us[0].mass_flow = 12345.0
        us[0].mass_flow_locked = True
        fsv.solve(fs)
        self.assertEqual(us[0].mass_flow, 12345.0)   # no lo pisó el solver

    def test_zero_duty_no_flow(self):
        fs, hx = _hx_flowsheet(0.0)
        fsv.solve(fs)
        for s in _util_streams(fs):
            self.assertEqual(s.mass_flow, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
