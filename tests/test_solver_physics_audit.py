"""Physical regressions: conservation, finite states and honest status."""
import math

import pytest

from flowsheet_model import Block, Stream, Flowsheet, SEC_PER_YEAR, TM_TO_KG
import flowsheet_solver as solver
from flowsheet_consistency_audit import AuditFinding, AuditReport, audit_flowsheet
from stream_enthalpy import stream_enthalpy_kW


def simple_flowsheet():
    fs = Flowsheet()
    fs.blocks = {i: Block(id=i, name=f"B-{i}", eq_type="Vessel - vertical", S=1)
                 for i in range(1, 5)}
    return fs


def stream(sid, src, dst, mass, component="water", **kwargs):
    return Stream(id=sid, name=f"S-{sid}", src=src, dst=dst, mass_flow=mass,
                  composition={component: 1.0}, main_component=component,
                  mass_flow_locked=True, composition_locked=True,
                  temperature_locked=True, **kwargs)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_nonphysical_feed_is_rejected_before_iteration(value):
    fs = simple_flowsheet()
    fs.streams = {1: stream(1, 1, 2, value), 2: stream(2, 2, 3, 100)}
    result = solver.solve(fs)
    assert not result.success
    assert result.overall_status == "error"
    assert result.mass_balance_errors
    assert result.iterations == 0


def test_zero_branch_cannot_hide_mass_creation():
    fs = simple_flowsheet()
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 2, 3, 150),
                  3: stream(3, 2, 4, 0)}
    assert solver._check_mass_balance(fs)


def test_closed_splitter_branch_is_resolved_not_a_solver_failure():
    fs = simple_flowsheet()
    fs.blocks[2].splitter_active = True
    fs.blocks[2].splitter_fractions = [1.0, 0.0]
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 2, 3, 0),
                  3: stream(3, 2, 4, 0)}
    for sid in (2, 3):
        fs.streams[sid].mass_flow_locked = False
    solver.solve_splitters(fs)
    assert fs.streams[2].mass_flow == 100
    assert solver._zero_flow_is_resolved(fs, fs.streams[3])
    assert not solver._check_mass_balance(fs)


def test_empty_separator_output_discards_previous_solution():
    outlet = stream(1, 1, 2, 75)
    outlet.mass_flow_locked = outlet.composition_locked = False
    solver._write_output(outlet, 0, {})
    assert outlet.mass_flow == 0
    assert outlet.composition == {}
    assert outlet.main_component == ""


def test_multi_inlet_splitter_conserves_each_species():
    fs = simple_flowsheet()
    fs.blocks[2].splitter_active = True
    fs.blocks[2].splitter_fractions = [0.25, 0.75]
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 4, 2, 300, "ethanol"),
                  3: stream(3, 2, 3, 0), 4: stream(4, 2, 4, 0)}
    for sid in (3, 4):
        fs.streams[sid].mass_flow_locked = False
        fs.streams[sid].composition_locked = False
    solver.solve_splitters(fs)
    for sid in (3, 4):
        assert fs.streams[sid].composition == {"water": 0.25, "ethanol": 0.75}
    assert sum(fs.streams[sid].mass_flow * fs.streams[sid].composition["water"]
               for sid in (3, 4)) == pytest.approx(100)


def test_locked_hx_circuit_does_not_borrow_mass_from_other_side():
    fs = simple_flowsheet()
    fs.blocks[2].eq_type = "Heat exchanger - shell & tube"
    fs.streams = {
        1: stream(1, 1, 2, 100, dst_port="tube_in"),
        2: stream(2, 4, 2, 200, dst_port="shell_in"),
        3: stream(3, 2, 3, 80, src_port="tube_out"),
        4: stream(4, 2, 4, 0, src_port="shell_out"),
    }
    fs.streams[4].mass_flow_locked = False
    solver._solve_mass_iteration(fs)
    assert fs.streams[4].mass_flow == 200
    assert any("tube" in error for error in solver._check_mass_balance(fs))


def test_downstream_spec_cannot_rewrite_separator_result():
    fs = simple_flowsheet()
    fs.blocks[1].component_recovery_active = True
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 2, 3, 150)}
    fs.streams[1].mass_flow_locked = False
    solver._solve_mass_iteration(fs)
    assert fs.streams[1].mass_flow == 100
    assert solver._check_mass_balance(fs)


