"""Frente A — auditor unificado de consistencia.

Verifica los 4 detectores (phase / component_balance / pseudo /
redundant_lock) y su integración en SolverResult.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_library as el
from flowsheet_consistency_audit import audit_flowsheet


def _build_fake_editor():
    class _FE:
        def __init__(self):
            self.fs = fm.Flowsheet()
            self.labor_workers = 0
        _add_example_block  = el.ExampleBuilder._add_example_block
        _add_example_stream = el.ExampleBuilder._add_example_stream
        _add_example_extra  = el.ExampleBuilder._add_example_extra
        _set_example_labor  = el.ExampleBuilder._set_example_labor
        _set_block_duty     = el.ExampleBuilder._set_block_duty
    return _FE()


def test_ethanol_example_balance_issues():
    """El ejemplo etanol tiene composiciones que no cierran balance."""
    fake = _build_fake_editor()
    el.ExampleBuilder._example_ethanol(fake)
    res = fsv.solve(fake.fs)
    report = res.audit_report
    assert report is not None, "audit_report ausente"

    balance_findings = report.by_category('component_balance')
    assert len(balance_findings) > 0, \
        "Auditor no detectó las inconsistencias conocidas en _example_ethanol"
    print(f"  ✓ Etanol: {len(balance_findings)} hallazgos de balance "
          f"detectados")


def test_pseudo_components_detected():
    """Ejemplo biodiesel usa vegetable_oil/biodiesel/glycerin → pseudo."""
    fake = _build_fake_editor()
    el.ExampleBuilder._example_biodiesel(fake)
    res = fsv.solve(fake.fs)
    report = res.audit_report

    pseudo = report.by_category('pseudo')
    pseudo_names = {f.data.get('component') for f in pseudo}
    expected = {'vegetable_oil', 'biodiesel', 'glycerin'}
    overlap = pseudo_names & expected
    assert overlap, \
        f"No detectó pseudo-componentes industriales. Vio: {pseudo_names}"
    print(f"  ✓ Biodiesel: {len(pseudo)} hallazgos de pseudo-comps")


def test_food_pseudo_is_info_not_warning():
    """Sucrose y glucose son food pseudo → severity='info', no 'warning'."""
    fake = _build_fake_editor()
    el.ExampleBuilder._example_sugar_mill(fake)
    res = fsv.solve(fake.fs)
    report = res.audit_report

    food_findings = [f for f in report.by_category('pseudo')
                     if f.data.get('component') in ('sucrose', 'glucose')]
    assert food_findings, "No vio sucrose/glucose en sugar_mill"
    for f in food_findings:
        assert f.severity == 'info', \
            f"Food pseudo '{f.data.get('component')}' debe ser INFO, " \
            f"no {f.severity}"
    print(f"  ✓ Sugar mill: {len(food_findings)} food pseudo-comps "
          f"clasificados como INFO")


def test_phase_inconsistency_detected():
    """Stream con phase declarada incompatible con T/P."""
    fs = fm.Flowsheet()
    from flowsheet_model import Block, Stream
    tk1 = Block(id=1, name="TK1", eq_type="Storage tank — cone roof",
                S=100, n=1, x=0, y=0)
    tk2 = Block(id=2, name="TK2", eq_type="Storage tank — cone roof",
                S=100, n=1, x=200, y=0)
    fs.blocks = {1: tk1, 2: tk2}
    # Agua pura a 50°C, 1 atm, declarada vapor → debería ser liquid.
    s = Stream(id=10, name="S-bad", src=1, dst=2, mass_flow=100,
               temperature=50, phase="vapor", composition={"water": 1.0},
               main_component="water")
    s.pressure_bar = 1.013
    s.mass_flow_locked = True
    s.composition_locked = True
    s.phase_locked = True
    fs.streams = {10: s}

    report = audit_flowsheet(fs)
    phase_findings = report.by_category('phase')
    assert len(phase_findings) > 0, \
        "No detectó phase inconsistency (water 50°C declarado vapor)"
    assert phase_findings[0].severity in ('warning', 'error')
    print("  ✓ Phase inconsistency: water 50°C declarado vapor → reportado")


def test_audit_in_solver_result():
    """audit_report debe estar en SolverResult tras solve()."""
    fake = _build_fake_editor()
    el.ExampleBuilder._example_reactor_flash_column(fake)
    res = fsv.solve(fake.fs)
    assert res.audit_report is not None
    print(f"  ✓ audit_report integrado en SolverResult "
          f"({len(res.audit_report.findings)} findings totales)")


if __name__ == '__main__':
    print("=" * 70)
    print("Tests del auditor de consistencia (Frente A)")
    print("=" * 70)
    test_ethanol_example_balance_issues()
    test_pseudo_components_detected()
    test_food_pseudo_is_info_not_warning()
    test_phase_inconsistency_detected()
    test_audit_in_solver_result()
    print("\nTodos los tests pasan ✓")
