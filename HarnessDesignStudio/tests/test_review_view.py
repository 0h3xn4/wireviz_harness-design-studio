# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The review view of one harness (design of 4.3.0, `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`, sections
4.2 to 4.4 and 10): `vcs.release.harness_findings`, the one selection of the findings of a harness,
and `review.review_view`, which has no caller yet (pull request 1 of the design).

The release gate now takes its rule errors from `harness_findings`; it must give **the same
blockers as before**. `_gate_of_4_2` is the selection the gate wrote inline at 4.2.0, word for word,
and the tests compare it with the blockers of `release_blockers` on every example and fixture
(with errors, waivers and a wrong engineering value added), and with the selection on random
findings. Then the blocks and rows of `flatsat` W002 (section 4.4), of `loose_ends`, `splices` and
`mini3-released`, the counts of section 2.8 on the examples, the state words and the order of the
findings, and `parse_ticked`."""

import tempfile
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from harness_design_studio.core import checks, drc, review, templates
from harness_design_studio.core.checks import Finding
from harness_design_studio.core.commands import Put, apply_ops
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import ConfigFile, Harness, Project, Waiver, evolve
from harness_design_studio.core.samples import mini3, sat15
from harness_design_studio.core.vcs import release
from harness_design_studio.core.vcs.release import Blocker, harness_findings, release_blockers
from harness_design_studio.core.vcs.snapshot import carried_interfaces, related_ids
from tests.loose_support import generated_loose
from tests.row_layout_support import row_layout_project
from tests.splice_support import branch_leg_project
from tools.format3_record import _release_history

EXAMPLES = ("blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat")
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "projects"


def _gate_of_4_2(project: Project, hid: str) -> list[Blocker]:
    """The rule errors of the release gate as `release_blockers` selected them inline at 4.2.0
    (word for word, from `core/vcs/release.py` of the tag v4.2.0)."""
    out: list[Blocker] = []
    h = project.harnesses[hid]
    related = related_ids(project, h)
    carried = carried_interfaces(h)
    for f in drc.run(project):
        if f.severity != "error" or f.waiver is not None:
            continue
        where = drc.locate(project, f.object_id)
        mine = (
            f.object_id in related
            or where == ("harness", hid)
            or (where is not None and where[0] == "interface" and where[1] in carried)
            or f.rule == "config-invalid"  # a wrong engineering value affects every harness
        )
        if mine:
            out.append(Blocker("rule_error", f.title, f.object_id))
    return out


def _old_mine(project: Project, h: Harness, f: Finding) -> bool:
    """The test of 4.2.0 for one finding, without the severity and the waiver."""
    where = drc.locate(project, f.object_id)
    return (
        f.object_id in related_ids(project, h)
        or where == ("harness", h.id)
        or (where is not None and where[0] == "interface" and where[1] in carried_interfaces(h))
        or f.rule == "config-invalid"
    )


def _rule_errors(project: Project, hid: str) -> list[Blocker]:
    found = release_blockers(
        project, hid, by="A. Person", comment="A comment long enough.", when="2026-11-21",
        outputs_folder=None, check_roles=False,
    )  # fmt: skip
    return [b for b in found if b.code == "rule_error"]


def _example(name: str) -> Callable[[Path], Project]:
    def make(tmp: Path) -> Project:
        p = templates.create_project(tmp / name, name)
        if not p.harnesses:
            generate_project(p)
        return p

    return make


def _sample(make: Callable[[], Project]) -> Callable[[Path], Project]:
    def build(tmp: Path) -> Project:
        p = make()
        generate_project(p)
        return p

    return build


def _with_errors(tmp: Path) -> Project:
    """mini3 with errors of every kind of place: a wire that ends on a pin its connector does not
    have (in W001), a wrong engineering value (the whole project), a waived warning, a box connector
    pin twice (on a device connector W002 plugs into) and a part used only by a device."""
    p = mini3()
    generate_project(p)
    h = p.harnesses["W001"]
    w = h.wires[0]
    apply_ops(p, [Put("harnesses", evolve(h, wires=[evolve(w, to_pin="99"), *h.wires[1:]]))])
    derating = p.config["derating"]
    p.config["derating"] = ConfigFile(
        name="derating", placeholder=True, values={**derating.values, "bundle_derating": 5}
    )
    box_id = next(c.mates_with for c in p.harnesses["W002"].connectors if c.mates_with)
    box = p.connectors[box_id]
    apply_ops(p, [Put("connectors", evolve(box, pins=[*box.pins, box.pins[0]]))])
    warning = next(f for f in drc.run(p) if f.severity == "warning" and f.can_waive)
    apply_ops(p, [checks.waive_op(warning, "Accepted for the test of the gate.")])
    return p


PROJECTS: dict[str, Callable[[Path], Project]] = {
    **{f"example-{n}": _example(n) for n in EXAMPLES},
    "mini3": _sample(mini3),
    "sat15": _sample(sat15),
    "fixture-mini3": lambda tmp: load_project(FIXTURES / "mini3").project,
    "fixture-sat15": lambda tmp: load_project(FIXTURES / "sat15").project,
    "custom_device": lambda tmp: load_project(FIXTURES / "custom_device").project,
    "loose_ends": lambda tmp: load_project(generated_loose(tmp / "loose")).project,
    "splices": lambda tmp: branch_leg_project(),
    "row_layout": lambda tmp: row_layout_project(),
    "mini3-released": _release_history,
    "with-errors": _with_errors,
}


@pytest.fixture(scope="module")
def made() -> Iterator[dict[str, Project]]:
    with tempfile.TemporaryDirectory() as tmp:
        yield {name: make(Path(tmp) / name) for name, make in PROJECTS.items()}


# ---- the gate gives the same blockers (section 4.3) ---------------------------------------------


@pytest.mark.parametrize("name", sorted(PROJECTS))
def test_the_gate_gives_the_blockers_of_4_2(made: dict[str, Project], name: str) -> None:
    p = made[name]
    for hid in sorted(p.harnesses):
        assert _rule_errors(p, hid) == _gate_of_4_2(p, hid), (name, hid)


def test_the_project_with_errors_has_errors_on_both_sides_of_the_selection(
    made: dict[str, Project],
) -> None:
    p = made["with-errors"]
    w001 = [b.object_id for b in _rule_errors(p, "W001")]
    w002 = [b.object_id for b in _rule_errors(p, "W002")]
    assert any(oid and oid.startswith("W001-") for oid in w001)  # the wire of W001
    assert "bundle_derating" in " ".join(b.message for b in _rule_errors(p, "W002"))
    assert not any(oid and oid.startswith("W001-") for oid in w002)
    assert any(f.waiver is not None for f in drc.run(p))


@pytest.mark.parametrize("name", sorted(PROJECTS))
def test_the_gates_errors_are_the_open_errors_of_the_view(
    made: dict[str, Project], name: str
) -> None:
    p = made[name]
    found = checks.find(p) + drc.run(p)
    for h in p.harnesses.values():
        view = review.review_view(p, h, found)
        rows = view.block("findings").rows + view.block("project").rows
        stopping = sorted(r.ref for r in rows if r.cells[-1] == review.STOPS)
        gate = sorted(
            f.id
            for f in drc.run(p)
            if f.severity == "error"
            and f.waiver is None
            and any(
                b.object_id == f.object_id and b.message == f.title for b in _gate_of_4_2(p, h.id)
            )
        )
        assert stopping == gate, (name, h.id)


def test_only_a_part_placed_nowhere_is_taken_in_besides_the_selection_of_4_2(
    made: dict[str, Project],
) -> None:
    """The one place `harness_findings` takes more than the gate of 4.2.0: a finding placed nowhere
    whose object is a part the harness uses. Among the rules of the tool only `part-unapproved`
    (a warning) has such findings, so no error of the gate changes."""
    for name, p in made.items():
        found = checks.find(p) + drc.run(p)
        for h in p.harnesses.values():
            for f in harness_findings(p, h, found):
                if not _old_mine(p, h, f):
                    assert f.rule == "part-unapproved" and f.severity == "warning", (name, f.id)
                    assert drc.locate(p, f.object_id) is None


def _objects(p: Project) -> list[str]:
    ids = [*p.units, *p.interfaces, *p.harnesses, *p.connectors, *p.parts]
    for h in p.harnesses.values():
        ids += [c.id for c in h.connectors] + [w.id for w in h.wires] + [s.id for s in h.shields]
        ids += [f"shield-parts.{h.id}.x", f"{h.wires[0].id}.from" if h.wires else h.id]
    ids += [f"wire-spec.{pid}" for pid in p.parts] + ["spare-pins", "design", "NOT-AN-ID"]
    return sorted(set(ids))


_RULES = ("config-invalid", "unchecked-config", "part-unapproved", "wire-dangling", "x-own-rule")


@st.composite
def _findings(draw: st.DrawFn, objects: list[str]) -> list[Finding]:
    out = []
    for n in range(draw(st.integers(0, 12))):
        rule = draw(st.sampled_from(_RULES))
        severity = draw(st.sampled_from(("error", "warning", "info")))
        oid = draw(st.sampled_from(objects))
        waived = draw(st.booleans())
        fid = f"{rule}.{oid}.{n}"
        waiver = (
            Waiver(id=fid, rule=rule, object_id="X", justification="A reason for the test.")
            if waived
            else None
        )
        out.append(Finding(fid, rule, severity, oid, f"Finding {n}", "Why.", waiver=waiver))  # type: ignore[arg-type]
    return out


@pytest.mark.parametrize("name", ["example-flatsat", "loose_ends", "splices", "with-errors"])
def test_on_random_findings_the_selection_is_that_of_4_2_but_for_parts_placed_nowhere(
    made: dict[str, Project], name: str
) -> None:
    p = made[name]
    objects = _objects(p)

    @settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(_findings(objects))
    def check(found: list[Finding]) -> None:
        for h in p.harnesses.values():
            used = {c.part_id for c in h.connectors} | {w.part_id for w in h.wires if w.part_id}
            mine = {id(f) for f in harness_findings(p, h, found)}
            for f in found:
                if f.rule in release.PROJECT_RULES:  # the whole project's: block 3, not the harness
                    assert id(f) not in mine
                if f.rule == "unchecked-config":  # a note always; the gate counts errors only
                    continue
                new = id(f) in mine or f.rule == "config-invalid"
                extra = drc.locate(p, f.object_id) is None and f.object_id in used
                assert new == (_old_mine(p, h, f) or extra), f
            view = review.review_view(p, h, found)
            listed = [r.ref for r in view.block("findings").rows]
            assert sorted(listed) == sorted(f.id for f in found if id(f) in mine)
            assert [r.ref for r in view.block("project").rows] == [
                f.id for f in sorted(found, key=review._rank) if f.rule in release.PROJECT_RULES
            ]

    check()


# ---- the blocks of flatsat W002 (section 4.4) and the counts of section 2.8 ---------------------


def test_the_blocks_of_flatsat_w002(made: dict[str, Project]) -> None:
    p = made["example-flatsat"]
    found = checks.find(p) + drc.run(p)
    v = review.review_view(p, p.harnesses["W002"], found)
    assert v.title == "Review of W002  aocs to bus" and (v.version, v.status) == ("1.0.0", "draft")
    assert v.release == "Release: not released yet." and v.points == () and v.list_hash == ""
    assert [b.key for b in v.blocks] == [
        "checklist",
        "findings",
        "project",
        "open",
        "sources",
        "how",
    ]
    checklist = v.block("checklist")
    assert checklist.rows == () and checklist.empty == review.NO_CHECKLIST
    findings = v.block("findings")
    assert findings.heading == "Findings of W002: 0 errors, 7 warnings, 11 notes open; 0 waived, 0 accepted as deviations"  # fmt: skip
    assert findings.columns == ("Severity", "Rule", "Finding", "Object", "Finding text", "State", "Release")  # fmt: skip
    rows = [r.cells for r in findings.rows]
    assert rows[0] == (
        "warning", "connector-lookalike", "connector-lookalike.PDU2-J01", "PDU2-J01",
        rows[0][4], "open", "",
    )  # fmt: skip
    assert [r[2] for r in rows[1:7]] == [
        "part-unapproved.EX-MICROD-15-M", "part-unapproved.EX-MICROD-21-M",
        "part-unapproved.EX-MICROD-31-M", "part-unapproved.EX-MICROD-9-M",
        "part-unapproved.EX-WIRE-SINGLE", "part-unapproved.EX-WIRE-TWISTED-SHIELDED",
    ]  # fmt: skip
    assert all(r[6] == "needs a written reason" for r in rows[1:7])
    assert [r[2] for r in rows[7:]] == [f"unconfirmed.IF-{n}" for n in ("009", "027", "029", "030", "031", "032", "034", "035", "038", "039", "040")]  # fmt: skip
    assert all(r[0] == "note" and r[4] == f"{r[3]} uses connectors the tool chose for you" for r in rows[7:])  # fmt: skip
    project = v.block("project")
    assert [r.cells[2] for r in project.rows] == [
        "unchecked-config.emc", "unchecked-config.separation", "unchecked-config.spare-pins",
    ]  # fmt: skip
    assert project.rows[2].cells == (
        "note", "unchecked-config", "unchecked-config.spare-pins",
        "Spare pins were not checked: the required fraction is still a placeholder", "",
    )  # fmt: skip
    open_ = {r.cells[0]: r.cells for r in v.block("open").rows}
    assert list(open_) == [
        "Configuration files still placeholders", "Engineering values not set",
        "Wires without a gauge", "Wires without a colour", "Pins in use without a termination",
        "Wires without strip lengths", "Pins in use without a contact part",
        "Interface types marked as example data",
    ]  # fmt: skip
    assert open_["Configuration files still placeholders"][1:] == (
        6, "config/derating.json, config/emc.json, config/generation.json, config/segmentation.json, "
        "config/segregation.json, config/titleblock.json", "harness-design-studio config DIR",
        "needs a written reason",
    )  # fmt: skip
    assert open_["Engineering values not set"][1:3] == (
        4, "derating.spare_pin_fraction, generation.power_signal_gap_pins, "
        "segregation.category_pairs_to_separate, emc.conflicting_class_pairs",
    )  # fmt: skip
    assert open_["Wires without a gauge"][1:] == (
        24, "W002-003, W002-004, W002-005, W002-006, W002-007 and 19 more", "Cut list, Production",
        "stops the release",
    )  # fmt: skip
    counts = {k: c[1] for k, c in open_.items()}
    assert counts["Wires without a colour"] == 13 and counts["Wires without strip lengths"] == 26
    assert counts["Pins in use without a termination"] == counts["Pins in use without a contact part"] == 52  # fmt: skip
    assert open_["Pins in use without a contact part"][3] == "Connectors"
    assert open_["Interface types marked as example data"][1:4] == (
        5, "analog, can, discrete, power_primary, rs422", "logical/interface_types.json",
    )  # fmt: skip
    sources = v.block("sources").rows
    boxes = [r.cells for r in sources if r.cells[0] == "Device connector"]
    parts = [r.cells for r in sources if r.cells[0] == "Part"]
    assert len(boxes) == 22 and len(parts) == 6
    assert ("Device connector", "PDU2-J01", "PDU2:J01", "not named", "", "") in boxes
    assert all(r[2] == "pending (example data)" and r[5] == "" for r in parts)
    assert [r[1] for r in parts][:2] == ["EX-MICROD-9-M", "EX-MICROD-15-M"]  # natural ID order
    assert [r.cells for r in v.block("how").rows] == [(line,) for line in review.HOW_LINES]


@pytest.mark.parametrize(
    ("name", "harnesses", "findings", "whole", "open_rows", "open_most", "sources", "sources_most"),
    [
        ("example-first-steps", 2, {"info": 2, "warning": 5}, 6, 18, 9, 9, 5),
        ("example-minimal-satellite", 11, {"info": 11, "warning": 30}, 6, 99, 9, 49, 5),
        ("example-small-satellite", 24, {"info": 24, "warning": 66}, 4, 216, 9, 107, 5),
        ("example-flatsat", 8, {"info": 44, "warning": 46}, 3, 61, 8, 120, 28),
    ],
)  # fmt: skip
def test_the_counts_of_section_2_8(
    made: dict[str, Project], name: str, harnesses: int, findings: dict[str, int], whole: int,
    open_rows: int, open_most: int, sources: int, sources_most: int,
) -> None:  # fmt: skip
    p = made[name]
    found = checks.find(p) + drc.run(p)
    views = [review.review_view(p, h, found) for h in p.harnesses.values()]
    assert len(views) == harnesses
    severities = Counter(r.cells[0] for v in views for r in v.block("findings").rows)
    assert severities == Counter({"note": findings["info"], "warning": findings["warning"]})
    assert {len(v.block("project").rows) for v in views} == {whole}
    assert sum(len(v.block("open").rows) for v in views) == open_rows
    assert max(len(v.block("open").rows) for v in views) == open_most
    assert sum(len(v.block("sources").rows) for v in views) == sources
    assert max(len(v.block("sources").rows) for v in views) == sources_most
    assert all(v.block("checklist").rows == () for v in views)


def test_the_blank_example_has_no_harness(made: dict[str, Project]) -> None:
    assert made["example-blank"].harnesses == {}


# ---- loose ends, splices, a release history (section 10) ----------------------------------------


def test_a_loose_end_is_an_end_not_decided_and_its_tbd_part(made: dict[str, Project]) -> None:
    p = made["loose_ends"]
    found = checks.find(p) + drc.run(p)
    v = review.review_view(p, p.harnesses["W011"], found)
    open_ = {r.cells[0]: r.cells for r in v.block("open").rows}
    assert open_["Ends not decided"][1:] == (2, "W011-P1, W011-P2", "Production", "needs a written reason")  # fmt: skip
    tbd = [
        r.cells for r in v.block("findings").rows if r.cells[2] == "part-unapproved.TBD-CONNECTOR"
    ]
    assert tbd and tbd[0][6] == "needs a written reason"
    assert ("Part", "TBD-CONNECTOR") in {r.cells[:2] for r in v.block("sources").rows}
    # a harness drawn by hand carries no interface: no row of interface types
    assert "Interface types marked as example data" not in open_
    assert "Ends not decided" not in {r.cells[0] for r in review.review_view(p, p.harnesses["W001"], found).block("open").rows}  # fmt: skip


def test_the_harnesses_of_splices(made: dict[str, Project]) -> None:
    p = made["splices"]
    found = checks.find(p) + drc.run(p)
    v = review.review_view(p, p.harnesses["W003"], found)
    assert [r.cells[2] for r in v.block("findings").rows] == [
        "part-unapproved.EX-MICROD-15-M", "part-unapproved.EX-MICROD-9-M", "part-unapproved.EX-SPLICE-1",
    ]  # fmt: skip
    assert [r.cells[:3] for r in v.block("sources").rows] == [
        ("Device connector", "OBC-J02", "OBC:J02"), ("Device connector", "OBC-J03", "OBC:J03"),
        ("Device connector", "PCDU-J02", "PCDU:J02"), ("Part", "EX-MICROD-9-M", "pending (example data)"),
        ("Part", "EX-MICROD-15-M", "pending (example data)"), ("Part", "EX-SPLICE-1", "pending (example data)"),
    ]  # fmt: skip
    assert "unchecked-config.wire-interface" in {r.ref for r in v.block("project").rows}


def test_a_released_harness_names_its_release_entry(made: dict[str, Project]) -> None:
    p = made["mini3-released"]
    found = checks.find(p) + drc.run(p)
    w001 = review.review_view(p, p.harnesses["W001"], found)
    entry = max(
        (e for e in p.changelog.values() if e.kind == "release" and e.harness_id == "W001"),
        key=lambda e: e.id,
    )
    assert (w001.version, w001.status) == ("2.0.0", "released") and entry.version == "2.0.0"
    assert w001.release == (
        f"Release: version 2.0.0 released on 2026-04-02 by Ada, checked by Bob. Comment: {entry.comment}"
    )
    assert entry.comment.startswith("Release for the review [Released on placeholder configuration")
    w002 = review.review_view(p, p.harnesses["W002"], found)
    assert w002.release == "Release: not released yet."


def test_a_new_version_shows_no_older_release(made: dict[str, Project]) -> None:
    p = made["mini3-released"]
    h = p.harnesses["W001"]
    draft = evolve(h, version="3.0.0", status="draft")
    assert review.review_view(p, draft, []).release == "Release: not released yet."


# ---- the rows of a finding: order, state, release (section 4.2, block 2) ------------------------


def _finding(
    rule: str, severity: str, oid: str, *, waived: str = "", changed: bool = False
) -> Finding:
    waiver = (
        Waiver(id=f"{rule}.{oid}", rule=rule, object_id=oid, justification=waived)
        if waived
        else None
    )
    return Finding(
        f"{rule}.{oid}", rule, severity, oid, f"Title of {oid}", "Why.",  # type: ignore[arg-type]
        waiver=waiver, waiver_changed=changed,
    )  # fmt: skip


def test_the_order_the_states_and_the_release_column(made: dict[str, Project]) -> None:
    p = made["mini3"]
    h = p.harnesses["W001"]
    w = h.wires
    part = h.connectors[0].part_id
    found = [
        _finding("pin-floating", "warning", w[1].id, waived="Spare by design."),
        _finding("current-over-wire", "error", w[0].id, waived="Analysed in the note."),
        _finding("part-unapproved", "warning", part, waived="Approved later."),
        _finding("pin-shared", "warning", w[0].id, changed=True),
        _finding("wire-dangling", "error", w[1].id),
        _finding("unconfirmed", "info", h.id),
        _finding("config-invalid", "error", "derating.bundle_derating"),
        _finding("unchecked-config", "info", "spare-pins"),
    ]
    v = review.review_view(p, h, found)
    block = v.block("findings")
    assert block.heading == f"Findings of {h.id}: 1 error, 1 warning, 1 note open; 2 waived, 1 accepted as a deviation"  # fmt: skip
    assert [(r.cells[1], r.cells[5], r.cells[6]) for r in block.rows] == [
        ("wire-dangling", "open", "stops the release"),
        ("pin-shared", "open: its waiver no longer applies (the finding changed)", ""),
        ("unconfirmed", "open", ""),
        ("current-over-wire", "accepted as a deviation: Analysed in the note.", ""),
        ("part-unapproved", "waived: Approved later.", "needs a written reason"),
        ("pin-floating", "waived: Spare by design.", ""),
    ]
    assert [r.cells[0] for r in block.rows] == [
        "error",
        "warning",
        "note",
        "error",
        "warning",
        "warning",
    ]
    project = v.block("project")
    assert [(r.cells[0], r.cells[1], r.cells[4]) for r in project.rows] == [
        ("error", "config-invalid", "stops the release"), ("note", "unchecked-config", ""),
    ]  # fmt: skip
    none = review.review_view(p, h, [])
    assert none.block("findings").rows == () and none.block("project").rows == ()
    assert none.block("findings").empty == (
        f"No finding of the design rules, the verifier or the logical checks is about {h.id} or what it carries."
    )
    assert none.block("project").empty == "No finding is about the whole project."


def test_a_finding_on_an_interface_two_harnesses_carry_is_on_both(made: dict[str, Project]) -> None:
    p = made["example-flatsat"]
    by_interface: dict[str, list[str]] = {}
    for h in p.harnesses.values():
        for i in carried_interfaces(h):
            by_interface.setdefault(i, []).append(h.id)
    shared = next((i for i, hs in sorted(by_interface.items()) if len(hs) > 1), None)
    if shared is None:  # flatsat routes every interface in one harness: make one on a box instead
        box = next(c.mates_with for c in p.harnesses["W002"].connectors if c.mates_with)
        found = [_finding("x-own-rule", "warning", box)]
        owners = [h.id for h in p.harnesses.values() if harness_findings(p, h, found)]
        assert "W002" in owners
        return
    found = [_finding("x-own-rule", "warning", shared)]
    owners = [h.id for h in p.harnesses.values() if harness_findings(p, h, found)]
    assert owners == by_interface[shared]


# ---- the checklist and the open values with settings --------------------------------------------


def test_the_checklist_block_with_a_list(made: dict[str, Project]) -> None:
    p = made["mini3"]
    naming = p.config["naming"]
    p.config["naming"] = ConfigFile(
        name="naming", placeholder=False,
        values={**naming.values, "review_checklist": ["Only point."]},
    )  # fmt: skip
    try:
        v = review.review_view(p, p.harnesses["W001"], [])
        digest = review.list_hash(["Only point."])
        block = v.block("checklist")
        assert v.points == ("Only point.",) and v.list_hash == digest
        assert block.heading == f"Checklist: 1 point (config/naming.json review_checklist, list {digest})"  # fmt: skip
        assert block.columns == ("No.", "Point", "Done (x)", "Note")
        assert [r.cells for r in block.rows] == [(1, "Only point.", "", "")]  # no point is ticked
    finally:
        p.config["naming"] = naming


def test_overrides_and_the_as_built_gate_are_rows_only_when_there(tmp_path: Path) -> None:
    p = mini3()
    generate_project(p)
    h = p.harnesses["W001"]
    v = review.review_view(p, h, [])
    whats = {r.cells[0] for r in v.block("open").rows}
    assert "Values set by hand (overrides)" not in whats and "As-built records" not in whats
    w = evolve(
        h.wires[0], gauge_awg=20, locked=True, overrides={"gauge_awg": "Chosen by the engineer."}
    )
    apply_ops(p, [Put("harnesses", evolve(h, wires=[w, *h.wires[1:]]))])
    naming = p.config["naming"]
    p.config["naming"] = ConfigFile(
        name="naming", placeholder=False, values={**naming.values, "release_requires_asbuilt": True}
    )
    rows = {
        r.cells[0]: r.cells
        for r in review.review_view(p, p.harnesses["W001"], []).block("open").rows
    }
    assert rows["Values set by hand (overrides)"][1] == 1
    assert str(rows["Values set by hand (overrides)"][2]).startswith(
        f"OVERRIDE {w.id} gauge_awg = 20: Chosen"
    )
    assert rows["As-built records"][1:] == ("no records", "nothing is recorded yet", "As-built", "needs a written reason")  # fmt: skip


def test_nothing_open_and_no_source(made: dict[str, Project]) -> None:
    p = made["mini3"]
    bare = Harness(id="W099", name="Empty", generated=False)
    v = review.review_view(p, bare, [])
    assert {r.cells[0] for r in v.block("open").rows} <= {
        "Configuration files still placeholders", "Engineering values not set",
    }  # fmt: skip
    assert v.block("sources").rows == ()
    assert v.block("sources").empty == "W099 plugs into no device connector and uses no part."
    assert v.block("open").empty == "Nothing is open."


# ---- parse_ticked (section 6.2) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "n", "ticked"),
    [
        ("all", 3, {1, 2, 3}), ("ALL ", 3, {1, 2, 3}), ("none", 3, set()), ("all", 0, set()),
        ("1-5,7,9-14", 26, {1, 2, 3, 4, 5, 7, 9, 10, 11, 12, 13, 14}), (" 2 , 4 - 5 ", 5, {2, 4, 5}),
        ("3", 3, {3}), ("1,1,1-2", 2, {1, 2}),
    ],
)  # fmt: skip
def test_parse_ticked(text: str, n: int, ticked: set[int]) -> None:
    assert review.parse_ticked(text, n) == frozenset(ticked)


@pytest.mark.parametrize(
    ("text", "n", "got"),
    [("27", 26, "27"), ("0", 3, "0"), ("1-5,7", 4, "1-5"), ("5-1", 6, "5-1"), ("1,,2", 3, ""),
     ("", 3, ""), ("one", 3, "one"), ("1-", 3, "1-"), ("1.5", 3, "1.5"), ("1", 0, "1"), ("-1", 3, "-1")],
)  # fmt: skip
def test_parse_ticked_refuses_with_the_text_of_the_design(text: str, n: int, got: str) -> None:
    with pytest.raises(review.TickedError) as err:
        review.parse_ticked(text, n)
    assert err.value.got == got
    assert str(err.value) == (
        f"--ticked must be all, none, or point numbers from 1 to {n} such as 1-5,7 (got '{got}')."
    )