def test_energy_connection_never_receives_material_mass():
    fs = simple_flowsheet()
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 2, 3, 0),
                  3: Stream(id=3, name="power", src=4, dst=2,
                            stream_kind="energy", energy_kW=100)}
    fs.streams[2].mass_flow_locked = False
    solver._solve_mass_iteration(fs)
    assert fs.streams[2].mass_flow == 100
    assert fs.streams[3].mass_flow == 0


def test_mixer_solves_enthalpy_instead_of_temperature_average():
    fs = simple_flowsheet()
    mass = SEC_PER_YEAR / TM_TO_KG
    fs.streams = {
        1: stream(1, 1, 2, mass, temperature=100, phase="vapor"),
        2: stream(2, 4, 2, mass, temperature=600, phase="vapor"),
        3: stream(3, 2, 3, 2 * mass, temperature=25, phase="vapor"),
    }
    fs.streams[3].temperature_locked = False
    solver._solve_energy_iteration(fs, tol_T=1e-8)
    hi = stream_enthalpy_kW(fs.streams[1]) + stream_enthalpy_kW(fs.streams[2])
    assert stream_enthalpy_kW(fs.streams[3]) == pytest.approx(hi, rel=1e-8)
    assert 100 < fs.streams[3].temperature < 600


def test_unconverged_recycle_and_consistency_errors_are_not_success():
    fs = simple_flowsheet()
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 2, 3, 100)}
    result = solver.SolverResult(recycle_solutions=[
        solver.RecycleSolution(cycle_blocks=["B-2"], converged=False)])
    solver._compute_status_per_item(fs, result)
    assert result.overall_status == "error"
    assert result.block_status[2] == "error"
    finding = AuditFinding("component_balance_strict", "error", "block", "B-2", "mass created")
    result = solver.SolverResult(consistency_errors=[finding.message],
                                 audit_report=AuditReport(findings=[finding]))
    solver._compute_status_per_item(fs, result)
    assert result.overall_status == "error"
    assert result.block_status[2] == "error"


def test_reactor_does_not_exempt_downstream_component_balance():
    fs = simple_flowsheet()
    fs.blocks[1].heat_of_reaction = -100
    fs.streams = {1: stream(1, 1, 2, 100), 2: stream(2, 2, 3, 100, "ethanol")}
    report = audit_flowsheet(fs)
    assert any(f.target_name == "B-2" and f.severity == "error"
               for f in report.findings)


def test_heat_exchanger_cannot_pass_without_enthalpy():
    fs = simple_flowsheet()
    fs.blocks[2].eq_type = "Heat exchanger - shell & tube"
    fs.streams = {1: stream(1, 1, 2, 100, "uncharacterized_material"),
                  2: stream(2, 2, 3, 100, "uncharacterized_material")}
    report = audit_flowsheet(fs)
    assert any(f.category == "thermo_missing" and f.target_name == "B-2"
               and f.severity == "error" for f in report.findings)


def test_cross_exchanger_keeps_compositions_on_their_own_sides():
    fs = simple_flowsheet()
    fs.blocks[2].eq_type = "Heat exchanger - shell & tube"
    fs.streams = {
        1: stream(1, 1, 2, 100, "water", dst_port="tube_in"),
        2: stream(2, 4, 2, 100, "ethanol", dst_port="shell_in"),
        3: stream(3, 2, 3, 100, src_port="tube_out"),
        4: stream(4, 2, 4, 100, src_port="shell_out"),
    }
    for sid in (3, 4):
        fs.streams[sid].composition_locked = False
    solver.auto_propagate_compositions(fs)
    assert fs.streams[3].composition == {"water": 1.0}
    assert fs.streams[4].composition == {"ethanol": 1.0}


def test_utility_role_does_not_remove_material_from_a_real_mixer():
    fs = simple_flowsheet()
    fs.streams = {1: stream(1, 1, 2, 100, "water", role="utility"),
                  2: stream(2, 4, 2, 300, "ethanol"),
                  3: stream(3, 2, 3, 400)}
    fs.streams[3].composition_locked = False
    solver.auto_propagate_compositions(fs)
    assert fs.streams[3].composition == {"water": 0.25, "ethanol": 0.75}


