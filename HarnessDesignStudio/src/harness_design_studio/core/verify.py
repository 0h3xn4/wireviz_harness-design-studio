# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Independent output verifier. A separate code path from `generate/`: it shares no logic with it.

It reads the project as data (exactly what is saved), re-derives from the logical layer alone what
the harnesses must contain, and compares. If generation has a bug, this is where it shows.
Checks: every logical signal appears end to end exactly once; both ends of every wire agree with
the pinout tables (pins, the wire's signal label and the cable connector's own pin table); no pin
is used twice; an interface uses the pins of one port of a connector (a fixed pin `RS422_2_TX+`
carries TX+ of port RS422_2, read by a copy of the rule of `core/ports.py`); with
`naming.far_device_names` on, an interface does not use a port named after a device other than the
one at its other end (`port_far_device`, 4.4.0; the device a name names is read by a copy of the
rule of `core/device_names.py`); a shielded type has a shield group covering its wires; harness
bookkeeping matches its wires; outputs are not stale.
Wire gauge, colour and part are not checked (they are design choices, see the design rules). It
never raises.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .generation_status import generation_status
from .issues import Issue
from .model import Connector, Harness, InterfaceInstance, Pin, Project, Wire

Endpoint = tuple[int, str]  # (end index of the interface, signal name at that end)
Connection = frozenset[Endpoint]


@dataclass
class VerifyReport:
    issues: list[Issue] = field(default_factory=list)
    interfaces_checked: int = 0
    wires_checked: int = 0
    stale: bool = False

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        state = "outdated, " if self.stale else ""
        return (
            f"{state}{self.interfaces_checked} interfaces and {self.wires_checked} wires checked: "
            f"{len(self.errors)} error(s)"
        )

    def error(self, code: str, message: str, obj: str | None = None) -> None:
        self.issues.append(Issue("error", code, message, None, obj))

    def warning(self, code: str, message: str, obj: str | None = None) -> None:
        self.issues.append(Issue("warning", code, message, None, obj))


def _pairing(signals: Sequence[tuple[str, str]]) -> tuple[list[str], list[str], set[str]]:
    """Outputs, inputs and the directional signals that pass straight through (no partner)."""
    outs = [n for n, d in signals if d == "out"]
    ins = [n for n, d in signals if d == "in"]
    paired = min(len(outs), len(ins)) if (outs and ins) else 0
    return outs[:paired], ins[:paired], {*outs[paired:], *ins[paired:]}


def passthrough_signals(signals: Sequence[tuple[str, str]]) -> set[str]:
    """Unpaired directional signals (more outputs than inputs or the reverse): they connect to
    the same name at the other end. The design rules use this too, so both agree."""
    return _pairing(signals)[2]


def direction_judged(signals: Sequence[tuple[str, str]]) -> bool:
    """True when the directions of an interface type can be judged: it has outputs and inputs.
    A one-directional type (analog SIG+/SIG-, discrete SIG, LVDS D+/D-, pyro FIRE+/FIRE-, I2C SCL
    with no input) lists its signals as `out` at both ends, so two outputs on a wire are right.
    The design rules `direction-conflict` and `link-direction` both use this."""
    return {"out", "in"} <= {d for _, d in signals}


def expected_connections(signals: Sequence[tuple[str, str]]) -> Counter[Connection]:
    """Connections an interface of this type needs, as unordered pairs of (end, signal).

    End 0/1 are the interface's first/second endpoint. An `out` signal at one end connects to the
    `in` signal at the same position in the other end; `passive`/`bidir` connect to the same name.
    """
    outs, ins, leftover = _pairing(signals)
    need: Counter[Connection] = Counter()
    for k in range(len(outs)):
        need[frozenset({(0, outs[k]), (1, ins[k])})] += 1
        need[frozenset({(1, outs[k]), (0, ins[k])})] += 1
    for name, direction in signals:  # unpaired directional signals pass straight through
        if direction in ("passive", "bidir") or name in leftover:
            need[frozenset({(0, name), (1, name)})] += 1
    return need


