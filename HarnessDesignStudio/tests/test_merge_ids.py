# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,union-attr,arg-type,index,type-arg"
"""REQ-MIGRATE-07, M7b (D-231): two Git branches each make a harness or a link with the same ID (`W003`, `L1`).
Git stops on the files (a harness file both added, the list of links); `merge-fix` keeps this
branch's object under the ID, gives the other branch's the next free one, changes every entry of
the other branch that names it, prints the renames and journals them, and refuses a release
history. The merges are real ones, made with the `git` program (skipped when it is not
installed); the tool itself reads Git's files and never starts `git` (D-164)."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from harness_design_studio.cli.main import main
from harness_design_studio.core import journal
from harness_design_studio.core.checks import finding_id
from harness_design_studio.core.commands import History
from harness_design_studio.core.edit import ops_add_interface
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.links import plan_add_link, plan_create_harness
from harness_design_studio.core.manual_harness import plan_cable_from_port
from harness_design_studio.core.merge_ids import plan_id_fix
from harness_design_studio.core.mergefix import (
    conflict_files,
    plan_merge_fix,
    take_our_side,
    take_their_side,
)
from harness_design_studio.core.model import Baseline, Waiver, evolve
from harness_design_studio.core.model.review import DiagramMark
from harness_design_studio.core.vcs import gitobjects
from harness_design_studio.core.vcs.hashing import content_hash
from harness_design_studio.core.vcs.snapshot import snapshot_for
from tests.test_gitinfo import needs_git
from tests.test_journal import Clock
from tests.test_merge_fix import git, tree

pytestmark = needs_git


@pytest.fixture
def clock(monkeypatch):
    return Clock(monkeypatch)


# ---- how the branches are made ---------------------------------------------------------------------


def start(root: Path, *, generate: bool = True, links: int = 0) -> Path:
    """A repository with the project `design` (template first-steps, generated: W001 and W002),
    committed on `main`. With `links`, that many links between free connectors first."""
    git(root, "init", "-q", "-b", "main")
    design = root / "design"
    assert main(["new", str(design), "--template", "first-steps"]) == 0
    if generate:
        assert main(["generate", str(design)]) == 0
    for a, b in [("OBC1-J03", "PCDU1-J03"), ("OBC1-J02", "PCDU1-J02")][:links]:
        edit(design, lambda p, a=a, b=b: plan_add_link(p, a, b, PAIRS)[0])
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    return design


def edit(design: Path, ops_of: Callable) -> None:
    p = load_project(design).project
    History(p).execute("edit", ops_of(p))
    save_project(p, design)


def branch(root: Path, name: str, *steps: Callable[[Path], None]) -> None:
    git(root, "checkout", "-q", "main")
    git(root, "checkout", "-q", "-b", name)
    journal.set_author(name)
    try:
        for step in steps:
            step(root / "design")
    finally:
        journal.set_author(None)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", name)


def merge(root: Path, *, clean: bool = False) -> Path:
    """Bob, on `bob`, merges Ann's branch `ann`."""
    git(root, "checkout", "-q", "bob")
    done = git(root, "merge", "--no-edit", "ann", check=False)
    assert (done.returncode == 0) == clean, done.stdout + done.stderr
    return root / "design"


def interface(type_id: str, a: str, b: str, ca: str | None = None, cb: str | None = None, iid=None):
    def step(design: Path) -> None:
        edit(design, lambda p: ops_add_interface(p, type_id, a, b, ca, cb, interface_id=iid)[0])
        assert main(["generate", str(design)]) == 0

    return step


def cable(port: str):
    def step(design: Path) -> None:
        edit(design, lambda p: plan_cable_from_port(p, port).ops)

    return step


PAIRS = [("1", "1"), ("2", "2")]


def link(a: str, b: str, pairs=PAIRS):
    def step(design: Path) -> None:
        edit(design, lambda p: plan_add_link(p, a, b, pairs)[0])

    return step


def harness_from(link_id: str):
    def step(design: Path) -> None:
        edit(design, lambda p: plan_create_harness(p, link_id)[0])

    return step


def mark(mark_id: str, dx: float):
    def step(design: Path) -> None:
        p = load_project(design).project
        p.diagram_marks[mark_id] = DiagramMark(id=mark_id, dx=dx, dy=1.0)
        save_project(p, design)

    return step


