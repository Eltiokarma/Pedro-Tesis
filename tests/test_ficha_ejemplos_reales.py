"""
tests/test_ficha_ejemplos_reales.py — equipos REALES sobre ejemplos reales.

Congela la batería pedida en la auditoría 2026-07: para cada tipo con
catálogo comercial, declarar un modelo real sobre su instancia en un
ejemplo del catálogo y verificar que:

  1. FÍSICA INTACTA — declarar un equipo comercial es solo-lectura: el
     golden completo (18 claves, incluidos hashes de T/P/caudal/
     composición y max imbalances) debe ser IDÉNTICO pre/post declarar.
  2. SUDOKU INTACTO — ningún lock ni procedencia se mueve: S, S_locked,
     duty, duty_locked, duty_origin por bloque; pressure/mass/temperature/
     composition_locked y pressure_lock_origin por corriente.
  3. ROUNDTRIP — to_dict/from_dict preserva equipo_comercial y re-resolver
     reproduce el mismo golden.
  4. VEREDICTO — el estado y los checks son los esperados, y la
     temperatura de envolvente usa el PEOR CASO (T máxima de proceso),
     no el promedio (hallazgo de la auditoría: la turbina promediaba
     291 °C cuando el vapor vivo entra a 400).
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import datasheet as ds
from export_examples import golden, _headless_mocks

_P_OP_LECHE_BAR = 180.0   # P de descarga de leche_gloria P-101 (homogeneizador)


def _caso_familia():
    """El caso débil-de-familia, resuelto EN VIVO contra el catálogo.

    Hardcodear el modelo pudre el test: 'NETZSCH|NEMO L.Cap' fue retirada
    por la cosecha (se sustituyó por NEMO SY/BY, modelos ordenables del
    folleto oficial) y los tres tests que la nombraban se cayeron sin que
    el motor cambiara.  Se pide lo que el caso NECESITA — una envolvente
    de familia de bomba PD cuyo P publicado NO alcanza los ~180 bar del
    homogeneizador — y se devuelve None si la cosecha ya cerró la deuda de
    familia (entonces no hay nada que verificar).
    """
    for e in ds.entradas_para("Pump — positive displacement"):
        if (e.get("granularidad") == "familia"
                and 0 < float((e.get("params") or {}).get("P_max_bar", 0))
                < _P_OP_LECHE_BAR):
            return ("leche_gloria", "P-101", ds.clave_de(e),
                    "debil_familia", None)
    return None


# (clave, tag, 'marca|modelo', estado esperado, apto esperado)
CASOS = [c for c in (
    ("boiler_ft",     "B-101",  "Bosch|UNIVERSAL UL-S 28000",
     "escalar", True),
    ("cw_natural",    "E-303",  "Alfa Laval|M10 — bastidor FG (PED)",
     "envolvente_modelo", True),
    _caso_familia(),
    ("solvent_rec",   "K-101",  "Atlas Copco|GA 90",
     "escalar", False),   # AND de envolvente: el FAD del GA 90 no alcanza
    ("steam_turbine", "TB-101", "Siemens Energy|Dresser-Rand RLA/RLVA",
     "escalar", True),
) if c is not None]


def _sudoku(fs):
    b = {blk.name: (round(float(blk.S or 0), 6), bool(blk.S_locked),
                    round(float(blk.duty or 0), 6), bool(blk.duty_locked),
                    getattr(blk, "duty_origin", ""))
         for blk in fs.blocks.values()}
    s = {st.name: (bool(st.pressure_locked), bool(st.mass_flow_locked),
                   bool(st.temperature_locked), bool(st.composition_locked),
                   getattr(st, "pressure_lock_origin", ""))
         for st in fs.streams.values()}
    return b, s


class TestEquiposRealesSobreEjemplos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _headless_mocks()
        import examples_registry as reg
        import flowsheet_solver as fsv
        cls.reg, cls.fsv = reg, fsv

    def _correr(self, clave, tag, equipo):
        fs0 = self.reg.load_example(clave)
        g0 = golden(fs0, self.fsv.solve(fs0))
        s0 = _sudoku(fs0)

        fs1 = self.reg.load_example(clave)
        blk = next(b for b in fs1.blocks.values() if b.name == tag)
        blk.equipo_comercial = equipo
        g1 = golden(fs1, self.fsv.solve(fs1))
        s1 = _sudoku(fs1)
        return fs0, g0, s0, fs1, g1, s1

    def test_fisica_y_sudoku_intactos(self):
        for clave, tag, equipo, _, _apto in CASOS:
            _, g0, s0, _, g1, s1 = self._correr(clave, tag, equipo)
            self.assertEqual(g0, g1,
                             f"{clave}/{tag}: declarar {equipo} MOVIÓ la "
                             f"física")
            self.assertEqual(s0, s1,
                             f"{clave}/{tag}: declarar {equipo} MOVIÓ el "
                             f"sudoku (locks/procedencia)")

    def test_roundtrip_persiste_y_reproduce(self):
        for clave, tag, equipo, _, _apto in CASOS:
            _, g0, _s0, fs1, _g1, s1 = self._correr(clave, tag, equipo)
            fs2 = type(fs1).from_dict(fs1.to_dict())
            blk2 = next(b for b in fs2.blocks.values() if b.name == tag)
            self.assertEqual(blk2.equipo_comercial, equipo,
                             f"{clave}/{tag}: equipo_comercial se perdió "
                             f"en el roundtrip")
            g2 = golden(fs2, self.fsv.solve(fs2))
            self.assertEqual(g0, g2,
                             f"{clave}/{tag}: el roundtrip no reproduce "
                             f"la física")
            self.assertEqual(s1, _sudoku(fs2),
                             f"{clave}/{tag}: el roundtrip movió el sudoku")

    def test_veredictos(self):
        for clave, tag, equipo, estado, apto in CASOS:
            fs = self.reg.load_example(clave)
            blk = next(b for b in fs.blocks.values() if b.name == tag)
            blk.equipo_comercial = equipo
            self.fsv.solve(fs)
            v = ds.verificacion(blk, fs)
            self.assertEqual(v["estado"], estado, f"{clave}/{tag}")
            self.assertEqual(v["apto"], apto, f"{clave}/{tag}: {v}")

    def test_envolvente_T_usa_peor_caso(self):
        """Hallazgo de la auditoría: la T de envolvente es la MÁXIMA de
        proceso (vapor vivo 400 °C), no el promedio (291 °C)."""
        fs = self.reg.load_example("steam_turbine")
        blk = next(b for b in fs.blocks.values() if b.name == "TB-101")
        blk.equipo_comercial = "Siemens Energy|Dresser-Rand RLA/RLVA"
        self.fsv.solve(fs)
        v = ds.verificacion(blk, fs)
        t_check = next(c for c in v["checks"] if c["param"] == "T_max_C")
        self.assertGreaterEqual(t_check["requerido"], 399.0,
                                "la envolvente debe compararse contra la "
                                "T de entrada (peor caso), no el promedio")
        self.assertTrue(t_check["ok"])       # 400 ≤ 440 sigue siendo apto

    def test_familia_check_violado_sigue_sin_afirmar(self):
        """leche_gloria P-101 opera a ~180 bar y la familia PD publica
        mucho menos: el check FALLA pero el estado débil mantiene
        apto=None (la decisión de si un fallo a nivel familia es
        concluyente queda documentada en el reporte de auditoría — hoy NO
        afirma)."""
        caso = _caso_familia()
        if caso is None:                                  # pragma: no cover
            self.skipTest("el catálogo ya no tiene entradas de familia")
        fs = self.reg.load_example("leche_gloria")
        blk = next(b for b in fs.blocks.values() if b.name == "P-101")
        blk.equipo_comercial = caso[2]
        self.fsv.solve(fs)
        v = ds.verificacion(blk, fs)
        self.assertEqual(v["estado"], "debil_familia")
        self.assertIsNone(v["apto"])
        p_check = next(c for c in v["checks"] if c["param"] == "P_max_bar")
        self.assertFalse(p_check["ok"])
        self.assertTrue(p_check["familia"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
