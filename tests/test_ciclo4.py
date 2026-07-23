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
    "book_table.py",     # tabla de libro (Design ciclo 4, 4a)
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


# ══════════════════════════════════════════════════════════════════════
# C.2 — cobertura de catálogo + BUG 16 (WHB desbloqueado sin sizer)
# ══════════════════════════════════════════════════════════════════════
# Internos de columna: excepción deliberada — no son bloques standalone
# en un flowsheet real (viven dentro de la torre); quedan como únicos
# eq_types sin ejemplo.
_INTERNOS_COLUMNA = {"Tray — sieve", "Tray — valve",
                     "Packing — random", "Packing — structured"}


def test_cobertura_catalogo_solo_internos_sin_ejemplo():
    """Los 3 ejemplos nuevos (solvent_rec, reformer_whb, cw_natural)
    cierran C.2: todo eq_type del catálogo menos los internos de
    columna tiene al menos una instancia en el set de ejemplos."""
    import json as _json
    import equipment_costs as ec
    usados = set()
    for fn in (ROOT / "data" / "examples").glob("*.json"):
        if fn.name.startswith("_") or fn.name == "manifest.json":
            continue
        d = _json.loads(fn.read_text(encoding="utf-8"))
        for b in d.get("blocks", {}).values():
            if b.get("eq_type"):
                usados.add(b["eq_type"])
    sin_uso = set(ec.EQUIPMENT_DATA) - usados
    assert sin_uso == _INTERNOS_COLUMNA, (
        f"eq_types sin ejemplo fuera de la excepción: "
        f"{sorted(sin_uso - _INTERNOS_COLUMNA)}; "
        f"internos que ganaron ejemplo: "
        f"{sorted(_INTERNOS_COLUMNA - sin_uso)}")


def test_bug16_whb_desbloqueado_se_dimensiona_en_solve():
    """BUG 16: los WHB (categoría HX pero S = kg/h de vapor) no pasaban
    por ningún sizer en solve() — _size_heat_exchangers los rehúsa
    (solo área) y _size_process_equipment salteaba toda la categoría →
    S=0 y costo colapsado en silencio para un WHB sin S_locked."""
    from flowsheet_model import Flowsheet, Block, Stream
    import flowsheet_solver as fsolv

    fs = Flowsheet()
    w = Block(id=fs.new_id(), name="E-1",
              eq_type="Heat exch. — WHB field erected", S=0.0,
              heat_source="bfw_to_steam_HP", heat_source_locked=True)
    fs.blocks[w.id] = w
    comp = {"methane": 0.25, "water": 0.75}
    s1 = Stream(id=fs.new_id(), name="in", src=0, dst=w.id,
                mass_flow=900000, mass_flow_locked=True,
                temperature=850, temperature_locked=True, role="feed",
                phase="vapor", phase_locked=True,
                composition=dict(comp), composition_locked=True)
    s2 = Stream(id=fs.new_id(), name="out", src=w.id, dst=0,
                temperature=330, temperature_locked=True,
                role="product", phase="vapor", phase_locked=True,
                composition=dict(comp))
    fs.streams[s1.id] = s1
    fs.streams[s2.id] = s2

    fsolv.solve(fs)
    assert w.S > 20000, (
        f"WHB desbloqueado quedó en S={w.S} — el solve no aplicó "
        f"size_whb (regresión del BUG 16)")


# ══════════════════════════════════════════════════════════════════════
# C.1 — capa 8: viscosidad μ(T) y conductividad k líquidas por compuesto
# ══════════════════════════════════════════════════════════════════════
def test_capa8_puntos_crc():
    """Los puntos experimentales (CRC 97ª, 25 °C) se leen del .md y se
    devuelven exactos en el punto de referencia."""
    import thermo_db as td
    esperados = {          # (μ mPa·s, k W/m·K) @ 25 °C
        "water": (0.890, 0.6062), "ethanol": (1.074, 0.167),
        "benzene": (0.604, 0.1411), "toluene": (0.560, 0.1310),
        "hexane": (0.300, 0.1200), "glycerin": (934.0, 0.285),
        "kerosene": (1.64, 0.115),
    }
    for n, (mu, k) in esperados.items():
        assert td.viscosity_Pa_s(n, 25) == pytest.approx(mu * 1e-3), n
        c = td.get(n)
        assert c.thermal_conductivity_W_mK(25) == pytest.approx(k), n


def test_capa8_lewis_squires_extrapola():
    """μ(T) desde UN punto (Lewis-Squires): contra CRC a 50 °C queda
    dentro de la banda documentada (±15 %)."""
    import thermo_db as td
    crc_50 = {"water": 0.547, "ethanol": 0.702, "glycerin": 142.0}
    for n, mu_crc in crc_50.items():
        mu = td.viscosity_Pa_s(n, 50) * 1e3
        assert abs(mu - mu_crc) / mu_crc < 0.15, \
            f"{n}: μ(50°C)={mu:.3f} vs CRC {mu_crc} (>15%)"


def test_capa8_mezcla_arrhenius_y_prandtl():
    import thermo_db as td
    # ln μ_mix = Σ w ln μ — 50/50 agua/etanol a 25 °C
    import math
    mu = td.viscosity_mix_Pa_s({"water": 0.5, "ethanol": 0.5}, 25)
    esperado = math.exp(0.5 * math.log(0.890e-3)
                        + 0.5 * math.log(1.074e-3))
    assert mu == pytest.approx(esperado)
    # componentes sin capa → se omiten; ninguno con capa → None
    assert td.viscosity_mix_Pa_s({"syngas": 1.0}, 25) is None
    # Pr del agua a 25 °C ≈ 6.1 (cp 4.18 · μ 0.89e-3 / k 0.606)
    pr = td.prandtl_liq({"water": 1.0}, 25)
    assert pr is not None and 5.5 < pr < 6.8, pr


def test_capa8_pressure_drop_consume_la_capa():
    """_viscosity_Pa_s usa la capa 8 cuando está poblada y conserva la
    heurística documentada cuando no."""
    import pressure_drop as pdp
    mu = pdp._viscosity_Pa_s({"water": 1.0}, 298.15, "liquid")
    assert mu == pytest.approx(0.890e-3), \
        "agua a 25°C debería salir de la capa 8 (0.89 cP), no 1 cP"
    mu_fallback = pdp._viscosity_Pa_s({"syngas": 1.0}, 298.15, "liquid")
    assert mu_fallback == pytest.approx(1.0e-3), \
        "sin capa poblada debe caer a la heurística (1 cP @ 25°C)"
    assert pdp._viscosity_Pa_s({"water": 1.0}, 298.15, "gas") \
        == pytest.approx(1.8e-5)


def test_capa8_prandtl_en_diagnostico_hx():
    """El diag del HX gana Pr_process informativo (sin tocar U)."""
    import examples_registry as reg
    import flowsheet_solver as fsolv
    fs = reg.load_example("cw_natural")
    fsolv.solve(fs)
    e303 = next(b for b in fs.blocks.values() if b.name == "E-303")
    diag = getattr(e303, "_hx_diagnostics", {}) or {}
    pr = diag.get("Pr_process")
    assert pr is not None and 1.5 < pr < 4.0, (
        f"Pr_process del agua a 80°C debería rondar 2-3, vino {pr}")
    assert diag.get("U_used"), "la U de servicio no debe desaparecer"


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
