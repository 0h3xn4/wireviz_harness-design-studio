# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-HARN-03. The routing tree a person draws (2.3.0, D-243, section 5.2 of the design of branching):
`core/branching.py` (the design names it `core/routing.py`, which holds the diagram's link routing).
Branch points, segments, an entered length that Generate keeps, a new leg, the join of two
harnesses on one device connector; each plan's refusals, its undo step through `History`, the
three integrity warnings of section 5.5, the refusal of a shield group across a branch (5.4), the
diagram mark `branch:<ID>` and the journal rows."""

import pytest

from harness_design_studio.core import branching, journal
from harness_design_studio.core.branching import (
    plan_add_branch_point,
    plan_add_leg,
    plan_add_segment,
    plan_delete_branch_point,
    plan_delete_segment,
    plan_join_harnesses,
    plan_rename_branch_point,
    plan_set_segment_length,
)
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.generate.lengths import wire_length
from harness_design_studio.core.integrity import check_integrity
from harness_design_studio.core.io import layout
from harness_design_studio.core.io.layout import model_hash, serialize
from harness_design_studio.core.links import plan_add_link, plan_create_harness
from harness_design_studio.core.manual_harness import (
    LOOSE,
    plan_cable_from_port,
    plan_plug_loose_end,
)
from harness_design_studio.core.model import Baseline, DiagramMark, Segment, evolve
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.vcs.snapshot import snapshot_for
from harness_design_studio.core.wires import plan_group_wires
from tests.helpers import pinout_project

ROUTING = ("segment_tree_split", "branch_point_unused", "shield_across_branch")


def labelled():
    """mini3 with labelled pins on four ports and no harness (`tests.helpers.pinout_project`)."""
    p = pinout_project()
    p.harnesses.clear()
    p.interfaces.clear()
    for cid, c in list(p.connectors.items()):
        p.connectors[cid] = evolve(c, pins=[evolve(x, interface_id=None) for x in c.pins])
    return p


def errors(p):
    return [i.render() for i in check_integrity(p) if i.severity == "error"]


def routing_warnings(p):
    return sorted((i.code, i.object_id) for i in check_integrity(p) if i.code in ROUTING)


def straight(p, history=None, pins=("1", "2")):
    """A drawn cable from OBC-J01 plugged into RW1-J02 (W001: W001-P1 to W001-P2), no segment."""
    h = history or History(p)
    made = plan_cable_from_port(p, "OBC-J01", pin_ids=list(pins))
    h.execute("cable", made.ops)
    pairs = [(x, x) for x in pins]
    h.execute("plug", plan_plug_loose_end(p, made.harness_id, made.loose_id, "RW1-J02", pairs))
    return made.harness_id


def released(p, hid):
    p.harnesses[hid] = evolve(p.harnesses[hid], status="released", version="1.0.0")


def generated_mini3():
    p = mini3()
    generate_project(p)
    return p


# ---- branch points ------------------------------------------------------------------------------


def test_a_branch_point_takes_the_next_free_id_of_the_naming_pattern_and_a_name():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, bid = plan_add_branch_point(p, hid)
    history.execute("branch", ops)
    assert bid == "W001-B1"
    assert [(b.id, b.name) for b in p.harnesses[hid].branch_points] == [("W001-B1", "Branch 1")]
    ops, second = plan_add_branch_point(p, hid, "  Y split ")
    history.execute("branch", ops)
    assert second == "W001-B2"
    assert p.harnesses[hid].branch_points[1].name == "Y split"
    assert errors(p) == []
    history.undo()
    history.undo()
    assert p.harnesses[hid].branch_points == []


def test_a_branch_point_name_is_unique_in_its_harness():
    p = labelled()
    hid = straight(p)
    ops, _bid = plan_add_branch_point(p, hid, "Branch Y")
    apply_ops(p, ops)
    with pytest.raises(EditError, match="has a branch point called 'branch y' already"):
        plan_add_branch_point(p, hid, "branch y")
    with pytest.raises(EditError, match="1 to 200 characters"):
        plan_add_branch_point(p, hid, "x" * 201)


def test_rename_a_branch_point():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, bid = plan_add_branch_point(p, hid)
    history.execute("branch", ops)
    ops, _other = plan_add_branch_point(p, hid, "Other")
    history.execute("branch", ops)
    history.execute("rename", plan_rename_branch_point(p, hid, bid, "Branch X"))
    assert p.harnesses[hid].branch_points[0].name == "Branch X"
    with pytest.raises(EditError, match="needs a name"):
        plan_rename_branch_point(p, hid, bid, "  ")
    with pytest.raises(EditError, match="called 'Other' already"):
        plan_rename_branch_point(p, hid, bid, "Other")
    with pytest.raises(EditError, match="'W001-B9' is not a branch point of W001"):
        plan_rename_branch_point(p, hid, "W001-B9", "Z")
    history.undo()
    assert p.harnesses[hid].branch_points[0].name == "Branch 1"


def test_deleting_a_branch_point_takes_its_segments_and_is_refused_on_a_wires_only_path():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, bid = plan_add_branch_point(p, hid)
    history.execute("branch", ops)
    ops, _sid = plan_add_segment(p, hid, "W001-P1", bid, 0.5)
    history.execute("segment", ops)
    # one segment: no wire runs through it yet, so it can go, and its segment with it
    unused = plan_delete_branch_point(p, hid, bid)
    apply_ops(p, apply_ops(p, unused))  # done and undone
    ops, _sid = plan_add_segment(p, hid, bid, "W001-P2", 0.7)
    history.execute("segment", ops)
    w = p.harnesses[hid].wires[0]
    assert wire_length(p.harnesses[hid], w) == pytest.approx(1.2)
    with pytest.raises(EditError, match="only path of the wires W001-001, W001-002"):
        plan_delete_branch_point(p, hid, bid)
    history.execute("segment", plan_delete_segment(p, hid, "W001-L2"))
    history.execute("delete", plan_delete_branch_point(p, hid, bid))
    h = p.harnesses[hid]
    assert (h.branch_points, h.segments) == ([], [])
    history.undo()
    assert [s.id for s in p.harnesses[hid].segments] == ["W001-L1"]


def test_the_plans_of_a_drawn_tree_refuse_a_generated_a_released_and_an_unknown_harness():
    p = generated_mini3()
    with pytest.raises(EditError, match="W002 is made by Generate"):
        plan_add_branch_point(p, "W002")
    with pytest.raises(EditError, match="made by Generate"):
        plan_add_segment(p, "W002", "W002-P1", "W002-P2")
    with pytest.raises(EditError, match="made by Generate"):
        plan_delete_segment(p, "W002", "W002-L1")
    with pytest.raises(EditError, match="Harness 'W404' does not exist"):
        plan_add_branch_point(p, "W404")
    q = labelled()
    hid = straight(q)
    released(q, hid)
    for call in (
        lambda: plan_add_branch_point(q, hid),
        lambda: plan_add_segment(q, hid, "W001-P1", "W001-P2"),
        lambda: plan_set_segment_length(q, hid, "W001-L1", 1.0),
        lambda: plan_add_leg(q, hid, "OBC-J01"),
    ):
        with pytest.raises(
            EditError, match="W001 is released \\(revision A\\); start a new revision"
        ):
            call()


def test_a_read_only_project_refuses():
    p = labelled()
    hid = straight(p)
    p.read_only = True
    with pytest.raises(EditError, match="read-only"):
        plan_add_branch_point(p, hid)


# ---- segments -----------------------------------------------------------------------------------


def test_a_segment_joins_two_nodes_of_the_harness_and_gives_the_wires_a_length():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, sid = plan_add_segment(p, hid, "W001-P1", "W001-P2", "1,5")
    history.execute("segment", ops)
    assert sid == "W001-L1"
    h = p.harnesses[hid]
    assert h.segments == [Segment(id=sid, from_node="W001-P1", to_node="W001-P2", length_m=1.5)]
    assert wire_length(h, h.wires[0]) == 1.5
    history.undo()
    assert p.harnesses[hid].segments == []


def test_a_segment_that_would_close_a_loop_is_refused():
    p = labelled()
    hid = straight(p)
    ops, bid = plan_add_branch_point(p, hid)
    apply_ops(p, ops)
    for a, b in (("W001-P1", bid), (bid, "W001-P2")):
        ops, _sid = plan_add_segment(p, hid, a, b)
        apply_ops(p, ops)
    before = model_hash(p)
    with pytest.raises(EditError, match="W001-P2 and W001-P1 are joined by segments already"):
        plan_add_segment(p, hid, "W001-P2", "W001-P1")
    with pytest.raises(EditError, match="joined by segments already"):
        plan_add_segment(p, hid, bid, "W001-P1")  # a second segment between the same two
    assert model_hash(p) == before


def test_a_segment_needs_two_different_known_nodes_and_a_length_in_metres():
    p = labelled()
    hid = straight(p)
    with pytest.raises(EditError, match="'OBC-J01' is not a connector or branch point of W001"):
        plan_add_segment(p, hid, "OBC-J01", "W001-P2")
    with pytest.raises(EditError, match="two different nodes"):
        plan_add_segment(p, hid, "W001-P1", "W001-P1")
    for bad in ("abc", -1, float("nan"), True):
        with pytest.raises(EditError, match="metres"):
            plan_add_segment(p, hid, "W001-P1", "W001-P2", bad)
    with pytest.raises(EditError, match="at most"):
        plan_add_segment(p, hid, "W001-P1", "W001-P2", 1e9)


def test_delete_a_segment():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, sid = plan_add_segment(p, hid, "W001-P1", "W001-P2", 2)
    history.execute("segment", ops)
    history.execute("delete", plan_delete_segment(p, hid, sid))
    assert p.harnesses[hid].segments == []
    with pytest.raises(EditError, match="'W001-L1' is not a segment of W001"):
        plan_delete_segment(p, hid, sid)
    history.undo()
    assert [s.length_m for s in p.harnesses[hid].segments] == [2.0]


def test_a_length_entered_on_a_drawn_harness_and_cleared():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, sid = plan_add_segment(p, hid, "W001-P1", "W001-P2")
    history.execute("segment", ops)
    history.execute("length", plan_set_segment_length(p, hid, sid, 0.8))
    assert p.harnesses[hid].segments[0].length_m == 0.8
    assert plan_set_segment_length(p, hid, sid, "0.8") == []  # nothing changes: no step
    history.execute("length", plan_set_segment_length(p, hid, sid, ""))
    assert p.harnesses[hid].segments[0].length_m is None
    history.undo()
    assert p.harnesses[hid].segments[0].length_m == 0.8
    with pytest.raises(EditError, match="not a segment"):
        plan_set_segment_length(p, hid, "W001-L7", 1)


def test_a_length_entered_on_a_generated_harness_is_kept_by_the_next_generate():
    p = generated_mini3()
    history = History(p)
    history.execute("length", plan_set_segment_length(p, "W002", "W002-L1", 3.25))
    generate_project(p)
    h = p.harnesses["W002"]
    assert [(s.id, s.length_m) for s in h.segments] == [("W002-L1", 3.25)]
    released(p, "W002")
    with pytest.raises(EditError, match="W002 is released"):
        plan_set_segment_length(p, "W002", "W002-L1", 1.0)


# ---- a new leg ----------------------------------------------------------------------------------


def test_a_leg_of_a_straight_cable_adds_a_loose_end_and_a_branch_point():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    before = dict(p.harnesses)
    leg = plan_add_leg(p, hid, "OBC-J01")
    history.execute("leg", leg.ops)
    h = p.harnesses[hid]
    assert (leg.loose_id, leg.wire_ids, leg.branch_id) == (
        "W001-P3",
        ("W001-003", "W001-004"),
        "W001-B1",
    )
    end = next(c for c in h.connectors if c.id == leg.loose_id)
    assert end.role == LOOSE and [x.signal for x in end.pins] == ["RX+", "RX-"]
    assert [
        (w.from_connector, w.from_pin, w.to_connector, w.to_pin, w.signal, w.manual)
        for w in h.wires[2:]
    ] == [  # fmt: skip
        ("W001-P1", "3", "W001-P3", "3", "RX+", True),
        ("W001-P1", "4", "W001-P3", "4", "RX-", True),
    ]
    assert [(s.id, s.from_node, s.to_node) for s in h.segments] == [
        ("W001-L1", "W001-P1", "W001-B1"),
        ("W001-L2", "W001-B1", "W001-P2"),
        ("W001-L3", "W001-B1", "W001-P3"),
    ]
    assert errors(p) == [] and routing_warnings(p) == []
    history.undo()
    assert p.harnesses == before


def test_a_leg_moves_the_drawn_leg_onto_the_branch_point_and_keeps_its_length():
    p = labelled()
    hid = straight(p)
    ops, _sid = plan_add_segment(p, hid, "W001-P1", "W001-P2", 1.2)
    apply_ops(p, ops)
    leg = plan_add_leg(p, hid, "W001-P1", pin_ids=["5"])  # the plug itself, a pin with no signal
    apply_ops(p, leg.ops)
    h = p.harnesses[hid]
    assert [(s.id, s.from_node, s.to_node, s.length_m) for s in h.segments] == [
        ("W001-L1", "W001-B1", "W001-P2", 1.2),
        ("W001-L2", "W001-P1", "W001-B1", None),
        ("W001-L3", "W001-B1", "W001-P3", None),
    ]
    assert wire_length(h, h.wires[0]) is None  # the piece to the branch point is to be measured
    assert errors(p) == []


def test_a_leg_from_a_plug_with_no_leg_in_a_harness_with_segments_is_one_segment():
    p = labelled()
    hid = straight(p)
    ops, bid = plan_add_branch_point(p, hid)
    apply_ops(p, ops)
    ops, _sid = plan_add_segment(p, hid, bid, "W001-P2")
    apply_ops(p, ops)
    leg = plan_add_leg(p, hid, "OBC-J01", pin_ids=["3"])
    apply_ops(p, leg.ops)
    assert leg.branch_id is None
    assert p.harnesses[hid].segments[-1].model_dump() == {
        "id": "W001-L2",
        "from_node": "W001-P1",
        "to_node": "W001-P3",
        "length_m": None,
    }


def test_a_leg_refuses_a_pin_with_a_wire_and_names_it():
    p = labelled()
    hid = straight(p)
    with pytest.raises(EditError, match="Pin 1 of W001-P1 has a wire already \\(W001-001\\)"):
        plan_add_leg(p, hid, "OBC-J01", pin_ids=["3", "1"])
    with pytest.raises(EditError, match="W001-P1 has no pin '9'"):
        plan_add_leg(p, hid, "OBC-J01", pin_ids=["9"])
    with pytest.raises(EditError, match="at least one pin"):
        plan_add_leg(p, hid, "OBC-J01", pin_ids=[])
    with pytest.raises(EditError, match="W001 has no connector that plugs into PCDU-J02"):
        plan_add_leg(p, hid, "PCDU-J02")
    full = labelled()
    fid = straight(full, pins=("1", "2", "3", "4"))
    with pytest.raises(EditError, match="no free pin with a signal"):
        plan_add_leg(full, fid, "OBC-J01")


def test_a_leg_refuses_a_loose_end_a_harness_of_a_connection_and_a_generated_one():
    p = labelled()
    made = plan_cable_from_port(p, "OBC-J01", pin_ids=["1"])
    apply_ops(p, made.ops)
    with pytest.raises(EditError, match="W001-P2 is a loose end"):
        plan_add_leg(p, made.harness_id, made.loose_id)
    q = labelled()
    ops, lid = plan_add_link(q, "OBC-J01", "RW1-J02", [("1", "3")])
    apply_ops(q, ops)
    ops, hid = plan_create_harness(q, lid)
    apply_ops(q, ops)
    with pytest.raises(EditError, match=f"{hid} was made from the connection {lid}"):
        plan_add_leg(q, hid, "OBC-J01")
    with pytest.raises(EditError, match="made by Generate"):
        plan_add_leg(generated_mini3(), "W002", "W002-P1")


# ---- the join -----------------------------------------------------------------------------------


def two_cables(p, history):
    """W001 (OBC-J01 pins 1, 2 to RW1-J02) and W002 (OBC-J01 pins 3, 4 to a loose end)."""
    hid = straight(p, history)
    other = plan_cable_from_port(p, "OBC-J01", pin_ids=["3", "4"])
    history.execute("cable", other.ops)
    return hid, other.harness_id


def test_two_drawn_harnesses_on_one_device_connector_become_one():
    p = labelled()
    history = History(p)
    keep, other = two_cables(p, history)
    assert any(i.code == "box_connector_mated_twice" for i in check_integrity(p))
    before = dict(p.harnesses)
    history.execute("join", plan_join_harnesses(p, keep, other))
    assert sorted(p.harnesses) == [keep]
    h = p.harnesses[keep]
    assert [c.id for c in h.connectors] == ["W001-P1", "W001-P2", "W002-P2"]
    assert [c.name for c in h.connectors] == ["P1", "P2", "W002-P2"]  # the name P2 was taken
    assert [(w.id, w.from_connector, w.to_connector) for w in h.wires] == [
        ("W001-001", "W001-P1", "W001-P2"),
        ("W001-002", "W001-P1", "W001-P2"),
        ("W002-001", "W001-P1", "W002-P2"),
        ("W002-002", "W001-P1", "W002-P2"),
    ]
    assert [(b.id, b.name) for b in h.branch_points] == [("W001-B1", "Branch 1")]
    assert [(s.id, s.from_node, s.to_node) for s in h.segments] == [
        ("W001-L1", "W001-P1", "W001-B1"),
        ("W001-L2", "W001-B1", "W001-P2"),
        ("W001-L3", "W001-B1", "W002-P2"),
    ]
    found = {i.code for i in check_integrity(p)}
    assert "box_connector_mated_twice" not in found and not found & set(ROUTING)
    assert errors(p) == []
    history.undo()
    assert p.harnesses == before


def test_the_join_carries_the_other_harness_drawn_tree_and_its_groups():
    p = labelled()
    history = History(p)
    keep, other = two_cables(p, history)
    ops, _sid = plan_add_segment(p, keep, "W001-P1", "W001-P2", 2.0)
    history.execute("segment", ops)
    ops, _sid = plan_add_segment(p, other, "W002-P1", "W002-P2", 0.5)
    history.execute("segment", ops)
    history.execute("pair", plan_group_wires(p, ["W002-001", "W002-002"], "twisted_pair"))
    p.harnesses[other] = evolve(p.harnesses[other], notes="Route along the frame.")
    history.execute("join", plan_join_harnesses(p, keep, other))
    h = p.harnesses[keep]
    assert [(s.id, s.from_node, s.to_node, s.length_m) for s in h.segments] == [
        ("W001-L1", "W001-B1", "W001-P2", 2.0),
        ("W002-L1", "W001-B1", "W002-P2", 0.5),
        ("W001-L2", "W001-P1", "W001-B1", None),
    ]
    assert [g.wire_ids for g in h.shields] == [["W002-001", "W002-002"]]
    assert h.notes == "W002: Route along the frame."
    assert errors(p) == [] and routing_warnings(p) == []


def test_a_join_is_refused_with_the_reason():
    p = labelled()
    history = History(p)
    keep, other = two_cables(p, history)
    with pytest.raises(EditError, match="two different harnesses"):
        plan_join_harnesses(p, keep, keep)
    # different parts on the shared connector
    h = p.harnesses[other]
    plug = evolve(h.connectors[0], part_id="EX-MICROD-15-F")
    p.harnesses[other] = evolve(h, connectors=[plug, *h.connectors[1:]])
    with pytest.raises(EditError, match="The plugs on OBC-J01 have different parts: W001-P1 is EX-MICROD-25-M, W002-P1 is EX-MICROD-15-F"):  # fmt: skip
        plan_join_harnesses(p, keep, other)
    p.harnesses[other] = h
    # a release history of the harness that would be deleted
    p.baselines["W002.1.0.0"] = Baseline(
        id="W002.1.0.0", harness_id=other, version="1.0.0", content_hash="x", snapshot=snapshot_for(p, h), released_on="2026-11-17", by="Ann", comment="first release"
    )  # fmt: skip
    with pytest.raises(EditError, match="W002 has a release history.*Join W001 into W002 instead"):
        plan_join_harnesses(p, keep, other)
    del p.baselines["W002.1.0.0"]
    released(p, other)
    with pytest.raises(EditError, match="W002 is released"):
        plan_join_harnesses(p, keep, other)


def test_a_join_refuses_a_pin_both_wire_and_harnesses_that_share_no_connector():
    p = labelled()
    history = History(p)
    keep = straight(p, history)
    twice = plan_cable_from_port(p, "OBC-J01", pin_ids=["2", "3"])
    history.execute("cable", twice.ops)
    with pytest.raises(EditError, match="W001 and W002 both wire pin of OBC-J01: 2 \\(W001-002 and W002-001\\)"):  # fmt: skip
        plan_join_harnesses(p, keep, twice.harness_id)
    apart = plan_cable_from_port(p, "PCDU-J02")
    history.execute("cable", apart.ops)
    with pytest.raises(EditError, match="no plugs on one device connector"):
        plan_join_harnesses(p, keep, apart.harness_id)


def test_a_join_refuses_two_shared_connectors_a_connection_and_generate():
    p = labelled()
    history = History(p)
    keep = straight(p, history, pins=("1",))
    second = straight(p, history, pins=("2",))
    with pytest.raises(EditError, match="both plug into OBC-J01, RW1-J02.*close a loop"):
        plan_join_harnesses(p, keep, second)
    q = labelled()
    ops, lid = plan_add_link(q, "OBC-J01", "RW1-J02", [("1", "3")])
    apply_ops(q, ops)
    ops, linked = plan_create_harness(q, lid)
    apply_ops(q, ops)
    drawn = plan_cable_from_port(q, "OBC-J01", pin_ids=["2"])
    apply_ops(q, drawn.ops)
    with pytest.raises(EditError, match=f"made from the connection {lid}"):
        plan_join_harnesses(q, drawn.harness_id, linked)
    g = generated_mini3()
    with pytest.raises(EditError, match="per_connector_group"):
        plan_join_harnesses(g, "W002", "W001")


# ---- shield groups across a branch (5.4) ----------------------------------------------------------


def test_a_shield_group_across_a_branch_is_refused_and_warned_in_a_file():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    leg = plan_add_leg(p, hid, "OBC-J01")
    history.execute("leg", leg.ops)
    with pytest.raises(EditError, match="W001-001 and W001-003 end on different connectors \\(RW1-J02, W001-P3\\); a shield group runs between two connectors"):  # fmt: skip
        plan_group_wires(p, ["W001-001", "W001-003"], "shielded_pair")
    history.execute("pair", plan_group_wires(p, ["W001-003", "W001-004"], "shielded_pair"))
    assert routing_warnings(p) == []
    h = p.harnesses[hid]
    group = h.shields[0]
    p.harnesses[hid] = evolve(h, shields=[evolve(group, wire_ids=["W001-001", "W001-003"])])
    assert routing_warnings(p) == [("shield_across_branch", group.id)]
    assert errors(p) == []  # a warning: the file still loads and edits pass


# ---- the integrity warnings (5.5) -------------------------------------------------------------------


def test_the_warnings_of_the_routing_tree():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, bid = plan_add_branch_point(p, hid)
    history.execute("branch", ops)  # a warning never stops an edit
    assert routing_warnings(p) == [("branch_point_unused", bid), ("segment_tree_split", hid)]
    text = {i.code: i.message for i in check_integrity(p)}
    assert "Branch point 'W001-B1' (Branch 1) in harness 'W001' has 0 segments" in text["branch_point_unused"]  # fmt: skip
    assert "do not reach W001-P1, W001-P2 from its routing tree" in text["segment_tree_split"]
    ops, _sid = plan_add_segment(p, hid, "W001-P1", bid)
    history.execute("segment", ops)
    assert (
        "do not reach W001-P2 from its routing tree, so the wires to it have no length"
        in {i.code: i.message for i in check_integrity(p)}["segment_tree_split"]
    )
    assert routing_warnings(p) == [("branch_point_unused", bid), ("segment_tree_split", hid)]
    ops, _sid = plan_add_segment(p, hid, bid, "W001-P2")
    history.execute("segment", ops)
    assert routing_warnings(p) == []


def test_a_harness_without_branch_points_is_never_called_split():
    p = labelled()
    hid = straight(p)
    assert routing_warnings(p) == []  # no segment at all: a straight cable, as before 2.3.0
    assert p.harnesses[hid].segments == []


def test_the_generated_samples_have_no_routing_warning():
    p = generated_mini3()
    assert routing_warnings(p) == []


def test_the_routing_warnings_reach_the_design_rule_model_inconsistent():
    from harness_design_studio.core import drc

    p = labelled()
    hid = straight(p)
    ops, _bid = plan_add_branch_point(p, hid)
    apply_ops(p, ops)
    found = [f for f in drc.run(p) if f.rule == "model-inconsistent"]
    assert any("has 0 segments" in f.title for f in found)


# ---- the diagram mark and the journal ----------------------------------------------------------------


def test_the_mark_of_a_branch_point_goes_with_it_and_is_outside_the_hash():
    p = labelled()
    history = History(p)
    hid = straight(p, history)
    ops, bid = plan_add_branch_point(p, hid)
    history.execute("branch", ops)
    before = model_hash(p)
    p.diagram_marks[f"branch:{bid}"] = DiagramMark(id=f"branch:{bid}", dx=12.0, dy=-4.0)
    assert model_hash(p) == before
    assert not layout.mark_is_orphan(p, f"branch:{bid}")
    assert "diagram/marks.json" in serialize(p)
    history.execute("delete", plan_delete_branch_point(p, hid, bid))
    assert layout.mark_is_orphan(p, f"branch:{bid}")
    assert "diagram/marks.json" not in serialize(p)  # written without the mark of a deleted thing
    history.undo()
    assert not layout.mark_is_orphan(p, f"branch:{bid}")


def test_each_plan_is_journalled_as_a_change_of_a_branch_point_or_a_segment():
    p = labelled()
    hid = straight(p)
    old = serialize(p)
    ops, bid = plan_add_branch_point(p, hid)
    apply_ops(p, ops)
    ops, sid = plan_add_segment(p, hid, "W001-P1", bid, 0.3)
    apply_ops(p, ops)
    objects = {r["object"] for r in journal.rows_for_save(p, old, serialize(p))}
    assert {f"branch_point:{bid}", f"segment:{sid}"} <= objects


def test_the_module_says_where_it_is_and_why():
    assert "core/routing.py" in (branching.__doc__ or "")
    assert set(branching.__all__) >= {"plan_add_leg", "plan_join_harnesses", "Leg"}


def test_put_ops_only_replace_the_one_harness():
    p = labelled()
    hid = straight(p)
    ops, _bid = plan_add_branch_point(p, hid)
    assert [type(o) for o in ops] == [Put] and ops[0].obj.id == hid


def test_the_fix_of_a_connector_with_two_plugs_is_the_join_or_the_mode():
    from harness_design_studio.core.branching import PlugFix, plug_fix

    p = labelled()
    history = History(p)
    keep, other = two_cables(p, history)
    assert plug_fix(p, "OBC-J01") == PlugFix("join", "OBC-J01", (keep, other))
    assert plug_fix(p, "RW1-J02") is None  # one plug
    assert plug_fix(p, "NOPE") is None
    p.harnesses[other] = evolve(p.harnesses[other], generated=True)
    assert plug_fix(p, "OBC-J01") is None  # one of each: neither fix
    p.harnesses[keep] = evolve(p.harnesses[keep], generated=True)
    assert plug_fix(p, "OBC-J01") == PlugFix("mode", "OBC-J01", (keep, other))
    p.config["segmentation"] = evolve(
        p.config["segmentation"], values={"mode": "per_connector_group"}
    )
    assert plug_fix(p, "OBC-J01") is None  # the next Generate joins them


def test_the_diagram_draws_the_branch_points_of_a_drawn_harness_and_its_lines_run_through_them():
    from harness_design_studio.core import cable_ends

    p = labelled()
    hid = straight(p)
    assert cable_ends.drawn_branch_points(p) == []
    leg = plan_add_leg(p, hid, "OBC-J01")
    apply_ops(p, leg.ops)
    (spot,) = cable_ends.drawn_branch_points(p)
    assert spot == cable_ends.BranchSpot(
        hid, "W001-B1", "Branch 1", ("W001-P1", "W001-P2", "W001-P3")
    )
    ends = {e.connector_id: e for e in cable_ends.drawn_ends(p)}
    assert ends["W001-P3"].via == ("W001-B1",) and ends["W001-P2"].via == ("W001-B1",)
    h = p.harnesses[hid]
    assert cable_ends.path_branches(h, "W001-P1", "W001-P1") == ()
    assert cable_ends.path_branches(h, "W001-P2", "W001-P3") == ("W001-B1",)
    assert cable_ends.path_branches(h, "W001-P1", "NOWHERE") == ()
    assert cable_ends.branch_mark("W001-B1") == "branch:W001-B1"
    assert cable_ends.drawn_branch_points(generated_mini3()) == []  # Generate's are not drawn
