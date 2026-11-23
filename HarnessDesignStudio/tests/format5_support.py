# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index"
"""A project with data of format 5, to run the written outputs over (design of 5.0.0
`docs/ait/DESIGN_5.0_FORMAT_5.md` sections 11 and 13; started by pull request 2, part A).

`format5_project()` is the branching fixture of `tests/test_outputs_routing.py` (W001 with two
branch points between DEV2 + DEV3 and DEV1 + DEV4, W002 straight between DEV5 and DEV6; every cable
connector of part `EX-MICROD-25-M`) with a service loop of 0.1 m and every segment given a length,
then given what a person enters for the lengths of part A, and generated again (Generate keeps it):

- the connector part `EX-MICROD-25-M` has a depth of 25 mm, and a backshell part
  `EX-BACKSHELL-25` one of 30 mm;
- W001-P1 and W001-P2 are measured to the mating face (`length_to`), W001-P3 and W001-P4 to the
  rear (the setting, unset); the backshell `W001-A1` (`EX-BACKSHELL-25`) sits on W001-P1. So a wire
  of W001-P1 loses 0.055 m, one of W001-P2 0.025 m, and `segments.csv` marks the two face ends;
- W002-P2 is measured to its face, and the backshell `W002-A1` on it has no part: the depth of that
  end is not known, so the wires of W002 have no length, and `check` says why
  (`length_depth_missing`).

The depths are made up (no real part is shipped, D-12). The later pull requests of the design add
their data to this project. The golden set `tests/fixtures/outputs/format5*` is made from it.
"""

from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import (
    Accessory,
    ConfigFile,
    Part,
    Project,
    evolve,
)

BACKSHELL = "EX-BACKSHELL-25"
CONNECTOR_PART = "EX-MICROD-25-M"
SEGMENTS = {"W001-L3": 0.375, "W001-L5": 0.3, "W002-L1": 0.8}
# the text files of the golden set kept to read in a diff
TEXT_FILES = (
    "harnesses/W001/wirelist.csv",
    "harnesses/W001/segments.csv",
    "harnesses/W001/wireviz.yaml",
    "harnesses/W002/wirelist.csv",
    "system/export.json",
)


def _with_loop(p: Project, loop: float) -> None:
    old = p.config["generation"]
    p.config = {
        **p.config,
        "generation": ConfigFile(
            name="generation",
            placeholder=old.placeholder,
            values={**old.values, "service_loop_m": loop},
        ),
    }


def format5_project() -> Project:
    from tests.test_outputs_routing import branching_project

    p = branching_project()
    _with_loop(p, 0.1)
    for hid in ("W001", "W002"):
        h = p.harnesses[hid]
        segments = [evolve(x, length_m=SEGMENTS.get(x.id, x.length_m)) for x in h.segments]
        p.harnesses[hid] = evolve(h, segments=segments)
    p.parts[CONNECTOR_PART] = evolve(p.parts[CONNECTOR_PART], depth_mm=25.0)
    p.parts[BACKSHELL] = Part(
        id=BACKSHELL, category="backshell", manufacturer="Example Ltd", part_number=BACKSHELL,
        description="Example backshell for a 25-way connector", depth_mm=30.0, unverified=True,
    )  # fmt: skip
    w1 = p.harnesses["W001"]
    p.harnesses["W001"] = evolve(
        w1,
        connectors=[
            evolve(c, length_to="face") if c.id in ("W001-P1", "W001-P2") else c
            for c in w1.connectors
        ],
        accessories=[
            Accessory(id="W001-A1", kind="backshell", part_id=BACKSHELL, target="W001-P1")
        ],
    )
    w2 = p.harnesses["W002"]
    p.harnesses["W002"] = evolve(
        w2,
        connectors=[evolve(c, length_to="face") if c.id == "W002-P2" else c for c in w2.connectors],
        accessories=[Accessory(id="W002-A1", kind="backshell", target="W002-P2")],
    )
    generate_project(p)
    return p


def golden_text_files(files: dict[str, bytes]) -> dict[str, bytes]:
    """The files of the golden set kept as text to review."""
    return {rel: files[rel] for rel in TEXT_FILES}
