# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index"
"""A project with row layouts, to run the written outputs over (format 4; design of 4.0.0
section 7, pull request 3).

`row_layout_project()` is the sample `mini3`, generated, with two layouts a person entered:

- the part `EX-MICROD-9-F` has the rows `1 3 / 2`, so its box connectors `OBC-J02`, `PCDU-J01` and
  `PCDU-J02` take them from the part, the cable connector `W001-P2` (of that part) too, and
  `W001-P1` (part `EX-MICROD-9-M`, without rows) the rows of `PCDU-J01`, which it plugs into;
- the box connector `RW1-J02` has its own rows `5 4 / 1`, so its pins 2 and 3 are in no row, and
  `W002-P2`, which plugs into it, takes them.

Both harnesses so have a connector with a layout; `OBC-J01`, `OBC-J03`, `PCDU-J03` and `RW1-J01`
have none. The rows are not those of a real Micro-D (none is shipped, L3): they are chosen so that
the order of a near block in the plan differs from the pin order. The golden set
`tests/fixtures/outputs/row_layout*` and `harness_plan/row_layout*` is made from it.
"""

from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.model import Project, evolve
from harness_design_studio.core.row_layout import parse_text
from harness_design_studio.core.samples import mini3

PART = "EX-MICROD-9-F"
PART_ROWS = "1 3 / 2"
OWN = "RW1-J02"
OWN_ROWS = "5 4 / 1"
# the text files of the golden set kept to read in a diff
TEXT_FILES = (
    "system/box_pinouts.csv",
    "harnesses/W001/pinouts.csv",
    "harnesses/W002/pinouts.csv",
    "system/export.json",
)


def row_layout_project() -> Project:
    p = mini3()
    generate_project(p)
    p.parts[PART] = evolve(p.parts[PART], row_layout=parse_text(PART_ROWS))
    p.connectors[OWN] = evolve(p.connectors[OWN], row_layout=parse_text(OWN_ROWS))
    return p


def golden_text_files(files: dict[str, bytes]) -> dict[str, bytes]:
    """The files of the golden set kept as text to review."""
    return {rel: files[rel] for rel in TEXT_FILES}
