"""Ciclo 4 — regresión del bloque B (tokenización) y C.3 (procedencia).

B1 solver_report: sin paleta light-only propia; severidades leen TOK en
   caliente (en dark el reporte ya no queda claro).
B2 inspector_evidence: 0 hex hardcodeados; figuras matplotlib respiran
   el tema (fondos/ticks/leyendas desde TOK).
B4 §G: el chip del solver recibe iteraciones y tiempo reales (el bug
   era leer `iter_count`/`elapsed_s`, atributos que SolverResult no
   tiene); payback con spec_ink (peso visual en dark); _tok de
   inspector_widgets sin fallback hex.
C3 reaction_from_dict persiste origin/estimation_method — una reacción
   aceptada desde "Sugerir productos" ya no es indistinguible de una
   escrita a mano.
"""
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

import tokens


# (?<!&) descarta entidades HTML tipo &#916; — falsos positivos que ya
# anotó la auditoría 2 en hx_edu.
_HEX_RE = re.compile(r"(?<!&)#[0-9a-fA-F]{3,8}\b")


@pytest.fixture
def tema_restaurado():
    """Devuelve el tema a light al salir (TOK muta in-place)."""
    prefs = tokens.current_prefs()
    yield
    tokens.apply_preferences(theme=prefs["theme"],
                             density=prefs["density"],
                             accent=prefs["accent"])


# ══════════════════════════════════════════════════════════════════════
# B1 — solver_report
# ══════════════════════════════════════════════════════════════════════
def test_solver_report_comparte_tok_canonico():
    """Muere el fallback light-only: el módulo consume el MISMO dict
    vivo de tokens.py (no una copia congelada)."""
    import solver_report as sr
    assert sr.TOK is tokens.TOK


def test_solver_report_sin_hex_propios():
    src = (ROOT / "solver_report.py").read_text(encoding="utf-8")
    assert _HEX_RE.findall(src) == [], \
        "solver_report.py volvió a duplicar hex propios"
    assert "white" not in src, "color literal 'white' (no theme-aware)"


def test_severidades_respiran_tema(tema_restaurado):
    """§G.5 auditoría 2: SEV congelaba la paleta light al importar —
    en dark el reporte quedaba claro."""
    import solver_report as sr
    tokens.apply_preferences(theme="light")
    light_ink = sr._sev("error")["ink"]
    tokens.apply_preferences(theme="dark")
    dark_ink = sr._sev("error")["ink"]
    assert light_ink == tokens.THEME_LIGHT["danger"]
    assert dark_ink == tokens.THEME_DARK["danger"]
    assert light_ink != dark_ink


# ══════════════════════════════════════════════════════════════════════
# B2 — inspector_evidence
# ══════════════════════════════════════════════════════════════════════
def test_inspector_evidence_sin_hex():
    """~45 hex de las curvas matplotlib → 0 (todo por _tok())."""
    src = (ROOT / "inspector_evidence.py").read_text(encoding="utf-8")
    assert _HEX_RE.findall(src) == [], \
        "inspector_evidence.py volvió a hardcodear hex"


def test_figuras_evidencia_respiran_tema(tema_restaurado):
    """_style_fig pinta fondo/ejes con TOK del tema activo."""
    mpl = pytest.importorskip("matplotlib")
    mpl.use("Agg")
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure
    import inspector_evidence as ev

    for theme in ("light", "dark"):
        tokens.apply_preferences(theme=theme)
        fig = Figure()
        ax = fig.add_subplot(111)
        ev._style_fig(fig, ax)
        esperado = tokens.TOK["bg_elev"].lower()
        assert to_hex(fig.patch.get_facecolor()) == esperado, theme
        assert to_hex(ax.get_facecolor()) == esperado, theme


def test_leyenda_evidencia_legible_en_dark(tema_restaurado):
    mpl = pytest.importorskip("matplotlib")
    mpl.use("Agg")
    from matplotlib.colors import to_hex
    from matplotlib.figure import Figure
    import inspector_evidence as ev

    tokens.apply_preferences(theme="dark")
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([0, 1], [0, 1], label="serie")
    leg = ev._legend(ax, loc="best")
    ink = tokens.TOK["ink"].lower()
    assert all(to_hex(t.get_color()) == ink for t in leg.get_texts())


# ══════════════════════════════════════════════════════════════════════
# B4 — menores §G
# ══════════════════════════════════════════════════════════════════════
def test_chip_recibe_iteraciones_reales():
    """§G.1: action_solve leía `result.iter_count` / `result.elapsed_s`
    — atributos inexistentes en SolverResult → el chip siempre 0/0."""
    from flowsheet_solver import SolverResult
    assert hasattr(SolverResult(), "iterations")
    assert not hasattr(SolverResult(), "iter_count")
    src = (ROOT / "flowsheet_qt.py").read_text(encoding="utf-8")
    assert 'getattr(result, "iter_count"' not in src, \
        "flowsheet_qt volvió a leer el atributo fantasma iter_count"
    assert 'getattr(result, "elapsed_s"' not in src, \
        "flowsheet_qt volvió a leer el atributo fantasma elapsed_s"
    assert 'getattr(result, "iterations"' in src


def test_payback_usa_spec_ink(tema_restaurado):
    """§G.2: la anotación de payback quedaba tenue en dark con `spec`;
    ahora usa el par spec_ink (más claro/pesado en dark)."""
    mpl = pytest.importorskip("matplotlib")
    mpl.use("Agg")
    from matplotlib.colors import to_hex
    import econ_figures as ef

    tokens.apply_preferences(theme="dark")
    cashflow = [{"year": 1, "cf": -30.0, "phase": "constr"},
                {"year": 2, "cf": 12.0, "phase": "op"},
                {"year": 3, "cf": 12.0, "phase": "op"},
                {"year": 4, "cf": 12.0, "phase": "op"}]
    fig, meta = ef.cashflow_figure(cashflow, payback_year=1.5)
    assert fig is not None
    ax = fig.axes[0]
    lbls = [t for t in ax.texts if "payback" in t.get_text()]
    assert lbls, "sin anotación de payback"
    assert to_hex(lbls[0].get_color()) == tokens.TOK["spec_ink"].lower()


