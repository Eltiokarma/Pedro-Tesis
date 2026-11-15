"""Independent mass/component tests for specified-performance separators."""
import math
import pytest
from flowsheet_model import Block, Stream, Flowsheet
from component_recovery import component_recovery_outputs, solve_component_recoveries


def fixture():
    b = Block(1, "Absorber", "Tower (column shell)", 1,
              component_recovery_active=True,
              component_recoveries={"gas": {"methane": .99, "co2": .02}},
              component_recovery_default_port="liquid")
    ins = [Stream(2, "feed", 0, 1, mass_flow=100,
                  composition={"methane": .8, "co2": .15, "unlisted_tracer": .05})]
    outs = [Stream(3, "gas", 1, 0, src_port="gas"),
            Stream(4, "liquid", 1, 0, src_port="liquid")]
    return b, ins, outs


def test_component_conservation_and_feed_scaling():
    b, ins, outs = fixture()
    a = component_recovery_outputs(b, ins, outs)
    assert a[3] == {"methane": pytest.approx(79.2), "co2": pytest.approx(.3)}
    for c, f in ins[0].composition.items():
        assert sum(v.get(c, 0) for v in a.values()) == pytest.approx(100 * f)
    ins[0].mass_flow *= 2
    doubled = component_recovery_outputs(b, ins, outs)
    for sid, comp in a.items():
        for c, m in comp.items():
            assert doubled[sid][c] == pytest.approx(2 * m)


@pytest.mark.parametrize("bad", [-.1, 1.1, math.nan, math.inf])
def test_invalid_recovery_rejected(bad):
    b, ins, outs = fixture()
    b.component_recoveries["gas"]["methane"] = bad
    with pytest.raises(ValueError):
        component_recovery_outputs(b, ins, outs)


def test_missing_composition_not_normalized_away():
    b, ins, outs = fixture()
    ins[0].composition = {"methane": .8}
    with pytest.raises(ValueError, match="sum to 1"):
        component_recovery_outputs(b, ins, outs)


def test_unknown_spec_rejected_but_feed_tracer_conserved():
    b, ins, outs = fixture()
    b.component_recoveries["gas"]["misspelled_methane"] = .9
    with pytest.raises(ValueError, match="unknown component"):
        component_recovery_outputs(b, ins, outs)


def test_zero_feed_clears_stale_outputs_and_roundtrip_preserves_specs():
    b, ins, outs = fixture()
    fs = Flowsheet()
    fs.blocks[b.id] = b
    fs.streams = {s.id: s for s in ins + outs}
    fs = Flowsheet.from_dict(fs.to_dict())
    assert not any(m.startswith("✗") for m in solve_component_recoveries(fs))
    fs.streams[2].mass_flow = 0
    solve_component_recoveries(fs)
    assert all(fs.streams[i].mass_flow == 0 and fs.streams[i].composition == {}
               for i in [3, 4])


def test_complete_split_does_not_create_roundoff_trace_in_default_phase():
    b, ins, outs = fixture()
    outs.append(Stream(5, "second gas", 1, 0, src_port="gas2"))
    b.component_recoveries = {"gas": {"methane": .2}, "gas2": {"methane": .8}}
    ins[0].mass_flow = 12345.6789
    result = component_recovery_outputs(b, ins, outs)
    assert "methane" not in result[4]
    assert result[3]["methane"] + result[5]["methane"] == pytest.approx(
        ins[0].mass_flow * .8, rel=1e-14)
