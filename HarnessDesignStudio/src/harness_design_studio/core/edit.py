# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Editing operations for the block diagram. Pure functions: they build lists of `Op`s.

Nothing here mutates a project. The GUI runs the returned ops through `History.execute`, so every
edit is a transaction that is rolled back if it would leave the project inconsistent.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from pydantic import TypeAdapter, ValidationError

from . import connector_choice
from .clone import clone_with as clone_with  # moved to clone.py; kept here for its callers
from .commands import Delete, Op, Put, SetConfig, SetZones
from .describe import part_gender
from .device_kinds import KIND_IDS
from .errors import HarnessError
from .generate.pins import Allocation, PinRules, Request
from .ids import check_id
from .model import (
    Connector,
    Endpoint,
    InterfaceInstance,
    InterfaceType,
    Link,
    Pin,
    Placement,
    Project,
    Unit,
    evolve,
)
from .model.base import Name
from .model.config import ConfigFile
from .model.physical import TBD_PART_ID
from .ports import ports_of

LANE_WIDTH = 470.0
LANE_X0 = 10.0
UNIT_W = 240.0
UNIT_FOOTPRINT_H = 150.0  # smallest room a unit gets, whatever its size
SLOT_STEP = 70.0
PORT_ROW = 28.0  # height of one connector row of a unit drawn in expert mode
UNIT_GAP = 24.0  # empty space kept between two stacked units
MAX_DIAGRAM_HEIGHT = 200_000.0  # no unit is placed lower than this


def expert_height(connector_count: int) -> float:
    """Height of a unit in expert mode: a header and one row per connector."""
    return 46 + PORT_ROW * connector_count


def guided_height(link_count: int) -> float:
    """Height of a unit in guided mode: it grows with the number of links that end on it."""
    return 70 + 14 * max(0, link_count - 2)


def unit_footprints(project: Project) -> dict[str, float]:
    """The room every unit needs: its taller height of the two modes, so that switching the mode
    never makes units overlap. One pass over the project, whatever its size."""
    connectors: dict[str, int] = {}
    for c in project.connectors.values():
        if c.role == "box" and c.unit_id is not None:
            connectors[c.unit_id] = connectors.get(c.unit_id, 0) + 1
    links: dict[str, int] = {}
    for i in project.interfaces.values():
        for uid in {e.unit_id for e in i.endpoints}:
            links[uid] = links.get(uid, 0) + 1
    floor = UNIT_FOOTPRINT_H - UNIT_GAP
    return {
        uid: max(floor, expert_height(connectors.get(uid, 0)), guided_height(links.get(uid, 0)))
        for uid in project.units
    }


def unit_footprint(project: Project, unit_id: str) -> float:
    return unit_footprints(project).get(unit_id, UNIT_FOOTPRINT_H - UNIT_GAP)


class EditError(HarnessError):
    """An edit that cannot be done; the message says why in plain language."""


def _check_new_id(new_id: str) -> None:
    """An EditError (not a raw validation error) for an ID the model would refuse."""
    try:
        check_id(new_id)
    except ValueError as exc:
        raise EditError(f"'{new_id}' cannot be used as an ID: it {exc}.") from exc


def _known[V](table: Mapping[str, V], key: str, what: str) -> V:
    """The object called `key`, or an EditError that says which one is missing."""
    got = table.get(key)
    if got is None:
        raise EditError(f"{what} '{key}' does not exist.")
    return got


# ---- templates ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class ConnectorTemplate:
    part_id: str
    carries: tuple[str, ...]


@dataclass(frozen=True)
class UnitTemplate:
    id: str
    label: str
    prefix: str
    subsystem: str
    connectors: tuple[ConnectorTemplate, ...]


_POWER = {"power_primary", "power_secondary", "heater"}
_MICROD_BY_TYPES = {1: 9, 2: 15, 3: 21, 4: 25}  # distinct interface types on one connector -> pins


def _box_part(carries: tuple[str, ...]) -> str:
    """The baseline connector (D-130) for a unit connector that carries these interface types:
    SMA for RF, an RJ45 for Ethernet, otherwise the Micro-D size that fits the number of types."""
    if carries == ("rf_coax",):
        return "EX-SMA-F"
    if carries == ("ethernet",):
        return "EX-RJ45-F"
    if set(carries) <= _POWER:
        return "EX-MICROD-9-F"
    return f"EX-MICROD-{_MICROD_BY_TYPES.get(len(carries), 31)}-F"


def _t(id_: str, label: str, prefix: str, sub: str, *conns: tuple[str, ...]) -> UnitTemplate:
    return UnitTemplate(
        id_, label, prefix, sub, tuple(ConnectorTemplate(_box_part(c), c) for c in conns)
    )


_COMMS = ("rs422", "rs485", "can")  # the baseline communication standards (D-130)

TEMPLATES: dict[str, UnitTemplate] = {
    t.id: t
    for t in (
        _t("computer", "Computer", "OBC", "avionics", (*_COMMS, "discrete"), ("power_primary",), ("rs422", "can"), ("ethernet",)),
        _t("power", "Power unit", "PCDU", "power", ("power_primary",), ("power_primary",), ("discrete", "rs422")),
        _t("actuator", "Actuator (wheel)", "RW", "aocs", ("power_primary",), _COMMS),
        _t("sensor", "Sensor (star tracker)", "ST", "aocs", ("power_primary",), ("rs422", "rs485")),
        _t("payload", "Payload", "PL", "payload", ("power_primary",), ("ethernet",), _COMMS, ("rf_coax",)),
        _t("transceiver", "Transceiver", "TRX", "comms", ("power_primary",), ("rs422", "can"), ("rf_coax",)),
        _t("pyro", "Pyro unit", "PYRO", "mechanisms", ("power_primary",), ("pyro",), ("discrete",)),
        _t("computer_xl", "Computer (many interfaces)", "OBC", "avionics", ("power_primary",), *[(*_COMMS, "discrete", "analog", "thermistor")] * 11, ("ethernet",), ("ethernet",)),
        _t("pdu", "Power distribution unit", "PCDU", "power", *[("power_primary",)] * 10, ("heater",), ("can", "rs422")),
        _t("battery", "Battery", "BAT", "power", ("power_primary",), ("can", "rs422")),
        _t("solar_array", "Solar array", "SA", "power", ("power_primary",), ("thermistor",)),
        _t("sun_sensor", "Sun sensor", "SS", "aocs", ("power_primary",), ("analog",)),
        _t("magnetorquer", "Magnetorquer", "MTQ", "aocs", ("power_primary",), ("discrete",)),
        _t("heater_panel", "Heater panel", "HTR", "thermal", ("heater",), ("thermistor",)),
    )
}  # fmt: skip


# ---- ids and placement -------------------------------------------------------------------------


def _taken(ids: set[str]) -> set[str]:
    return {i.casefold() for i in ids}


def _connector_owners(project: Project) -> set[str]:
    """Casefolded `<unit>` parts of connector IDs `<unit>-Jnn`: a renamed unit keeps its old connector IDs,
    so the old unit ID is not free for a new unit (its connectors would be overwritten)."""
    return {c.id.rsplit("-", 1)[0].casefold() for c in project.connectors.values() if "-" in c.id}


def next_unit_id(project: Project, prefix: str) -> tuple[str, int]:
    taken = _taken(set(project.units)) | _connector_owners(project)
    n = 1
    while f"{prefix}{n}".casefold() in taken:
        n += 1
    return f"{prefix}{n}", n


def next_interface_id(project: Project, extra: set[str] | None = None) -> str:
    taken = _taken(set(project.interfaces) | (extra or set()))
    n = 1
    while f"IF-{n:03d}".casefold() in taken:
        n += 1
    return f"IF-{n:03d}"


