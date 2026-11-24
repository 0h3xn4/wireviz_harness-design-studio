# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""4.1.0 (design of 4.1.0, `docs/ait/DESIGN_4.1_PRODUCTION_SHEET.md` part B, REQ-LABEL-02): a new
project starts in the label format `harness_device_connector`.

Every way a person starts a project (`new FOLDER`, `new FOLDER --template blank`, the scripting
interface's `create_project`, the editor's *New project* and the empty project of
`tools.usability_setup`) writes `config/model.json` with `"label_format":
"harness_device_connector"`, not as a placeholder (a label text is not an engineering value, so it
is not listed under *Placeholder files*). The registry default stays `standard`, what a file that
names no format is read as: the examples, the fixtures `mini3`, `sat15` and `custom_device` name
none and keep their labels. Example data only."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio import api
from harness_design_studio.cli.main import main as cli_main
from harness_design_studio.core import label_format, settings, templates
from harness_design_studio.core.assumptions import ASSUMPTIONS
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.outputs import tables
from harness_design_studio.core.samples import mini3, new_project, start_project
from tests.test_default_branching import micro_d

NEW = "harness_device_connector"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "projects"


def model_on_disk(folder: Path) -> Any:
    """`config/model.json` of a project folder as JSON, or None when the folder has none."""
    path = folder / "config" / "model.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def assert_new_format(folder: Path) -> None:
    data = model_on_disk(folder)
    assert data == {
        "name": "model",
        "placeholder": False,
        "values": {"label_format": NEW},
    }
    project = load_project(folder).project
    assert label_format.format_of(project) == NEW
    assert "model" not in project.placeholder_configs()


# ---- every way a person starts a new project --------------------------------------------------


def test_start_project_writes_the_new_format_and_new_project_does_not() -> None:
    started = start_project("x")
    assert started.config["model"].values == {"label_format": NEW}
    assert started.config["model"].placeholder is False
    assert "model" not in started.placeholder_configs()
    assert label_format.format_of(started) == NEW == label_format.NEW_PROJECT_FORMAT
    assert "model" not in new_project("x").config  # the base of the examples and the tests
    assert label_format.format_of(new_project("x")) == "standard"


def test_new_folder_and_the_blank_template_start_in_the_new_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["new", str(tmp_path / "p")]) == 0
    assert cli_main(["new", str(tmp_path / "q"), "--template", "blank"]) == 0
    capsys.readouterr()
    assert_new_format(tmp_path / "p")
    assert_new_format(tmp_path / "q")


def test_the_scripting_interface_starts_in_the_new_format(tmp_path: Path) -> None:
    project = api.create_project(tmp_path / "p")
    assert label_format.format_of(project) == NEW
    assert_new_format(tmp_path / "p")


