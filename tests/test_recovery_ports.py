"""Custom recovery outlets must have distinct, live PFD connection points."""
import copy
import os
from types import SimpleNamespace

import pytest

import equipment_ports as ep
import pfd_symbols as pfd
from examples_registry import load_example
from flowsheet_model import Block


def membrane():
    fs = load_example("chloralkali_hcl")
    block = next(b for b in fs.blocks.values() if b.name == "V-101-MEM")
    outlets = [s.src_port for s in fs.streams.values() if s.src == block.id]
    assert len(outlets) == 6
    return fs, block, outlets


def test_six_recovery_outlets_are_distinct_and_catalog_is_unchanged():
    _, block, outlets = membrane()
    before = copy.deepcopy(ep.EQUIPMENT_PORTS)
    static = dict(ep.get_ports(block.eq_type))
    ports = ep.get_block_ports(block)
    assert all(ports[name][0] == "right" for name in outlets)
    right = [frac for side, frac in ports.values() if side == "right"]
    assert len(right) == len(set(right))
    assert all(0 < frac < 1 for frac in right)
    assert all(ep.get_block_port_kind(block, name) == "process_out" for name in outlets)
    ports["extra"] = ("left", .5)
    assert ep.EQUIPMENT_PORTS == before
    assert ep.get_ports(block.eq_type) == static
    plain = Block(100, "Other separator", block.eq_type, 1)
    assert ep.get_block_ports(plain) == static


def test_pfd_geometry_uses_block_specs_only_when_requested():
    _, block, outlets = membrane()
    static = pfd.port_coords(block.eq_type, 180, 140)
    dynamic = pfd.port_coords(block.eq_type, 180, 140, block=block)
    assert len({dynamic[name] for name in outlets}) == 6
    assert all(dynamic[name][0] == 180 for name in outlets)
    assert pfd.port_coords(block.eq_type, 180, 140) == static
    assert pfd.port_coords(block.eq_type, 180, 140, block=None) == static


def test_lumped_yield_recovery_ports_are_supported():
    block = Block(1, "Pseudo yield", "Vessel - vertical", 1,
                  lumped_yield_active=True,
                  component_recoveries={"light_cut": {}, "heavy_cut": {}},
                  component_recovery_default_port="coke")
    ports = ep.get_block_ports(block)
    assert all(name in ports for name in ("light_cut", "heavy_cut", "coke"))
    block.lumped_yield_active = False
    assert ep.get_block_ports(block) == ep.get_ports(block.eq_type)


@pytest.mark.parametrize("eq_type", ["Cooling tower — induced draft",
                                    "Cooling tower — natural draft"])
def test_cooling_tower_air_has_a_distinct_process_inlet(eq_type):
    ports = ep.get_ports(eq_type)
    assert ports["aire"] == ("left", .8)
    assert ports["aire"] != ports["makeup"]
    assert ep.get_port_kind(eq_type, "aire") == "process_in"
    assert pfd.port_coords(eq_type, 100, 200)["aire"] == (0, 160)


def test_qt_dots_tooltips_and_stream_anchors_use_the_same_recovery_geometry():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QGraphicsScene
    from flowsheet_qt import BlockItem, StreamItem

    app = QApplication.instance() or QApplication([])
    _, block, outlets = membrane()
    scene = QGraphicsScene()
    item = BlockItem(block)
    scene.addItem(item)
    scene.block_items = {block.id: item}
    # Exercise the real endpoint resolver both before attachment and with live
    # scene dots. It must resolve the declared name, never the first right port.
    detached = SimpleNamespace(scene=lambda: None, editor=None)
    attached = SimpleNamespace(scene=lambda: scene, editor=None)
    fallback_points, live_points = [], []
    for name in outlets:
        dot = item.port_items[name]
        assert dot.data(1) == "process_out"
        assert name in item.toolTip()
        side, x, y = StreamItem._resolve_port(detached, block, name, "right")
        assert side == "right"
        fallback_points.append((x, y))
        side, x, y = StreamItem._resolve_port(attached, block, name, "right")
        center = dot.sceneBoundingRect().center()
        assert (x, y) == pytest.approx((center.x(), center.y()))
        assert side == "right"
        live_points.append((x, y))
    assert len(set(fallback_points)) == len(set(live_points)) == 6
    scene.clear()
    app.processEvents()
