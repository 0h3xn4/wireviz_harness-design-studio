# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The electrical design rules of 4.2.0: twisted pairs and shielded signals (milestone E2).

The design is `docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md` (decision D-258, proposed): one part per
rule, sections 3 and 4 here. The checks read fields that format 4 has (`SignalDef.pair`, the
construction and shielding of an interface type, `ShieldGroup`, the signals of the pins) and one
setting, `config/naming.json` `pair_suffixes`; they change nothing.

  pair-untwisted     two wires of a signal pair that no twisted pair, shielded pair or quad holds
  signal-unshielded  a wire of a harness Generate did not make whose signal every interface type
                     that has it shields, in no shield

The rules are `ELECTRICAL_RULES`, with the texts of the design. They are not in the registry
`rules.RULES` yet (pull request 4 of the design registers them), so `check`, `drc` and every written
file are as before; the tests call them directly.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from harness_design_studio.core import settings
from harness_design_studio.core.configcheck import (
    PAIR_SUFFIXES_FILE,
    PAIR_SUFFIXES_KEY,
    pair_suffixes_problem,
)
from harness_design_studio.core.model import (
    Connector,
    Harness,
    InterfaceType,
    Pin,
    Project,
    Wire,
)
from harness_design_studio.core.ports import natural_key, read_signal

from .base import Hit, Rule, cfg

# A group of these kinds twists the wires it holds together (section 3.1); an overall shield and a
# coax do not.
TWISTING_KINDS = ("twisted_pair", "shielded_pair", "quad")
# A group of these kinds is a shield over the wires it holds (section 4.1, as the verifier counts
# every group that is not a twisted pair).
SHIELDING_KINDS = ("shielded_pair", "overall_shield", "coax", "quad")

# How a type asks for a shield, in the order a finding names them.
OVERALL, PER_PAIR, COAX = "overall", "per pair", "as a coax"
_WAYS = (OVERALL, PER_PAIR, COAX)


# ---- the ends of a wire and the interface types of their signals -----------------------------------


@dataclass(frozen=True)
class End:
    """The pin whose signal a wire end carries: the pin of the device connector the cable connector
    plugs into when it has a signal, else the cable connector's own pin (`rules._end_signal`)."""

    connector: Connector
    pin: Pin

    @property
    def signal(self) -> str:
        return self.pin.signal or ""


def signal_end(project: Project, h: Harness, connector_id: str, pin_id: str) -> End | None:
    """The end of a wire on `connector_id`/`pin_id` of `h`, or None when no pin there has a signal."""
    cable = next((c for c in h.connectors if c.id == connector_id), None)
    if cable is None:
        return None
    box = project.connectors.get(cable.mates_with or "")
    for conn in (box, cable):
        pin = next((p for p in conn.pins if p.id == pin_id), None) if conn else None
        if conn is not None and pin is not None and pin.signal:
            return End(conn, pin)
    return None


def _in_type(pin: Pin, t: InterfaceType) -> str | None:
    """The signal of type `t` that the pin carries: its own name when the type has it, else, for a
    fixed pin named for a port (`RS422_2_TX+`), the one signal its name reads as (`core/ports.py`,
    D-237, as `rules._type_signal` reads it); None when the type has no such signal."""
    names = [s.name for s in t.signals]
    if pin.signal in names:
        return pin.signal
    if pin.fixed and pin.signal:
        found = read_signal(pin.signal, names)
        if len(found) == 1:
            return found[0].signal
    return None


def signal_types(project: Project, end: End) -> list[tuple[InterfaceType, str]]:
    """The interface types of the signal at an end, each with the signal of that type, in ID order:
    the type of the pin's interface when the pin has one (as `devices.derive_meaning_types`), else
    every type that has the signal, narrowed by the connector's `carries` when that leaves any."""
    iface = project.interfaces.get(end.pin.interface_id or "")
    if iface is not None and iface.type_id in project.interface_types:
        t = project.interface_types[iface.type_id]
        s = _in_type(end.pin, t)
        return [(t, s)] if s else []
    found = [
        (t, s)
        for t in sorted(project.interface_types.values(), key=lambda x: x.id)
        if (s := _in_type(end.pin, t))
    ]
    if end.connector.carries:
        narrowed = [(t, s) for t, s in found if t.id in end.connector.carries]
        found = narrowed or found
    return found


def _pair_in(t: InterfaceType, signal: str) -> str | None:
    return next((s.pair for s in t.signals if s.name == signal), None)