# Port names (D-237). The verifier reads them with its own copy of the rule of `core/ports.py`
# (`read_signal`), not with an import of it; `tests/test_ports_checks.py` compares the two.
_PORT_SEPARATORS = ("_", ".", "-")

PortReading = tuple[str, str, str, str]  # (port, signal, form, separator); port "" is bare


def port_readings(name: str, signals: Iterable[str]) -> tuple[PortReading, ...]:
    """Every way a fixed pin's name reads against the signal names of a type, sorted: a signal name
    itself is the bare reading; `P<sep>t` and `t<sep>P` (sep `_`, `.` or `-`, P not empty) are
    signal t of port P. One reading: the pin carries t. None, or two and more: it carries its own
    name (no port is guessed)."""
    names = set(signals)
    if name in names:
        return (("", name, "bare", ""),)
    out: set[PortReading] = set()
    for t in names:
        if not t:
            continue
        for sep in _PORT_SEPARATORS:
            tail, head = sep + t, t + sep
            if len(name) > len(tail) and name.endswith(tail):
                out.add((name[: -len(tail)], t, "prefix", sep))
            if len(name) > len(head) and name.startswith(head):
                out.add((name[len(head) :], t, "suffix", sep))
    return tuple(sorted(out))


def _carried(pin: Pin, signals: Sequence[str]) -> tuple[str | None, str | None]:
    """(signal of the type, port) a box pin carries: a fixed pin `RS422_2_TX+` carries TX+ of port
    RS422_2; a fixed pin with a signal name carries it in the bare port ""; any other pin carries
    its own name and no port (None)."""
    if pin.fixed and pin.signal:
        found = port_readings(pin.signal, signals)
        if len(found) == 1:
            return found[0][1], found[0][0]
    return pin.signal, None


def _check_ports(
    project: Project, rep: VerifyReport, i: InterfaceInstance, names: list[str]
) -> None:
    """An interface uses the pins of one port at each connector (`port_mixed`)."""
    for cid in sorted({e.connector_id for e in i.endpoints if e.connector_id}):
        box = project.connectors.get(cid)
        if box is None:
            continue
        ports = {
            port
            for pin in box.pins
            if pin.interface_id == i.id
            for _sig, port in [_carried(pin, names)]
            if port is not None
        }
        if len(ports) > 1:
            shown = ", ".join(n or "pins named by the signal alone" for n in sorted(ports))
            rep.error(
                "port_mixed",
                f"Interface {i.id} uses the pins of {len(ports)} ports on {cid} ({shown}); "
                "an interface uses the pins of one port. Regenerate, or lock the pins of one port.",
                i.id,
            )


# Device names (4.4.0, D-262). The verifier reads which device a port name names with its own copy
# of the rule of `core/device_names.py` (`named_device`), not with an import of it;
# `tests/test_device_names.py` compares the two.
_DEVICE_SEPARATORS = frozenset("_.-")

DeviceNaming = tuple[str, str, str, str]  # (device, rest, form, separator); device "" for two


def device_naming(name: str, unit_ids: Iterable[str], port: bool = False) -> DeviceNaming | None:
    """The device a pin or port name names among `unit_ids`, or None. `D<sep>rest` (form prefix)
    and `rest<sep>D` (form suffix), with D a device ID, sep `_`, `.` or `-` and rest not empty,
    name D; a port name equal to an ID names it (form whole). The ID is compared exactly, with
    case; the longest ID at each end wins; a name whose prefix and suffix are two devices names
    neither, and gives the device "". A pin name that is an ID names nothing."""
    ids = {u for u in unit_ids if u}
    if not name:
        return None
    if name in ids:
        return (name, "", "whole", "") if port else None
    heads = sorted(
        (len(u), u)
        for u in ids
        if len(name) > len(u) + 1 and name.startswith(u) and name[len(u)] in _DEVICE_SEPARATORS
    )
    tails = sorted(
        (len(u), u)
        for u in ids
        if len(name) > len(u) + 1 and name.endswith(u) and name[-len(u) - 1] in _DEVICE_SEPARATORS
    )
    head = heads[-1][1] if heads else ""
    tail = tails[-1][1] if tails else ""
    if head and tail and head != tail:
        return ("", "", "", "")
    if head:
        return (head, name[len(head) + 1 :], "prefix", name[len(head)])
    if tail:
        return (tail, name[: -len(tail) - 1], "suffix", name[-len(tail) - 1])
    return None


