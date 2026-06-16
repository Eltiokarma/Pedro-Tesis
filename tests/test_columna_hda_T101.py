"""
tests/test_columna_hda_T101.py — CAPA 3 del Frente B (columnas activas en loop).

Verifica que `hda/T-101` (benceno/tolueno) quedó ACTIVADA **dentro de su lazo de
reciclo de tolueno vivo** y que el lazo converge limpio:

  · T-101 column_active=True, LK=benzene / HK=toluene.
  · El tear `S-9-recic` está etiquetado role="recycle" y des-lockeado (el fix
    de DATOS que destraba la selección de tear: `_choose_tear` ya prefiere
    role="recycle" y deja de mispickear la arista forward S-2).
  · El lazo converge (Wegstein vectorial {masa,comp,T} — YA existe en el
    solver): éxito, sin errores de masa.
  · El nodo de mezcla P-101 (feed tolueno fresco + reciclo) balancea Σin=Σout.
  · La columna separa físico: producto S-8 benceno ~0.98, flujo ~7503
    (idéntico al SS frozen); el reciclo S-7 lleva el 2% de benceno de arrastre.
  · Balance por componente en T-101 cierra.

Contexto: ver docs/columnas_activas_design.md §6 (Capa 3). El diagnóstico previo
(`columnas_capa3_hda_diagnostico.md`) sobre-dimensionó el fix como "construir
solver"; el fix real fue DATOS: corregir role="recycle" del tear. El bug latente
de `_choose_tear` (mispickea sin el tag) queda anotado como mejora aparte.

USO:  python -m unittest tests.test_columna_hda_T101 -v
"""
import os
import sys
import json
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from export_examples import _headless_mocks


def _solve_hda():
    _headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    path = os.path.join(_PARENT, "data", "examples", "hda.json")
    with open(path, encoding="utf-8") as f:
        fs = fm.Flowsheet.from_dict(json.load(f))
    res = fsv.solve(fs)
    return fs, res


class TestHdaColumnaEnLoop(unittest.TestCase):

    def setUp(self):
        self.fs, self.res = _solve_hda()
        self.byname = {b.name: b for b in self.fs.blocks.values()}
        self.sbyname = {s.name: s for s in self.fs.streams.values()}

    def test_columna_activa(self):
        col = self.byname["T-101"]
        self.assertTrue(getattr(col, "column_active", False))
        self.assertEqual(col.column_LK, "benzene")
        self.assertEqual(col.column_HK, "toluene")

    def test_tear_es_recycle(self):
        # El fix de datos: el reciclo de tolueno está etiquetado role="recycle".
        s = self.sbyname["S-9-recic"]
        self.assertEqual(getattr(s, "role", None), "recycle")
        self.assertFalse(s.mass_flow_locked, "el tear debe estar des-lockeado")

    def test_loop_converge_sin_errores(self):
        self.assertTrue(self.res.success, "el lazo vivo debe converger")
        self.assertEqual(len(self.res.mass_balance_errors), 0,
                         f"mass errors: {self.res.mass_balance_errors}")

    def test_P101_mezcla_balancea(self):
        # P-101 = nodo de mezcla feed-tolueno + reciclo: Σin = Σout.
        ins = sum(s.mass_flow for s in self.fs.streams.values()
                  if self.byname.get("P-101")
                  and s.dst == self.byname["P-101"].id)
        outs = sum(s.mass_flow for s in self.fs.streams.values()
                   if self.byname.get("P-101")
                   and s.src == self.byname["P-101"].id)
        self.assertGreater(ins, 1.0)
        self.assertAlmostEqual(ins, outs, delta=max(0.01 * ins, 1.0))

    def test_producto_benceno_fisico(self):
        s8 = self.sbyname["S-8"]
        self.assertAlmostEqual((s8.composition or {}).get("benzene", 0.0),
                               0.98, delta=0.03)
        self.assertAlmostEqual(s8.mass_flow, 7503.0, delta=20.0)

    def test_reciclo_lleva_arrastre(self):
        # El reciclo (tolueno) ahora lleva el ~2% de benceno de arrastre real.
        s7 = self.sbyname["S-7"]
        self.assertGreater((s7.composition or {}).get("toluene", 0.0), 0.9)
        self.assertGreater((s7.composition or {}).get("benzene", 0.0), 0.0)

    def test_balance_componente_columna(self):
        feed = self.sbyname["S-6"]
        s7 = self.sbyname["S-7"]
        s8 = self.sbyname["S-8"]
        for comp in ("benzene", "toluene"):
            m_in = feed.mass_flow * (feed.composition or {}).get(comp, 0.0)
            m_out = (s7.mass_flow * (s7.composition or {}).get(comp, 0.0)
                     + s8.mass_flow * (s8.composition or {}).get(comp, 0.0))
            self.assertAlmostEqual(
                m_in, m_out, delta=max(0.02 * m_in, 1.0),
                msg=f"balance de {comp}: in={m_in:.2f} out={m_out:.2f}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
