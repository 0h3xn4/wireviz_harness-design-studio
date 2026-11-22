# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Pin allocation for one box connector. Rules (each placement records why it was chosen):

1. Pins the user locked are never moved.
2. Signals of a twisted pair go on adjacent pins; power and return are grouped.
3. Power goes first on the connector; other signals follow after the configured gap.
4. A previous generated allocation is kept when it is still valid (small changes, small diffs).
5. On a fixed pinout an interface takes one port: the free pins of the exact names when they hold
   every signal (as at 2.0.1), else one complete named port such as `RS422_2_TX+` (D-237).
6. With `naming.far_device_names` on (4.4.0, A-FAR-DEVICE), an interface takes the port named after
   the device at its other end first (`TTC2_TX+` for the interface to TTC2), and never a port named
   after another device. Off (the default), the allocation is the one of 4.3.0.
"""

from dataclasses import dataclass, field

from harness_design_studio.core import settings
from harness_design_studio.core.device_names import named_device
from harness_design_studio.core.model import Connector, InterfaceType, Project
from harness_design_studio.core.ports import ConnectorPorts, Port, natural_key, ports_of

DEFAULT_ORDER = ("power", "ground")  # the interface categories allocated first, in this order
# How a fixed pinout gives ports to interfaces (D-237): the words of the explanation of a pin.
PORT_ORDER_TEXT = "ports in name order, interfaces in ID order"
# The setting that gives an interface the port named after its far device (4.4.0, A-FAR-DEVICE).
FAR_DEVICE_SETTING = "naming.far_device_names"

# The model that picks the run of pins for a group of signals (`model.pin_fit_strategy`, S3b).
# `first_fit` is what the tool always did and is the default.
STRATEGIES = ("first_fit", "last_fit", "spread")
DEFAULT_STRATEGY = "first_fit"
STRATEGY_TEXT = {
    "first_fit": "the first free run of pins, from the first pin up",
    "last_fit": "the last free run of pins, from the last pin down (power at the end, the signals below it)",
    "spread": "the first free run of pins that has a free pin on each side of it, apart from the pins of its own interface (first fit when there is no room)",
}


@dataclass(frozen=True)
class PinRules:
    """The settings the pin allocation of every connector runs with."""

    gap: int  # generation.power_signal_gap_pins (0 when unset)
    return_gap: int  # generation.power_return_gap_pins
    categories: tuple[str, ...]  # model.pin_allocation_categories
    fit: str  # model.pin_fit_strategy in force
    earlier: str  # the fit the harnesses were last generated with
    far_devices: bool = False  # naming.far_device_names is true (4.4.0)
    units: tuple[str, ...] = ()  # the device IDs a port name is read against (only when on)


def strategy(project: Project) -> str:
    """The pin fit strategy in force: the one function generation and the explanation call."""
    value = settings.effective(project, "model", "pin_fit_strategy").value
    return str(value) if value in STRATEGIES else DEFAULT_STRATEGY


def far_devices(project: Project) -> bool:
    """`naming.far_device_names` is on (4.4.0, A-FAR-DEVICE): only the value `true` turns it on;
    not set, `false` or a refused value (`config_invalid`) is the behaviour of 4.3.0. The one
    function generation, the editor's dry run and the explanation call."""
    return settings.effective(project, "naming", "far_device_names").value is True


def earlier_strategy(project: Project) -> str:
    """The fit the harnesses were last generated with: a non-default one is recorded in the
    generation record (`model:pin_fit_strategy`); no entry means the default."""
    lines = (
        project.generation.provenance.get("model:pin_fit_strategy") if project.generation else None
    )
    name = lines[0].split(":", 1)[0] if lines else DEFAULT_STRATEGY
    return name if name in STRATEGIES else DEFAULT_STRATEGY


def _rank(categories: tuple[str, ...], category: str) -> int:
    """The place of a category in the order of allocation: its index in `categories`, after which
    every other category comes (model.pin_allocation_categories)."""
    return categories.index(category) if category in categories else len(categories)