def effective_zones(project: Project) -> list[str]:
    zones = list(project.zones)
    extra = sorted({u.zone for u in project.units.values() if u.zone and u.zone not in zones})
    return zones + extra


def lane_index(lane_count: int, x: float) -> int:
    """Lane (0-based) of a unit whose left edge is at `x`."""
    centre = x + UNIT_W / 2
    return max(0, min(lane_count - 1, int((centre - LANE_X0) // LANE_WIDTH)))


def lane_index_of_x(project: Project, x: float) -> int:
    return lane_index(len(effective_zones(project)), x)


def zone_of_x(project: Project, x: float) -> str:
    """The zone (lane) at `x`; '' while the project has no zones (one implicit lane)."""
    zones = effective_zones(project)
    return zones[lane_index_of_x(project, x)] if zones else ""


def lane_x(index: int) -> float:
    return LANE_X0 + index * LANE_WIDTH + 20


def position_of(project: Project, unit_id: str) -> tuple[float, float]:
    p = project.placements.get(unit_id)
    if p is not None:
        return p.x, p.y
    return free_slot(project, _known(project.units, unit_id, "Device").zone)


def ops_autoplace(project: Project) -> list[Op]:
    """Positions for units that have none (e.g. projects saved before layouts existed).

    Deterministic: units are placed in (zone, ID) order, each in the first free slot of its lane,
    and each placement is visible to the next so units never stack.
    """
    missing = sorted(
        (u for u in project.units.values() if u.id not in project.placements),
        key=lambda u: (u.zone or "", u.id),
    )
    if not missing:
        return []
    from copy import copy

    scratch = copy(project)
    scratch.placements = dict(project.placements)
    ops: list[Op] = []
    for u in missing:
        x, y = free_slot(scratch, u.zone)
        place = Placement(id=u.id, x=x, y=y)
        scratch.placements[u.id] = place
        ops.append(Put("placements", place))
    return ops


MAX_SWEEPS = 30  # ordering sweeps of ops_arrange; it stops earlier once nothing moves


def ops_arrange(project: Project) -> list[Op]:
    """Tidy the diagram: units stay in their lanes (zones); inside each lane they are ordered
    to shorten and uncross links (barycenter ordering from the neighbouring lanes, a few sweeps),
    then stacked top to bottom without overlap. Deterministic; one undo step."""
    zones = effective_zones(project)
    lanes: dict[int, list[str]] = {k: [] for k in range(max(1, len(zones)))}  # no zones: one lane
    for uid in sorted(project.units):
        zone = project.units[uid].zone
        lane = (
            zones.index(zone)
            if zone in zones
            else lane_index_of_x(project, position_of(project, uid)[0])
        )
        lanes[lane].append(uid)
    lane_of = {u: k for k, units in lanes.items() for u in units}
    neighbours: dict[str, set[str]] = {u: set() for u in project.units}
    for i in project.interfaces.values():
        ends = [e.unit_id for e in i.endpoints if e.unit_id in project.units]
        for a in ends:
            neighbours[a].update(b for b in ends if b != a)
    order = {u: float(pos) for units in lanes.values() for pos, u in enumerate(units)}
    # start from the current vertical order so a tidy diagram stays put
    for units in lanes.values():
        units.sort(key=lambda u: (position_of(project, u)[1], u))
        order.update({u: float(pos) for pos, u in enumerate(units)})

    def centre(u: str) -> float:
        others = [order[n] for n in neighbours[u] if lane_of[n] != lane_of[u]]
        return sum(others) / len(others) if others else order[u]

    for _sweep in range(MAX_SWEEPS):
        before = {k: list(units) for k, units in lanes.items()}
        for k in sorted(lanes):
            lanes[k].sort(key=lambda u: (centre(u), u))
            order.update({u: float(pos) for pos, u in enumerate(lanes[k])})
        if lanes == before:  # settled: arranging again changes nothing
            break
    room = unit_footprints(project)
    ops: list[Op] = []
    for k, units in sorted(lanes.items()):
        y = 40.0
        for uid in units:
            x = lane_x(k)
            now = project.placements.get(uid)
            if now is None or (now.x, now.y) != (x, y):
                ops.append(Put("placements", Placement(id=uid, x=x, y=y)))
            y += room[uid] + UNIT_GAP
    return ops


def free_slot(
    project: Project, zone: str | None = None, height: float | None = None
) -> tuple[float, float]:
    """First position in the preferred lane (then the others) that overlaps no placed unit.
    `height` is the room the new unit needs (default: the smallest footprint)."""
    zones = effective_zones(project)
    need = height if height is not None else UNIT_FOOTPRINT_H - UNIT_GAP
    room = unit_footprints(project)
    placed = [
        (p.x, p.y, room[uid]) for uid, p in project.placements.items() if uid in project.units
    ]
    if zone in zones:
        order = [zones.index(zone)]  # the caller asked for this lane: stay in it
    else:  # no preference: fill the emptiest lane first so the diagram stays balanced
        counts = [
            sum(1 for px, _, _ in placed if lane_index_of_x(project, px) == i)
            for i in range(max(1, len(zones)))
        ]
        order = sorted(range(max(1, len(zones))), key=lambda i: (counts[i], i))
    for lane in order:
        x = lane_x(lane)
        y = 40.0
        while y < MAX_DIAGRAM_HEIGHT:
            if not any(
                abs(px - x) < UNIT_W + 10 and y < py + ph + UNIT_GAP and py < y + need + UNIT_GAP
                for px, py, ph in placed
            ):
                return x, y
            y += SLOT_STEP
    raise EditError("There is no room left in the diagram for another device.")


# ---- compatibility (prevent errors instead of reporting them) -----------------------------------


@dataclass(frozen=True)
class Compat:
    ok: bool
    short: str = ""
    why: str = ""
    # what the person should know although the connector can take the interface (not a refusal):
    # a second harness plug on the connector, or a released harness that plugs into it (D-237)
    note: str = ""


_USED: tuple[tuple[InterfaceInstance, ...], dict[str, tuple[InterfaceInstance, ...]]] | None = None


def _same(a: tuple[object, ...], b: tuple[object, ...]) -> bool:
    """The same objects in the same order (entities are immutable, so this means nothing changed)."""
    return len(a) == len(b) and all(x is y for x, y in zip(a, b, strict=True))


def _used_connectors(project: Project) -> dict[str, tuple[InterfaceInstance, ...]]:
    """Connector ID -> the interfaces that end on it, in the order of the project. Built once and
    reused while the interfaces are the same objects (they are immutable), so asking about every
    connector of a large project does not scan all interfaces each time."""
    global _USED
    current = tuple(project.interfaces.values())
    hit = _USED
    if hit is not None and _same(hit[0], current):
        return hit[1]
    found: dict[str, list[InterfaceInstance]] = {}
    for i in current:
        for e in i.endpoints:
            if e.connector_id is not None:
                on = found.setdefault(e.connector_id, [])
                if not on or on[-1] is not i:
                    on.append(i)
    index = {cid: tuple(on) for cid, on in found.items()}
    _USED = (current, index)
    return index


def interface_using(project: Project, connector_id: str) -> InterfaceInstance | None:
    """The first interface that ends on the connector, or None. A connector can carry several
    (D-237): `interfaces_using` gives them all."""
    on = _used_connectors(project).get(connector_id)
    return on[0] if on else None


def interfaces_using(project: Project, connector_id: str) -> tuple[InterfaceInstance, ...]:
    """Every interface that ends on the connector, in ID order."""
    return tuple(sorted(_used_connectors(project).get(connector_id, ()), key=lambda i: i.id))


def unit_connectors(project: Project, unit_id: str) -> list[Connector]:
    return sorted(
        (c for c in project.connectors.values() if c.unit_id == unit_id and c.role == "box"),
        key=lambda c: c.id,
    )


def carries(connector: Connector, type_id: str) -> bool:
    return not connector.carries or type_id in connector.carries


def fixed_pinout(connector: Connector) -> bool:
    """The device design names the pins (a pin with `fixed` and a signal): Generate places the
    signals by name, and a connector can hold several interfaces by ports (D-237)."""
    return any(p.fixed and p.signal for p in connector.pins)


def free_connectors(project: Project, unit_id: str, type_id: str) -> list[Connector]:
    """The connectors of the device that carry the type and that no interface ends on (tier 1 of
    the choice of a connector)."""
    used = _used_connectors(project)
    return [
        c for c in unit_connectors(project, unit_id) if carries(c, type_id) and c.id not in used
    ]


# ---- room on a connector: a dry run of Generate's own pin allocation (D-237) ---------------------


@dataclass(frozen=True)
class Room:
    """Whether one more interface of a type fits on a connector, by a dry run of the pin allocation
    of Generate with every interface that ends on the connector and the new one."""

    ok: bool
    why: str = ""  # the refusal in plain words; "" when it fits
    pins: tuple[tuple[str, str], ...] = ()  # (signal, pin) the new interface would get
    port: str = ""  # the named port these pins form; "" for none (bare names or a free pinout)


@dataclass
class _RoomCache:
    """The dry runs made while the project is the same objects (like `_USED`). A run and an answer
    also keep the connector object they were made for, and count only while it is the same."""

    token: tuple[tuple[object, ...], ...]
    frozen: set[str] | None = None
    rules: PinRules | None = None
    next_id: str | None = None
    runs: dict[tuple[str, str, str, str], tuple[Connector, Allocation]] = field(
        default_factory=dict
    )
    answers: dict[tuple[str | None, ...], tuple[Connector, Compat]] = field(default_factory=dict)


_ROOM: _RoomCache | None = None


def _same_values(kept: tuple[object, ...], table: Mapping[str, object]) -> bool:
    """`table` holds the objects of `kept`, in the same order (no tuple is built to compare)."""
    return len(kept) == len(table) and all(
        x is y for x, y in zip(kept, table.values(), strict=True)
    )


def _room_cache(project: Project) -> _RoomCache:
    """The cache of dry runs, kept while every entity that the allocation and the notes read is the
    same object: the interfaces, the harnesses, the interface types, the devices, the settings and
    the generation record (the connector itself is checked per run). Asking about every connector
    while the pointer moves costs one allocation per connector, once."""
    global _ROOM
    tables: tuple[Mapping[str, object], ...] = (
        project.interfaces,
        project.harnesses,
        project.interface_types,
        project.units,
        project.config,
    )
    hit = _ROOM
    if (
        hit is not None
        and all(_same_values(k, t) for k, t in zip(hit.token, tables, strict=False))
        and hit.token[-1][0] is project.generation
    ):
        return hit
    _ROOM = _RoomCache((*(tuple(t.values()) for t in tables), (project.generation,)))
    return _ROOM


def _dry_run(
    cache: _RoomCache,
    project: Project,
    connector_id: str,
    new_id: str,
    type_id: str,
    leave_out: str,
) -> Allocation:
    """The allocation Generate would make on the connector for the interfaces that end on it (not
    `leave_out`), plus an interface `new_id` of `type_id` when one is given."""
    from .generate import engine

    box = project.connectors[connector_id]
    key = (connector_id, new_id, type_id, leave_out)
    hit = cache.runs.get(key)
    if hit is not None and hit[0] is box:
        return hit[1]
    if cache.frozen is None:
        cache.frozen = engine.frozen_interfaces(project)
    if cache.rules is None:
        cache.rules = engine.pin_rules(project)
    requests = [
        Request(i.id, project.interface_types[i.type_id])
        for i in interfaces_using(project, connector_id)
        if i.id != leave_out and i.id not in cache.frozen and i.type_id in project.interface_types
    ]
    if new_id:
        requests.append(Request(new_id, project.interface_types[type_id]))
    result = engine.allocate_box(project, box, requests, cache.frozen, cache.rules)
    cache.runs[key] = (box, result)
    return result


def _new_interface_id(project: Project, cache: _RoomCache) -> str:
    if cache.next_id is None:
        cache.next_id = next_interface_id(project)
    return cache.next_id


def taken_pins(project: Project, connector_id: str) -> frozenset[str]:
    """The pins of the connector that the interfaces ending on it hold in the dry run, and the
    pins that must stay (locked, or of a released or hand-made harness)."""
    c = project.connectors[connector_id]
    cache = _room_cache(project)
    run = _dry_run(cache, project, connector_id, "", "", "")
    frozen = cache.frozen or set()
    held = {p.id for p in c.pins if p.locked or (p.interface_id and p.interface_id in frozen)}
    return frozenset(run.pins.values()) | frozenset(held)


def free_ports(project: Project, connector_id: str, type_id: str) -> tuple[str, ...]:
    """The complete named ports of the type on the connector that no interface holds in the dry
    run and no lock keeps, in natural order of their names."""
    c = project.connectors.get(connector_id)
    itype = project.interface_types.get(type_id)
    if c is None or itype is None or not fixed_pinout(c):
        return ()
    taken = taken_pins(project, connector_id)
    return tuple(
        p.name for p in ports_of(c, itype).usable if not any(pp.pin_id in taken for pp in p.pins)
    )


def connector_room(
    project: Project, connector_id: str, type_id: str, interface_id: str | None = None
) -> Room:
    """Can the connector take one more interface of `type_id`? A dry run of `generate.pins.allocate`
    (through `engine.allocate_box`, the very function Generate calls) with every interface that
    ends on the connector and the new one: refused when the new interface gets no pins, or when it
    would take the pins of an interface that has them now. `interface_id` is the interface being
    placed (left out of the others); a new one gets the next free interface ID, so it is placed in
    the order Generate would place it."""
    c = project.connectors[connector_id]
    itype = project.interface_types[type_id]
    cache = _room_cache(project)
    new_id = interface_id or _new_interface_id(project, cache)
    leave_out = interface_id or ""
    base = _dry_run(cache, project, connector_id, "", "", leave_out)
    after = _dry_run(cache, project, connector_id, new_id, type_id, leave_out)
    others = [i for i in interfaces_using(project, connector_id) if i.id != leave_out]
    head = (
        f"{c.id} cannot take another {itype.name}"
        if any(i.type_id == type_id for i in others)
        else f"{c.id} cannot take {itype.name} as well"
    )
    failed = [msg for iid, msg in after.errors if iid == new_id]
    if failed:
        return Room(False, f"{head}: {_full_text(c, itype, base, failed[0])}")
    before = {iid for iid, _msg in base.errors}
    pushed = sorted({iid for iid, _msg in after.errors if iid != new_id and iid not in before})
    if pushed:
        return Room(
            False,
            f"{head}: {', '.join(pushed)} would lose {'its' if len(pushed) == 1 else 'their'}"
            " pins to it",
        )
    got = tuple(sorted((sig, pid) for (iid, sig), pid in after.pins.items() if iid == new_id))
    port = ""
    if fixed_pinout(c):
        mine = {pid for _sig, pid in got}
        port = next(
            (p.name for p in ports_of(c, itype).usable if {pp.pin_id for pp in p.pins} == mine),
            "",
        )
    return Room(True, "", got, port)


def _full_text(c: Connector, itype: InterfaceType, base: Allocation, msg: str) -> str:
    """Why a connector is full, in plain words: the ports of the type and who uses them, else the
    words of the pin allocation."""
    if fixed_pinout(c):
        usable = ports_of(c, itype).usable
        owner = {pid: iid for (iid, _sig), pid in base.pins.items()}
        owner.update({p.id: p.interface_id for p in c.pins if p.locked and p.interface_id})
        users = [{owner[pp.pin_id] for pp in p.pins if pp.pin_id in owner} for p in usable]
        if usable and all(users):
            names = ", ".join(p.name for p in usable)
            ids = ", ".join(sorted(set().union(*users)))
            word = "port" if len(usable) == 1 else "ports"
            verb = "is" if len(usable) == 1 else "are"
            return f"its {itype.name} {word} {names} {verb} used by {ids}"
    own = f"{c.id} has "
    if msg.startswith(own + "too few"):
        return msg[len(own) :]
    if msg.startswith(own):
        return "it has " + msg[len(own) :]
    return msg


def _far_key(project: Project, unit_id: str | None, connector_id: str | None) -> str | None:
    """What decides, in the segmentation in force, whether two interfaces from one connector share
    a harness: the far connector, the far device or the zone of the far device. None: not known.
    In `per_connector_group` it is the far connector, as in `per_connector_pair`: the interfaces to
    other far connectors are joined into the harness as a branch (`_shared_note`)."""
    from .generate.segmentation import GROUP_MODE, mode_of

    mode = mode_of(project)
    if mode in ("per_connector_pair", GROUP_MODE):
        if connector_id is not None:
            return f"connector {connector_id}"
        mode = "per_unit_pair"
    if unit_id is None:
        return None
    if mode == "per_unit_pair":
        return f"device {unit_id}"
    unit = project.units.get(unit_id)
    return f"zone {unit.zone or ''}" if unit is not None else None


def _shared_note(
    project: Project,
    c: Connector,
    others: Collection[InterfaceInstance],
    far_unit: str | None,
    far_connector: str | None,
) -> str:
    """The notes of a connector that already carries interfaces: a second harness plug when the
    others go elsewhere, and a released harness that plugs into it."""
    from .generate.segmentation import GROUP_MODE, mode_of

    notes: list[str] = []
    mine = _far_key(project, far_unit, far_connector)
    elsewhere: list[str] = []
    if mine is not None:
        for i in others:
            far = [e for e in i.endpoints if e.connector_id != c.id]
            # compared at what is known of the new end: the far connector, else the far device
            keys = {
                _far_key(project, e.unit_id, e.connector_id if far_connector else None) for e in far
            }
            if far and mine not in keys:
                elsewhere.append(i.id)
    if elsewhere and mode_of(project) == GROUP_MODE:
        notes.append(
            f"{c.id} also carries {', '.join(elsewhere)} to another connector: Generate joins it"
            f" into the harness on {c.id} as a branch."
        )
    elif elsewhere:
        notes.append(
            f"{c.id} also carries {', '.join(elsewhere)} to another connector: Generate makes a"
            f" second harness with its own plug on {c.id} and warns about it; with"
            " segmentation.mode per_connector_group it makes one harness that branches."
        )
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        if h.status != "released" or not any(k.mates_with == c.id for k in h.connectors):
            continue
        ends = {k.mates_with for k in h.connectors if k.mates_with and k.mates_with != c.id}
        units = {project.connectors[x].unit_id for x in ends if x in project.connectors}
        if far_connector is not None and far_connector not in ends:
            continue
        if far_connector is None and far_unit is not None and units and far_unit not in units:
            continue
        notes.append(
            f"{h.id} is released and plugs into {c.id}: the new interface is wired only after a"
            f" new version of {h.id}."
        )
    return " ".join(notes)


def shared_connectors(project: Project, unit_id: str, type_id: str) -> list[Connector]:
    """Tier 2 of the choice of a connector: the connectors of the device that carry the type, that
    interfaces already end on, that have a fixed pinout, and on which the dry run places the new
    interface on a free complete named port. A connector whose pins the device leaves free is
    never shared by the tool's choice: only a person shares it (Expert mode)."""
    if type_id not in project.interface_types:
        return []
    fixed = [
        c for c in unit_connectors(project, unit_id) if carries(c, type_id) and fixed_pinout(c)
    ]
    if not fixed:  # the common case: nothing to share, and the interfaces are not read at all
        return []
    used = _used_connectors(project)
    return [c for c in fixed if c.id in used and connector_room(project, c.id, type_id).port]


def _guided_fits(project: Project, type_id: str, connector_id: str) -> bool:
    """The tool may choose this connector itself: it is free and carries the type (tier 1), or it
    is one of the shared connectors of tier 2."""
    c = project.connectors.get(connector_id)
    if c is None or c.role != "box" or c.unit_id is None or not carries(c, type_id):
        return False
    if connector_id not in _used_connectors(project):
        return True
    return c in shared_connectors(project, c.unit_id, type_id)


def choose_connector(
    project: Project, unit_id: str, type_id: str, avoid: Collection[str] = ()
) -> Connector | None:
    """The connector the tool chooses for an interface of this type at a device, in two tiers
    (D-237). Tier 1: the free connectors that carry the type, in the order of the model
    `model.connector_choice` (`connector_choice.ranked`), as it always was. Tier 2, only when tier
    1 finds none: the connectors with a fixed pinout that have a free complete port of the type
    (`shared_connectors`), in the same order, counting the pins the other interfaces hold. The
    connectors in `avoid` are left out of both. None when there is none."""
    itype = project.interface_types.get(type_id)
    method = connector_choice.method(project)
    free = [c for c in free_connectors(project, unit_id, type_id) if c.id not in avoid]
    if free:
        return connector_choice.ranked(method, free, itype)[0]
    shared = [c for c in shared_connectors(project, unit_id, type_id) if c.id not in avoid]
    taken = {c.id: taken_pins(project, c.id) for c in shared}
    ranked = connector_choice.ranked(method, shared, itype, taken)
    return ranked[0] if ranked else None


def _type_name(project: Project, type_id: str) -> str:
    t = project.interface_types.get(type_id)
    return t.name if t else type_id


def unit_compat(
    project: Project, type_id: str, unit_id: str, source_unit: str | None = None
) -> Compat:
    """Can `unit_id` take an interface of this type (Guided mode: connector chosen automatically)?
    Yes when a connector of either tier of `choose_connector` is there."""
    if type_id not in project.interface_types:
        return Compat(
            False, "Unknown interface type", f"Interface type '{type_id}' does not exist."
        )
    if unit_id not in project.units:
        return Compat(False, "Unknown device", f"Device '{unit_id}' does not exist.")
    if source_unit == unit_id:
        return Compat(False, "Same device", "A device cannot be connected to itself.")
    if not free_connectors(project, unit_id, type_id) and not shared_connectors(
        project, unit_id, type_id
    ):
        name = _type_name(project, type_id)
        return Compat(
            False,
            f"No free {name} connector",
            f'{unit_id} has no free {name} connector. Use a device template that has one (for example "Computer (many interfaces)").',
        )
    return Compat(True)


def connector_compat(
    project: Project,
    type_id: str,
    connector_id: str,
    source_unit: str | None = None,
    *,
    interface_id: str | None = None,
    far_unit: str | None = None,
    far_connector: str | None = None,
) -> Compat:
    """Can this exact connector take an interface of this type (Expert mode)? A connector that
    interfaces already end on takes one more when it has room (`connector_room`, D-237); the
    answer then carries a note when the others go to another far connector or a released harness
    plugs into it. `interface_id` is the interface being moved onto the connector, if any; the far
    end is `far_unit` (else `source_unit`) and `far_connector` when they are known."""
    c = project.connectors.get(connector_id)
    if c is None or c.role != "box" or c.unit_id is None:
        return Compat(
            False, "Not a device connector", f"'{connector_id}' is not a connector of a device."
        )
    if source_unit == c.unit_id:
        return Compat(False, "Same device", "A device cannot be connected to itself.")
    if not carries(c, type_id):
        names = ", ".join(_type_name(project, t) for t in c.carries)
        return Compat(
            False,
            "Wrong type",
            f"{c.id} does not carry {_type_name(project, type_id)} (it carries {names}).",
        )
    others = [i for i in interfaces_using(project, connector_id) if i.id != interface_id]
    if not others:
        return Compat(True)
    if type_id not in project.interface_types:
        return Compat(
            False, "Unknown interface type", f"Interface type '{type_id}' does not exist."
        )
    cache = _room_cache(project)
    key = (connector_id, type_id, interface_id, far_unit or source_unit, far_connector)
    hit = cache.answers.get(key)
    if hit is not None and hit[0] is c:
        return hit[1]
    room = connector_room(project, connector_id, type_id, interface_id)
    if not room.ok:
        answer = Compat(False, "Full", room.why + ".")
    else:
        note = _shared_note(project, c, others, far_unit or source_unit, far_connector)
        answer = Compat(True, note=note)
    cache.answers[key] = (c, answer)
    return answer


# ---- unit operations ---------------------------------------------------------------------------


def ops_add_unit(
    project: Project,
    template_id: str,
    x: float | None = None,
    y: float | None = None,
    *,
    unit_id: str | None = None,
    name: str | None = None,
) -> tuple[list[Op], str]:
    """Ops that add a unit made from a template. The ID comes from the template's prefix unless
    `unit_id` is given (it must be free); `name` replaces the generated name."""
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        raise EditError(f"Unknown device template '{template_id}'.")
    missing = sorted({c.part_id for c in tpl.connectors} - set(project.parts))
    if missing:
        raise EditError(
            f"The parts library lacks {', '.join(missing)}; add the starter parts first."
        )
    if unit_id is None:
        uid, n = next_unit_id(project, tpl.prefix)
        unit_name = name or f"{tpl.label} {n}"
    else:
        uid = unit_id
        if uid.casefold() in _taken(set(project.units)) | _connector_owners(project):
            raise EditError(f"ID {uid} is already used.")
        _check_new_id(uid)
        unit_name = name or f"{tpl.label} {uid}"
    if x is None or y is None:
        x, y = free_slot(project, None, expert_height(len(tpl.connectors)))
    zone = zone_of_x(project, x) or None  # a project without zones has one implicit lane
    ops: list[Op] = [
        Put(
            "units",
            Unit(id=uid, name=unit_name, subsystem=tpl.subsystem, zone=zone, side="nominal"),
        ),
        Put("placements", Placement(id=uid, x=x, y=y)),
    ]
    for k, ct in enumerate(tpl.connectors, start=1):
        part = project.parts[ct.part_id]
        pins = [Pin(id=str(i)) for i in range(1, (part.pin_count or 0) + 1)]
        ops.append(
            Put(
                "connectors",
                Connector(
                    id=f"{uid}-J{k:02d}",
                    name=f"J{k:02d}",
                    role="box",
                    part_id=ct.part_id,
                    unit_id=uid,
                    gender=part_gender(part),  # a part that says male or female sets it
                    carries=list(ct.carries),
                    pins=pins,
                ),
            )
        )
    return ops, uid


@dataclass(frozen=True)
class DeleteImpact:
    interfaces: tuple[str, ...]
    connectors: tuple[str, ...]
    blocked_by_harnesses: tuple[str, ...]


def delete_impact(project: Project, unit_id: str) -> DeleteImpact:
    conns = {c.id for c in unit_connectors(project, unit_id)}
    ifs = sorted(
        i.id for i in project.interfaces.values() if any(e.unit_id == unit_id for e in i.endpoints)
    )
    blocked = []
    for h in project.harnesses.values():
        if h.generated and h.status != "released":  # generated plans just become outdated
            continue
        # a wire ends on a cable connector of the harness; the unit's connector is what it mates with
        box_of = {c.id: c.mates_with for c in h.connectors}

        def on_unit(
            cid: str, conns: set[str] = conns, box_of: dict[str, str | None] = box_of
        ) -> bool:
            return cid in conns or box_of.get(cid) in conns

        if any(
            on_unit(w.from_connector) or on_unit(w.to_connector) or w.interface_id in ifs
            for w in h.wires
        ):
            blocked.append(h.id)
    blocked.sort()
    return DeleteImpact(tuple(ifs), tuple(sorted(conns)), tuple(blocked))


def links_of_connectors(project: Project, connector_ids: set[str]) -> list[Link]:
    """The links (M2) that join one of these box connectors, by ID."""
    return [
        x
        for x in sorted(project.links.values(), key=lambda x: x.id)
        if x.a_connector in connector_ids or x.b_connector in connector_ids
    ]


def ops_delete_unit(project: Project, unit_id: str) -> list[Op]:
    if unit_id not in project.units:
        raise EditError(f"Device '{unit_id}' does not exist.")
    impact = delete_impact(project, unit_id)
    if impact.blocked_by_harnesses:
        raise EditError(
            f"{unit_id} cannot be deleted: {_blocked_text(project, impact.blocked_by_harnesses)}"
        )
    ops: list[Op] = [Delete("interfaces", i) for i in impact.interfaces]
    ops += [Delete("links", x.id) for x in links_of_connectors(project, set(impact.connectors))]
    ops += [Delete("connectors", c) for c in impact.connectors]
    gone = {unit_id, *impact.interfaces, *impact.connectors}
    ops += _waiver_deletes(project, gone)
    if unit_id in project.placements:
        ops.append(Delete("placements", unit_id))
    ops.append(Delete("units", unit_id))
    return ops


def ops_delete_interface(project: Project, interface_id: str) -> list[Op]:
    if interface_id not in project.interfaces:
        raise EditError(f"Interface '{interface_id}' does not exist.")
    users = sorted(
        h.id
        for h in project.harnesses.values()
        if (not h.generated or h.status == "released")
        and any(w.interface_id == interface_id for w in h.wires)
    )
    if users:
        raise EditError(f"{interface_id} cannot be deleted: {_blocked_text(project, users)}")
    return [Delete("interfaces", interface_id), *_waiver_deletes(project, {interface_id})]


def _blocked_text(project: Project, harness_ids: tuple[str, ...] | list[str]) -> str:
    """What to do about harnesses that stop a deletion (released ones and hand-made ones)."""
    released = [h for h in harness_ids if project.harnesses[h].status == "released"]
    by_hand = [h for h in harness_ids if h not in released]
    parts = []
    if released:
        parts.append(
            f"{', '.join(released)} is released. Start a new version of it first "
            "(Harness plans, New version) so it can be changed."
        )
    if by_hand:
        parts.append(
            f"{', '.join(by_hand)} was made by hand and has wires for it. "
            "Delete that harness first (Harness plans, Delete harness)."
        )
    return " ".join(parts)


def _waiver_deletes(project: Project, object_ids: set[str]) -> list[Op]:
    """Waivers about objects that no longer exist would only confuse the next reader."""
    return [
        Delete("waivers", w.id)
        for w in project.waivers.values()
        if w.object_id in object_ids or w.object_id.split(".")[0] in object_ids
    ]


def ops_delete_harness(project: Project, harness_id: str) -> list[Op]:
    """Delete a draft harness (a generated one comes back at the next generate)."""
    h = project.harnesses.get(harness_id)
    if h is None:
        raise EditError(f"Harness '{harness_id}' does not exist.")
    if h.status == "released":
        raise EditError(
            f"{harness_id} is released and cannot be deleted. Start a new version to change it."
        )
    # a link that made this harness no longer has one
    ops: list[Op] = [
        Put("links", evolve(x, harness_id=""))
        for x in sorted(project.links.values(), key=lambda x: x.id)
        if x.harness_id == harness_id
    ]
    return [*ops, Delete("harnesses", harness_id)]


def ops_move_unit(project: Project, unit_id: str, x: float, y: float) -> list[Op]:
    unit = _known(project.units, unit_id, "Device")
    ops: list[Op] = [Put("placements", Placement(id=unit_id, x=x, y=y))]
    zone = zone_of_x(project, x) or None
    if zone is not None and unit.zone != zone:
        ops.append(Put("units", evolve(unit, zone=zone)))
    return ops


def ops_add_zone(project: Project, name: str) -> list[Op]:
    name = name.strip()
    if not name:
        raise EditError("A zone needs a name.")
    try:
        TypeAdapter(Name).validate_python(name, strict=True)
    except ValidationError as exc:
        raise EditError(
            "A zone name can have 1 to 200 characters and no control characters."
        ) from exc
    if name.casefold() in {z.casefold() for z in effective_zones(project)}:
        raise EditError(f"A zone called '{name}' already exists.")
    return [SetZones((*project.zones, name))]


def ops_rename_unit(project: Project, old: str, new: str) -> list[Op]:
    if old not in project.units:
        raise EditError(f"Device '{old}' does not exist.")
    if new == old:
        return []
    if new.casefold() in _taken(set(project.units) - {old}):
        raise EditError(f"ID {new} is already used.")
    foreign = {
        c.id.rsplit("-", 1)[0].casefold()
        for c in project.connectors.values()
        if "-" in c.id and c.unit_id != old
    }
    if new.casefold() in foreign:
        raise EditError(f"ID {new} is already used as the start of other connector IDs.")
    _check_new_id(new)
    unit = evolve(project.units[old], id=new)
    ops: list[Op] = [Put("units", unit), Delete("units", old)]
    if old in project.placements:
        p = project.placements[old]
        ops += [Put("placements", evolve(p, id=new)), Delete("placements", old)]
    for c in unit_connectors(project, old):
        ops.append(Put("connectors", evolve(c, unit_id=new)))
    for i in project.interfaces.values():
        if any(e.unit_id == old for e in i.endpoints):
            eps = [evolve(e, unit_id=new) if e.unit_id == old else e for e in i.endpoints]
            ops.append(Put("interfaces", evolve(i, endpoints=eps)))
    return ops


# ---- interface operations ----------------------------------------------------------------------


def ops_add_interface(
    project: Project,
    type_id: str,
    from_unit: str,
    to_unit: str,
    from_connector: str | None = None,
    to_connector: str | None = None,
    *,
    interface_id: str | None = None,
    name: str | None = None,
    redundancy: str | None = None,
    avoid_connectors: set[str] | None = None,
) -> tuple[list[Op], str]:
    """Add an interface; connectors not given are chosen automatically (`choose_connector`, two
    tiers) and marked `auto`. A connector given may already carry interfaces when it has room
    (`connector_compat`)."""
    chosen: list[tuple[str, str, bool]] = []
    if interface_id is not None and interface_id in project.interfaces:
        raise EditError(f"ID {interface_id} is already used.")
    ends = ((from_unit, from_connector), (to_unit, to_connector))
    for k, (unit_id, conn_id) in enumerate(ends):
        far_unit, far_connector = ends[1 - k]
        if unit_id not in project.units:
            raise EditError(f"Device '{unit_id}' does not exist.")
        if conn_id is None:
            compat = unit_compat(
                project, type_id, unit_id, from_unit if unit_id == to_unit else None
            )
            if not compat.ok:
                raise EditError(compat.why)
            pick = choose_connector(project, unit_id, type_id, avoid_connectors or ())
            if pick is None:
                raise EditError(f"{unit_id} has no free {_type_name(project, type_id)} connector.")
            chosen.append((unit_id, pick.id, True))
        else:
            compat = connector_compat(
                project,
                type_id,
                conn_id,
                from_unit if unit_id == to_unit else None,
                interface_id=interface_id,
                far_unit=far_unit,
                far_connector=far_connector,
            )
            if not compat.ok:
                raise EditError(compat.why)
            if project.connectors[conn_id].unit_id != unit_id:
                raise EditError(f"{conn_id} is not a connector of {unit_id}.")
            chosen.append((unit_id, conn_id, False))
    iid = interface_id or next_interface_id(project)
    _check_new_id(iid)
    side = project.units[from_unit].side
    inst = InterfaceInstance(
        id=iid,
        name=name or f"{_type_name(project, type_id)} {from_unit} to {to_unit}",
        type_id=type_id,
        endpoints=[Endpoint(unit_id=u, connector_id=c, auto=a) for u, c, a in chosen],
        redundancy=redundancy if redundancy is not None else ("none" if side == "none" else side),  # type: ignore[arg-type]
    )
    return [Put("interfaces", inst)], iid


def ops_confirm_interface(project: Project, interface_id: str) -> list[Op]:
    i = project.interfaces.get(interface_id)
    if i is None:
        raise EditError(f"Interface '{interface_id}' does not exist.")
    return [Put("interfaces", evolve(i, endpoints=[evolve(e, auto=False) for e in i.endpoints]))]


def twin_id(unit_id: str, suffix: str = "R") -> str:
    """The ID of a copy: `-R` for the redundant twin (the second device of a pair), `-3`, `-4` ...
    for further copies (see `core.copies`)."""
    return f"{unit_id}-{suffix}"


@dataclass(frozen=True)
class RedundantCopy:
    ops: list[Op]
    twin_id: str
    skipped: tuple[str, ...]  # interfaces that could not be mirrored (no free connector)


def ops_redundant_copy(project: Project, unit_id: str, suffix: str = "R") -> RedundantCopy:
    """Copy a nominal unit as its redundant twin and mirror its interfaces (names end in -R).
    `suffix` is `R` for the twin; `core.copies` passes `3`, `4` ... for the further copies of a
    device that is made in a number (the copy then ends in that number, and so do its links)."""
    unit = project.units.get(unit_id)
    if unit is None:
        raise EditError(f"Device '{unit_id}' does not exist.")
    if unit.side == "redundant":
        raise EditError(f"{unit_id} is already on the redundant chain.")
    tid = twin_id(unit_id, suffix)
    if tid.casefold() in _taken(set(project.units)):
        raise EditError(f"{unit_id} already has a redundant copy ({tid}).")
    ops = _twin_unit_ops(project, unit, suffix)
    # Work on a scratch view so mirrored interfaces see the twin's connectors.
    scratch = clone_with(project, ops)
    skipped: list[str] = []
    for i in sorted(project.interfaces.values(), key=lambda x: x.id):
        if i.redundancy == "redundant" or not any(e.unit_id == unit_id for e in i.endpoints):
            continue
        other = next((e for e in i.endpoints if e.unit_id != unit_id), None)
        if other is None:
            continue
        other_twin = (
            twin_id(other.unit_id, suffix)
            if twin_id(other.unit_id, suffix) in scratch.units
            else other.unit_id
        )
        mine = next(e for e in i.endpoints if e.unit_id == unit_id)
        from_a = i.endpoints[0].unit_id == unit_id
        f_unit, t_unit = (tid, other_twin) if from_a else (other_twin, tid)
        f_conn = _twin_connector(mine, tid) if from_a else None
        t_conn = None if from_a else _twin_connector(mine, tid)
        iid = f"{i.id}-{suffix}"
        try:
            new_ops, _ = ops_add_interface(
                scratch,
                i.type_id,
                f_unit,
                t_unit,
                f_conn,
                t_conn,
                interface_id=iid,
                name=f"{i.name} (redundant)",
                redundancy="redundant",
            )
        except EditError:
            skipped.append(i.id)
            continue
        ops += new_ops
        scratch = clone_with(scratch, new_ops)
    return RedundantCopy(ops, tid, tuple(skipped))


def _twin_connector(endpoint: Endpoint, tid: str) -> str | None:
    if endpoint.connector_id is None:
        return None
    suffix = endpoint.connector_id.rsplit("-", 1)[-1]
    return f"{tid}-{suffix}"


def _twin_unit_ops(project: Project, unit: Unit, suffix: str = "R") -> list[Op]:
    tid = twin_id(unit.id, suffix)
    lane = lane_index_of_x(project, position_of(project, unit.id)[0])
    zones = effective_zones(project)
    target_zone = (
        zones[(lane + 1) % len(zones)] if len(zones) > 1 else (zones[0] if zones else None)
    )
    x, y = free_slot(project, target_zone, unit_footprint(project, unit.id))
    twin = evolve(
        unit,
        id=tid,
        name=f"{unit.name} (redundant)" if suffix == "R" else f"{unit.name} (copy {suffix})",
        side="redundant",
        zone=zone_of_x(project, x) or None,
    )
    ops: list[Op] = [Put("units", twin), Put("placements", Placement(id=tid, x=x, y=y))]
    for c in unit_connectors(project, unit.id):
        suffix = c.id.rsplit("-", 1)[-1]
        new_id = f"{tid}-{suffix}"
        if new_id.casefold() in {x.casefold() for x in project.connectors}:
            raise EditError(f"Cannot make the redundant copy: connector {new_id} already exists.")
        # the copy starts without the original's pin assignments: they belong to interfaces that
        # do not end on the twin. Pins the person locked or the unit fixes keep their signal.
        pins = [
            evolve(p, interface_id=None, signal=p.signal if p.locked or p.fixed else None)
            if p.interface_id is not None
            else p
            for p in c.pins
        ]
        ops.append(Put("connectors", evolve(c, id=new_id, unit_id=tid, pins=pins)))
    return ops


def ops_complete_chain(project: Project, interface_id: str) -> tuple[list[Op], str]:
    """Fix for a cross-strap: move the nominal end of the interface onto a redundant twin."""
    i = _known(project.interfaces, interface_id, "Interface")
    nominal = [
        e
        for e in i.endpoints
        if e.unit_id in project.units and project.units[e.unit_id].side == "nominal"
    ]
    if not nominal:
        raise EditError("This interface has no nominal end to replace.")
    end = nominal[0]
    tid = twin_id(end.unit_id)
    ops: list[Op] = []
    scratch = project
    if tid not in project.units:
        ops += _twin_unit_ops(project, project.units[end.unit_id])
        scratch = clone_with(project, ops)
    conn = _twin_connector(end, tid)
    if conn is None or not _guided_fits(scratch, i.type_id, conn):
        pick = choose_connector(scratch, tid, i.type_id)
        if pick is None:
            raise EditError(f"{tid} has no free {_type_name(project, i.type_id)} connector.")
        conn = pick.id
    eps = [
        Endpoint(unit_id=tid, connector_id=conn, auto=end.auto) if e is end else e
        for e in i.endpoints
    ]
    ops.append(Put("interfaces", evolve(i, endpoints=eps, redundancy="redundant")))
    return ops, tid


def ops_set_endpoint_connector(
    project: Project, interface_id: str, index: int, connector_id: str
) -> list[Op]:
    """Expert mode: choose the exact connector for one end of an interface (marks it confirmed)."""
    i = _known(project.interfaces, interface_id, "Interface")
    if not 0 <= index < len(i.endpoints):
        raise EditError(f"{interface_id} has no end number {index}.")
    end = i.endpoints[index]
    if end.connector_id == connector_id:
        return []
    far = [e for k, e in enumerate(i.endpoints) if k != index]
    compat = connector_compat(
        project,
        i.type_id,
        connector_id,
        None,
        interface_id=interface_id,
        far_unit=far[0].unit_id if len(far) == 1 else None,
        far_connector=far[0].connector_id if len(far) == 1 else None,
    )
    if not compat.ok:
        raise EditError(compat.why)
    c = project.connectors[connector_id]
    if c.unit_id != end.unit_id:
        raise EditError(f"{connector_id} is not a connector of {end.unit_id}.")
    eps = [
        Endpoint(unit_id=end.unit_id, connector_id=connector_id, auto=False) if k == index else e
        for k, e in enumerate(i.endpoints)
    ]
    return [Put("interfaces", evolve(i, endpoints=eps))]


def ops_set_connector_part(project: Project, connector_id: str, part_id: str) -> list[Op]:
    c = _known(project.connectors, connector_id, "Connector")
    part = project.parts.get(part_id)
    if part is None or part.category != "connector" or part_id == TBD_PART_ID:
        raise EditError(f"'{part_id}' is not a connector part in the library.")
    if part.pin_count is not None and len(c.pins) > part.pin_count:
        raise EditError(
            f"{connector_id} has {len(c.pins)} pins but {part_id} only has {part.pin_count}."
        )
    return [Put("connectors", evolve(c, part_id=part_id))]


def ops_update_interface(project: Project, interface_id: str, **changes: object) -> list[Op]:
    """Change plain fields (name, redundancy, max_current_a, voltage_v, requirement_id, notes)."""
    allowed = {
        "name",
        "redundancy",
        "max_current_a",
        "voltage_v",
        "requirement_id",
        "notes",
        "flow",
    }
    bad = set(changes) - allowed
    if bad:
        raise EditError(f"These interface fields cannot be changed here: {', '.join(sorted(bad))}.")
    return [
        Put("interfaces", evolve(_known(project.interfaces, interface_id, "Interface"), **changes))
    ]


def parse_device_kind(value: object) -> str | None:
    """The kind of a device from a value a person gave: None (or an empty text) means *Automatic*;
    anything else must be one of the IDs of `device_kinds.KIND_IDS`, else an error that names them
    all."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str) and value.strip() in KIND_IDS:
        return value.strip()
    raise EditError(
        f"'{value}' is not a kind of device. Choose one of: {', '.join(KIND_IDS)}, "
        "or leave the kind empty to read it from the name."
    )


def ops_update_unit(project: Project, unit_id: str, **changes: object) -> list[Op]:
    """Change plain fields of a device: name, side, notes, mass_relevant and `kind` (the kind of
    equipment its card looks like, `core/device_kinds.py`; None or an empty text goes back to
    reading it from the name)."""
    allowed = {"name", "side", "notes", "mass_relevant", "kind"}
    bad = set(changes) - allowed
    if bad:
        raise EditError(f"These device fields cannot be changed here: {', '.join(sorted(bad))}.")
    if "kind" in changes:
        changes["kind"] = parse_device_kind(changes["kind"])
    return [Put("units", evolve(_known(project.units, unit_id, "Device"), **changes))]


def signal_names(project: Project) -> list[str]:
    """Signal names (PWR, RTN, CANH ...), sorted: those of the interface types the project's
    interfaces use, or of all interface types while no interface exists yet."""
    used = {i.type_id for i in project.interfaces.values()}
    types = [t for t in project.interface_types.values() if t.id in used] or list(
        project.interface_types.values()
    )
    return sorted({sig.name for t in types for sig in t.signals})


def wire_colour_map(project: Project) -> dict[str, str]:
    """The wire colour set for each signal name (`generation.wire_colour_by_signal`), if any."""
    cfg = project.config.get("generation")
    got = cfg.values.get("wire_colour_by_signal") if cfg is not None else None
    return {str(k): str(v) for k, v in got.items()} if isinstance(got, dict) else {}


def ops_set_wire_colours(project: Project, colours: dict[str, str]) -> list[Op]:
    """Ops that set the wire colour of each signal; an empty colour removes the entry. The wires
    take the colours the next time the harnesses are generated."""
    old = _known(project.config, "generation", "Configuration file")
    values = dict(old.values)
    kept = {k: v for k, v in sorted(colours.items()) if v}
    if kept:
        values["wire_colour_by_signal"] = kept
    else:
        values.pop("wire_colour_by_signal", None)
    if values == old.values:
        return []
    return [
        SetConfig(
            ConfigFile(
                name="generation", placeholder=old.placeholder, values=values, about=old.about
            )
        )
    ]


# ---- canvas editing: layout of several units, duplicate, interface delete impact ------------------
# (kept together at the end of the module; the GUI canvas uses these through the controller)

ALIGN_MODES = ("left", "hcenter", "right", "top", "vmiddle", "bottom")
DISTRIBUTE_AXES = ("horizontal", "vertical")


def _half(value: float) -> float:
    """A position rounded to half a unit of the diagram (alignments never leave odd decimals)."""
    return round(value * 2) / 2


def _unit_boxes(
    project: Project, unit_ids: list[str], heights: Mapping[str, float] | None
) -> dict[str, tuple[float, float, float]]:
    """(x, y, height) of each named unit; the height is `heights[id]` or the unit's footprint."""
    room = unit_footprints(project)
    boxes: dict[str, tuple[float, float, float]] = {}
    for uid in unit_ids:
        _known(project.units, uid, "Device")
        x, y = position_of(project, uid)
        h = heights[uid] if heights is not None and uid in heights else room[uid]
        boxes[uid] = (x, y, h)
    return boxes


def _move_ops(project: Project, positions: Mapping[str, tuple[float, float]]) -> list[Op]:
    """Ops that put each unit at its new position (and in the zone of that place); a unit that
    stays where it is gives none."""
    ops: list[Op] = []
    for uid in sorted(positions):
        x, y = positions[uid]
        if position_of(project, uid) != (x, y) or uid not in project.placements:
            ops += ops_move_unit(project, uid, x, y)
    return ops


def ops_move_units(project: Project, positions: Mapping[str, tuple[float, float]]) -> list[Op]:
    """Move several units in one step (a drag of a selection)."""
    for uid in positions:
        _known(project.units, uid, "Device")
    return _move_ops(project, positions)


def ops_align(
    project: Project,
    unit_ids: list[str],
    mode: str,
    heights: Mapping[str, float] | None = None,
) -> list[Op]:
    """Line the named units up on their left, centre or right edge, or on their top, middle or
    bottom edge. `heights` are the heights now drawn (default: each unit's room)."""
    if mode not in ALIGN_MODES:
        raise EditError(f"Unknown way to align: {mode}.")
    ids = sorted(set(unit_ids))
    if len(ids) < 2:
        raise EditError("Select at least two devices to align them.")
    boxes = _unit_boxes(project, ids, heights)
    xs = [b[0] for b in boxes.values()]
    ys = [b[1] for b in boxes.values()]
    target: dict[str, tuple[float, float]] = {}
    for uid, (x, y, h) in boxes.items():
        nx, ny = x, y
        if mode == "left":
            nx = min(xs)
        elif mode == "right":
            nx = max(xs)
        elif mode == "hcenter":
            nx = sum(xs) / len(xs)
        elif mode == "top":
            ny = min(ys)
        elif mode == "bottom":
            ny = max(b[1] + b[2] for b in boxes.values()) - h
        else:  # vmiddle
            middle = sum(b[1] + b[2] / 2 for b in boxes.values()) / len(boxes)
            ny = middle - h / 2
        target[uid] = (_half(nx), _half(ny))  # (a device may sit below zero: nothing is clamped)
    return _move_ops(project, target)


def ops_distribute(
    project: Project,
    unit_ids: list[str],
    axis: str,
    heights: Mapping[str, float] | None = None,
) -> list[Op]:
    """Space three or more units evenly between the outermost two (equal gaps between edges)."""
    if axis not in DISTRIBUTE_AXES:
        raise EditError(f"Unknown way to distribute: {axis}.")
    ids = sorted(set(unit_ids))
    if len(ids) < 3:
        raise EditError("Select at least three devices to space them evenly.")
    boxes = _unit_boxes(project, ids, heights)
    horizontal = axis == "horizontal"
    order = sorted(ids, key=lambda u: (boxes[u][0] if horizontal else boxes[u][1], u))
    size = {u: (UNIT_W if horizontal else boxes[u][2]) for u in order}
    first = boxes[order[0]][0 if horizontal else 1]
    last = boxes[order[-1]][0 if horizontal else 1] + size[order[-1]]
    gap = (last - first - sum(size.values())) / (len(order) - 1)
    if gap < 0:
        raise EditError("The devices are too close together to be spread out evenly.")
    target: dict[str, tuple[float, float]] = {}
    at = first
    for uid in order:
        x, y, _h = boxes[uid]
        target[uid] = (_half(at), y) if horizontal else (x, _half(at))
        at += size[uid] + gap
    return _move_ops(project, target)


def ops_duplicate_unit(project: Project, unit_id: str) -> tuple[list[Op], str]:
    """A copy of a unit: the same kind of connectors, none of its links or pin assignments (those
    belong to the original), a new ID built from the original's, placed in the same lane."""
    import re

    unit = _known(project.units, unit_id, "Device")
    prefix = re.sub(r"\d+$", "", unit.id) or "U"
    new_id, _n = next_unit_id(project, prefix)
    _check_new_id(new_id)
    x, y = free_slot(project, unit.zone, unit_footprint(project, unit_id))
    twin = evolve(unit, id=new_id, name=f"{unit.name} (copy)", zone=zone_of_x(project, x) or None)
    ops: list[Op] = [Put("units", twin), Put("placements", Placement(id=new_id, x=x, y=y))]
    taken = {c.casefold() for c in project.connectors}
    for k, c in enumerate(unit_connectors(project, unit_id), start=1):
        suffix = c.id.rsplit("-", 1)[-1] if "-" in c.id else f"J{k:02d}"
        cid = f"{new_id}-{suffix}"
        if cid.casefold() in taken:
            raise EditError(f"Cannot copy {unit_id}: connector {cid} already exists.")
        taken.add(cid.casefold())
        pins = [
            evolve(p, interface_id=None, signal=p.signal if p.locked or p.fixed else None)
            if p.interface_id is not None
            else p
            for p in c.pins
        ]
        ops.append(Put("connectors", evolve(c, id=cid, unit_id=new_id, pins=pins)))
    return ops, new_id


@dataclass(frozen=True)
class InterfaceImpact:
    """What deleting one interface touches, for the question asked before it is done."""

    ends: tuple[str, ...]  # the units at its two ends
    type_name: str
    plan_wires: dict[str, int]  # generated, not released harness -> wires that become outdated
    blocked_by_harnesses: tuple[str, ...]


def interface_impact(project: Project, interface_id: str) -> InterfaceImpact:
    i = _known(project.interfaces, interface_id, "Interface")
    plan: dict[str, int] = {}
    blocked: list[str] = []
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        n = sum(1 for w in h.wires if w.interface_id == interface_id)
        if not n:
            continue
        if h.generated and h.status != "released":
            plan[h.id] = n
        else:
            blocked.append(h.id)
    t = project.interface_types.get(i.type_id)
    return InterfaceImpact(
        tuple(e.unit_id for e in i.endpoints),
        t.name if t is not None else i.type_id,
        plan,
        tuple(blocked),
    )


def ops_delete_many(project: Project, unit_ids: list[str], interface_ids: list[str]) -> list[Op]:
    """Delete units and interfaces in one step; an interface that goes with a unit is deleted once."""
    ops: list[Op] = []
    seen: set[tuple[str, str]] = set()

    def add(new: list[Op]) -> None:
        for op in new:
            key = (op.collection, op.key if isinstance(op, Delete) else op.obj.id)  # type: ignore[union-attr]
            if key not in seen:
                seen.add(key)
                ops.append(op)

    gone: set[str] = set()
    for uid in sorted(unit_ids):
        add(ops_delete_unit(project, uid))
        gone.update(delete_impact(project, uid).interfaces)
    for iid in sorted(interface_ids):
        if iid not in gone:
            add(ops_delete_interface(project, iid))
    return ops
