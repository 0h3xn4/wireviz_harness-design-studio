# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""2.4.0 (D-247, owner decision of 2026-11-18): a new project makes one harness that branches.

"That should be the default actually, because most connectors will be custom and bespoke." A new
project (`new FOLDER`, the blank example, the editor's New project, `api.create_project`) starts
with `segmentation.mode` = `per_connector_group`; the examples with outputs keep the mode their
outputs were made with; a project that names `per_connector_pair` keeps it, and the editor offers
the switch once (`branching.branch_offer`). The case behind it: one device with a 21-pin Micro-D
that carries RS-422, RS-485 and CAN to three devices with one connector each gives one harness with
one plug on the Micro-D. Example data only."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness_design_studio import api
from harness_design_studio.cli.main import main as cli_main
from harness_design_studio.core import branching, settings, templates
from harness_design_studio.core.assumptions import ASSUMPTIONS
from harness_design_studio.core.generate import segmentation
from harness_design_studio.core.generate.engine import generate_project, plan_generation
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.model import (
    ConfigFile,
    Connector,
    Endpoint,
    InterfaceInstance,
    InterfaceType,
    Pin,
    Project,
    SignalDef,
    Unit,
)
from harness_design_studio.core.samples import new_project, start_project

GROUP = "per_connector_group"
PAIR = "per_connector_pair"
# the mode each template starts in: the blank project is the start of new work; the other four are
# examples of a finished design whose outputs are fixed (`tools.output_hashes`, the numbers
# snapshot), so they keep the mode their outputs were made with
TEMPLATE_MODES = {
    "blank": GROUP,
    "first-steps": PAIR,
    "minimal-satellite": PAIR,
    "small-satellite": PAIR,
    "flatsat": "per_zone_pair",
    "full-connectors": PAIR,  # one harness per pair of connectors reads easily (design of 5.1.0)
    "names-and-ports": GROUP,  # OBC1-J01 serves TTC1 and TTC2: one harness that branches
    "splice-by-hand": PAIR,  # no interface: Generate makes nothing, the mode is not used
    "splice-from-connection": PAIR,
    "branching-harness": GROUP,  # the feature: one harness per device connector that serves two
    "loose-cable-end": PAIR,
    "shields-and-ends": PAIR,
    "lengths-to-the-face": PAIR,
    "released-harness": PAIR,
    "overrides-and-deviations": PAIR,
    "build-data-and-as-built": PAIR,
    "imports-from-files": PAIR,
}


def mode_on_disk(folder: Path) -> Any:
    data = json.loads((folder / "config" / "segmentation.json").read_text(encoding="utf-8"))
    return data["values"]["mode"]


# ---- every way a person starts a new project --------------------------------------------------


def test_every_template_is_listed_with_its_mode() -> None:
    assert [t.name for t in templates.TEMPLATES] == list(TEMPLATE_MODES)


@pytest.mark.parametrize("name", list(TEMPLATE_MODES))
def test_a_project_from_a_template_starts_in_its_mode(tmp_path: Path, name: str) -> None:
    project = templates.create_project(tmp_path / name, name)
    assert project.config["segmentation"].values["mode"] == TEMPLATE_MODES[name]
    assert mode_on_disk(tmp_path / name) == TEMPLATE_MODES[name]


def test_new_folder_starts_in_per_connector_group(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli_main(["new", str(tmp_path / "p")]) == 0
    capsys.readouterr()
    assert mode_on_disk(tmp_path / "p") == GROUP
    assert cli_main(["new", str(tmp_path / "q"), "--template", "first-steps"]) == 0
    assert mode_on_disk(tmp_path / "q") == PAIR  # an example keeps its outputs


def test_the_scripting_interface_starts_in_per_connector_group(tmp_path: Path) -> None:
    project = api.create_project(tmp_path / "p")
    assert project.config["segmentation"].values["mode"] == GROUP
    assert mode_on_disk(tmp_path / "p") == GROUP


def test_the_blank_example_is_the_start_of_a_project() -> None:
    """The bundled blank project is `start_project` (tools/build_examples.py); `new_project`, on
    which the examples and the tests build, keeps per_connector_pair."""
    loaded = load_project(templates._root() / "projects" / "blank").project
    assert loaded.config["segmentation"].values == {"mode": GROUP}
    assert start_project("x").config["segmentation"].values == {"mode": GROUP}
    assert new_project("x").config["segmentation"].values == {"mode": PAIR}


def test_the_registry_and_the_assumption_name_the_mode_of_a_new_project() -> None:
    """The registry's default stays per_connector_pair (what a file that names no mode, or an
    unknown one, is read as: the groups of 2.2); it says what a new project starts in."""
    s = settings.setting("segmentation", "mode")
    assert s is not None and s.default == PAIR
    assert segmentation.NEW_PROJECT_MODE == GROUP
    assert "A new project starts in per_connector_group (since 2.4.0, D-247)" in s.what
    assert "a project keeps the mode it names" in s.what
    text = ASSUMPTIONS["A-SEGMENT-MODE"].text
    assert "per_connector_group: the mode a new project starts in since 2.4.0" in text
    assert "per_connector_pair, the default of a file that names no mode" in text


# ---- the case behind the decision: one Micro-D, three buses, three devices ----------------------


def bus(tid: str, name: str, *signals: tuple[str, str | None]) -> InterfaceType:
    """A custom interface type, as a person makes one for a bespoke connector."""
    return InterfaceType(
        id=tid, name=name, category="data", construction="twisted_shielded_pair",
        shielding="overall", signals=[SignalDef(name=n, direction="bidir", pair=pr) for n, pr in signals],
    )  # fmt: skip


BUSES = {
    "rs422_gnd": bus(
        "rs422_gnd", "RS-422 with ground",
        ("TX+", "TX"), ("TX-", "TX"), ("RX+", "RX"), ("RX-", "RX"), ("GND", None),
    ),  # fmt: skip
    "rs485_2w": bus("rs485_2w", "RS-485 2-wire", ("D+", "D"), ("D-", "D"), ("GND", None)),
    "can_gnd": bus("can_gnd", "CAN with ground", ("CAN_H", "BUS"), ("CAN_L", "BUS"), ("CAN_GND", None)),
}  # fmt: skip
FAR = {"rs422_gnd": "SENSOR", "rs485_2w": "ACTUATOR", "can_gnd": "NODE"}
MICRO_D = "OBC-J01"


def micro_d(p: Project) -> Project:
    """OBC with one 21-pin Micro-D (`OBC-J01`) and three devices with one 9-pin connector each;
    RS-422, RS-485 and CAN from the Micro-D to one device each."""
    p.interface_types.update(BUSES)
    p.units["OBC"] = Unit(id="OBC", name="On-board computer", subsystem="avionics", side="nominal")
    p.connectors[MICRO_D] = Connector(
        id=MICRO_D, name="J01", role="box", part_id="EX-MICROD-21-F", unit_id="OBC",
        gender="female", pins=[Pin(id=str(k + 1)) for k in range(21)],
    )  # fmt: skip
    for n, (tid, far) in enumerate(FAR.items(), start=1):
        p.units[far] = Unit(id=far, name=far.title(), subsystem="avionics", side="nominal")
        p.connectors[f"{far}-J01"] = Connector(
            id=f"{far}-J01", name="J01", role="box", part_id="EX-MICROD-9-M", unit_id=far,
            gender="male", pins=[Pin(id=str(k + 1)) for k in range(9)],
        )  # fmt: skip
        iid = f"IF-{n:03d}"
        p.interfaces[iid] = InterfaceInstance(
            id=iid, name=BUSES[tid].name, type_id=tid,
            endpoints=[Endpoint(unit_id="OBC", connector_id=MICRO_D), Endpoint(unit_id=far, connector_id=f"{far}-J01")],
        )  # fmt: skip
    return p


def codes(p: Project) -> list[str]:
    return [f.code for f in plan_generation(p).report.findings]


def test_a_new_project_gives_one_harness_with_one_plug_on_the_micro_d() -> None:
    p = micro_d(start_project("Micro-D"))  # the mode of a new project, not set by the test
    assert segmentation.mode_of(p) == GROUP
    assert "box_connector_shared" not in codes(p)
    generate_project(p)
    assert list(p.harnesses) == ["W001"]
    h = p.harnesses["W001"]
    assert [c.mates_with for c in h.connectors].count(MICRO_D) == 1  # ONE plug on the Micro-D
    assert sorted(c.mates_with or "" for c in h.connectors) == sorted(
        [MICRO_D, *(f"{far}-J01" for far in FAR.values())]
    )
    assert len(h.branch_points) == 1 and len(h.segments) == 4  # the trunk and three legs
    signals = sorted(w.signal or "" for w in h.wires)
    assert len(h.wires) == 11 and signals.count("GND") == 2 and "CAN_GND" in signals
    assert sorted(h.interfaces) == ["IF-001", "IF-002", "IF-003"]
    assert branching.branch_offer(p) is None


def test_the_same_project_in_per_connector_pair_gets_three_plugs_and_the_offer() -> None:
    """A project made before 2.4.0 keeps per_connector_pair: three cables with three plugs on the
    one Micro-D (`box_connector_shared`), and the editor's offer names the connector and them."""
    p = micro_d(new_project("older tool"))
    assert segmentation.mode_of(p) == PAIR
    assert codes(p).count("box_connector_shared") == 1
    generate_project(p)
    assert list(p.harnesses) == ["W001", "W002", "W003"]
    offer = branching.branch_offer(p)
    assert offer == branching.BranchOffer((MICRO_D,), ("W001", "W002", "W003"))
    p.config["segmentation"] = ConfigFile(
        name="segmentation", placeholder=True, values={"mode": GROUP}
    )
    assert branching.branch_offer(p) is None  # the mode that joins them: nothing to offer
    generate_project(p)
    assert list(p.harnesses) == ["W001"] and len(p.harnesses["W001"].segments) == 4


def test_no_offer_without_a_shared_connector_or_in_another_mode() -> None:
    p = new_project("pairs")
    for u in ("A", "B", "C", "D"):
        p.units[u] = Unit(id=u, name=u, subsystem="s", side="nominal")
        p.connectors[f"{u}-J01"] = Connector(
            id=f"{u}-J01", name="J01", role="box", part_id="EX-MICROD-25-F", unit_id=u,
            gender="female", pins=[Pin(id=str(k + 1)) for k in range(25)],
        )  # fmt: skip
    for n, (a, b) in enumerate((("A", "B"), ("C", "D")), start=1):
        p.interfaces[f"IF-00{n}"] = InterfaceInstance(
            id=f"IF-00{n}", name=f"IF-00{n}", type_id="rs422",
            endpoints=[Endpoint(unit_id=a, connector_id=f"{a}-J01"), Endpoint(unit_id=b, connector_id=f"{b}-J01")],
        )  # fmt: skip
    generate_project(p)
    assert len(p.harnesses) == 2 and branching.branch_offer(p) is None
    zones = micro_d(new_project("zones"))
    zones.config["segmentation"] = ConfigFile(
        name="segmentation", placeholder=True, values={"mode": "per_unit_pair"}
    )
    generate_project(zones)
    assert (
        len(zones.harnesses) == 3 and branching.branch_offer(zones) is None
    )  # chosen by the project
