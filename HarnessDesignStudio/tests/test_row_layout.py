# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index,union-attr"
"""REQ-PIN-05: the row layout of a connector (format 4, D-250, D-251; design of 4.0.0
`docs/ait/DESIGN_4.0_ROW_LAYOUT.md` sections 3, 4.1, 4.2, 6.1 and 13, pull request 1).

`RowLayout` (`core/model/physical.py`) is the rows of a connector's insert, each a list of pin
names, with the mark `rings`; it is held by a connector part (`Part.row_layout`) and by a box
connector (`Connector.row_layout`), both left out of the files while unset. The rules of section
4.2 are checked when a file is read: a part or a connector that breaks one is set aside with the
reason. `core/row_layout.py` works out the layout of a connector by the rules of section 3, has the
text form of section 6.1 and the rows from their lengths, and keeps a box connector's own rows in
step with its pins when a pin is renamed or deleted (`core/devices.py`).
"""

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from harness_design_studio.core import devices, row_layout
from harness_design_studio.core.commands import History, apply_ops
from harness_design_studio.core.edit import EditError
from harness_design_studio.core.ids import PIN_RE
from harness_design_studio.core.io import canonical
from harness_design_studio.core.io.layout import model_hash, serialize
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.model import Connector, Part, Pin, RowLayout, evolve
from harness_design_studio.core.model.physical import MAX_ROWS
from harness_design_studio.core.row_layout import (
    follow_pins,
    from_lengths,
    layout_of,
    layout_text,
    parse_lengths,
    parse_text,
)
from harness_design_studio.core.samples import mini3

MICROD_21 = [[str(n) for n in range(1, 12)], [str(n) for n in range(12, 22)]]


def rows(*rows: list[str], rings: bool = False) -> RowLayout:
    return RowLayout(rows=[list(r) for r in rows], rings=rings)


def box(pins: int = 21, **changes) -> Connector:
    return Connector(
        id="DEV-J1", name="J1", role="box", part_id="EX-MICROD-21-F", unit_id="DEV",
        pins=[Pin(id=str(n)) for n in range(1, pins + 1)], **changes,
    )  # fmt: skip


def refused(make, message: str) -> None:
    with pytest.raises(ValidationError) as exc:
        make()
    assert message in str(exc.value), str(exc.value)


# ---- the model and the rules of section 4.2 ------------------------------------------------------


def test_a_layout_round_trips_and_is_left_out_while_unset() -> None:
    part = Part(id="EX-MICROD-21-F", category="connector", pin_count=21)
    assert "row_layout" not in part.model_dump(mode="json")
    assert "row_layout" not in box().model_dump(mode="json")
    with_rows = evolve(part, row_layout=RowLayout(rows=MICROD_21))
    data = with_rows.model_dump(mode="json")
    assert data["row_layout"] == {"rows": MICROD_21}  # `rings` left out while false
    assert Part.model_validate(data) == with_rows
    ring = rows(["1", "2", "3"], ["4"], rings=True)
    assert ring.model_dump(mode="json") == {"rows": [["1", "2", "3"], ["4"]], "rings": True}
    own = box(row_layout=ring)
    assert Connector.model_validate(own.model_dump(mode="json")) == own


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: RowLayout(rows=[]), "at least one row"),
        (lambda: rows(["1"], []), "row 2 is empty"),
        (lambda: rows(["1", "7"], ["7"]), "pin 7 is in row 1 and in row 2"),
        (lambda: rows(["7", "a", "A"]), "pin A is twice in row 1"),
        (lambda: RowLayout(rows=[[str(n)] for n in range(1, MAX_ROWS + 2)]), "at most 64 rows"),
        (lambda: rows([str(n) for n in range(1, 1002)]), "at most 1000 pins"),
        (lambda: rows(["1/2"]), "pin names use letters"),
        (lambda: RowLayout(rows=[["1"]], rings="yes"), "valid boolean"),
        (lambda: RowLayout.model_validate({"rows": [["1"]], "offset": 1}), "Extra inputs"),
    ],
)
def test_each_rule_of_a_layout_is_refused_with_its_reason(make, message: str) -> None:
    refused(make, message)


def test_64_rows_and_1000_pins_are_allowed() -> None:
    assert len(RowLayout(rows=[[str(n)] for n in range(1, MAX_ROWS + 1)]).rows) == 64
    assert len(rows([str(n) for n in range(1, 1001)]).names()) == 1000