def test_the_editor_s_new_project_starts_in_the_new_format(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from harness_design_studio.gui.controller import EditorController

    _ = QApplication.instance() or QApplication([])
    ctl = EditorController(drc_delay_ms=600_000)
    ctl.new_project(tmp_path / "p", "Mine")
    try:
        assert label_format.format_of(ctl.project) == NEW
        assert_new_format(tmp_path / "p")
    finally:
        ctl.open_sample()  # releases the lock of the folder


def test_the_empty_project_of_the_usability_material_starts_in_the_new_format(
    tmp_path: Path,
) -> None:
    from tools import usability_setup

    usability_setup.build(tmp_path)
    assert_new_format(tmp_path / "t1-empty")
    assert model_on_disk(tmp_path / "t6-t7-generated") is None  # a sample keeps standard


def test_the_blank_example_is_the_start_of_a_project() -> None:
    folder = templates._root() / "projects" / "blank"
    assert_new_format(folder)


# ---- every existing project keeps its labels ----------------------------------------------------


# the feature example that shows the label format of a new project (design of 5.1.0 section 4.12)
SHOWS_NEW_FORMAT = "build-data-and-as-built"


@pytest.mark.parametrize(
    "name", [t.name for t in templates.TEMPLATES if t.name not in ("blank", SHOWS_NEW_FORMAT)]
)
def test_a_project_from_an_example_keeps_the_standard_format(tmp_path: Path, name: str) -> None:
    folder = tmp_path / name
    project = templates.create_project(folder, name)
    model = model_on_disk(folder)  # lengths-to-the-face sets model.length_reference, no format
    assert model is None or "label_format" not in model["values"], model
    assert label_format.format_of(project) == "standard"


def test_the_build_data_example_shows_the_format_of_a_new_project(tmp_path: Path) -> None:
    folder = tmp_path / "p"
    project = templates.create_project(folder, SHOWS_NEW_FORMAT)
    assert model_on_disk(folder) == {
        "name": "model",
        "placeholder": False,
        "values": {"label_format": NEW},
    }
    assert label_format.format_of(project) == NEW


@pytest.mark.parametrize("name", ["mini3", "sat15", "custom_device"])
def test_the_fixtures_name_no_format(name: str) -> None:
    folder = FIXTURES / name
    assert model_on_disk(folder) is None
    assert label_format.format_of(load_project(folder).project) == "standard"


def test_the_registry_default_stays_standard_and_says_what_a_new_project_starts_in() -> None:
    s = settings.setting("model", "label_format")
    assert s is not None and s.default == "standard" == label_format.DEFAULT_FORMAT
    assert s.choices == label_format.FORMATS and NEW in s.choices
    assert "A new project starts in harness_device_connector (since 4.1.0, D-256)" in s.what
    assert "a project keeps the format it names, and a file that names none is read as standard" in s.what  # fmt: skip
    template = settings.setting("model", "label_connector_template")
    assert template is not None and "{mates_name}" in template.what
    text = ASSUMPTIONS["A-LABEL-FORMAT"].text
    assert "harness_device_connector" in text and "W001:MTQ1:J01" in text
    assert "the format a new project starts in since 4.1.0" in text


def test_a_value_the_tool_does_not_know_is_still_refused() -> None:
    from harness_design_studio.core import configcheck
    from harness_design_studio.core.model import ConfigFile

    p = start_project("x")
    assert not [i for i in configcheck.validate(p) if i.code == "config_invalid"]
    p.config["model"] = ConfigFile(
        name="model", placeholder=False, values={"label_format": "fancy"}
    )
    found = [i.message for i in configcheck.validate(p) if i.code == "config_invalid"]
    assert found == [
        "config/model.json: label_format must be one of standard, compact, descriptive, custom, "
        "harness_device_connector."
    ]
    assert label_format.format_of(p) == "standard"


# ---- what a new project writes ------------------------------------------------------------------


def test_a_new_project_labels_its_connectors_by_device_and_connector_name() -> None:
    """The Micro-D case of D-247 in a new project: one harness, one plug on each device connector,
    each labelled HARNESS:DEVICE:NAME; the wires keep the standard text."""
    p = micro_d(start_project("Micro-D"))
    generate_project(p)
    h = p.harnesses["W001"]
    texts = {r[0]: r[2] for r in tables.labels(p, h)[1:] if r[1] == "connector"}
    assert sorted(texts.values()) == [
        "W001:ACTUATOR:J01",
        "W001:NODE:J01",
        "W001:OBC:J01",
        "W001:SENSOR:J01",
    ]
    wire = h.wires[0]
    far = f"{wire.to_connector}.{wire.to_pin}"
    assert tables.wire_label_texts(p, wire, h)[0] == f"{wire.id} {wire.signal} to {far}"


def test_an_older_project_keeps_its_labels() -> None:
    p = mini3()
    generate_project(p)
    texts = {r[0]: r[2] for r in tables.labels(p, p.harnesses["W001"])[1:] if r[1] == "connector"}
    assert texts == {"W001-P1": "W001-P1 mates PCDU-J01", "W001-P2": "W001-P2 mates RW1-J01"}


def test_explain_of_a_cable_connector_says_the_person_s_label_is_not_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from harness_design_studio.core.model import evolve

    p = micro_d(start_project("Micro-D"))
    generate_project(p)
    h = p.harnesses["W001"]
    plug = next(c for c in h.connectors if c.mates_with == "OBC-J01")
    p.harnesses["W001"] = evolve(
        h, connectors=[evolve(c, label="Main plug") if c is plug else c for c in h.connectors]
    )
    api.save_project(p, tmp_path / "p")
    capsys.readouterr()
    assert cli_main(["explain", str(tmp_path / "p"), plug.id]) == 0
    out = capsys.readouterr().out
    assert f"Connector {plug.id}. Connector label: W001:OBC:J01" in out
    assert "Device = OBC" in out and "Device connector name = J01" in out
    assert "Label of the cable connector = Main plug" in out
    assert "not printed: the label of a connector is not part of the format harness_device_connector" in out  # fmt: skip
    assert "{name} {harness}:{device}:{mates_name}" in out
    assert "label = harness ID + ':' + device + ':' + name of the device connector" in out
