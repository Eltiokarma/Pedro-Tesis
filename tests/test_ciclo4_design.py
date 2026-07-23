"""Regresión del bundle de Design ciclo 4 (tablas de libro + deuda
tabular) — `docs/design_ciclo4/`, respuesta a PROMPT_DESIGN_CICLO4.

Cubre lo implementado:
  4a  BookTable (componente) + specs stoich/flash/WH (Qt-free)
  4b  MetricCard flex-column + ClassificationScale + identidades
      (N_s Perry, C_v Crane, vapor del WHB)
  4c  pasada formal streams_table (escala de celda + sudoku de masa)
  4d  procedencia por componente · revisiones △N · anclaje de notas ·
      gradiente térmico de proceso (eje global)
  4e  escala compacta on-canvas oficializada + degradación por zoom
  bugs 2 y 3 del bundle (DeltaBar 3 celdas · sub que fluye)
"""
import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from flowsheet_model import Flowsheet, Block, Stream
import inspector_evidence as ev
import tokens


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def tema_claro():
    yield
    tokens.apply_preferences(theme="light")


# ══════════════════════════════════════════════════════════════════════
# 4a — specs de tabla de libro (Qt-free)
# ══════════════════════════════════════════════════════════════════════

def _fogler_fs(X=0.5):
    sys.path.insert(0, str(ROOT / "tests"))
    from test_libros_fogler import _fogler_so2_fs
    return _fogler_so2_fs(X_declarada=X)


def test_stoich_book_spec_decisiones_del_bundle():
    """(A) limitante = pill accent + ribbon · (I) inerte = pill neutral
    + fila muted · «Cambio» negativo = dir 'down' (consumo, NO rojo
    semántico) · procedencia de X = sudoku ▪ declarada."""
    fs, r = _fogler_fs()
    spec = ev.stoich_book_spec(r, fs)
    assert spec is not None
    filas = {row["cells"][0]["t"]: row for row in spec["rows"]}
    lim = filas["SO2"]
    assert lim["ribbon"] == "accent"
    assert lim["cells"][0]["badge"] == {"text": "A", "kind": "accent"}
    inerte = filas["N2"]
    assert inerte["muted"] and \
        inerte["cells"][0]["badge"] == {"text": "I", "kind": "neutral"}
    # consumo: tinta neutra + ↓, nunca el rojo del solver
    assert lim["cells"][4]["dir"] == "down"
    assert filas["SO3"]["cells"][4]["dir"] == "up"
    # procedencia sudoku de X
    assert spec["provenance"]["glyph"] == "▪"
    assert spec["provenance"]["label"] == "declarada"
    assert spec["provenance"]["kind"] == "spec"
    # chips δ/ε/y_A0 y pie de fuente
    assert {c["label"].split(" ")[0] for c in spec["chips"]} \
        >= {"δ", "ε", "y_A0"}
    assert "Fogler" in spec["source"]


def test_flash_book_spec_eje_frio_calido_y_sigma():
    """K>1 = 'up' (cálido, sube al vapor) · K<1 = 'down' (frío) ·
    fila Σ como footer visual · chip V/F cool."""
    sys.path.insert(0, str(ROOT / "tests"))
    from test_libros_flash_s2 import _flash_ternario
    import flowsheet_solver as fsolv
    fs, v = _flash_ternario()
    fsolv.solve(fs)
    spec = ev.flash_book_spec(v)
    assert spec is not None
    body = [r for r in spec["rows"] if not r.get("sigma")]
    sigma = [r for r in spec["rows"] if r.get("sigma")]
    assert len(sigma) == 1
    for row in body:
        k_cell = row["cells"][4]
        assert k_cell["K"] in ("up", "down")
        k_val = float(k_cell["t"])
        assert (k_cell["K"] == "up") == (k_val >= 1.0)
    # volátil primero (orden por K desc)
    ks = [float(r["cells"][4]["t"]) for r in body]
    assert ks == sorted(ks, reverse=True)
    assert any(c["kind"] == "cool" and c["label"] == "V/F"
               for c in spec["chips"])


