"""Frente 5 (auditoría frontend) — acople del predictor chemfx.

Protege los tres eslabones que estaban rotos o sin cablear:
  1. include_auto era un flag ignorado (# noqa ARG001) y fa.auto siempre
     vacío: el cache auto_reactions_db.md (567 combustiones/cracking
     generados en Fase 6) no tenía loader y nunca llegaba al predictor.
  2. ReactivityDock estaba definido en chemfx/ui pero NUNCA se
     instanciaba: el menú Vista, el hide inicial y el refresh post-solve
     lo tomaban con getattr(..., None) y degradaban a no-op silencioso.
  3. El ΔH del predictor (Joback/Benson) se descartaba en el diálogo de
     reacción custom: con especies sin ΔHf en thermo_db, Hess devolvía
     None y el ΔH quedaba 0 silencioso.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


# ══════════════════════════════════════════════════════════════════════
# 1. Loader del cache AUTO
# ══════════════════════════════════════════════════════════════════════
def test_loader_parsea_cache_completo():
    from chemfx.auto_reactions.loader import load_auto_reactions
    rxns = load_auto_reactions(force_reload=True)
    assert len(rxns) >= 500, f"cache AUTO con {len(rxns)} < 500 reacciones"
    for r in rxns[:50] + rxns[-50:]:
        assert r["id"].startswith("AUTO_")
        assert r["stoich"], f"{r['id']} sin estequiometría"
        assert any(sp.nu < 0 for sp in r["stoich"]), f"{r['id']} sin reactantes"
        assert any(sp.nu > 0 for sp in r["stoich"]), f"{r['id']} sin productos"
        assert r.get("T_min_K", 0) < r.get("T_max_K", 0)


def test_loader_balance_atomico_muestral():
    """Las AUTO del cache deben estar balanceadas átomo a átomo (el
    generator las balancea; el loader no debe corromperlas al parsear)."""
    from chemfx.auto_reactions.loader import load_auto_reactions
    from chemfx.auto_reactions.combustion_complete import _parse_formula_chnos

    rxns = load_auto_reactions()
    checked = 0
    for r in rxns:
        total = {}
        parseable = True
        for sp in r["stoich"]:
            try:
                atoms = _parse_formula_chnos(sp.formula)
            except Exception:
                parseable = False
                break
            if not atoms:
                parseable = False
                break
            for el, n in atoms.items():
                total[el] = total.get(el, 0) + sp.nu * n
        if not parseable:
            continue
        checked += 1
        bad = {el: v for el, v in total.items() if abs(v) > 1e-6}
        assert not bad, f"{r['id']} desbalanceada: {bad}"
    assert checked >= 300, f"solo {checked} reacciones verificables"


def test_loader_degrada_sin_cache(monkeypatch, tmp_path):
    import chemfx.auto_reactions.loader as loader
    monkeypatch.setattr(loader, "_DATA_PATH", tmp_path / "no_existe.md")
    assert loader.load_auto_reactions(force_reload=True) == []
    # Restaurar el cache memoizado para los demás tests
    monkeypatch.undo()
    assert len(loader.load_auto_reactions(force_reload=True)) >= 500


# ══════════════════════════════════════════════════════════════════════
# 2. predict_reactions honra include_auto
# ══════════════════════════════════════════════════════════════════════
def test_predict_reactions_metano_oxigeno_trae_combustion_auto():
    from chemfx.predictor.reaction_predictor import predict_reactions

    fa = predict_reactions(["methane", "oxygen"], T_K=1000.0)
    assert fa.auto, "fa.auto vacío: include_auto=True no surte efecto"
    labels = [getattr(r, "display_label", "") for r in fa.auto]
    assert any("CH4" in lb for lb in labels), f"sin combustión de CH4: {labels}"
    # Solo reacciones cuyos reactantes están TODOS en el feed
    for r in fa.auto:
        for sp in r.stoichiometry:
            if sp.nu < 0:
                assert sp.formula in ("CH4", "O2"), (
                    f"{r.id} matcheó con reactante fuera del feed: "
                    f"{sp.formula}")


def test_predict_reactions_include_auto_false():
    from chemfx.predictor.reaction_predictor import predict_reactions
    fa = predict_reactions(["methane", "oxygen"], T_K=1000.0,
                           include_auto=False)
    assert fa.auto == []


def test_auto_fuera_de_rango_T_no_matchea():
    from chemfx.predictor.reaction_predictor import predict_reactions
    # Combustiones AUTO arrancan en 700 K — a 300 K no aplican
    fa = predict_reactions(["methane", "oxygen"], T_K=300.0)
    assert all("combust" not in getattr(r, "transformation_id", "")
               for r in fa.auto), "combustión matcheó a 300 K"


def test_auto_trae_dh_estimado_por_hess():
    """Para especies del thermo_db (CH4/O2/CO2/H2O) el ΔH de la
    combustión completa debe salir de Hess ≈ -802 kJ/mol CH4."""
    from chemfx.predictor.reaction_predictor import predict_reactions
    fa = predict_reactions(["methane", "oxygen"], T_K=1000.0)
    completas = [r for r in fa.auto
                 if "completa" in getattr(r, "display_label", "").lower()
                 and any(sp.formula == "CH4" for sp in r.stoichiometry)]
    assert completas, "no matcheó la combustión completa de CH4"
    est = completas[0].delta_h_298
    assert est is not None, "combustión de CH4 sin ΔH estimado"
    assert -900.0 < est.value < -700.0, f"ΔH fuera de rango: {est.value}"


def test_auto_degrada_sin_rdkit_thermo():
    """El camino AUTO no depende de rdkit/thermo: con ambos bloqueados
    la combustión de CH4 igual aparece (loader + Hess local)."""
    import subprocess
    code = (
        "import sys\n"
        "class B:\n"
        "    def find_module(self, name, path=None):\n"
        "        if name.split('.')[0] in ('rdkit', 'thermo'):\n"
        "            return self\n"
        "    def load_module(self, name):\n"
        "        raise ImportError('blocked: ' + name)\n"
        "sys.meta_path.insert(0, B())\n"
        "from chemfx.predictor.reaction_predictor import predict_reactions\n"
        "fa = predict_reactions(['methane', 'oxygen'], T_K=1000.0)\n"
        "assert fa.auto, 'AUTO vacio sin rdkit'\n"
        "print('OK', len(fa.auto))\n"
    )
    r = subprocess.run([sys.executable, "-c", code],
                       cwd=str(Path(__file__).resolve().parent.parent),
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"stderr: {r.stderr[-800:]}"
    assert r.stdout.startswith("OK")


# ══════════════════════════════════════════════════════════════════════
# 3. ReactivityDock montado en la ventana principal
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_reactivity_dock_montado(qapp):
    import flowsheet_qt as fq
    win = fq.FlowsheetMainWindow()
    try:
        dock = getattr(win, "reactivity_dock", None)
        assert dock is not None, "reactivity_dock sigue huérfano"
        # Oculto al arrancar (UI principal = paleta + inspector)
        assert not dock.isVisible()
        # El refresh post-solve no debe reventar con flowsheet vacío
        dock.refresh_from_flowsheet(win.fs)
        # La acción de Vista existe (menú lo toma vía toggleViewAction)
        assert dock.toggleViewAction() is not None
    finally:
        win.close()


def test_reactivity_dock_refresh_con_ejemplo(qapp):
    """analyze_flowsheet sobre un ejemplo real → el dock refresca sin
    error y cuenta los warnings que los bloques traen anotados."""
    import chemfx
    import flowsheet_qt as fq
    from examples_registry import load_example

    win = fq.FlowsheetMainWindow()
    try:
        fs = load_example("methanol")
        chemfx.analyze_flowsheet(fs)
        win.reactivity_dock.refresh_from_flowsheet(fs)
        n_warns = sum(len(getattr(b, "reaction_warnings", []) or [])
                      for b in fs.blocks.values())
        tab0 = win.reactivity_dock._tabs.tabText(0)
        assert f"({n_warns})" in tab0, f"tab '{tab0}' ≠ {n_warns} warnings"
    finally:
        win.close()
