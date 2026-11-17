# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Generate with `segmentation.mode` = `per_connector_group` (2.3.0, D-243;
`docs/ait/DESIGN_2.3_BRANCHING.md` section 5.1, tests of section 9). The groups of
`per_connector_pair` that plug into one device connector become one harness that branches: one plug
on each device connector, a branch point on an end with more than one connector, the trunk and the
legs. Opt-in (B2): the default stays `per_connector_pair`. Drafts are taken over (the lowest ID is
kept, what a person set carries over), released harnesses never (B6). A ring of connectors stays as
its pairs with the warning `branch_not_built`. Example data only."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from harness_design_studio.core import connector_edit, edit, settings, wires
from harness_design_studio.core.assumptions import ASSUMPTIONS
from harness_design_studio.core.commands import History, apply_ops
from harness_design_studio.core.derive import explain_object
from harness_design_studio.core.generate import segmentation
from harness_design_studio.core.generate.engine import generate_project, plan_generation
from harness_design_studio.core.integrity import check_integrity, one_plug_advice
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import (
    Accessory,
    ConfigFile,
    Connector,
    Endpoint,
    Harness,
    InterfaceInstance,
    Pin,
    Project,
    Unit,
    Wire,
    evolve,
)
from harness_design_studio.core.samples import new_project
from tests.test_e2e_rs422x3 import (
    J1,
    add_interfaces,
    files,
    imported,
    ports_used,
    run,
    with_port_column,
)

GROUP = "per_connector_group"
STAR = [("OBC1", "STR1"), ("OBC1", "STR2"), ("OBC1", "STR3")]  # the D-237 case
TWO_TWO = [("DEV2", "DEV1"), ("DEV2", "DEV4"), ("DEV3", "DEV1"), ("DEV3", "DEV4")]  # 2 + 2
RING = [("A", "B"), ("B", "C"), ("A", "C")]


def set_mode(p: Project, mode: str, **segregation: object) -> Project:
    p.config["segmentation"] = ConfigFile(
        name="segmentation", placeholder=True, values={"mode": mode}
    )
    if segregation:
        old = p.config["segregation"]
        p.config["segregation"] = evolve(old, values={**old.values, **segregation})
    return p


def build(edges: Sequence[tuple[str, ...]], mode: str = GROUP) -> Project:
    """One connector `<device>-J01` per device and one interface per edge (`IF-001`, ... in the
    order given; a third item is the redundancy)."""
    p = set_mode(new_project("branching"), mode)
    for u in sorted({u for e in edges for u in e[:2]}):
        p.units[u] = Unit(id=u, name=u, subsystem="s", zone="panel-A", side="nominal")
        p.connectors[f"{u}-J01"] = Connector(
            id=f"{u}-J01", name="J01", role="box", part_id="EX-MICROD-25-F", unit_id=u,
            gender="female", pins=[Pin(id=str(k + 1)) for k in range(25)],
        )  # fmt: skip
    for n, (a, b, *chain) in enumerate(edges, start=1):
        iid = f"IF-{n:03d}"
        p.interfaces[iid] = InterfaceInstance(
            id=iid, name=iid, type_id="rs422", redundancy=cast(Any, chain[0] if chain else "none"),
            endpoints=[Endpoint(unit_id=a, connector_id=f"{a}-J01"), Endpoint(unit_id=b, connector_id=f"{b}-J01")],
        )  # fmt: skip
    return p


def codes(plan: object) -> list[str]:
    return [f.code for f in plan.report.findings]  # type: ignore[attr-defined]


def shape(p: Project, hid: str) -> tuple[object, ...]:
    h = p.harnesses[hid]
    return (
        h.name,
        h.group_key,
        [(c.id, c.mates_with) for c in h.connectors],
        [(b.id, b.name) for b in h.branch_points],
        [(s.id, s.from_node, s.to_node) for s in h.segments],
    )


# ---- the two cases of the design ---------------------------------------------------------------