def test_a_part_layout_is_for_a_connector_part_within_its_pin_count() -> None:
    refused(
        lambda: Part(id="W1", category="wire", row_layout=rows(["1"])),
        "only a connector part has a row layout; W1 is a part of category wire",
    )
    refused(
        lambda: Part(id="P", category="connector", pin_count=21, row_layout=rows(*MICROD_21, ["22"])),
        "the row layout names 22 pins; the part has 21",
    )  # fmt: skip
    assert Part(id="P", category="connector", row_layout=rows(["A1", "B7"])).row_layout
    assert Part(id="P", category="connector", pin_count=21, row_layout=rows(["1", "12"]))


def test_an_own_layout_is_for_a_box_connector_and_names_its_pins() -> None:
    refused(
        lambda: box(row_layout=rows(*MICROD_21, ["22"])),
        "the row layout names pin 22; DEV-J1 has no pin 22",
    )
    refused(
        lambda: Connector(
            id="W001-P1",
            name="P1",
            role="cable",
            part_id="X",
            mates_with="DEV-J1",
            pins=[Pin(id="1")],
            row_layout=rows(["1"]),
        ),  # fmt: skip
        "only a box connector has its own row layout; W001-P1 takes the rows of its part",
    )
    assert box(row_layout=rows(["1", "2"])).row_layout  # not every pin needs a row


def test_a_file_with_a_broken_layout_sets_the_object_aside_with_the_reason(tmp_path: Path) -> None:
    root = tmp_path / "p"
    save_project(mini3(), root)
    path = root / "physical" / "connectors" / "power.json"
    doc = json.loads(path.read_bytes())
    doc["connectors"][0]["row_layout"] = {"rows": [["1", "2"], ["2"]]}
    path.write_bytes(canonical.dumps(doc))
    parts = root / "library" / "connector.json"
    lib = json.loads(parts.read_bytes())
    lib["parts"][0]["row_layout"] = {"rows": []}
    parts.write_bytes(canonical.dumps(lib))
    r = load_project(root)
    messages = [i.message for i in r.issues if i.code == "quarantined"]
    assert any("pin 2 is in row 1 and in row 2" in m for m in messages), messages
    assert any("at least one row" in m for m in messages), messages
    assert {q.file for q in r.project.quarantine} >= {
        "physical/connectors/power.json", "library/connector.json",
    }  # fmt: skip


def test_a_layout_is_in_the_model_hash_and_saved_sparse(tmp_path: Path) -> None:
    p = mini3()
    before, files = model_hash(p), serialize(p)
    cid = "PCDU-J01"
    p.connectors[cid] = evolve(p.connectors[cid], row_layout=rows(["1", "2"], ["3"]))
    pid = "EX-MICROD-21-F"
    p.parts[pid] = evolve(p.parts[pid], row_layout=RowLayout(rows=MICROD_21))
    assert model_hash(p) != before
    after = serialize(p)
    changed = {rel for rel in after if after[rel] != files.get(rel)}
    assert changed == {"physical/connectors/power.json", "library/connector.json"}
    save_project(p, tmp_path / "p")
    q = load_project(tmp_path / "p")
    assert not q.has_errors and model_hash(q.project) == model_hash(p)
    assert q.project.connectors[cid].row_layout == rows(["1", "2"], ["3"])


# ---- where the layout of a connector comes from (section 3) -------------------------------------


def _project_with(part_rows=None, own_rows=None):
    p = mini3()
    box_id = "PCDU-J01"  # W001-P1 plugs into it
    part_id = p.connectors[box_id].part_id
    if part_rows is not None:
        p.parts[part_id] = evolve(p.parts[part_id], row_layout=part_rows)
    if own_rows is not None:
        p.connectors[box_id] = evolve(p.connectors[box_id], row_layout=own_rows)
    plug = next(c for c in p.harnesses["W001"].connectors if c.mates_with == box_id)
    return p, p.connectors[box_id], plug


def test_without_a_layout_a_connector_has_none() -> None:
    p, b, plug = _project_with()
    assert layout_of(p, b) is None and layout_of(p, plug) is None


def test_a_box_connector_takes_its_own_rows_before_its_parts() -> None:
    p, b, _plug = _project_with(rows(["1", "2", "3"]), rows(["3", "1"], ["2"]))
    got = layout_of(p, b)
    assert (got.source, got.source_id, got.rows) == ("own", b.id, (("3", "1"), ("2",)))
    p, b, _plug = _project_with(rows(["1", "2"], ["3"]))
    got = layout_of(p, b)
    assert (got.source, got.source_id, got.rows) == ("part", b.part_id, (("1", "2"), ("3",)))


