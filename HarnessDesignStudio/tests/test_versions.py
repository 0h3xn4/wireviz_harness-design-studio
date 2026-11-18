# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-CC-05: the one order of revisions and versions (`core/vcs/versions.py`, design of 3.0.0
`docs/ait/DESIGN_3.0_HARNESS_PLAN.md` section 5, pull request R1), the next version, the mapping
of an old letter and the pinout test of section 5.3.

R1 changes nothing visible in 2.x: the baselines, the editor's top bar and the state of a harness
keep the letter order they had, which the tests below prove on every letter up to ZZZ."""

import json
import random
from types import SimpleNamespace
from typing import Any

import pytest

from harness_design_studio.core.describe import harness_state
from harness_design_studio.core.model import Connector, Harness, Snapshot, Wire, evolve
from harness_design_studio.core.vcs.report import baselines_of
from harness_design_studio.core.vcs.versions import (
    bump,
    is_first,
    is_version,
    letter_number,
    letter_to_version,
    pinout_changes,
    pinout_note_due,
    sort_versions,
    version_key,
)


def next_revision(rev: str) -> str:
    """A -> B ... Z -> AA -> AB: how format 2 counted its revisions (`release.next_revision` until
    format 3, D-242), kept here to hold the letter order against it."""
    chars = list(rev)
    k = len(chars) - 1
    while k >= 0:
        if chars[k] != "Z":
            chars[k] = chr(ord(chars[k]) + 1)
            return "".join(chars)
        chars[k] = "A"
        k -= 1
    return "A" + "".join(chars)


def letters(last: str) -> list[str]:
    """Every revision of letters from A to `last`, counted as format 2 counted them."""
    out = ["A"]
    while out[-1] != last:
        out.append(next_revision(out[-1]))
    return out


ALL = letters("ZZZ")  # 18,278 revisions, in the order the tool makes them


def old_baseline_key(rev: str) -> tuple[int, str]:
    """`report.baselines_of` before R1: by length, then as text."""
    return (len(rev), rev)


# ---- the order -------------------------------------------------------------------------------


def test_letters_sort_in_the_letter_order() -> None:
    assert sort_versions(["AA", "Z", "B", "A", "AB", "ZZ", "AAA", "BA", "AZ"]) == [
        "A", "B", "Z", "AA", "AB", "AZ", "BA", "ZZ", "AAA",
    ]  # fmt: skip
    assert version_key("A") < version_key("B") < version_key("Z") < version_key("AA")


def test_versions_sort_by_their_numbers_not_as_text() -> None:
    assert sort_versions(["2.0.0", "1.10.0", "1.2.0", "1.0.0", "1.9.0", "1.2.10", "1.2.9"]) == [
        "1.0.0", "1.2.0", "1.2.9", "1.2.10", "1.9.0", "1.10.0", "2.0.0",
    ]  # fmt: skip
    assert (
        version_key("1.0.0") < version_key("1.2.0") < version_key("1.10.0") < version_key("2.0.0")
    )
    assert version_key("0.0.0") < version_key("0.0.1") < version_key("9999.9999.9999")


def test_a_letter_sorts_as_the_version_it_maps_to() -> None:
    # section 5.5: B is 2.0.0, so 1.2.0 comes between A and B and 27.0.0 is next to AA
    assert sort_versions(["B", "1.2.0", "A", "AA", "26.5.0", "28.0.0"]) == [
        "A", "1.2.0", "B", "26.5.0", "AA", "28.0.0",
    ]  # fmt: skip
    # a letter and its own version (only a hand-edited file holds both): next to each other,
    # the version first, so the order is total and two keys are equal only for equal texts
    assert sort_versions(["B", "2.0.0", "A"]) == ["A", "2.0.0", "B"]
    assert version_key("B") != version_key("2.0.0")


def test_other_values_sort_after_letters_and_versions_by_length_then_text() -> None:
    others = ["b", "A1", "-", "1.0", "01.0.0", "v1.0.0", "10000.0.0", ""]
    assert sort_versions([*others, "AA", "1.0.0", "A"]) == [
        "1.0.0", "A", "AA", "", "-", "b", "A1", "1.0", "01.0.0", "v1.0.0", "10000.0.0",
    ]  # fmt: skip
    # among themselves exactly as baselines_of sorted them before R1
    assert sort_versions(others) == sorted(others, key=old_baseline_key)


def test_is_version_is_the_one_way_to_write_a_version() -> None:
    for good in ("0.0.0", "1.0.0", "1.10.2", "9999.9999.9999"):
        assert is_version(good), good
    for bad in ("01.0.0", "v1.0.0", "1.0", "1.0.0.0", "10000.0.0", "1.00.0", " 1.0.0", "A", ""):
        assert not is_version(bad), bad


def test_letter_number_counts_as_next_revision_counts() -> None:
    assert [letter_number(r) for r in ("A", "Z", "AA", "AZ", "BA", "ZZ", "AAA")] == [
        1, 26, 27, 52, 53, 702, 703,
    ]  # fmt: skip
    assert [letter_number(r) for r in ALL] == list(range(1, len(ALL) + 1))
    for other in ("a", "A1", "-", "", "1.0.0", "Ä"):
        assert letter_number(other) is None


# ---- R1 changes nothing visible: the new order is the old one on every letter -------------------


def test_the_order_is_the_old_baseline_order_on_every_letter_up_to_zzz() -> None:
    # Both orders are total and the letters are distinct, so the same order of the whole list
    # means the same order of every pair, and so of every list of letters up to ZZZ.
    shuffled = ALL[:]
    random.Random(242).shuffle(shuffled)
    assert sort_versions(shuffled) == sorted(shuffled, key=old_baseline_key) == ALL


def test_the_order_is_the_old_order_on_random_lists_of_letters() -> None:
    rng = random.Random(3)
    for _ in range(500):
        sample = rng.sample(ALL[:702], rng.randint(1, 30))  # up to ZZ
        assert sort_versions(sample) == sorted(sample, key=old_baseline_key)


def test_baselines_of_keeps_the_letter_order() -> None:
    revs = letters("ZZ")
    shuffled = revs[:]
    random.Random(7).shuffle(shuffled)
    baselines = {
        f"W001.{r}": SimpleNamespace(id=f"W001.{r}", harness_id="W001", version=r) for r in shuffled
    }
    baselines["W002.A"] = SimpleNamespace(id="W002.A", harness_id="W002", version="A")
    project: Any = SimpleNamespace(baselines=baselines)
    got = [b.version for b in baselines_of(project, "W001")]
    assert got == revs == sorted(shuffled, key=old_baseline_key)


def _top_bar_text(revisions: set[str]) -> str:
    from harness_design_studio.gui.main_window import MainWindow

    harnesses = {str(i): SimpleNamespace(version=r) for i, r in enumerate(sorted(revisions))}
    fake: Any = SimpleNamespace(ctl=SimpleNamespace(project=SimpleNamespace(harnesses=harnesses)))
    return MainWindow._revision_text(fake)


def _old_top_bar_text(revisions: set[str]) -> str:
    """`MainWindow._revision_text` before R1: the revisions sorted as text."""
    revs = sorted(revisions)
    if not revs:
        return ""
    return revs[0] if len(revs) == 1 else f"{revs[0]}-{revs[-1]}"


def test_the_top_bar_shows_the_range_as_before_where_the_letters_have_one_length() -> None:
    rng = random.Random(11)
    one = letters("Z")
    two = [r for r in letters("ZZ") if len(r) == 2]
    cases: list[set[str]] = [set(), {"A"}, {"A", "B"}, set(one), set(two)]
    cases += [set(rng.sample(group, rng.randint(1, 8))) for group in (one, two) for _ in range(200)]
    for revs in cases:
        assert _top_bar_text(revs) == _old_top_bar_text(revs), revs


def test_the_top_bar_puts_z_before_aa() -> None:
    # The one place that ordered differently: as text, AA came before Z, so a project with
    # harnesses at revisions Z and AA showed the range "AA-Z" (and "AA-B" for B and AA). It needs
    # 27 revisions of one harness; R1 shows the range in the letter order, as baselines_of does.
    assert _old_top_bar_text({"Z", "AA"}) == "AA-Z"
    assert _top_bar_text({"Z", "AA"}) == "Z-AA"
    assert _top_bar_text({"B", "AA", "C"}) == "B-AA"


def test_the_state_of_a_draft_is_revised_after_the_first_version() -> None:
    # Format 3 (D-242): a harness starts at 1.0.0; a draft at any later version is a new version
    # of a released harness, as a draft at a later letter was in format 2 (A is 1.0.0).
    base = Harness(id="W001", name="W001")
    assert base.version == "1.0.0"
    for version in ["1.0.0", "1.0.1", "1.1.0", "2.0.0", "0.1.0", "27.0.0"]:
        for status in ("draft", "in_review", "released"):
            h = evolve(base, version=version, status=status)
            want = {"released": "released", "in_review": "in-review"}.get(
                status, "draft" if version == "1.0.0" else "revised"
            )
            assert harness_state(h) == want, (version, status)
    assert is_first("1.0.0") and not is_first("1.0.1") and not is_first("2.0.0")


# ---- the next version and the mapping --------------------------------------------------------


@pytest.mark.parametrize(
    "version,kind,after",
    [
        ("1.4.2", "major", "2.0.0"),
        ("1.4.2", "minor", "1.5.0"),
        ("1.4.2", "patch", "1.4.3"),
        ("1.0.0", "patch", "1.0.1"),
        ("1.9.0", "minor", "1.10.0"),
        ("0.0.0", "major", "1.0.0"),
        ("27.0.0", "minor", "27.1.0"),
    ],
)
def test_bump(version: str, kind: Any, after: str) -> None:
    assert bump(version, kind) == after
    assert version_key(after) > version_key(version)


@pytest.mark.parametrize(
    "version,kind",
    [("B", "minor"), ("1.0", "patch"), ("v1.0.0", "major"), ("1.0.0", "breaking"),
     ("9999.0.0", "major"), ("1.9999.0", "minor"), ("1.0.9999", "patch")],
)  # fmt: skip
def test_bump_refuses_what_is_not_a_version_kind_or_in_range(version: str, kind: Any) -> None:
    with pytest.raises(ValueError):
        bump(version, kind)


@pytest.mark.parametrize(
    "revision,version",
    [
        ("A", "1.0.0"),
        ("B", "2.0.0"),
        ("Z", "26.0.0"),
        ("AA", "27.0.0"),
        ("ZZ", "702.0.0"),
        ("NTO", "9999.0.0"),
        ("1.2.0", "1.2.0"),  # already a version: kept
        ("1.10.2", "1.10.2"),
    ],
)
def test_letter_to_version(revision: str, version: str) -> None:
    assert letter_to_version(revision) == version


@pytest.mark.parametrize("revision", ["b", "A1", "01", "-", "1.0", "", "v1.0.0", "NTP", "ZZZ"])
def test_letter_to_version_guesses_nothing(revision: str) -> None:
    assert letter_to_version(revision) is None


def test_the_mapping_keeps_the_order_and_gives_each_letter_its_own_version() -> None:
    mapped = [letter_to_version(r) for r in ALL[:9999]]
    assert len(set(mapped)) == len(mapped) and None not in mapped
    assert sort_versions(m for m in mapped if m) == mapped
    assert [letter_number(r) for r in ALL[:9999]] == [int(m.split(".")[0]) for m in mapped if m]


# ---- the pinout test of section 5.3 -----------------------------------------------------------


def _harness() -> Harness:
    p1 = Connector(id="W001-P1", name="P1", role="cable", part_id="PLUG-9", gender="male",
                   mates_with="BAT1-J01")  # fmt: skip
    p2 = Connector(id="W001-P2", name="P2", role="cable", part_id="PLUG-9", gender="male",
                   mates_with="PCDU1-J09")  # fmt: skip
    x1 = Connector(id="W001-X1", name="X1", role="inline", part_id="INLINE-4", gender="female")
    wires = [
        Wire(id="W001-001", signal="PWR", from_connector="W001-P1", from_pin="1",
             to_connector="W001-P2", to_pin="1", gauge_awg=20),
        Wire(id="W001-002", signal="SIG", from_connector="W001-X1", from_pin="1",
             to_connector="W001-X1", to_pin="2", gauge_awg=24),
    ]  # fmt: skip
    return Harness(id="W001", name="W001", connectors=[p1, p2, x1], wires=wires)


def _snap(h: Harness) -> Snapshot:
    return Snapshot(harnesses=[h])


def _with_connector(h: Harness, cid: str, **changes: Any) -> Harness:
    return evolve(h, connectors=[evolve(c, **changes) if c.id == cid else c for c in h.connectors])


def _with_wire(h: Harness, wid: str, **changes: Any) -> Harness:
    return evolve(h, wires=[evolve(w, **changes) if w.id == wid else w for w in h.wires])


def _changed(before: Harness, after: Harness) -> list[tuple[str, str, str]]:
    return [(c.kind, c.id, c.change) for c in pinout_changes(_snap(before), _snap(after))]


def test_no_change_is_no_pinout_change() -> None:
    h = _harness()
    assert _changed(h, h) == []


@pytest.mark.parametrize(
    "field,value",
    [("part_id", "PLUG-9-B"), ("gender", "female"), ("keying", "K2"), ("mates_with", "BAT2-J01"),
     ("mates_with", None)],
)  # fmt: skip
def test_a_device_end_whose_part_gender_keying_or_mate_changes(field: str, value: Any) -> None:
    h = _harness()
    assert _changed(h, _with_connector(h, "W001-P1", **{field: value})) == [
        ("cable_connector", "W001-P1", "changed")
    ]


def test_an_end_that_starts_to_plug_into_a_device() -> None:
    h = _harness()
    assert _changed(h, _with_connector(h, "W001-X1", mates_with="OBC1-J03")) == [
        ("cable_connector", "W001-X1", "changed")
    ]


def test_other_fields_and_ends_that_plug_into_no_device_are_not_pinout_changes() -> None:
    h = _harness()
    assert _changed(h, _with_connector(h, "W001-P1", name="P1 battery", notes="a note")) == []
    assert _changed(h, _with_connector(h, "W001-X1", part_id="INLINE-6", gender="male")) == []
    for field, value in (("gauge_awg", 22), ("colour", "RD"), ("length_m", 1.5), ("signal", "V")):
        assert _changed(h, _with_wire(h, "W001-001", **{field: value})) == [], field
    # a wire moved between two pins of the inline connector: no device end
    assert _changed(h, _with_wire(h, "W001-002", to_pin="3")) == []


def test_a_wire_added_removed_or_moved_at_a_device_end() -> None:
    h = _harness()
    new = Wire(id="W001-003", from_connector="W001-P1", from_pin="2", to_connector="W001-X1",
               to_pin="3")  # fmt: skip
    assert _changed(h, evolve(h, wires=[*h.wires, new])) == [("wire", "W001-003", "added")]
    assert _changed(evolve(h, wires=[*h.wires, new]), h) == [("wire", "W001-003", "removed")]
    assert _changed(h, _with_wire(h, "W001-001", from_pin="5")) == [("wire", "W001-001", "changed")]
    # an end moved from the inline connector onto a device end, and back
    moved = _with_wire(h, "W001-002", to_connector="W001-P2", to_pin="4")
    assert _changed(h, moved) == [("wire", "W001-002", "changed")]
    assert _changed(moved, h) == [("wire", "W001-002", "changed")]
    # a wire added only between ends that plug into no device
    inner = Wire(id="W001-004", from_connector="W001-X1", from_pin="3", to_connector="W001-X1",
                 to_pin="4")  # fmt: skip
    assert _changed(h, evolve(h, wires=[*h.wires, inner])) == []


def test_a_device_end_added_or_removed() -> None:
    h = _harness()
    p3 = Connector(id="W001-P3", name="P3", role="cable", part_id="PLUG-9", mates_with="OBC1-J01")
    loose = Connector(id="W001-L1", name="L1", role="loose", part_id="TBD-CONNECTOR")
    assert _changed(h, evolve(h, connectors=[*h.connectors, p3])) == [
        ("cable_connector", "W001-P3", "added")
    ]
    assert _changed(evolve(h, connectors=[*h.connectors, p3]), h) == [
        ("cable_connector", "W001-P3", "removed")
    ]
    assert _changed(h, evolve(h, connectors=[*h.connectors, loose])) == []


def test_the_box_connector_itself_is_the_device_not_the_harness() -> None:
    h = _harness()
    box = Connector(id="BAT1-J01", name="J01", role="box", part_id="RCPT-9", unit_id="BAT1")
    before = Snapshot(harnesses=[h], connectors=[box])
    after = Snapshot(harnesses=[h], connectors=[evolve(box, part_id="RCPT-15")])
    assert pinout_changes(before, after) == []


def test_the_note_is_due_for_minor_and_patch_only() -> None:
    h = _harness()
    changes = pinout_changes(_snap(h), _snap(_with_connector(h, "W001-P1", gender="female")))
    assert changes
    assert pinout_note_due("minor", changes) and pinout_note_due("patch", changes)
    assert not pinout_note_due("major", changes)
    for kind in ("major", "minor", "patch"):
        assert not pinout_note_due(kind, [])  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        pinout_note_due("breaking", changes)  # type: ignore[arg-type]


# ---- a new version: the person chooses the kind (section 5.3, format 3) --------------------------------


def _released_project(tmp_path):
    from harness_design_studio.core.commands import History
    from harness_design_studio.core.outputs.build import write_outputs
    from harness_design_studio.core.samples import sat15_full
    from harness_design_studio.core.vcs.release import plan_release

    p = sat15_full()
    hid = next(
        h.id
        for h in sorted(p.harnesses.values(), key=lambda x: x.id)
        if all(w.gauge_awg and w.length_m for w in h.wires)
    )
    folder = tmp_path / "outputs"
    write_outputs(p, folder)
    reason = "Test project: values are placeholders"
    plan = plan_release(
        p, hid, by="Ada", checker="Bob", comment="First release for the CDR", when="2026-03-01",
        outputs_folder=folder, accept_placeholders=reason, accept_unapproved_parts=reason,
    )  # fmt: skip
    assert plan.ok, [b.message for b in plan.blockers]
    History(p).execute(plan.label, plan.ops)
    return p, hid


@pytest.mark.parametrize(
    ("kind", "after"), [("major", "2.0.0"), ("minor", "1.1.0"), ("patch", "1.0.1")]
)
def test_a_new_version_of_each_kind(kind: str, after: str, tmp_path) -> None:
    from harness_design_studio.core.commands import History
    from harness_design_studio.core.vcs.release import plan_new_version

    p, hid = _released_project(tmp_path)
    plan = plan_new_version(p, hid, kind=kind, by="Ada", comment="A change of the harness", when="2026-03-02")  # fmt: skip
    assert plan.ok and plan.label == f"New version {after} of {hid}"
    History(p).execute(plan.label, plan.ops)
    h = p.harnesses[hid]
    assert (h.version, h.status) == (after, "draft")
    entry = max(p.changelog.values(), key=lambda e: e.id)
    assert (entry.kind, entry.version) == ("new_version", after)
    assert f"{hid}.1.0.0" in p.baselines  # the released version stays on record


def test_a_new_version_needs_a_kind_and_a_released_harness(tmp_path) -> None:
    from harness_design_studio.core.samples import mini3
    from harness_design_studio.core.vcs.release import plan_new_version

    p, hid = _released_project(tmp_path)
    plan = plan_new_version(p, hid, kind="huge", by="Ada", comment="A change of the harness", when="2026-03-02")  # fmt: skip
    assert [b.code for b in plan.blockers] == ["kind_unknown"]
    q = mini3()
    plan = plan_new_version(q, "W001", kind="minor", by="Ada", comment="A change of it", when="2026-03-02")  # fmt: skip
    assert [b.code for b in plan.blockers] == ["not_released"]


def test_a_step_back_is_refused(tmp_path) -> None:
    """A version must be higher than every baseline of the harness, also one a merge brought in."""
    from harness_design_studio.core.vcs.release import plan_new_version

    p, hid = _released_project(tmp_path)
    base = p.baselines[f"{hid}.1.0.0"]
    p.baselines[f"{hid}.1.1.0"] = evolve(base, id=f"{hid}.1.1.0", version="1.1.0")  # (a merge)
    plan = plan_new_version(p, hid, kind="minor", by="Ada", comment="A change of the harness", when="2026-03-02")  # fmt: skip
    assert [b.code for b in plan.blockers] == ["version_not_higher"]
    assert "not higher than its baseline 1.1.0" in plan.blockers[0].message
    assert plan_new_version(p, hid, kind="major", by="Ada", comment="A change of the harness", when="2026-03-02").ok  # fmt: skip


def test_the_release_freeze_takes_only_a_higher_version(tmp_path) -> None:
    from harness_design_studio.core.commands import History, Put
    from harness_design_studio.core.errors import TransactionError

    p, hid = _released_project(tmp_path)
    h = p.harnesses[hid]
    history = History(p)
    for version in ("1.0.0", "0.9.0"):
        with pytest.raises(TransactionError):
            history.execute("x", [Put("harnesses", evolve(h, version=version, status="draft"))])
    history.execute("x", [Put("harnesses", evolve(h, version="1.0.1", status="draft"))])


def test_new_version_on_the_command_line_and_revise_as_its_older_name(tmp_path, capsys) -> None:
    from harness_design_studio.cli.main import main
    from harness_design_studio.core.io.loader import load_project
    from harness_design_studio.core.io.saver import save_project

    p, hid = _released_project(tmp_path)
    root = tmp_path / "p"
    save_project(p, root)
    args = [str(root), hid, "--by", "Ada", "--comment", "Rework for the build"]
    assert main(["new-version", *args]) == 2  # --kind is required
    assert "--kind" in capsys.readouterr().err
    assert main(["new-version", *args, "--kind", "minor", "--json", "--date", "2026-04-01"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert (doc["action"], doc["kind"]) == (f"New version 1.1.0 of {hid}", "minor")
    assert list(doc) == ["ok", "action", "by", "kind", "blockers", "outputs"]
    assert load_project(root).project.harnesses[hid].version == "1.1.0"
    from harness_design_studio.cli.main import build_parser

    listing = build_parser().format_help()
    assert "new-version  " in listing or "new-version " in listing
    assert "    revise " not in listing  # the older name is left out of the command list
    q, hid2 = _released_project(tmp_path / "q")
    root2 = tmp_path / "q" / "p"
    save_project(q, root2)
    assert main(["revise", str(root2), hid2, "--by", "Ada", "--comment", "Rework for the build", "--kind", "patch", "--date", "2026-04-01"]) == 0  # fmt: skip
    assert load_project(root2).project.harnesses[hid2].version == "1.0.1"


def test_log_json_and_the_expression_field_carry_both_names(tmp_path, capsys) -> None:
    from harness_design_studio.cli.main import main
    from harness_design_studio.core.extensions.fields import Context, _build
    from harness_design_studio.core.io.saver import save_project

    p, hid = _released_project(tmp_path)
    root = tmp_path / "p"
    save_project(p, root)
    assert main(["log", str(root), "--json"]) == 0
    entries = json.loads(capsys.readouterr().out)["entries"]
    assert entries and all(e["version"] == e["revision"] == "1.0.0" for e in entries)
    h = p.harnesses[hid]
    fields = {f.id: f for f in _build()}
    assert fields["harness.version"].fn(Context(p, harness=h)) == "1.0.0"
    assert fields["harness.revision"].fn(Context(p, harness=h)) == "1.0.0"  # older name (Q29)


def test_the_verifier_refuses_an_export_whose_two_names_differ(tmp_path) -> None:
    from harness_design_studio.core.outputs.build import build_outputs
    from harness_design_studio.core.outputs.verify import verify_outputs
    from harness_design_studio.core.samples import mini3

    p = mini3()
    files = dict(build_outputs(p, drawings=False).files)
    assert verify_outputs(p, files).ok
    doc = json.loads(files["system/export.json"])
    assert all(x["revision"] == x["version"] == "1.0.0" for x in doc["harnesses"])
    doc["harnesses"][0]["revision"] = "2.0.0"
    files["system/export.json"] = json.dumps(doc).encode()
    report = verify_outputs(p, files)
    assert not report.ok and any(i.code == "out_json" for i in report.errors)
