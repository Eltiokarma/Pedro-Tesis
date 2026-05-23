"""
tests/test_distillation_columns.py — Cobertura de sizing + costos
para columnas de destilación, incluyendo:

  · size_tower con defaults canónicos y overrides
  · packing_type: platos vs random vs structured
  · Tipos packing nuevos (Packing — random / structured)
  · COLUMN_DEFAULTS consistencia (cambio 3)
  · Backward-compat de los 6 campos nuevos en Block

USO:
    python -m unittest tests.test_distillation_columns -v
"""
import math
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import econ_defaults as ed
import equipment_costs as ec
import equipment_sizing as es
import flowsheet_model as fm


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _make_tower(N=20, **block_kwargs):
    """Construye un FS con una tower de N etapas y un feed de vapor
    (necesario para que size_tower calcule D vía Souders-Brown)."""
    fs = fm.Flowsheet()
    b = fm.Block(id=1, name="T-101", eq_type="Tower (column shell)",
                  S=50.0)
    b.column_N_stages = N
    for k, v in block_kwargs.items():
        setattr(b, k, v)
    fs.blocks[1] = b
    # Vapor stream entrante
    s = fm.Stream(id=2, name="S-vap", src=0, dst=1, mass_flow=1000,
                   phase="vapor", composition={"methane": 1.0},
                   main_component="methane")
    s.mass_flow_locked = True
    s.composition_locked = True
    fs.streams[2] = s
    return fs, b


# ─────────────────────────────────────────────────────────────
# Tipos packing nuevos (Cambio 1)
# ─────────────────────────────────────────────────────────────

class TestPackingTypesNuevos(unittest.TestCase):
    def test_packing_random_existe_y_cuesta(self):
        self.assertIn("Packing — random", ec.EQUIPMENT_DATA)
        pc = ec.purchased_cost("Packing — random", 50.0)
        self.assertGreater(pc["Cp_base"], 0)

    def test_packing_structured_existe_y_cuesta_mas_que_random(self):
        self.assertIn("Packing — structured", ec.EQUIPMENT_DATA)
        pc_r = ec.purchased_cost("Packing — random",     50.0)["Cp_base"]
        pc_s = ec.purchased_cost("Packing — structured", 50.0)["Cp_base"]
        # Estructurado es 1.5–2× más caro por m³
        self.assertGreater(pc_s, pc_r)
        self.assertLess(pc_s / pc_r, 3.0)

    def test_packing_categoria_correcta(self):
        for k in ("Packing — random", "Packing — structured"):
            self.assertEqual(ec.EQUIPMENT_DATA[k]["categoria"],
                              "Trays / packing")


# ─────────────────────────────────────────────────────────────
# size_tower — defaults canónicos
# ─────────────────────────────────────────────────────────────

class TestSizeTowerDefaults(unittest.TestCase):
    """Sin overrides: usa COLUMN_DEFAULTS de econ_defaults."""

    def test_default_platos_N20(self):
        # H se calcula desde la FÓRMULA con los defaults canónicos (no
        # un literal) para que el test no re-rompa si cambia el default:
        #   N_real = N / tray_eff ;  H = N_real·tray_space + head
        # D = 0.30 (clamp mínimo, vapor pequeño).  V = π/4·D²·H
        d = ed.get_column_defaults()
        N_real = 20 / d["tray_efficiency"]
        H_expected = N_real * d["tray_spacing_m"] + d["column_head_height_m"]
        fs, b = _make_tower(N=20)
        V = es.size_tower(b, fs)
        self.assertIsNotNone(V)
        expected_V = math.pi / 4 * 0.30**2 * H_expected
        self.assertAlmostEqual(V, expected_V, delta=0.1)

    def test_default_sin_feed_None(self):
        # Sin feed conectado: size_tower devuelve None (necesita vapor
        # para calcular el diámetro Souders-Brown).
        fs = fm.Flowsheet()
        b = fm.Block(id=1, name="T", eq_type="Tower (column shell)", S=50)
        fs.blocks[1] = b
        self.assertIsNone(es.size_tower(b, fs))


