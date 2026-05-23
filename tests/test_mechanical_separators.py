"""
tests/test_mechanical_separators.py — Solver unificado de separadores
mecánicos (mech_sep_active): filtro/centrífuga/ciclón/decanter.

Cubre:
  · Decanter — gravity: split líquido-líquido por densidad, η declarada.
  · Cyclone vía modelo nuevo (target_phase='solid'): venteo sin sólido a η.
  · Centrífuga vía modelo nuevo (target_phase='solid').
  · Regresión: bloque SIN flag = pass-through (no separa).

USO:
    python -m unittest tests.test_mechanical_separators -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_model as fm
import flowsheet_solver as fsv


def _fs_with(eq_type, feed_comp, feed_mass, out_ports, **block_kw):
    """Construye fs con un bloque + feed lockeado + N salidas libres."""
    fs = fm.Flowsheet()
    b = fm.Block(id=1, name="X-1", eq_type=eq_type, S=10.0)
    for k, v in block_kw.items():
        setattr(b, k, v)
    fs.blocks[1] = b
    feed = fm.Stream(id=2, name="S-in", src=0, dst=1, mass_flow=feed_mass,
                     composition=dict(feed_comp),
                     main_component=max(feed_comp, key=feed_comp.get))
    feed.mass_flow_locked = True
    feed.composition_locked = True
    fs.streams[2] = feed
    outs = {}
    sid = 3
    for port in out_ports:
        s = fm.Stream(id=sid, name=f"S-{port}", src=1, dst=0, src_port=port)
        fs.streams[sid] = s
        outs[port] = s
        sid += 1
    return fs, b, outs


class TestDecanter(unittest.TestCase):
    def test_decanter_density_split(self):
        # 50/50 biodiesel (ρ≈850) / glicerina (ρ≈1260).  ρ_avg=1055 →
        # glicerina es la fase pesada (target).  η=0.95.
        fs, b, outs = _fs_with(
            "Decanter — gravity",
            {"biodiesel": 0.5, "glycerin": 0.5}, 1000.0,
            ["fase_pesada", "fase_liviana"],
            mech_sep_active=True, mech_sep_efficiency=0.95,
            mech_sep_target_phase="liquid")
        msgs = fsv.solve_mechanical_separators(fs)
        pesada = outs["fase_pesada"]; liviana = outs["fase_liviana"]
        # pesada = glicerina × 0.95 = 475
        self.assertAlmostEqual(pesada.mass_flow, 475.0, delta=1.0)
        # liviana = biodiesel(500) + glicerina×0.05(25) = 525
        self.assertAlmostEqual(liviana.mass_flow, 525.0, delta=1.0)
        # conservación
        self.assertAlmostEqual(pesada.mass_flow + liviana.mass_flow,
                               1000.0, delta=1e-6)
        # composición: la pesada es casi pura glicerina
        self.assertGreater(pesada.composition.get("glycerin", 0), 0.95)
        self.assertTrue(any(m.startswith("✓") for m in msgs))

    def test_decanter_un_componente_passthrough(self):
        # Feed de un solo componente → no hay dos fases que decantar →
        # pass-through (sin inventar separación).
        fs, b, outs = _fs_with(
            "Decanter — gravity",
            {"water": 1.0}, 1000.0,
            ["fase_pesada", "fase_liviana"],
            mech_sep_active=True, mech_sep_efficiency=0.9)
        msgs = fsv.solve_mechanical_separators(fs)
        self.assertTrue(any("pass-through" in m for m in msgs))


class TestCycloneNewModel(unittest.TestCase):
    def test_cyclone_solid_to_producto(self):
        # aire (gas) + arena (solid).  target_phase=solid, η=0.9.
        fs, b, outs = _fs_with(
            "Cyclone — gas/solid",
            {"air": 0.7, "sand": 0.3}, 1000.0,
            ["producto", "venteo"],
            mech_sep_active=True, mech_sep_efficiency=0.9,
            mech_sep_target_phase="solid")
        fsv.solve_mechanical_separators(fs)
        # producto = arena × 0.9 = 270; venteo = aire(700) + arena×0.1(30)=730
        self.assertAlmostEqual(outs["producto"].mass_flow, 270.0, delta=1.0)
        self.assertAlmostEqual(outs["venteo"].mass_flow, 730.0, delta=1.0)
        # el venteo casi no tiene sólido
        self.assertLess(outs["venteo"].composition.get("sand", 1.0), 0.05)


class TestCentrifugeNewModel(unittest.TestCase):
    def test_centrifuge_solid_liquid(self):
        # slurry 50/50 sólido(NaCl)/agua, η=0.95, target solid → solido.
        fs, b, outs = _fs_with(
            "Centrifuge — decanter",
            {"nacl": 0.5, "water": 0.5}, 1000.0,
            ["solido", "liquido"],
            mech_sep_active=True, mech_sep_efficiency=0.95,
            mech_sep_target_phase="solid")
        fsv.solve_mechanical_separators(fs)
        self.assertAlmostEqual(outs["solido"].mass_flow, 475.0, delta=1.0)
        self.assertAlmostEqual(outs["liquido"].mass_flow, 525.0, delta=1.0)


class TestRegressionNoFlag(unittest.TestCase):
    def test_sin_flag_no_separa(self):
        # Sin mech_sep_active ni separator/cyclone_active → el solver no
        # procesa el bloque (pass-through: las salidas quedan sin escribir).
        fs, b, outs = _fs_with(
            "Centrifuge — decanter",
            {"nacl": 0.5, "water": 0.5}, 1000.0,
            ["solido", "liquido"])
        msgs = fsv.solve_mechanical_separators(fs)
        self.assertEqual(outs["solido"].mass_flow, 0.0)
        self.assertEqual(outs["liquido"].mass_flow, 0.0)
        # no debe haber msg de este bloque
        self.assertFalse(any("X-1" in m for m in msgs))

    def test_locks_respetados(self):
        # Si las salidas están lockeadas, el solver NO las sobreescribe.
        fs, b, outs = _fs_with(
            "Cyclone — gas/solid",
            {"air": 0.7, "sand": 0.3}, 1000.0,
            ["producto", "venteo"],
            mech_sep_active=True, mech_sep_efficiency=0.9,
            mech_sep_target_phase="solid")
        outs["producto"].mass_flow = 123.0
        outs["producto"].mass_flow_locked = True
        fsv.solve_mechanical_separators(fs)
        self.assertEqual(outs["producto"].mass_flow, 123.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