def test_the_d237_case_gives_one_harness_with_one_plug_on_the_shared_connector() -> None:
    p = build(STAR)
    plan = generate_project(p)
    assert plan.report.added == ["W001"] and list(p.harnesses) == ["W001"]
    assert "box_connector_shared" not in codes(plan)
    assert shape(p, "W001") == (
        "OBC1-J01 to STR1-J01 + STR2-J01 + STR3-J01",
        "cg|none|OBC1-J01",
        [("W001-P1", "OBC1-J01"), ("W001-P2", "STR1-J01"), ("W001-P3", "STR2-J01"), ("W001-P4", "STR3-J01")],
        [("W001-B2", "Branch Y")],
        [("W001-L1", "W001-P1", "W001-B2"), ("W001-L2", "W001-P2", "W001-B2"), ("W001-L3", "W001-P3", "W001-B2"), ("W001-L4", "W001-P4", "W001-B2")],
    )  # fmt: skip
    h = p.harnesses["W001"]
    assert h.interfaces == ["IF-001", "IF-002", "IF-003"] and len(h.wires) == 12
    # every wire runs pin to pin between the plug on OBC1-J01 and the plug of its star tracker
    far = {"IF-001": "W001-P2", "IF-002": "W001-P3", "IF-003": "W001-P4"}
    for w in h.wires:
        assert {w.from_connector, w.to_connector} == {"W001-P1", far[w.interface_id or ""]}
    assert not [i for i in check_integrity(p) if i.code == "box_connector_mated_twice"]
    assert generate_project(p).empty


def test_two_connectors_at_each_end_give_branch_x_the_trunk_and_branch_y() -> None:
    """The users' harness *DEV2 + DEV3 <-> DEV1 + DEV4*: DEV1-J01 is the first connector, so it is
    end X; DEV2 and DEV3 are joined to it (end Y); DEV4 is joined to them (end X)."""
    p = build(TWO_TWO)
    plan = generate_project(p)
    assert list(p.harnesses) == ["W001"] and "box_connector_shared" not in codes(plan)
    assert shape(p, "W001") == (
        "DEV1-J01 + DEV4-J01 to DEV2-J01 + DEV3-J01",
        "cg|none|DEV1-J01",
        [("W001-P1", "DEV1-J01"), ("W001-P2", "DEV4-J01"), ("W001-P3", "DEV2-J01"), ("W001-P4", "DEV3-J01")],
        [("W001-B1", "Branch X"), ("W001-B2", "Branch Y")],
        [("W001-L1", "W001-B1", "W001-B2"), ("W001-L2", "W001-P1", "W001-B1"), ("W001-L3", "W001-P2", "W001-B1"), ("W001-L4", "W001-P3", "W001-B2"), ("W001-L5", "W001-P4", "W001-B2")],
    )  # fmt: skip
    assert len(p.harnesses["W001"].wires) == 16
    assert generate_project(p).empty


def test_the_name_lists_three_connectors_of_an_end_and_then_how_many_more() -> None:
    p = build([("HUB", f"D{k}") for k in range(1, 6)])
    generate_project(p)
    # D1-J01 comes first in natural order, so it and the other far devices are end X
    assert p.harnesses["W001"].name == "D1-J01 + D2-J01 + D3-J01 and 2 more to HUB-J01"
    assert segmentation.end_names(["A", "B", "C", "D"]) == "A + B + C and 1 more"


# ---- what is not joined ----------------------------------------------------------------------


def test_a_ring_stays_as_pairs_with_the_warning_branch_not_built() -> None:
    p = build(RING)
    plan = generate_project(p)
    assert sorted(h.group_key or "" for h in p.harnesses.values()) == [
        "cp|none|A-J01|B-J01", "cp|none|A-J01|C-J01", "cp|none|B-J01|C-J01",
    ]  # fmt: skip
    (ring,) = [f for f in plan.report.findings if f.code == "branch_not_built"]
    assert ring.severity == "warning" and ring.object_id == "A-J01"
    assert ring.message == (
        "A-J01, B-J01 and C-J01 are wired in a ring, so one harness cannot run them as two ends of"
        " one trunk. They stay separate harnesses; draw the harness to join them."
    )
    # the plugs stay, and the advice says why the mode did not join them
    shared = [f for f in plan.report.findings if f.code == "box_connector_shared"]
    assert len(shared) == 3 and all("wired in a ring" in f.message for f in shared)
    # explain of a harness of the ring names the ring
    steps = [s.expression for d in explain_object(p, "W001") for s in d.steps]
    assert ring.message in steps
    assert generate_project(p).empty


