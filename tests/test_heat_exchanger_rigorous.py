"""
tests/test_heat_exchanger_rigorous.py — diseño térmico riguroso de HX.

Cubre el módulo heat_exchanger_rigorous (LMTD real, factor F de Bowman,
approach mínimo) y la validación termodinámica de cross-exchange en
flowsheet_solver.is_cross_exchange (cierre de energía 5%).
"""
import math
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import heat_exchanger_rigorous as hxr
import flowsheet_model as fm
import flowsheet_solver as fsv


class TestLMTD(unittest.TestCase):
    def test_counter_pure(self):
        # Contracorriente, ΔT constante: caliente 150→100, frío 50→100.
        # ΔT1 = 150−100 = 50, ΔT2 = 100−50 = 50 → LMTD = 50.
        lmtd, w = hxr.compute_lmtd_real(150, 100, 50, 100, flow="counter")
        self.assertIsNone(w)
        self.assertAlmostEqual(lmtd, 50.0, delta=1e-6)

    def test_counter_unequal(self):
        # Caliente 200→100, frío 40→120. ΔT1=200−120=80, ΔT2=100−40=60.
        # LMTD = (80−60)/ln(80/60) = 20/0.28768 = 69.52.
        lmtd, w = hxr.compute_lmtd_real(200, 100, 40, 120, flow="counter")
        self.assertIsNone(w)
        self.assertAlmostEqual(lmtd, (80 - 60) / math.log(80 / 60), delta=1e-3)

    def test_thermal_cross_warns(self):
        # Cruce: caliente 80→70, frío 30→90 en contracorriente.
        # ΔT1 = 80−90 = −10, ΔT2 = 70−30 = 40 → producto < 0 → cruce.
        lmtd, w = hxr.compute_lmtd_real(80, 70, 30, 90, flow="counter")
        self.assertIsNone(lmtd)
        self.assertIsNotNone(w)
        self.assertIn("cruce", w.lower())


class TestFactorF(unittest.TestCase):
    def test_one_shell_two_tube_value(self):
        # 1 carcasa / 2 tubos.  Caso clásico (Kern fig 18): R=1, P=0.5.
        # F debe estar en (0.75, 1.0] y ser < 1 (penalización por 1-2).
        Thi, Tho, Tci, Tco = 100, 60, 20, 60      # R=1, P=0.5
        R = (Thi - Tho) / (Tco - Tci)
        P = (Tco - Tci) / (Thi - Tci)
        self.assertAlmostEqual(R, 1.0, delta=1e-9)
        self.assertAlmostEqual(P, 0.5, delta=1e-9)
        F, w = hxr.f_correction_factor(R, P, n_shell=1, n_tube=2)
        self.assertGreaterEqual(F, 0.75)
        self.assertLessEqual(F, 1.0)
        self.assertLess(F, 1.0)
        # Valor de tabla para R=1, P=0.5 ≈ 0.80.
        self.assertAlmostEqual(F, 0.80, delta=0.03)

    def test_low_F_warns_and_clamps(self):
        # P alto con R alto → F crudo < 0.75 → warning + clamp.
        F, w = hxr.f_correction_factor(R=3.0, P=0.45, n_shell=1, n_tube=2)
        self.assertIsNotNone(w)
        self.assertGreaterEqual(F, 0.75)      # clamped

    def test_no_temp_change_F_unity(self):
        # P≈0 (frío casi no cambia) → F = 1.
        F, w = hxr.f_correction_factor(R=2.0, P=1e-12)
        self.assertAlmostEqual(F, 1.0, delta=1e-6)


class TestApproach(unittest.TestCase):
    def test_violation_warns(self):
        w = hxr.check_approach(T_hot_out=45, T_cold_in=40, dT_min=10)
        self.assertIsNotNone(w)
        self.assertIn("approach", w.lower())

    def test_ok_none(self):
        w = hxr.check_approach(T_hot_out=80, T_cold_in=40, dT_min=10)
        self.assertIsNone(w)


class TestUByService(unittest.TestCase):
    def test_services(self):
        self.assertEqual(hxr.u_typical_by_service("gas", "gas"),
                         hxr._U_SENSIBLE[("gas", "gas")])
        self.assertEqual(hxr.u_typical_by_service("liquid", "liquid"),
                         hxr._U_SENSIBLE[("liquid", "liquid")])
        self.assertEqual(hxr.u_typical_by_service("vapor", "water",
                                                  phase_change="condensation"),
                         hxr._U_CONDENSATION)
        self.assertEqual(hxr.u_typical_by_service("liquid", "liquid",
                                                  phase_change="evaporation"),
                         hxr._U_EVAPORATION)
        # fluido no reconocido → normaliza a 'liquid' (no gas) → liq-liq
        self.assertEqual(hxr.u_typical_by_service("plasma", "plasma"),
                         hxr._U_SENSIBLE[("liquid", "liquid")])


class TestCrossExchangeClosure(unittest.TestCase):
    """is_cross_exchange valida cierre de energía (5%)."""

    def _build(self, T_cold_out):
        """HX 2-in/2-out: caliente 150→100; frío 50→T_cold_out.
        Mismos m·cp ⇒ cierra sólo si T_cold_out = 100."""
        fs = fm.Flowsheet()
        b = fm.Block(id=fs.new_id(), name="E-1",
                     eq_type="Heat exch. — floating head", S=20.0)
        fs.blocks[b.id] = b
        src = fs.new_id()      # ids ficticios de bloques vecinos
        dst = fs.new_id()

        def mk(name, srcid, dstid, T, m, cp):
            sid = fs.new_id()
            s = fm.Stream(id=sid, name=name, src=srcid, dst=dstid,
                          mass_flow=m, temperature=T, cp=cp, phase="liquid")
            fs.streams[sid] = s
            return s

        # par caliente (cede): in 150 → out 100
        mk("hot-in",  src,  b.id, 150.0, 100000.0, 2.0)
        mk("hot-out", b.id, dst,  100.0, 100000.0, 2.0)
        # par frío (recibe): in 50 → out T_cold_out
        mk("cold-in",  src,  b.id, 50.0,        90000.0, 2.0)
        mk("cold-out", b.id, dst,  T_cold_out,  90000.0, 2.0)
        return fs, b

    def test_balance_closed_is_cross(self):
        # Q_hot = 100000·2·50 ; Q_cold = 90000·2·(Tco−50).
        # Cierra (<5%) si Tco ≈ 50 + 50·100/90 = 105.56.
        fs, b = self._build(T_cold_out=105.56)
        self.assertTrue(fsv.is_cross_exchange(fs, b))

    def test_balance_open_not_cross(self):
        # Frío sólo sube a 70 → Q_cold ≈ 0.4·Q_hot → 60% imbalance → False,
        # y se registra warning en fs._solver_warnings.
        fs, b = self._build(T_cold_out=70.0)
        fs._solver_warnings = []
        self.assertFalse(fsv.is_cross_exchange(fs, b))
        self.assertTrue(any("no cierra" in w for w in fs._solver_warnings))

    def test_no_cp_keeps_structural(self):
        # Sin cp/comp resoluble → no se puede evaluar energía → conserva
        # el resultado estructural (True).
        fs, b = self._build(T_cold_out=70.0)
        for s in fs.streams.values():
            s.cp = 0.0
        self.assertTrue(fsv.is_cross_exchange(fs, b))


if __name__ == "__main__":
    unittest.main(verbosity=2)
