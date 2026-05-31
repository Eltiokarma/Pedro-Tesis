"""
tests/test_floating_streams.py — Suite integrada de Streams flotantes
y corrientes de energía (E3).

Cubre:
  · Stream model: stream_kind + energy_kW por default = 'mass'/0.0
  · Solver guards: streams con src<=0 o dst<=0 se ignoran
  · apply_energy_streams: acopla duties con conservación
  · Backward-compat JSON

USO:
    python -m unittest tests.test_floating_streams -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_model as fm
import flowsheet_solver as fsv


# ─────────────────────────────────────────────────────────────
# Modelo (stream_kind + energy_kW)
# ─────────────────────────────────────────────────────────────

class TestStreamKindModel(unittest.TestCase):
    def test_defaults_mass(self):
        s = fm.Stream(id=1, name="S", src=10, dst=20)
        self.assertEqual(s.stream_kind, "mass")
        self.assertEqual(s.energy_kW, 0.0)

    def test_floating_defaults(self):
        s = fm.Stream(id=1, name="S-flo", src=-1, dst=-1)
        self.assertEqual(s.src, -1)
        self.assertEqual(s.dst, -1)
        self.assertEqual(s.stream_kind, "mass")

    def test_energy_stream_constructor(self):
        s = fm.Stream(id=1, name="Q", src=10, dst=20,
                       stream_kind="energy", energy_kW=500.0)
        self.assertEqual(s.stream_kind, "energy")
        self.assertEqual(s.energy_kW, 500.0)


class TestJSONRoundtrip(unittest.TestCase):
    def test_roundtrip_energy_stream(self):
        fs = fm.Flowsheet()
        s = fm.Stream(id=1, name="Q-1", src=10, dst=20,
                       stream_kind="energy", energy_kW=350.0)
        fs.streams[1] = s
        d = fs.to_dict()
        fs2 = fm.Flowsheet.from_dict(d)
        s2 = fs2.streams[1]
        self.assertEqual(s2.stream_kind, "energy")
        self.assertEqual(s2.energy_kW, 350.0)

    def test_roundtrip_floating_stream(self):
        fs = fm.Flowsheet()
        s = fm.Stream(id=1, name="S-flo", src=-1, dst=-1,
                       start_xy=[100.0, 200.0], end_xy=[220.0, 200.0])
        fs.streams[1] = s
        d = fs.to_dict()
        fs2 = fm.Flowsheet.from_dict(d)
        s2 = fs2.streams[1]
        self.assertEqual(s2.src, -1)
        self.assertEqual(s2.dst, -1)
        self.assertEqual(s2.start_xy, [100.0, 200.0])
        self.assertEqual(s2.end_xy, [220.0, 200.0])

    def test_legacy_json_sin_claves(self):
        # JSON antiguo sin stream_kind/energy_kW → defaults 'mass'/0.0
        old = {
            "blocks": {}, "streams": {
                "1": {"id": 1, "name": "S", "src": 10, "dst": 20}
            },
            "_next_id": 2, "opex_extras": [], "fixed_overrides": {},
        }
        fs = fm.Flowsheet.from_dict(old)
        self.assertEqual(fs.streams[1].stream_kind, "mass")
        self.assertEqual(fs.streams[1].energy_kW, 0.0)


# ─────────────────────────────────────────────────────────────
# Solver guards (streams flotantes ignorados)
# ─────────────────────────────────────────────────────────────

class TestSolverIgnoraFlotantes(unittest.TestCase):
    def _make_pass_through(self):
        fs = fm.Flowsheet()
        a = fm.Block(id=1, name="A", eq_type="Storage tank — cone roof",
                      S=100, x=0, y=0)
        b = fm.Block(id=2, name="B", eq_type="Heat exch. — floating head",
                      S=50, x=200, y=0)
        c = fm.Block(id=3, name="C", eq_type="Storage tank — cone roof",
                      S=100, x=400, y=0)
        fs.blocks = {1: a, 2: b, 3: c}
        s_in = fm.Stream(id=10, name="S-in", src=1, dst=2,
                          mass_flow=1000, composition={"water": 1.0},
                          main_component="water")
        s_in.mass_flow_locked = True
        s_in.composition_locked = True
        s_out = fm.Stream(id=11, name="S-out", src=2, dst=3)
        fs.streams = {10: s_in, 11: s_out}
        return fs, s_in, s_out

    def test_flotante_no_rompe_balance(self):
        fs, s_in, s_out = self._make_pass_through()
        # Stream flotante (src=-1, dst=-1) — debe ser IGNORADO
        s_flo = fm.Stream(id=20, name="S-flo", src=-1, dst=-1,
                           start_xy=[100.0, 100.0], end_xy=[200.0, 100.0])
        fs.streams[20] = s_flo
        res = fsv.solve(fs)
        self.assertEqual(len(res.mass_balance_errors), 0)
        # Stream conectado propaga normalmente (in=1000 → out=1000)
        self.assertAlmostEqual(s_out.mass_flow, 1000.0, delta=1.0)
        # Stream flotante intacto
        self.assertEqual(s_flo.src, -1)
        self.assertEqual(s_flo.dst, -1)

    def test_solo_flotantes_no_crashea(self):
        # Flowsheet de solo streams flotantes (sin bloques conectados)
        fs = fm.Flowsheet()
        fs.streams[1] = fm.Stream(id=1, name="F1", src=-1, dst=-1,
                                    start_xy=[0, 0], end_xy=[100, 0])
        fs.streams[2] = fm.Stream(id=2, name="F2", src=-1, dst=-1,
                                    start_xy=[200, 200], end_xy=[300, 200])
        res = fsv.solve(fs)
        self.assertEqual(len(res.mass_balance_errors), 0)
        self.assertEqual(len(res.energy_balance_errors), 0)


# ─────────────────────────────────────────────────────────────
# apply_energy_streams (E3)
# ─────────────────────────────────────────────────────────────

class TestEnergyStreams(unittest.TestCase):
    def _make_two_hx(self):
        fs = fm.Flowsheet()
        a = fm.Block(id=1, name="HOT", eq_type="Heat exch. — floating head",
                      S=50, x=0, y=0)
        b = fm.Block(id=2, name="COLD", eq_type="Heat exch. — floating head",
                      S=50, x=400, y=0)
        fs.blocks = {1: a, 2: b}
        return fs, a, b

    def test_acoplamiento_basico(self):
        fs, a, b = self._make_two_hx()
        s_q = fm.Stream(id=10, name="Q-cross", src=1, dst=2,
                         stream_kind="energy", energy_kW=500.0)
        fs.streams = {10: s_q}
        msgs = fsv.apply_energy_streams(fs)
        self.assertTrue(any("Energy stream" in m for m in msgs))
        self.assertAlmostEqual(a.duty, -500.0, delta=1e-6)
        self.assertAlmostEqual(b.duty,  500.0, delta=1e-6)

    def test_conservacion_siempre_cero(self):
        # Múltiples streams de energía: Σ duty = 0
        fs, a, b = self._make_two_hx()
        c = fm.Block(id=3, name="MID", eq_type="Heat exch. — floating head",
                      S=50, x=200, y=0)
        fs.blocks[3] = c
        fs.streams[10] = fm.Stream(id=10, name="Q1", src=1, dst=3,
                                     stream_kind="energy", energy_kW=200)
        fs.streams[11] = fm.Stream(id=11, name="Q2", src=3, dst=2,
                                     stream_kind="energy", energy_kW=150)
        fsv.apply_energy_streams(fs)
        total = a.duty + b.duty + c.duty
        self.assertAlmostEqual(total, 0.0, delta=1e-6)
        # HOT cede 200, MID recibe 200 y cede 150, COLD recibe 150
        self.assertAlmostEqual(a.duty, -200.0)
        self.assertAlmostEqual(c.duty, +200 - 150)
        self.assertAlmostEqual(b.duty, +150.0)

    def test_flotante_no_aplica(self):
        # Stream energy flotante NO debe afectar a ningún bloque
        fs, a, b = self._make_two_hx()
        s_q = fm.Stream(id=10, name="Q-flo", src=-1, dst=-1,
                         stream_kind="energy", energy_kW=500.0)
        fs.streams = {10: s_q}
        fsv.apply_energy_streams(fs)
        self.assertEqual(a.duty, 0.0)
        self.assertEqual(b.duty, 0.0)

    def test_duty_locked_no_se_pisa(self):
        fs, a, b = self._make_two_hx()
        a.duty = 100.0
        a.duty_locked = True       # user override explícito
        s_q = fm.Stream(id=10, name="Q", src=1, dst=2,
                         stream_kind="energy", energy_kW=500.0)
        fs.streams = {10: s_q}
        fsv.apply_energy_streams(fs)
        self.assertEqual(a.duty, 100.0,
            "duty_locked debe respetarse: A.duty intacto")
        self.assertAlmostEqual(b.duty, 500.0)

    def test_idempotente_3_solves(self):
        """REGRESIÓN bug crítico: solve() llamado N veces debe dar
        las mismas duties.  Antes del fix, cada solve acumulaba el
        efecto del energy stream → duties × N."""
        fs, a, b = self._make_two_hx()
        s_q = fm.Stream(id=10, name="Q", src=1, dst=2,
                         stream_kind="energy", energy_kW=500.0)
        fs.streams = {10: s_q}
        fsv.solve(fs)
        d1 = (a.duty, b.duty)
        fsv.solve(fs)
        d2 = (a.duty, b.duty)
        fsv.solve(fs)
        d3 = (a.duty, b.duty)
        self.assertEqual(d1, d2, "duties cambian entre solve #1 y #2")
        self.assertEqual(d2, d3, "duties cambian entre solve #2 y #3")
        self.assertAlmostEqual(a.duty, -500.0)
        self.assertAlmostEqual(b.duty, +500.0)

    def test_apply_energy_streams_idempotente_directa(self):
        """apply_energy_streams llamada N veces directamente."""
        fs, a, b = self._make_two_hx()
        fs.streams = {10: fm.Stream(id=10, name="Q", src=1, dst=2,
                                       stream_kind="energy",
                                       energy_kW=300.0)}
        fsv.apply_energy_streams(fs)
        fsv.apply_energy_streams(fs)
        fsv.apply_energy_streams(fs)
        self.assertAlmostEqual(a.duty, -300.0)
        self.assertAlmostEqual(b.duty, +300.0)

    def test_cambiar_energy_kW_actualiza(self):
        """Si el user edita energy_kW entre solves, las duties deben
        reflejar el valor nuevo (no acumular con el viejo)."""
        fs, a, b = self._make_two_hx()
        s_q = fm.Stream(id=10, name="Q", src=1, dst=2,
                         stream_kind="energy", energy_kW=500.0)
        fs.streams = {10: s_q}
        fsv.apply_energy_streams(fs)
        self.assertAlmostEqual(a.duty, -500.0)
        # User cambia el valor
        s_q.energy_kW = 100.0
        fsv.apply_energy_streams(fs)
        self.assertAlmostEqual(a.duty, -100.0,
            "Duty no se actualizó al nuevo energy_kW")
        self.assertAlmostEqual(b.duty, +100.0)
        # Y si pasa a 0, las duties vuelven a 0
        s_q.energy_kW = 0.0
        fsv.apply_energy_streams(fs)
        self.assertAlmostEqual(a.duty, 0.0)
        self.assertAlmostEqual(b.duty, 0.0)

    def test_blocks_inexistentes_warning_propagado(self):
        """REGRESIÓN: si energy stream tiene src/dst que no existen
        en fs.blocks, el warning debe propagarse a
        result.energy_warnings (no perderse silenciosamente)."""
        fs = fm.Flowsheet()
        fs.streams = {10: fm.Stream(id=10, name="Q-bad",
                                       src=999, dst=998,
                                       stream_kind="energy",
                                       energy_kW=500.0)}
        res = fsv.solve(fs)
        self.assertTrue(
            any("bloque src/dst inexistente" in w
                for w in res.energy_warnings),
            f"Warning no propagado: {res.energy_warnings}")


# ─────────────────────────────────────────────────────────────
# Sin regresión en ejemplos existentes
# ─────────────────────────────────────────────────────────────

class TestExamplesNotAffected(unittest.TestCase):
    def test_validate_ui_sin_streams_energy(self):
        # Los 41 ejemplos no usan stream_kind='energy' → apply_energy_streams
        # debe devolver lista vacía al iterarlos
        import examples_registry as reg
        fs = reg.load_example('hda')
        msgs = fsv.apply_energy_streams(fs)
        self.assertEqual(msgs, [],
            "Ejemplos legacy no deben tener streams kind='energy'")


if __name__ == "__main__":
    unittest.main(verbosity=2)