def test_a_ring_names_only_the_connectors_that_close_it() -> None:
    p = build([*RING, ("C", "D")])
    seg = segmentation.segment(p)
    assert [r.connectors for r in seg.rings] == [("A-J01", "B-J01", "C-J01")]
    assert len(seg.groups) == 4 and all(g.mode == "per_connector_pair" for g in seg.groups)


def test_chains_are_not_joined_while_they_are_kept_apart() -> None:
    edges = [
        ("OBC1", "STR1", "nominal"),
        ("OBC1", "STR2", "redundant"),
        ("OBC1", "STR3", "nominal"),
    ]
    p = build(edges)
    seg = segmentation.segment(p)
    assert [(g.key, g.interface_ids) for g in seg.groups] == [
        ("cg|nominal|OBC1-J01", ("IF-001", "IF-003")),
        ("cp|redundant|OBC1-J01|STR2-J01", ("IF-002",)),
    ]
    # with forbid_nominal_with_redundant off the two chains may share a harness, and are joined
    set_mode(p, GROUP, forbid_nominal_with_redundant=False)
    seg = segmentation.segment(p)
    assert [(g.key, g.interface_ids) for g in seg.groups] == [
        ("cg||OBC1-J01", ("IF-001", "IF-002", "IF-003"))
    ]


def test_a_project_without_a_shared_connector_groups_the_same_in_both_modes() -> None:
    edges = [("A", "B"), ("C", "D"), ("E", "F")]
    pair = segmentation.segment(build(edges, "per_connector_pair"))
    group = segmentation.segment(build(edges))
    assert group.mode == GROUP and pair.mode == "per_connector_pair"
    assert group.groups == pair.groups and group.rings == []


def test_the_default_stays_per_connector_pair() -> None:
    s = settings.setting("segmentation", "mode")
    assert s is not None and s.default == "per_connector_pair"
    assert s.choices == ("per_connector_pair", "per_unit_pair", "per_zone_pair", GROUP)
    p = new_project("default")
    assert p.config["segmentation"].values["mode"] == "per_connector_pair"
    assert settings.choice(p, "segmentation", "mode") == "per_connector_pair"
    assert settings.choice(set_mode(p, GROUP), "segmentation", "mode") == GROUP


# ---- taking over drafts (B6) --------------------------------------------------------------------


def pairs_then(p: Project) -> Project:
    """Generate in per_connector_pair (one draft per interface, W001, ...), then switch to the new
    mode."""
    set_mode(p, "per_connector_pair")
    generate_project(p)
    assert list(p.harnesses) == [f"W{n:03d}" for n in range(1, len(p.interfaces) + 1)]
    return set_mode(p, GROUP)


def carried(h: Harness) -> list[tuple[tuple[str, str, str], Wire]]:
    """The wires of a harness by what they carry: interface, signal and the device connector the
    wire starts at (a wire's ID changes when its harness is taken over)."""
    box = {c.id: c.mates_with or "" for c in h.connectors}
    return [((w.interface_id or "", w.signal or "", box[w.from_connector]), w) for w in h.wires]