def test_a_cable_connector_takes_its_parts_rows_else_the_mated_box_connectors() -> None:
    p, b, plug = _project_with(None, rows(["2", "1"], ["3"]))
    got = layout_of(p, plug)
    assert (got.source, got.source_id, got.rows) == ("mated", b.id, (("2", "1"), ("3",)))
    p, b, plug = _project_with(rows(["3", "2", "1"]), None)  # the part of the box connector
    got = layout_of(p, plug)
    assert (got.source, got.source_id) == ("mated", b.id) and got.row_of("3") == 1
    pid = plug.part_id
    p.parts[pid] = evolve(p.parts[pid], row_layout=rows(["1"], ["2", "3"]))
    got = layout_of(p, plug)
    assert (got.source, got.source_id, got.rows) == ("part", pid, (("1",), ("2", "3")))


def test_names_that_are_not_pins_are_left_out_and_pins_in_no_row_come_after() -> None:
    p, b, _plug = _project_with(rows(["1", "9"], ["8", "7"], ["2"]))  # the box connector has 1 to 3
    got = layout_of(p, b)
    assert got.rows == (("1",), (), ("2",))  # a row keeps its number
    assert got.left_out == ("9", "8", "7") and got.outside == ("3",)
    assert (got.row_of("1"), got.row_of("2"), got.row_of("3")) == (1, 3, None)
    assert got.order() == ("1", "2", "3") and not got.rings


# ---- the text form (section 6.1) ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1–11 / 12–21", MICROD_21),
        ("1:11/12:21", MICROD_21),
        ("1 – 11 / 12 : 21", MICROD_21),
        ("1 3 5 7 9 / 2 4 6 8 10", [["1", "3", "5", "7", "9"], ["2", "4", "6", "8", "10"]]),
        ("1,2, 3", [["1", "2", "3"]]),
        ("11–9 A1", [["11", "10", "9", "A1"]]),
        ("1-11", [["1-11"]]),  # `-` is part of a name, never a range mark
        ("1..3", [["1..3"]]),  # so is `..`
    ],
)
def test_the_text_form_is_read(text: str, expected: list[list[str]]) -> None:
    assert parse_text(text) == RowLayout(rows=expected)


