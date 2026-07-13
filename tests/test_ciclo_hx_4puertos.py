"""
tests/test_ciclo_hx_4puertos.py — detección de ciclos PORT-AWARE para HX de 4
puertos.

Un HX de 4 puertos (2-in/2-out) tiene dos lados que NO se mezclan (tube/shell,
proceso/servicio).  La detección de ciclos colapsaba el bloque a un nodo único
→ aristas cruzadas falsas (un fluido que entra por un lado "sale" por el otro en
el grafo) → ciclo FALSO que inflaba el circuit rank e introducía un tear espurio.

El fix (`flowsheet_solver._decompose_scc_cycles` + `_scc_circuit_rank`,
port-aware vía `_portaware_nodes`): las aristas de detección de ciclos NO cruzan
lados.

HALLAZGO MEDIDO (corrige la premisa del brief): el HX **NO sale del SCC** — en
un HX feed-efluente ambos lados están genuinamente en el lazo (la recirculación
pasa por el HX dos veces), así que el bloque DEBE seguir en el SCC.  Lo que se
elimina es el ciclo FALSO que cruza sus lados → el circuit rank baja al nº real
de reciclos (hda_full/gas_sweet: 3 → 2) y desaparece el tear espurio.

Los 3 HX de 4 puertos en los 41 (los tres en SCC de reciclo):
  · hda_full/E-101  (tube/shell, feed-efluente)
  · gas_sweet/E-101 (tube/shell, feed-efluente)
  · industrial/E-202 (liq/steam-cond, proceso/servicio)

USO:  python -m unittest tests.test_ciclo_hx_4puertos -v
"""
import os
import sys
import json
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from export_examples import _headless_mocks


def _load(key, live=False):
    _headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    path = os.path.join(_PARENT, "data", "examples", f"{key}.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if live:
        fs0 = fm.Flowsheet.from_dict(json.loads(json.dumps(d)))
        scc = [s for s in fsv._strongly_connected_components(fs0)
               if fsv._is_recycle_scc(s, fs0)][0]
        names = {s.name for s in fsv._streams_in_scc(scc, fs0)}
        for s in d["streams"].values():
            if s["name"] in names:
                s["mass_flow_locked"] = False
    return fm.Flowsheet.from_dict(d)


def _recycle_scc(fs):
    import flowsheet_solver as fsv
    return [s for s in fsv._strongly_connected_components(fs)
            if fsv._is_recycle_scc(s, fs)]


class TestDeteccionHX4Puertos(unittest.TestCase):

    def test_stream_side_mapeo(self):
        import flowsheet_solver as fsv
        self.assertEqual(fsv._stream_side("tube_in"), "tube")
        self.assertEqual(fsv._stream_side("shell_out"), "shell")
        self.assertEqual(fsv._stream_side("steam_in"), "util")
        self.assertEqual(fsv._stream_side("cond_out"), "util")
        self.assertEqual(fsv._stream_side("liq_in"), "proc")
        self.assertIsNone(fsv._stream_side(""))

    def test_los_3_hx_4puertos(self):
        import flowsheet_solver as fsv
        casos = {"hda_full": "E-101", "gas_sweet": "E-101",
                 "industrial": "E-202"}
        for key, hxname in casos.items():
            fs = _load(key)
            ids = fsv._four_port_hx_ids(fs)
            names = {fs.blocks[i].name for i in ids}
            self.assertIn(hxname, names, f"{key}: {hxname} debe ser HX 4-puertos")

    def test_hda_simple_sin_hx_4puertos(self):
        # hda (lazo simple) no tiene HX de 4 puertos → no se afecta.
        import flowsheet_solver as fsv
        fs = _load("hda")
        self.assertEqual(fsv._four_port_hx_ids(fs), set())


class TestCicloFalsoEliminado(unittest.TestCase):
    """El ciclo falso del HX feed-efluente desaparece: rank real 2, sin tear
    espurio.  (El HX SIGUE en el SCC: ambos lados están en el lazo.)"""

    def _scc(self, key):
        import flowsheet_solver as fsv
        fs = _load(key, live=True)
        sccs = _recycle_scc(fs)
        self.assertEqual(len(sccs), 1)
        return fs, sccs[0]

    def test_hda_full_rank_2_sin_S3(self):
        import flowsheet_solver as fsv
        fs, scc = self._scc("hda_full")
        self.assertEqual(fsv._scc_circuit_rank(scc, fs), 2)
        cycles = fsv._decompose_scc_cycles(scc, fs)
        self.assertEqual(len(cycles), 2)
        be = {c["back_edge"].name for c in cycles}
        self.assertNotIn("S-3", be, "S-3 (falso ciclo del HX) no debe ser back-edge")
        self.assertNotIn("S-4", be)
        tears = {t.name for t in fsv._choose_tears(scc, fs)}
        self.assertNotIn("S-3", tears, f"S-3 no debe ser tear; {tears}")
        self.assertIn("S-tol-recic", tears)

    def test_gas_sweet_rank_2(self):
        import flowsheet_solver as fsv
        fs, scc = self._scc("gas_sweet")
        self.assertEqual(fsv._scc_circuit_rank(scc, fs), 2)
        self.assertEqual(len(fsv._decompose_scc_cycles(scc, fs)), 2)

    def test_hx_sigue_en_scc(self):
        # CORRIGE la premisa del brief: el HX feed-efluente NO sale del SCC
        # (ambos lados en el lazo). Lo que cambia es el rank, no la membresía.
        import flowsheet_solver as fsv
        for key, hxname in (("hda_full", "E-101"), ("gas_sweet", "E-101")):
            fs, scc = self._scc(key)
            scc_names = {fs.blocks[b].name for b in scc}
            self.assertIn(hxname, scc_names,
                          f"{key}: {hxname} sigue en el SCC (está en el lazo)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
