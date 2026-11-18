# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Segmentation: which interfaces share a harness. Rules come from the `segmentation` and
`segregation` configuration (DECISIONS D-10: one harness per pair of unit connectors when a file
names no mode; D-247: since 2.4.0 a new project starts in `per_connector_group`).

The mode `per_connector_group` (2.3.0, D-243) first makes the groups of `per_connector_pair` and
then joins those that plug into one device connector into one harness that branches
(`docs/ait/DESIGN_2.3_BRANCHING.md` section 5.1). In the three modes of 2.2 the groups are made by
the code of 2.2 (`tests/reference/segmentation_220.py`). A project in a mode keeps it: every
project the tool wrote names its mode, so D-247 switches none of them; a file that names no mode
or one this version does not know is read as `per_connector_pair`, as by every version before."""

from collections import deque
from dataclasses import dataclass, field, replace

from harness_design_studio.core.model import Endpoint, InterfaceInstance, Project

GROUP_MODE = "per_connector_group"
MODES = ("per_connector_pair", "per_unit_pair", "per_zone_pair", GROUP_MODE)
# The mode of a new project (the blank example, `samples.start_project`, the editor's New project;
# owner decision of 2026-11-18, D-247: most connectors are custom, so one device connector often
# carries interfaces to several devices, and one plug on it is what gets built). It is not the
# default of the registry (`core.settings`): a file that names no mode, or one that is not one of
# `MODES`, is read as `MODES[0]`, so every project groups as it did at 2.2
# (`tests/test_segmentation_compat_220.py`).
NEW_PROJECT_MODE = GROUP_MODE
MAX_END_NAMES = 3  # the connectors of one end named in the name of a joined harness


@dataclass(frozen=True)
class Group:
    key: str
    mode: str
    chain: str
    interface_ids: tuple[str, ...]
    label: str  # human name of the harness, e.g. "OBC to RW1"
    zones: tuple[str, str] | None = None  # only for per_zone_pair
    # only for per_connector_group: (device connector, "X" or "Y") for each connector of the group,
    # the end of the harness it is on (not a field of any file)
    sides: tuple[tuple[str, str], ...] | None = None

    def side_of(self) -> dict[str, str]:
        return dict(self.sides or ())


@dataclass(frozen=True)
class Ring:
    """Device connectors of one chain joined by interfaces that cannot be the two ends of one trunk
    (an odd ring): their `per_connector_pair` groups stay separate harnesses (`branch_not_built`)."""

    chain: str
    connectors: tuple[str, ...]  # the connectors of the ring that closes it, in natural order
    group_keys: tuple[str, ...]  # the groups that stay separate

    @property
    def message(self) -> str:
        return (
            f"{words(list(self.connectors))} are wired in a ring, so one harness cannot run them as "
            "two ends of one trunk. They stay separate harnesses; draw the harness to join them."
        )


@dataclass
class Skipped:
    interface_id: str
    reason: str
    severity: str = "warning"


@dataclass
class Segmentation:
    groups: list[Group] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)
    mode: str = "per_connector_pair"
    notes: list[str] = field(default_factory=list)
    rings: list[Ring] = field(default_factory=list)  # per_connector_group only


def words(items: list[str]) -> str:
    """`A`, `A and B`, `A, B and C`."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _esc(name: str) -> str:
    """Zone names may contain the key separator; escape so two different pairs never collide."""
    return name.replace("%", "%25").replace("|", "%7C")


def _cfg(project: Project, name: str) -> dict[str, object]:
    c = project.config.get(name)
    return dict(c.values) if c is not None else {}


def _category_classes(sep: dict[str, object]) -> dict[str, str]:
    """Class of every category named in `category_pairs_to_separate`: the pairs are coloured greedily
    (sorted names), so only the listed pairs end in different classes. Colour 0 is "main"."""
    pairs = sep.get("category_pairs_to_separate")
    if not isinstance(pairs, list):
        return {}
    edges = [sorted(map(str, p)) for p in pairs if isinstance(p, list) and len(p) == 2]
    colour: dict[str, int] = {}
    for cat in sorted({c for e in edges for c in e}):
        taken = {colour[o] for e in edges if cat in e for o in e if o != cat and o in colour}
        colour[cat] = next(n for n in range(len(colour) + 1) if n not in taken)
    members = {n: sorted(c for c, k in colour.items() if k == n) for n in set(colour.values())}
    return {c: "main" if k == 0 else "cat-" + "+".join(members[k]) for c, k in colour.items()}