def test_the_join_keeps_the_lowest_draft_id_and_carries_over_what_a_person_set() -> None:
    p = pairs_then(build(STAR))
    h = History(p)
    old = {hid: dict(carried(p.harnesses[hid])) for hid in p.harnesses}
    w2 = p.harnesses["W002"].wires[0]  # a wire of IF-002, locked by a gauge with a reason
    h.execute("lock", wires.plan_wire_edit(p, [w2.id], {"gauge_awg": 22}, reason="bench test"))
    w3 = p.harnesses["W003"].wires[1]
    h.execute("label", wires.plan_wire_edit(p, [w3.id], {"label": "TO STR3", "note": "check"}))
    star3 = next(c for c in p.harnesses["W003"].connectors if c.mates_with == "STR3-J01")
    h.execute("edit", connector_edit.plan_edit_connector(p, "W003", star3.id, keying="B"))
    w1 = p.harnesses["W001"].wires[0]
    h.execute("strip", wires.plan_wire_edit(p, [w1.id], {"note": "kept"}))

    plan = generate_project(p)
    assert list(p.harnesses) == ["W001"]
    assert plan.report.removed == ["W002", "W003"] and plan.report.changed == ["W001"]
    new = p.harnesses["W001"]
    assert new.group_key == "cg|none|OBC1-J01"
    by_key = {k: w for k, w in carried(new)}
    keys = {hid: {w.id: k for k, w in found.items()} for hid, found in old.items()}
    locked = by_key[keys["W002"][w2.id]]
    assert (
        locked.locked and locked.gauge_awg == 22 and locked.overrides == {"gauge_awg": "bench test"}
    )
    assert locked.id.startswith("W001-")  # under the numbering of the kept harness
    labelled = by_key[keys["W003"][w3.id]]
    assert (labelled.label, labelled.note) == ("TO STR3", "check") and labelled.id.startswith(
        "W001-"
    )
    assert by_key[keys["W001"][w1.id]].id == w1.id  # the kept harness keeps its wire IDs
    assert by_key[keys["W001"][w1.id]].note == "kept"
    plug = next(c for c in new.connectors if c.mates_with == "STR3-J01")
    assert plug.id.startswith("W001-P") and plug.locked and plug.keying == "B"
    assert len({w.id for w in new.wires}) == len(new.wires) == 12
    # nothing is lost: what was set carried over
    assert "locked_data_lost" not in codes(plan)
    assert generate_project(p).empty


def test_what_cannot_carry_over_is_reported() -> None:
    p = pairs_then(build(STAR))
    p.harnesses["W002"] = evolve(
        p.harnesses["W002"],
        accessories=[Accessory(id="ACC-001", kind="backshell", target="W002-P1")],
        notes="route along the panel",
    )
    seg = p.harnesses["W001"].segments[0]
    p.harnesses["W001"] = evolve(p.harnesses["W001"], segments=[evolve(seg, length_m=0.5)])
    plan = plan_generation(p)
    lost = {f.object_id: f.message for f in plan.report.findings if f.code == "locked_data_lost"}
    assert lost == {
        "W001": "W001: the entered length of segment W001-L1 (0.5 m) cannot be carried over and will be lost.",
        "W002": "W002: the accessory ACC-001 (backshell on W002-P1), the notes of W002 cannot be"
        " carried over to W001 and will be lost.",
    }


def test_a_released_harness_is_never_taken_over() -> None:
    p = pairs_then(build(STAR))
    p.harnesses["W001"] = evolve(p.harnesses["W001"], status="released")
    before = p.harnesses["W001"]
    plan = generate_project(p)
    assert p.harnesses["W001"] == before and plan.report.frozen == ["W001"]
    # IF-002 and IF-003 join into the draft with the lowest ID; W003 is taken over
    assert sorted(p.harnesses) == ["W001", "W002"] and plan.report.removed == ["W003"]
    assert p.harnesses["W002"].group_key == "cg|none|OBC1-J01"
    assert p.harnesses["W002"].interfaces == ["IF-002", "IF-003"]
    # two plugs on OBC1-J01, one of them released: the warning stays, with the advice of 2.1.0
    (shared,) = [f for f in plan.report.findings if f.code == "box_connector_shared"]
    assert (
        shared.object_id == "OBC1-J01"
        and "two harnesses cannot both plug into it" in shared.message
    )
    assert "frozen_orphan" not in codes(plan) and "frozen_changed" not in codes(plan)
    assert generate_project(p).empty


