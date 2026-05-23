"""Tests de solver_report.build_report — lógica pura (sin Qt)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flowsheet_solver import SolverResult, RecycleSolution
import solver_report as sr


class TestBuildReport(unittest.TestCase):

    def _ok(self):
        r = SolverResult()
        r.success = True
        r.iterations = 3
        r.overall_status = "ok"
        r.propagated_mass = [("S-1", 1000.0), ("S-2", 1000.0)]
        return r

    def test_status_ok_sin_secciones_criticas(self):
        rep = sr.build_report(self._ok(), [])
        self.assertEqual(rep["status"], "ok")
        self.assertEqual(rep["headline"], "Convergió")
        # solo la sección colapsable de flujos propagados
        titles = [s["title"] for s in rep["sections"]]
        self.assertEqual(titles, ["Flujos propagados"])
        self.assertTrue(rep["sections"][0]["collapsible"])

    def test_metricas_cuentan_warnings_y_errores(self):
        r = self._ok()
        r.overall_status = "warning"
        r.energy_warnings = ["w1", "w2"]
        r.component_warnings = ["c1"]
        r.mass_balance_errors = ["e1"]
        r.unresolved_streams = ["S-x"]
        sem = [("n1", "warn", "msg"), ("n2", "error", "msg")]
        rep = sr.build_report(r, sem)
        mt = {label: val for label, val, _ in rep["metrics"]}
        # warnings: 2 energy + 1 component + 1 sem-warn = 4
        self.assertEqual(mt["Advertencias"], "4")
        # errores: 1 mass + 1 unresolved + 1 sem-error = 3
        self.assertEqual(mt["Errores"], "3")

    def test_secciones_ordenadas_errores_primero(self):
        r = self._ok()
        r.overall_status = "error"
        r.mass_balance_errors = ["e1"]
        r.energy_warnings = ["w1"]
        rep = sr.build_report(r, [])
        kinds = [s["kind"] for s in rep["sections"]]
        # el error debe ir antes que el warning
        self.assertLess(kinds.index("error"), kinds.index("warn"))

    def test_recycle_no_convergido_marca_warn(self):
        r = self._ok()
        r.recycle_solutions = [
            RecycleSolution(tear_stream="S-r", cycle_blocks=["A", "B"],
                            converged=False, iterations=50, final_value=10.0,
                            history=[0.0, 5.0, 8.0, 10.0]),
        ]
        rep = sr.build_report(r, [])
        rec = [s for s in rep["sections"] if s.get("is_recycle")][0]
        self.assertEqual(rec["kind"], "warn")
        self.assertEqual(len(rec["rows"]), 1)
        # warnings cuenta el recycle no convergido
        mt = {label: val for label, val, _ in rep["metrics"]}
        self.assertEqual(mt["Advertencias"], "1")

    def test_fmt_recycle_incluye_trayectoria(self):
        d = {"converged": True, "tear": "S-r", "iterations": 4,
             "final_value": 5000.0, "cycle_blocks": ["M", "R", "V"],
             "history": [0.0, 1800.0, 3900.0, 4700.0, 4920.0, 5000.0]}
        head, subs = sr._fmt_recycle_row(d)
        self.assertIn("convergió", head)
        self.assertIn("S-r", head)
        self.assertTrue(any("ciclo:" in s for s in subs))
        self.assertTrue(any("trayectoria:" in s for s in subs))
        # historia larga se trunca con elipsis
        self.assertIn("…", " ".join(subs))

    def test_empty_status(self):
        r = SolverResult()
        r.overall_status = "empty"
        rep = sr.build_report(r, [])
        self.assertEqual(rep["headline"], "Diagrama vacío")
        self.assertEqual(rep["sections"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