def _class_of(
    project: Project, i: InterfaceInstance, seg: dict[str, object], sep: dict[str, object]
) -> str:
    cat = project.interface_types[i.type_id].category
    if cat == "pyro" and sep.get("forbid_pyro_with_other") in (None, True):
        return "pyro"
    return _category_classes(sep).get(cat, "main")


def orient(
    project: Project, i: InterfaceInstance, mode: str, zones: tuple[str, str] | None
) -> tuple[Endpoint, Endpoint]:
    """Order the two endpoints so every interface of a group agrees on which end is X."""
    a, b = i.endpoints[0], i.endpoints[1]
    if mode == "per_connector_pair":
        return (a, b) if (a.connector_id or "") <= (b.connector_id or "") else (b, a)
    if mode == "per_unit_pair" or zones is None or zones[0] == zones[1]:
        return (a, b) if a.unit_id <= b.unit_id else (b, a)
    za = project.units[a.unit_id].zone or ""
    return (a, b) if za == zones[0] else (b, a)


def mode_of(project: Project) -> str:
    """The segmentation mode in force: the one set, or the default when it is not one of `MODES`."""
    mode = str(_cfg(project, "segmentation").get("mode", MODES[0]))
    return mode if mode in MODES else MODES[0]


def segment(project: Project) -> Segmentation:
    seg_cfg = _cfg(project, "segmentation")
    sep_cfg = _cfg(project, "segregation")
    mode = str(seg_cfg.get("mode", "per_connector_pair"))
    result = Segmentation(mode=mode if mode in MODES else "per_connector_pair")
    if mode not in MODES:
        result.notes.append(f"segmentation.mode '{mode}' is not known; using per_connector_pair")
    buckets: dict[str, list[str]] = {}
    zone_pairs: dict[str, tuple[str, str]] = {}
    classes: dict[str, dict[str, list[str]]] = {}
    labels: dict[str, str] = {}
    chains: dict[str, str] = {}
    manual = {
        w.interface_id
        for h in project.harnesses.values()
        if not h.generated
        for w in h.wires
        if w.interface_id
    }
    for i in sorted(project.interfaces.values(), key=lambda x: x.id):
        if i.id in manual:
            result.skipped.append(Skipped(i.id, "it is already routed by a manual harness", "info"))
            continue
        if i.type_id not in project.interface_types:
            result.skipped.append(Skipped(i.id, "its interface type does not exist", "error"))
            continue
        if len(i.endpoints) > 2:
            result.skipped.append(
                Skipped(i.id, "multi-drop interfaces (more than two devices) are not generated yet")
            )
            continue
        if len(i.endpoints) != 2:
            n = len(i.endpoints)
            result.skipped.append(
                Skipped(i.id, f"it has {n} {'end' if n == 1 else 'ends'} and needs two")
            )
            continue
        names = [s.name for s in project.interface_types[i.type_id].signals]
        dup = sorted({n for n in names if names.count(n) > 1})
        if dup:
            result.skipped.append(
                Skipped(
                    i.id,
                    f"its interface type {i.type_id} lists the signal name {', '.join(dup)} more than once",
                    "error",
                )
            )
            continue
        a, b = i.endpoints
        if any(e.unit_id not in project.units for e in i.endpoints):
            result.skipped.append(Skipped(i.id, "a device of this interface does not exist"))
            continue
        if a.connector_id is None or b.connector_id is None:
            result.skipped.append(Skipped(i.id, "a connector has not been chosen on every end"))
            continue
        if a.connector_id not in project.connectors or b.connector_id not in project.connectors:
            result.skipped.append(Skipped(i.id, "a connector of this interface does not exist"))
            continue
        if a.connector_id == b.connector_id:
            result.skipped.append(
                Skipped(i.id, f"both ends are on the same connector ({a.connector_id})", "error")
            )
            continue
        # with forbid_nominal_with_redundant off, the two chains may share a harness
        keep_chains = sep_cfg.get("forbid_nominal_with_redundant") is not False
        chain = i.redundancy if keep_chains else ""
        cls = _class_of(project, i, seg_cfg, sep_cfg)
        ua, ub = sorted([a.unit_id, b.unit_id])
        za, zb = sorted([project.units[a.unit_id].zone or "", project.units[b.unit_id].zone or ""])
        if result.mode in ("per_connector_pair", GROUP_MODE):
            ca, cb = sorted([a.connector_id, b.connector_id])
            key, label = f"cp|{chain}|{ca}|{cb}", f"{ca} to {cb}"
        elif result.mode == "per_unit_pair":
            key, label = f"up|{chain}|{cls}|{ua}|{ub}", f"{ua} to {ub}"
        else:
            key, label = (
                f"zp|{chain}|{cls}|{_esc(za)}|{_esc(zb)}",
                f"{za or 'no zone'} to {zb or 'no zone'}",
            )
            zone_pairs[key] = (za, zb)
        if cls != "main":
            label += f" ({cls.removeprefix('cat-')})"
        if chain == "redundant":
            label += " (redundant)"
        buckets.setdefault(key, []).append(i.id)
        classes.setdefault(key, {}).setdefault(cls, []).append(i.id)
        labels[key] = label
        chains[key] = chain
    base_mode = "per_connector_pair" if result.mode == GROUP_MODE else result.mode
    for key in sorted(buckets):
        result.groups.append(
            Group(
                key, base_mode, chains[key], tuple(buckets[key]), labels[key], zone_pairs.get(key)
            )
        )
        if len(classes[key]) > 1:
            parts = "; ".join(f"{c}: {', '.join(ids)}" for c, ids in sorted(classes[key].items()))
            result.notes.append(
                f"{labels[key]} mixes interface classes ({parts}). In this mode they share a "
                "harness because they use the same pair of device connectors; give the separated "
                "class its own connector, or segment per device pair or per zone pair."
            )
    if result.mode == GROUP_MODE:
        result.groups, result.rings = _join(project, result.groups)
    return result