def _and(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _wire_order(w: Wire) -> tuple[object, ...]:
    return natural_key(w.id)


# ---- pair-untwisted (section 3) ------------------------------------------------------------------


def pair_suffixes(project: Project) -> tuple[tuple[str, str], ...]:
    """The endings that make two names a pair: `naming.pair_suffixes` when it is set and valid, the
    registry's default when it is not set, and none while a value is refused (`config-invalid`
    says why; the tool does not guess a table in its place)."""
    raw = cfg(project, PAIR_SUFFIXES_FILE).get(PAIR_SUFFIXES_KEY)
    if raw is None:
        raw = settings.effective(project, PAIR_SUFFIXES_FILE, PAIR_SUFFIXES_KEY).value
        rows = [list(r) for r in raw] if isinstance(raw, list | tuple) else []
    elif pair_suffixes_problem(raw) is not None:
        return ()
    else:
        rows = raw if isinstance(raw, list) else []
    return tuple((str(a), str(b)) for a, b in rows)


def name_pair(a: str, b: str, suffixes: Sequence[tuple[str, str]]) -> str | None:
    """The name the two signals share when they differ only by the two endings of a row
    (`1PPS+` and `1PPS-` give `1PPS`), compared exactly; None when they do not, or when nothing is
    left in front of the endings."""
    for x, y in suffixes:
        for p, q in ((x, y), (y, x)):
            if a.endswith(p) and b.endswith(q):
                base = a[: -len(p)]
                if base and base == b[: -len(q)]:
                    return base
    return None


@dataclass(frozen=True)
class Basis:
    """Why two signals are a pair: the pair names and the interface types that give them, or no
    type and the name the two signals share (`by_names`)."""

    names: tuple[str, ...]
    types: tuple[str, ...]
    by_names: bool


def _types_pair(
    project: Project,
    ta: list[tuple[InterfaceType, str]],
    tb: list[tuple[InterfaceType, str]],
    sa: str,
    sb: str,
    suffixes: Sequence[tuple[str, str]],
) -> Basis | None:
    """Two ends are a pair when every type that has both signals gives them one pair, or, when no
    type has both, when their names differ only by the endings of a row (section 3.1, rule 2)."""
    a = {t.id: s for t, s in ta}
    b = {t.id: s for t, s in tb}
    common = sorted(set(a) & set(b))
    if common:
        names: set[str] = set()
        for tid in common:
            t = project.interface_types[tid]
            pa, pb = _pair_in(t, a[tid]), _pair_in(t, b[tid])
            if a[tid] == b[tid] or pa is None or pa != pb:
                return None
            names.add(pa)
        return Basis(tuple(sorted(names)), tuple(common), False)
    base = name_pair(sa, sb, suffixes)
    return Basis((base,), (), True) if base is not None else None


@dataclass(frozen=True)
class SignalPair:
    """Two wires of one harness that are a signal pair, and what makes them one: the interface type
    of their interface (`source` "interface"), the types of the signals at their ends ("types") or
    their names ("names"). `signals` are those of the end where the pair was found."""

    harness: str
    a: Wire
    b: Wire
    signals: tuple[str, str]
    source: str
    basis: Basis

    @property
    def key(self) -> str:
        return f"{self.harness}.{self.a.id}+{self.b.id}"


def _with_interface(project: Project, w: Wire) -> InterfaceType | None:
    i = project.interfaces.get(w.interface_id or "")
    return project.interface_types.get(i.type_id) if i is not None else None


def _interface_pairs(project: Project, h: Harness, wires: list[Wire]) -> Iterator[SignalPair]:
    """Rule 1: the wires of one interface whose signals (up to `/`, as `shields.plan` reads them)
    have one `pair` in the type and that run from the same connector to the same connector (Generate
    makes a pair of each pair of the type for each direction of the wires, `shields.plan`); exactly
    two make a pair."""
    groups: dict[tuple[str, str, str, str, str], list[tuple[Wire, str]]] = {}
    for w in wires:
        t = _with_interface(project, w)
        src = (w.signal or "").split("/")[0]
        pair = _pair_in(t, src) if t is not None else None
        if t is not None and pair is not None:
            key = (w.interface_id or "", t.id, pair, w.from_connector, w.to_connector)
            groups.setdefault(key, []).append((w, src))
    for (_iid, tid, pair, _a, _b), members in groups.items():
        if len(members) != 2 or members[0][1] == members[1][1]:
            continue
        (a, sa), (b, sb) = sorted(members, key=lambda m: _wire_order(m[0]))
        yield SignalPair(h.id, a, b, (sa, sb), "interface", Basis((pair,), (tid,), False))


def _drawn_pairs(project: Project, h: Harness, wires: list[Wire]) -> Iterator[SignalPair]:
    """Rule 2: two wires without an interface that join the same two connectors and, at each of the
    two where both have a signal, carry two signals that are a pair; a wire that could pair with two
    others at one connector is in no pair (a base name shared by three wires, section 3.3)."""
    suffixes = pair_suffixes(project)
    by_ends: dict[frozenset[str], list[Wire]] = {}
    for w in wires:
        ends = frozenset((w.from_connector, w.to_connector))
        if len(ends) == 2:
            by_ends.setdefault(ends, []).append(w)
    types_at: dict[tuple[str, str], list[tuple[InterfaceType, str]]] = {}

    def types(end: End) -> list[tuple[InterfaceType, str]]:
        k = (end.connector.id, end.pin.id)
        if k not in types_at:
            types_at[k] = signal_types(project, end)
        return types_at[k]

    for ends, group in by_ends.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=_wire_order)
        connectors = sorted(ends, key=natural_key)
        at: dict[str, dict[str, End]] = {c: {} for c in connectors}
        for w in group:
            for cid, pid in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin)):
                end = signal_end(project, h, cid, pid)
                if end is not None:
                    at[cid][w.id] = end
        found: dict[str, dict[tuple[str, str], Basis]] = {c: {} for c in connectors}
        partners: dict[str, dict[str, int]] = {c: {} for c in connectors}
        for c in connectors:
            here = [w for w in group if w.id in at[c]]
            for i, wa in enumerate(here):
                for wb in here[i + 1 :]:
                    ea, eb = at[c][wa.id], at[c][wb.id]
                    basis = _types_pair(
                        project, types(ea), types(eb), ea.signal, eb.signal, suffixes
                    )
                    if basis is not None:
                        found[c][(wa.id, wb.id)] = basis
                        for x in (wa.id, wb.id):
                            partners[c][x] = partners[c].get(x, 0) + 1
        wire = {w.id: w for w in group}
        candidates = sorted(
            {k for c in connectors for k in found[c]},
            key=lambda k: (natural_key(k[0]), natural_key(k[1])),
        )
        for ia, ib in candidates:
            both = [c for c in connectors if ia in at[c] and ib in at[c]]
            if not all(
                (ia, ib) in found[c] and partners[c][ia] == 1 and partners[c][ib] == 1 for c in both
            ):
                continue
            first = both[0]
            basis = found[first][(ia, ib)]
            signals = (at[first][ia].signal, at[first][ib].signal)
            source = "names" if basis.by_names else "types"
            yield SignalPair(h.id, wire[ia], wire[ib], signals, source, basis)