def _far_device_names(project: Project) -> bool:
    """`config/naming.json` `far_device_names` is `true` (read as saved; anything else is off)."""
    cfg = project.config.get("naming")
    return cfg is not None and cfg.values.get("far_device_names") is True


def _check_port_far_device(
    project: Project,
    rep: VerifyReport,
    i: InterfaceInstance,
    names: list[str],
    released: dict[str, str],
) -> None:
    """An interface does not use a port named after a device other than the one at its other end
    (`port_far_device`, 4.4.0): an error for pins nobody locked, a warning for locked pins or an
    interface of a released harness (`released`: interface -> harness), which are kept."""
    units = list(project.units)
    for end in i.endpoints:
        others = [e for e in i.endpoints if e is not end]
        far = others[0].unit_id if len(others) == 1 else ""
        box = project.connectors.get(end.connector_id or "")
        if not far or far == end.unit_id or box is None or box.role != "box":
            continue
        mine = [(pin, _carried(pin, names)[1]) for pin in box.pins if pin.interface_id == i.id]
        for port in sorted({p for _pin, p in mine if p}):
            found = device_naming(port, units, port=True)
            if found is None or not found[0] or found[0] == far:
                continue
            text = (
                f"Interface {i.id} goes to unit {far} but uses port {port} of {box.id}, which is"
                f" named after unit {found[0]} (naming.far_device_names)."
            )
            if i.id in released:
                rep.warning(
                    "port_far_device",
                    f"{text} It is kept because harness {released[i.id]} is released; a new"
                    f" version takes the port of {far}.",
                    i.id,
                )
            elif any(pin.locked for pin, p in mine if p == port):
                rep.warning(
                    "port_far_device", f"{text} It is kept because a person locked the pins.", i.id
                )
            else:
                rep.error(
                    "port_far_device", f"{text} Regenerate, or choose the port of {far}.", i.id
                )


def _cable_index(project: Project) -> dict[str, tuple[Harness, Connector]]:
    return {c.id: (h, c) for h in project.harnesses.values() for c in h.connectors}


def _check_wire_ends(
    project: Project, rep: VerifyReport, cables: dict[str, tuple[Harness, Connector]]
) -> tuple[dict[tuple[str, str], list[str]], dict[tuple[str, str], list[str]]]:
    """Wire ends exist, mate with real unit connectors, and no pin is used twice."""
    cable_use: dict[tuple[str, str], list[str]] = {}
    box_use: dict[tuple[str, str], list[str]] = {}
    for h in project.harnesses.values():
        splices = _splices_of(h)
        for w in h.wires:
            rep.wires_checked += 1
            same_pin = (w.from_connector, w.from_pin) == (w.to_connector, w.to_pin)
            if same_pin:
                rep.error(
                    "wire_same_pin",
                    f"Wire {w.id} starts and ends on the same pin ({w.from_pin} of {w.from_connector}).",
                    w.id,
                )
            for side, cid, pid in (
                ("from", w.from_connector, w.from_pin),
                ("to", w.to_connector, w.to_pin),
            ):
                # one pin used once (same pin: reported above); a splice node joins its wires
                if not (same_pin and side == "to") and cid not in splices:
                    cable_use.setdefault((cid, pid), []).append(w.id)
                owner = cables.get(cid)
                if owner is None or owner[0].id != h.id:
                    rep.error(
                        "wire_end_missing",
                        f"Wire {w.id} {side} end is on {cid}, which is not part of harness {h.id}.",
                        w.id,
                    )
                    continue
                cable = owner[1]
                if pid not in {p.id for p in cable.pins}:
                    rep.error(
                        "wire_pin_missing",
                        f"Wire {w.id} {side} end uses pin {pid}, which {cid} does not have.",
                        w.id,
                    )
                if cable.mates_with in project.connectors:
                    if not (same_pin and side == "to"):
                        box_use.setdefault((str(cable.mates_with), pid), []).append(w.id)
                elif h.generated and cable.role != "splice":
                    rep.error(
                        "mate_missing",
                        f"Cable connector {cid} does not plug into an existing device connector.",
                        cid,
                    )
        if h.generated:
            carried = sorted({w.interface_id for w in h.wires if w.interface_id})
            if sorted(h.interfaces) != carried:
                rep.error(
                    "harness_interfaces",
                    f"Harness {h.id} lists interfaces {sorted(h.interfaces)} but its wires carry {carried}.",
                    h.id,
                )
    return cable_use, box_use


