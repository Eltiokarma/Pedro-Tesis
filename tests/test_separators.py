"""
tests/test_separators.py — Tests para los modelos internos de
separadores mecánicos (filtros, centrífugas, secadores,
cristalizadores, evaporadores, ciclones).

Cubre:
  · Modo unlocked: solver computa outputs desde recovery/moisture
  · Modo locked:   solver respeta outputs ya declarados
  · Sugar mill end-to-end: balance cierra con separator/dryer
    activos sin composiciones hardcodeadas

USO:
    python -m unittest tests.test_separators -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import flowsheet_model as fm
import flowsheet_solver as fsv


# Tolerancia balance masa (consistente con el resto del solver)
MASS_TOL = 1e-6


def _make_block(eq_type, **kwargs):
    """Helper para crear un Block con los args mínimos."""
    b = fm.Block(id=1, name="X-1", eq_type=eq_type, S=10.0)
    for k, v in kwargs.items():
        setattr(b, k, v)
    return b


def _add_feed(fs, block_id, mass_flow, composition, main_component):
    s = fm.Stream(id=2, name="S-in", src=0, dst=block_id,
                   mass_flow=mass_flow, composition=composition,
                   main_component=main_component)
    s.mass_flow_locked   = True
    s.composition_locked = True
    fs.streams[2] = s
    return s


def _add_out(fs, sid, name, block_id, port, locked=False,
              mass=None, composition=None):
    s = fm.Stream(id=sid, name=name, src=block_id, dst=0, src_port=port)
    if mass is not None:
        s.mass_flow = mass
        s.mass_flow_locked = locked
    if composition is not None:
        s.composition = dict(composition)
        s.composition_locked = locked
    fs.streams[sid] = s
    return s


# ─────────────────────────────────────────────────────────────
# Filtro / Centrífuga (separator_active)
# ─────────────────────────────────────────────────────────────

class TestSeparatorUnlocked(unittest.TestCase):
    """Outputs SIN lock → el solver los computa desde recovery + moisture."""

    def test_filter_basic_balance(self):
        fs = fm.Flowsheet()
        b = _make_block("Filter — belt",
                         separator_active=True,
                         solids_recovery=0.95,
                         cake_moisture=0.30,
                         solid_components=["sucrose"])
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0, {"sucrose": 0.5, "water": 0.5}, "sucrose")
        cake = _add_out(fs, 3, "S-cake", 1, "producto")
        filt = _add_out(fs, 4, "S-filt", 1, "venteo")

        msgs = fsv.solve_separators(fs)
        self.assertTrue(any("Separator" in m for m in msgs))

        # Balance global
        self.assertAlmostEqual(cake.mass_flow + filt.mass_flow, 1000.0,
                                  delta=MASS_TOL)

        # Recovery: 95 % sucrose va a cake
        sucrose_cake = cake.composition["sucrose"] * cake.mass_flow
        sucrose_filt = filt.composition["sucrose"] * filt.mass_flow
        self.assertAlmostEqual(sucrose_cake, 500 * 0.95, delta=1.0)
        self.assertAlmostEqual(sucrose_filt, 500 * 0.05, delta=1.0)

        # Cake moisture: 30 % de la torta es agua
        self.assertAlmostEqual(cake.composition["water"], 0.30, delta=0.01)

    def test_centrifuge_uses_solido_liquido_ports(self):
        fs = fm.Flowsheet()
        b = _make_block("Centrifuge — disc stack",
                         separator_active=True,
                         solids_recovery=0.92,
                         cake_moisture=0.10,
                         solid_components=["biomass"])
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"biomass": 0.10, "water": 0.90}, "water")
        cake = _add_out(fs, 3, "S-solid", 1, "solido")
        moth = _add_out(fs, 4, "S-liquid", 1, "liquido")

        fsv.solve_separators(fs)

        self.assertAlmostEqual(cake.mass_flow + moth.mass_flow, 1000.0,
                                  delta=MASS_TOL)
        # cake masa: M_solid_cake / (1 - moist) = 92 / 0.90 = 102.2
        self.assertAlmostEqual(cake.mass_flow, 102.22, delta=0.1)


class TestSeparatorPassthrough(unittest.TestCase):
    """Bug fixes D/F/G/J: cuando el equipo no puede operar (falta
    el material esperado), debe pasar el feed al output principal
    SIN inventar masa y SIN dejar todo en cero."""

    def test_separator_feed_sin_solidos_passthrough(self):
        fs = fm.Flowsheet()
        b = _make_block("Filter — belt",
                         separator_active=True,
                         solids_recovery=0.95,
                         cake_moisture=0.30,
                         solid_components=["MISSING"])
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"a": 0.5, "b": 0.5}, "a")
        cake = _add_out(fs, 3, "cake", 1, "producto")
        moth = _add_out(fs, 4, "filt", 1, "venteo")
        fsv.solve_separators(fs)
        # Balance: in=1000 = cake + moth (NO ceros, NO inventar)
        self.assertAlmostEqual(cake.mass_flow + moth.mass_flow, 1000.0,
                                  delta=MASS_TOL)

    def test_dryer_humedad_imposible_passthrough(self):
        # final_moisture 50 % pero feed solo tiene 30 %.  Si el solver
        # intentara alcanzar 50 % añadiría agua → masa inventada.
        # Fix: pass-through al producto sin cambio.
        fs = fm.Flowsheet()
        b = _make_block("Dryer — drum",
                         dryer_active=True,
                         final_moisture=0.50,
                         moisture_component="water")
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"sucrose": 0.7, "water": 0.3}, "sucrose")
        dry = _add_out(fs, 3, "dry", 1, "producto")
        vap = _add_out(fs, 4, "vap", 1, "venteo")
        fsv.solve_dryers(fs)
        # NO debe inventar masa: in=1000 ≤ out (era 1400 antes del fix)
        total = dry.mass_flow + vap.mass_flow
        self.assertAlmostEqual(total, 1000.0, delta=MASS_TOL,
            msg=f"Dryer inventó masa: total={total} vs feed=1000")

    def test_crystallizer_sin_solute_passthrough(self):
        fs = fm.Flowsheet()
        b = _make_block("Crystallizer",
                         crystallizer_active=True,
                         solute_component="salt",     # no en feed
                         crystal_yield=0.80)
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"sucrose": 0.4, "water": 0.6}, "sucrose")
        xt = _add_out(fs, 3, "x", 1, "producto")
        mo = _add_out(fs, 4, "m", 1, "venteo")
        fsv.solve_crystallizers(fs)
        self.assertAlmostEqual(xt.mass_flow + mo.mass_flow, 1000.0,
                                  delta=MASS_TOL)

    def test_cyclone_sin_solidos_passthrough_a_gas(self):
        fs = fm.Flowsheet()
        b = _make_block("Cyclone — gas/solid",
                         cyclone_active=True,
                         collection_efficiency=1.0,
                         solid_components=["silica"])
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"nitrogen": 1.0}, "nitrogen")
        sol = _add_out(fs, 3, "sol", 1, "producto")
        gas = _add_out(fs, 4, "gas", 1, "venteo")
        fsv.solve_cyclones(fs)
        # Sin sólido en feed: todo el gas va al venteo, sol=0
        self.assertAlmostEqual(sol.mass_flow + gas.mass_flow, 1000.0,
                                  delta=MASS_TOL)
        self.assertAlmostEqual(gas.mass_flow, 1000.0, delta=MASS_TOL)


class TestSeparatorLocked(unittest.TestCase):
    """Outputs LOCKEADOS → el solver NO los toca (modo datos)."""

    def test_filter_lock_respected(self):
        fs = fm.Flowsheet()
        b = _make_block("Filter — belt",
                         separator_active=True,
                         solids_recovery=0.95,
                         cake_moisture=0.30,
                         solid_components=["sucrose"])
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0, {"sucrose": 0.5, "water": 0.5}, "sucrose")
        cake = _add_out(fs, 3, "S-cake", 1, "producto",
                         locked=True, mass=600,
                         composition={"sucrose": 0.9, "water": 0.1})
        filt = _add_out(fs, 4, "S-filt", 1, "venteo",
                         locked=True, mass=400,
                         composition={"sucrose": 0.05, "water": 0.95})

        fsv.solve_separators(fs)

        # Lock respetado: valores intactos
        self.assertEqual(cake.mass_flow, 600.0)
        self.assertEqual(cake.composition["sucrose"], 0.9)
        self.assertEqual(filt.mass_flow, 400.0)
        self.assertEqual(filt.composition["sucrose"], 0.05)


# ─────────────────────────────────────────────────────────────
# Dryer (dryer_active)
# ─────────────────────────────────────────────────────────────

class TestDryer(unittest.TestCase):
    def test_dryer_unlocked_computes_outputs(self):
        fs = fm.Flowsheet()
        b = _make_block("Dryer — drum",
                         dryer_active=True,
                         final_moisture=0.05,
                         moisture_component="water")
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0, {"sucrose": 0.6, "water": 0.4}, "sucrose")
        dry = _add_out(fs, 3, "S-dry", 1, "producto")
        vap = _add_out(fs, 4, "S-vap", 1, "venteo")

        fsv.solve_dryers(fs)
        self.assertAlmostEqual(dry.mass_flow + vap.mass_flow, 1000.0,
                                  delta=MASS_TOL)
        # final_moisture 5 % aplicada al producto
        self.assertAlmostEqual(dry.composition["water"], 0.05, delta=0.001)
        self.assertEqual(vap.composition, {"water": 1.0})


# ─────────────────────────────────────────────────────────────
# Crystallizer
# ─────────────────────────────────────────────────────────────

class TestCrystallizer(unittest.TestCase):
    def test_crystallizer_yield(self):
        fs = fm.Flowsheet()
        b = _make_block("Crystallizer",
                         crystallizer_active=True,
                         solute_component="sucrose",
                         crystal_yield=0.80)
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"sucrose": 0.40, "water": 0.60}, "sucrose")
        xtals = _add_out(fs, 3, "S-xtals", 1, "producto")
        moth  = _add_out(fs, 4, "S-mother", 1, "venteo")

        fsv.solve_crystallizers(fs)
        # 80 % de los 400 t sucrose → 320 t crystals
        self.assertAlmostEqual(xtals.mass_flow, 320.0, delta=1.0)
        # madre: 1000 - 320 = 680
        self.assertAlmostEqual(moth.mass_flow, 680.0, delta=1.0)


# ─────────────────────────────────────────────────────────────
# Evaporator
# ─────────────────────────────────────────────────────────────

class TestEvaporator(unittest.TestCase):
    def test_evaporator_concentration_factor(self):
        fs = fm.Flowsheet()
        b = _make_block("Evaporator — vertical",
                         evaporator_active=True,
                         concentration_factor=2.0,
                         volatile_component="water")
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"sucrose": 0.20, "water": 0.80}, "water")
        conc = _add_out(fs, 3, "S-conc", 1, "producto")
        vap  = _add_out(fs, 4, "S-vap", 1, "venteo")

        fsv.solve_evaporators(fs)
        # CF=2 → concentrado = 500, vapor = 500
        self.assertAlmostEqual(conc.mass_flow, 500.0, delta=1.0)
        self.assertAlmostEqual(vap.mass_flow,  500.0, delta=1.0)
        # vapor es agua pura
        self.assertEqual(vap.composition, {"water": 1.0})


# ─────────────────────────────────────────────────────────────
# Cyclone
# ─────────────────────────────────────────────────────────────

class TestCyclone(unittest.TestCase):
    def test_cyclone_collection_efficiency(self):
        fs = fm.Flowsheet()
        b = _make_block("Cyclone — gas/solid",
                         cyclone_active=True,
                         collection_efficiency=0.92,
                         solid_components=["silica"])
        fs.blocks[1] = b
        _add_feed(fs, 1, 1000.0,
                    {"silica": 0.10, "nitrogen": 0.90}, "nitrogen")
        sol = _add_out(fs, 3, "S-solids", 1, "producto")
        gas = _add_out(fs, 4, "S-gas", 1, "venteo")

        fsv.solve_cyclones(fs)
        # 92 % de los 100 t silica → 92 t collected
        self.assertAlmostEqual(sol.mass_flow, 92.0, delta=1.0)
        # gas: nitrógeno + finos no colectados = 908
        self.assertAlmostEqual(gas.mass_flow, 908.0, delta=1.0)


# ─────────────────────────────────────────────────────────────
# Sugar mill end-to-end
# ─────────────────────────────────────────────────────────────

class TestSugarMillEndToEnd(unittest.TestCase):
    """Verifica que tras el refactor de _example_sugar_mill, el
    solver mantiene balance cerrado con FL-101 y DR-101 usando
    sus modelos internos.  Sin esto, los outputs serían inválidos."""

    def test_sugar_mill_solves_clean(self):
        try:
            from validate_ui import headless_mocks
            headless_mocks()
        except Exception:
            pass
        import examples_library as el

        class _Fake:
            def __init__(self):
                self.fs = fm.Flowsheet()
                self.labor_workers = 0
            _add_example_block  = el.ExampleBuilder._add_example_block
            _add_example_stream = el.ExampleBuilder._add_example_stream
            _add_example_extra  = el.ExampleBuilder._add_example_extra
            _set_example_labor  = el.ExampleBuilder._set_example_labor
            _set_block_duty     = el.ExampleBuilder._set_block_duty

        fake = _Fake()
        el.ExampleBuilder._example_sugar_mill(fake)
        res = fsv.solve(fake.fs)
        self.assertEqual(len(res.mass_balance_errors), 0,
            f"mass errors: {res.mass_balance_errors}")
        self.assertEqual(len(res.energy_balance_errors), 0,
            f"eng errors: {res.energy_balance_errors}")

        # Verificar que FL-101 y DR-101 escribieron outputs calculados
        s_az_humedo = next(s for s in fake.fs.streams.values()
                              if s.name == "S-az-humedo")
        s_melaza    = next(s for s in fake.fs.streams.values()
                              if s.name == "S-melaza")
        s_azucar    = next(s for s in fake.fs.streams.values()
                              if s.name == "S-azucar")
        s_vap_dry   = next(s for s in fake.fs.streams.values()
                              if s.name == "S-vap-dry")
        s_masa      = next(s for s in fake.fs.streams.values()
                              if s.name == "S-masa")

        # Mass balance FL-101: cake + mother = masa cocida
        self.assertAlmostEqual(s_az_humedo.mass_flow + s_melaza.mass_flow,
                                  s_masa.mass_flow, delta=1.0)

        # Mass balance DR-101: dry + vapor = az_humedo
        self.assertAlmostEqual(s_azucar.mass_flow + s_vap_dry.mass_flow,
                                  s_az_humedo.mass_flow, delta=1.0)

        # Composiciones: torta a 3 % moisture, azúcar refino 0.5 %
        self.assertAlmostEqual(s_az_humedo.composition["water"], 0.03,
                                  delta=0.001)
        self.assertAlmostEqual(s_azucar.composition["water"], 0.005,
                                  delta=0.001)

        # Vapor de secado es agua pura
        self.assertEqual(s_vap_dry.composition, {"water": 1.0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
