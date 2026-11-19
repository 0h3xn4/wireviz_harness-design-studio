# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-PIN-06: the checks, the plans and the scripting functions of the row layout (design of
4.0.0 sections 4.3, 9 and 10; pull request 2).

The three checks of `core/integrity.py` (`row_layout_pin_missing`, `row_layout_pins_outside`,
`row_layout_mate_differs`) are reported by `validate` and `check` and, the two warnings, by the
rule `model-inconsistent`; none is an error. The plans `plan_set_row_layout`,
`plan_clear_row_layout` and `plan_share_with_part` (`core/row_layout_edit.py`) are one undo step
each, are journaled on save as every edit, and are not locked by a release. The scripting
interface adds `row_layout_of`, `set_row_layout` and `clear_row_layout`, which call those plans.
"""

from pathlib import Path

import pytest

from harness_design_studio import api
from harness_design_studio.core import journal
from harness_design_studio.core.commands import History, Put, apply_ops
from harness_design_studio.core.drc import run as run_drc
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.errors import TransactionError
from harness_design_studio.core.integrity import check_integrity, row_layout_issues
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Connector, Pin, Project, RowLayout, evolve
from harness_design_studio.core.row_layout import layout_of
from harness_design_studio.core.row_layout_edit import (
    plan_clear_row_layout,
    plan_set_row_layout,
    plan_share_with_part,
)
from harness_design_studio.core.samples import mini3, sat15
from harness_design_studio.core.vcs.locks import check_locks

MICROD_21 = [[str(n) for n in range(1, 12)], [str(n) for n in range(12, 22)]]
CODES = ("row_layout_pin_missing", "row_layout_pins_outside", "row_layout_mate_differs")


def rows(*rows: list[str], rings: bool = False) -> RowLayout:
    return RowLayout(rows=[list(r) for r in rows], rings=rings)


def issues(p: Project) -> list[tuple[str, str, str, str]]:
    return [(i.severity, i.code, i.object_id or "", i.message) for i in row_layout_issues(p)]


def with_connectors(p: Project, *ids: str, part: str = "EX-MICROD-21-F", pins: int = 21) -> Project:
    """Box connectors of OBC with `pins` pins named 1 to N, no harness on them."""
    for cid in ids:
        p.connectors[cid] = Connector(
            id=cid, name=cid.rsplit("-", 1)[1], role="box", part_id=part, unit_id="OBC",
            pins=[Pin(id=str(n)) for n in range(1, pins + 1)],
        )  # fmt: skip
    return p


# ---- the checks of section 4.3 ---------------------------------------------------------------


def test_no_check_speaks_on_projects_without_a_layout() -> None:
    for p in (mini3(), sat15()):
        assert row_layout_issues(p) == []
        assert not [i for i in check_integrity(p) if i.code in CODES]


def test_a_name_of_the_part_that_the_connector_does_not_have() -> None:
    p = with_connectors(mini3(), "OBC-J21", pins=20)
    p.parts["EX-MICROD-21-F"] = evolve(
        p.parts["EX-MICROD-21-F"], row_layout=RowLayout(rows=MICROD_21)
    )
    assert issues(p) == [
        ("warning", "row_layout_pin_missing", "OBC-J21",
         "The row layout of part EX-MICROD-21-F names pin 21, which OBC-J21 does not have; it is "
         "left out of the rows of OBC-J21."),
    ]  # fmt: skip


def test_pins_in_no_row_are_a_note() -> None:
    p = with_connectors(mini3(), "OBC-J21")
    p.connectors["OBC-J21"] = evolve(p.connectors["OBC-J21"], row_layout=rows(MICROD_21[0]))
    assert issues(p) == [
        ("info", "row_layout_pins_outside", "OBC-J21",
         "Pins 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 of OBC-J21 are in no row of the own row "
         "layout of OBC-J21; they are listed after the rows, without a row, and "
         "power-return-adjacent judges them in the order of the list of pins."),
    ]  # fmt: skip
    assert len(rows(MICROD_21[0]).names()) == 11


def test_a_cable_connector_whose_part_has_other_rows_than_the_box_connector() -> None:
    p = mini3()  # W001-P1 (part EX-MICROD-9-M) plugs into PCDU-J01 (part EX-MICROD-9-F)
    p.connectors["PCDU-J01"] = evolve(p.connectors["PCDU-J01"], row_layout=rows(["1", "2"], ["3"]))
    p.parts["EX-MICROD-9-M"] = evolve(p.parts["EX-MICROD-9-M"], row_layout=rows(["2", "1"], ["3"]))
    assert issues(p) == []  # the order inside a row is not compared: a mating face is mirrored
    p.parts["EX-MICROD-9-M"] = evolve(p.parts["EX-MICROD-9-M"], row_layout=rows(["1"], ["2", "3"]))
    found = [i for i in issues(p) if i[1] == "row_layout_mate_differs"]
    assert found == [
        ("warning", "row_layout_mate_differs", "W001-P1",
         "W001-P1 and the device connector PCDU-J01 it plugs into have different row layouts (the "
         "row layout of part EX-MICROD-9-M; the own row layout of PCDU-J01): row 1 holds 1 on "
         "W001-P1 and 1 2 on PCDU-J01. The order inside a row is not compared, since a mating "
         "face is seen mirrored."),
    ]  # fmt: skip


def test_two_mating_parts_with_other_rows() -> None:
    p = mini3()
    f, m = p.parts["EX-MICROD-9-F"], p.parts["EX-MICROD-9-M"]
    assert f.mates_with == m.id
    p.parts[f.id] = evolve(f, row_layout=rows([str(n) for n in range(1, 6)], ["6", "7", "8", "9"]))
    p.parts[m.id] = evolve(
        m, row_layout=rows([str(n) for n in range(5, 0, -1)], ["9", "8", "7", "6"])
    )
    assert [i for i in issues(p) if i[1] == "row_layout_mate_differs"] == []
    p.parts[m.id] = evolve(m, row_layout=rows([str(n) for n in range(1, 6)]))
    (found,) = [i for i in issues(p) if i[1] == "row_layout_mate_differs"]
    assert found[2] == "EX-MICROD-9-F"
    assert "row 2 holds 6–9 on EX-MICROD-9-F and no row on EX-MICROD-9-M" in found[3]


def test_where_the_checks_appear(tmp_path: Path) -> None:
    p = with_connectors(mini3(), "OBC-J21", pins=20)
    p.parts["EX-MICROD-21-F"] = evolve(
        p.parts["EX-MICROD-21-F"], row_layout=RowLayout(rows=[MICROD_21[0], ["12", "22"]])
    )
    save_project(p, tmp_path / "p")
    for merge_check in (False, True):  # `validate`, then `check`
        result = api.validate(tmp_path / "p", merge_check=merge_check)
        got = {(i.severity, i.code) for i in result.issues if i.code in CODES}
        assert got == {("warning", "row_layout_pin_missing"), ("info", "row_layout_pins_outside")}
        assert not [i for i in result.issues if i.code in CODES and i.severity == "error"]
    found = [f for f in run_drc(p) if f.rule == "model-inconsistent" and f.object_id == "OBC-J21"]
    assert len(found) == 1 and "names pin 22" in found[0].title  # the note is not a finding
    History(p).execute("an edit", [Put("units", evolve(p.units["OBC"], name="OBC renamed"))])


# ---- the plans -------------------------------------------------------------------------------


def test_setting_the_rows_of_a_part_and_of_a_box_connector_is_one_undo_step_each() -> None:
    p = mini3()
    history = History(p)
    before = model_hash(p)
    history.execute(
        "rows", plan_set_row_layout(p, RowLayout(rows=MICROD_21), part="EX-MICROD-21-F")
    )
    assert p.parts["EX-MICROD-21-F"].row_layout == RowLayout(rows=MICROD_21)
    history.execute(
        "own", plan_set_row_layout(p, rows(["1", "2", "3"], ["4", "5"]), connector="OBC-J01")
    )
    assert layout_of(p, p.connectors["OBC-J01"]).source == "own"
    assert plan_set_row_layout(p, rows(["1", "2", "3"], ["4", "5"]), connector="OBC-J01") == []
    history.undo()
    assert p.connectors["OBC-J01"].row_layout is None
    history.undo()
    assert p.parts["EX-MICROD-21-F"].row_layout is None and model_hash(p) == before
    history.redo()
    history.redo()
    assert p.connectors["OBC-J01"].row_layout == rows(["1", "2", "3"], ["4", "5"])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"part": "EX-MICROD-9-F", "layout": RowLayout(rows=MICROD_21)},
      "The rows cannot be stored on EX-MICROD-9-F: the row layout names 21 pins; the part has 9"),
     ({"connector": "OBC-J01", "layout": rows(["1", "6"])},
      "The rows cannot be stored on OBC-J01: the row layout names pin 6; OBC-J01 has no pin 6"),
     ({"connector": "W001-P1", "layout": rows(["1"])}, "W001-P1 is a connector of a harness"),
     ({"connector": "NOPE", "layout": rows(["1"])}, "'NOPE' is not a connector of the project"),
     ({"part": "NOPE", "layout": rows(["1"])}, "Part 'NOPE' does not exist"),
     ({"layout": rows(["1"])}, "Name a part or a connector, not both"),
     ({"part": "EX-MICROD-9-F", "connector": "OBC-J01", "layout": rows(["1"])},
      "Name a part or a connector, not both")],
)  # fmt: skip
def test_a_layout_that_breaks_a_rule_is_refused_with_the_reason(kwargs, message) -> None:
    p = mini3()
    layout = kwargs.pop("layout")
    with pytest.raises(EditError, match=message):
        plan_set_row_layout(p, layout, **kwargs)


def test_only_a_connector_part_has_rows_and_a_read_only_project_none() -> None:
    p = mini3()
    wire = next(x for x in p.parts.values() if x.category == "wire")
    with pytest.raises(EditError, match="only a connector part has rows"):
        plan_set_row_layout(p, rows(["1"]), part=wire.id)
    p.read_only = True
    for plan in (
        lambda: plan_set_row_layout(p, rows(["1"]), part="EX-MICROD-9-F"),
        lambda: plan_clear_row_layout(p, part="EX-MICROD-9-F"),
        lambda: plan_share_with_part(p, "OBC-J01"),
    ):
        with pytest.raises(EditError, match="read-only"):
            plan()


def test_clearing_gives_a_box_connector_back_the_rows_of_its_part() -> None:
    p = with_connectors(mini3(), "OBC-J21")
    p.parts["EX-MICROD-21-F"] = evolve(
        p.parts["EX-MICROD-21-F"], row_layout=RowLayout(rows=MICROD_21)
    )
    p.connectors["OBC-J21"] = evolve(p.connectors["OBC-J21"], row_layout=rows(["1", "2"]))
    assert plan_clear_row_layout(p, part="EX-MICROD-9-F") == []
    history = History(p)
    history.execute("back", plan_clear_row_layout(p, connector="OBC-J21"))
    assert layout_of(p, p.connectors["OBC-J21"]).source == "part"
    assert plan_clear_row_layout(p, connector="OBC-J21") == []
    history.execute("clear", plan_clear_row_layout(p, part="EX-MICROD-21-F"))
    assert layout_of(p, p.connectors["OBC-J21"]) is None
    history.undo()
    history.undo()
    assert p.connectors["OBC-J21"].row_layout == rows(["1", "2"])


def test_use_for_every_connector_of_this_part() -> None:
    p = with_connectors(mini3(), "OBC-J21", "OBC-J22", "OBC-J23")
    own = RowLayout(rows=MICROD_21)
    other = rows(MICROD_21[1], MICROD_21[0])
    for cid, layout in (("OBC-J21", own), ("OBC-J22", own), ("OBC-J23", other)):
        p.connectors[cid] = evolve(p.connectors[cid], row_layout=layout)
    history = History(p)
    history.execute("share", plan_share_with_part(p, "OBC-J21"))
    assert p.parts["EX-MICROD-21-F"].row_layout == own
    assert p.connectors["OBC-J21"].row_layout is None and p.connectors["OBC-J22"].row_layout is None
    assert p.connectors["OBC-J23"].row_layout == other  # other rows stay its own
    assert history.next_undo_label == "share"
    history.undo()  # one step puts everything back
    assert p.parts["EX-MICROD-21-F"].row_layout is None
    assert p.connectors["OBC-J21"].row_layout == own == p.connectors["OBC-J22"].row_layout
    apply_ops(p, plan_share_with_part(p, "OBC-J21"))
    with pytest.raises(EditError, match="has other rows"):
        plan_share_with_part(p, "OBC-J23")
    with pytest.raises(EditError, match="OBC-J02 has no rows of its own"):
        plan_share_with_part(p, "OBC-J02")


def test_the_part_has_these_rows_already_and_only_the_own_rows_go() -> None:
    p = with_connectors(mini3(), "OBC-J21")
    own = RowLayout(rows=MICROD_21)
    p.parts["EX-MICROD-21-F"] = evolve(p.parts["EX-MICROD-21-F"], row_layout=own)
    p.connectors["OBC-J21"] = evolve(p.connectors["OBC-J21"], row_layout=own)
    ops = plan_share_with_part(p, "OBC-J21")
    assert [op.collection for op in ops] == ["connectors"]


def test_a_release_does_not_lock_the_rows() -> None:
    """The rows are device and library data, not harness data (design section 3)."""
    p = mini3()
    apply_ops(p, [Put("harnesses", evolve(p.harnesses["W001"], status="released"))])
    box, part = p.connectors["PCDU-J01"], p.parts["EX-MICROD-9-F"]  # both used by W001
    check_locks(p, plan_set_row_layout(p, rows(["1", "2", "3"]), connector=box.id))
    check_locks(p, plan_set_row_layout(p, rows(["1", "2"], ["3"]), part=part.id))
    with pytest.raises(TransactionError):  # the part's other fields stay locked
        check_locks(p, [Put("parts", evolve(part, pin_count=12))])


def test_the_plans_are_journaled_on_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(journal, "now", lambda: "2026-11-19T10:00:00Z")
    p = mini3()
    journal.start(p)
    save_project(p, tmp_path / "p")
    History(p).execute(
        "rows", plan_set_row_layout(p, rows(["1", "2"], ["3"]), connector="PCDU-J01")
    )
    save_project(p, tmp_path / "p")
    entries = [e for e in journal.history(p) if e["object"] == "connector:PCDU-J01"]
    assert [(e["field"], e["old"], e["new"]) for e in entries] == [
        ("row_layout", None, {"rows": [["1", "2"], ["3"]]})
    ]


# ---- the scripting interface (section 10) ----------------------------------------------------


def test_the_scripting_functions(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    save_project(mini3(), folder)
    journal_started = api.start_journal(folder, author="Example Ltd")
    assert journal_started
    none = api.row_layout_of(folder, "PCDU-J01")
    assert none.to_dict() == {
        "object": "PCDU-J01", "kind": "connector", "rows": [], "rings": False, "source": "none",
        "source_id": "", "text": "",
    }  # fmt: skip
    got = api.set_row_layout(folder, part="EX-MICROD-9-F", rows="1–5 / 6–9", author="Example Ltd")
    assert got.text == "1–5 / 6–9" and got.source == "own" and got.kind == "part"
    plug = api.row_layout_of(folder, "W001-P1")  # a cable connector: the box connector's rows
    assert (plug.source, plug.source_id, plug.rows) == ("mated", "PCDU-J01", (("1", "2", "3"), ()))
    own = api.set_row_layout(folder, connector="PCDU-J01", rows=[["3", "2", "1"]], rings=True)
    assert (own.source, own.text, own.rings) == ("own", "3–1 (rings)", True)
    back = api.clear_row_layout(folder, connector="PCDU-J01")
    assert (back.source, back.source_id) == ("part", "EX-MICROD-9-F")
    assert api.clear_row_layout(folder, connector="PCDU-J01") == back  # nothing to remove
    entries = api.get_journal(folder, object_id="part:EX-MICROD-9-F").entries
    assert [(e.field, e.author) for e in entries] == [("row_layout", "Example Ltd")]
    assert api.load_project(folder).parts["EX-MICROD-9-F"].row_layout == rows(
        ["1", "2", "3", "4", "5"], ["6", "7", "8", "9"]
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"connector": "W001-P1", "rows": "1 2"}, "is a connector of a harness"),
     ({"part": "EX-MICROD-9-F", "rows": "1 / 1"}, "pin 1 is in row 1 and in row 2"),
     ({"part": "EX-MICROD-9-F", "rows": [["1"], ["1"]]}, "pin 1 is in row 1 and in row 2"),
     ({"part": "EX-MICROD-9-F", "rows": ""}, "give the rows"),
     ({"part": "EX-MICROD-9-F", "rows": "1–10"}, "names 10 pins; the part has 9")],
)  # fmt: skip
def test_the_scripting_functions_refuse_with_the_reason(tmp_path: Path, kwargs, message) -> None:
    folder = tmp_path / "p"
    save_project(mini3(), folder)

    def files() -> list[tuple[Path, bytes]]:
        found = (f for f in folder.rglob("*") if f.is_file() and not f.name.startswith("."))
        return sorted((f.relative_to(folder), f.read_bytes()) for f in found)

    before = files()
    with pytest.raises(EditError, match=message):
        api.set_row_layout(folder, **kwargs)
    assert files() == before
