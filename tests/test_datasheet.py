"""
tests/test_datasheet.py — Ficha Técnica: agregador + modo selección.

Cobertura dura: datasheet_spec() debe producir una ficha válida para CADA
bloque de CADA ejemplo del catálogo (el fallback genérico garantiza los 60
tipos).  Y la verificación comercial debe transitar sus seis estados con
los veredictos del artboard 5f (§4.1 del inventario).
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import datasheet as ds
import equipment_costs as ec
from flowsheet_model import Block, Stream, Flowsheet

# Importar el PySide6 REAL en tiempo de colección: export_examples.
# _headless_mocks() usa sys.modules.setdefault(), así que si el módulo
# real ya está cargado los mocks NO lo pisan — sin esto, el test de
# cobertura (que corre primero y mockea Qt) rompería los smoke Qt.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    import PySide6.QtWidgets as _QtW_real          # noqa: F401
    _QT_REAL = True
except Exception:
    _QT_REAL = False

_SECCIONES = ("identidad", "condiciones", "corrientes", "diseno",
              "materiales", "auxiliares", "costos", "notas", "verificacion")


def _fs_rotary(S=12.0, equipo="", eq_type="Compressor — rotary"):
    fs = Flowsheet()
    b = Block(id=1, name="K-1", eq_type=eq_type, S=S,
              delta_p_bar=6.0, efficiency=0.75, equipo_comercial=equipo)
    fs.blocks = {1: b}
    si = Stream(id=10, name="in", src=0, dst=1, mass_flow=8000.0,
                composition={"nitrogen": 0.79, "oxygen": 0.21},
                main_component="nitrogen", temperature=25.0,
                pressure_bar=1.013, phase="gas")
    so = Stream(id=11, name="out", src=1, dst=0, mass_flow=8000.0,
                composition={"nitrogen": 0.79, "oxygen": 0.21},
                main_component="nitrogen", temperature=25.0,
                pressure_bar=7.0, phase="gas")
    fs.streams = {10: si, 11: so}
    return fs, b


def _tipo_sin_catalogo():
    """Un eq_type SIN catálogo comercial, resuelto en vivo.

    El fixture hardcodeado se pudre con cada cosecha: estos tests usaban
    'Reactor — CSTR (agitado)' hasta que la cosecha lo abrió (+6 modelos
    Pfaudler/De Dietrich) y pasaron a rojo sin que el motor cambiara.  Se
    prefiere un candidato legible y, si el catálogo también lo abre, se
    cae a cualquier otro tipo sin entradas."""
    for t in ("Reactor — PFR (tubular)", "Vessel — vertical",
              "Storage tank — cone roof"):
        if not ds.entradas_para(t):
            return t
    for t in sorted(ec.EQUIPMENT_DATA):
        if not ds.entradas_para(t):
            return t
    raise unittest.SkipTest("todo eq_type tiene catálogo comercial")


def _entrada_familia():
    """(eq_type, 'marca|modelo') de una entrada granularidad=familia.

    Mismo motivo que arriba: la entrada concreta cambia cuando la cosecha
    sustituye envolventes de familia por envolventes por tamaño (la deuda
    que el brief pide cerrar).  None si ya no queda ninguna — el estado
    'debil_familia' deja de ser testeable y el test se salta."""
    for t in sorted(ec.EQUIPMENT_DATA):
        for e in ds.entradas_para(t):
            if e.get("granularidad") == "familia":
                return t, ds.clave_de(e)
    return None


class TestFichaTodosLosEjemplos(unittest.TestCase):
    """El fallback genérico cubre TODO bloque de TODO ejemplo."""

    def test_spec_valida_para_cada_bloque(self):
        from export_examples import _headless_mocks
        _headless_mocks()
        import examples_registry as reg
        import flowsheet_solver as fsv
        for meta in reg.list_examples():
            fs = reg.load_example(meta["clave"])
            fsv.solve(fs)
            for b in fs.blocks.values():
                if getattr(b, "auto_aux", False):
                    continue
                spec = ds.datasheet_spec(b, fs)
                for k in _SECCIONES:
                    self.assertIn(k, spec,
                                  f"{meta['clave']}/{b.name}: falta '{k}'")
                self.assertEqual(spec["identidad"]["tag"], b.name)
                self.assertIn(spec["verificacion"]["estado"],
                              ("no_aplica", "sin_declarar", "desconocido",
                               "escalar", "envolvente_modelo",
                               "debil_familia"),
                              f"{meta['clave']}/{b.name}")


class TestCatalogoHelpers(unittest.TestCase):

    def test_entradas_para_rotary(self):
        entradas = ds.entradas_para("Compressor — rotary")
        self.assertGreaterEqual(len(entradas), 10)   # GA ×10 + CSD ×4

    def test_entrada_de_parsea_clave(self):
        fs, b = _fs_rotary(equipo="Atlas Copco|GA 90")
        e = ds.entrada_de(b)
        self.assertIsNotNone(e)
        self.assertEqual(e["modelo"], "GA 90")

    def test_entrada_de_exige_eq_type(self):
        """Un 'marca|modelo' de OTRO tipo no resuelve (la clave completa
        del catálogo es (marca, modelo, eq_type))."""
        fs, b = _fs_rotary(equipo="Bosch|UNIVERSAL UL-S 1250")
        self.assertIsNone(ds.entrada_de(b))


class TestVerificacion(unittest.TestCase):

    def test_no_aplica(self):
        fs = Flowsheet()
        b = Block(id=1, name="R-1", eq_type=_tipo_sin_catalogo(), S=2.0)
        fs.blocks = {1: b}; fs.streams = {}
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "no_aplica")
        self.assertIsNone(v["apto"])

    def test_sin_declarar(self):
        fs, b = _fs_rotary(equipo="")
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "sin_declarar")
        self.assertGreaterEqual(v["n_disponibles"], 10)

    def test_desconocido(self):
        fs, b = _fs_rotary(equipo="Acme|Inexistente 9000")
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "desconocido")

    def test_escalar_apto_con_utilizacion(self):
        """5f.3: GA 90 sobre un proceso de 12 kW → APTO, utilización 13%."""
        fs, b = _fs_rotary(S=12.0, equipo="Atlas Copco|GA 90")
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "escalar")
        self.assertTrue(v["apto"])
        self.assertAlmostEqual(v["utilizacion"], 12.0 / 90.0, places=3)
        self.assertIn("Sobredimensionado", v["mensaje"])

    def test_escalar_no_apto(self):
        fs, b = _fs_rotary(S=120.0, equipo="Atlas Copco|GA 90")
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "escalar")
        self.assertFalse(v["apto"])

    def test_envolvente_modelo(self):
        """5f.4: M10 FD — sin ratio, AND de desigualdades del bastidor."""
        fs = Flowsheet()
        b = Block(id=1, name="E-1", eq_type="Heat exch. — flat plate",
                  S=0.0, equipo_comercial="Alfa Laval|M10 — bastidor FD (ASME)")
        fs.blocks = {1: b}
        si = Stream(id=10, name="in", src=0, dst=1, mass_flow=50000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=120.0, pressure_bar=8.0, phase="liquid")
        so = Stream(id=11, name="out", src=1, dst=0, mass_flow=50000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=60.0, pressure_bar=7.5, phase="liquid")
        fs.streams = {10: si, 11: so}
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "envolvente_modelo")
        self.assertIsNone(v["utilizacion"])
        self.assertTrue(v["apto"])           # 8 ≤ 26.8 bar · 120 ≤ 250 °C
        params = {c["param"] for c in v["checks"]}
        self.assertIn("P_max_bar", params)
        self.assertIn("T_max_C", params)
        self.assertFalse(any(c["familia"] for c in v["checks"]))

    def test_envolvente_modelo_violada(self):
        """El bastidor FM (10 bar) NO aguanta un proceso a 14 bar."""
        fs = Flowsheet()
        b = Block(id=1, name="E-1", eq_type="Heat exch. — flat plate",
                  S=0.0, equipo_comercial="Alfa Laval|M10 — bastidor FM (PED)")
        fs.blocks = {1: b}
        si = Stream(id=10, name="in", src=0, dst=1, mass_flow=50000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=90.0, pressure_bar=14.0, phase="liquid")
        so = Stream(id=11, name="out", src=1, dst=0, mass_flow=50000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=60.0, pressure_bar=13.5, phase="liquid")
        fs.streams = {10: si, 11: so}
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "envolvente_modelo")
        self.assertFalse(v["apto"])

    def test_debil_familia_nunca_afirma(self):
        """5f.5: envolvente de FAMILIA — apto SIEMPRE None (nunca tilde
        verde), checks marcados FAMILIA."""
        caso = _entrada_familia()
        if caso is None:                                  # pragma: no cover
            self.skipTest("el catálogo ya no tiene entradas de familia")
        eq_type, equipo = caso
        fs = Flowsheet()
        b = Block(id=1, name="P-1", eq_type=eq_type,
                  S=0.0, equipo_comercial=equipo)
        fs.blocks = {1: b}
        si = Stream(id=10, name="in", src=0, dst=1, mass_flow=30000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=40.0, pressure_bar=2.0, phase="liquid")
        so = Stream(id=11, name="out", src=1, dst=0, mass_flow=30000.0,
                    composition={"water": 1.0}, main_component="water",
                    temperature=40.0, pressure_bar=6.0, phase="liquid")
        fs.streams = {10: si, 11: so}
        v = ds.verificacion(b, fs)
        self.assertEqual(v["estado"], "debil_familia")
        self.assertIsNone(v["apto"])
        self.assertTrue(v["checks"])
        self.assertTrue(all(c["familia"] for c in v["checks"]))

    def test_restriccion_block_S_intacto(self):
        """Declarar un equipo comercial NO toca Block.S (restricción dura)."""
        fs, b = _fs_rotary(S=12.0, equipo="Atlas Copco|GA 90")
        ds.datasheet_spec(b, fs)
        ds.verificacion(b, fs)
        self.assertEqual(b.S, 12.0)


class TestSeccionFichaQt(unittest.TestCase):
    """Smoke Qt offscreen: la sección Ficha del inspector se construye
    para los tres escenarios del selector (5f.1 / 5f.2 / con declarado)."""

    @classmethod
    def setUpClass(cls):
        if not _QT_REAL:                              # pragma: no cover
            raise unittest.SkipTest("PySide6 real no disponible")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _panel(self, fs, b):
        import block_inspector as bi
        p = bi.BlockInspectorPanel()
        p.fs = fs
        p.block = b
        return p

    def test_sin_catalogo_afirmacion_tranquila(self):
        """5f.1 + cosecha 2026-07: sin catálogo NO va selector, y en su
        lugar va el callout con la RAZÓN de ingeniería (título + qué fija
        el tamaño), que reemplazó al viejo texto 'Ingeniería a pedido'."""
        from PySide6.QtWidgets import QComboBox, QLabel
        eq_type = _tipo_sin_catalogo()
        fs = Flowsheet()
        b = Block(id=1, name="R-1", eq_type=eq_type, S=2.0)
        fs.blocks = {1: b}; fs.streams = {}
        sect = self._panel(fs, b)._section_ficha(b, b.eq_type)
        self.assertFalse(sect.findChildren(QComboBox),
                         "5f.1: sin catálogo NO va selector")
        textos = " ".join(l.text() for l in sect.findChildren(QLabel))
        motivo = ds.motivo_a_pedido(eq_type)
        self.assertIn(motivo["titulo"], textos)
        razones = motivo.get("que_fija_el_tamano") or []
        self.assertTrue(razones, f"{eq_type}: motivo sin razones")
        for razon in razones:
            self.assertIn(razon, textos)

    def test_ficha_completa_para_todo_tipo(self):
        """La ficha renderiza contenido (condiciones, diseño, materiales,
        costos, pendiente de detalle) para TODO tipo — con o sin catálogo
        comercial.  Pedido 2026-07: 'ver esto en todos los equipos de
        todos los ejemplos'."""
        from PySide6.QtWidgets import QLabel
        fs = Flowsheet()
        b = Block(id=1, name="R-1", eq_type=_tipo_sin_catalogo(),
                  S=2.0, duty=150.0, T_op_K=473.15, P_op_bar=5.0)
        fs.blocks = {1: b}
        fs.streams = {
            10: Stream(id=10, name="in", src=0, dst=1, mass_flow=9000.0,
                       composition={"water": 1.0}, main_component="water",
                       temperature=180.0, pressure_bar=5.0, phase="liquid"),
            11: Stream(id=11, name="out", src=1, dst=0, mass_flow=9000.0,
                       composition={"water": 1.0}, main_component="water",
                       temperature=200.0, pressure_bar=5.0, phase="liquid"),
        }
        sect = self._panel(fs, b)._section_ficha(b, b.eq_type)
        textos = " ".join(l.text() for l in sect.findChildren(QLabel))
        for esperado in ("CONDICIONES DE OPERACIÓN", "DISEÑO",
                        "MATERIALES", "COSTOS (BARE MODULE)", "CBM",
                        "Ingeniería de detalle pendiente"):
            self.assertIn(esperado, textos,
                          f"la ficha de un tipo sin catálogo debe mostrar "
                          f"'{esperado}'")

    def test_selector_poblado(self):
        from PySide6.QtWidgets import QComboBox
        fs, b = _fs_rotary(equipo="")
        sect = self._panel(fs, b)._section_ficha(b, b.eq_type)
        combos = sect.findChildren(QComboBox)
        self.assertTrue(combos, "5f.2: con catálogo va selector")
        cb = combos[0]
        self.assertGreaterEqual(cb.count(), 15)   # placeholder + 14 rotary
        self.assertEqual(cb.itemData(0), "")

    def test_declarado_muestra_veredicto(self):
        from PySide6.QtWidgets import QLabel
        fs, b = _fs_rotary(S=12.0, equipo="Atlas Copco|GA 90")
        sect = self._panel(fs, b)._section_ficha(b, b.eq_type)
        textos = " ".join(l.text() for l in sect.findChildren(QLabel))
        self.assertIn("APTO", textos)
        self.assertIn("fuente del", textos)   # trazabilidad no negociable