@dataclass
class Request:
    interface_id: str
    itype: InterfaceType
    far: str = ""  # the device at the other end of the interface ("" for none or not known)


@dataclass
class Allocation:
    # (interface_id, signal) -> pin id
    pins: dict[tuple[str, str], str] = field(default_factory=dict)
    reasons: dict[str, list[str]] = field(default_factory=dict)  # pin id -> lines
    errors: list[tuple[str, str]] = field(default_factory=list)  # (interface_id, message)
    warnings: list[tuple[str, str]] = field(default_factory=list)
    # (connector ID, message): interfaces of one type on repeated bare names (pin_port_unknown)
    port_warnings: list[tuple[str, str]] = field(default_factory=list)


def _allocate_fixed(
    connector: Connector,
    requests: list[Request],
    previous: dict[tuple[str, str], str],
    held: dict[tuple[str, str], str],
    categories: tuple[str, ...] = DEFAULT_ORDER,
    fit: str = DEFAULT_STRATEGY,
    far_devices: bool = False,
    units: tuple[str, ...] = (),
) -> Allocation:
    """The pinout is fixed by the unit's design: every signal goes to the free pin of that name.
    A signal the connector has no pin for is an error; nothing is placed on unnamed pins. A locked
    pin that already carries a signal of an interface keeps it (`held`): that signal is not
    placed again and the pin is not offered to anyone else.

    Ports (D-237, `core/ports.py`): the pins `RS422_2_TX+`, `RS422_2_TX-` ... form the port RS422_2
    of a type with the signals TX+, TX- .... The keys of `previous` and `held` are the signals of
    the type. An interface uses the pins of one port, all or nothing:

    1. an interface whose locked pins are in a named port takes its other signals from that port,
       or fails; locked pins in two ports are an error;
    2. an interface gets back the complete named port it held before, while it is still free;
    3. every other interface, by the order of the categories and then by ID, takes the free pins
       of the exact names: the code and the result of 2.0.1;
    4. an interface that step 3 cannot place, and that has no locked pin, takes the first free
       complete named port in natural order of the names (`RS422_2` before `RS422_10`).

    Step 3 runs for every interface before step 4, so a named port never takes a pin that the
    exact-name path gives to another interface. Two or more interfaces of one type on repeated bare
    names (`TX+` on two pins) are placed as at 2.0.1, with a warning in `port_warnings`.

    With `far_devices` (`naming.far_device_names`, 4.4.0; design of 4.4.0 section 3.2) a port whose
    name names a device of `units` (`TTC2`, `TTC2_TM`; `core/device_names.py`) is that device's port,
    and the far device of an interface is `Request.far`:

    0. after step 1, every interface with no locked pin whose far device F has a usable port here
       takes, in the ranked order, the port of F it held before while it is free, else the first
       free port of F in natural order;
    2. the port held before is kept only when it names no device other than F;
    4. a port that names a device other than F is left out; when nothing is left, the error names
       the ports so left out.

    An interface with no far device sees every port, as without the setting. Without `far_devices`
    nothing of this runs: the function is the one of 4.3.0 (`tests/test_ports_compat_430.py`)."""
    result = Allocation()
    by_signal: dict[str, list[str]] = {}
    for p in connector.pins:
        if p.fixed and p.signal and not p.locked:
            by_signal.setdefault(p.signal, []).append(p.id)
    offered = {pid for ids in by_signal.values() for pid in ids}
    used: set[str] = set(held.values())
    ranked = sorted(requests, key=lambda r: (_rank(categories, r.itype.category), r.interface_id))
    found: dict[str, ConnectorPorts] = {}
    port_of: dict[str, dict[str, str]] = {}  # type ID -> pin ID -> port name ("" is the bare port)
    for req in ranked:
        if req.itype.id not in found:
            cp = found[req.itype.id] = ports_of(connector, req.itype)
            every = (cp.bare, *cp.named) if cp.bare is not None else cp.named
            port_of[req.itype.id] = {pp.pin_id: port.name for port in every for pp in port.pins}
    # type ID -> port name -> the device the port is named after (only with `far_devices`)
    named_after: dict[str, dict[str, str]] = {}
    if far_devices:
        for type_id, cp in found.items():
            named_after[type_id] = {
                x.name: r.unit
                for x in cp.named
                if (r := named_device(x.name, units, port=True)) is not None and r.names
            }
    owner = {p.id: p.interface_id for p in connector.pins if p.interface_id}  # released pins
    owner.update({pid: iid for (iid, _sig), pid in held.items()})
    placed: dict[int, list[tuple[str, str, str]]] = {}  # place in `ranked` -> (signal, pin, why)
    errors: dict[int, str] = {}
    unlocked: list[int] = []  # no locked pin of their own: steps 2 to 4
    exact_only: set[int] = set()  # a locked pin, none in a named port: step 3 only
    missing_of: dict[int, list[str]] = {}  # the signals step 3 found no free pin for

    def free(pid: str | None) -> bool:
        return pid is not None and pid in offered and pid not in used

    def far_port(req: Request, name: str) -> bool:
        """The port `name` is named after the far device of `req` (never without `far_devices`)."""
        return bool(req.far) and named_after.get(req.itype.id, {}).get(name) == req.far

    def other_device(req: Request, name: str) -> str:
        """The device other than the far device of `req` that port `name` is named after; "" for
        none, for an interface with no far device, and always without `far_devices`."""
        unit = named_after.get(req.itype.id, {}).get(name, "")
        return unit if req.far and unit and unit != req.far else ""

    def port_why(req: Request, port: Port) -> str:
        return _far_why(req.far) if far_port(req, port.name) else _port_why(req.itype)

    def port_before(k: int) -> Port | None:
        """The complete named port interface `k` held before, while it is still free."""
        req = ranked[k]
        iid, sigs = req.interface_id, _signals(req.itype)
        before = [previous.get((iid, sig)) for sig in sigs]
        held_in = {port_of[req.itype.id].get(pid or "") for pid in before}
        name = held_in.pop() if len(held_in) == 1 else None
        port = found[req.itype.id].port(name) if name else None
        if (
            port is not None
            and port.usable
            and all(
                port.pin_of(sig) == pid and free(pid) for sig, pid in zip(sigs, before, strict=True)
            )
        ):
            return port
        return None

    def take(k: int, iid: str, port: Port, signals: list[str], why: str) -> None:
        picks = [(sig, port.pin_of(sig) or "") for sig in signals]
        used.update(pid for _sig, pid in picks)
        owner.update({pid: iid for _sig, pid in picks})
        placed[k] = [
            (
                sig,
                pid,
                f"pin-allocation: {sig} of {iid} uses pin {pid}, the {sig} of port {port.name} of"
                f" {connector.id}{why}",
            )
            for sig, pid in picks
        ]

    # 1. locked pins in a named port
    for k, req in enumerate(ranked):
        iid, sigs = req.interface_id, _signals(req.itype)
        on_lock = [held[(iid, sig)] for sig in sigs if (iid, sig) in held]
        ports_here = port_of[req.itype.id]
        names = sorted({ports_here[pid] for pid in on_lock if pid in ports_here}, key=natural_key)
        if not any(names):
            if on_lock:
                exact_only.add(k)
            else:
                unlocked.append(k)
            continue
        if len(names) > 1:
            shown = ", ".join(n or "the pins named by the signal alone" for n in names)
            errors[k] = (
                f"the locked pins of {iid} on {connector.id} are in {len(names)} ports ({shown});"
                " an interface uses the pins of one port only, so unlock the pins of all ports"
                " but one"
            )
            continue
        port = found[req.itype.id].port(names[0])
        rest = [sig for sig in sigs if (iid, sig) not in held]
        lacking = [sig for sig in rest if port is None or not free(port.pin_of(sig))]
        if port is None or lacking:
            errors[k] = (
                f"the locked pins of {iid} on {connector.id} are in port {names[0]}, which has no"
                f" free pin for {', '.join(lacking or rest)}; the pins of two ports are never mixed"
            )
            continue
        take(k, iid, port, rest, ", the port its locked pins are in")

    # 0. the port named after the far device (naming.far_device_names): the one held before, then
    # the first free one in natural order
    if far_devices:
        for k in unlocked:
            req = ranked[k]
            port = port_before(k) if req.far else None
            if port is not None and far_port(req, port.name):
                take(k, req.interface_id, port, _signals(req.itype), _far_why(req.far))
        for k in unlocked:
            req = ranked[k]
            if k in placed or not req.far:
                continue
            sigs = _signals(req.itype)
            port = next(
                (
                    x
                    for x in found[req.itype.id].usable
                    if far_port(req, x.name) and all(free(x.pin_of(sig)) for sig in sigs)
                ),
                None,
            )
            if port is not None:
                take(k, req.interface_id, port, sigs, _far_why(req.far))

    # 2. the complete named port an interface held before
    for k in unlocked:
        if k in placed:  # step 0 gave it the port of its far device
            continue
        req = ranked[k]
        port = port_before(k)
        if port is not None and not other_device(req, port.name):
            take(k, req.interface_id, port, _signals(req.itype), port_why(req, port))

    # 3. the exact names, as at 2.0.1
    for k, req in enumerate(ranked):
        if k in placed or k in errors:
            continue
        missing = []
        picked: list[tuple[str, str]] = []
        for sig in (s.name for s in req.itype.signals):
            if (req.interface_id, sig) in held:
                continue  # already on its locked pin
            free_pins = [pid for pid in by_signal.get(sig, []) if pid not in used]
            if not free_pins:
                missing.append(sig)
                continue
            before_pin = previous.get((req.interface_id, sig))
            # keep the earlier pin: small diffs; else the first free pin of that name (the last, for last_fit)
            chosen = (
                before_pin if before_pin in free_pins else free_pins[-1 if fit == "last_fit" else 0]
            )
            picked.append((sig, chosen))
            used.add(chosen)
        if missing:
            for _sig, pid in picked:  # all or nothing per interface
                used.discard(pid)
            missing_of[k] = missing
            continue
        owner.update({pid: req.interface_id for _sig, pid in picked})
        placed[k] = [
            (
                sig,
                pid,
                f"pin-allocation: {sig} of {req.interface_id} uses pin {pid} because the pinout of {connector.id} is fixed by the unit design",
            )
            for sig, pid in picked
        ]

    # 4. the first free complete named port
    for k in sorted(missing_of):
        req = ranked[k]
        iid, sigs = req.interface_id, _signals(req.itype)
        cp = found[req.itype.id]
        text = f"{connector.id} has a fixed pinout and no free pin named {', '.join(missing_of[k])}"
        if k in exact_only or not cp.named:
            errors[k] = text
            continue
        port = next(
            (
                x
                for x in cp.usable
                if not other_device(req, x.name) and all(free(x.pin_of(sig)) for sig in sigs)
            ),
            None,
        )
        if port is None:
            left_out = any(other_device(req, x.name) for x in cp.named)
            states = "; ".join(
                f"port {x.name} is named after unit {unit}"
                if (unit := other_device(req, x.name))
                else _port_state(x, owner)
                for x in cp.named
            )
            whom = f" for unit {req.far}" if left_out else ""
            errors[k] = f"{text}, and no free complete {req.itype.name} port{whom} ({states})"
            continue
        take(k, iid, port, sigs, port_why(req, port))

    for k, req in enumerate(ranked):
        if k in errors:
            result.errors.append((req.interface_id, errors[k]))
            continue
        for sig, pid, line in placed[k]:
            result.pins[(req.interface_id, sig)] = pid
            result.reasons.setdefault(pid, []).append(line)
        for sig in (s.name for s in req.itype.signals):
            if (locked_pin := held.get((req.interface_id, sig))) is not None:
                result.pins[(req.interface_id, sig)] = locked_pin
                result.reasons.setdefault(locked_pin, []).append(
                    f"pin-allocation: {sig} of {req.interface_id} stays on pin {locked_pin} because the pin is locked"
                )
    result.port_warnings.extend(_repeated_names(connector, ranked, found, placed, port_of))
    return result


