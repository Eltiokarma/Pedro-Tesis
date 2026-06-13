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
        self.assertEqual(c.origin, "unverified")   # gana el .md, no el overlay

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
        self.assertEqual(td.get("ammonia").origin, "unverified")


class TestSeamEquilibrioOverlay(_OverlayTestBase):
    """Dirección (b) sobre el seam de EQUILIBRIO
    (solve_equilibrium_reactor_from_composition), el más ejercido por los
    reactores del flowsheet.

    HALLAZGO (codificado como invariante, no como argumento): el seam de
    equilibrio solo resuelve reacciones con van't Hoff (A,B), y NINGUNA de
    ellas tiene una especie ausente de thermo_db.  Por eso el caso "producto
    estimado consumido por el seam de equilibrio" NO es disparable con el
    catálogo actual sin inventar una reacción artificial (≠ Capa 4 curada).
    Se cubre, en cambio, con:
      · un INVARIANTE enforced — si alguien agrega una reacción-con-Keq cuyo
        producto falta en thermo_db, este test falla y obliga a estimarlo al
        overlay (cierra el loop sobre el seam de equilibrio en ese momento);
      · una prueba POSITIVA de que el overlay poblado NO perturba el seam de
        equilibrio y el sourceado sigue ganando a través de él.
    """

    def test_invariante_eq_seam_usa_solo_sourceados(self):
        """Todas las especies de reacciones con van't Hoff están sourceadas
        (mw>0).  Convierte el argumento "el seam de equilibrio usa los mismos
        get().mw" en un invariante verificado."""
        faltantes = []
        for rid in rdb.list_ids():
            r = rdb.get(rid)
            if r.vant_hoff_A is None or r.vant_hoff_B is None:
                continue                      # no resuelve por equilibrio
            for s in r.stoich:
                if s.thermo_name is None:
                    continue
                c = td.get(s.thermo_name)
                if c is None or c.mw <= 0:
                    faltantes.append((rid, s.thermo_name))
        self.assertEqual(
            faltantes, [],
            "Reacción(es) con van't Hoff tienen especies ausentes de "
            "thermo_db. Estimalas al overlay (estimated_overlay) para que el "
            f"seam de equilibrio las consuma: {faltantes}")

    def test_eq_seam_no_perturbado_por_overlay(self):
        """El overlay poblado no altera el resultado del seam de equilibrio
        ni sombrea sourceados (R004: N2 + 3H2 ⇌ 2NH3, van't Hoff)."""
        feed = {"nitrogen": 0.25, "hydrogen": 0.75}
        # overlay vacío (setUp lo dejó así)
        r0 = rdb.solve_equilibrium_reactor_from_composition(
            ["R004"], feed, 1.0, 700.0, 200.0)
        self.assertIsNotNone(r0)
        nh3_0 = r0["outlet_composition"]["ammonia"]

        # poblar overlay con un estimado (sin deps: upsert directo)
        ov.upsert("urea", mw=60.06, smiles="NC(N)=O",
                  dh_f_gas_kJ_mol=-109.0,
                  cp_gas_coefs=[71928.0, 0.0, 0.0, 0.0, 0.0],
                  estimation_uncertainty={"dh_f": 5.0})
        self.assertEqual(td.get("urea").origin, "estimated")     # overlay sirve la nueva

        r1 = rdb.solve_equilibrium_reactor_from_composition(
            ["R004"], feed, 1.0, 700.0, 200.0)
        self.assertIsNotNone(r1)
        # idéntico: el overlay no perturba el camino de equilibrio
        self.assertAlmostEqual(r1["outlet_composition"]["ammonia"], nh3_0,
                               delta=1e-12)
        # sourceado gana a través del seam; urea (no participa en R004) ausente
        self.assertEqual(td.get("ammonia").origin, "unverified")
        self.assertNotIn("urea", r1["outlet_composition"])
        self.assertAlmostEqual(sum(r1["outlet_composition"].values()), 1.0,
                               delta=1e-6)


if __name__ == "__main__":
    unittest.main()