class TestDialogoEquipoComercialQt(unittest.TestCase):
    """Auditoría 2026-07: el selector también vive en el diálogo de
    crear/editar bloque (BlockEditDialog) — el usuario esperaba la opción
    al crear el equipo, no solo en la sección Ficha del inspector."""

    @classmethod
    def setUpClass(cls):
        if not _QT_REAL:                              # pragma: no cover
            raise unittest.SkipTest("PySide6 real no disponible")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_dialogo_con_catalogo_ofrece_selector(self):
        import flowsheet_qt as fq
        b = Block(id=1, name="K-1", eq_type="Compressor — rotary", S=12.0)
        dlg = fq.BlockEditDialog(None, b)
        self.assertFalse(dlg.gb_comercial.isHidden(),
                         "tipo con catálogo debe mostrar el grupo")
        self.assertEqual(dlg.comercial_combo.count(), 15)  # placeholder+14
        idx = dlg.comercial_combo.findData("Atlas Copco|GA 90")
        self.assertGreater(idx, 0)
        dlg.comercial_combo.setCurrentIndex(idx)
        dlg.apply_to_model()
        self.assertEqual(b.equipo_comercial, "Atlas Copco|GA 90")

    def test_dialogo_sin_catalogo_oculta_grupo(self):
        import flowsheet_qt as fq
        b = Block(id=1, name="R-1", eq_type=_tipo_sin_catalogo(), S=2.0)
        dlg = fq.BlockEditDialog(None, b)
        self.assertTrue(dlg.gb_comercial.isHidden(),
                        "ingeniería a pedido: el grupo no aparece")
        dlg.apply_to_model()
        self.assertEqual(b.equipo_comercial, "")

    def test_dialogo_preserva_declarado(self):
        import flowsheet_qt as fq
        b = Block(id=1, name="TB-1", eq_type="Turbine — steam", S=700.0,
                  equipo_comercial="Siemens Energy|Dresser-Rand RLA/RLVA")
        dlg = fq.BlockEditDialog(None, b)
        self.assertEqual(dlg.comercial_combo.currentData(),
                         "Siemens Energy|Dresser-Rand RLA/RLVA")
        dlg.apply_to_model()
        self.assertEqual(b.equipo_comercial,
                         "Siemens Energy|Dresser-Rand RLA/RLVA")


if __name__ == "__main__":
    unittest.main(verbosity=2)