def waive(object_id: str, rule: str = "wire-length"):
    def step(design: Path) -> None:
        p = load_project(design).project
        w = Waiver(
            id=finding_id(rule, object_id),
            rule=rule,
            object_id=object_id,
            justification="Accepted for the test of a merge.",
            finding_hash="0123456789ab",
        )
        p.waivers[w.id] = w
        save_project(p, design)

    return step


def files(design: Path, rel: str) -> dict:
    return json.loads((design / rel).read_text(encoding="utf-8"))


def validate_clean(design: Path, capsys) -> str:
    capsys.readouterr()
    assert main(["validate", str(design)]) == 0
    out = capsys.readouterr().out
    assert " 0 error(s), 0 warning(s)." in out, out
    return out


def two_generated(root: Path) -> Path:
    """(a): each branch adds an interface (different ones) and presses Generate: both get W003."""
    start(root)
    branch(root, "ann", interface("power_primary", "PCDU1", "OBC1", iid="IF-003"))
    branch(root, "bob", interface("rs422", "OBC1", "PCDU1", "OBC1-J03", "PCDU1-J03", "IF-004"))
    return merge(root)


# ---- what happens without the fix: the findings of D-231 ----------------------------------------------


def test_a_both_generate_W003_git_stops_on_the_harness_and_validate_names_it(
    tmp_path, clock, capsys
):
    design = two_generated(tmp_path)
    stages = gitobjects.stages(gitobjects.open_repo(design))
    assert stages["physical/harnesses/W003.json"].keys() == {2, 3}  # added on both: add/add
    assert set(stages["generated/generation.json"]) == {1, 2, 3}
    assert conflict_files(design) == ["generated/generation.json", "physical/harnesses/W003.json"]
    capsys.readouterr()
    assert main(["validate", str(design)]) == 1
    out = capsys.readouterr().out
    assert "merge_conflict" in out and "[physical/harnesses/W003.json]" in out
    assert load_project(design).project.recovered  # the editor opens it in recovery mode


