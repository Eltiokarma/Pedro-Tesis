"""Reaction evidence uses polymer repeat units, preserving bulk properties."""
import pytest

import inspector_evidence as evidence
import components
import reactions_db
import thermo_db
from flowsheet_model import Block, Flowsheet, Stream, SEC_PER_YEAR, TM_TO_KG


def test_r027_inspector_counts_feed_and_product_on_repeat_unit_basis():
    bulk = thermo_db.get("polyethylene") or components.get("polyethylene")
    bulk_mw = bulk.mw
    repeat_mw = reactions_db.component_for_mass("polyethylene").mw
    assert bulk_mw > repeat_mw * 100
    # One kmol/h each of monomer and already-present polymer repeat units.
    # Polymer currently lives in the legacy catalog: the old UI omitted it.
    # Falling back to its bulk-chain MW would instead undercount about 1000x.
    annual_flow = 2 * repeat_mw * SEC_PER_YEAR / (3600 * TM_TO_KG)
    block = Block(1, "R-PE", "Reactor - autoclave", 1,
                  reactions=["R027"], reactor_mode="stoich",
                  reactor_conversion=.25)
    feed = Stream(2, "mixed feed", 0, 1, mass_flow=annual_flow,
                  composition={"ethylene": .5, "polyethylene": .5})
    fs = Flowsheet()
    fs.blocks = {1: block}
    fs.streams = {2: feed}
    result = evidence.stoich_table(block, fs)
    assert result is not None
    rows = {r["name"]: r for r in result["rows"]}
    assert rows["polyethylene"]["F0_kmol_h"] == pytest.approx(1)
    assert rows["ethylene"]["F0_kmol_h"] == pytest.approx(1)
    assert rows["polyethylene"]["F_X_kmol_h"] == pytest.approx(1.25)
    assert rows["ethylene"]["F_X_kmol_h"] == pytest.approx(.75)
    assert "unidades repetitivas C2H4" in evidence.stoich_table_text(block, fs)
    assert "unidades repetitivas C2H4" in evidence.stoich_book_spec(block, fs)["note"]
    assert bulk.mw == bulk_mw
