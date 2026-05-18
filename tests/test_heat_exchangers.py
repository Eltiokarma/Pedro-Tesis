"""
tests/test_heat_exchangers.py — Cobertura de sizing + costos para
intercambiadores de calor, incluyendo:

  · size_heat_exchanger (con / sin override, clamp mínimo)
  · is_cross_exchange (detección de HX proceso-proceso)
  · Tipo condenser nuevo (CAMBIO 1)
  · Heat integration factor canónico 0.4 (CAMBIO 4)

USO:
    python -m unittest tests.test_heat_exchangers -v
"""
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
import flowsheet_solver as fsv


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _mk_block(eq_type, duty=0.0, S=50.0, **kwargs):
    b = fm.Block(id=1, name="E-1", eq_type=eq_type, S=S)
    b.duty = duty
    for k, v in kwargs.items():
        setattr(b, k, v)
    return b


def _add_stream(fs, sid, src, dst, port_src=None, port_dst=None,
                 mass=0.0, composition=None):
    s = fm.Stream(id=sid, name=f"S-{sid}", src=src, dst=dst,
                   mass_flow=mass,
                   composition=dict(composition or {}),
                   src_port=port_src or "", dst_port=port_dst or "")
    fs.streams[sid] = s
    return s


# ─────────────────────────────────────────────────────────────
# 1. size_heat_exchanger — caso nominal
# ─────────────────────────────────────────────────────────────

class TestSizeHeatExchangerNominal(unittest.TestCase):
    """Q=1000 kW, U=400 W/m²·K, ΔTlm=40 K → A=62.5 m²."""

    def test_fixed_tube_nominal(self):
        b = _mk_block("Heat exch. — fixed tube", duty=1000.0)
        A = es.size_heat_exchanger(b, None)
        self.assertIsNotNone(A)
        self.assertAlmostEqual(A, 62.5, delta=0.625)   # 1 % tolerancia


# ─────────────────────────────────────────────────────────────
# 2. size_heat_exchanger — duty=0 → None
# ─────────────────────────────────────────────────────────────

class TestSizeHeatExchangerDutyCero(unittest.TestCase):
    def test_duty_cero_returns_None(self):
        b = _mk_block("Heat exch. — fixed tube", duty=0.0)
        self.assertIsNone(es.size_heat_exchanger(b, None))

    def test_duty_None_returns_None(self):
        b = _mk_block("Heat exch. — fixed tube", duty=0.0)
        b.duty = None
        self.assertIsNone(es.size_heat_exchanger(b, None))


# ─────────────────────────────────────────────────────────────
# 3. size_heat_exchanger — override
# ─────────────────────────────────────────────────────────────

class TestSizeHeatExchangerOverride(unittest.TestCase):
    """Con U_override=1500 y dtlm_override=10, el solver usa esos
    valores y NO los de la tabla (fixed tube: U=400, ΔTlm=40)."""

    def test_override_aplicado(self):
        b = _mk_block("Heat exch. — fixed tube", duty=1000.0)
        b.U_override = 1500.0
        b.dtlm_override = 10.0
        A = es.size_heat_exchanger(b, None)
        # A = 1000 × 1000 / (1500 × 10) = 66.6667
        self.assertAlmostEqual(A, 66.667, delta=0.667)
        # Verificar NO usa tabla (62.5 con U=400/ΔT=40)
        self.assertNotAlmostEqual(A, 62.5, delta=1.0)

    def test_override_cero_usa_tabla(self):
        # 0 / None ambos significan 'no override' → tabla
        b = _mk_block("Heat exch. — fixed tube", duty=1000.0)
        b.U_override = 0.0           # 0 = no override
        b.dtlm_override = None       # None = no override
        A = es.size_heat_exchanger(b, None)
        self.assertAlmostEqual(A, 62.5, delta=0.625)


# ─────────────────────────────────────────────────────────────
# 4. Clamp de área mínima
# ─────────────────────────────────────────────────────────────

class TestSizeHeatExchangerClampMinimo(unittest.TestCase):
    """Duty minúsculo → A no baja de 0.5 m²."""

    def test_clamp_minimo(self):
        b = _mk_block("Heat exch. — fixed tube", duty=0.001)
        # A computado = 0.001 × 1000 / (400 × 40) = 6.25e-5 m²
        # Clampeado a 0.5
        A = es.size_heat_exchanger(b, None)
        self.assertAlmostEqual(A, 0.5)


# ─────────────────────────────────────────────────────────────
# 5–7. is_cross_exchange
# ─────────────────────────────────────────────────────────────

class TestIsCrossExchange(unittest.TestCase):
    def _make_hx(self, eq_type, n_ins, n_outs):
        fs = fm.Flowsheet()
        b = _mk_block(eq_type, duty=0.0)
        fs.blocks[1] = b
        sid = 100
        for i in range(n_ins):
            _add_stream(fs, sid, 999 + i, 1)
            sid += 1
        for i in range(n_outs):
            _add_stream(fs, sid, 1, 999 + i)
            sid += 1
        return fs, b

    def test_cross_exchange_2x2(self):
        fs, b = self._make_hx("Heat exch. — fixed tube", n_ins=2, n_outs=2)
        self.assertTrue(fsv.is_cross_exchange(fs, b))

    def test_no_cross_1x1(self):
        fs, b = self._make_hx("Heat exch. — fixed tube", n_ins=1, n_outs=1)
        self.assertFalse(fsv.is_cross_exchange(fs, b))

    def test_no_cross_no_es_hx(self):
        fs, b = self._make_hx("Pump — centrifugal", n_ins=2, n_outs=2)
        self.assertFalse(fsv.is_cross_exchange(fs, b))