def _port_why(itype: InterfaceType) -> str:
    """The reason of a pin of a named port that no lock chose. Steps 2 and 4 give the same words,
    so a second Generate that keeps every port records the same lines (REQ-GEN-01)."""
    return (
        f"; an interface keeps the port it used before, else takes the first free {itype.name}"
        f" port ({PORT_ORDER_TEXT})"
    )


def _far_why(far: str) -> str:
    """The reason of a pin of the port named after the far device (step 0, and step 2 when the
    port names it): the same words on every Generate, so a second plan is empty (REQ-GEN-01). The
    words reach `generated/generation.json`, so they say *unit*."""
    return f"; the port named after unit {far} at the other end ({FAR_DEVICE_SETTING})"


def _signals(itype: InterfaceType) -> list[str]:
    return [s.name for s in itype.signals]


def _port_state(port: Port, owner: dict[str, str]) -> str:
    """Why a named port could not be used, in a few words."""
    if port.missing:
        return f"port {port.name} has no pin for {', '.join(port.missing)}"
    if port.doubled:
        return f"port {port.name} has more than one pin for {', '.join(port.doubled)}"
    if port.problems:
        return f"port {port.name} is written in more than one way"
    users = sorted({owner[pp.pin_id] for pp in port.pins if pp.pin_id in owner})
    if users:
        return f"port {port.name} is used by {', '.join(users)}"
    return f"port {port.name} has a locked pin"