def test_a_released_joined_harness_stays_as_it_is_and_a_new_interface_gets_its_own_plug() -> None:
    p = build(STAR)
    generate_project(p)
    p.harnesses["W001"] = evolve(p.harnesses["W001"], status="released")
    before = p.harnesses["W001"]
    plan = generate_project(p)
    assert plan.empty and plan.report.frozen == ["W001"]
    assert not [f for f in plan.report.findings if f.severity != "info" and f.code != "wire_part"]
    # a fourth star tracker on OBC1-J01: a harness of its own, and the plug warning
    q = build([*STAR, ("OBC1", "STR4")])
    q.harnesses["W001"] = before
    q.generation = p.generation
    q.connectors["OBC1-J01"] = p.connectors["OBC1-J01"]
    plan = generate_project(q)
    assert q.harnesses["W001"] == before and plan.report.added == ["W002"]
    assert q.harnesses["W002"].interfaces == ["IF-004"]
    assert "box_connector_shared" in codes(plan) and "frozen_orphan" not in codes(plan)


def test_a_switch_back_to_per_connector_pair_gives_the_pairs_again() -> None:
    p = build(STAR)
    generate_project(p)
    set_mode(p, "per_connector_pair")
    plan = generate_project(p)
    assert sorted(h.group_key or "" for h in p.harnesses.values()) == [
        f"cp|none|OBC1-J01|STR{k}-J01" for k in (1, 2, 3)
    ]
    assert "box_connector_shared" in codes(plan)


# ---- determinism ------------------------------------------------------------------------------


def test_generating_twice_changes_nothing_and_two_projects_are_byte_identical(
    tmp_path: Path,
) -> None:
    folders = []
    for n in (1, 2):
        p = pairs_then(build(TWO_TWO))
        generate_project(p)
        assert generate_project(p).empty
        save_project(p, tmp_path / str(n))
        folders.append(tmp_path / str(n))
    a, b = (files(f) for f in folders)
    assert a == b
    p = load_project(folders[0]).project
    assert plan_generation(p).empty


# ---- settings, explain, the advice --------------------------------------------------------------


def test_explain_names_the_join_and_the_assumption() -> None:
    p = build(STAR)
    generate_project(p)
    (d,) = [x for x in explain_object(p, "W001") if x.id == "segmentation"]
    steps = {s.label: s.expression for s in d.steps}
    assert steps["Join of the group"] == (
        "IF-001, IF-002 and IF-003 share a harness because they plug into OBC1-J01; mode"
        " per_connector_group; ends X: OBC1-J01, Y: STR1-J01, STR2-J01, STR3-J01"
    )
    assert "A-SEGMENT-MODE" in d.assumptions
    assert d.equation.startswith("harness = the interfaces of one chain whose device connectors")
    assert "per_connector_group" in ASSUMPTIONS["A-SEGMENT-MODE"].text
    # the generation record says the same
    assert p.generation is not None
    assert any("plug into OBC1-J01" in line for line in p.generation.provenance["harness:W001"])


def test_the_advice_on_a_second_plug_names_per_connector_group() -> None:
    p = build(STAR, "per_connector_pair")
    plan = generate_project(p)
    advice = one_plug_advice("per_connector_pair")
    assert advice.endswith(
        "or set segmentation.mode to per_connector_group for one harness that branches."
    )
    assert "planned for 2.3.0" not in advice
    shared = [f for f in plan.report.findings if f.code == "box_connector_shared"]
    assert shared and shared[0].message.endswith(advice)
    (mated,) = [i for i in check_integrity(p) if i.code == "box_connector_mated_twice"]
    assert mated.message.endswith(advice)
    # in the new mode, before the next Generate: the advice says that Generate joins them
    set_mode(p, GROUP)
    (mated,) = [i for i in check_integrity(p) if i.code == "box_connector_mated_twice"]
    assert mated.message.endswith(one_plug_advice(GROUP))
    assert "Generate joins them into one harness that branches" in mated.message
    # following the advice removes the warning
    plan = generate_project(p)
    assert "box_connector_shared" not in codes(plan)