def signal_pairs(project: Project, h: Harness) -> list[SignalPair]:
    """The signal pairs of a harness (section 3.1), sorted by their first and second wire: the wires
    with an interface paired by the interface's type, the others by the types of the signals at
    their ends or by their names."""
    with_type = [w for w in h.wires if _with_interface(project, w) is not None]
    without = [w for w in h.wires if _with_interface(project, w) is None]
    pairs = [*_interface_pairs(project, h, with_type), *_drawn_pairs(project, h, without)]
    return sorted(pairs, key=lambda p: (_wire_order(p.a), _wire_order(p.b)))


def twisted(h: Harness, a: str, b: str) -> bool:
    """One twisted pair, shielded pair or quad holds both wires (section 3.1)."""
    return any(g.kind in TWISTING_KINDS and a in g.wire_ids and b in g.wire_ids for g in h.shields)


def _pair_title(p: SignalPair) -> str:
    sa, sb = p.signals
    head = f"Wires {p.a.id} ({sa}) and {p.b.id} ({sb}) in {p.harness} are"
    if p.source == "names":
        return f"{head} a pair by their names but are not twisted together"
    names = _and(list(p.basis.names))
    word = "type" if len(p.basis.types) == 1 else "types"
    return (
        f"{head} pair {names} of the interface {word} {_and(list(p.basis.types))} but are not "
        "twisted together"
    )