# ─────────────────────────────────────────────────────────────
# 8. Condensador nuevo (Cambio 1) — sizing térmico
# ─────────────────────────────────────────────────────────────

class TestCondenserNuevo(unittest.TestCase):
    """Q=2000 kW al condenser shell-tube con U=1000 / ΔTlm=15:
        A = 2000 × 1000 / (1000 × 15) = 133.33 m²"""

    def test_condenser_shell_tube_sizing(self):
        b = _mk_block("Heat exch. — condenser shell-tube", duty=2000.0)
        A = es.size_heat_exchanger(b, None)
        self.assertAlmostEqual(A, 133.333, delta=1.33)
        # Confirmar U y ΔTlm de tabla son los nuevos (no defaults)
        self.assertEqual(es.U_TYPICAL["Heat exch. — condenser shell-tube"], 1000)
        self.assertEqual(es.DTLM_TYPICAL["Heat exch. — condenser shell-tube"], 15.0)

    def test_condenser_air_cooled_sizing(self):
        b = _mk_block("Heat exch. — condenser air-cooled", duty=1000.0)
        A = es.size_heat_exchanger(b, None)
        # A = 1000 × 1000 / (600 × 20) = 83.33
        self.assertAlmostEqual(A, 83.333, delta=0.833)


# ─────────────────────────────────────────────────────────────
# 9. Costo Turton del condensador (sanity check)
# ─────────────────────────────────────────────────────────────

class TestCondenserCostoTurton(unittest.TestCase):
    """equipment_costs.purchased_cost no lanza KeyError para los
    eq_type nuevos: la entrada en EQUIPMENT_DATA está bien formada."""

    def test_condenser_shell_tube_cost(self):
        # No debe lanzar KeyError
        pc = ec.purchased_cost("Heat exch. — condenser shell-tube", 100.0)
        self.assertIn("Cp_base", pc)
        self.assertGreater(pc["Cp_base"], 0)

    def test_condenser_air_cooled_cost(self):
        pc = ec.purchased_cost("Heat exch. — condenser air-cooled", 500.0)
        self.assertIn("Cp_base", pc)
        self.assertGreater(pc["Cp_base"], 0)

    def test_shell_tube_misma_correlacion_que_fixed_tube(self):
        # Comparten K1/K2/K3 con fixed tube por diseño
        cond = ec.EQUIPMENT_DATA["Heat exch. — condenser shell-tube"]
        fixed = ec.EQUIPMENT_DATA["Heat exch. — fixed tube"]
        for k in ("K1", "K2", "K3"):
            self.assertEqual(cond[k], fixed[k])


# ─────────────────────────────────────────────────────────────
# 10. Heat integration factor canónico 0.4 (Cambio 4)
# ─────────────────────────────────────────────────────────────

class TestHeatIntegrationConsistencia(unittest.TestCase):
    """HEAT_INTEGRATION['factor'] == get_heat_integration_factor()
    == 0.4 (sin contradicciones entre fuentes)."""

    def test_canonical_factor_es_04(self):
        self.assertEqual(ed.HEAT_INTEGRATION["factor"], 0.4)
        self.assertEqual(ed.get_heat_integration_factor(), 0.4)

    def test_factor_y_dict_coinciden(self):
        self.assertEqual(ed.HEAT_INTEGRATION["factor"],
                          ed.get_heat_integration_factor())


# ─────────────────────────────────────────────────────────────
# Smoke test: serialización backward-compat del Block con
# U_override/dtlm_override (CAMBIO 3)
# ─────────────────────────────────────────────────────────────

class TestBlockSerialization(unittest.TestCase):
    """JSON antiguos sin U_override / dtlm_override deben cargarse
    sin error con esos campos en None (vía Block.__annotations__
    filtering en from_dict).
    """

    def test_block_json_roundtrip_con_override(self):
        b = _mk_block("Heat exch. — fixed tube", duty=500.0)
        b.U_override = 1200.0
        b.dtlm_override = 8.5
        fs = fm.Flowsheet(); fs.blocks[1] = b
        d = fs.to_dict()
        fs2 = fm.Flowsheet.from_dict(d)
        b2 = fs2.blocks[1]
        self.assertEqual(b2.U_override, 1200.0)
        self.assertEqual(b2.dtlm_override, 8.5)

    def test_block_json_legacy_sin_override(self):
        # JSON antiguo: dict del Block SIN las claves nuevas
        old = {
            "blocks": {"1": {"id":1, "name":"E", "eq_type":"Heat exch. — fixed tube",
                              "S":50.0, "duty":500.0}},
            "streams": {}, "_next_id":2,
            "opex_extras":[], "fixed_overrides":{},
        }
        fs = fm.Flowsheet.from_dict(old)
        b = fs.blocks[1]
        # Campos nuevos quedan en default None
        self.assertIsNone(b.U_override)
        self.assertIsNone(b.dtlm_override)


if __name__ == "__main__":
    unittest.main(verbosity=2)
