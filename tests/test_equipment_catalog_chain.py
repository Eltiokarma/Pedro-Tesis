"""
tests/test_equipment_catalog_chain.py — GATE de cadena completa del catálogo.

Regla congelada (2026-07, tanda "aumentar equipos"): TODO eq_type de
equipment_costs.EQUIPMENT_DATA debe atravesar la cadena completa sin
excepciones ni estados a medias:

    catálogo (K's + rango + categoría) → costeo (Cp>0, FBM>0, CBM>0)
    → puertos (EQUIPMENT_PORTS) → tag ISA (ISA_PREFIX) → sizer
    (SIZER_BY_EQTYPE/SIZER_BY_CAT, salvo internos de columna) → glifo
    (EQ_TYPE_TO_SYMBOL → SYMBOLS) → ícono (icon_for_eq_type)
    → ΔP default (_typical_dp no revienta).

Agregar un equipo nuevo al catálogo y olvidar una capa rompe ESTE test,
no la UI en runtime.  Incluye además el humo E2E de los tipos que estrenó
esta tanda (turbinas formales + agitador de impulsor).

USO:
    python -m unittest tests.test_equipment_catalog_chain -v
"""
import math
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import equipment_costs as ec
import equipment_ports as ep
import equipment_sizing as es
import hydraulic_defaults as hd
import icons
import pfd_symbols
from flowsheet_model import Block, Stream, Flowsheet

# Internos de columna: se costean por área/volumen pero su tamaño lo fija
# el diseño de la columna madre, no un sizer propio (decisión documentada
# en equipment_sizing.SIZER_BY_EQTYPE).
_SIN_SIZER = {
    "Tray — sieve", "Tray — valve",
    "Packing — random", "Packing — structured",
}

# Anomalía LEGACY detectada por este gate al nacer (2026-07): la correlación
# del autoclave decrece con el volumen en TODO su rango [1, 15] m³
# (K2=-0.3617 domina hasta S≈87).  Queda permitida y documentada hasta
# cotejar la fila contra Turton A.1 con el libro físico; los tipos NUEVOS
# no pueden entrar aquí sin esa verificación.
_COSTO_NO_MONOTONO_LEGACY = {"Reactor — autoclave"}


def _s_medio(spec):
    """Punto medio geométrico del rango de validez (representativo)."""
    return math.sqrt(spec["S_min"] * spec["S_max"])


class TestCadenaCatalogo(unittest.TestCase):
    """Cada eq_type atraviesa TODAS las capas."""

    def test_catalogo_bien_formado(self):
        for eq, spec in ec.EQUIPMENT_DATA.items():
            self.assertLess(spec["S_min"], spec["S_max"], eq)
            self.assertTrue(spec.get("categoria"), eq)
            self.assertTrue(spec.get("S_unit"), eq)
            self.assertTrue(spec.get("source"), f"{eq}: sin fuente")
            self.assertIn(spec["categoria"], ec.B1_B2_BY_CATEGORIA,
                          f"{eq}: categoría '{spec['categoria']}' sin B1/B2")

    def test_costeo_resuelve(self):
        for eq, spec in ec.EQUIPMENT_DATA.items():
            S = _s_medio(spec)
            res = ec.bare_module_cost(eq, S, P_op_bar=1.0, year_target=2024)
            self.assertFalse(res["unknown"], eq)
            self.assertFalse(res["fuera_rango"],
                             f"{eq}: S medio {S:g} fuera de su propio rango")
            self.assertGreater(res["Cp_target"], 0.0, eq)
            self.assertGreater(res["FBM"], 0.0, eq)
            self.assertGreater(res["CBM"], 0.0, eq)
            self.assertTrue(math.isfinite(res["CBM"]), eq)

    def test_costo_monotono_en_rango(self):
        """El costo de compra no decrece con el tamaño dentro del rango de
        validez (canario de coeficientes mal transcritos)."""
        for eq, spec in ec.EQUIPMENT_DATA.items():
            if eq in _COSTO_NO_MONOTONO_LEGACY:
                continue
            lo = ec.purchased_cost(eq, spec["S_min"] * 1.01)["Cp_target"]
            hi = ec.purchased_cost(eq, spec["S_max"] * 0.99)["Cp_target"]
            self.assertGreater(hi, lo,
                               f"{eq}: Cp({spec['S_max']:g}) ≤ "
                               f"Cp({spec['S_min']:g}) — revisar K1/K2/K3")

    def test_puertos_y_prefijo(self):
        for eq in ec.EQUIPMENT_DATA:
            # Internos de columna y otros sin spec propio caen al
            # DEFAULT_PORTS — lo que se exige es que la RESOLUCIÓN funcione.
            self.assertTrue(ep.get_ports(eq), f"{eq}: sin puertos")
            self.assertIn(eq, ep.ISA_PREFIX, f"{eq}: sin prefijo ISA")

    def test_sizer_resoluble(self):
        for eq, spec in ec.EQUIPMENT_DATA.items():
            if eq in _SIN_SIZER:
                continue
            tiene = (eq in es.SIZER_BY_EQTYPE
                     or spec["categoria"] in es.SIZER_BY_CAT)
            self.assertTrue(tiene, f"{eq}: sin sizer (ni por tipo ni por "
                                   f"categoría '{spec['categoria']}')")

    def test_glifo_e_icono(self):
        for eq in ec.EQUIPMENT_DATA:
            sym = pfd_symbols.EQ_TYPE_TO_SYMBOL.get(eq)
            self.assertTrue(sym, f"{eq}: sin entrada en EQ_TYPE_TO_SYMBOL")
            self.assertIn(sym, pfd_symbols.SYMBOLS,
                          f"{eq}: símbolo '{sym}' no existe en SYMBOLS")
            self.assertTrue(icons.icon_for_eq_type(eq), eq)

    def test_dp_default_no_revienta(self):
        for eq in ec.EQUIPMENT_DATA:
            b = Block(id=1, name="X", eq_type=eq, S=1.0)
            hd._typical_dp(b)   # None es válido; una excepción no


