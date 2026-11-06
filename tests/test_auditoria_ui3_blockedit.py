"""tests/test_auditoria_ui3_blockedit.py — auditoría UI 3 §3.1.

`BlockEditDialog` («Opciones avanzadas…») era superficie duplicada del
inspector de bloques.  Se retiró, pero NO en silencio: antes se migraron
al inspector los campos que solo vivían en el diálogo:

  · Columna — tipo de interno (`packing_type`), eficiencia de plato
    (`tray_efficiency`) y HETP (`HETP_m`) → sección Sizing.
  · Predictor de reacciones (Fase 8) — `allow_reactions` y
    `active_reactions` → sección nueva «Predictor rxn» (todo bloque).

Estos tests fijan tres cosas:
  1. el diálogo y su entrada ya no existen;
  2. TODO campo que el diálogo editaba tiene casa en el inspector (tabla
     campo-por-campo, para que una próxima limpieza no pierda nada);
  3. cada campo migrado se pinta y se guarda (ida y vuelta).
"""
import inspect
import os
import sys

import pytest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _tipo(pred_name):
    import block_inspector as bi
    import equipment_costs as ec
    pred = getattr(bi, pred_name)
    for k in ec.EQUIPMENT_DATA:
        if pred(k):
            return k
    pytest.skip(f"ningún eq_type cumple {pred_name}")


def _panel(b):
    from block_inspector import BlockInspectorPanel
    from flowsheet_model import Flowsheet
    fs = Flowsheet()
    fs.blocks = {b.id: b}
    fs.streams = {}
    p = BlockInspectorPanel()
    p.load_block(b, fs, lambda: None)
    return p


def _bloque(pred_name, **kw):
    from flowsheet_model import Block
    return Block(id=1, name="X-1", eq_type=_tipo(pred_name), S=1.0, **kw)


# ─────────────────── 1. El diálogo y su entrada se fueron ───────────────────

def test_block_edit_dialog_retirado():
    import flowsheet_qt as fq
    assert not hasattr(fq, "BlockEditDialog")
    # la reacción custom sigue: la usa la sección Reactividad del inspector
    assert hasattr(fq, "CustomReactionDialog")


def test_entrada_opciones_avanzadas_retirada(app):
    import block_inspector as bi
    import flowsheet_qt as fq
    P = bi.BlockInspectorPanel
    assert not hasattr(P, "_build_advanced_link")
    assert not hasattr(P, "_do_open_advanced")
    assert "open_advanced" not in inspect.signature(P.load_block).parameters
    assert "open_advanced" not in inspect.signature(
        bi.BlockInspectorDock.show_for).parameters
    src = inspect.getsource(fq.FlowsheetMainWindow.edit_block)
    assert "_open_advanced" not in src


def test_ningun_boton_opciones_avanzadas_en_el_panel(app):
    from PySide6.QtWidgets import QPushButton
    import block_inspector as bi
    for pred in ("_is_reactor", "_is_tower", "_is_hx"):
        b = _bloque(pred)
        p = _panel(b)
        for sec in bi._sections_for(b.eq_type):
            if sec in ("economia", "diagnostico"):
                continue
            p._build_section_content(sec)
            textos = [w.text() for w in p.findChildren(QPushButton)]
            assert not any("avanzad" in t.lower() for t in textos), (sec, textos)


# ──────────── 2. Tabla campo-por-campo: diálogo → inspector ────────────
# (predicado de tipo, sección del inspector, dónde vive, clave).  Es la
# lista COMPLETA de lo que BlockEditDialog.apply_to_model escribía.