def test_inspector_widgets_fallback_sin_hex(tema_restaurado):
    """§G.3: el helper _tok caía a '#000000' fijo — ahora cae a
    TOK['ink'] del tema activo."""
    src = (ROOT / "inspector_widgets.py").read_text(encoding="utf-8")
    assert "#000000" not in src
    import inspector_widgets as iw
    tokens.apply_preferences(theme="dark")
    assert iw._tok("token_que_no_existe") == tokens.TOK["ink"]


def test_hx_icons_sin_default_negro():
    src = (ROOT / "hx_icons.py").read_text(encoding="utf-8")
    assert '"#000"' not in src, "GlyphLabel volvió al default #000"


# ══════════════════════════════════════════════════════════════════════
# C3 — procedencia de reacciones custom
# ══════════════════════════════════════════════════════════════════════
_BASE = {
    "id": "CUSTOM-1", "name": "A + B -> C",
    "stoich": [{"formula": "CO", "phase": "g", "nu": -1},
               {"formula": "H2O", "phase": "g", "nu": -1},
               {"formula": "CO2", "phase": "g", "nu": 1},
               {"formula": "H2", "phase": "g", "nu": 1}],
    "dh_rxn_298_kJ_mol": -41.2,
    "keq_298": 1.0e4,
}


def test_reaccion_manual_queda_user():
    import reactions_db as rdb
    rxn = rdb.reaction_from_dict(dict(_BASE))
    assert rxn.origin == "user"
    assert rxn.estimation_method == ""
    assert rxn.transformation_id is None


def test_reaccion_del_predictor_persiste_procedencia():
    """El dict del builder con la procedencia del predictor debe
    llegar intacto al objeto Reaction (round-trip)."""
    import reactions_db as rdb
    d = dict(_BASE)
    d.update({"origin": "predicted",
              "estimation_method": "joback",
              "estimation_uncertainty_kJ_mol": 12.5,
              "transformation_id": "T01_esterification_fischer",
              "confidence_mechanism": "media",
              "confidence_thermo": "baja"})
    rxn = rdb.reaction_from_dict(d)
    assert rxn.origin == "predicted"
    assert rxn.estimation_method == "joback"
    assert rxn.estimation_uncertainty_kJ_mol == pytest.approx(12.5)
    assert rxn.transformation_id == "T01_esterification_fischer"
    assert rxn.confidence_mechanism == "media"
    assert rxn.confidence_thermo == "baja"


def test_origin_invalido_rechazado():
    import reactions_db as rdb
    d = dict(_BASE); d["origin"] = "marciano"
    with pytest.raises(ValueError, match="origin"):
        rdb.reaction_from_dict(d)
    d = dict(_BASE); d["confidence_mechanism"] = "altisima"
    with pytest.raises(ValueError, match="confidence_mechanism"):
        rdb.reaction_from_dict(d)


# ══════════════════════════════════════════════════════════════════════
# P3/P4 — censo final: 0 hex sueltos en las superficies UI auditadas
# ══════════════════════════════════════════════════════════════════════
_UI_FILES = [
    "flowsheet_qt.py", "chemfx/ui/reactivity_dock_qt.py",
    "block_inspector.py", "stream_inspector.py", "streams_table.py",
    "econ_richview.py", "editor_chrome.py", "welcome_qt.py",
    "hx_inspector.py", "inspector_widgets.py", "hx_edu.py", "hx_icons.py",
    "solver_report.py", "inspector_evidence.py", "econ_figures.py",
    "econ_widgets.py", "dialog_kit.py", "indicators.py",
    "estimated_overlay.py", "hx_bubbles.py", "stream_bubbles.py",
]


def test_censo_hex_ui_cero():
    """La clase 'hex suelto en superficie UI' murió en el ciclo 4.
    tokens.py (la paleta) y los glifos/papel del PFD quedan fuera por
    diseño."""
    for rel in _UI_FILES:
        malos = []
        for i, line in enumerate(
                (ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#") or "antes:" in line:
                continue     # comentarios (p.ej. "antes: #3a3a3a")
            malos += [(i, m) for m in _HEX_RE.findall(line)]
        assert malos == [], f"{rel} tiene hex sueltos: {malos[:5]}"


def test_hx_edu_popover_usa_qfont():
    """P3: el popover educativo adopta la escala FONT_* (qfont); no
    quedan QFont numéricos sueltos en hx_edu."""
    src = (ROOT / "hx_edu.py").read_text(encoding="utf-8")
    assert "QFont(" not in src
    for tok in ("qfont(FONT_TITLE)", "qfont(FONT_UI)",
                "qfont(FONT_VALUE)", "qfont(FONT_HINT)"):
        assert tok in src, f"falta {tok}"


def test_evidencia_reactor_distingue_predictor():
    import inspector_evidence as ev
    block = SimpleNamespace(
        eq_type="Reactor — jacketed agitated", reactor_mode="stoich",
        reactions=[], reactor_conversion=None, T_op_K=0, P_op_bar=0,
        custom_reactions=[dict(_BASE, origin="predicted"),
                          dict(_BASE)])
    txt = ev.reactor_text(block)
    assert txt is not None
    assert "2 reacción(es)" in txt
    assert "(1 del predictor)" in txt
