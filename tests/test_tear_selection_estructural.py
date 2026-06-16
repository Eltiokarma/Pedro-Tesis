"""
tests/test_tear_selection_estructural.py — selección de tear por ESTRUCTURA.

Endurece la selección de tear para que elija el reciclo físico por la
ESTRUCTURA del grafo (back-edge que vuelve al mixer del feed principal), SIN
depender del tag `role`.  Antes, hda corría vivo (#103) solo porque
corregimos a mano `S-9-recic.role="recycle"`; eso era frágil para la capa
agéntica (flowsheets sin roles pre-taggeados → mispick → convergencia falsa).

El fix (en `flowsheet_solver.py`):
  · `_decompose_scc_cycles`: raíz del spanning tree = entrada con feed externo
    de MAYOR caudal (antes: menor id) → los back-edges son los RETORNOS de
    reciclo, no las feed-lines forward.  Coincide con el docstring previo.
  · `_choose_tear` (mono): rankea los back-edges por el caudal de feed externo
    de su bloque DESTINO (estructura) y deja `role` como desempate secundario.

Condiciones de aceptación medidas:
  · C1 — hda elige `S-9-recic` AUNQUE su role sea "internal" (estructura, no tag).
  · C2 — gate 41/41 byte-idéntico (verificado por `gate_examples.py`, no acá).
  · C3 — hda_full: PARCIAL.  Identifica `S-tol-recic` (reciclo de tolueno) y la
    raíz correcta (P-101), pero el lazo de gas sale como `S-gas-pre` (back-edge
    natural, equivalente a tearear `S-gas-recic`) y aparece `S-3` (falso ciclo
    del HX feed-efluente E-101, 2-in/2-out).  Eliminar esos dos residuos exige
    descomposición a nivel de puertos del HX — frente aparte (documentado).

USO:  python -m unittest tests.test_tear_selection_estructural -v
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


def _load(key, mutate=None):
    _headless_mocks()
    import flowsheet_model as fm
    path = os.path.join(_PARENT, "data", "examples", f"{key}.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if mutate:
        mutate(d)
    return fm.Flowsheet.from_dict(d)


def _recycle_sccs(fs):
    import flowsheet_solver as fsv
    return [s for s in fsv._strongly_connected_components(fs)
            if fsv._is_recycle_scc(s, fs)]


def _strip_recycle_role(d):
    for s in d["streams"].values():
        if s.get("role") == "recycle":
            s["role"] = "internal"


def _unlock_recycles(d, names):
    for s in d["streams"].values():
        if s["name"] in names:
            s["mass_flow_locked"] = False
            s["composition_locked"] = False
            s["role"] = "internal"   # a propósito: probar que NO depende del tag


class TestC1_HdaEstructural(unittest.TestCase):
    """hda elige el reciclo físico por estructura, sin depender de `role`."""

    def _picks(self, mutate=None):
        import flowsheet_solver as fsv
        fs = _load("hda", mutate)
        sccs = _recycle_sccs(fs)
        self.assertEqual(len(sccs), 1)
        scc = sccs[0]
        streams = fsv._streams_in_scc(scc, fs)
        mono = fsv._choose_tear(streams, fs, scc)
        multi = fsv._choose_tears(scc, fs)
        return (mono.name if mono else None, [t.name for t in multi])

    def test_mono_y_multi_con_role(self):
        mono, multi = self._picks()
        self.assertEqual(mono, "S-9-recic")
        self.assertEqual(multi, ["S-9-recic"])

    def test_mono_y_multi_SIN_role(self):
        # C1 dura: aunque S-9-recic esté como role="internal", la estructura
        # (vuelve a P-101, el mixer del feed principal de tolueno) lo elige.
        mono, multi = self._picks(_strip_recycle_role)
        self.assertEqual(mono, "S-9-recic",
                         "mono debe elegir el reciclo por estructura, no por role")
        self.assertEqual(multi, ["S-9-recic"],
                         "multi debe elegir el reciclo por estructura, no por role")

    def test_no_elige_feedline_forward(self):
        # Nunca debe elegir S-2 (arista forward E-101→F-101, feed de makeup H₂).
        mono, multi = self._picks(_strip_recycle_role)
        self.assertNotEqual(mono, "S-2")
        self.assertNotIn("S-2", multi)


class TestC3_HdaFullParcial(unittest.TestCase):
    """hda_full: mejora medible (identifica S-tol-recic; raíz correcta), con
    residuo documentado (S-gas-pre, S-3 del falso ciclo del HX)."""

    def _multi(self, mutate=None):
        import flowsheet_solver as fsv
        fs = _load("hda_full", mutate)
        scc = _recycle_sccs(fs)[0]
        return [t.name for t in fsv._choose_tears(scc, fs)]

    def test_identifica_reciclo_tolueno_si_destearado(self):
        # Con los reciclos des-lockeados (estado futuro), multi agarra el
        # reciclo de tolueno real S-tol-recic por estructura (sin tag role).
        names = self._multi(lambda d: _unlock_recycles(
            d, ("S-gas-recic", "S-tol-recic")))
        self.assertIn("S-tol-recic", names,
                      f"esperaba el reciclo de tolueno; got {names}")

    def test_residuo_documentado(self):
        # RESIDUO conocido (fuera de scope): el lazo de gas sale como S-gas-pre
        # (back-edge natural; tearearlo es equivalente a S-gas-recic) y aparece
        # S-3 (falso ciclo del HX feed-efluente E-101).  Este test FIJA el
        # estado actual para que un futuro fix del HX lo actualice a propósito.
        names = self._multi(lambda d: _unlock_recycles(
            d, ("S-gas-recic", "S-tol-recic")))
        self.assertIn("S-gas-pre", names)   # residuo 1: back-edge del gas
        self.assertIn("S-3", names)         # residuo 2: falso ciclo del HX E-101


if __name__ == "__main__":
    unittest.main(verbosity=2)