_CAMPOS = [
    ("_is_reactor", "identidad", "fields", "S"),
    ("_is_reactor", "identidad", "fields", "n"),
    ("_is_reactor", "termo", "fields", "duty"),           # + duty_locked
    ("_is_reactor", "termo", "fields", "heat_of_reaction"),
    ("_is_reactor", "termo", "fields", "T_op_K"),
    ("_is_reactor", "termo", "fields", "P_op_bar"),
    ("_is_pump_compressor", "termo", "fields", "delta_p_bar"),
    ("_is_pump_compressor", "sizing", "fields", "efficiency"),
    ("_is_reactor", "utility", "extras", "heat_source"),
    ("_is_hx", "sizing", "fields", "U_override"),
    ("_is_hx", "sizing", "fields", "dtlm_override"),
    ("_is_tower", "sizing", "fields", "tray_spacing_m"),
    ("_is_tower", "sizing", "fields", "K_souders_brown"),
    ("_is_tower", "sizing", "fields", "column_head_height_m"),
    ("_is_tower", "sizing", "extras", "packing_type"),      # migrado
    ("_is_tower", "sizing", "fields", "tray_efficiency"),   # migrado
    ("_is_tower", "sizing", "fields", "HETP_m"),            # migrado
    ("_is_reactor", "reactividad", "extras", "reactor_mode"),
    ("_is_reactor", "reactividad", "fields", "reactor_volume_L"),
    ("_is_reactor", "reactividad", "fields", "batch_time_s"),
    ("_is_reactor", "reactividad", "rows", "reactions"),
    ("_is_reactor", "reactividad", "custom", "custom_reactions"),
    ("_is_tower", "columna", "extras", "column_active"),
    ("_is_tower", "columna", "extras", "column_LK"),
    ("_is_tower", "columna", "extras", "column_HK"),
    ("_is_tower", "columna", "fields", "column_x_D_LK"),
    ("_is_tower", "columna", "fields", "column_x_B_LK"),
    ("_is_tower", "columna", "fields", "column_R_factor"),
    ("_is_tower", "columna", "extras", "column_method"),
    ("_is_tower", "columna", "fields", "column_N_stages"),
    ("_is_flash_vessel", "flash", "extras", "flash_active"),
    ("_is_flash_vessel", "flash", "fields", "flash_T_K"),
    ("_is_flash_vessel", "flash", "fields", "flash_P_bar"),
    ("_is_dryer", "especial", "extras", "dryer_active"),
    ("_is_dryer", "especial", "fields", "final_moisture"),
    ("_is_dryer", "especial", "extras", "moisture_component"),
    ("_is_crystallizer", "especial", "extras", "crystallizer_active"),
    ("_is_crystallizer", "especial", "extras", "solute_component"),
    ("_is_crystallizer", "especial", "fields", "crystal_yield"),
    ("_is_evaporator", "especial", "extras", "evaporator_active"),
    ("_is_evaporator", "especial", "fields", "concentration_factor"),
    ("_is_evaporator", "especial", "extras", "volatile_component"),
    # separador/ciclón legacy → modelo unificado mech_sep (η + fase)
    ("_is_mech_separator", "especial", "extras", "mech_sep_active"),
    ("_is_mech_separator", "especial", "fields", "mech_sep_efficiency"),
    ("_is_mech_separator", "especial", "extras", "solid_components"),
    ("_is_cyclone", "especial", "extras", "mech_sep_active"),
    ("_is_cyclone", "especial", "fields", "mech_sep_efficiency"),
    ("_is_reactor", "predictor", "extras", "allow_reactions"),  # migrado
]


@pytest.mark.parametrize("pred,sec,donde,clave", _CAMPOS,
                         ids=[f"{c[3]}@{c[1]}" for c in _CAMPOS])
def test_cada_campo_del_dialogo_tiene_casa_en_el_inspector(
        app, pred, sec, donde, clave):
    import block_inspector as bi
    b = _bloque(pred)
    assert sec in bi._sections_for(b.eq_type)
    p = _panel(b)
    p._build_section_content(sec)
    if donde == "fields":
        assert clave in p._fields
    elif donde == "extras":
        assert clave in p._extras
    elif donde == "rows":
        assert p._reaction_rows, "catálogo de reacciones vacío"
    elif donde == "custom":
        assert hasattr(p, "_custom_rxns_data")


def test_tag_se_edita_en_el_header(app):
    b = _bloque("_is_reactor")
    p = _panel(b)
    p._header._tag.setText("R-201")
    p._apply_to_block()
    assert b.name == "R-201"


# ─────────────── 3. Campos migrados: pintar y guardar ───────────────

def test_columna_internos_ida_y_vuelta(app):
    b = _bloque("_is_tower", packing_type="structured",
                tray_efficiency=0.65, HETP_m=0.3)
    p = _panel(b)
    p._build_section_content("sizing")
    pk = p._extras["packing_type"]
    assert pk.currentData() == "structured"
    assert float(p._fields["tray_efficiency"].value()) == pytest.approx(0.65)
    assert float(p._fields["HETP_m"].value()) == pytest.approx(0.3)
    # editar sin tocar no mueve nada
    p._apply_to_block()
    assert (b.packing_type, b.tray_efficiency, b.HETP_m) == \
        ("structured", pytest.approx(0.65), pytest.approx(0.3))
    # editar
    pk.setCurrentIndex(pk.findData(""))
    p._fields["tray_efficiency"].setValue("0.5")
    p._fields["HETP_m"].setValue("")
    p._apply_to_block()
    assert b.packing_type == ""
    assert b.tray_efficiency == pytest.approx(0.5)
    assert not b.HETP_m          # vacío → default canónico del sizing


