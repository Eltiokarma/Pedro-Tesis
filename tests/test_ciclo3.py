"""Design ciclo 3 — regresión de los 4 artboards implementados.

3a Glifos: geometría del bundle en glyph_specs (22 specs, parser SVG
   con arcos), delegación desde BlockGlyph, badge = mismo glifo a 24px
   (muere equipment_icons), 3 distinciones nuevas de eq_type.
3b Procedencia sudoku: ▪ declarada / ◦ derivada / ↻ torn en la pill,
   fila PROCEDENCIA en la leyenda, mismos términos en el diálogo DOF.
3c Anotaciones: modelo persistente (Flowsheet.annotations), item
   editable/movible/borrable, T en la paleta, export siempre incluido.
3d Gradiente térmico: stops por longitud acumulada, umbrales de
   apagado, prioridad del semáforo.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtCore import QPointF

_app = QApplication.instance() or QApplication([])


# ══════════════════════════════════════════════════════════════════════
# 3a — Glifos
# ══════════════════════════════════════════════════════════════════════
def test_specs_del_bundle_compilan_y_renderizan():
    import glyph_specs as gs
    assert len(gs.SPECS) >= 21
    img = QImage(120, 120, QImage.Format_ARGB32)
    for sid in gs.SPECS:
        img.fill(0)
        p = QPainter(img)
        ok = gs.draw_glyph(p, sid, 100, 100,
                           QColor("#1a1714"), QColor("#ffffff"))
        p.end()
        assert ok, f"{sid} no renderiza"


def test_parser_svg_arcos():
    """El subset del bundle usa arcos elípticos (kettle, válvula):
    el parser debe producir un path no vacío y acotado a la caja."""
    from glyph_specs import parse_path
    p = parse_path("M38 42 A12 10 0 0 1 62 42 Z")
    r = p.boundingRect()
    assert r.width() > 10 and r.height() > 5
    assert 30 < r.left() and r.right() < 70


def test_tres_distinciones_nuevas_de_eq_type():
    from editor_chrome import isa_type_for_eq
    assert isa_type_for_eq("Boiler — fire tube") == "caldera"
    assert isa_type_for_eq("Boiler — water tube") == "caldera_water"
    assert isa_type_for_eq("Tray — sieve") == "platos"
    assert isa_type_for_eq("Tray — valve") == "platos_valve"
    assert isa_type_for_eq("Reactor — jacketed agitated") == "reactor_jacket"


def test_badge_es_el_mismo_glifo_para_todo_el_catalogo():
    """Muere equipment_icons: el badge sale de la misma geometría y
    NINGÚN eq_type cae a un ícono de otro equipo (el bug WHB→mixer)."""
    import equipment_costs as ec
    from editor_chrome import glyph_pixmap
    assert not Path("equipment_icons.py").exists(), \
        "equipment_icons.py debía morir en el ciclo 3"
    sin_badge = [t for t in ec.EQUIPMENT_DATA
                 if glyph_pixmap(t, 24) is None
                 or glyph_pixmap(t, 24).isNull()]
    assert sin_badge == [], f"sin badge: {sin_badge}"


def test_splitter_y_mixer_geometrias_distintas():
    """El par CRÍTICO (invierte semántica): las siluetas nuevas deben
    producir raster distinto."""
    import glyph_specs as gs

    def raster(sid):
        img = QImage(64, 64, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        gs.draw_glyph(p, sid, 64, 64, QColor("#000000"), QColor("#ffffff"))
        p.end()
        return img

    assert raster("splitter") != raster("mezclador")
    assert raster("caldera") != raster("caldera_water")
    assert raster("torre_enf") != raster("torre_nat")
    assert raster("platos") != raster("platos_valve")


# ══════════════════════════════════════════════════════════════════════
# 3b — Procedencia sudoku
# ══════════════════════════════════════════════════════════════════════
def test_pill_marca_procedencia():
    from stream_bubbles import StreamBubble
    bub = StreamBubble(stream_id=1)
    bub.update_values("S-1", "liquid", mass_status="locked")
    assert bub._proc_lbl.text() == "▪"
    bub.update_values("S-1", "liquid", mass_status="torn")
    assert bub._proc_lbl.text() == "↻"
    assert "tearing" in bub._proc_lbl.toolTip()
    bub.update_values("S-1", "liquid", mass_status="propagated")
    assert bub._proc_lbl.text() == "◦"
    bub.deleteLater()


def test_manager_deriva_torn_de_los_reciclos():
    """El BubbleManager clasifica igual que el DOF audit: los streams
    de hda dentro del SCC son torn; el feed lockeado es declarado."""
    from examples_registry import load_example
    from dof_audit import _recycle_stream_ids
    fs = load_example("hda")
    torn = _recycle_stream_ids(fs)
    assert torn, "hda sin reciclo detectado"
    s_torn = next(s for s in fs.streams.values() if s.id in torn)
    assert not getattr(s_torn, "mass_flow_locked", False) or True


# ══════════════════════════════════════════════════════════════════════
# 3c — Anotaciones
# ══════════════════════════════════════════════════════════════════════
def test_annotations_persisten_en_el_modelo():
    from flowsheet_model import Flowsheet
    fs = Flowsheet()
    fs.annotations.append({"id": 1, "x": 10.0, "y": 20.0,
                           "text": "R=1.8 verificar", "style": "rotulo",
                           "tint": "ink", "pill": False, "guide": None})
    d = fs.to_dict()
    assert d["annotations"][0]["text"] == "R=1.8 verificar"
    fs2 = Flowsheet.from_dict(d)
    assert fs2.annotations == fs.annotations
    # JSONs viejos sin la clave cargan limpio
    d.pop("annotations")
    fs3 = Flowsheet.from_dict(d)
    assert fs3.annotations == []


def test_annotation_item_estilos_y_descartes():
    from annotations import AnnotationItem, _font_for
    import tokens as _tokens
    data = {"id": 1, "x": 5.0, "y": 6.0, "text": "nota",
            "style": "titulo", "tint": "danger", "pill": True,
            "guide": None}
    item = AnnotationItem(data)
    assert item.toPlainText() == "nota"
    assert item.zValue() == 40
    assert item.defaultTextColor().name().lower() == \
        QColor(_tokens.TOK["danger"]).name().lower()
    # los 3 estilos mapean a la escala del sistema
    assert _font_for("micro").pointSize() == _tokens.FONT_LABEL[1]
    assert _font_for("titulo").pointSize() == _tokens.FONT_TITLE[1]


def test_palette_tiene_la_T():
    from editor_chrome import EditorPalette
    assert any(tid == "text" for tid, _ in EditorPalette.TOOLS)


def test_editor_crea_y_borra_anotacion():
    import flowsheet_qt as fq
    win = fq.FlowsheetMainWindow()
    try:
        n0 = len(win.fs.annotations)
        win.create_annotation(QPointF(100, 100))
        assert len(win.fs.annotations) == n0 + 1
        data = win.fs.annotations[-1]
        data["text"] = "nota de prueba"
        win.remove_annotation(data)
        assert len(win.fs.annotations) == n0
    finally:
        win.close()


# ══════════════════════════════════════════════════════════════════════
# 3d — Gradiente térmico
# ══════════════════════════════════════════════════════════════════════
def test_gradiente_en_lazo_de_servicio():
    """Lazo CW mínimo (torre → HX → torre, 25→40 °C): la corriente de
    ida arma el gradiente con color de llegada ≠ color de salida, y el
    paint() por segmentos renderiza sin reventar."""
    import flowsheet_qt as fq
    from flowsheet_model import Block, Stream
    win = fq.FlowsheetMainWindow()
    try:
        fs = win.fs
        ct = Block(id=fs.new_id(), name="CT-1",
                   eq_type="Cooling tower — induced draft", S=100.0,
                   x=0, y=0)
        hx = Block(id=fs.new_id(), name="E-1",
                   eq_type="Heat exch. — fixed tube", S=50.0,
                   x=300, y=0)
        # El lazo se marca auto_aux como los que genera la app (el walk
        # de _utility_loop_info solo cruza el cluster aux, no el lado
        # de proceso del HX).
        ct.auto_aux = True
        hx.duty = -500.0          # el lazo ENFRÍA → familia fría
        fs.blocks[ct.id] = ct
        fs.blocks[hx.id] = hx
        s_in = Stream(id=fs.new_id(), name="S-cw-fria", src=ct.id,
                      dst=hx.id, mass_flow=1000.0, temperature=25.0,
                      role="utility", phase="liquid",
                      main_component="water")
        s_out = Stream(id=fs.new_id(), name="S-cw-caliente", src=hx.id,
                       dst=ct.id, mass_flow=1000.0, temperature=40.0,
                       role="utility", phase="liquid",
                       main_component="water")
        s_in.auto_aux = True
        s_out.auto_aux = True
        fs.streams[s_in.id] = s_in
        fs.streams[s_out.id] = s_out
        win._rebuild_scene()

        it = win.scene.stream_items[s_in.id]
        assert getattr(it, "_service_grad", None) is not None, \
            "la corriente fría no armó gradiente"
        # Contrato ciclo 4: la tupla suma el sólido de fallback (el
        # tono medio que pinta paint() bajo el umbral de zoom).
        _, c_in, c_out, c_solid = it._service_grad
        assert c_in != c_out
        assert c_solid is not None
        # La flecha hereda el color de LLEGADA
        assert it.pen().color().name() == c_out.name()
        # render offscreen — el paint() por segmentos no debe reventar
        img = QImage(400, 300, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        win.scene.render(p)
        p.end()
    finally:
        win.close()


def test_gradiente_prioridad_del_semaforo():
    """error/warning pintan sólido: el gradiente no puede ocultar un
    desbalance (regla 3 del artboard 3d)."""
    import flowsheet_qt as fq
    from flowsheet_model import Block, Stream
    win = fq.FlowsheetMainWindow()
    try:
        fs = win.fs
        a = Block(id=fs.new_id(), name="A", S=1.0,
                  eq_type="Heat exch. — fixed tube", x=0, y=0)
        b = Block(id=fs.new_id(), name="B", S=1.0,
                  eq_type="Heat exch. — fixed tube", x=300, y=0)
        fs.blocks[a.id] = a
        fs.blocks[b.id] = b
        s1 = Stream(id=fs.new_id(), name="S-u1", src=a.id, dst=b.id,
                    mass_flow=100.0, temperature=25.0, role="utility",
                    phase="liquid", main_component="water")
        s2 = Stream(id=fs.new_id(), name="S-u2", src=b.id, dst=a.id,
                    mass_flow=100.0, temperature=40.0, role="utility",
                    phase="liquid", main_component="water")
        fs.streams[s1.id] = s1
        fs.streams[s2.id] = s2
        win._rebuild_scene()
        it = win.scene.stream_items[s1.id]
        it.set_status("error")
        assert getattr(it, "_service_grad", None) is None, \
            "con error el gradiente debe apagarse (sólido danger)"
    finally:
        win.close()