def test_c_both_add_a_link_git_stops_on_the_list_of_links(tmp_path, clock):
    start(tmp_path)
    branch(tmp_path, "ann", link("OBC1-J03", "PCDU1-J03"))
    branch(tmp_path, "bob", link("OBC1-J02", "PCDU1-J02"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["logical/links.json"]
    assert gitobjects.stages(gitobjects.open_repo(design))["logical/links.json"].keys() == {2, 3}


def test_d_the_same_harness_on_both_branches_merges_without_a_conflict(tmp_path, clock, capsys):
    start(tmp_path)
    branch(tmp_path, "ann", cable("OBC1-J02"))
    branch(tmp_path, "bob", cable("OBC1-J02"))
    design = merge(tmp_path, clean=True)
    assert conflict_files(design) == []
    validate_clean(design, capsys)
    assert main(["merge-fix", str(design)]) == 0
    assert "W003" in load_project(design).project.harnesses
    assert "W004" not in load_project(design).project.harnesses


# ---- (a) generated harnesses ---------------------------------------------------------------------------


def test_a_merge_fix_renames_the_other_branchs_harness_and_everything_in_it(
    tmp_path, clock, capsys
):
    design = two_generated(tmp_path)
    ours = take_our_side((design / "physical/harnesses/W003.json").read_bytes())
    theirs = json.loads(take_their_side((design / "physical/harnesses/W003.json").read_bytes()))
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "Renamed (the other branch's; this branch's keep their IDs):" in out
    assert "  harness W003 -> W004\n" in out and "    W003-P1 -> W004-P1\n" in out
    assert (design / "physical/harnesses/W003.json").read_bytes() == ours  # ours as it was
    new = files(design, "physical/harnesses/W004.json")
    assert new["id"] == "W004" and new["group_key"] == theirs["group_key"]
    assert [c["id"] for c in new["connectors"]] == [
        c["id"].replace("W003", "W004") for c in theirs["connectors"]
    ]
    for w in new["wires"]:
        assert w["id"].startswith("W004-") and w["interface_id"] == "IF-003"  # Ann's
        assert w["from_connector"].startswith("W004-") or "-J" in w["from_connector"]
    validate_clean(design, capsys)
    p = load_project(design).project
    assert set(p.harnesses) == {"W001", "W002", "W003", "W004"}
    assert {i for h in p.harnesses.values() for i in h.interfaces} == {
        "IF-001", "IF-002", "IF-003", "IF-004",
    }  # fmt: skip
    # the journal: the merge entry, then one entry that names the renames
    entries = list(p.journal)
    assert entries[-1].kind == "edit" and entries[-1].field == "ids"
    assert entries[-1].new == {"renamed": {"W003": "W004"}}
    assert "W003 -> W004" in entries[-1].reason
    assert any(e.kind == "merge" for e in entries[-3:])
    assert len(p.journal.heads()) == 1
    # generate keeps both harnesses, the outputs are written and verified
    capsys.readouterr()
    assert main(["generate", str(design)]) == 0
    assert "0 added, 0 changed, 4 unchanged, 0 removed" in capsys.readouterr().out
    assert main(["export", str(design)]) == 0
    assert main(["verify", str(design), "--outputs"]) == 0
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "merged")
    assert conflict_files(design) == []


def test_a_generated_harness_renamed_without_a_record_conflict_is_generated_again(
    tmp_path, clock, capsys
):
    """Bob draws a cable (W003) and does not press Generate; Ann adds an interface and does (W003):
    the record merges as Ann's, and names W003's wires. merge-fix renames Ann's harness and runs
    generate, so the record names W004."""
    start(tmp_path)
    branch(tmp_path, "ann", interface("power_primary", "PCDU1", "OBC1", iid="IF-003"))
    branch(tmp_path, "bob", cable("OBC1-J03"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["physical/harnesses/W003.json"]
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "  harness W003 -> W004\n" in out and "0 added, 0 changed, 3 unchanged" in out
    record = (design / "generated/generation.json").read_text()
    assert "W004-001" in record and "W003-001" not in record
    p = load_project(design).project
    assert p.harnesses["W004"].generated and not p.harnesses["W003"].generated
    validate_clean(design, capsys)


def test_a_dry_run_shows_the_plan_and_writes_nothing(tmp_path, clock, capsys):
    design = two_generated(tmp_path)
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "  harness W003 -> W004\n" in out and "Dry run: nothing was written." in out
    assert "Then it would run generate and check." in out
    assert tree(design) == before
    assert main(["merge-fix", str(design), "--dry-run", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["result"] == "planned" and doc["dry_run"] is True
    assert [(r["kind"], r["old"], r["new"]) for r in doc["renamed"]] == [
        ("harness", "W003", "W004")
    ]
    assert {"old": "W003-P1", "new": "W004-P1"} in doc["renamed"][0]["parts"]
    assert tree(design) == before


def test_a_json_of_the_fix_lists_the_renames(tmp_path, clock, capsys):
    design = two_generated(tmp_path)
    capsys.readouterr()
    assert main(["merge-fix", str(design), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["result"] == "fixed" and doc["dry_run"] is False and doc["check"]["ok"]
    assert [(r["kind"], r["old"], r["new"]) for r in doc["renamed"]] == [
        ("harness", "W003", "W004")
    ]


def test_the_same_input_gives_the_same_renames_and_bytes(tmp_path, clock):
    plans = []
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        clock.n = 0
        design = two_generated(root)
        plan = plan_merge_fix(design)
        assert plan_merge_fix(design).ids == plan.ids  # read-only: the same twice
        plans.append(plan.ids)
    assert plans[0].renames == plans[1].renames
    assert plans[0].writes == plans[1].writes


def test_both_generate_for_the_same_group_is_refused(tmp_path, clock, capsys):
    """With one harness per pair of devices, Ann and Bob each add an interface between PCDU1 and
    OBC1: Generate makes W003 for the same group on both branches. Renaming one would leave two
    harnesses that Generate makes for one group, so a person chooses."""
    git(tmp_path, "init", "-q", "-b", "main")
    design = tmp_path / "design"
    assert main(["new", str(design), "--template", "first-steps"]) == 0
    path = design / "config/segmentation.json"
    doc = json.loads(path.read_text())
    doc["values"]["mode"] = "per_unit_pair"
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    assert main(["generate", str(design)]) == 0
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "start")
    branch(tmp_path, "ann", interface("power_primary", "PCDU1", "OBC1", iid="IF-003"))
    branch(tmp_path, "bob", interface("rs422", "OBC1", "PCDU1", "OBC1-J03", "PCDU1-J03", "IF-004"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["generated/generation.json", "physical/harnesses/W003.json"]
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 1
    err = capsys.readouterr().err
    assert "let Generate make harness W003 for the same group" in err
    assert "Nothing was changed." in err
    assert tree(design) == before


def test_an_interface_id_on_both_branches_is_set_aside_and_merge_fix_undoes(
    tmp_path, clock, capsys
):
    """Both branches let the tool choose the interface ID: IF-003 in two files of different
    subsystems merges without a conflict, the loader sets one aside, and merge-fix puts every file
    back (interface IDs are not renamed; D-231, Not done)."""
    start(tmp_path)
    branch(tmp_path, "ann", interface("power_primary", "PCDU1", "OBC1"))
    branch(tmp_path, "bob", interface("rs422", "OBC1", "PCDU1", "OBC1-J03", "PCDU1-J03"))
    design = merge(tmp_path)
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 2
    err = capsys.readouterr().err
    assert "duplicate ID 'IF-003'" in err and "merge-fix changed nothing" in err
    assert tree(design) == before
    assert not (design / "physical/harnesses/W004.json").exists()


# ---- (b) harnesses drawn by hand ------------------------------------------------------------------------


@pytest.mark.parametrize("ours_moved", [False, True])
def test_b_a_hand_drawn_harness_and_the_place_of_its_loose_end(tmp_path, clock, capsys, ours_moved):
    start(tmp_path)
    branch(tmp_path, "ann", cable("PCDU1-J02"), mark("pos:W003-P2", 40.0))
    bob = [cable("OBC1-J02")] + ([mark("pos:W003-P2", -25.0)] if ours_moved else [])
    branch(tmp_path, "bob", *bob)
    design = merge(tmp_path)
    expected = ["physical/harnesses/W003.json"] + (["diagram/marks.json"] if ours_moved else [])
    assert conflict_files(design) == sorted(expected)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "Harnesses W003 and W004 are both called 'Cable 1'" in out
    assert "diagram/marks.json: diagram mark pos:W003-P2 -> pos:W004-P2" in out
    marks = {m["id"]: m for m in files(design, "diagram/marks.json")["marks"]}
    assert marks["pos:W004-P2"]["dx"] == 40.0  # Ann's loose end keeps its place
    assert ("pos:W003-P2" in marks) == ours_moved
    if ours_moved:
        assert marks["pos:W003-P2"]["dx"] == -25.0
    p = load_project(design).project
    assert p.harnesses["W003"].connectors[0].mates_with == "OBC1-J02"
    assert p.harnesses["W004"].connectors[0].mates_with == "PCDU1-J02"
    validate_clean(design, capsys)


# ---- (c) links -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("existing", [0, 1])
def test_c_the_other_branchs_link_gets_the_next_free_id(tmp_path, clock, capsys, existing):
    """With no link before (both added the file) and with one (L1 both started from; both add L2
    at the same place of the list, and the common version is read from Git's objects)."""
    start(tmp_path, links=existing)
    pairs = [("OBC1-J02", "PCDU1-J02"), ("OBC1-J02", "PCDU1-J02")] if existing else [
        ("OBC1-J03", "PCDU1-J03"), ("OBC1-J02", "PCDU1-J02"),
    ]  # fmt: skip
    new_id = f"L{existing + 1}"
    branch(tmp_path, "ann", link(*pairs[0], [("3", "3")]), mark(f"bend:{new_id}", 12.0))
    branch(tmp_path, "bob", link(*pairs[1], [("4", "4")]))
    design = merge(tmp_path)
    assert "logical/links.json" in conflict_files(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    after = f"L{existing + 2}"
    assert f"  link {new_id} -> {after}\n" in out
    links = {x["id"]: x for x in files(design, "logical/links.json")["links"]}
    assert links[new_id]["pairs"] == [{"a_pin": "4", "b_pin": "4"}]  # Bob's
    assert links[after]["pairs"] == [{"a_pin": "3", "b_pin": "3"}]  # Ann's
    marks = {m["id"] for m in files(design, "diagram/marks.json")["marks"]}
    assert marks == {f"bend:{after}"}
    validate_clean(design, capsys)
    assert list(load_project(design).project.journal)[-1].new == {"renamed": {new_id: after}}


def test_c_and_b_a_link_and_the_harness_made_from_it_on_each_branch(tmp_path, clock, capsys):
    start(tmp_path)
    branch(tmp_path, "ann", link("OBC1-J03", "PCDU1-J03"), harness_from("L1"))
    branch(tmp_path, "bob", link("OBC1-J02", "PCDU1-J02"), harness_from("L1"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["logical/links.json", "physical/harnesses/W003.json"]
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "  harness W003 -> W004\n" in out and "  link L1 -> L2\n" in out
    links = {x["id"]: x for x in files(design, "logical/links.json")["links"]}
    assert links["L1"]["harness_id"] == "W003" and links["L2"]["harness_id"] == "W004"
    validate_clean(design, capsys)
    assert list(load_project(design).project.journal)[-1].new == {
        "renamed": {"L1": "L2", "W003": "W004"}
    }


def test_a_link_that_merged_without_a_conflict_is_told_apart_by_this_branchs_commit(
    tmp_path, clock, capsys
):
    """Both links were there before; Ann makes a harness from L2, Bob from L1: links.json merges
    without a conflict (the two changes are far apart), both links name W003, and only the commit
    of HEAD tells which is Bob's."""
    start(tmp_path, links=2)
    branch(tmp_path, "ann", harness_from("L2"))
    branch(tmp_path, "bob", harness_from("L1"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["physical/harnesses/W003.json"]
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "link L2 made harness W003 of the other branch; it names W004 now" in out
    links = {x["id"]: x for x in files(design, "logical/links.json")["links"]}
    assert links["L1"]["harness_id"] == "W003" and links["L2"]["harness_id"] == "W004"
    validate_clean(design, capsys)


# ---- waivers and deviations ----------------------------------------------------------------------------


def test_a_waiver_of_the_other_branch_follows_the_new_id_and_must_be_given_again(
    tmp_path, clock, capsys
):
    start(tmp_path)
    branch(tmp_path, "ann", cable("PCDU1-J02"), waive("W003-001"))
    branch(tmp_path, "bob", cable("OBC1-J02"), waive("W003-002"))
    design = merge(tmp_path)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "waiver wire-length.W003-001 -> wire-length.W004-001" in out
    assert "check shows it as changed until it is given again" in out
    waivers = {w["id"]: w for w in files(design, "waivers.json")["waivers"]}
    assert set(waivers) == {"wire-length.W003-002", "wire-length.W004-001"}
    assert waivers["wire-length.W004-001"]["object_id"] == "W004-001"


# ---- refusals ---------------------------------------------------------------------------------------------


def test_a_harness_in_review_on_the_other_branch_is_not_renamed(tmp_path, clock, capsys):
    def review(design: Path) -> None:
        assert main(["review", str(design), "W003", "--by", "Ann"]) == 0

    start(tmp_path)
    branch(tmp_path, "ann", cable("PCDU1-J02"), review)
    branch(tmp_path, "bob", cable("OBC1-J02"))
    design = merge(tmp_path)
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 1
    err = capsys.readouterr().err
    assert "Both branches made harness W003" in err and "Released IDs never change" in err
    assert "Nothing was changed." in err
    assert tree(design) == before


def released(hid: str):
    """The harness released: its status and its baseline, as `release` writes them (the release
    blockers of a project on placeholder values are not the point here)."""

    def step(design: Path) -> None:
        p = load_project(design).project
        h = evolve(p.harnesses[hid], status="released", released_on="2026-11-16", approver="Bea")
        p.harnesses[hid] = h
        b = Baseline(
            id=f"{hid}.A", harness_id=hid, revision="A", released_on="2026-11-16", by="Bea",
            comment="First release for the merge test.", content_hash=content_hash(p),
            snapshot=snapshot_for(p, h),
        )  # fmt: skip
        p.baselines[b.id] = b
        save_project(p, design)

    return step


def test_a_released_harness_is_not_renamed(tmp_path, clock, capsys):
    start(tmp_path)
    branch(tmp_path, "ann", cable("PCDU1-J02"), released("W003"))
    branch(tmp_path, "bob", cable("OBC1-J02"))
    design = merge(tmp_path)
    assert (design / "baselines" / "W003").is_dir()
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 1
    err = capsys.readouterr().err
    assert "release history" in err and "this branch: draft, the other branch: released" in err
    assert tree(design) == before


def test_a_harness_changed_on_both_branches_is_not_an_id_collision(tmp_path, clock, capsys):
    def rename(name: str):
        def step(design: Path) -> None:
            path = design / "physical/harnesses/W001.json"
            doc = json.loads(path.read_text())
            doc["notes"] = name
            path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

        return step

    start(tmp_path)
    branch(tmp_path, "ann", rename("Ann's note"))
    branch(tmp_path, "bob", rename("Bob's note"))
    design = merge(tmp_path)
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 1
    err = capsys.readouterr().err
    assert "physical/harnesses/W001.json was changed on both branches" in err
    assert tree(design) == before


def test_a_link_changed_on_both_branches_is_refused(tmp_path, clock, capsys):
    def note(text: str):
        def step(design: Path) -> None:
            path = design / "logical/links.json"
            doc = json.loads(path.read_text())
            doc["links"][0]["note"] = text
            path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

        return step

    start(tmp_path, links=1)
    branch(tmp_path, "ann", note("Ann"))
    branch(tmp_path, "bob", note("Bob"))
    design = merge(tmp_path)
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 1
    assert "The link L1 of logical/links.json was changed on both branches" in (
        capsys.readouterr().err
    )
    assert tree(design) == before


def test_a_baselined_link_is_not_renamed(tmp_path, clock, capsys):
    start(tmp_path)
    branch(tmp_path, "ann", link("OBC1-J03", "PCDU1-J03"), harness_from("L1"), released("W003"))
    branch(tmp_path, "bob", link("OBC1-J02", "PCDU1-J02"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["logical/links.json"]
    before = tree(design)
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 1
    assert "a baseline holds a link L1" in capsys.readouterr().err
    assert tree(design) == before


def test_without_git_merge_fix_cannot_tell_the_sides_and_refuses(tmp_path, clock, capsys):
    (tmp_path / "repo").mkdir()
    design = two_generated(tmp_path / "repo")
    copy = tmp_path / "copy"
    shutil.copytree(design, copy)
    plan = plan_id_fix(copy, ["physical/harnesses/W003.json"])
    assert plan.problem.startswith("The project folder is not in a Git repository")
    assert not plan.writes and not plan.renames


def test_the_same_harness_written_differently_is_kept_once(tmp_path, clock, capsys):
    """Both branches made the same harness, but one wrote it with another layout (by hand, a tool):
    Git stops on the file; its two sides read the same, so nothing is renamed."""

    def relayout(design: Path) -> None:
        path = design / "physical/harnesses/W003.json"
        path.write_text(json.dumps(json.loads(path.read_text()), indent=4, sort_keys=True))

    start(tmp_path)
    branch(tmp_path, "ann", cable("OBC1-J02"), relayout)
    branch(tmp_path, "bob", cable("OBC1-J02"))
    design = merge(tmp_path)
    assert conflict_files(design) == ["physical/harnesses/W003.json"]
    capsys.readouterr()
    assert main(["merge-fix", str(design)]) == 0
    out = capsys.readouterr().out
    assert "Made on both branches with the same content, kept once: W003." in out
    assert "Renamed" not in out and not (design / "physical/harnesses/W004.json").exists()
    entries = list(load_project(design).project.journal)
    assert not any(e.field == "ids" for e in entries)
    validate_clean(design, capsys)


# ---- the pieces -----------------------------------------------------------------------------------------


def test_take_their_side_keeps_the_other_branch():
    text = b"a\n<<<<<<< HEAD\nours\n||||||| base\nold\n=======\ntheirs\n>>>>>>> b\nz\n"
    assert take_their_side(text) == b"a\ntheirs\nz\n"
    assert take_our_side(text) == b"a\nours\nz\n"
    for bad in (b"=======\n", b"<<<<<<< x\nours\n", b"<<<<<<< a\n<<<<<<< b\n", b">>>>>>> x\n"):
        with pytest.raises(ValueError):
            take_their_side(bad)


def test_the_versions_git_keeps_are_read_from_a_pack(tmp_path, clock):
    design = two_generated(tmp_path)
    git(tmp_path, "gc", "-q")  # every object into a pack
    repo = gitobjects.open_repo(design)
    head = gitobjects.head_file(repo, "physical/harnesses/W003.json")
    assert head == take_our_side((design / "physical/harnesses/W003.json").read_bytes())
    assert gitobjects.head_file(repo, "physical/harnesses/W009.json") is None
    assert gitobjects.head_file(repo, "physical") is None  # a folder is not a file
    stage = gitobjects.stages(repo)["physical/harnesses/W003.json"]
    theirs = gitobjects.blob(repo, stage[3])
    assert theirs == take_their_side((design / "physical/harnesses/W003.json").read_bytes())
    with pytest.raises(gitobjects.GitUnreadable):
        gitobjects.blob(repo, "0" * 40)
    with pytest.raises(gitobjects.GitUnreadable):
        gitobjects.blob(repo, stage[3], limit=10)  # larger than the limit