def _repeated_names(
    connector: Connector,
    ranked: list[Request],
    found: dict[str, ConnectorPorts],
    placed: dict[int, list[tuple[str, str, str]]],
    port_of: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    """`pin_port_unknown`: two or more interfaces of one type need pins whose bare names repeat
    (`TX+` on two pins), so nothing tells which pins form one port. The interfaces that a named
    port placed are not counted."""
    out: list[tuple[str, str]] = []
    for type_id in sorted(found):
        bare = found[type_id].bare
        if bare is None or not bare.doubled:
            continue
        ids = sorted(
            {
                req.interface_id
                for k, req in enumerate(ranked)
                if req.itype.id == type_id
                and not any(port_of[type_id].get(pid) for _s, pid, _w in placed.get(k, []))
            }
        )
        if len(ids) < 2:
            continue
        itype = next(r.itype for r in ranked if r.itype.id == type_id)
        first = _signals(itype)[0]
        out.append(
            (
                connector.id,
                f"{connector.id} has more than one pin named {', '.join(bare.doubled)} for the"
                f" {itype.name} interfaces {', '.join(ids)}: the tool cannot tell which pins form"
                " one port, so each signal takes the first free pin of its name. Name the ports"
                f" (P1_{first}, P2_{first} ...) or lock the pins of each port",
            )
        )
    return out


def groups_of(
    itype: InterfaceType, categories: tuple[str, ...] = DEFAULT_ORDER
) -> list[tuple[str, list[str]]]:
    """Signal groups that must sit together: power as one block, else pairs, else singles."""
    if itype.category in categories:
        return [("power and return grouped", [s.name for s in itype.signals])]
    out: list[tuple[str, list[str]]] = []
    seen: dict[str, int] = {}
    for s in itype.signals:
        if s.pair is None:
            out.append(("single signal", [s.name]))
        elif s.pair in seen:
            out[seen[s.pair]][1].append(s.name)
        else:
            seen[s.pair] = len(out)
            out.append((f"pair {s.pair} on adjacent pins", [s.name]))
    return out


def allocate(
    connector: Connector,
    requests: list[Request],
    previous: dict[tuple[str, str], str],
    gap_pins: int,
    held: dict[tuple[str, str], str] | None = None,
    return_gap: int = 0,
    categories: tuple[str, ...] = DEFAULT_ORDER,
    strategy: str = DEFAULT_STRATEGY,
    far_devices: bool = False,
    units: tuple[str, ...] = (),
) -> Allocation:
    """Allocate pins of `connector` for `requests`. Locked pins (and their signals) are untouched.
    `held` maps (interface, signal) to a locked pin that already carries that signal: it is used
    as it is instead of placing the signal on another pin. `return_gap` unassigned pins are left
    between the signals of a power interface (ECSS-Q-ST-30-11C 6.11.3 a). `strategy` is the model
    that picks the run of pins (`model.pin_fit_strategy`, see STRATEGY_TEXT). `far_devices` and
    `units`: on a fixed pinout, the port named after the far device of a request (`Request.far`)
    first, and never a port named after another of `units` (`naming.far_device_names`, 4.4.0);
    a connector without a fixed pinout reads no name."""
    result = Allocation()
    held = held or {}
    if strategy not in STRATEGIES:
        strategy = DEFAULT_STRATEGY
    if any(p.fixed and p.signal for p in connector.pins):  # even when a released harness holds some
        return _allocate_fixed(
            connector, requests, previous, held, categories, strategy, far_devices, units
        )
    order = [p.id for p in connector.pins]
    index = {pid: k for k, pid in enumerate(order)}
    taken = {p.id for p in connector.pins if p.locked}
    owner = {p.id: p.interface_id or "" for p in connector.pins if p.locked}  # "" = no interface
    power_end = -1  # index of the last pin used by a power group
    power_start = len(order)  # index of the first pin used by a power group (last_fit)
    ranked = sorted(requests, key=lambda r: (_rank(categories, r.itype.category), r.interface_id))

    def place(req: Request, fit: str) -> tuple[bool, bool]:
        """Place every group of one interface by the fit `fit`. Returns (failed, no_room): no_room
        is only true for `spread`, when a group has no run of pins with a free pin on each side."""
        nonlocal power_end, power_start
        is_power = req.itype.category in categories
        down = fit == "last_fit"
        min_start = 0 if is_power or down else (power_end + 1 + gap_pins if power_end >= 0 else 0)
        limit = (
            power_start - gap_pins
            if down and not is_power and power_start < len(order)
            else len(order)
        )  # last_fit: the signals lie below the power group, the gap between them
        note = "" if fit == DEFAULT_STRATEGY else f"; {fit.replace('_', ' ')}"
        for why, signals in groups_of(req.itype, categories):
            for s in [s for s in signals if (req.interface_id, s) in held]:
                pid = held[(req.interface_id, s)]
                if is_power and pid in index:  # a locked power pin counts for the gap as well
                    power_end = max(power_end, index[pid])
                    power_start = min(power_start, index[pid])
                result.pins[(req.interface_id, s)] = pid
                result.reasons.setdefault(pid, []).append(
                    f"pin-allocation: {s} of {req.interface_id} stays on pin {pid} because the pin is locked"
                )
            signals = [s for s in signals if (req.interface_id, s) not in held]
            if not signals:
                continue
            k = len(signals)
            chosen: list[str] | None = None
            reason = ""  # only set when a rule had to be relaxed
            spaced = is_power and return_gap > 0 and k > 1
            stride = 1 + return_gap if spaced else 1
            span = (k - 1) * stride + 1
            old = [previous.get((req.interface_id, s)) for s in signals]
            if all(o is not None and o in index and o not in taken for o in old):
                idxs = [index[o] for o in old if o is not None]
                if (
                    idxs == list(range(idxs[0], idxs[0] + k * stride, stride))
                    and idxs[0] >= min_start
                    and idxs[-1] < limit
                ):
                    chosen = [o for o in old if o is not None]  # kept: small changes, small diffs
                    if spaced:
                        taken.update(order[idxs[0] : idxs[-1] + 1])
                        owner.update(dict.fromkeys(order[idxs[0] : idxs[-1] + 1], req.interface_id))
            if chosen is None:
                for start in starts(min_start, limit, span, down):
                    block = order[start : start + span]
                    if any(b in taken for b in block):
                        continue
                    if fit == "spread" and not apart(start, span, req.interface_id):
                        continue
                    chosen = block[::stride]
                    if spaced:
                        taken.update(block)  # the pins between stay unassigned
                        owner.update(dict.fromkeys(block, req.interface_id))
                    break
            if chosen is None and fit == "spread":
                return False, True
            if chosen is None and spaced:
                result.warnings.append(
                    (
                        req.interface_id,
                        f"{', '.join(signals)} could not be separated by an unassigned contact on {connector.id}",
                    )
                )
                spaced = False
                for start in starts(min_start, limit, k, down):
                    block = order[start : start + k]
                    if not any(b in taken for b in block):
                        chosen = block
                        break
            if chosen is None:
                free = [
                    pid
                    for k2, pid in enumerate(order)
                    if pid not in taken and min_start <= k2 < limit
                ]
                if len(free) >= k:
                    chosen, reason = (
                        free[-k:] if down else free[:k],
                        "no adjacent block was free, so the pins are not adjacent",
                    )
                    result.warnings.append(
                        (
                            req.interface_id,
                            f"{', '.join(signals)} could not be placed on adjacent pins of {connector.id}",
                        )
                    )
                else:
                    result.errors.append(
                        (
                            req.interface_id,
                            f"{connector.id} has too few free pins for {', '.join(signals)} ({len(free)} free, {k} needed)",
                        )
                    )
                    return True, False
            for s, pid in zip(signals, chosen, strict=True):
                taken.add(pid)
                owner[pid] = req.interface_id
                result.pins[(req.interface_id, s)] = pid
                result.reasons.setdefault(pid, []).append(
                    f"pin-allocation: {s} of {req.interface_id} ({why}{'; ' + reason if reason else ''}{note})"
                )
            if is_power:
                power_end = max(power_end, max(index[p] for p in chosen))
                power_start = min(power_start, min(index[p] for p in chosen))
        return False, False

    def apart(start: int, span: int, interface_id: str) -> bool:
        """The pin before and the pin after a run belong to no other interface (spread)."""
        before, after = start - 1, start + span
        return all(
            owner.get(order[j], interface_id) == interface_id
            for j in (before, after)
            if 0 <= j < len(order)
        )

    for req in ranked:
        taken_before, owner_before = set(taken), dict(owner)
        ends_before = (power_end, power_start)
        n_warnings, n_errors = len(result.warnings), len(result.errors)
        for fit in ("spread", "first_fit") if strategy == "spread" else (strategy,):
            failed, no_room = place(req, fit)
            if not failed and not no_room:
                break
            _forget(result, req.interface_id)  # all or nothing per interface
            taken.clear()
            taken.update(taken_before)
            owner.clear()
            owner.update(owner_before)
            power_end, power_start = ends_before
            if no_room:  # no gap fits: first fit, as the model says
                del result.warnings[n_warnings:]
                del result.errors[n_errors:]
                continue
            break
    return result


def starts(low: int, limit: int, span: int, down: bool) -> range:
    """The first indexes a run of `span` pins can start at, in the order a fit looks at them:
    from `low` up, or from the last place that fits down. `limit` is one past the last pin the run
    may use."""
    last = limit - span
    return range(last, low - 1, -1) if down else range(low, last + 1)


def _forget(result: Allocation, interface_id: str) -> None:
    """Take every pin of one interface out of the result again (its other pins stay free)."""
    for key in [k for k in result.pins if k[0] == interface_id]:
        pid = result.pins.pop(key)
        if pid in result.reasons:
            result.reasons[pid] = [
                line for line in result.reasons[pid] if f" of {interface_id} " not in line
            ]
            if not result.reasons[pid]:
                del result.reasons[pid]
