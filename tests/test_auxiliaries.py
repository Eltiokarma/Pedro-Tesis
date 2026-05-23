"""
tests/test_auxiliaries.py — auto-instanciación de corrientes auxiliares
(equipment_auxiliaries).

Cubre:
  · Instanciación por eq_type (HX, air cooler, fired heater, cooling tower,
    reactor jacketed) con role/phase/composition correctos y auto_aux=True.
  · aux_user_edited → no instancia.
  · No duplica si el puerto ya tiene stream.
  · Bloque sin spec → no instancia.
  · No-doble-contar: costing rellena mass_flow del aux y cuenta el costo.
  · Backwards compat: from_dict no auto-puebla.
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_model as fm
import equipment_auxiliaries as aux


def _block(eq_type, **kw):
    fs = fm.Flowsheet()
    bid = fs.new_id()
    b = fm.Block(id=bid, name="X-1", eq_type=eq_type, S=10.0, x=200, y=200)
    for k, v in kw.items():
        setattr(b, k, v)
    fs.blocks[bid] = b
    return fs, b


def _aux_streams(fs):
    return [s for s in fs.streams.values() if getattr(s, "auto_aux", False)]


def _aux_blocks(fs):
    return [b for b in fs.blocks.values() if getattr(b, "auto_aux", False)]


def _block_ports(fs, block_id):
    """Puertos del bloque principal usados por las corrientes auxiliares."""
    out = set()
    for s in _aux_streams(fs):
        if s.src == block_id:
            out.add(s.src_port)
        elif s.dst == block_id:
            out.add(s.dst_port)
    return out


class TestInstantiation(unittest.TestCase):
    def test_hx_shell_utility(self):
        fs, b = _block("Heat exch. — floating head")
        ids = aux.instantiate_auxiliaries(fs, b)
        streams = _aux_streams(fs)
        self.assertEqual(len(streams), 2)           # shell_in + shell_out
        self.assertEqual(len(_aux_blocks(fs)), 2)   # source + sink
        ports = _block_ports(fs, b.id)
        self.assertEqual(ports, {"shell_in", "shell_out"})
        for s in streams:
            self.assertEqual(s.role, "utility")
            self.assertEqual(s.composition, {"water": 1.0})
            self.assertFalse(s.mass_flow_locked)

    def test_air_cooler_ambient(self):
        fs, b = _block("Heat exch. — air cooler")
        aux.instantiate_auxiliaries(fs, b)
        streams = _aux_streams(fs)
        self.assertEqual(len(streams), 2)
        for s in streams:
            self.assertEqual(s.role, "ambient")
            self.assertEqual(s.composition, {"air": 1.0})

    def test_fired_heater_fuel_and_stack(self):
        fs, b = _block("Fired heater — non-reformer")
        aux.instantiate_auxiliaries(fs, b)
        streams = _aux_streams(fs)
        roles = sorted(s.role for s in streams)
        self.assertEqual(roles, ["ambient", "utility"])   # stack + fuel
        fuel = next(s for s in streams if s.role == "utility")
        self.assertEqual(fuel.dst_port, "combustible")
        self.assertEqual(fuel.composition, {"methane": 1.0})

    def test_cooling_tower_three_aux(self):
        fs, b = _block("Cooling tower — induced draft")
        aux.instantiate_auxiliaries(fs, b)
        streams = _aux_streams(fs)
        self.assertEqual(len(streams), 3)   # makeup + blowdown + vapor_loss
        ports = _block_ports(fs, b.id)
        self.assertEqual(ports, {"makeup", "blowdown", "vapor_loss"})

    def test_reactor_jacket(self):
        fs, b = _block("Reactor — jacketed agitated")
        aux.instantiate_auxiliaries(fs, b)
        ports = _block_ports(fs, b.id)
        self.assertEqual(ports, {"util_in", "util_out"})

    def test_no_spec_no_aux(self):
        fs, b = _block("Pump — centrifugal")
        ids = aux.instantiate_auxiliaries(fs, b)
        self.assertEqual(ids, [])
        self.assertEqual(_aux_streams(fs), [])

    def test_user_edited_skips(self):
        fs, b = _block("Heat exch. — floating head", aux_user_edited=True)
        ids = aux.instantiate_auxiliaries(fs, b)
        self.assertEqual(ids, [])

    def test_no_duplicate_existing_port(self):
        fs, b = _block("Heat exch. — floating head")
        # ya hay un stream en shell_in
        sid = fs.new_id()
        fs.streams[sid] = fm.Stream(id=sid, name="S-x", src=99, dst=b.id,
                                    dst_port="shell_in")
        aux.instantiate_auxiliaries(fs, b)
        ports = _block_ports(fs, b.id)
        self.assertNotIn("shell_in", ports)   # no se duplicó
        self.assertIn("shell_out", ports)


class TestCostingFill(unittest.TestCase):
    def test_aux_fill_and_count(self):
        import flowsheet_export as fexp
        # HX cooler con duty<0 + su aux CW.  El costing debe rellenar el
        # mass_flow del aux y CONTAR el costo (no es closed-loop real).
        fs, b = _block("Heat exch. — floating head")
        b.duty = -500.0
        # feed de proceso para T_avg
        fid = fs.new_id()
        fs.streams[fid] = fm.Stream(id=fid, name="S-p", src=0, dst=b.id,
                                    mass_flow=1000.0, temperature=80.0,
                                    composition={"water": 1.0},
                                    main_component="water")
        aux.instantiate_auxiliaries(fs, b)
        rows, summary = fexp.compute_utilities_from_duties(fs)
        # el cooler aparece en el summary con costo > 0 (no "closed loop")
        names = [row[0] for row in summary]
        self.assertIn("X-1", names)
        self.assertFalse(any(row[1] == "(closed loop)" and row[0] == "X-1"
                             for row in summary))
        # el aux CW entrando (shell_in) quedó con mass_flow > 0
        cw_in = next((s for s in _aux_streams(fs)
                      if s.dst == b.id and s.dst_port == "shell_in"), None)
        self.assertIsNotNone(cw_in)
        self.assertGreater(cw_in.mass_flow, 0.0)


class TestValidationSuppressed(unittest.TestCase):
    def test_aux_streams_no_warnings(self):
        import flowsheet_validation as fval
        fs, b = _block("Heat exch. — floating head")
        aux.instantiate_auxiliaries(fs, b)
        issues = fval.validate_all_streams(fs)
        # ninguna de las issues corresponde a una corriente auxiliar
        aux_names = {s.name for s in _aux_streams(fs)}
        self.assertFalse(any(name in aux_names for name, _, _ in issues))


class TestBackwardsCompat(unittest.TestCase):
    def test_from_dict_no_autopopulate(self):
        # Flowsheet "viejo": un HX sin auto_aux ni aux streams.
        fs = fm.Flowsheet()
        bid = fs.new_id()
        fs.blocks[bid] = fm.Block(id=bid, name="E-1",
                                  eq_type="Heat exch. — floating head", S=10.0)
        d = fs.to_dict()
        fs2 = fm.Flowsheet.from_dict(d)
        # cargar NO crea auxiliares
        self.assertEqual(_aux_streams(fs2), [])
        self.assertEqual(_aux_blocks(fs2), [])
        # y los flags nuevos cargan con default False
        b2 = next(iter(fs2.blocks.values()))
        self.assertFalse(getattr(b2, "auto_aux", False))
        self.assertFalse(getattr(b2, "aux_user_edited", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
