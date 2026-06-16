"""
tests/test_columna_capa1_acetic.py — CAPA 1 del Frente B (columnas activas).

Verifica que la columna terminal limpia `acetic/T-101` quedó ACTIVADA y que
el motor FUG calcula un split FÍSICO (no el hardcode previo):

  · acetic/T-101 tiene column_active=True con LK=methanol / HK=acetic_acid.
  · El split lo calcula el motor: destilado rico en metanol (LK volátil,
    bp 65 °C), fondo rico en ácido acético (HK, bp 118 °C).
  · El balance por componente cierra (Σ feed = Σ salidas).
  · Reproduce razonablemente el split que estaba declarado a mano
    (D≈10, B≈1847; el hardcode "puro" era idealizado, el FUG da 99 %).

Contexto: ver docs/columnas_activas_design.md §4.5 (plan de capas) y la nota
de Capa 1.  dist_eth_az/T-101 (la otra clase-A) se DIFIRIÓ por azeotropía
(FUG emite "AZEOTROPO PASADO": α_top<1, x_D=0.956 > azeótropo eth-water).

USO:  python -m unittest tests.test_columna_capa1_acetic -v
"""
import os
import sys
import json
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from export_examples import _headless_mocks


def _solve_acetic():
    _headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    path = os.path.join(_PARENT, "data", "examples", "acetic.json")
    with open(path, encoding="utf-8") as f:
        fs = fm.Flowsheet.from_dict(json.load(f))
    res = fsv.solve(fs)
    return fs, res


class TestAceticColumnaActiva(unittest.TestCase):

    def setUp(self):
        self.fs, self.res = _solve_acetic()
        self.byname = {b.name: b for b in self.fs.blocks.values()}
        self.sbyname = {s.name: s for s in self.fs.streams.values()}

    def test_columna_esta_activa(self):
        col = self.byname["T-101"]
        self.assertTrue(getattr(col, "column_active", False),
                        "acetic/T-101 debe quedar column_active=True")
        self.assertEqual(col.column_LK, "methanol")
        self.assertEqual(col.column_HK, "acetic_acid")

    def test_split_fisico(self):
        # Destilado (S-vap) rico en metanol; fondo (S-fondo) rico en acético.
        dist = self.sbyname["S-vap"].composition or {}
        bot = self.sbyname["S-fondo"].composition or {}
        self.assertGreater(dist.get("methanol", 0.0), 0.9,
                           f"destilado debe ser metanol-rico; got {dist}")
        self.assertGreater(bot.get("acetic_acid", 0.0), 0.99,
                           f"fondo debe ser acético-rico; got {bot}")

    def test_balance_por_componente_cierra(self):
        feed = self.sbyname["S-4"]
        dist = self.sbyname["S-vap"]
        bot = self.sbyname["S-fondo"]
        for comp in ("methanol", "acetic_acid"):
            m_in = feed.mass_flow * (feed.composition or {}).get(comp, 0.0)
            m_out = (dist.mass_flow * (dist.composition or {}).get(comp, 0.0)
                     + bot.mass_flow * (bot.composition or {}).get(comp, 0.0))
            self.assertAlmostEqual(
                m_in, m_out, delta=max(0.02 * m_in, 0.5),
                msg=f"balance de {comp} no cierra: in={m_in:.3f} out={m_out:.3f}")

    def test_reproduce_split_declarado(self):
        # El hardcode previo: D≈10 (metanol), B≈1847 (acético).
        self.assertAlmostEqual(self.sbyname["S-vap"].mass_flow, 10.0, delta=1.0)
        self.assertAlmostEqual(self.sbyname["S-fondo"].mass_flow, 1847.0, delta=2.0)

    def test_no_hay_errores_de_balance(self):
        # El solver no debe reportar errores duros de masa/energía nuevos.
        self.assertEqual(len(self.res.mass_balance_errors), 0)
        self.assertEqual(len(self.res.energy_balance_errors), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
