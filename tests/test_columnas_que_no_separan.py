"""Las 3 'columnas que no separan' del inventario de hardcode.

El inventario marcó 3 torres con entrada ≈ salidas (no fraccionan):
  · hydraulic/T-101  → re-tipada a vessel (este PR): agua pura 1-in/1-out, una
                       columna no puede separar un solo componente.
  · talara/T-201     → recuperaciones de pseudocortes declaradas y conservativas.
  · hda_full/T-103   → divisor de purga de tolueno, sin inventar difenilo.

Ver docs/inventario_hardcode.md §6 para el veredicto completo.
"""
import examples_registry as reg
import flowsheet_solver as fsv
import pytest


def _stream(fs, name):
    return next(s for s in fs.streams.values() if s.name == name)


def _block(fs, name):
    return next(b for b in fs.blocks.values() if b.name == name)


# ── LIMPIA: hydraulic/T-101 re-tipada a vessel ──────────────────────────
def test_hydraulic_t101_ya_no_es_tower():
    """T-101 era 'Tower (column shell)' sobre agua pura 1-in/1-out (no separa
    nada).  Re-tipada a vessel para reflejar la física: un pass-through, no
    una columna de separación."""
    fs = reg.load_example("hydraulic")
    b = _block(fs, "T-101")
    assert b.eq_type == "Vessel — vertical"
    assert b.column_active is False


def test_hydraulic_t101_pass_through_agua():
    """Comportamiento preservado tras el re-tipado: agua propaga, masa cierra,
    y el Δp de −0.3 bar se mantiene (no se perdió nada computado)."""
    fs = reg.load_example("hydraulic")
    res = fsv.solve(fs)
    assert res.overall_status == "ok" and len(res.mass_balance_errors) == 0
    inn = _stream(fs, "S-cooled")
    out = _stream(fs, "S-product")
    assert out.composition == inn.composition == {"water": 1.0}
    assert abs(out.mass_flow - inn.mass_flow) < 1e-6           # 1-in = 1-out
    assert abs((inn.pressure_bar - out.pressure_bar) - 0.3) < 1e-6   # Δp preservado


# ── Modelos auditados: conservan especies y declaran su alcance ─────────
def test_talara_t201_sigue_splitter_correcto():
    """El ensayo de pseudocortes determina VGO y residuo; la torre conserva
    cada componente mediante recuperaciones especificadas, sin fingir VLE."""
    fs = reg.load_example("talara")
    fsv.solve(fs)
    b = _block(fs, "T-201")
    assert b.component_recovery_active and not b.splitter_active
    assert b.eq_type == "Tower (column shell)"
    assert b.P_op_bar == 0.08
    ins = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    feed = sum(s.mass_flow for s in ins)
    assert abs(sum(s.mass_flow for s in outs) - feed) < 1e-6
    species = {c for s in ins + outs for c in s.composition}
    for component in species:
        incoming = sum(s.mass_flow * s.composition.get(component, 0) for s in ins)
        outgoing = sum(s.mass_flow * s.composition.get(component, 0) for s in outs)
        assert abs(outgoing - incoming) < 1e-6
    assert _stream(fs, "C7-VGO").composition == {"crude_oil": 1.0}
    assert _stream(fs, "C8-resid-vac").composition == {"atmospheric_residue": 1.0}


def test_hda_full_purga_tolueno_no_inventa_separacion_de_difenilo():
    """Sin reacción lateral de difenilo, la antigua T-103 es una purga
    homogénea. Ambas ramas conservan composición y suman la alimentación."""
    fs = reg.load_example("hda_full")
    res = fsv.solve(fs)
    b = _block(fs, "SPL-TOL")
    assert b.column_active is False and b.splitter_active
    assert b.eq_type == "Splitter — flow divider"
    assert len(res.mass_balance_errors) == 0
    feed = next(s for s in fs.streams.values() if s.dst == b.id)
    outs = [s for s in fs.streams.values() if s.src == b.id]
    # El lazo iterativo cierra a precisión relativa, no a una cantidad fija
    # en t/a que cambia su significado cuando se escala la planta.
    assert sum(s.mass_flow for s in outs) == pytest.approx(feed.mass_flow, rel=1e-8)
    assert all(s.composition == pytest.approx(feed.composition, abs=1e-9) for s in outs)
    assert all('biphenyl' not in s.composition for s in outs)