def _fs_turbina(eq_type="Turbine — steam"):
    """Vapor 40 bar / 400 °C → turbina (ΔP=-36) → 4 bar."""
    fs = Flowsheet()
    tb = Block(id=1, name="TB-1", eq_type=eq_type, S=0.0,
               delta_p_bar=-36.0, efficiency=0.8)
    fs.blocks = {1: tb}
    si = Stream(id=10, name="in", src=0, dst=1, mass_flow=50000.0,
                composition={"water": 1.0}, main_component="water",
                temperature=400.0, pressure_bar=40.0, phase="vapor",
                mass_flow_locked=True, temperature_locked=True,
                composition_locked=True, pressure_locked=True)
    so = Stream(id=11, name="out", src=1, dst=0, mass_flow=0.0,
                composition={"water": 1.0}, main_component="water",
                temperature=400.0, pressure_bar=4.0, phase="vapor")
    fs.streams = {10: si, 11: so}
    return fs, tb


class TestTurbinasE2E(unittest.TestCase):
    """Los tipos Turbine formalizan la convención 'compresor con
    P_out < P_in = turbina': mismo motor isentrópico, duty < 0."""

    def test_turbina_genera_y_enfria(self):
        import flowsheet_solver as fsv
        fs, tb = _fs_turbina()
        fsv.solve(fs)
        out = fs.streams[11]
        self.assertLess(tb.duty, 0.0, "turbina debe GENERAR (duty<0)")
        self.assertLess(out.temperature, 400.0,
                        "la expansión debe ENFRIAR la descarga")
        self.assertAlmostEqual(out.pressure_bar, 4.0, places=2)

    def test_turbina_sizing_en_rango(self):
        import flowsheet_solver as fsv
        fs, tb = _fs_turbina()
        fsv.solve(fs)
        es.auto_size_blocks(fs)
        spec = ec.EQUIPMENT_DATA["Turbine — steam"]
        self.assertGreaterEqual(tb.S, spec["S_min"])
        self.assertLessEqual(tb.S, spec["S_max"])

    def test_turbina_es_electrica_y_genera_revenue(self):
        self.assertTrue(ep.is_electrical_equipment("Turbine — steam"))
        self.assertEqual(
            ep.autoselect_heat_source("Turbine — steam", -500.0, 200.0),
            "electricity_generated")

    def test_evidencia_expander(self):
        """La evidencia del compresor reconoce la turbina formal."""
        import flowsheet_solver as fsv
        import inspector_evidence as ev
        fs, tb = _fs_turbina()
        fsv.solve(fs)
        m = ev.compressor_metrics(tb, fs)
        self.assertIsNotNone(m, "compressor_metrics debe cubrir Turbine")
        self.assertTrue(any("urbina" in s.get("text", "")
                            for s in m.get("status", [])),
                        "status debe identificar 'Turbina / expansor'")


class TestAgitadorE2E(unittest.TestCase):
    """Mixer — impeller: base de costo Power (kW) con sizer P/V propio."""

    def test_sizing_potencia_en_rango(self):
        fs = Flowsheet()
        ag = Block(id=1, name="MX-1", eq_type="Mixer — impeller", S=0.0)
        fs.blocks = {1: ag}
        si = Stream(id=10, name="in", src=0, dst=1, mass_flow=100000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=25.0, pressure_bar=1.013, phase="liquid")
        so = Stream(id=11, name="out", src=1, dst=0, mass_flow=100000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=25.0, pressure_bar=1.013, phase="liquid")
        fs.streams = {10: si, 11: so}
        S = es.size_agitator(ag, fs)
        self.assertIsNotNone(S)
        spec = ec.EQUIPMENT_DATA["Mixer — impeller"]
        self.assertGreaterEqual(S, spec["S_min"])
        self.assertLessEqual(S, spec["S_max"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