# ---- per_connector_group: the join of the groups of per_connector_pair -----------------------


def _natural(connector_id: str) -> tuple[object, ...]:
    from harness_design_studio.core.links import natural_key

    return (natural_key(connector_id), connector_id)


def _ends(g: Group) -> tuple[str, str]:
    """The two device connectors of a `per_connector_pair` group (its key: cp|chain|A|B)."""
    _cp, _chain, a, b = g.key.split("|")
    return a, b


def _released(project: Project) -> dict[str, tuple[str, str]]:
    """Interface -> (ID, group key) of the released harness Generate made that carries it, the
    lowest ID first. Such a harness is never taken over (B6), so its interfaces are not joined."""
    from harness_design_studio.core.vcs.snapshot import carried_interfaces

    out: dict[str, tuple[str, str]] = {}
    for h in sorted(project.harnesses.values(), key=lambda x: x.id):
        if h.generated and h.status == "released":
            for iid in sorted(carried_interfaces(h)):
                out.setdefault(iid, (h.id, h.group_key or ""))
    return out


def _colour(groups: list[Group]) -> tuple[dict[str, str], tuple[str, ...]]:
    """Two-colour the connectors of one connected candidate by a walk in breadth from its first
    connector in natural ID order (end X), neighbours in the same order. Returns the side of each
    connector and, when two connectors of one side are joined, the ring that closes it."""
    adj: dict[str, set[str]] = {}
    for g in groups:
        a, b = _ends(g)
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    first = min(adj, key=_natural)
    side = {first: "X"}
    parent: dict[str, str] = {}
    todo = deque([first])
    while todo:
        u = todo.popleft()
        for v in sorted(adj[u], key=_natural):
            if v not in side:
                side[v] = "Y" if side[u] == "X" else "X"
                parent[v] = u
                todo.append(v)
            elif side[v] == side[u]:
                return side, _cycle(parent, u, v)
    return side, ()


def _cycle(parent: dict[str, str], u: str, v: str) -> tuple[str, ...]:
    """The connectors of the ring that the edge u-v closes in the tree of the walk."""

    def up(x: str) -> list[str]:
        path = [x]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        return path

    pu, pv = up(u), up(v)
    common = next(x for x in pu if x in set(pv))
    ring = pu[: pu.index(common) + 1] + pv[: pv.index(common)]
    return tuple(sorted(ring, key=_natural))