def test_wh_stage_book_spec_estreno():
    """La tabla de etapas WH: COND/FEED/REB marcados, 6 columnas,
    L/V en kmol/h desde el _wh_result (misma fuente que la figura)."""
    import distillation_wanghenke as wh
    comps = ["benzene", "toluene"]
    r = wh.wang_henke(comps, [0.5, 0.5], F=10.0 / 3600.0, T_feed_K=380.0,
                      P_bar=1.013, N=8, feed_stage=4, D_over_F=0.5,
                      R=1.8, max_iter=80)
    assert r["converged"]
    r["feed_stage"] = 4
    r["_comps"] = comps
    b = types.SimpleNamespace(_wh_result=r, column_LK="benzene",
                              column_HK="toluene", column_active=True)
    spec = ev.wh_stage_book_spec(b, None)
    assert spec is not None
    assert len(spec["columns"]) == 6
    rows = spec["rows"]
    assert rows[0]["cells"][0]["badge"]["text"] == "COND"
    assert rows[0]["ribbon"] == "cool"
    assert rows[3]["cells"][0]["badge"]["text"] == "FEED"
    assert rows[3]["ribbon"] == "accent"
    assert rows[-1]["cells"][0]["badge"]["text"] == "REB"
    assert rows[-1]["ribbon"] == "warm"
    # condensador total: V_1 = 0 → "—" honesto
    assert rows[0]["cells"][5]["t"] == "—"
    # L en kmol/h del orden del feed (10 kmol/h)
    L2 = float(rows[1]["cells"][4]["t"])
    assert 1.0 < L2 < 100.0
    assert "Wang-Henke" in spec["source"] or "Seader" in spec["source"]


def test_wh_book_spec_nunca_mccabe():
    """Sin _wh_result convergido NO hay tabla WH (jamás etiquetamos
    McCabe como Wang-Henke)."""
    b = types.SimpleNamespace(_wh_result=None, column_LK="a",
                              column_HK="b", column_active=True)
    assert ev.wh_stage_book_spec(b, None) is None
    b2 = types.SimpleNamespace(_wh_result={"converged": False},
                               column_LK="a", column_HK="b",
                               column_active=True)
    assert ev.wh_stage_book_spec(b2, None) is None


def test_book_table_widget_par_claro_oscuro(qapp, tema_claro):
    """El widget BookTable construye y pinta en ambos temas (todo por
    tokens — el par dark llega gratis)."""
    from PySide6.QtGui import QImage
    from book_table import BookTable
    fs, r = _fogler_fs()
    spec = ev.stoich_book_spec(r, fs)
    for theme in ("light", "dark"):
        tokens.apply_preferences(theme=theme)
        bt = BookTable(spec)
        bt.resize(520, max(200, bt.sizeHint().height()))
        assert bt.grid._natural > 100     # columnas medidas, no <pre>
        img = QImage(bt.size(), QImage.Format_ARGB32)
        img.fill(0)
        bt.render(img)


# ══════════════════════════════════════════════════════════════════════
# 4b — MetricCard flex-column + escala + identidades
# ══════════════════════════════════════════════════════════════════════

def test_metric_card_sub_fluye_bug3(qapp):
    """Bug 3 del bundle: el sub es fila propia que fluye — una tarjeta
    con sub largo CRECE en vez de recortar («Perry fig. 10-32»)."""
    from inspector_widgets import MetricCard
    plain = MetricCard(label="Q", value="655.08", unit="m³/h")
    rich = MetricCard(label="N_s (US)", value="8003", unit="@ 3550 rpm",
                      state="accent",
                      sub="Rodete Francis / flujo mixto — Perry 8ª "
                          "fig. 10-32 (regla completa en el sub)")
    assert rich.sizeHint().height() > plain.sizeHint().height()
    assert plain.minimumHeight() == 58


def test_metric_card_escala_de_clasificacion(qapp):
    """La escala 4b: 3 bandas + marcador; presente solo si se pide."""
    from inspector_widgets import MetricCard, ClassificationScale
    scale = {"marker": 8003, "min": 0, "max": 12000, "bands": [
        {"label": "radial", "to": 4000, "kind": "cool"},
        {"label": "mixto", "to": 9000, "kind": "accent"},
        {"label": "axial", "to": 12000, "kind": "warm"}]}
    con = MetricCard(label="N_s", value="8003", scale=scale)
    sin = MetricCard(label="N_s", value="8003")
    assert con.findChild(ClassificationScale) is not None
    assert sin.findChild(ClassificationScale) is None