# ─────────────────────────────────────────────────────────────
# size_tower — overrides
# ─────────────────────────────────────────────────────────────

class TestSizeTowerOverrides(unittest.TestCase):
    def test_tray_spacing_override(self):
        # Override de tray_spacing a 0.46 m (18"); tray_efficiency queda
        # en el default canónico (NO se overridea acá), así que la altura
        # se calcula con ese default vía fórmula:
        #   N_real = N / tray_eff ;  H = N_real·0.46 + head
        d = ed.get_column_defaults()
        N_real = 20 / d["tray_efficiency"]
        H_expected = N_real * 0.46 + d["column_head_height_m"]
        fs, b = _make_tower(N=20, tray_spacing_m=0.46)
        V = es.size_tower(b, fs)
        expected_V = math.pi / 4 * 0.30**2 * H_expected
        self.assertAlmostEqual(V, expected_V, delta=0.1)

    def test_tray_efficiency_aumenta_etapas_reales(self):
        # eff 0.65 → N_real = 30.77 → H = 30.77·0.6 + 3 = 21.46 m
        fs, b = _make_tower(N=20, tray_efficiency=0.65)
        V = es.size_tower(b, fs)
        expected_V = math.pi / 4 * 0.30**2 * 21.46
        self.assertAlmostEqual(V, expected_V, delta=0.2)

    def test_column_head_height_override(self):
        # Override de head a 5 m; tray_efficiency queda en el default
        # canónico, así que la altura se calcula con ese default:
        #   N_real = N / tray_eff ;  H = N_real·tray_space + 5.0
        d = ed.get_column_defaults()
        N_real = 20 / d["tray_efficiency"]
        H_expected = N_real * d["tray_spacing_m"] + 5.0
        fs, b = _make_tower(N=20, column_head_height_m=5.0)
        V = es.size_tower(b, fs)
        expected_V = math.pi / 4 * 0.30**2 * H_expected
        self.assertAlmostEqual(V, expected_V, delta=0.1)

    def test_override_cero_o_None_usa_default(self):
        # Tray spacing en 0 → usa default 0.6
        fs, b = _make_tower(N=20, tray_spacing_m=0.0)
        V1 = es.size_tower(b, fs)
        # Tray spacing = None → usa default 0.6
        fs, b = _make_tower(N=20, tray_spacing_m=None)
        V2 = es.size_tower(b, fs)
        self.assertAlmostEqual(V1, V2)


# ─────────────────────────────────────────────────────────────
# size_tower — packing_type
# ─────────────────────────────────────────────────────────────

class TestSizeTowerPackingType(unittest.TestCase):
    """Empacada (random/structured): usa HETP en lugar de tray_spacing,
    y tray_efficiency se ignora (la incorpora HETP)."""

    def test_random_packing_default_HETP(self):
        # HETP default 0.5 → H = 20·0.5 + 3 = 13 m
        fs, b = _make_tower(N=20, packing_type="random")
        V = es.size_tower(b, fs)
        expected_V = math.pi / 4 * 0.30**2 * 13.0
        self.assertAlmostEqual(V, expected_V, delta=0.1)

    def test_structured_HETP_chico(self):
        # HETP override 0.3 → H = 20·0.3 + 3 = 9 m
        fs, b = _make_tower(N=20, packing_type="structured",
                              HETP_m=0.3)
        V = es.size_tower(b, fs)
        expected_V = math.pi / 4 * 0.30**2 * 9.0
        self.assertAlmostEqual(V, expected_V, delta=0.1)

    def test_packing_ignora_tray_efficiency(self):
        # tray_efficiency=0.5 NO debe afectar empacada
        fs, b = _make_tower(N=20, packing_type="random",
                              HETP_m=0.5, tray_efficiency=0.5)
        V = es.size_tower(b, fs)
        # Si ignora eff: H = 20·0.5 + 3 = 13
        expected_V = math.pi / 4 * 0.30**2 * 13.0
        self.assertAlmostEqual(V, expected_V, delta=0.1)


