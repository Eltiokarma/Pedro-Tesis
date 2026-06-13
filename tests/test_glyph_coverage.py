"""GATE UI — cobertura de glyphs ISA del catálogo de equipos.

Protege el contrato entre equipment_costs.EQUIPMENT_DATA y las siluetas
del editor (editor_chrome): cada eq_type del catálogo debe tener una
silueta nativa mapeada en EQ_TYPE_TO_ISA, dibujable (_draw_ +
BLOCK_DIMS) y alcanzable desde la paleta (PALETTE_GROUPS).  Al agregar
equipos futuros (steam trap, strainer, deaerator) este gate obliga a
registrarlos explícitamente — un eq_type fuera del dict cae al
fallback honesto (SVG de pfd_symbols o rect neutro, nunca tanque).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsScene
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QRectF

import equipment_costs as ec
import editor_chrome as ech

_app = QApplication.instance() or QApplication([])


def _render_glyph(eq_type, w=90, h=90):
    """Pinta un IsaGlyphItem offscreen y devuelve la QImage."""
    scene = QGraphicsScene()
    scene.addItem(ech.IsaGlyphItem(eq_type, w, h))
    img = QImage(w + 10, h + 10, QImage.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, w + 10, h + 10),
                 QRectF(-5, -5, w + 10, h + 10))
    p.end()
    return img


def _blank(w=100, h=100):
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    return img


# ── cobertura del dict explícito ───────────────────────────────────────
def test_catalogo_completo_en_eq_type_to_isa():
    faltantes = set(ec.EQUIPMENT_DATA) - set(ech.EQ_TYPE_TO_ISA)
    assert not faltantes, (
        f"eq_types del catálogo sin entrada en EQ_TYPE_TO_ISA: "
        f"{sorted(faltantes)} — registrar su silueta (o agregar un "
        f"glyph nuevo) en editor_chrome.py")


def test_glyphs_mapeados_son_dibujables():
    for et, isa in ech.EQ_TYPE_TO_ISA.items():
        assert isa in ech.BLOCK_DIMS, f"{et} -> {isa}: sin BLOCK_DIMS"
        assert getattr(ech.BlockGlyph, f"_draw_{isa}", None) is not None, \
            f"{et} -> {isa}: sin BlockGlyph._draw_{isa}"


def test_todo_eq_type_pertenece_a_un_palette_group():
    agrupadas = set()
    for siluetas in ech.PALETTE_GROUPS.values():
        agrupadas.update(siluetas)
    huerfanos = [et for et in ec.EQUIPMENT_DATA
                 if ech.isa_type_for_eq(et) not in agrupadas]
    assert not huerfanos, (
        f"eq_types inalcanzables desde la paleta: {huerfanos} — "
        f"agregar su silueta a un PALETTE_GROUPS")


# ── render offscreen de los 56 ─────────────────────────────────────────
def test_render_catalogo_sin_excepciones_y_no_vacio():
    blank = _blank()
    for et in sorted(ec.EQUIPMENT_DATA):
        img = _render_glyph(et)
        assert img != blank, f"{et}: render vacío"


# ── fallback honesto para eq_types desconocidos ────────────────────────
def test_eq_type_desconocido_no_es_tanque():
    inventado = "Steam trap — inventado (no existe)"
    assert ech.isa_type_for_eq(inventado) is None
    img = _render_glyph(inventado)
    tanque = _render_glyph("Storage tank — cone roof")
    assert img != _blank(), "eq_type desconocido: render vacío"
    assert img != tanque, (
        "eq_type desconocido se dibuja como tanque — debe usar el "
        "fallback honesto (SVG pfd_symbols o rect neutro)")