def _wire_connection(
    project: Project,
    rep: VerifyReport,
    cables: dict[str, tuple[Harness, Connector]],
    iface_id: str,
    w: Wire,
) -> Connection | None:
    """The (end, signal) pair a wire really joins, read from the pinout tables. None if inconsistent."""
    i = project.interfaces[iface_id]
    ends: list[Endpoint] = []
    for cid, pid in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin)):
        end = _end_of(project, rep, cables, i, cid, pid, w.id)
        if end is None:
            return None
        ends.append(end)
    if ends[0] == ends[1]:
        if (w.from_connector, w.from_pin) != (w.to_connector, w.to_pin):  # else reported earlier
            rep.error(
                "wire_same_end",
                f"Wire {w.id} joins two pins at the same end of interface {i.id}, both carrying {ends[0][1]}.",
                w.id,
            )
        return None
    label = _wire_label(ends[0][1], ends[1][1])
    if w.signal is not None and w.signal not in label:
        rep.error(
            "wire_signal_mismatch",
            f"Wire {w.id} is labelled {w.signal}, but its pins carry {ends[0][1]} and {ends[1][1]} "
            f"in the pinout tables of {i.id}.",
            w.id,
        )
    return frozenset(ends)


def _end_of(
    project: Project,
    rep: VerifyReport,
    cables: dict[str, tuple[Harness, Connector]],
    i: InterfaceInstance,
    cid: str,
    pid: str,
    wire_id: str,
    *,
    strict: bool = True,
) -> Endpoint | None:
    """The (end of the interface, signal) a pin of a cable connector reaches, read from the pinout
    table of the device connector it plugs into; None (and an error) if it reaches none. With
    `strict` False a device connector that is not an end of the interface gives None and no
    error (a net through a splice may reach the ends of other interfaces too)."""
    owner = cables.get(cid)
    box = project.connectors.get(owner[1].mates_with or "") if owner else None
    if box is None:
        return None
    idx = next(
        (
            k
            for k, e in enumerate(i.endpoints)
            if e.connector_id == box.id and e.unit_id == box.unit_id
        ),
        None,
    )
    if idx is None:
        if strict:
            rep.error(
                "wrong_endpoint",
                f"Wire {wire_id} ends on {box.id}, which is not an end of interface {i.id}.",
                wire_id,
            )
        return None
    pin = next((p for p in box.pins if p.id == pid), None)
    if pin is None or pin.signal is None or pin.interface_id != i.id:
        rep.error(
            "pinout_mismatch",
            f"Wire {wire_id}: pin {pid} of {box.id} is not allocated to {i.id} in the pinout table.",
            wire_id,
        )
        return None
    cable_pin = next((p for p in owner[1].pins if p.id == pid), None) if owner else None
    if cable_pin is not None and (
        cable_pin.signal not in (None, pin.signal)
        or cable_pin.interface_id not in (None, pin.interface_id)
    ):
        rep.error(
            "cable_pin_mismatch",
            f"Wire {wire_id}: pin {pid} of cable connector {cid} is marked "
            f"{cable_pin.signal or 'no signal'} of {cable_pin.interface_id or 'no interface'}, "
            f"but pin {pid} of {box.id} carries {pin.signal} of {pin.interface_id}.",
            wire_id,
        )
        return None
    itype = project.interface_types.get(i.type_id)
    carried = _carried(pin, [s.name for s in itype.signals] if itype else [])[0]
    return idx, carried or pin.signal