def test_pump_metrics_registros_separados():
    """4b: alerta (banda danger CON el margen) e identidad (N_s accent
    span 2 con escala) viven en registros distintos — no compiten."""
    import examples_registry as reg
    import flowsheet_solver as fsolv
    fs = reg.load_example("cw_natural")
    fsolv.solve(fs)
    bomba = next(b for b in fs.blocks.values()
                 if "reciprocating" in (b.eq_type or "").lower()
                 or "pump" in (b.eq_type or "").lower())
    m = ev.pump_metrics(bomba, fs)
    assert m is not None
    ns = next((x for x in m["metrics"] if x["key"] == "Ns"), None)
    assert ns is not None
    assert ns["state"] == "accent" and ns["span"] == 2
    assert ns["scale"]["bands"][1]["label"] == "mixto"
    assert "Perry" in ns["sub"]
    # si hay riesgo, la pill lleva el margen adentro (banda semántica)
    for s in m["status"]:
        if "cavitación" in s["text"]:
            assert "margen" in s["text"] and s["kind"] == "danger"


def test_valve_metrics_cv_crane():
    """4b: C_v de Crane como MetricCard spec a lo ancho con la ecuación
    citada (servicio líquido)."""
    fs = Flowsheet()
    v = Block(id=fs.new_id(), name="V-1", eq_type="Valve — gate", S=1.0)
    fs.blocks[v.id] = v
    feed = Stream(id=fs.new_id(), name="S-in", src=0, dst=v.id,
                  mass_flow=50000, mass_flow_locked=True, temperature=25,
                  pressure_bar=5.0, pressure_locked=True, phase="liquid",
                  main_component="water", role="feed")
    out = Stream(id=fs.new_id(), name="S-out", src=v.id, dst=0,
                 mass_flow=50000, temperature=25, pressure_bar=2.0,
                 pressure_locked=True, phase="liquid", role="product")
    fs.streams[feed.id] = feed
    fs.streams[out.id] = out
    m = ev.valve_metrics(v, fs)
    assert m is not None
    cv = next((x for x in m["metrics"] if x["key"] == "Cv"), None)
    assert cv is not None
    assert cv["state"] == "spec" and cv["span"] == 3
    assert "Crane TP-410" in cv["sub"]


def test_hx_metrics_vapor_whb_sinnott():
    """4b: el caudal de vapor del WHB (S, la variable de costeo
    Sinnott) entra como tarjeta sinnott span 2."""
    b = types.SimpleNamespace(
        eq_type="Heat exch. — WHB field erected", S=65959.0, duty=0.0,
        _hx_diagnostics={"T_h_in": 850.0, "T_h_out": 330.0,
                         "T_c_in": 250.0, "T_c_out": 250.0,
                         "dTlm": 258.1, "approach": 80.0, "dT_min": 10.0,
                         "U_used": 120.0, "F": 1.0, "warnings": []})
    m = ev.hx_metrics(b)
    assert m is not None
    steam = next((x for x in m["metrics"] if x["key"] == "steam"), None)
    assert steam is not None
    assert steam["state"] == "sinnott" and steam["span"] == 2
    assert steam["unit"] == "kg/h" and "Sinnott" in steam["sub"]


def test_deltabar_valor_celda_propia_bug2(qapp):
    """Bug 2: el valor mide su propio ancho — pinta sin recorte a
    cualquier ancho de panel (el track colapsa, el valor no)."""
    from PySide6.QtGui import QImage
    from inspector_widgets import DeltaBar
    assert DeltaBar.LABEL_MIN == 38            # spec 4b
    for w in (160, 340, 800):
        db = DeltaBar(label="IN", frac=1.0, value="5 600 000.0",
                      kind="in")
        db.resize(w, 24)
        img = QImage(db.size(), QImage.Format_ARGB32)
        img.fill(0)
        db.render(img)


# ══════════════════════════════════════════════════════════════════════
# 4c — pasada formal streams_table
# ══════════════════════════════════════════════════════════════════════

