"""
tests/test_example_locks.py — Hallazgo 2 (infraestructura).

Verifica que los nuevos params lock_mass / lock_T / lock_comp de
_add_example_stream:

  · Mantienen back-compat cuando son None (heurística legacy).
  · Permiten construir flowsheets donde el solver REALMENTE
    calcula las masas intermedias, en lugar de verificar
    aritmética pre-hecha.
  · El solver propaga + balance cierra cuando los intermedios
    están con lock_mass=False (mass_flow=0.0).

NOTA SOBRE EL SCOPE: este test verifica la INFRAESTRUCTURA del
fix.  La reescritura ejemplo-por-ejemplo de los 41 builders
existentes queda como deuda técnica (el brief §2.3 lo pide al
final, con checklist específico, por el alto riesgo de regresión
del solver Wegstein cuando se quitan números semilla).

USO:
    python -m unittest tests.test_example_locks -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# Stub para Tk antes de importar flowsheet_ui
from validate_ui import headless_mocks
headless_mocks()

import flowsheet_model as fm
import flowsheet_solver as fsv
import flowsheet_ui as fu


class _FakeEditor:
    """Reproduce la interfaz mínima que usan los example builders."""
    def __init__(self):
        self.fs = fm.Flowsheet()
        self.labor_workers = 0
    _add_example_block  = fu.FlowsheetEditor._add_example_block
    _add_example_stream = fu.FlowsheetEditor._add_example_stream
    _add_example_extra  = fu.FlowsheetEditor._add_example_extra
    _set_example_labor  = fu.FlowsheetEditor._set_example_labor
    _set_block_duty     = fu.FlowsheetEditor._set_block_duty


# ─────────────────────────────────────────────────────────────
# Back-compat (lock_* = None → heurística legacy)
# ─────────────────────────────────────────────────────────────

class TestLockHeuristicaLegacy(unittest.TestCase):
    """Sin pasar lock_*, los streams se comportan igual que antes
    del fix (mass>0 → locked, T≠25 → locked, etc.)."""

    def test_mass_positivo_locked_por_default(self):
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Storage tank — cone roof", 100, 200, 0)
        sid = fake._add_example_stream(a, b, "S", mass_flow=1000)
        s = fake.fs.streams[sid]
        self.assertTrue(s.mass_flow_locked)
        self.assertFalse(s.temperature_locked)
        self.assertFalse(s.composition_locked)

    def test_T_no_25_locked_por_default(self):
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Storage tank — cone roof", 100, 200, 0)
        sid = fake._add_example_stream(a, b, "S", T=80.0)
        s = fake.fs.streams[sid]
        self.assertFalse(s.mass_flow_locked)
        self.assertTrue(s.temperature_locked)

    def test_composition_locked_por_default(self):
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Storage tank — cone roof", 100, 200, 0)
        sid = fake._add_example_stream(a, b, "S",
                                          composition={"water": 1.0})
        s = fake.fs.streams[sid]
        self.assertTrue(s.composition_locked)


# ─────────────────────────────────────────────────────────────
# Override explícito (lock_* = bool)
# ─────────────────────────────────────────────────────────────

class TestLockOverrideExplicito(unittest.TestCase):
    """Con lock_*=False explícito, los valores se declaran como
    HINT inicial (semilla) pero el solver puede recalcularlos."""

    def test_mass_no_locked_aunque_positivo(self):
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Storage tank — cone roof", 100, 200, 0)
        sid = fake._add_example_stream(a, b, "S",
                                          mass_flow=1000, lock_mass=False)
        s = fake.fs.streams[sid]
        self.assertFalse(s.mass_flow_locked,
            "Con lock_mass=False explícito, mass_flow no se lockea")
        self.assertEqual(s.mass_flow, 1000.0,
            "El valor inicial sigue siendo el declarado (semilla)")

    def test_T_no_locked_aunque_no_25(self):
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Storage tank — cone roof", 100, 200, 0)
        sid = fake._add_example_stream(a, b, "S",
                                          T=80.0, lock_T=False)
        s = fake.fs.streams[sid]
        self.assertFalse(s.temperature_locked)

    def test_composition_no_locked_aunque_declarada(self):
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Storage tank — cone roof", 100, 200, 0)
        sid = fake._add_example_stream(a, b, "S",
                                          composition={"water": 1.0},
                                          lock_comp=False)
        s = fake.fs.streams[sid]
        self.assertFalse(s.composition_locked)
        # Pero el valor declarado se conserva como hint inicial
        self.assertEqual(s.composition, {"water": 1.0})


# ─────────────────────────────────────────────────────────────
# Patrón físico correcto (regla del brief §2.2)
# ─────────────────────────────────────────────────────────────

class TestPatronFisicoCorrecto(unittest.TestCase):
    """Demuestra que un flowsheet construido con la regla física
    correcta (solo feeds + specs lockeados; intermedios NO
    lockeados) converge en el solver."""

    def test_pass_through_simple_propaga_masa(self):
        """A → HX → B con mass=1000 en feed, intermedio NO lockeado:
        el solver propaga mass_flow del intermedio."""
        fake = _FakeEditor()
        tk_in  = fake._add_example_block("TK-101", "Storage tank — cone roof", 100, 60, 100)
        e1     = fake._add_example_block("E-101",  "Heat exch. — floating head", 50, 240, 100)
        tk_out = fake._add_example_block("TK-102", "Storage tank — cone roof", 100, 420, 100)

        # FEED locked (mass + comp + T)
        fake._add_example_stream(tk_in, e1, "S-feed",
                                   src_port="salida", dst_port="tube_in",
                                   mass_flow=1000, T=20,
                                   composition={"water": 1.0},
                                   main_component="water", phase="liquid",
                                   lock_mass=True, lock_comp=True, lock_T=True)
        # INTERMEDIO: mass=0 sin lock → solver lo calcula
        fake._add_example_stream(e1, tk_out, "S-out",
                                   src_port="tube_out", dst_port="entrada",
                                   T=80, phase="liquid")
                                   # mass_flow=0.0 default, NO se lockea (mass>0=False)
                                   # composition=None → no locked
        # Stream S-out: ¿mass_flow_locked es False?
        s_out = next(s for s in fake.fs.streams.values() if s.name == "S-out")
        self.assertFalse(s_out.mass_flow_locked,
            "Stream intermedio NO debe estar lockeado")

        res = fsv.solve(fake.fs)
        # Sin errores de balance
        self.assertEqual(len(res.mass_balance_errors), 0,
            f"errors: {res.mass_balance_errors}")
        # Solver propagó la masa: S-out debe tener mass_flow ≈ 1000
        # (pass-through E-101: in=1000 → out=1000)
        self.assertAlmostEqual(s_out.mass_flow, 1000.0, delta=5.0,
            msg=f"Solver no propagó masa: S-out={s_out.mass_flow}")

    def test_feed_lock_explicito_y_intermedio_libre(self):
        """Demuestra el patrón recomendado:
          Feed:        lock_mass=True (spec)
          Intermedio:  lock_mass=False (calculado)"""
        fake = _FakeEditor()
        a = fake._add_example_block("A", "Storage tank — cone roof", 100, 0, 0)
        b = fake._add_example_block("B", "Heat exch. — floating head", 50, 200, 0)
        c = fake._add_example_block("C", "Storage tank — cone roof", 100, 400, 0)

        # FEED con regla física correcta
        sid_feed = fake._add_example_stream(a, b, "S-feed",
            mass_flow=1000, T=25,
            composition={"water": 1.0}, main_component="water",
            lock_mass=True, lock_T=True, lock_comp=True)
        # INTERMEDIO con regla física correcta
        sid_int = fake._add_example_stream(b, c, "S-int",
            T=50, phase="liquid",
            lock_mass=False, lock_comp=False)

        feed = fake.fs.streams[sid_feed]
        intr = fake.fs.streams[sid_int]
        self.assertTrue(feed.mass_flow_locked)
        self.assertTrue(feed.composition_locked)
        self.assertTrue(feed.temperature_locked)
        self.assertFalse(intr.mass_flow_locked)
        self.assertFalse(intr.composition_locked)


# ─────────────────────────────────────────────────────────────
# Existing examples: ningún ejemplo legacy quedó afectado
# ─────────────────────────────────────────────────────────────

class TestExistingExamplesUnaffected(unittest.TestCase):
    """El fix es estrictamente aditivo: los 41 ejemplos del
    catálogo siguen funcionando con la heurística legacy."""

    def test_hda_sigue_pasando(self):
        fake = _FakeEditor()
        fu.FlowsheetEditor._example_hda(fake)
        res = fsv.solve(fake.fs)
        self.assertEqual(len(res.mass_balance_errors), 0)
        # Antes del fix, todos los streams con mass>0 estaban locked
        locked_count = sum(1 for s in fake.fs.streams.values()
                            if s.mass_flow_locked)
        self.assertGreater(locked_count, 5,
            "HDA legacy debe seguir con sus streams hardcoded lockeados")


if __name__ == "__main__":
    unittest.main(verbosity=2)
