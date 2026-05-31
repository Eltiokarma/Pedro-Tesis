"""
GATE — Overlay de estimados (Capa 4b), DOS DIRECCIONES:

  (a) Overlay VACÍO == idéntico al sourceado: thermo_db.get() no cambia para
      compuestos del .md, y get() de algo no estimado sigue devolviendo None.
      (El no-regresión fuerte 41/41 + suite se corre en gate_examples; acá se
       fija el invariante de no-sombreado.)

  (b) Compuesto ESTIMADO recuperable por get() Y consumible por el seam:
      se estima urea (Joback vía chemfx), se persiste al overlay, thermo_db.get
      la devuelve con origin='estimated', y el seam de reactor la incluye en el
      outlet (hoy, sin overlay, urea se pierde).

El test hace backup/restore de data/estimated_compounds.json para no dejar
estado (el JSON commiteado queda {}).
"""
import os
import json
import unittest

import estimated_overlay as ov
import thermo_db as td
import reactions_db as rdb


def _deps_available():
    try:
        import rdkit       # noqa: F401
        import thermo      # noqa: F401
        import chemicals   # noqa: F401
        return True
    except Exception:
        return False


class _OverlayTestBase(unittest.TestCase):
    def setUp(self):
        # backup del JSON real + dejar overlay vacío
        self._backup = None
        if os.path.exists(ov.OVERLAY_PATH):
            with open(ov.OVERLAY_PATH, encoding="utf-8") as f:
                self._backup = f.read()
        ov.clear()

    def tearDown(self):
        # restaurar el JSON exactamente como estaba
        if self._backup is not None:
            with open(ov.OVERLAY_PATH, "w", encoding="utf-8") as f:
                f.write(self._backup)
        else:
            ov.clear()
        ov.load(force_reload=True)


class TestOverlayVacioIdentico(_OverlayTestBase):
    """Dirección (a)."""

    def test_sourceado_no_sombreado(self):
        c = td.get("methanol")
        self.assertIsNotNone(c)
        self.assertEqual(c.origin, "experimental")   # gana el .md, no el overlay

    def test_overlay_vacio_no_inventa(self):
        self.assertIsNone(td.get("urea"))             # no estimada → None
        self.assertIsNone(td.get("compuesto_inexistente_xyz"))

    def test_json_commiteado_es_vacio(self):
        # El archivo versionado debe estar vacío (invariante de no-regresión).
        if self._backup is not None:
            self.assertEqual(json.loads(self._backup), {})


@unittest.skipUnless(_deps_available(),
                     "requiere rdkit + thermo + chemicals (predictor opcional)")
class TestEstimadoRecuperableYConsumible(_OverlayTestBase):
    """Dirección (b)."""

    def _add_urea(self):
        rec = ov.estimate_and_add("urea", smiles="NC(N)=O", formula="urea")
        self.assertIsNotNone(rec, "Joback no estimó urea")
        return rec

    def test_b1_recuperable_por_get(self):
        rec = self._add_urea()
        # trazabilidad en el registro persistido
        self.assertEqual(rec["source"], "estimated")
        self.assertEqual(rec["estimation_method"], "joback")
        self.assertEqual(rec["smiles"], "NC(N)=O")
        self.assertIn("dh_f", rec["estimation_uncertainty"])
        # recuperable por thermo_db.get con origin='estimated'
        c = td.get("urea")
        self.assertIsNotNone(c)
        self.assertEqual(c.origin, "estimated")
        self.assertEqual(c.quality, "Joback")
        self.assertAlmostEqual(c.mw, 60.06, delta=0.1)
        self.assertIsNotNone(c.dh_f_gas_kJ_mol)
        self.assertEqual(c.smiles, "NC(N)=O")

    def test_b2_consumible_por_el_seam(self):
        feed = {"ammonia": 0.55, "co2": 0.45}
        # SIN overlay: urea se pierde del outlet
        r0 = rdb.solve_stoichiometric_reactor(
            ["R031"], feed, 1.0, 450.0, 150.0, conversion=0.9)
        self.assertIsNotNone(r0)
        self.assertNotIn("urea", r0["outlet_composition"])
        # CON overlay: urea aparece en el outlet, mass-balanceada
        self._add_urea()
        r1 = rdb.solve_stoichiometric_reactor(
            ["R031"], feed, 1.0, 450.0, 150.0, conversion=0.9)
        self.assertIsNotNone(r1)
        self.assertIn("urea", r1["outlet_composition"])
        self.assertGreater(r1["outlet_composition"]["urea"], 0.0)
        self.assertAlmostEqual(sum(r1["outlet_composition"].values()), 1.0,
                               delta=1e-6)

    def test_b_sourceado_sigue_ganando_con_overlay_lleno(self):
        # Con el overlay poblado, un compuesto del .md sigue siendo sourceado.
        self._add_urea()
        self.assertEqual(td.get("ammonia").origin, "experimental")


if __name__ == "__main__":
    unittest.main()