def _components(groups: list[Group]) -> list[list[Group]]:
    """The connected parts of the graph with a node per device connector and an edge per group, each
    with its groups in key order; the parts in the natural order of their first connector."""
    root: dict[str, str] = {}

    def find(x: str) -> str:
        while root.setdefault(x, x) != x:
            root[x] = root[root[x]]
            x = root[x]
        return x

    for g in groups:
        a, b = _ends(g)
        ra, rb = find(a), find(b)
        if ra != rb:
            root[max(ra, rb, key=_natural)] = min(ra, rb, key=_natural)
    parts: dict[str, list[Group]] = {}
    for g in groups:
        parts.setdefault(find(_ends(g)[0]), []).append(g)
    return [parts[k] for k in sorted(parts, key=_natural)]


def end_names(connectors: list[str]) -> str:
    """The connectors of one end of a joined harness for its name: at most three, then *and N more*."""
    shown = connectors[:MAX_END_NAMES]
    more = len(connectors) - len(shown)
    return " + ".join(shown) + (f" and {more} more" if more else "")


def _joined(chain: str, part: list[Group], side: dict[str, str], key: str) -> Group:
    ends = {s: sorted((c for c, k in side.items() if k == s), key=_natural) for s in ("X", "Y")}
    label = f"{end_names(ends['X'])} to {end_names(ends['Y'])}"
    if chain == "redundant":
        label += " (redundant)"
    return Group(
        key,
        GROUP_MODE,
        chain,
        tuple(sorted(i for g in part for i in g.interface_ids)),
        label,
        None,
        tuple(sorted(side.items())),
    )


def _join(project: Project, pairs: list[Group]) -> tuple[list[Group], list[Ring]]:
    """Join the `per_connector_pair` groups that plug into one device connector (section 5.1):
    per chain, each connected part of the graph of connectors whose connectors fall on two sides is
    one group `cg|<chain>|<first connector>`; a part of one group stays that group (key `cp|...`);
    a ring stays as its groups and is reported. A group with an interface that a released harness
    carries is not joined; the groups of a released joined harness are given its key again, so that
    Generate leaves it as it is."""
    released = _released(project)
    held: dict[str, list[Group]] = {}  # the key of a released joined harness -> its groups
    out: list[Group] = []
    rings: list[Ring] = []
    free: dict[str, list[Group]] = {}
    for g in pairs:
        owner = next((released[i] for i in g.interface_ids if i in released), None)
        if owner is None:
            free.setdefault(g.chain, []).append(g)
        elif owner[1].startswith("cg|"):
            held.setdefault(owner[1], []).append(g)
        else:
            out.append(g)
    taken = {key for _hid, key in released.values()}
    for key, groups in held.items():
        side, ring = _colour(groups)
        joined = _joined(groups[0].chain, groups, side, key)
        # never built (released), so a ring that its interfaces close today only loses the sides
        out.append(replace(joined, sides=None) if ring else joined)
    for chain in sorted(free):
        for part in _components(free[chain]):
            if len(part) == 1:
                out.append(part[0])
                continue
            side, ring = _colour(part)
            if ring:
                rings.append(Ring(chain, ring, tuple(g.key for g in part)))
                out.extend(part)
                continue
            first = min(side, key=_natural)
            key = f"cg|{chain}|{first}"
            if key in taken:  # a released joined harness has this key: never take it over
                key += "|" + min(i for g in part for i in g.interface_ids)
            out.append(_joined(chain, part, side, key))
    return sorted(out, key=lambda g: g.key), rings


def join_text(project: Project, group: Group) -> str:
    """Why the interfaces of a joined group share a harness, for the generation record and
    `explain`: the connectors they share, the mode and the two ends."""
    count: dict[str, int] = {}
    for iid in group.interface_ids:
        i = project.interfaces.get(iid)
        for e in i.endpoints if i is not None else []:
            if e.connector_id is not None:
                count[e.connector_id] = count.get(e.connector_id, 0) + 1
    shared = sorted((c for c, n in count.items() if n > 1), key=_natural)
    side = group.side_of()
    ends = {s: sorted((c for c, k in side.items() if k == s), key=_natural) for s in ("X", "Y")}
    return (
        f"{words(list(group.interface_ids))} share a harness because they plug into "
        f"{words(shared) if shared else 'connectors joined by interfaces'}; mode {GROUP_MODE}; "
        f"ends X: {', '.join(ends['X'])}, Y: {', '.join(ends['Y'])}"
    )
