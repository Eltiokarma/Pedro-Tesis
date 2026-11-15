"""PR-A — Conciencia física del solver.

Verifica los warnings advisory tagged [W-...] que EXPONEN inconsistencias
físicas latentes (cierre de energía por bloque, T de descarga de compresor,
duty espurio, reactor placeholder, split-lock, duty>S, signo de duty) y el
INVARIANTE de regresión: estos warnings NO alteran overall_status.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_solver as fsv
import examples_registry as reg

_TAG = re.compile(r"\[(W-[A-Z-]+)\]")


def _solve(clave):
    fs = reg.load_example(clave)
    res = fsv.solve(fs)
    return fs, res


def _tags(res):
    out = set()
    for w in res.awareness_warnings:
        m = _TAG.match(w)
        if m:
            out.add(m.group(1))
    return out


def _lines(res, tag):
    return [w for w in res.awareness_warnings if w.startswith(f"[{tag}]")]


# ── 1.1 [W-ENERGY-BLOCK] ────────────────────────────────────────────────
def test_energy_block_compressor_detector_sigue_vivo():
    """El catálogo ya calcula los duties de máquina (multi-etapa con
    intercooling contabilizado), así que methanol K-101 ya NO dispara.
    Detector vivo: si se RE-introduce un duty espurio hardcodeado (el
    defecto histórico de ammonia: 1200 kW declarados), vuelve a disparar."""
    fs = reg.load_example("methanol")
    k = next(b for b in fs.blocks.values() if b.name == "K-101")
    k.duty = 5000.0
    k.duty_locked = True
    res = fsv.solve(fs)
    lines = [w for w in res.awareness_warnings
             if w.startswith("[W-ENERGY-BLOCK]") and "K-101" in w]
    assert lines, "K-101 con duty espurio debe disparar W-ENERGY-BLOCK"
    assert "≠ ΔH" in lines[0]


def test_energy_block_barrido_amplio():
    """The detector covers several equipment types without requiring bad examples."""
    import flowsheet_model as fm
    for eq_type in ('Heat exch. - floating head', 'Mixer - static', 'Storage tank - cone roof'):
        fs = fm.Flowsheet()
        fs.blocks[1] = b = fm.Block(id=1, name='BAD-ENERGY', eq_type=eq_type, S=1)
        fs.streams[2] = fm.Stream(id=2, name='in', src=0, dst=1, mass_flow=100000,
                                  temperature=25, composition={'water':1}, phase='liquid')
        fs.streams[3] = fm.Stream(id=3, name='out', src=1, dst=0, mass_flow=100000,
                                  temperature=100, composition={'water':1}, phase='liquid')
        assert any(w.startswith('[W-ENERGY-BLOCK]') for w in fsv._compute_awareness_warnings(fs))
        b.duty = fsv.infer_block_duty(fs, b)
        assert not any(w.startswith('[W-ENERGY-BLOCK]') for w in fsv._compute_awareness_warnings(fs))


def test_energia_reactor_primera_ley():
    """Programa de energía de reactor (análogo al de columnas): el duty de
    un reactor con química real se deriva por PRIMERA LEY con el mismo
    modelo entálpico del chequeo (duty = H_out − H_in + Q_rxn), así que
    ammonia/methanol/sulfuric R-101 ya NO disparan W-ENERGY-BLOCK."""
    for clave in ("ammonia", "methanol", "sulfuric"):
        fs, res = _solve(clave)
        hits = [w for w in _lines(res, "W-ENERGY-BLOCK") if "R-101" in w]
        assert hits == [], f"{clave}/R-101 debería cerrar energía: {hits}"
        # el duty refinado cierra el balance contra las corrientes
        from stream_enthalpy import stream_enthalpy_kW
        b = next(x for x in fs.blocks.values() if x.name == "R-101")
        ins = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        h_in = sum(stream_enthalpy_kW(s) or 0.0 for s in ins)
        h_out = sum(stream_enthalpy_kW(s) or 0.0 for s in outs)
        m_in = sum(s.mass_flow for s in ins) * 1000.0 / (365 * 24 * 3600.0)
        q_rxn = -m_in * b.heat_of_reaction
        resid = h_out - h_in - b.duty - q_rxn
        assert abs(resid) < 1.0, f"{clave}/R-101 resid={resid:+.1f} kW"


def test_energia_reactor_detector_sigue_vivo():
    """Changing a solved reactor duty must expose the first-law error."""
    fs, result = _solve('ammonia')
    b = next(x for x in fs.blocks.values() if x.name == 'R-101')
    assert not any('R-101' in w for w in _lines(result, 'W-ENERGY-BLOCK'))
    b.duty -= 5000
    hits = [w for w in fsv._compute_awareness_warnings(fs)
            if w.startswith('[W-ENERGY-BLOCK]') and 'R-101' in w]
    assert hits


def test_comp_t_ldpe_extremo():
    """ldpe K-101/S-HP: con el modelo multi-etapa la descarga baja de
    ~1322 °C (1 etapa) a ~134 °C → ya NO dispara.  Detector vivo: si la
    descarga se fuerza a un valor >250 °C (lock), vuelve a disparar."""
    _, res = _solve("ldpe")
    assert not any("S-HP" in w for w in _lines(res, "W-COMP-T")), \
        "multi-etapa debería mantener la descarga < 250 °C"
    fs = reg.load_example("ldpe")
    s = next(x for x in fs.streams.values() if x.name == "S-HP")
    s.temperature = 1322.0
    s.temperature_locked = True
    res2 = fsv.solve(fs)
    lines = [w for w in res2.awareness_warnings
             if w.startswith("[W-COMP-T]") and "S-HP" in w and "250" in w]
    assert lines, "descarga forzada a 1322 °C debe disparar W-COMP-T"


def test_comp_t_solo_supera_umbral():
    """Ningún W-COMP-T debe dispararse por debajo de 250 °C."""
    for clave in ("ldpe", "acetic", "urea", "ammonia", "quimpac"):
        _, res = _solve(clave)
        for w in _lines(res, "W-COMP-T"):
            grados = float(re.search(r"=\s*(-?\d+)\s*°C", w).group(1))
            assert grados > 250


# ── 1.3 [W-T-OVERRIDE] ──────────────────────────────────────────────────
def test_t_override_se_dispara():
    """El catálogo ya no pierde intenciones de T (las descargas quedaron
    lockeadas al valor resuelto o declaradas a 25 = 'calcular').  Detector
    vivo: una T declarada ≠25 sin lock que el solver recalcula dispara."""
    fs = reg.load_example("ammonia")
    s = next(x for x in fs.streams.values() if x.name == "S-1")
    s.temperature = 500.0            # intención declarada que el solver pisará
    s.temperature_locked = False
    res = fsv.solve(fs)
    lines = [w for w in res.awareness_warnings
             if w.startswith("[W-T-OVERRIDE]") and "S-1" in w]
    assert lines, "T declarada 500°C recalculada debe disparar W-T-OVERRIDE"


# ── 1.4 [W-MIXER-DUTY] / [W-TANK-DUTY] ──────────────────────────────────
def test_mixer_duty_industrial():
    """industrial M-101 quedó con salida entálpicamente consistente (72.8 °C)
    → ya no dispara.  Detector vivo: re-introducir la T espuria dispara."""
    fs = reg.load_example("industrial")
    b = next(x for x in fs.blocks.values() if x.name == "M-101")
    out = next(s for s in fs.streams.values() if s.src == b.id)
    out.temperature = 25.0           # T espuria: la mezcla real da ~72.8 °C
    out.temperature_locked = True
    res = fsv.solve(fs)
    assert any("M-101" in w for w in _lines(res, "W-MIXER-DUTY"))


def test_tank_duty_industrial():
    """industrial TK-301 quedó con salida entálpicamente consistente
    (137.9 °C) → ya no dispara.  Detector vivo: T espuria dispara."""
    fs = reg.load_example("industrial")
    b = next(x for x in fs.blocks.values() if x.name == "TK-301")
    out = next(s for s in fs.streams.values() if s.src == b.id)
    out.temperature = 25.0           # T espuria: la mezcla real da ~137.9 °C
    out.temperature_locked = True
    res = fsv.solve(fs)
    assert any("TK-301" in w for w in _lines(res, "W-TANK-DUTY"))


# ── 1.5 [W-PLACEHOLDER] + bonus ─────────────────────────────────────────
def test_catalogue_has_no_fake_reaction_identifiers():
    """Every declared reaction is real or an explicitly defined custom model."""
    import reactions_db
    for item in reg.list_examples():
        fs = reg.load_example(item['clave'])
        for block in fs.blocks.values():
            for reaction_id in block.reactions:
                assert reactions_db.get(reaction_id) is not None, (item['clave'], block.name, reaction_id)


def test_placeholder_bonus_ldpe_r027():
    """The warning still identifies an intentionally reintroduced fake ID."""
    fs = reg.load_example('ldpe')
    block = next(b for b in fs.blocks.values() if b.name == 'R-101')
    assert block.reactions == ['R027']
    block.reactions = ['R027_PLACEHOLDER']
    lines = fsv._compute_awareness_warnings(fs)
    assert any('[W-PLACEHOLDER]' in w and 'R027 existe curada' in w for w in lines)


def test_talara_desalter_uses_conservative_component_recovery():
    """Desalting separates water/contaminants, not a bulk fixed-ratio split."""
    fs, result = _solve('talara')
    b = next(b for b in fs.blocks.values() if b.name == 'V-101')
    assert b.component_recovery_active and not b.splitter_active
    assert not any('V-101' in w for w in _lines(result, 'W-SPLIT-LOCK'))
    ins = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    from component_recovery import _canonical
    for species in {_canonical(c) for s in ins+outs for c in s.composition}:
        m_in = sum(s.mass_flow*x for s in ins for c,x in s.composition.items()
                   if _canonical(c) == species)
        m_out = sum(s.mass_flow*x for s in outs for c,x in s.composition.items()
                    if _canonical(c) == species)
        assert abs(m_in-m_out) < max(1e-6, m_in*1e-8)


def test_split_lock_detector_sigue_vivo():
    """Wrong keyed outlet fractions conflict with locked flows and are detected."""
    import flowsheet_model as fm
    fs = fm.Flowsheet()
    fs.blocks[1] = fm.Block(id=1, name='SPLIT', eq_type='Splitter', S=1, splitter_active=True)
    fs.streams[2] = fm.Stream(id=2, name='feed', src=0, dst=1, mass_flow=1000,
                              composition={'water':1})
    fs.streams[3] = fm.Stream(id=3, name='small', src=1, dst=0, mass_flow=200,
                              mass_flow_locked=True, split_fraction=.8, composition={'water':1})
    fs.streams[4] = fm.Stream(id=4, name='large', src=1, dst=0, mass_flow=800,
                              mass_flow_locked=True, split_fraction=.2, composition={'water':1})
    assert any(w.startswith('[W-SPLIT-LOCK]') for w in fsv._compute_awareness_warnings(fs))
    fs.streams[3].split_fraction, fs.streams[4].split_fraction = .2, .8
    assert not any(w.startswith('[W-SPLIT-LOCK]') for w in fsv._compute_awareness_warnings(fs))


def test_duty_s_talara_fhtn():
    """Undersizing the actual solved heater must produce a cost-capacity warning."""
    fs, result = _solve('talara')
    assert not any('F-HTN' in w for w in _lines(result, 'W-DUTY-S'))
    b = next(x for x in fs.blocks.values() if x.name == 'F-HTN')
    assert b.duty > 0
    b.S = abs(b.duty)*.5
    assert any(w.startswith('[W-DUTY-S]') and 'F-HTN' in w
               for w in fsv._compute_awareness_warnings(fs))


def test_sign_rxn_flash_col_aircooler():
    """rxn_flash_col E-101 calentaba (25→87 °C) y estaba mal tipado como
    air cooler; re-tipado a floating head → ya no dispara.  Detector vivo:
    re-tipar a air cooler (duty>0) vuelve a disparar."""
    _, res = _solve("rxn_flash_col")
    assert not any("E-101" in w for w in _lines(res, "W-SIGN"))
    fs = reg.load_example("rxn_flash_col")
    b = next(x for x in fs.blocks.values() if x.name == "E-101")
    b.eq_type = "Heat exch. — air cooler"     # el mal tipado histórico
    res2 = fsv.solve(fs)
    lines = [w for w in res2.awareness_warnings
             if w.startswith("[W-SIGN]") and "E-101" in w and "air cooler" in w]
    assert lines, "air cooler con duty>0 debe disparar W-SIGN"


# ── INVARIANTE: los warnings NO alteran overall_status ──────────────────
def test_awareness_no_altera_overall_status(monkeypatch):
    """Advisory diagnostics do not change solver acceptance of a valid process."""
    _, baseline = _solve('ldpe')
    original = fsv._compute_awareness_warnings
    monkeypatch.setattr(fsv, '_compute_awareness_warnings',
                        lambda fs: original(fs) + ['[W-DUTY-S] injected advisory'])
    _, with_advisory = _solve('ldpe')
    assert with_advisory.overall_status == baseline.overall_status == 'ok'
    assert '[W-DUTY-S] injected advisory' in with_advisory.awareness_warnings


def test_ok_example_con_warnings_sigue_ok():
    """A real cost-capacity advisory does not invalidate material/energy closure."""
    fs = reg.load_example('ldpe')
    b = next(b for b in fs.blocks.values() if b.name == 'K-101')
    b.S, b.S_locked = 1, True
    result = fsv.solve(fs)
    assert result.overall_status == 'ok'
    assert any('K-101' in w for w in _lines(result, 'W-DUTY-S'))


def test_phys_nonvol_detecta_solido_en_vapor():
    """Un componente no-volátil (sal) ruteado a una salida de fase vapor —
    el síntoma del separador mal configurado (BUG 2) — debe disparar
    [W-PHYS-NONVOL] aunque el balance de masa cierre.  Protege ejemplos
    nuevos / ediciones de UI de la nonsense física silenciosa."""
    import flowsheet_model as fm
    fs = fm.Flowsheet()
    dr = fm.Block(id=fs.new_id(), name="DR-BAD", eq_type="Dryer — drum",
                  S=0.0, dryer_active=True, moisture_component="water",
                  final_moisture=0.005, solid_components=["sodium chloride"],
                  duty=40.0, duty_locked=True)
    fs.blocks[dr.id] = dr
    fs.streams[fs.new_id()] = (i := fm.Stream(
        id=fs._next_id - 1, name="S-in", src=0, dst=dr.id, role="feed",
        mass_flow=1000, mass_flow_locked=True, phase="liquid",
        main_component="sodium chloride", composition_locked=True,
        composition={"sodium chloride": 0.9, "water": 0.1}))
    fs.streams[fs.new_id()] = fm.Stream(
        id=fs._next_id - 1, name="S-vent-bad", src=dr.id, dst=0, role="waste",
        phase="vapor", main_component="sodium chloride",
        composition={"sodium chloride": 0.99, "water": 0.01})
    res = fsv.solve(fs)
    lines = _lines(res, "W-PHYS-NONVOL")
    assert any("S-vent-bad" in w and "sodium chloride" in w for w in lines), \
        f"debe disparar W-PHYS-NONVOL por sal en vapor: {res.awareness_warnings}"


def test_phys_nonvol_no_falso_positivo_agua_en_vapor():
    """El vapor de agua legítimo (volátil) NO debe disparar W-PHYS-NONVOL."""
    import flowsheet_model as fm
    fs = fm.Flowsheet()
    dr = fm.Block(id=fs.new_id(), name="DR-OK", eq_type="Dryer — drum",
                  S=0.0, dryer_active=True, moisture_component="water",
                  final_moisture=0.005, solid_components=["sodium chloride"],
                  duty=40.0, duty_locked=True)
    fs.blocks[dr.id] = dr
    fs.streams[fs.new_id()] = fm.Stream(
        id=fs._next_id - 1, name="S-in", src=0, dst=dr.id, role="feed",
        mass_flow=1000, mass_flow_locked=True, phase="liquid",
        main_component="sodium chloride", composition_locked=True,
        composition={"sodium chloride": 0.9, "water": 0.1})
    fs.streams[fs.new_id()] = fm.Stream(
        id=fs._next_id - 1, name="S-vapor", src=dr.id, dst=0, role="waste",
        phase="vapor", main_component="water", composition={"water": 1.0})
    res = fsv.solve(fs)
    assert _lines(res, "W-PHYS-NONVOL") == [], \
        "agua en vapor no debe disparar W-PHYS-NONVOL"