def test_stream_row_sudoku_de_masa(qapp):
    """La celda de flujo lleva la marca ▪/◦/↻ con el vocabulario del
    ciclo 3 (misma marca que burbuja / leyenda / DOF)."""
    from PySide6.QtWidgets import QLabel
    from streams_table import _StreamRow
    fs = Flowsheet()
    s = Stream(id=fs.new_id(), name="S-1", src=0, dst=0,
               mass_flow=1000.0, mass_flow_locked=False, role="internal")
    fs.streams[s.id] = s
    for status, glyph in (("locked", "▪"), ("derived", "◦"),
                          ("torn", "↻")):
        row = _StreamRow(s, fs, "tm/año", 1000.0, mass_status=status)
        textos = [l.text() for l in row.findChildren(QLabel)]
        assert glyph in textos, f"{status} sin glifo {glyph}"


def test_stream_row_sin_8pt_suelto():
    """4c: muere el 8pt suelto de la celda T·P — los tamaños del rich
    text salen de FONT_VALUE/FONT_LABEL."""
    src = (ROOT / "streams_table.py").read_text(encoding="utf-8")
    assert "font-size:8pt" not in src.replace(" ", "")
    assert "FONT_VALUE[1]" in src and "FONT_LABEL[1]" in src


# ══════════════════════════════════════════════════════════════════════
# 4d — deuda del ciclo 3
# ══════════════════════════════════════════════════════════════════════

def test_comp_provenance_por_componente():
    """Procedencia POR componente: cae al lock de la corriente y
    respeta el dict fino _comp_provenance si el solver lo publica."""
    from stream_inspector import StreamInspectorPanel
    s = types.SimpleNamespace(composition_locked=True,
                              _comp_provenance={})
    si = types.SimpleNamespace(stream=s)
    g, tok, _tip = StreamInspectorPanel._comp_provenance(si, "water")
    assert (g, tok) == ("▪", "spec")
    s2 = types.SimpleNamespace(composition_locked=False,
                               _comp_provenance={"ch4": "declared"})
    si2 = types.SimpleNamespace(stream=s2)
    assert StreamInspectorPanel._comp_provenance(si2, "h2o")[0] == "◦"
    assert StreamInspectorPanel._comp_provenance(si2, "ch4")[0] == "▪"


def test_revisiones_round_trip_y_marco(qapp):
    """△N: Flowsheet.revisions persiste y el Marco PFD dibuja el
    cuadro con el REV del título en la última letra."""
    fs = Flowsheet()
    fs.revisions = [
        {"rev": "A", "desc": "Emisión", "date": "05-07", "by": "PC"},
        {"rev": "B", "desc": "+ WHB E-201", "date": "18-07", "by": "PC"},
    ]
    fs2 = Flowsheet.from_dict(fs.to_dict())
    assert fs2.revisions == fs.revisions
    # JSON viejo sin la clave → lista vacía, carga limpia
    d = fs.to_dict()
    del d["revisions"]
    assert Flowsheet.from_dict(d).revisions == []

    from flowsheet_qt import _PaperFrame
    pf = _PaperFrame(revisions=fs.revisions)
    assert pf._rev == "B"
    pf_sin = _PaperFrame()
    assert pf_sin._revisions == []


def test_anotacion_guide_anchor_round_trip():
    """El ancla (block_id + offset relativo) persiste con la nota."""
    fs = Flowsheet()
    fs.annotations.append({
        "id": 1, "x": 10.0, "y": 20.0, "text": "nota", "style": "rotulo",
        "tint": "ink", "pill": False, "guide": [50.0, 60.0],
        "guide_anchor": {"kind": "block", "id": 3,
                         "offset": [5.0, -3.0]},
    })
    fs2 = Flowsheet.from_dict(fs.to_dict())
    assert fs2.annotations[0]["guide_anchor"]["id"] == 3


