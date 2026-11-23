# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,union-attr,type-arg,attr-defined"
"""REQ-LIB-09. The library update compares the ICD fields of a connector and the level of a pin
(design of 5.0.0, `docs/ait/DESIGN_5.0_FORMAT_5.md` sections 2.6 and 9, part F; patch 4.4.1).

The run of section 2.6: a copy of `first-steps`, `save-device p RW1 --library lib`, then a change
in `lib/RW1.device.json` of one field only, `source_doc`, `source_version` or `source_link` of the
connector RW1-J01, or `level` of its pin 1. Each reads *library changed* (in the core and on the
command line), the diff has the one row, `--apply` takes it and the device is up to date again.
A device whose library-owned fields are equal still reads *up to date* and gives no row; a change
of the function with the level lists both, in the order of the fields."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio.cli.jsonout import SHAPES
from harness_design_studio.cli.main import main
from harness_design_studio.core import library_link as ll
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import Connector, Pin

DEVICE = "RW1"
BOX = "RW1-J01"
PIN = "1"
FILE = "RW1.device.json"


def cli(capsys: pytest.CaptureFixture[str], *argv: object) -> tuple[int, str, str]:
    rc = main([str(a) for a in argv])
    got = capsys.readouterr()
    return rc, got.out, got.err


def doc(capsys: pytest.CaptureFixture[str], *argv: object, rc: int = 0) -> dict:
    code, out, err = cli(capsys, *argv, "--json")
    assert code == rc, (argv, out, err)
    found = json.loads(out)
    assert list(found) == list(SHAPES["update-device"])
    return found


def files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and not p.name.startswith(".harness.lock")
    }


def connector(data: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in data["devices"][0]["connectors"] if c["id"] == BOX)


def pin(data: dict[str, Any]) -> dict[str, Any]:
    return next(p for p in connector(data)["pins"] if p["id"] == PIN)


def edit_library(lib: Path, change) -> None:
    path = lib / FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def project_connector(proj: Path) -> Connector:
    return load_project(proj).project.connectors[BOX]


def project_pin(proj: Path) -> Pin:
    return next(p for p in project_connector(proj).pins if p.id == PIN)


def state(proj: Path, lib: Path) -> str:
    project = load_project(proj).project
    found = ll.link_state(project, ll.project_libraries(proj, [lib]), DEVICE)
    assert found is not None
    return found.state


@pytest.fixture
def folders(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[Path, Path]:
    """A copy of `first-steps` whose RW1 was saved to the library `lib` (the run of 2.6)."""
    proj, lib = tmp_path / "p", tmp_path / "lib"
    lib.mkdir()
    assert cli(capsys, "new", proj, "--template", "first-steps")[0] == 0
    assert cli(capsys, "save-device", proj, DEVICE, "--library", lib)[0] == 0
    return proj, lib


# The field, where it is (the connector or its pin), the value the library gets.
CASES = [
    ("source_doc", "connector", "ICD-RW"),
    ("source_version", "connector", "Issue 2"),
    ("source_link", "connector", "https://example.org/icd/rw"),
    ("level", "pin", "3V3"),
]


def test_an_unchanged_device_reads_up_to_date(folders, capsys):
    proj, lib = folders
    assert state(proj, lib) == ll.UP_TO_DATE
    rc, out, _ = cli(capsys, "update-device", proj, DEVICE, "--library", lib)
    assert rc == 0 and f"{DEVICE}: up to date." in out
    found = doc(capsys, "update-device", proj, DEVICE, "--library", lib)
    assert [d["rows"] for d in found["devices"]] == [[]]
    before = files(proj)
    assert cli(capsys, "update-device", proj, DEVICE, "--library", lib, "--apply")[0] == 0
    assert files(proj) == before
    assert cli(capsys, "update-device", proj, "--library", lib, "--check")[0] == 0


@pytest.mark.parametrize(("name", "where", "value"), CASES, ids=[c[0] for c in CASES])
def test_a_library_change_of_one_icd_field_is_seen_and_taken(folders, capsys, name, where, value):
    proj, lib = folders
    on_pin = where == "pin"
    get = project_pin if on_pin else project_connector
    assert getattr(get(proj), name) is None
    edit_library(lib, lambda d: (pin(d) if on_pin else connector(d)).update({name: value}))

    assert state(proj, lib) == ll.LIBRARY_CHANGED
    before = files(proj)
    rc, out, _ = cli(capsys, "update-device", proj, DEVICE, "--library", lib)
    assert rc == 0 and f"{DEVICE}: library changed" in out
    assert name in out and value in out and files(proj) == before
    found = doc(capsys, "update-device", proj, DEVICE, "--library", lib)
    (rw1,) = found["devices"]
    assert rw1["state"] == ll.LIBRARY_CHANGED
    assert rw1["rows"] == [
        {
            "device": DEVICE,
            "connector": BOX,
            "pin": PIN if on_pin else "",
            "field": name,
            "here": "",
            "library": value,
            "locked_by": "",
        }
    ]
    assert cli(capsys, "update-device", proj, "--library", lib, "--check")[0] == 1
    assert files(proj) == before

    rc, out, _ = cli(capsys, "update-device", proj, DEVICE, "--library", lib, "--apply")
    assert rc == 0 and f"Took the library's version of {DEVICE}" in out
    assert getattr(get(proj), name) == value
    assert state(proj, lib) == ll.UP_TO_DATE
    assert cli(capsys, "update-device", proj, "--library", lib, "--check")[0] == 0


def test_the_run_of_the_design_lists_every_field_in_order(folders, capsys):
    """Section 2.6: the source document, its issue and the level of pin 1, then the function of
    pin 1 as well; every row is listed (the connector's fields before the pin's), and `--apply`
    takes them all."""
    proj, lib = folders
    assert project_pin(proj).function != "Wheel speed"

    def change(d: dict[str, Any]) -> None:
        connector(d).update(source_doc="ICD-RW", source_version="Issue 2")
        pin(d).update(level="3V3", function="Wheel speed")

    edit_library(lib, change)
    rc, out, _ = cli(capsys, "update-device", proj, DEVICE, "--library", lib)
    assert rc == 0 and f"{DEVICE}: library changed" in out
    found = doc(capsys, "update-device", proj, DEVICE, "--library", lib)
    rows = [
        (r["connector"], r["pin"], r["field"], r["library"]) for r in found["devices"][0]["rows"]
    ]
    assert rows == [
        (BOX, "", "source_doc", "ICD-RW"),
        (BOX, "", "source_version", "Issue 2"),
        (BOX, PIN, "function", "Wheel speed"),
        (BOX, PIN, "level", "3V3"),
    ]
    assert cli(capsys, "update-device", proj, DEVICE, "--library", lib, "--apply")[0] == 0
    c, p = project_connector(proj), project_pin(proj)
    assert (c.source_doc, c.source_version, p.level, p.function) == (
        "ICD-RW", "Issue 2", "3V3", "Wheel speed",
    )  # fmt: skip
    assert state(proj, lib) == ll.UP_TO_DATE


def test_the_fields_are_library_owned_and_keep_the_order_of_4_4_0():
    """The lists of 4.4.0 stay as they were, in their order, with the four fields after them;
    every connector field sorts before every pin field, and no two fields share a place."""
    assert ll.CONNECTOR_FIELDS == (
        "name", "part_id", "gender", "keying", "carries", "notes", "label", "row_layout",
        "source_doc", "source_version", "source_link",
    )  # fmt: skip
    assert ll.PIN_FIELDS == (
        "signal", "fixed", "function", "contact_size", "termination", "contact_part", "role",
        "direction", "level",
    )  # fmt: skip
    own = [ll._FIELD_ORDER[f] for f in ("connector", "pin", *ll.CONNECTOR_FIELDS)]
    pins = [ll._FIELD_ORDER[f] for f in ll.PIN_FIELDS]
    assert own == sorted(own) and pins == sorted(pins) and max(own) < min(pins)
    assert len(set(pins)) == len(pins) and max(pins) < 99