def test_machine_discharge_pressure_never_becomes_its_suction_pressure():
    fs = simple_flowsheet()
    fs.blocks[2].eq_type = "Compressor - centrifugal"
    fs.blocks[2].P_op_bar = 20
    fs.streams = {1: stream(1, 1, 2, 100, "nitrogen", pressure_bar=1.01325),
                  2: stream(2, 2, 3, 100, "nitrogen", pressure_bar=1.01325)}
    solver._seed_reactor_pressures(fs)
    assert fs.streams[1].pressure_bar == 1.01325
    assert fs.streams[2].pressure_bar == 20


def test_recycle_trial_defers_downstream_column_until_final_forward_pass(monkeypatch):
    import distillation_fug

    fs = simple_flowsheet()
    for bid in (2, 4):
        fs.blocks[bid].column_active = True
        fs.blocks[bid].column_LK = "ethanol"
        fs.blocks[bid].column_HK = "water"
    fs.streams = {
        1: stream(1, 1, 2, 100),
        2: stream(2, 2, 3, 80, src_port="vapor"),
        3: stream(3, 2, 0, 20, src_port="liq"),
        4: stream(4, 3, 4, 80),
        5: stream(5, 4, 0, 40, src_port="vapor"),
        6: stream(6, 4, 0, 40, src_port="liq"),
    }
    for st in fs.streams.values():
        st.composition = {"ethanol": 0.5, "water": 0.5}
    calls = []
    def record_design(**kwargs):
        calls.append(kwargs["F"])
        return None
    monkeypatch.setattr(distillation_fug, "design_column", record_design)
    monkeypatch.setattr(solver, "_ACTIVE_SCC_BLOCK_IDS", {3})
    solver.solve_columns(fs)
    assert calls == [100]  # The upstream column still supplies the loop.
    calls.clear()
    monkeypatch.setattr(solver, "_ACTIVE_SCC_BLOCK_IDS", set())
    solver.solve_columns(fs)
    assert calls == [100, 80]  # Final propagation also solves the product column.


@pytest.mark.parametrize("pressure", [1.5, 3.0])
def test_column_saturated_bottom_uses_actual_outlet_pressure(monkeypatch, pressure):
    import distillation_fug
    import nrtl

    fs = simple_flowsheet()
    column = fs.blocks[2]
    column.column_active = True
    column.column_LK, column.column_HK = "ethanol", "water"
    feed = stream(1, 1, 2, 1000, pressure_bar=pressure, phase="liquid")
    feed.composition = {"ethanol": 0.5, "water": 0.5}
    feed.temperature = 85
    dist = stream(2, 2, 3, 0, src_port="destilado", pressure_bar=pressure)
    bottom = stream(3, 2, 4, 0, src_port="bottom", pressure_bar=pressure)
    for outlet in (dist, bottom):
        outlet.mass_flow_locked = outlet.composition_locked = outlet.temperature_locked = False
        outlet.pressure_locked = True
    fs.streams = {1: feed, 2: dist, 3: bottom}
    original_design = distillation_fug.design_column
    used_pressure = []
    def record_pressure(**kwargs):
        used_pressure.append(kwargs["P_bar"])
        return original_design(**kwargs)
    monkeypatch.setattr(distillation_fug, "design_column", record_pressure)
    solver.solve_columns(fs)
    assert used_pressure == [pressure]
    assert bottom.mass_flow > 0
    mol = solver._mass_to_mol(bottom.composition)
    expected, _ = nrtl.bubble_point(list(mol), list(mol.values()), bottom.pressure_bar)
    assert bottom.temperature + 273.15 == pytest.approx(expected, abs=1e-7)
    assert bottom.pressure_bar == pressure


def test_final_display_quality_tracks_explicit_species_phase_allocation():
    fs = simple_flowsheet()
    allocation = {"water": 0.0, "nitrogen": 1.0}
    feed = stream(1, 1, 2, 100, phase="two_phase", vapor_fraction=0.9)
    feed.composition = {"water": 0.7, "nitrogen": 0.3}
    feed.component_vapor_fractions = dict(allocation)
    outlet = stream(2, 2, 3, 0, phase="two_phase", vapor_fraction=0.9)
    outlet.mass_flow_locked = outlet.composition_locked = False
    outlet.component_vapor_fractions = dict(allocation)
    fs.streams = {1: feed, 2: outlet}
    result = solver.solve(fs)
    assert result.success
    assert feed.vapor_fraction == pytest.approx(0.3)
    assert outlet.vapor_fraction == pytest.approx(0.3)
    assert outlet.component_vapor_fractions == allocation
