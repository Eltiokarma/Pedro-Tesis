"""
tests/test_propagacion_hx_4puertos.py — propagación de masa PORT-AWARE en HX
de 4 puertos (forward pass).

`_solve_mass_iteration` trataba un HX de 4 puertos (2-in/2-out, lados que NO se
mezclan) como un nodo único: con AMBOS lados vivos quedaban 2 salidas
desconocidas, la regla de bloque (1 incógnita) no disparaba → las salidas
colapsaban a 0 → el reactor aguas abajo se quedaba sin feed.  Es el análogo de
#106 (que hizo port-aware la DETECCIÓN DE CICLOS) pero en el forward pass.

El fix parea inlet↔outlet por lado (tube_in→tube_out, shell_in→shell_out) vía
`_stream_side`, sólo cuando el lado es 1-in/1-out y NINGUNO está mass-locked
(el caso feed-efluente VIVO).  Con un lado anclado (closure de los 41 goldens)
la regla de bloque ya resuelve → byte-idéntico (lo cubre gate_examples).

Fixture: hda_full/E-101 (tube = feed S-1→S-2; shell = efluente R-101 S-4→S-4b).

USO:  python -m unittest tests.test_propagacion_hx_4puertos -v
"""
import os
import sys
import json
import copy
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from export_examples import _headless_mocks


def _solve_with_unlocked(unlock_names):
    """hda_full con ciertos streams des-lockeados (mass+comp); resto baseline."""
    _headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    path = os.path.join(_PARENT, "data", "examples", "hda_full.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    for s in d["streams"].values():
        if s["name"] in unlock_names:
            s["mass_flow_locked"] = False
            s["composition_locked"] = False
            s["composition"] = {}
    fs = fm.Flowsheet.from_dict(d)
    fsv.solve(fs)
    return {s.name: s for s in fs.streams.values()}


class TestPropagacionHX4Puertos(unittest.TestCase):

    def test_e101_es_hx_4puertos(self):
        _headless_mocks()
        import flowsheet_model as fm
        import flowsheet_solver as fsv
        path = os.path.join(_PARENT, "data", "examples", "hda_full.json")
        with open(path, encoding="utf-8") as f:
            fs = fm.Flowsheet.from_dict(json.load(f))
        e101 = next(b.id for b in fs.blocks.values() if b.name == "E-101")
        self.assertIn(e101, fsv._four_port_hx_ids(fs))

    def test_ambos_lados_vivos_no_colapsa(self):
        # AMBOS lados de E-101 des-lockeados (la condición del loop vivo).
        sb = _solve_with_unlocked({"S-2", "S-4", "S-4b"})
        # tube: S-2 (out) == S-1 (in);  shell: S-4b (out) == S-4 (in).
        self.assertAlmostEqual(sb["S-2"].mass_flow, sb["S-1"].mass_flow, delta=1.0)
        self.assertAlmostEqual(sb["S-4b"].mass_flow, sb["S-4"].mass_flow, delta=1.0)
        # NO colapsa a 0.
        self.assertGreater(sb["S-2"].mass_flow, 1000.0)
        self.assertGreater(sb["S-4b"].mass_flow, 1000.0)

    def test_no_cruza_lados(self):
        # tube_out debe seguir al tube_in (~80168), NO al shell (~93305).
        sb = _solve_with_unlocked({"S-2", "S-4", "S-4b"})
        self.assertLess(abs(sb["S-2"].mass_flow - sb["S-1"].mass_flow), 1.0)
        self.assertGreater(abs(sb["S-2"].mass_flow - sb["S-4"].mass_flow), 1000.0)

    def test_un_lado_anclado_sigue_propagando(self):
        # Con sólo un lado libre (el otro anclado) ya funcionaba (regla de
        # bloque); guard de no-regresión.
        sb = _solve_with_unlocked({"S-2"})
        self.assertAlmostEqual(sb["S-2"].mass_flow, sb["S-1"].mass_flow, delta=1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
