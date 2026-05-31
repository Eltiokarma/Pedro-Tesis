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
import examples_registry as reg


def _blk(fs, name, eq_type, S, x=0, y=0):
    """Crea un Block directamente (API de flowsheet_model).  S_locked sigue
    la convención de los ejemplos: el área declarada es spec, no se
    auto-dimensiona."""
    bid = fs.new_id()
    b = fm.Block(id=bid, name=name, eq_type=eq_type, S=S, n=1, x=x, y=y)
    b.S_locked = (S > 0)
    fs.blocks[bid] = b
    return bid


def _strm(fs, src, dst, name, mass_flow=0.0, role="internal",
          src_port="", dst_port="", T=25.0, composition=None, phase=""):
    """Crea un Stream directamente (API de flowsheet_model).  Los locks
    siguen la misma heurística declarativa que from_dict (mass>0, T≠25,
    comp/phase presentes ⇒ locked); feeds quedan lockeados, intermedios no."""
    sid = fs.new_id()
    s = fm.Stream(id=sid, name=name, src=src, dst=dst, mass_flow=mass_flow,
                  role=role, src_port=src_port, dst_port=dst_port,
                  temperature=T, phase=phase,
                  composition=dict(composition) if composition else {})
    s.mass_flow_locked   = (mass_flow > 0)
    s.temperature_locked = abs(T - 25.0) > 0.01
    s.composition_locked = bool(composition)
    s.phase_locked       = bool(phase)
    fs.streams[sid] = s
    return sid


def test_column_propagates_T():
    """T, P y phase deben quedar coherentes tras solve_columns."""
    fs = reg.load_example('rxn_flash_col')
    fsv.solve(fs)

    dist = next(s for s in fs.streams.values() if s.name == "S-etanol")
    bot  = next(s for s in fs.streams.values() if s.name == "S-agua")

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
    fs = fm.Flowsheet()
    tk   = _blk(fs, "TK", "Storage tank — cone roof", 100.0, 0, 0)
    v    = _blk(fs, "V-101", "Vessel — vertical", 10.0, 200, 0)
    tk_v = _blk(fs, "TK-V", "Storage tank — cone roof", 10.0, 400, -100)
    tk_l = _blk(fs, "TK-L", "Storage tank — cone roof", 10.0, 400, 100)
    # Flash a 60°C, 1 atm: por debajo del bubble point de la mezcla
    # agua/etanol → single-phase liquid.
    fs.blocks[v].flash_active = True
    fs.blocks[v].flash_T_K = 333.15   # 60°C
    fs.blocks[v].flash_P_bar = 1.013

    _strm(fs, tk, v, "S-feed", 1000, role="feed", T=55,
          src_port="salida", dst_port="alimentacion",
          composition={"water": 0.9, "ethanol": 0.1}, phase="liquid")
    _strm(fs, v, tk_v, "S-vap", src_port="vapor", dst_port="entrada")
    _strm(fs, v, tk_l, "S-liq", src_port="liquido", dst_port="entrada")

    res = fsv.solve(fs)
    has_warn = any("single-phase" in w
                   for w in res.energy_warnings + res.energy_balance_errors)
    assert has_warn, \
        f"No reportó single-phase. Warnings: {res.energy_warnings}"
    print("  ✓ Flash single-phase reportado correctamente")


def test_reactor_propagates_P():
    """Reactor con reactions debe propagar P_op_bar a sus outputs."""
    fs = reg.load_example('smr_eq')
    fsv.solve(fs)

    r101 = next(b for b in fs.blocks.values() if b.name == "R-101")
    out = next(s for s in fs.streams.values()
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
