"""Frente B — propagación de T, P y phase en los solvers de unit ops
automáticas (solve_columns / solve_flashes / solve_equilibrium_reactors).

Verifica que tras el solve los outputs quedan con T/P/phase coherentes con
la termo, respetando los locks declarados por el builder/user.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_library as el


class _FE:
    """Editor falso headless: presta los 5 helpers de ExampleBuilder."""
    def __init__(self):
        self.fs = fm.Flowsheet()
        self.labor_workers = 0
    _add_example_block  = el.ExampleBuilder._add_example_block
    _add_example_stream = el.ExampleBuilder._add_example_stream
    _add_example_extra  = el.ExampleBuilder._add_example_extra
    _set_example_labor  = el.ExampleBuilder._set_example_labor
    _set_block_duty     = el.ExampleBuilder._set_block_duty


def test_column_propagates_T():
    """T, P y phase deben quedar coherentes tras solve_columns."""
    fake = _FE()
    el.ExampleBuilder._example_reactor_flash_column(fake)
    fsv.solve(fake.fs)

    dist = next(s for s in fake.fs.streams.values() if s.name == "S-etanol")
    bot  = next(s for s in fake.fs.streams.values() if s.name == "S-agua")

    # T del distillate (azeo eth-water, ~78°C) y del bottom (~100°C).
    # Ambas están declaradas (locked) en el builder → deben mantenerse.
    assert 70 < dist.temperature < 90, \
        f"T distillate fuera de rango: {dist.temperature}°C"
    assert 95 < bot.temperature < 105, \
        f"T bottom fuera de rango: {bot.temperature}°C"
    # P propagada: bottom = P_col + 0.1 bar (gradiente de la columna).
    assert dist.pressure_bar > 0, "P distillate no propagada"
    assert abs(bot.pressure_bar - 1.113) < 0.01, \
        f"P bottom {bot.pressure_bar} ≠ P_col+0.1"
    # Phase inferida: el bottom siempre sale líquido saturado.
    assert bot.phase == "liquid", f"bottom phase {bot.phase} != liquid"
    print(f"  ✓ Column: T_top={dist.temperature:.1f}°C, "
          f"T_bot={bot.temperature:.1f}°C, P_bot={bot.pressure_bar:.3f}bar, "
          f"phase_bot={bot.phase}")


def test_flash_reports_single_phase():
    """Un flash subenfriado (todo líquido) debe reportar single-phase."""
    fake = _FE()
    tk   = fake._add_example_block("TK", "Storage tank — cone roof", 100.0, 0, 0)
    v    = fake._add_example_block("V-101", "Vessel — vertical", 10.0, 200, 0)
    tk_v = fake._add_example_block("TK-V", "Storage tank — cone roof", 10.0, 400, -100)
    tk_l = fake._add_example_block("TK-L", "Storage tank — cone roof", 10.0, 400, 100)
    # Flash a 60°C, 1 atm: por debajo del bubble point de la mezcla
    # agua/etanol → single-phase liquid.
    fake.fs.blocks[v].flash_active = True
    fake.fs.blocks[v].flash_T_K = 333.15   # 60°C
    fake.fs.blocks[v].flash_P_bar = 1.013

    fake._add_example_stream(tk, v, "S-feed", 1000, role="feed", T=55,
                             src_port="salida", dst_port="alimentacion",
                             composition={"water": 0.9, "ethanol": 0.1},
                             phase="liquid")
    fake._add_example_stream(v, tk_v, "S-vap", src_port="vapor",
                             dst_port="entrada")
    fake._add_example_stream(v, tk_l, "S-liq", src_port="liquido",
                             dst_port="entrada")

    res = fsv.solve(fake.fs)
    has_warn = any("single-phase" in w
                   for w in res.energy_warnings + res.energy_balance_errors)
    assert has_warn, \
        f"No reportó single-phase. Warnings: {res.energy_warnings}"
    print("  ✓ Flash single-phase reportado correctamente")


def test_reactor_propagates_P():
    """Reactor con reactions debe propagar P_op_bar a sus outputs."""
    fake = _FE()
    el.ExampleBuilder._example_smr_equilibrium(fake)
    fsv.solve(fake.fs)

    r101 = next(b for b in fake.fs.blocks.values() if b.name == "R-101")
    out = next(s for s in fake.fs.streams.values()
               if s.src == r101.id and s.dst > 0)
    assert abs(out.pressure_bar - r101.P_op_bar) < 0.01, \
        f"P no propagada: stream={out.pressure_bar}, reactor={r101.P_op_bar}"
    print(f"  ✓ Reactor P propagation: {out.pressure_bar:.2f}bar = "
          f"P_op={r101.P_op_bar}bar")


if __name__ == '__main__':
    print("=" * 70)
    print("Tests de propagación T/P/phase (Frente B)")
    print("=" * 70)
    test_column_propagates_T()
    test_flash_reports_single_phase()
    test_reactor_propagates_P()
    print("\nTodos los tests pasan ✓")
