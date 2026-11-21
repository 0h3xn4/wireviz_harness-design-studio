# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""CD-X4: a device made with the editor's plans is the device a person writes by hand. The two
projects are saved and compared byte for byte, and with the committed fixture
`tests/fixtures/projects/custom_device` (device written without the editor, then generated); a
second Generate has nothing to do, the verifier and the design rules find nothing new, and the
rule count stays 43. Rebuild the fixture on purpose with
`python -c "from tests.test_device_equivalence import write_fixture; write_fixture()"` and review
the diff."""

from pathlib import Path

from harness_design_studio.core import devices, edit
from harness_design_studio.core.commands import History, Op, Put, apply_ops
from harness_design_studio.core.drc import RULES, run
from harness_design_studio.core.generate.engine import generate_project, plan_generation
from harness_design_studio.core.integrity import check_integrity
from harness_design_studio.core.io.layout import model_hash
from harness_design_studio.core.io.loader import load_project
from harness_design_studio.core.io.saver import save_project
from harness_design_studio.core.issues import errors
from harness_design_studio.core.model import Connector, Part, Pin, Placement, Project, Unit
from harness_design_studio.core.samples import new_project
from harness_design_studio.core.verify import verify_project

FIXTURE = Path(__file__).parent / "fixtures" / "projects" / "custom_device"


def base() -> Project:
    """The project both versions start from: a computer, a power unit, the custom parts."""
    p = new_project("custom device (example data)")
    for part in (
        Part(id="MY-HD-6-F", category="connector", pin_count=6, mates_with="MY-HD-6-M",
             description="Custom 6-pin, female", unverified=True),
        Part(id="MY-HD-6-M", category="connector", pin_count=6, mates_with="MY-HD-6-F",
             description="Custom 6-pin, male", unverified=True),
    ):  # fmt: skip
        p.parts[part.id] = part
    for template in ("computer", "pdu"):
        ops, _ = edit.ops_add_unit(p, template)
        History(p).execute("add", ops)
    p.units["GYRO1"] = Unit(id="GYRO1", name="Gyro unit", subsystem="aocs", side="nominal")
    p.placements["GYRO1"] = Placement(id="GYRO1", x=edit.lane_x(1), y=40)
    return p


def _interfaces(p: Project) -> None:
    for type_id, source, conn in (
        ("power_primary", "PCDU1", "GYRO1-J01"),
        ("can", "OBC1", "GYRO1-J02"),
    ):
        ops, _ = edit.ops_add_interface(p, type_id, source, "GYRO1", to_connector=conn)
        History(p).execute("interface", ops)


def hand_written() -> Project:
    """The device as a person writes the files: connector objects with their pins, no planner."""
    p = base()
    pins1 = [Pin(id="A1", signal="PWR", fixed=True), Pin(id="A2", signal="RTN", fixed=True)]
    pins2 = [Pin(id="1", signal="CANH", fixed=True), Pin(id="2", signal="CANL", fixed=True)]
    for cid, name, pins, carries in (
        ("GYRO1-J01", "J01", pins1, ["power_primary"]),
        ("GYRO1-J02", "J02", pins2, ["can"]),
    ):
        spare = [Pin(id=str(i)) for i in range(3, 7)]
        p.connectors[cid] = Connector(
            id=cid, name=name, role="box", part_id="MY-HD-6-F", unit_id="GYRO1",
            gender="female", carries=carries, pins=[*pins, *spare],
        )  # fmt: skip
    _interfaces(p)
    return p


def with_editor() -> Project:
    """The same device from the plans, one undo step each."""
    p = base()
    h = History(p)
    for carries in (["power_primary"], ["can"]):
        ops, cid = devices.ops_add_connector(p, "GYRO1", part_id="MY-HD-6-F", carries=carries)
        h.execute("add connector", ops)
    steps: list[list[Op]] = [
        devices.ops_rename_pin(p, "GYRO1-J01", "1", "A1"),
    ]
    h.execute("rename", steps[0])
    h.execute("rename", devices.ops_rename_pin(p, "GYRO1-J01", "2", "A2"))
    h.execute("fill", devices.fill_from_type(p, "GYRO1-J01", ["A1", "A2"], "power_primary"))
    h.execute("fill", devices.fill_from_type(p, "GYRO1-J02", ["1", "2"], "can"))
    _interfaces(p)
    return p


def folder_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(f.relative_to(root)): f.read_bytes() for f in sorted(root.rglob("*")) if f.is_file()
    }


def write_fixture() -> None:
    p = hand_written()
    generate_project(p)
    import shutil

    shutil.rmtree(FIXTURE, ignore_errors=True)
    save_project(p, FIXTURE)


def test_editor_and_hand_written_device_are_the_same_project() -> None:
    a, b = hand_written(), with_editor()
    assert model_hash(a) == model_hash(b)
    assert a.connectors == b.connectors


def test_saved_files_are_identical_byte_for_byte(tmp_path: Path) -> None:
    a, b = hand_written(), with_editor()
    save_project(a, tmp_path / "hand")
    save_project(b, tmp_path / "editor")
    assert folder_bytes(tmp_path / "hand") == folder_bytes(tmp_path / "editor")


def test_the_editor_device_generates_to_the_committed_fixture(tmp_path: Path) -> None:
    p = with_editor()
    plan = generate_project(p)
    assert not plan.report.errors
    save_project(p, tmp_path / "out")
    assert folder_bytes(tmp_path / "out") == folder_bytes(FIXTURE)
    gyro = p.connectors["GYRO1-J01"]
    assert [(x.id, x.signal, x.interface_id) for x in gyro.pins[:2]] == [
        ("A1", "PWR", "IF-001"), ("A2", "RTN", "IF-001")
    ]  # fmt: skip


def test_the_fixture_loads_clean_and_a_second_generate_is_empty() -> None:
    p = load_project(FIXTURE).project
    assert errors(check_integrity(p)) == []
    before = model_hash(p)
    plan = plan_generation(p)
    assert plan.empty
    apply_ops(p, plan.ops)
    assert model_hash(p) == before


def test_verify_and_rules_find_nothing_the_hand_written_device_does_not() -> None:
    a, b = hand_written(), with_editor()
    generate_project(a)
    generate_project(b)
    assert verify_project(b).errors == verify_project(a).errors == []
    assert [(f.rule, f.object_id) for f in run(b)] == [(f.rule, f.object_id) for f in run(a)]
    assert len(RULES) == 43


def test_editor_made_connectors_are_a_single_put_each() -> None:
    p = base()
    ops, _ = devices.ops_add_connector(p, "GYRO1", part_id="MY-HD-6-F")
    assert len(ops) == 1 and isinstance(ops[0], Put)


# ---- a device with two ports on one connector (D-237) ----------------------------------------------

PORTS = ("RS422_1", "RS422_2")
RS422 = ("TX+", "TX-", "RX+", "RX-")


def _two_port_base() -> Project:
    p = base()
    p.units["IOB1"] = Unit(id="IOB1", name="I/O board", subsystem="avionics", side="nominal")
    p.placements["IOB1"] = Placement(id="IOB1", x=edit.lane_x(1), y=240)
    return p


def two_ports_hand_written() -> Project:
    """The connector written by hand: two RS-422 ports, the second locked to IF-002."""
    from harness_design_studio.core.model import Endpoint, InterfaceInstance

    p = _two_port_base()
    names = [f"{port}_{s}" for port in PORTS for s in RS422]
    pins = [
        Pin(id=str(k + 1), signal=name, fixed=True)
        if k < 4
        else Pin(id=str(k + 1), signal=name, fixed=True, locked=True, interface_id="IF-002")
        for k, name in enumerate(names)
    ]
    p.connectors["IOB1-J01"] = Connector(
        id="IOB1-J01", name="J01", role="box", part_id="EX-MICROD-9-F", unit_id="IOB1",
        gender="female", carries=["rs422"], pins=[*pins, Pin(id="9")],
    )  # fmt: skip
    for iid, far in (("IF-001", "OBC1-J01"), ("IF-002", "OBC1-J03")):
        p.interfaces[iid] = InterfaceInstance(
            id=iid, name="RS-422 OBC1 to IOB1", type_id="rs422", redundancy="nominal",
            endpoints=[Endpoint(unit_id="OBC1", connector_id=far),
                       Endpoint(unit_id="IOB1", connector_id="IOB1-J01")],
        )  # fmt: skip
    return p


def two_ports_with_editor() -> Project:
    """The same device from the core API: a connector, its pinout pasted as fixed rows, two
    interfaces on it (the second because the connector has room), the second locked to its port."""
    p = _two_port_base()
    h = History(p)
    ops, cid = devices.ops_add_connector(p, "IOB1", part_id="EX-MICROD-9-F", carries=["rs422"])
    h.execute("add connector", ops)
    rows = [
        {"pin": str(k + 1), "signal": f"{port}_{s}", "mode": "fixed"}
        for k, (port, s) in enumerate((port, s) for port in PORTS for s in RS422)
    ]
    h.execute("pinout", devices.ops_paste_rows(p, cid, rows))
    for far in ("OBC1-J01", "OBC1-J03"):
        ops, _iid = edit.ops_add_interface(p, "rs422", "OBC1", "IOB1", far, cid)
        h.execute("interface", ops)
    h.execute("port", devices.ops_assign_port(p, cid, "RS422_2", "IF-002"))
    return p


def test_a_two_port_device_from_the_core_api_is_the_hand_written_one(tmp_path: Path) -> None:
    a, b = two_ports_hand_written(), two_ports_with_editor()
    assert a.connectors == b.connectors and a.interfaces == b.interfaces
    save_project(a, tmp_path / "hand")
    save_project(b, tmp_path / "editor")
    assert folder_bytes(tmp_path / "hand") == folder_bytes(tmp_path / "editor")
    generate_project(a)
    generate_project(b)
    owners = [(x.id, x.interface_id) for x in b.connectors["IOB1-J01"].pins[:8]]
    assert owners == [(str(k), "IF-001" if k < 5 else "IF-002") for k in range(1, 9)]
    save_project(a, tmp_path / "hand2")
    save_project(b, tmp_path / "editor2")
    assert folder_bytes(tmp_path / "hand2") == folder_bytes(tmp_path / "editor2")
    assert verify_project(b).errors == []