# ─────────────────────────────────────────────────────────────
# COLUMN_DEFAULTS canónicos (Cambio 3)
# ─────────────────────────────────────────────────────────────

class TestColumnDefaultsCanonical(unittest.TestCase):
    def test_get_column_defaults_estructura(self):
        d = ed.get_column_defaults()
        for k in ("K_souders_brown", "tray_spacing_m",
                   "column_head_height_m", "tray_efficiency", "HETP_m"):
            self.assertIn(k, d)
            self.assertGreater(d[k], 0)

    def test_defaults_valores_esperados(self):
        d = ed.get_column_defaults()
        self.assertEqual(d["K_souders_brown"],      0.06)
        self.assertEqual(d["tray_spacing_m"],       0.6)
        self.assertEqual(d["column_head_height_m"], 3.0)
        # tray_efficiency default = 0.7 (valor industrial genérico).
        # Antes era 1.0 (teorico=real); el cambio sube la altura de
        # columnas con FUG sin tray_efficiency declarado por ~30-43%.
        self.assertEqual(d["tray_efficiency"],      0.7)
        self.assertEqual(d["HETP_m"],               0.5)

    def test_get_column_defaults_devuelve_copia(self):
        # No debe poder mutar el canónico por error
        d1 = ed.get_column_defaults()
        d1["tray_spacing_m"] = 999.0
        d2 = ed.get_column_defaults()
        self.assertEqual(d2["tray_spacing_m"], 0.6)


# ─────────────────────────────────────────────────────────────
# Backward-compat de los 6 campos nuevos en Block
# ─────────────────────────────────────────────────────────────

class TestBlockBackwardCompat(unittest.TestCase):
    def test_block_default_sin_overrides(self):
        b = fm.Block(id=1, name="T", eq_type="Tower (column shell)", S=50)
        # Todos los nuevos campos en None / '' (default)
        self.assertIsNone(b.tray_spacing_m)
        self.assertIsNone(b.K_souders_brown)
        self.assertIsNone(b.column_head_height_m)
        self.assertIsNone(b.tray_efficiency)
        self.assertIsNone(b.HETP_m)
        self.assertEqual(b.packing_type, "")

    def test_block_json_roundtrip_con_overrides(self):
        b = fm.Block(id=1, name="T", eq_type="Tower (column shell)", S=50)
        b.tray_spacing_m       = 0.76
        b.K_souders_brown      = 0.04
        b.column_head_height_m = 4.5
        b.tray_efficiency      = 0.65
        b.HETP_m               = 0.3
        b.packing_type         = "structured"
        fs = fm.Flowsheet(); fs.blocks[1] = b
        d = fs.to_dict()
        fs2 = fm.Flowsheet.from_dict(d)
        b2 = fs2.blocks[1]
        self.assertEqual(b2.tray_spacing_m,       0.76)
        self.assertEqual(b2.K_souders_brown,      0.04)
        self.assertEqual(b2.column_head_height_m, 4.5)
        self.assertEqual(b2.tray_efficiency,      0.65)
        self.assertEqual(b2.HETP_m,               0.3)
        self.assertEqual(b2.packing_type,         "structured")

    def test_block_json_legacy_sin_claves(self):
        # JSON antiguo sin las claves nuevas → defaults None / ''
        old = {
            "blocks": {"1": {"id":1, "name":"T",
                              "eq_type":"Tower (column shell)",
                              "S":50.0}},
            "streams": {}, "_next_id":2,
            "opex_extras":[], "fixed_overrides":{},
        }
        fs = fm.Flowsheet.from_dict(old)
        b = fs.blocks[1]
        self.assertIsNone(b.tray_spacing_m)
        self.assertIsNone(b.K_souders_brown)
        self.assertIsNone(b.column_head_height_m)
        self.assertIsNone(b.tray_efficiency)
        self.assertIsNone(b.HETP_m)
        self.assertEqual(b.packing_type, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