def test_gradiente_proceso_eje_global(qapp):
    """4d: eje GLOBAL por proyecto (T_min/T_max de las corrientes de
    proceso) con medio neutro ink_ghost; solo tinta si el destino
    cambia la T (>1 °C)."""
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
        s1 = Stream(id=fs.new_id(), name="S-frio", src=a.id, dst=b.id,
                    mass_flow=100.0, temperature=25.0, role="internal")
        s2 = Stream(id=fs.new_id(), name="S-caliente", src=b.id, dst=0,
                    mass_flow=100.0, temperature=400.0, role="product")
        fs.streams[s1.id] = s1
        fs.streams[s2.id] = s2
        win._rebuild_scene()
        it = win.scene.stream_items[s1.id]
        assert it._process_axis() == (25.0, 400.0)
        grad = getattr(it, "_service_grad", None)
        assert grad is not None, "la corriente de proceso no tintó"
        # la de salida no tiene siguiente → sin gradiente
        it2 = win.scene.stream_items[s2.id]
        assert getattr(it2, "_service_grad", None) is None
        # extremos del eje: frío = cold_deep, caliente = hot_deep
        c_frio = it._process_color_at(25.0, 25.0, 400.0)
        c_cal = it._process_color_at(400.0, 25.0, 400.0)
        assert c_frio.name() == tokens.TOK["service_cold_deep"].lower()
        assert c_cal.name() == tokens.TOK["service_hot_deep"].lower()
        # medio del eje = neutro (separa proceso de servicio)
        c_mid = it._process_color_at(212.5, 25.0, 400.0)
        assert c_mid.name() == tokens.TOK["ink_ghost"].lower()
    finally:
        win.close()


def test_gradiente_proceso_umbral_ruido(qapp):
    """ΔT ≤ 1 °C no tinta: el lenguaje de roles del ciclo 2 no se pisa
    por ruido térmico."""
    import flowsheet_qt as fq
    from flowsheet_model import Block, Stream
    win = fq.FlowsheetMainWindow()
    try:
        fs = win.fs
        a = Block(id=fs.new_id(), name="A", S=1.0,
                  eq_type="Pump — centrifugal", x=0, y=0)
        fs.blocks[a.id] = a
        s1 = Stream(id=fs.new_id(), name="S-1", src=0, dst=a.id,
                    mass_flow=100.0, temperature=25.0, role="feed")
        s2 = Stream(id=fs.new_id(), name="S-2", src=a.id, dst=0,
                    mass_flow=100.0, temperature=25.4, role="product")
        # tercero para que el eje global exista
        s3 = Stream(id=fs.new_id(), name="S-3", src=0, dst=0,
                    mass_flow=100.0, temperature=300.0, role="internal")
        for s in (s1, s2, s3):
            fs.streams[s.id] = s
        win._rebuild_scene()
        it = win.scene.stream_items[s1.id]
        assert it._process_gradient_colors() is None
    finally:
        win.close()


# ══════════════════════════════════════════════════════════════════════
# 4e — escala compacta oficializada + degradación
# ══════════════════════════════════════════════════════════════════════

def test_escala_compacta_oficial_en_tokens():
    assert tokens.COMPACT_VALUE_PX == 9
    assert tokens.COMPACT_LABEL_PX == 8
    assert tokens.COMPACT_MIN_PX == 7
    assert tokens.BUBBLE_COLLAPSE_ZOOM == 0.5


def test_burbuja_degradacion_por_zoom(qapp):
    """A zoom < 0.5 la burbuja colapsa (solo número + dot de fase) y se
    restituye al volver — el estado del user no se toca."""
    from PySide6.QtWidgets import QWidget
    from stream_bubbles import StreamBubble
    host = QWidget()
    b = StreamBubble(1, host)
    b.update_values(name="S-7", phase="vapor", T_K=1100.0, P_bar=25.0,
                    mdot_kg_s=0.138, mass_status="torn")
    assert b._name_lbl.isVisibleTo(host)
    b.set_zoom_degraded(True)
    assert not b._name_lbl.isVisibleTo(host)
    assert not b._close_btn.isVisibleTo(host)
    b.set_zoom_degraded(False)
    assert b._name_lbl.isVisibleTo(host)

    from hx_bubbles import HXBubble
    hb = HXBubble(2, host)
    hb.update_values("E-201", {"dTlm": 258.1, "F": 1.0, "U_eff": 120,
                               "approach": 80, "data_source": None})
    hb.set_zoom_degraded(True)
    assert not hb._body.isVisibleTo(host)
    hb.set_zoom_degraded(False)
    assert hb._body.isVisibleTo(host)
