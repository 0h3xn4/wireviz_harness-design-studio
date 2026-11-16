# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""A released harness on a connector that takes another interface (D-237, owner question Q2,
`docs/ait/DESIGN_2.1_PORTS.md` section 5, *A released harness on the connector*). W001 is
released with IF-A on port RS422_1 of OBC1-J1; IF-B is added on port RS422_2. To the same far
connector it joins the frozen group: Generate says `frozen_changed`, and after `revise` W001
revision B carries both. To another far connector it gets a harness of its own with a second plug
on OBC1-J1 (`box_connector_shared`), and the released harness is not modified. Example data only."""

from pathlib import Path

import pytest

from harness_design_studio.core import devices, drc, edit
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Project, evolve
from harness_design_studio.core.outputs.build import write_outputs
from harness_design_studio.core.vcs.release import plan_new_revision, plan_release
from tests.test_multi_interface_connector import add, obc, pins_of, port_pins

REASON = "Test project: values are placeholders"
WHEN = "2026-03-01"


def released(tmp_path: Path) -> tuple[Project, str, str]:
    """W001 released, carrying IF-A on port RS422_1 of OBC1-J1 (locked there by a person)."""
    p = obc(("J1", port_pins("RS422_1", "RS422_2")), sensors=2)
    a = add(p, "OBC1", "ST1", "OBC1-J1", "ST1-J02")
    History(p).execute("port", devices.ops_assign_port(p, "OBC1-J1", "RS422_1", a))
    generate_project(p)
    (hid,) = p.harnesses
    h = p.harnesses[hid]
    apply_ops(
        p,
        [
            Put(
                "harnesses",
                evolve(h, wires=[evolve(w, gauge_awg=24, length_m=1.0) for w in h.wires]),
            )
        ],
    )
    folder = tmp_path / "outputs"
    write_outputs(p, folder)
    plan = plan_release(
        p, hid, by="Ada", checker="Bob", comment="First release for the CDR", when=WHEN,
        outputs_folder=folder, accept_placeholders=REASON, accept_unapproved_parts=REASON,
    )  # fmt: skip
    assert plan.ok, [b.message for b in plan.blockers]
    History(p).execute(plan.label, plan.ops)
    assert p.harnesses[hid].status == "released"
    return p, hid, a


def codes(p: Project) -> set[str]:
    return {f.code for f in generate_project(p).report.findings}


def rules(p: Project) -> set[str]:
    return {f.rule for f in drc.run(p)}


def test_same_far_connector_joins_the_frozen_group_and_the_revision_carries_both(
    tmp_path: Path,
) -> None:
    p, hid, a = released(tmp_path)
    compat = edit.connector_compat(p, "rs422", "OBC1-J1", far_unit="ST1", far_connector="ST1-J02")
    assert compat.ok and f"{hid} is released and plugs into OBC1-J1" in compat.note
    # a port whose pins the release locks cannot be chosen for another interface
    b = add(p, "OBC1", "ST1", "OBC1-J1", "ST1-J02")
    with pytest.raises(edit.EditError) as exc:
        devices.ops_assign_port(p, "OBC1-J1", "RS422_1", b)
    assert str(exc.value).startswith("Port RS422_1 of OBC1-J1 cannot change.")
    assert hid in str(exc.value) and "released" in str(exc.value)
    found = codes(p)
    assert "frozen_changed" in found and "box_connector_shared" not in found
    assert pins_of(p, "OBC1-J1", b) == []  # not wired until the new revision
    assert "released-modified" not in rules(p)
    plan = plan_new_revision(
        p, hid, by="Ada", comment="Add the second star tracker link", when=WHEN
    )
    assert plan.ok, [x.message for x in plan.blockers]
    History(p).execute(plan.label, plan.ops)
    assert p.harnesses[hid].revision == "B"
    found = codes(p)
    assert "frozen_changed" not in found
    assert sorted(p.harnesses[hid].interfaces) == sorted([a, b])
    assert pins_of(p, "OBC1-J1", a) == ["1", "2", "3", "4"]
    assert pins_of(p, "OBC1-J1", b) == ["5", "6", "7", "8"]
    assert len(p.harnesses) == 1


def test_another_far_connector_gets_its_own_harness_and_the_release_stays(
    tmp_path: Path,
) -> None:
    p, hid, a = released(tmp_path)
    before = p.harnesses[hid]
    compat = edit.connector_compat(p, "rs422", "OBC1-J1", far_unit="ST2", far_connector="ST2-J02")
    assert compat.ok and "second harness" in compat.note and "released" not in compat.note
    b = add(p, "OBC1", "ST2", "OBC1-J1", "ST2-J02")
    found = codes(p)
    assert "box_connector_shared" in found and "frozen_changed" not in found
    assert p.harnesses[hid] == before
    (new,) = [h for h in p.harnesses.values() if h.id != hid]
    assert new.interfaces == [b]
    assert pins_of(p, "OBC1-J1", a) == ["1", "2", "3", "4"]
    assert pins_of(p, "OBC1-J1", b) == ["5", "6", "7", "8"]
    assert "released-modified" not in rules(p)