def test_columna_internos_vacios_usan_default(app):
    b = _bloque("_is_tower")
    p = _panel(b)
    p._build_section_content("sizing")
    assert p._extras["packing_type"].currentData() == ""
    assert p._fields["tray_efficiency"].value() == ""
    assert p._fields["HETP_m"].value() == ""


def test_columna_empaque_cambia_el_sizing(app):
    """El campo migrado no es decorativo: lo que el inspector guarda lo
    consume `equipment_sizing.size_tower` (H = N·HETP con empaque)."""
    import equipment_sizing as es
    from flowsheet_model import Flowsheet, Stream
    b = _bloque("_is_tower", column_N_stages=20)
    fs = Flowsheet()
    fs.blocks = {1: b}
    fs.streams = {10: Stream(id=10, name="v", src=0, dst=1,
                             mass_flow=50000.0, composition={"water": 1.0},
                             main_component="water", temperature=100.0,
                             pressure_bar=1.0, phase="vapor")}
    p = _panel(b)
    p.fs = fs
    p._build_section_content("sizing")
    V_platos = es.size_tower(b, fs)
    pk = p._extras["packing_type"]
    pk.setCurrentIndex(pk.findData("structured"))
    p._fields["HETP_m"].setValue("0.3")
    p._apply_to_block()
    V_emp = es.size_tower(b, fs)
    assert b.packing_type == "structured" and b.HETP_m == pytest.approx(0.3)
    # empaque estructurado (HETP 0.3 m) es más bajo que platos a 0.6 m
    assert V_emp < V_platos
    # y el HETP guardado entra tal cual: subirlo agranda la columna
    p._build_section_content("sizing")
    p._fields["HETP_m"].setValue("0.6")
    p._apply_to_block()
    assert es.size_tower(b, fs) > V_emp


def test_predictor_aplica_a_todo_bloque():
    import block_inspector as bi
    import equipment_costs as ec
    for k in list(ec.EQUIPMENT_DATA)[:40]:
        assert "predictor" in bi._sections_for(k), k


_FA = {
    "n_curated": 1, "n_predicted": 2, "n_warnings": 0,
    "curated_ids": ["rx_cur"], "curated_names": ["Curada A"],
    "predicted_summary": [
        {"id": "rx_p1", "display_label": "Pred 1",
         "confidence_mechanism": "media"},
        {"id": "rx_p2", "display_label": "Pred 2"},
    ],
}


def test_predictor_toggle_ida_y_vuelta(app):
    b = _bloque("_is_hx", allow_reactions=True)
    p = _panel(b)
    p._build_section_content("predictor")
    cb = p._extras["allow_reactions"]
    assert cb.isChecked()
    cb.setChecked(False)
    p._apply_to_block()
    assert b.allow_reactions is False
    p._build_section_content("predictor")
    p._extras["allow_reactions"].setChecked(True)
    p._apply_to_block()
    assert b.allow_reactions is True


def test_predictor_active_reactions(app):
    b = _bloque("_is_reactor", active_reactions=["rx_p1", "rx_fuera"])
    b.feed_analysis_cache = dict(_FA)
    p = _panel(b)
    p._build_section_content("predictor")
    filas = dict(p._predictor_rows)
    assert set(filas) == {"rx_cur", "rx_p1", "rx_p2"}
    assert filas["rx_p1"].isChecked() and not filas["rx_cur"].isChecked()
    filas["rx_p1"].setChecked(False)
    filas["rx_cur"].setChecked(True)
    p._apply_to_block()
    # rx_fuera no está en el análisis actual: se conserva, no se pierde
    assert b.active_reactions == ["rx_fuera", "rx_cur"]


def test_predictor_sin_analisis_no_toca_active(app):
    from PySide6.QtWidgets import QLabel
    b = _bloque("_is_reactor", active_reactions=["rx_x"])
    p = _panel(b)
    sect = p._section_predictor(b, b.eq_type)
    assert not p._predictor_rows
    assert any("Solve" in l.text() for l in sect.findChildren(QLabel))
    p._apply_to_block()
    assert b.active_reactions == ["rx_x"]