# ---- nets through splices (format 3, M6a): the verifier's own copy of `core/nets.py` ------------


def _splices_of(h: Harness) -> set[str]:
    return {c.id for c in h.connectors if c.role == "splice"}


def splice_nets(h: Harness) -> list[tuple[frozenset[tuple[str, str]], frozenset[str]]]:
    """The nets of a harness as (pins, wire IDs): the pins joined by its wires, a pin joining every
    wire on it. Worked out here by a walk over the wires, not with `core/nets.py`; a test compares
    the two (and the output check's third copy)."""
    by_pin: dict[tuple[str, str], list[Wire]] = {}
    for w in h.wires:
        by_pin.setdefault((w.from_connector, w.from_pin), []).append(w)
        by_pin.setdefault((w.to_connector, w.to_pin), []).append(w)
    seen: set[tuple[str, str]] = set()
    out = []
    for start in sorted(by_pin):
        if start in seen:
            continue
        pins: set[tuple[str, str]] = set()
        wires: set[str] = set()
        todo = [start]
        while todo:
            pin = todo.pop()
            if pin in pins:
                continue
            pins.add(pin)
            for w in by_pin[pin]:
                wires.add(w.id)
                todo += [(w.from_connector, w.from_pin), (w.to_connector, w.to_pin)]
        seen |= pins
        out.append((frozenset(pins), frozenset(wires)))
    return out


def _splice_connections(
    project: Project,
    rep: VerifyReport,
    cables: dict[str, tuple[Harness, Connector]],
    i: InterfaceInstance,
    wires: list[Wire],
    spliced: list[Harness],
) -> tuple[Counter[Connection], set[str], int]:
    """The connections of interface `i` through splices: each net with a splice node that holds a
    wire of the interface joins each pair of its ends (pins not on a splice) that reach two pins of
    the interface's ends: one connection per pair (section 6.4 of the design of 2.3.0). Returns
    the connections, the wires they cover and how many nets could not be read. `spliced` are the
    harnesses that have a splice, by ID."""
    found: Counter[Connection] = Counter()
    covered: set[str] = set()
    unreadable = 0
    mine = {w.id for w in wires}
    for h in spliced:
        splices = _splices_of(h)
        interface_of = {w.id: w.interface_id for w in h.wires}
        for pins, ids in splice_nets(h):
            if not (ids & mine) or not any(cid in splices for cid, _ in pins):
                continue
            covered |= ids & mine
            alone = all(interface_of[x] == i.id for x in ids)  # no other interface on the net
            first = min(ids & mine)
            ends: list[Endpoint] = []
            bad = False
            for cid, pid in sorted(p for p in pins if p[0] not in splices):
                end = _end_of(project, rep, cables, i, cid, pid, first, strict=alone)
                if end is None:
                    owner = cables.get(cid)
                    box = project.connectors.get(owner[1].mates_with or "") if owner else None
                    bad = bad or (box is not None and alone)
                    continue
                ends.append(end)
            if bad:
                unreadable += 1
            for k, a in enumerate(ends):
                for b in ends[k + 1 :]:
                    if a != b:
                        found[frozenset({a, b})] += 1
    return found, covered, unreadable


def _wire_label(a: str, b: str) -> set[str]:
    """Labels a wire between signals `a` and `b` may carry: the shared name, or one of the two orders."""
    return {a} if a == b else {f"{a}/{b}", f"{b}/{a}"}


