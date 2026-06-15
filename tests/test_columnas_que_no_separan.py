"""Las 3 'columnas que no separan' del inventario de hardcode.

El inventario marcó 3 torres con entrada ≈ salidas (no fraccionan):
  · hydraulic/T-101  → re-tipada a vessel (este PR): agua pura 1-in/1-out, una
                       columna no puede separar un solo componente.
  · talara/T-201     → DIFERIDA: torre de vacío real (costeo correcto) modelada
                       como splitter de masa; fraccionar de verdad necesita
                       pseudo-cortes (proyecto aparte).
  · hda_full/T-103   → DIFERIDA: columna pasiva en loop frozen que sí separa
                       débilmente; parte del proyecto 'columnas activas'.

Ver docs/inventario_hardcode.md §6 para el veredicto completo.
"""
import examples_registry as reg
import flowsheet_solver as fsv


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


# ── DIFERIDAS: regresión-guard de su estado documentado ─────────────────
def test_talara_t201_sigue_splitter_correcto():
    """DIFERIDA: torre de vacío modelada como splitter de masa 55/45.  Las
    fracciones alinean con sus salidas (no es el cruce de V-101): C7-VGO=0.55,
    C8-resid-vac=0.45.  Queda como simplificación documentada, no se re-tipa
    (mis-costearía una torre real)."""
    fs = reg.load_example("talara")
    fsv.solve(fs)
    b = _block(fs, "T-201")
    assert b.splitter_active and b.eq_type == "Tower (column shell)"
    outs = [s for s in fs.streams.values() if s.src == b.id]
    feed = sum(s.mass_flow for s in fs.streams.values() if s.dst == b.id)
    for k, s in enumerate(outs):
        assert abs(s.mass_flow - feed * b.splitter_fractions[k]) / feed < 0.02


def test_hda_full_t103_sigue_pasiva_loop_intacto():
    """DIFERIDA: columna pasiva en el loop frozen de hda_full.  NO se encendió
    nada — sigue column_active=False (parte del proyecto 'columnas activas').
    El balance global del ejemplo sigue cerrando."""
    fs = reg.load_example("hda_full")
    res = fsv.solve(fs)
    b = _block(fs, "T-103")
    assert b.column_active is False and b.eq_type == "Tower (column shell)"
    assert len(res.mass_balance_errors) == 0