def _pair_untwisted(project: Project) -> Iterator[Hit]:
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        for p in signal_pairs(project, h):
            if not twisted(h, p.a.id, p.b.id):
                yield Hit(p.a.id, _pair_title(p), key=p.key)


# ---- signal-unshielded (section 4) ---------------------------------------------------------------


def _asks(t: InterfaceType, signal: str) -> str:
    """How the type asks for a shield for the signal (`as a coax`, `overall`, `per pair`), or ""
    when it does not: as Generate and the verifier read a type (a twisted shielded pair whose
    shielding is none asks for nothing)."""
    if t.construction == "coax":
        return COAX
    if t.shielding == "overall":
        return OVERALL
    if t.shielding == "per_pair" and _pair_in(t, signal) is not None:
        return PER_PAIR
    return ""


@dataclass(frozen=True)
class ShieldAsk:
    """What the interface types at the ends of a wire say about its shield: the signal named, the
    types with the way each asks ("" when one does not) and whether the wire asks for a shield."""

    signal: str
    types: tuple[tuple[str, str], ...]

    @property
    def asked(self) -> bool:
        return bool(self.types) and all(way for _t, way in self.types)


def shield_asked(project: Project, h: Harness, w: Wire) -> ShieldAsk:
    """Whether a wire asks for a shield (section 4.1, A-SHIELD-BY-TYPE): the types of the signal at
    each end, and a shield asked when there is at least one and every one of them asks. The signal
    named is that of the first end (from, then to) whose signal a type has."""
    by_type: dict[str, str] = {}
    signal = ""
    for cid, pid in ((w.from_connector, w.from_pin), (w.to_connector, w.to_pin)):
        end = signal_end(project, h, cid, pid)
        if end is None:
            continue
        found = signal_types(project, end)
        if found and not signal:
            signal = end.signal
        for t, s in found:
            way = _asks(t, s)
            # a type met at both ends asks only if it asks for both signals
            by_type[t.id] = way if by_type.get(t.id, way) == way else ""
    return ShieldAsk(signal, tuple(sorted(by_type.items())))


def shielded(h: Harness, wire_id: str) -> bool:
    """A shielded pair, an overall shield, a coax or a quad holds the wire (section 4.1)."""
    return any(g.kind in SHIELDING_KINDS and wire_id in g.wire_ids for g in h.shields)


def _unshielded_title(h: Harness, w: Wire, ask: ShieldAsk) -> str:
    types = [t for t, _way in ask.types]
    ways = [way for way in _WAYS if any(x == way for _t, x in ask.types)]
    word, verb = ("type", "shields") if len(types) == 1 else ("types", "shield")
    pairs = sorted(
        (g.id for g in h.shields if g.kind == "twisted_pair" and w.id in g.wire_ids),
        key=natural_key,
    )
    tail = ""
    if pairs:
        tail = f" (it is in twisted pair{'s' if len(pairs) > 1 else ''} {_and(pairs)})"
    return (
        f"Wire {w.id} in {h.id} carries {ask.signal}, which the interface {word} {_and(types)} "
        f"{verb} ({_and(ways)}), but is in no shield{tail}"
    )


def _signal_unshielded(project: Project) -> Iterator[Hit]:
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        if h.generated:
            continue  # the verifier judges the shields of a generated harness (shield_missing)
        for w in sorted(h.wires, key=_wire_order):
            if shielded(h, w.id):
                continue
            ask = shield_asked(project, h, w)
            if ask.asked:
                yield Hit(w.id, _unshielded_title(h, w, ask), key=f"{h.id}.{w.id}")


# ---- the rules (sections 3.2 and 4.2) ----------------------------------------------------------
#
# Not spliced into `rules.RULES` yet: pull request 4 of the design puts them after
# `direction-conflict`, so the report keeps the signals together.

ELECTRICAL_RULES: tuple[Rule, ...] = (
    Rule("pair-untwisted", "warning", "Twisted pairs",
         "Two wires of a signal pair that are not twisted together pick up noise and radiate it.",
         "Select the two wires and use Group wires (twisted pair, or shielded pair if the signal needs a shield); for a harness Generate made, give the interface type a twisted construction and generate again.",
         _pair_untwisted),
    Rule("signal-unshielded", "warning", "Shielded signals",
         "A signal that its interface type shields picks up and radiates noise when its wire runs without a shield.",
         "Put the wire into a shielded pair, an overall shield or a coax (Group wires; Change group... for a wire in a twisted pair).",
         _signal_unshielded),
)  # fmt: skip
