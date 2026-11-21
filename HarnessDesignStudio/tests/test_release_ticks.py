# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""REQ-CC-11: a release records the ticks of the review checklist that the person releasing states,
with the list hash; no gate (design of 4.3.0, `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`, part D,
sections 6.1 to 6.4, and section 10; pull request 2 of the design).

`release DIR HARNESS --ticked POINTS` (and `plan_release(..., ticked=)`, which the editor's Review
page will use) reads `all`, `none` or numbers and ranges with `review.parse_ticked`; the two
blockers `ticked_invalid` and `ticked_no_checklist`; the five notes of section 6.3
(`vcs/release.review_note`), the ranges, the cut of a point not ticked and `and N more`; the
check of `comment_long` with the note; a release in a project without a list writes the comment of
today byte for byte; the note in the change log, the baseline and `log`; the command line end to
end, its `--json` keys unchanged."""

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from harness_design_studio.cli.main import main
from harness_design_studio.core import configcheck, review, samples, templates
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Baseline, ChangeEntry, Project, evolve
from harness_design_studio.core.outputs.build import write_outputs
from harness_design_studio.core.vcs import release
from harness_design_studio.core.vcs.release import (
    MAX_COMMENT,
    number_ranges,
    plan_release,
    release_blockers,
    review_note,
    ticked_blockers,
)
from tools.format3_record import _release_history

BY, CHECKER, WHEN = "R. Example", "C. Example", "2026-03-01"
COMMENT = "Release for the review"
REASONS: dict[str, Any] = dict(
    accept_placeholders="placeholders fine for the test",
    accept_unapproved_parts="example parts fine for the test",
)
POINTS = [f"Point {n}: the wire list agrees with the drawing." for n in range(1, 27)]
NO_LIST = (
    "This project has no review checklist, so there is nothing to tick "
    "(config/naming.json: review_checklist)."
)
# the comment of a release of mini3 W001 at 4.2.0, with the two reasons (no checklist)
COMMENT_OF_TODAY = (
    "Release for the review [Released on placeholder configuration (derating, emc, generation, "
    "segmentation, segregation, titleblock); accepted by R. Example: placeholders fine for the "
    "test] [Released with parts that are not approved (EX-MICROD-9-F, EX-MICROD-9-M); accepted by "
    "R. Example: example parts fine for the test]"
)


def invalid(got: str, n: int = 26) -> str:
    return (
        f"--ticked must be all, none, or point numbers from 1 to {n} such as 1-5,7 (got '{got}')."
    )


def releasable() -> Project:
    """mini3, generated, with W001 sized and measured: the gate asks only for the two reasons."""
    p = samples.mini3()
    generate_project(p)
    h = p.harnesses["W001"]
    wires = [evolve(w, gauge_awg=20, length_m=1.5) for w in h.wires]
    apply_ops(p, [Put("harnesses", evolve(h, wires=wires))])
    return p


def set_list(p: Project, points: list[str] | None) -> None:
    plan = configcheck.plan_set_checklist(p, points)
    assert plan.ok, plan.error
    History(p).execute("Review checklist", plan.ops)


def with_list(points: list[str] = POINTS) -> Project:
    p = releasable()
    set_list(p, points)
    return p


def head(points: list[str] = POINTS) -> str:
    n = len(points)
    return f" [Review checklist ({n} point{'' if n == 1 else 's'}, list {review.list_hash(points)})"


def release_plan(p: Project, folder: Path | None, **kw: object) -> release.ReleasePlan:
    args: dict[str, object] = dict(
        by=BY, checker=CHECKER, comment=COMMENT, when=WHEN, outputs_folder=folder, **REASONS
    )
    args.update(kw)
    return plan_release(p, "W001", **args)  # type: ignore[arg-type]


def comment_of(plan: release.ReleasePlan) -> str:
    assert plan.ok, [b.message for b in plan.blockers]
    objs = [o.obj for o in plan.ops if isinstance(o, Put)]
    entry = next(o for o in objs if isinstance(o, ChangeEntry))
    base = next(o for o in objs if isinstance(o, Baseline))
    assert entry.comment == base.comment  # the change log and the baseline keep the same comment
    return entry.comment


# ---- parse_ticked and the ranges ---------------------------------------------------------------


@given(st.integers(1, 100).flatmap(lambda n: st.tuples(st.just(n), st.sets(st.integers(1, n)))))
def test_the_ranges_of_the_note_read_back_as_the_same_points(case: tuple[int, set[int]]) -> None:
    n, ticked = case
    text = number_ranges(ticked)
    if ticked:
        assert review.parse_ticked(text.replace(" ", ""), n) == frozenset(ticked)
        assert review.parse_ticked(text, n) == frozenset(ticked)  # the spaces do not count
    else:
        assert text == ""


@pytest.mark.parametrize(
    ("numbers", "text"),
    [
        ({1, 2, 3, 4, 5, 7, *range(9, 27)}, "1-5, 7, 9-26"), ({7, 8}, "7-8"), ({3}, "3"),
        ({1, 3, 5}, "1, 3, 5"), ({10, 2, 1}, "1-2, 10"),
    ],
)  # fmt: skip
def test_number_ranges(numbers: set[int], text: str) -> None:
    assert number_ranges(numbers) == text


@pytest.mark.parametrize(
    ("ticked", "points"),
    [("all", set(range(1, 27))), ("none", set()), (" 1-5,7 ", {1, 2, 3, 4, 5, 7}),
     (frozenset({2, 26}), {2, 26}), (frozenset(), set())],
)  # fmt: skip
def test_text_and_numbers_are_the_same_ticks(ticked: object, points: set[int]) -> None:
    p = with_list()
    assert ticked_blockers(p, ticked) == []  # type: ignore[arg-type]
    assert release._ticked_points(p, ticked) == frozenset(points)  # type: ignore[arg-type]


# ---- the two blockers (6.2) --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ticked", "got"),
    [("27", "27"), ("0", "0"), ("1-27", "1-27"), ("5-3", "5-3"), ("one", "one"), ("", ""),
     ("1,,2", ""), (frozenset({27}), "27"), (frozenset({0, 30}), "0"), (frozenset({1, 99}), "99")],
)  # fmt: skip
def test_ticked_invalid(ticked: object, got: str) -> None:
    p = with_list()
    found = ticked_blockers(p, ticked)  # type: ignore[arg-type]
    assert [(b.code, b.message, b.about) for b in found] == [
        ("ticked_invalid", invalid(got), "ticked")
    ]
    assert review_note(p, BY, ticked) == ""  # type: ignore[arg-type]  # nothing is recorded


@pytest.mark.parametrize("ticked", ["all", "none", "1", "1-5,7", frozenset(), frozenset({1})])
def test_ticked_no_checklist(ticked: object) -> None:
    p = releasable()
    found = ticked_blockers(p, ticked)  # type: ignore[arg-type]
    assert [(b.code, b.message, b.about) for b in found] == [
        ("ticked_no_checklist", NO_LIST, "ticked")
    ]
    assert review_note(p, BY, ticked) == ""  # type: ignore[arg-type]


def test_a_refused_list_is_no_list_to_tick() -> None:
    p = releasable()
    from tests.test_review_checklist import _with_list

    _with_list(p, ["same", "SAME"])  # refused: config-invalid says why and blocks the release
    assert [b.code for b in ticked_blockers(p, "all")] == ["ticked_no_checklist"]
    assert review_note(p, BY, None) == ""


def test_without_ticked_nothing_blocks_and_the_gate_has_the_blockers_of_today() -> None:
    """R5: no gate on the checklist; points not ticked, or no ticks given, never stop a release."""
    for p in (releasable(), with_list()):
        assert ticked_blockers(p, None) == []
        codes = {b.code for b in release_blockers(p, "W001", by=BY, comment=COMMENT, when=WHEN, outputs_folder=None, checker=CHECKER, **REASONS)}  # fmt: skip
        assert codes == {"outputs_unsaved"}
    p = with_list()
    ticks: tuple[release.Ticked, ...] = ("none", "1", frozenset())
    for ticked in ticks:
        codes = {b.code for b in release_blockers(p, "W001", by=BY, comment=COMMENT, when=WHEN, outputs_folder=None, checker=CHECKER, ticked=ticked, **REASONS)}  # fmt: skip
        assert codes == {"outputs_unsaved"}


def test_both_blockers_are_listed_with_the_others() -> None:
    p = releasable()
    found = release_blockers(
        p, "W001", by=BY, comment="short", when=WHEN, outputs_folder=None, ticked="all"
    )
    codes = [b.code for b in found]
    assert "ticked_no_checklist" in codes and "comment_short" in codes
    assert "placeholder_config" in codes


# ---- the note (6.3) ----------------------------------------------------------------------------


def test_the_five_notes() -> None:
    # no checklist, no --ticked: every project of today
    assert review_note(releasable(), BY, None) == ""
    p = with_list()
    who = f"{head()}, recorded by {BY}: "
    assert review_note(p, BY, None) == f"{head()}: no ticks recorded]"
    assert review_note(p, f"  {BY} ", "all") == f"{who}all ticked]"
    assert review_note(p, BY, frozenset(range(1, 27))) == f"{who}all ticked]"
    assert review_note(p, BY, "1-26") == f"{who}all ticked]"
    assert review_note(p, BY, "none") == f"{who}none ticked]"
    assert review_note(p, BY, frozenset()) == f"{who}none ticked]"
    assert review_note(p, BY, "1-5,7,9-26") == (
        f"{who}ticked 1-5, 7, 9-26; not ticked 6 ({POINTS[5]}), 8 ({POINTS[7]})]"
    )


def test_one_point_and_the_list_hash() -> None:
    p = with_list(["`check` prints no error."])  # stored as given; the hash is of the stored list
    assert review.points(p) == ("`check` prints no error.",)
    digest = review.list_hash(["`check` prints no error."])
    assert len(digest) == 8
    assert review_note(p, BY, None) == f" [Review checklist (1 point, list {digest}): no ticks recorded]"  # fmt: skip
    assert review_note(p, BY, "1") == f" [Review checklist (1 point, list {digest}), recorded by {BY}: all ticked]"  # fmt: skip


def test_at_most_five_points_not_ticked_are_named_each_cut_to_60_characters() -> None:
    long = [f"{n:02d} " + "a" * 57 + ("" if n % 2 else "bcd") for n in range(1, 31)]  # 60 or 63
    p = with_list(long)
    note = review_note(p, BY, "1,30")
    named = [f"{n} ({long[n - 1] if n % 2 else long[n - 1][:57] + '...'})" for n in range(2, 7)]
    assert note == (
        f"{head(long)}, recorded by {BY}: ticked 1, 30; not ticked {', '.join(named)} and 23 more]"
    )
    assert all(len(x.split(" (", 1)[1]) - 1 <= 60 for x in named)
    assert f"({long[2]})" in note  # 60 characters: not cut
    five_left = review_note(p, BY, "1-25")
    assert five_left.endswith(f"not ticked 26 ({long[25][:57]}...), 27 ({long[26]}), 28 ({long[27][:57]}...), 29 ({long[28]}), 30 ({long[29][:57]}...)]")  # fmt: skip
    assert "more" not in five_left


def test_the_note_stays_short_on_the_longest_list() -> None:
    long = [f"{n:03d} " + "z" * 296 for n in range(1, 101)]  # 100 points of 300 characters
    p = with_list(long)
    worst = review_note(p, BY, ",".join(str(n) for n in range(1, 101, 2)))  # 50 single numbers
    assert len(worst) < 700
    assert worst.endswith(" and 45 more]")


def test_comment_long_counts_the_note() -> None:
    p = with_list()
    other = len(release.placeholder_note(p, BY, REASONS["accept_placeholders"])) + len(
        release.part_note(p, p.harnesses["W001"], BY, REASONS["accept_unapproved_parts"])
    )
    note = len(review_note(p, BY, "1-5,7,9-26"))
    comment = "x" * (MAX_COMMENT - other - note + 1)  # the note takes it past 2000
    args = dict(by=BY, when=WHEN, outputs_folder=None, checker=CHECKER, **REASONS)

    def codes(c: str, ticked: object) -> set[str]:
        return {b.code for b in release_blockers(p, "W001", comment=c, ticked=ticked, **args)}  # type: ignore[arg-type]

    assert "comment_long" in codes(comment, "1-5,7,9-26")
    assert "comment_long" not in codes(comment[:-2], "1-5,7,9-26")
    assert "comment_long" not in codes(comment, "all")  # a shorter note fits


# ---- the release (6.3, 6.4) ----------------------------------------------------------------------


def test_a_release_without_a_list_writes_the_comment_of_today_byte_for_byte(tmp_path: Path) -> None:
    p = releasable()
    folder = tmp_path / "outputs"
    write_outputs(p, folder)
    assert comment_of(release_plan(p, folder)) == COMMENT_OF_TODAY
    assert comment_of(release_plan(p, folder, ticked=None)) == COMMENT_OF_TODAY
    assert "--ticked" not in COMMENT_OF_TODAY


def test_no_recorded_release_has_a_list(tmp_path: Path) -> None:
    """The guard of pull request 2 (*identical*): no example, template or recorded project sets a
    checklist, so their releases keep the comment of today."""
    p = _release_history(tmp_path)
    assert review.points(p) == ()
    assert all("[Review checklist" not in e.comment for e in p.changelog.values())
    for name in ("blank", "first-steps", "minimal-satellite", "small-satellite", "flatsat"):
        q = templates.create_project(tmp_path / name, name)
        assert review.points(q) == () and review_note(q, BY, None) == ""


def test_the_note_is_last_in_the_comment_of_the_release(tmp_path: Path) -> None:
    p = with_list()
    folder = tmp_path / "outputs"
    write_outputs(p, folder)  # the list is part of the content hash: export after setting it
    plain = comment_of(release_plan(p, folder))
    assert plain == COMMENT_OF_TODAY + f"{head()}: no ticks recorded]"
    ticked = comment_of(release_plan(p, folder, ticked="1-5,7,9-26"))
    assert ticked == COMMENT_OF_TODAY + review_note(p, BY, "1-5,7,9-26")
    blocked = release_plan(p, folder, ticked="27")
    assert [b.code for b in blocked.blockers] == ["ticked_invalid"] and blocked.ops == []


def test_a_list_set_after_the_export_makes_the_outputs_stale(tmp_path: Path) -> None:
    p = releasable()
    folder = tmp_path / "outputs"
    write_outputs(p, folder)
    set_list(p, POINTS)
    assert [b.code for b in release_plan(p, folder, ticked="all").blockers] == ["outputs_stale"]


# ---- the command line ----------------------------------------------------------------------------


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "p"
    save_project(with_list(), root)
    assert main(["export", str(root)]) == 0
    return root


def cli(root: Path, *more: str) -> list[str]:
    return [
        "release", str(root), "W001", "--by", BY, "--checker", CHECKER, "--comment", COMMENT,
        "--date", WHEN, "--accept-placeholders", REASONS["accept_placeholders"],
        "--accept-unapproved-parts", REASONS["accept_unapproved_parts"], *more,
    ]  # fmt: skip


def test_the_command_line_end_to_end(folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(cli(folder, "--ticked", "27")) == 1
    err = capsys.readouterr().err
    assert f"blocked: [ticked_invalid] {invalid('27')}" in err  # the option is not named twice
    assert main(cli(folder, "--ticked", "1-5,7,9-26")) == 0
    capsys.readouterr()
    q = load_project(folder).project
    note = review_note(q, BY, "1-5,7,9-26")
    entry = next(e for e in q.changelog.values() if e.kind == "release")
    assert entry.comment == COMMENT_OF_TODAY + note
    assert q.baselines["W001.1.0.0"].comment == entry.comment
    assert main(["log", str(folder), "W001"]) == 0
    assert note.strip() in capsys.readouterr().out
    assert main(["verify", str(folder), "--outputs"]) == 0  # the outputs written again are current


def test_the_command_line_without_a_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "p"
    save_project(releasable(), root)
    assert main(["export", str(root)]) == 0
    capsys.readouterr()
    assert main(cli(root, "--ticked", "all")) == 1
    assert f"blocked: [ticked_no_checklist] --ticked: {NO_LIST}" in capsys.readouterr().err
    assert main(cli(root)) == 0  # without --ticked a release goes ahead as today
    entry = next(e for e in load_project(root).project.changelog.values() if e.kind == "release")
    assert entry.comment == COMMENT_OF_TODAY


def test_json_keeps_its_keys(folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    capsys.readouterr()
    assert main([*cli(folder, "--ticked", "0"), "--json"]) == 1
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["blockers"] == [
        {"code": "ticked_invalid", "message": invalid("0"), "about": "ticked"}
    ]
    assert main([*cli(folder, "--ticked", "all"), "--json"]) == 0
    done = json.loads(capsys.readouterr().out)
    assert "ticked" not in done and "review" not in done  # R12: the note is in the comment
    assert set(done) == set(blocked)


def test_the_help_names_the_option(capsys: pytest.CaptureFixture[str]) -> None:
    code: object
    try:
        code = main(["release", "--help"])
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    text = " ".join(capsys.readouterr().out.split())
    assert "--ticked POINTS" in text
    assert "points not ticked do not stop the release" in text
    cli_doc = (Path(__file__).resolve().parent.parent / "docs" / "CLI.md").read_text("utf-8")
    assert "--ticked POINTS" in cli_doc