def test_the_editor_note_says_generate_joins_it_as_a_branch() -> None:
    p = build(STAR[:1])
    other = edit.connector_compat(p, "rs422", "OBC1-J01", far_unit="STR2", far_connector="STR2-J01")
    assert other.ok and other.note == (
        "OBC1-J01 also carries IF-001 to another connector: Generate joins it into the harness on"
        " OBC1-J01 as a branch."
    )
    set_mode(p, "per_connector_pair")
    other = edit.connector_compat(p, "rs422", "OBC1-J01", far_unit="STR2", far_connector="STR2-J01")
    assert (
        "with segmentation.mode per_connector_group it makes one harness that branches"
        in other.note
    )


# ---- through the command line ------------------------------------------------------------------


def test_the_rs422x3_case_end_to_end_in_the_new_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The case of `tests/test_e2e_rs422x3.py` with `settings --set segmentation.mode=...`: one plug
    on J1, port k for IF-k, `validate` and `check` accept the value, `verify --outputs` finds no
    error, `explain` names the join, a second Generate changes no file, a switch back gives the
    pairs."""
    proj = imported(tmp_path, capsys, with_port_column())
    add_interfaces(proj)
    code, out = run(capsys, "settings", str(proj), "--set", f'segmentation.mode="{GROUP}"')
    assert code == 0, out
    for command in ("validate", "check"):
        code, out = run(capsys, command, str(proj))
        assert code == 0 and "segmentation.mode" not in out, out
    code, out = run(capsys, "settings", str(proj))
    assert code == 0 and GROUP in out, out

    code, out = run(capsys, "generate", str(proj))
    assert code == 0, out
    assert "1 added" in out and "box_connector_shared" not in out and "not known" not in out
    q = load_project(proj).project
    assert list(q.harnesses) == ["W001"]
    assert [(c.id, c.mates_with) for c in q.harnesses["W001"].connectors] == [
        ("W001-P1", J1), ("W001-P2", "STR1-J01"), ("W001-P3", "STR2-J01"), ("W001-P4", "STR3-J01"),
    ]  # fmt: skip
    assert [b.name for b in q.harnesses["W001"].branch_points] == ["Branch Y"]
    assert ports_used(proj) == {f"IF-00{k}": {f"RS422_{k}"} for k in (1, 2, 3)}

    assert run(capsys, "export", str(proj))[0] == 0
    first = files(proj / "outputs")
    code, out = run(capsys, "verify", str(proj), "--outputs")
    assert code == 0 and "0 error(s)" in out, out
    code, out = run(capsys, "drc", str(proj))
    assert code == 0 and "Open: 0 error(s)" in out and "cable plugs on it" not in out, out
    code, out = run(capsys, "explain", str(proj), "W001")
    assert code == 0 and "share a harness because they plug into OBC1-J01" in out, out

    before = files(proj)
    code, out = run(capsys, "generate", str(proj))
    assert code == 0 and "0 added, 0 changed, 1 unchanged" in out, out
    assert files(proj) == before
    assert run(capsys, "export", str(proj))[0] == 0
    assert files(proj / "outputs") == first

    code, out = run(
        capsys, "settings", str(proj), "--set", 'segmentation.mode="per_connector_pair"'
    )
    assert code == 0, out
    code, out = run(capsys, "generate", str(proj))
    assert code == 0 and "box_connector_shared" in out, out
    assert len(load_project(proj).project.harnesses) == 3


def test_apply_ops_of_a_plan_gives_what_generate_project_gives() -> None:
    """The plan is pure: applying it through the history gives the same project."""
    p, q = pairs_then(build(STAR)), pairs_then(build(STAR))
    History(p).execute("Generate", plan_generation(p).ops)
    apply_ops(q, plan_generation(q).ops)
    assert p.harnesses == q.harnesses
