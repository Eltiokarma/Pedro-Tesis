"""
tests/test_pressure_coherence.py — coherencia P_op_bar vs presión propagada.

El solver de presión no usaba P_op_bar (solo pressure_locked/delta_p_bar), así
que reactores a 25/80/200 bar dejaban sus corrientes en 1.013 → CAPEX/material
adyacentes mal.  _seed_reactor_pressures + effective_pressure lo corrigen de
raíz (sin editar cada ejemplo).
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_registry as reg


def _solve(clave):
    """Carga un ejemplo desde su JSON canónico (registry) y lo resuelve."""
    fs = reg.load_example(clave)
    fsv.solve(fs)
    return fs


def _block(fs, name):
    return next((b for b in fs.blocks.values() if b.name == name), None)


def _max_pin(fs, b):
    ins = [s for s in fs.streams.values() if s.dst == b.id]
    return max((s.pressure_bar for s in ins), default=1.013)


class TestCoherence(unittest.TestCase):
    # (ejemplo, bloque, P_op esperada) — los que declaran P_op>2
    CASES = [
        ("smr_eq",      "R-101", 25.0),
        ("haber_rec",   "R-101", 200.0),
        ("industrial",  "R-101", 80.0),
        ("acetic",      "R-101", 35.0),
        ("urea",        "R-101", 150.0),
        ("ldpe",        "R-101", 2000.0),
        ("hno3",        "R-301", 11.0),
    ]

    def test_pin_pressure_matches_pop(self):
        for nm, bname, p_exp in self.CASES:
            fs = _solve(nm)
            b = _block(fs, bname)
            self.assertIsNotNone(b, f"{nm}: falta {bname}")
            pin = _max_pin(fs, b)
            self.assertAlmostEqual(
                pin, p_exp, delta=max(2.0, p_exp * 0.02),
                msg=f"{nm}/{bname}: P_in={pin:.1f} ≠ P_op={p_exp:.1f}")

    def test_adjacent_inherits_section_pressure(self):
        # En haber, el mixer/heater upstream del reactor (200 bar) hereda la
        # presión de la sección para el costing (antes quedaba en atmósfera).
        fs = _solve("haber_rec")
        f101 = _block(fs, "F-101")
        self.assertIsNotNone(f101)
        self.assertGreater(fsv.effective_pressure(fs, f101), 150.0)

    def test_atmospheric_examples_untouched(self):
        # Los ejemplos atmosféricos (sin P_op>1) no activan el solver de
        # presión: sus corrientes siguen en ~1.013.
        for nm in ("distillation", "ethanol",
                   "biodiesel"):
            fs = _solve(nm)
            for s in fs.streams.values():
                self.assertLess(s.pressure_bar, 2.0,
                                f"{nm}/{s.name}: P={s.pressure_bar} (debería atm)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
