# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return,arg-type,attr-defined,index"
"""A project with splices, to run the whole tool over (format 3, M6a; section 6 of the design of
2.3.0).

`splice_project()` is the sample `mini3`, generated, with a harness a person drew, `W003` *Power Y*:
a power line from `PCDU-J02` to `OBC-J02` and `OBC-J03` through two splices, `W003-X1` (PWR, a crimp
splice) and `W003-X2` (RTN, a solder sleeve), and segments with lengths (each splice is a node of
the routing tree). `branch_leg_project()` adds `W004`: a harness with a branch point whose one leg
carries a splice. The splice part `EX-SPLICE-1` is marked as example data. Nothing here is shipped;
the golden set `tests/fixtures/outputs/splices*` is made from `splice_project()`.
"""

from harness_design_studio.core.commands import Put, apply_ops
from harness_design_studio.core.generate.engine import generate_project
from harness_design_studio.core.manual_harness import plan_add_connector, plan_new_harness
from harness_design_studio.core.model import Part, Project, evolve
from harness_design_studio.core.model.physical import BranchPoint, Segment
from harness_design_studio.core.samples import mini3
from harness_design_studio.core.splices import plan_add_splice
from harness_design_studio.core.wires import plan_add_wire

SPLICE_PART = "EX-SPLICE-1"
HARNESS = "W003"


def splice_part() -> Part:
    return Part(
        id=SPLICE_PART,
        category="splice",
        manufacturer="Example Co.",
        part_number="EX-SPLICE-1",
        description="Crimp splice, one node (example)",
        pin_count=1,
        mass_g=0.4,
        unverified=True,
    )


def _signals(p: Project, cid: str, names: tuple[str, ...]) -> None:
    c = p.connectors[cid]
    pins = [evolve(x, signal=names[i]) if i < len(names) else x for i, x in enumerate(c.pins)]
    p.connectors[cid] = evolve(c, pins=pins)


def _plug(p: Project, hid: str, box: str) -> str:
    ops, cid = plan_add_connector(p, hid, mates_with=box)
    apply_ops(p, ops)
    return cid


def splice_project() -> Project:
    """The project of the module text."""
    p = mini3()
    generate_project(p)
    for cid in ("PCDU-J02", "OBC-J02", "OBC-J03"):
        _signals(p, cid, ("PWR", "RTN"))
    apply_ops(p, [Put("parts", splice_part())])
    ops, hid = plan_new_harness(p, "Power Y")
    apply_ops(p, ops)
    near = _plug(p, hid, "PCDU-J02")
    far_a = _plug(p, hid, "OBC-J02")
    far_b = _plug(p, hid, "OBC-J03")
    ops, x1 = plan_add_splice(p, hid, SPLICE_PART, termination="crimp")
    apply_ops(p, ops)
    ops, x2 = plan_add_splice(p, hid, SPLICE_PART, termination="solder")
    apply_ops(p, ops)
    for pin, splice, sig, colour in (("1", x1, "PWR", "red"), ("2", x2, "RTN", "black")):
        apply_ops(p, plan_add_wire(p, hid, near, pin, splice, "1", signal=sig, gauge_awg=22, colour=colour))  # fmt: skip
        for far in (far_a, far_b):
            apply_ops(p, plan_add_wire(p, hid, splice, "1", far, pin, signal=sig, gauge_awg=24, colour=colour))  # fmt: skip
    h = p.harnesses[hid]
    segments = [
        Segment(id=f"{hid}-L1", from_node=near, to_node=x1, length_m=0.5),
        Segment(id=f"{hid}-L2", from_node=x1, to_node=x2, length_m=0.02),
        Segment(id=f"{hid}-L3", from_node=x1, to_node=far_a, length_m=1.0),
        Segment(id=f"{hid}-L4", from_node=x1, to_node=far_b, length_m=1.25),
    ]
    apply_ops(p, [Put("harnesses", evolve(h, segments=segments))])
    generate_project(p)  # the device pins changed: Generate again (it keeps W003, a person's)
    return p


def branch_leg_project() -> Project:
    """`splice_project()` with `W004`, a harness a person drew from `PCDU-J03` to an inline
    connector and a test connector: its branch point `W004-B1` has two legs, and the leg towards
    the test connector carries the splice `W004-X1`, which joins SIG to both far connectors."""
    p = splice_project()
    _signals(p, "PCDU-J03", ("SIG", "RTN"))
    ops, hid = plan_new_harness(p, "Branch with a splice")
    apply_ops(p, ops)
    near = _plug(p, hid, "PCDU-J03")
    ops, inline = plan_add_connector(p, hid, part_id="EX-MICROD-9-M", role="inline", pin_ids=["1", "2"])  # fmt: skip
    apply_ops(p, ops)
    ops, test = plan_add_connector(p, hid, part_id="EX-MICROD-9-M", role="test", pin_ids=["1", "2"])  # fmt: skip
    apply_ops(p, ops)
    ops, x1 = plan_add_splice(p, hid, SPLICE_PART, termination="crimp")
    apply_ops(p, ops)
    apply_ops(p, plan_add_wire(p, hid, near, "1", x1, "1", signal="SIG"))
    apply_ops(p, plan_add_wire(p, hid, x1, "1", inline, "1", signal="SIG"))
    apply_ops(p, plan_add_wire(p, hid, x1, "1", test, "1", signal="SIG"))
    apply_ops(p, plan_add_wire(p, hid, near, "2", inline, "2", signal="RTN"))
    h = p.harnesses[hid]
    apply_ops(
        p,
        [
            Put(
                "harnesses",
                evolve(
                    h,
                    branch_points=[BranchPoint(id=f"{hid}-B1", name="Branch 1")],
                    segments=[
                        Segment(id=f"{hid}-L1", from_node=near, to_node=f"{hid}-B1", length_m=0.3),
                        Segment(id=f"{hid}-L2", from_node=f"{hid}-B1", to_node=inline, length_m=0.6),
                        Segment(id=f"{hid}-L3", from_node=f"{hid}-B1", to_node=x1, length_m=0.2),
                        Segment(id=f"{hid}-L4", from_node=x1, to_node=test, length_m=0.4),
                    ],
                ),
            )
        ],
    )  # fmt: skip
    generate_project(p)
    return p


# The harnesses of the golden set that hold splices: their text outputs are kept to read, beside
# the digest of every file of `branch_leg_project()`.
SPLICE_HARNESSES = ("W003", "W004")


def golden_text_files(files: dict[str, bytes]) -> dict[str, bytes]:
    """The written files of the golden set kept as text to review: the CSV, SVG and YAML files of
    the harnesses with splices and the system BOM and mass table."""
    keep = {"system/bom.csv", "system/mass_length.csv"}
    return {
        rel: data
        for rel, data in sorted(files.items())
        if rel in keep
        or (
            rel.split("/")[1:2]
            and rel.split("/")[1] in SPLICE_HARNESSES
            and rel.endswith((".csv", ".svg", ".yaml"))
        )
    }