def _check_shields(project: Project, rep: VerifyReport) -> None:
    """A type with shielding has a shield group covering its wires (overall: every wire; per
    pair: at least one wire, as signals without a pair are not shielded). The groups' ends and
    kinds are checked by design rules, not here."""
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        if not h.generated:
            continue
        covered = {wid for sh in h.shields if sh.kind != "twisted_pair" for wid in sh.wire_ids}
        for iid in sorted({w.interface_id for w in h.wires if w.interface_id}):
            i = project.interfaces.get(iid)
            itype = project.interface_types.get(i.type_id) if i else None
            if itype is None or itype.shielding == "none":
                continue
            ids = sorted(w.id for w in h.wires if w.interface_id == iid)
            missing = ids if not covered.intersection(ids) else []
            if itype.shielding == "overall":
                missing = [w for w in ids if w not in covered]
            if missing:
                rep.error(
                    "shield_missing",
                    f"Interface {iid} ({itype.id}) is shielded ({itype.shielding.replace('_', ' ')}) but no shield group of {h.id} covers "
                    f"{', '.join(missing[:3])}{' and others' if len(missing) > 3 else ''}.",
                    h.id,
                )


def _expected_signal(x: str | None, y: str | None) -> set[str | None]:
    """The signal label a wire between two pins may carry: one name when both pins have it,
    "x/y" (or "y/x") when they differ, the one that is there when only one has a name."""
    a, b = (x or "").strip(), (y or "").strip()
    if a and b and a != b:
        return {f"{a}/{b}"[:200], f"{b}/{a}"[:200]}
    return {a or b or None}


def link_issues(project: Project) -> list[Issue]:
    """Errors for a harness made from a link that no longer carries what the link pairs: the pins
    through the two cable connectors and the signals must be the link's. Only links that name a
    harness are checked (`Link.harness_id`); a link with no harness has nothing to compare. It
    reads the link, the harness and the device pins as saved, and shares no code with the planner
    that made the harness."""
    out: list[Issue] = []
    for link in sorted(project.links.values(), key=lambda x: x.id):
        h = project.harnesses.get(link.harness_id or "")
        if h is None:
            continue  # no harness named, or a harness that is gone (the integrity check says so)
        ends = (link.a_connector, link.b_connector)
        cable = [next((c.id for c in h.connectors if c.mates_with == box), None) for box in ends]
        if cable[0] is None or cable[1] is None:
            lacking = ends[0] if cable[0] is None else ends[1]
            out.append(
                Issue(
                    "error", "link_wire_mismatch",
                    f"Link {link.id} says harness {h.id} was made from it, but {h.id} has no cable connector that plugs into {lacking}. Make the harness again from the link, or delete the link.",
                    None, link.id,
                )
            )  # fmt: skip
            continue
        ca, cb = cable
        want = Counter((p.a_pin, p.b_pin) for p in link.pairs)
        found: Counter[tuple[str, str]] = Counter()
        wire_of: dict[tuple[str, str], list[Wire]] = {}
        for w in h.wires:
            if (w.from_connector, w.to_connector) == (ca, cb):
                key = (w.from_pin, w.to_pin)
            elif (w.from_connector, w.to_connector) == (cb, ca):
                key = (w.to_pin, w.from_pin)
            else:
                continue
            found[key] += 1
            wire_of.setdefault(key, []).append(w)
        a, b = (project.connectors.get(box) for box in ends)
        pins_a = {p.id: p for p in a.pins} if a is not None else {}
        pins_b = {p.id: p for p in b.pins} if b is not None else {}
        for key in sorted(set(want) | set(found)):
            n_want, n_have = want.get(key, 0), found.get(key, 0)
            where = f"pin {key[0]} of {ends[0]} with pin {key[1]} of {ends[1]}"
            between = f"pin {key[0]} of {ends[0]} and pin {key[1]} of {ends[1]}"
            if n_want > n_have:
                text = f"Link {link.id} pairs {where}, but harness {h.id} has no wire between those pins. Add the wire, or change the pairing of the link."  # fmt: skip
            elif n_have > n_want:
                ids = ", ".join(w.id for w in wire_of[key])
                text = f"Harness {h.id} has {'a wire' if n_have == 1 else 'wires'} {ids} between {between}, which link {link.id} does not pair. Remove the wire, or add the pair to the link."  # fmt: skip
            else:
                if key[0] in pins_a and key[1] in pins_b:
                    ok = _expected_signal(pins_a[key[0]].signal, pins_b[key[1]].signal)
                    bad = [w for w in wire_of[key] if w.signal not in ok]
                else:
                    bad = []
                if not bad:
                    continue
                shown = bad[0].signal or "no signal"
                text = f"Wire {bad[0].id} of harness {h.id} carries {shown} between {between}, which does not match the signals of the pins in link {link.id}. Correct the wire, or the signal of the pin."  # fmt: skip
            out.append(Issue("error", "link_wire_mismatch", text, None, link.id))
    return out


