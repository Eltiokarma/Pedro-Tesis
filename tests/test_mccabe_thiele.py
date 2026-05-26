"""Tests del motor McCabe-Thiele (recomendación de columna binaria)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_library as el
import mccabe_thiele as mt


def _build(example_name):
    class _FE:
        def __init__(self):
            self.fs = fm.Flowsheet()
            self.labor_workers = 0
        _add_example_block  = el.ExampleBuilder._add_example_block
        _add_example_stream = el.ExampleBuilder._add_example_stream
        _add_example_extra  = el.ExampleBuilder._add_example_extra
        _set_example_labor  = el.ExampleBuilder._set_example_labor
        _set_block_duty     = el.ExampleBuilder._set_block_duty
    fake = _FE()
    getattr(el.ExampleBuilder, example_name)(fake)
    fsv.solve(fake.fs)
    return fake.fs


def test_design_benzene_toluene():
    d = mt.design('benzene', 'toluene', z_F=0.5, x_D=0.95, x_B=0.05,
                  R=1.5, q=1.0)
    assert d is not None
    assert 6 <= d['N_stages'] <= 30, f"N fuera de rango: {d['N_stages']}"
    assert 1 <= d['feed_stage'] <= d['N_stages']
    assert d['R_min'] is not None and d['R'] > d['R_min']
    # la escalera debe descender monótona en x desde x_D hasta ≤ x_B
    xs = [p[0] for p in d['stages']]
    assert xs[0] == d['x_D'] and xs[-1] <= d['x_B'] + 1e-6


def test_R_factor_path():
    """Sin R explícito usa R = R_factor · R_min."""
    d = mt.design('benzene', 'toluene', z_F=0.5, x_D=0.95, x_B=0.05,
                  R=None, R_factor=1.3, q=1.0)
    assert d is not None
    assert abs(d['R'] - 1.3 * d['R_min']) < 1e-6


def test_invalid_specs_return_none():
    # x_B > z_F (incoherente)
    assert mt.design('benzene', 'toluene', z_F=0.5, x_D=0.95, x_B=0.6,
                     R=1.5) is None
    # componente sin VLE
    assert mt.design('benzene', 'no_existe_xyz', z_F=0.5, x_D=0.95,
                     x_B=0.05, R=1.5) is None


def test_design_from_block_columns():
    """Los ejemplos con column_active deben recomendar un diagrama."""
    found = 0
    for ex in ('_example_distillation', '_example_ethanol',
               '_example_reactor_flash_column'):
        fs = _build(ex)
        cols = [b for b in fs.blocks.values()
                if getattr(b, 'column_active', False)]
        for b in cols:
            d = mt.design_from_block(b, fs)
            assert d is not None, f"{ex}/{b.name}: sin diagrama"
            assert d['N_stages'] >= 2
            assert 0.0 < d['z_F'] < 1.0
            found += 1
    assert found >= 3


def test_sizing_from_block():
    """design_from_block debe adjuntar 'sizing' con etapas reales (E_o) y
    diámetro (Souders-Brown) físicamente razonables."""
    fs = _build('_example_distillation')
    b = next(x for x in fs.blocks.values() if getattr(x, 'column_active', False))
    d = mt.design_from_block(b, fs)
    sz = d.get('sizing')
    assert sz is not None
    assert sz['alpha_avg'] is not None and sz['alpha_avg'] > 1.0   # LK más volátil
    assert 0.1 <= sz['E_o'] <= 0.95
    assert sz['N_real'] >= d['N_stages']                          # reales ≥ teóricas
    assert sz['diameter_m'] is not None and 0.05 < sz['diameter_m'] < 20.0


def test_oconnell_monotonic():
    """E_o decrece al subir α·μ (O'Connell)."""
    e1 = mt.oconnell_efficiency(2.0, 0.3)
    e2 = mt.oconnell_efficiency(5.0, 0.5)
    assert e1 is not None and e2 is not None and e1 > e2


def test_packed_design():
    """Alternativa de torre de relleno: NTU ≈ N teóricas (λ≈1) y altura
    Z = N·HETP positiva."""
    d = mt.design('benzene', 'toluene', z_F=0.5, x_D=0.95, x_B=0.05, R=1.5)
    pk = mt.packed_design(d, packing='pall')
    assert pk['NTU'] > 0
    assert pk['NTU_rect'] > 0 and pk['NTU_strip'] > 0
    # NTU del mismo orden que las etapas teóricas
    assert 0.5 * d['N_stages'] <= pk['NTU'] <= 2.0 * d['N_stages']
    assert abs(pk['Z_packed_m'] - d['N_stages'] * pk['HETP_m']) < 1e-6


def test_packing_attached_from_block():
    fs = _build('_example_distillation')
    b = next(x for x in fs.blocks.values() if getattr(x, 'column_active', False))
    d = mt.design_from_block(b, fs)
    assert d.get('packing') and d['packing']['Z_packed_m'] > 0


def test_matplotlib_render_smoke():
    """El path de dibujo (matplotlib) no debe romper con un diseño real."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
    except Exception:
        return                              # sin matplotlib → skip
    d = mt.design('benzene', 'toluene', z_F=0.5, x_D=0.95, x_B=0.05, R=1.5)
    fig = Figure()
    ax = fig.add_subplot(111)
    xs, ys = d['equilibrium']
    ax.plot([0, 1], [0, 1])
    ax.plot(xs, ys)
    ax.plot([p[0] for p in d['stages']], [p[1] for p in d['stages']])
    fig.canvas.draw() if hasattr(fig, "canvas") else None  # no debe lanzar


if __name__ == '__main__':
    test_design_benzene_toluene()
    test_R_factor_path()
    test_invalid_specs_return_none()
    test_design_from_block_columns()
    test_matplotlib_render_smoke()
    print("McCabe-Thiele: OK")
