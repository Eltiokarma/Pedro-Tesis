"""
tests/test_example_locks.py — heurística declarativa de locks + propagación.

Tras retirar los builders imperativos (ExampleBuilder), la heurística de
inferencia de locks que vivía en el helper `_add_example_stream`
("mass>0 ⇒ locked", "T≠25 ⇒ locked", "comp/phase presentes ⇒ locked")
quedó EN UN SOLO lugar: Flowsheet.from_dict, como migración backward-compat
para JSONs legacy que no traen los flags `*_locked` explícitos (los 41 JSON
del catálogo SÍ los traen, así que para ellos la heurística no se dispara).

Este test verifica:
  · from_dict infiere los locks por heurística cuando el JSON NO trae el flag
    (back-compat legacy).
  · from_dict RESPETA el flag explícito cuando el JSON sí lo trae (override),
    conservando el valor declarado como semilla.
  · El solver propaga masa/comp a través de intermedios NO lockeados (regla
    física: solo feeds + specs van locked).

USO:
    python -m unittest tests.test_example_locks -v
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


# ─────────────────────────────────────────────────────────────
# Helpers test-local sobre la API directa de flowsheet_model.
# (No dependen de ExampleBuilder — los builders fueron retirados.)
# ─────────────────────────────────────────────────────────────

def _blk(fs, name, eq_type="Storage tank — cone roof", S=100.0, x=0, y=0):
    bid = fs.new_id()
    b = fm.Block(id=bid, name=name, eq_type=eq_type, S=S, n=1, x=x, y=y)
    b.S_locked = (S > 0)
    fs.blocks[bid] = b
    return bid


def _strm(fs, src, dst, name, mass_flow=0.0, role="internal",
          src_port="", dst_port="", T=25.0, composition=None,
          main_component="", phase="",
          lock_mass=None, lock_T=None, lock_comp=None):
    """Crea un Stream con la misma convención de locks declarativos que
    from_dict: None ⇒ heurística (mass>0 / T≠25 / comp|main_comp), bool ⇒
    override explícito.  Es API directa (fm.Stream); los locks se setean a
    mano."""
    sid = fs.new_id()
    s = fm.Stream(id=sid, name=name, src=src, dst=dst, mass_flow=mass_flow,
                  role=role, src_port=src_port, dst_port=dst_port,
                  temperature=T, main_component=main_component, phase=phase,
                  composition=dict(composition) if composition else {})
    s.mass_flow_locked   = ((mass_flow > 0) if lock_mass is None
                              else bool(lock_mass))
    s.temperature_locked = ((abs(T - 25.0) > 0.01) if lock_T is None
                              else bool(lock_T))
    s.composition_locked = ((bool(composition) or bool(main_component))
                              if lock_comp is None else bool(lock_comp))
    s.phase_locked = bool(phase)
    fs.streams[sid] = s
    return sid


def _legacy_stream_dict(**over):
    """Dict de stream estilo JSON LEGACY (sin flags *_locked) para ejercitar
    la heurística de migración de from_dict."""
    base = {"id": 1, "name": "S", "src": 10, "dst": 20}
    base.update(over)
    return {"blocks": {}, "streams": {"1": base},
            "_next_id": 2, "opex_extras": [], "fixed_overrides": {}}


# ─────────────────────────────────────────────────────────────
# Heurística de from_dict (JSON legacy SIN flags *_locked)
# ─────────────────────────────────────────────────────────────

class TestFromDictHeuristicaLegacy(unittest.TestCase):
    """from_dict infiere los locks cuando el JSON no trae el flag — la misma
    heurística que antes hacía el helper _add_example_stream."""

    def test_mass_positivo_locked_por_default(self):
        fs = fm.Flowsheet.from_dict(_legacy_stream_dict(mass_flow=1000.0))
        s = fs.streams[1]
        self.assertTrue(s.mass_flow_locked)
        self.assertFalse(s.temperature_locked)   # T default 25
        self.assertFalse(s.composition_locked)

    def test_T_no_25_locked_por_default(self):
        fs = fm.Flowsheet.from_dict(_legacy_stream_dict(temperature=80.0))
        s = fs.streams[1]
        self.assertFalse(s.mass_flow_locked)
        self.assertTrue(s.temperature_locked)

    def test_composition_locked_por_default(self):
        fs = fm.Flowsheet.from_dict(
            _legacy_stream_dict(composition={"water": 1.0}))
        s = fs.streams[1]
        self.assertTrue(s.composition_locked)

    def test_phase_locked_por_default(self):
        fs = fm.Flowsheet.from_dict(_legacy_stream_dict(phase="liquid"))
        self.assertTrue(fs.streams[1].phase_locked)


# ─────────────────────────────────────────────────────────────
# Override explícito (JSON CON flags *_locked → from_dict los respeta)
# ─────────────────────────────────────────────────────────────

class TestFromDictRespetaFlagExplicito(unittest.TestCase):
    """Cuando el JSON trae el flag explícito, from_dict NO infiere: usa el
    valor declarado.  El valor (mass/T/comp) se conserva como semilla."""

    def test_mass_no_locked_aunque_positivo(self):
        fs = fm.Flowsheet.from_dict(
            _legacy_stream_dict(mass_flow=1000.0, mass_flow_locked=False))
        s = fs.streams[1]
        self.assertFalse(s.mass_flow_locked,
            "flag explícito False debe respetarse pese a mass>0")
        self.assertEqual(s.mass_flow, 1000.0,
            "el valor declarado se conserva como semilla")

    def test_T_no_locked_aunque_no_25(self):
        fs = fm.Flowsheet.from_dict(
            _legacy_stream_dict(temperature=80.0, temperature_locked=False))
        self.assertFalse(fs.streams[1].temperature_locked)

    def test_composition_no_locked_aunque_declarada(self):
        fs = fm.Flowsheet.from_dict(
            _legacy_stream_dict(composition={"water": 1.0},
                                composition_locked=False))
        s = fs.streams[1]
        self.assertFalse(s.composition_locked)
        self.assertEqual(s.composition, {"water": 1.0})


# ─────────────────────────────────────────────────────────────
# Patrón físico correcto: el solver propaga intermedios no lockeados
# ─────────────────────────────────────────────────────────────

class TestPatronFisicoCorrecto(unittest.TestCase):
    """Un flowsheet con la regla física correcta (solo feeds + specs
    lockeados; intermedios NO lockeados) converge: el solver propaga."""

    def test_pass_through_simple_propaga_masa(self):
        """A → HX → B con mass=1000 en feed, intermedio NO lockeado:
        el solver propaga mass_flow del intermedio."""
        fs = fm.Flowsheet()
        tk_in  = _blk(fs, "TK-101", "Storage tank — cone roof", 100, 60, 100)
        e1     = _blk(fs, "E-101",  "Heat exch. — floating head", 50, 240, 100)
        tk_out = _blk(fs, "TK-102", "Storage tank — cone roof", 100, 420, 100)

        # FEED locked (mass + comp + T)
        _strm(fs, tk_in, e1, "S-feed",
              src_port="salida", dst_port="tube_in",
              mass_flow=1000, T=20, composition={"water": 1.0},
              main_component="water", phase="liquid",
              lock_mass=True, lock_comp=True, lock_T=True)
        # INTERMEDIO: mass=0 sin lock → solver lo calcula
        _strm(fs, e1, tk_out, "S-out",
              src_port="tube_out", dst_port="entrada", T=80, phase="liquid")

        s_out = next(s for s in fs.streams.values() if s.name == "S-out")
        self.assertFalse(s_out.mass_flow_locked,
            "Stream intermedio NO debe estar lockeado")

        res = fsv.solve(fs)
        self.assertEqual(len(res.mass_balance_errors), 0,
            f"errors: {res.mass_balance_errors}")
        self.assertAlmostEqual(s_out.mass_flow, 1000.0, delta=5.0,
            msg=f"Solver no propagó masa: S-out={s_out.mass_flow}")

    def test_feed_lock_explicito_y_intermedio_libre(self):
        """Patrón recomendado: feed lock_mass=True (spec); intermedio
        lock_mass=False (calculado)."""
        fs = fm.Flowsheet()
        a = _blk(fs, "A", "Storage tank — cone roof", 100, 0, 0)
        b = _blk(fs, "B", "Heat exch. — floating head", 50, 200, 0)
        c = _blk(fs, "C", "Storage tank — cone roof", 100, 400, 0)

        sid_feed = _strm(fs, a, b, "S-feed", mass_flow=1000, T=25,
                         composition={"water": 1.0}, main_component="water",
                         lock_mass=True, lock_T=True, lock_comp=True)
        sid_int = _strm(fs, b, c, "S-int", T=50, phase="liquid",
                        lock_mass=False, lock_comp=False)

        feed = fs.streams[sid_feed]
        intr = fs.streams[sid_int]
        self.assertTrue(feed.mass_flow_locked)
        self.assertTrue(feed.composition_locked)
        self.assertTrue(feed.temperature_locked)
        self.assertFalse(intr.mass_flow_locked)
        self.assertFalse(intr.composition_locked)


# ─────────────────────────────────────────────────────────────
# Ejemplos del catálogo: cargan desde JSON y siguen propagando
# ─────────────────────────────────────────────────────────────

class TestExistingExamplesUnaffected(unittest.TestCase):
    """El ejemplo HDA, cargado desde su JSON canónico (registry), resuelve
    limpio: feed + tear del recycle van locked; los intermedios propagan."""

    def test_hda_sigue_pasando(self):
        fs = reg.load_example('hda')
        res = fsv.solve(fs)
        self.assertEqual(len(res.mass_balance_errors), 0)
        by_name = {s.name: s for s in fs.streams.values()}
        self.assertTrue(by_name["S-feed-tol"].mass_flow_locked,
            "el feed fresco debe seguir locked")
        self.assertTrue(by_name["S-9-recic"].mass_flow_locked,
            "el tear del recycle debe seguir locked (spec del loop)")
        for n in ("S-1", "S-2", "S-3", "S-4", "S-5", "S-6", "S-7", "S-8"):
            self.assertFalse(by_name[n].mass_flow_locked,
                f"{n} es intermedio: debe propagarse, no quedar hardcoded")
        self.assertAlmostEqual(by_name["S-1"].mass_flow, 11000, delta=55)
        self.assertAlmostEqual(by_name["S-benceno"].mass_flow, 8500, delta=43)


if __name__ == "__main__":
    unittest.main(verbosity=2)
