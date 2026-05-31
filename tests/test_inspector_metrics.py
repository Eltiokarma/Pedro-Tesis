"""GATE 1 — anti-divergencia metrics vs text (inspector_evidence).

Para un ejemplo representativo de cada familia: *_metrics() devuelve dict y
cada valor numérico estructurado (metrics[].value, gauges[].text, bars[].value)
aparece como SUBSTRING en la *_text() correspondiente.  Misma fuente, misma
física, mismo formato → la card nunca muestra un número que difiera del texto.

Sin tocar el solver: solo se resuelve el ejemplo y se comparan las dos vistas.
"""
import pytest

import examples_registry as reg
import flowsheet_solver as fsv
import inspector_evidence as ev


def _solve(clave):
    fs = reg.load_example(clave)
    fsv.solve(fs)
    return fs


def _first(fs, pred):
    return next((b for b in fs.blocks.values() if pred(b)), None)


def _assert_consistent(metrics, text, label):
    """Cada value estructurado debe aparecer en el texto."""
    assert metrics is not None, f"{label}: metrics is None"
    assert text is not None, f"{label}: text is None (fuente divergente)"
    assert metrics.get("metrics"), f"{label}: sin metrics[]"
    for m in metrics["metrics"]:
        val = m["value"]
        assert val in text, (
            f"{label}: metric '{m['key']}' value={val!r} "
            f"NO aparece en text (divergencia).\ntext={text!r}")
    for g in metrics.get("gauges", []) or []:
        if g.get("text"):
            assert g["text"] in text, (
                f"{label}: gauge '{g['key']}' text={g['text']!r} no en text")
    for b in metrics.get("bars", []) or []:
        assert b["value"] in text, (
            f"{label}: bar value={b['value']!r} no en text")


def test_hx_metrics_matches_text():
    fs = _solve("distillation")
    blk = _first(fs, lambda b: getattr(b, "_hx_diagnostics", None))
    if blk is None:
        pytest.skip("sin HX con _hx_diagnostics en distillation")
    _assert_consistent(ev.hx_metrics(blk), ev.hx_text(blk), "hx")
    # patrón del handoff §6: el dTlm del diag aparece en ambos
    assert any(x["key"] == "dTlm" for x in ev.hx_metrics(blk)["metrics"])


def test_reactor_metrics_matches_text():
    fs = _solve("ammonia")
    blk = _first(fs, lambda b: ev.reactor_metrics(b) is not None)
    if blk is None:
        pytest.skip("sin reactor en ammonia")
    _assert_consistent(ev.reactor_metrics(blk), ev.reactor_text(blk), "reactor")


def test_mass_balance_metrics_matches_text():
    fs = _solve("ammonia")
    blk = _first(fs, lambda b: ev.mass_balance_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin balance de masa")
    _assert_consistent(ev.mass_balance_metrics(blk, fs),
                       ev.mass_balance_text(blk, fs), "mass_balance")


def test_energy_balance_metrics_matches_text():
    fs = _solve("ammonia")
    blk = _first(fs, lambda b: ev.energy_balance_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin balance de energía")
    _assert_consistent(ev.energy_balance_metrics(blk, fs),
                       ev.energy_balance_text(blk, fs), "energy_balance")


def test_mccabe_metrics_matches_text():
    fs = _solve("distillation")
    blk = _first(fs, lambda b: ev.mccabe_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin columna diseñada en distillation")
    _assert_consistent(ev.mccabe_metrics(blk, fs),
                       ev.mccabe_text(blk, fs), "mccabe")


def test_profile_metrics_matches_text():
    fs = _solve("distillation")
    blk = _first(fs, lambda b: ev.profile_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin perfil en distillation")
    _assert_consistent(ev.profile_metrics(blk, fs),
                       ev.profile_text(blk, fs), "profile")


def test_pump_metrics_matches_text():
    fs = _solve("hda_full")
    blk = _first(fs, lambda b: ev.pump_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin bomba en hda_full")
    _assert_consistent(ev.pump_metrics(blk, fs),
                       ev.pump_text(blk, fs), "pump")


def test_compressor_metrics_matches_text():
    fs = _solve("hda_full")
    blk = _first(fs, lambda b: ev.compressor_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin compresor en hda_full")
    _assert_consistent(ev.compressor_metrics(blk, fs),
                       ev.compressor_text(blk, fs), "compressor")


def test_hydraulic_metrics_matches_text():
    fs = _solve("hda_full")
    blk = _first(fs, lambda b: ev.hydraulic_breakdown_metrics(b, fs) is not None)
    if blk is None:
        pytest.skip("sin hidráulica en hda_full")
    _assert_consistent(ev.hydraulic_breakdown_metrics(blk, fs),
                       ev.hydraulic_breakdown_text(blk, fs), "hydraulic")


def test_mech_sep_metrics_matches_text():
    fs = _solve("biodiesel")
    blk = _first(fs, lambda b: ev.mech_sep_metrics(b) is not None)
    if blk is None:
        pytest.skip("sin separador mecánico en biodiesel")
    _assert_consistent(ev.mech_sep_metrics(blk), ev.mech_sep_text(blk),
                       "mech_sep")


def test_flash_metrics_matches_text():
    for clave in ("hda_full", "biodiesel", "ammonia", "distillation"):
        fs = _solve(clave)
        blk = _first(fs, lambda b: ev.flash_metrics(b) is not None)
        if blk is not None:
            _assert_consistent(ev.flash_metrics(blk), ev.flash_text(blk),
                               f"flash[{clave}]")
            return
    pytest.skip("sin flash en los ejemplos probados")


def test_splitter_metrics_matches_text():
    for clave in ("hda_full", "ammonia", "industrial", "talara"):
        fs = _solve(clave)
        blk = _first(fs, lambda b: ev.splitter_metrics(b) is not None)
        if blk is not None:
            _assert_consistent(ev.splitter_metrics(blk), ev.splitter_text(blk),
                               f"splitter[{clave}]")
            return
    pytest.skip("sin splitter en los ejemplos probados")


def test_tank_metrics_matches_text():
    for clave in ("biodiesel", "ethanol", "talara", "hda_full"):
        fs = _solve(clave)
        blk = _first(fs, lambda b: ev.tank_metrics(b, fs) is not None)
        if blk is not None:
            _assert_consistent(ev.tank_metrics(blk, fs),
                               ev.tank_text(blk, fs), f"tank[{clave}]")
            return
    pytest.skip("sin tanque en los ejemplos probados")


def test_utility_aux_metrics_matches_text():
    for clave in ("distillation", "hda_full", "ammonia", "talara"):
        fs = _solve(clave)
        blk = _first(fs, lambda b: ev.utility_aux_metrics(b, fs) is not None)
        if blk is not None:
            _assert_consistent(ev.utility_aux_metrics(blk, fs),
                               ev.utility_aux_text(blk, fs),
                               f"utility_aux[{clave}]")
            return
    pytest.skip("sin utility aux en los ejemplos probados")