def verify_project(project: Project) -> VerifyReport:
    rep = VerifyReport()
    cables = _cable_index(project)
    cable_use, box_use = _check_wire_ends(project, rep, cables)
    drawn = {w.id for h in project.harnesses.values() for w in h.wires if w.manual}
    for label, use in (("", cable_use), ("device connector ", box_use)):
        for (cid, pid), users in sorted(use.items()):
            if len(users) > 1:
                text = (
                    f"Pin {pid} of {label}{cid} is used by {len(users)} wires: "
                    f"{', '.join(sorted(users))}."
                )
                if drawn.intersection(users):  # a person put a wire there: said, not an error
                    rep.warning("pin_shared", text, cid)
                else:
                    rep.error("pin_reused", text, cid)

    spliced = sorted((h for h in project.harnesses.values() if _splices_of(h)), key=lambda x: x.id)
    by_interface: dict[str, list[Wire]] = {}
    for h in project.harnesses.values():
        for w in h.wires:
            if w.interface_id is not None:
                by_interface.setdefault(w.interface_id, []).append(w)

    far_on = _far_device_names(project)
    released = {
        iid: h.id
        for h in sorted(project.harnesses.values(), key=lambda x: x.id, reverse=True)
        if h.status == "released"
        for iid in h.interfaces
    }  # the first harness by ID wins
    for i in sorted(project.interfaces.values(), key=lambda x: x.id):
        itype = project.interface_types.get(i.type_id)
        if (
            itype is None
            or len(i.endpoints) != 2
            or any(e.connector_id not in project.connectors for e in i.endpoints)
        ):
            continue  # not routable (reported elsewhere)
        rep.interfaces_checked += 1
        _check_ports(project, rep, i, [s.name for s in itype.signals])
        if far_on:
            _check_port_far_device(project, rep, i, [s.name for s in itype.signals], released)
        need = expected_connections([(s.name, s.direction) for s in itype.signals])
        wires = by_interface.get(i.id, [])
        found, through, unreadable = _splice_connections(project, rep, cables, i, wires, spliced)
        for w in wires:
            if w.id in through:
                continue  # counted per net, above
            conn = _wire_connection(project, rep, cables, i.id, w)
            if conn is None:
                unreadable += 1
            else:
                found[conn] += 1
        for conn, n in sorted(need.items(), key=lambda kv: sorted(kv[0])):
            have = found.get(conn, 0)
            a, b = sorted(conn)
            text = f"{a[1]} (end {a[0] + 1}) to {b[1]} (end {b[0] + 1})"
            if have == 0 and not unreadable:
                rep.error("signal_missing", f"Interface {i.id}: {text} has no wire.", i.id)
            elif have > n:
                rep.error(
                    "signal_duplicated",
                    f"Interface {i.id}: {text} has {have} wires, expected {n}.",
                    i.id,
                )
        for conn in sorted(set(found) - set(need), key=lambda c: sorted(c)):
            a, b = sorted(conn)
            rep.error(
                "wire_extra",
                f"Interface {i.id} has a wire {a[1]} to {b[1]} that its type does not define.",
                i.id,
            )
    _check_shields(project, rep)
    rep.issues.extend(link_issues(project))
    for iid in sorted(set(by_interface) - set(project.interfaces)):
        rep.warning("wire_orphan", f"Wires trace to interface {iid}, which no longer exists.", iid)

    has_outputs = project.generation is not None or any(
        h.generated for h in project.harnesses.values()
    )
    if has_outputs and generation_status(project) != "current":
        rep.stale = True
        rep.error(
            "outputs_outdated",
            "The model changed after the harness plans were generated. Generate again before releasing.",
        )
    return rep