def test_the_rings_mark_and_an_empty_text() -> None:
    assert parse_text("1–8 / 9–12 (rings)") == RowLayout(
        rows=[[str(n) for n in range(1, 9)], ["9", "10", "11", "12"]], rings=True
    )
    assert parse_text("") is None and parse_text("   ") is None
    assert layout_text(None) == ""


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("1 2 / / 3", "row 2 is empty"),
        ("1 2 / 2", "pin 2 is in row 1 and in row 2"),
        ("01:03", "without a leading zero"),
        ("A:C", "is not a run of pins"),
        ("1–3–5", "more than one range mark"),
        ("1 (rings) / 2", "goes at the end"),
        ("(rings)", "needs rows before it"),
        ("1:5000", "more than 1000 pins"),
        ("1 # 2", "is not a pin name"),
        (" / ".join(str(n) for n in range(1, 66)), "at most 64 rows"),
    ],
)
def test_a_text_that_is_not_a_layout_is_refused_in_words(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_text(text)


@pytest.mark.parametrize(
    ("layout", "text"),
    [
        (RowLayout(rows=MICROD_21), "1–11 / 12–21"),
        (rows(["1", "2"], ["3", "4", "5"]), "1 2 / 3–5"),
        (rows(["5", "4", "3", "7", "A1"]), "5–3 7 A1"),
        (rows(["1", "3", "5"], ["2", "4"]), "1 3 5 / 2 4"),
        (rows(["01", "02", "03"]), "01 02 03"),  # not whole numbers as the writer writes them
        (rows(["1", "2", "3"], rings=True), "1–3 (rings)"),
    ],
)
def test_the_text_form_is_written_with_runs_of_three_or_more(layout, text: str) -> None:
    assert layout_text(layout) == text
    assert parse_text(text) == layout


PIN_NAMES = st.one_of(
    st.integers(min_value=0, max_value=60).map(str),
    st.from_regex(PIN_RE, fullmatch=True).filter(lambda s: not s.endswith(".")),
)


@st.composite
def layouts(draw) -> RowLayout:
    names = draw(st.lists(PIN_NAMES, min_size=1, max_size=40, unique_by=str.casefold))
    cuts = sorted(draw(st.sets(st.integers(1, len(names) - 1), max_size=6))) if len(names) > 1 else []  # fmt: skip
    bounds = [0, *cuts, len(names)]
    return RowLayout(
        rows=[names[a:b] for a, b in zip(bounds, bounds[1:], strict=False)], rings=draw(st.booleans())
    )  # fmt: skip


@settings(max_examples=300, deadline=None)
@given(layouts())
def test_the_text_form_round_trips(layout: RowLayout) -> None:
    assert parse_text(layout_text(layout)) == layout


# ---- the rows from their lengths ------------------------------------------------------------------


def test_the_rows_from_their_lengths_on_a_part_and_on_a_connector() -> None:
    assert parse_lengths("11, 10") == [11, 10] and parse_lengths("3 2") == [3, 2]
    assert from_lengths([11, 10]) == RowLayout(rows=MICROD_21)
    pins = [Pin(id=n) for n in ("A1", "A2", "A3", "B1", "B2", "S")]
    assert from_lengths([3, 2], pins) == rows(["A1", "A2", "A3"], ["B1", "B2"])
    with pytest.raises(ValueError, match="the rows hold 7 pins; the connector has 6"):
        from_lengths([4, 3], pins)
    for bad in ("", "11, 0", "x", "1.5"):
        with pytest.raises(ValueError):
            parse_lengths(bad)


# ---- the edits of a pin keep the own rows in step (section 13) -----------------------------------


def test_follow_pins_renames_drops_and_clears() -> None:
    own = rows(["1", "2"], ["3"])
    pins = [Pin(id=n) for n in ("1", "A2", "3")]
    assert follow_pins(own, pins, {"2": "A2"}) == rows(["1", "A2"], ["3"])
    assert follow_pins(own, [Pin(id="1"), Pin(id="2")]) == rows(["1", "2"])  # the row goes
    assert follow_pins(own, [Pin(id="9")]) is None  # no row left: no layout
    assert follow_pins(own, [Pin(id=n) for n in "1234"]) is own  # nothing changes
    assert follow_pins(None, pins) is None


def _with_own_rows():
    p = mini3()
    cid = "OBC-J01"  # pins 1 to 5, no harness on it
    p.connectors[cid] = evolve(p.connectors[cid], row_layout=rows(["1", "2", "3"], ["4", "5"]))
    return p, cid


def test_renaming_a_pin_renames_it_in_the_own_rows_in_one_undo_step() -> None:
    p, cid = _with_own_rows()
    history = History(p)
    history.execute("rename", devices.ops_rename_pin(p, cid, "2", "A2"))
    assert p.connectors[cid].row_layout == rows(["1", "A2", "3"], ["4", "5"])
    history.undo()
    assert p.connectors[cid].row_layout == rows(["1", "2", "3"], ["4", "5"])


def test_deleting_pins_takes_them_out_of_the_own_rows() -> None:
    p, cid = _with_own_rows()
    apply_ops(p, devices.ops_delete_pins(p, cid, {"4", "5"}))
    assert p.connectors[cid].row_layout == rows(["1", "2", "3"])  # and the empty row goes
    apply_ops(p, devices.ops_delete_pins(p, cid, {"1", "2", "3"}))
    assert p.connectors[cid].row_layout is None


def test_a_new_pin_list_and_a_new_part_keep_the_own_rows_to_the_pins() -> None:
    p, cid = _with_own_rows()
    c = p.connectors[cid]
    apply_ops(p, devices.ops_set_pinout(p, cid, [*c.pins[:2], *c.pins[3:]]))
    assert p.connectors[cid].row_layout == rows(["1", "2"], ["4", "5"])
    apply_ops(p, devices.ops_change_part(p, cid, "EX-MICROD-9-F"))  # 9 pins: nothing goes
    assert p.connectors[cid].row_layout == rows(["1", "2"], ["4", "5"])
    assert Connector.model_validate(p.connectors[cid].model_dump(mode="json"))  # still valid


def test_a_saved_project_after_the_edits_loads_without_a_set_aside_object(tmp_path: Path) -> None:
    p, cid = _with_own_rows()
    apply_ops(p, devices.ops_rename_pin(p, cid, "5", "S"))
    apply_ops(p, devices.ops_delete_pins(p, cid, {"1"}))
    save_project(p, tmp_path / "p")
    r = load_project(tmp_path / "p")
    assert not r.has_errors and not r.project.quarantine
    assert r.project.connectors[cid].row_layout == rows(["2", "3"], ["4", "S"])


def test_a_part_cannot_have_fewer_pins_than_its_rows_name() -> None:
    p = mini3()
    pid = "EX-MICROD-21-F"
    p.parts[pid] = evolve(p.parts[pid], row_layout=RowLayout(rows=MICROD_21))
    with pytest.raises(EditError, match="The row layout of EX-MICROD-21-F names 21 pins"):
        devices.ops_update_part(p, pid, pin_count=20)
    assert devices.ops_update_part(p, pid, pin_count=25)


def test_the_module_only_reads_the_project() -> None:
    p, b, plug = _project_with(rows(["1", "2"], ["3"]), rows(["3"], ["2", "1"]))
    before = model_hash(p)
    layout_of(p, b), layout_of(p, plug), layout_text(b.row_layout)
    assert model_hash(p) == before
    assert row_layout.RANGE_MARKS == ("–", ":")
