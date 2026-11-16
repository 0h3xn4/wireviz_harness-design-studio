# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""IDs that two Git branches both made (M7b, D-231): the part of `merge-fix` that renames one side.

A harness gets the first free number of the naming pattern (`W005`) and a link the first free
`L<n>`. Two people who each make a harness or a link on their own branch get the same ID with
different content. Git then stops on the files: a harness lives in `physical/harnesses/<id>.json`,
so both branches added that file (Git's "add/add"); a link lives in the one list
`logical/links.json`, where both added an entry with the same ID at the same place. `plan_id_fix`
works out the way out, and writes nothing:

* a harness file that **both branches added** (the index has stages 2 and 3 and no 1) with
  different content: this branch's harness keeps the ID, the other branch's gets the next free ID of
  the naming pattern, and so do the IDs inside it that start with the old ID (`W005-P1`, `W005-001`
  become `W006-P1`, `W006-001`). With the same content on both sides it is kept once, nothing is
  renamed.
* `logical/links.json`, `waivers.json` and `diagram/marks.json` in conflict: merged entry by entry
  against the version both branches started from (stage 1, read from Git's object store); a link
  that both branches added with different content: the other branch's gets the next free `L<n>`.
  An entry that both branches changed in different ways is a real conflict, not an ID collision:
  refused.
* every entry of the other branch that names a renamed ID (a link that made the harness, the place
  of a loose end `pos:<connector>`, the label marks of a link, a waiver or a deviation) is changed
  to the new ID. Which branch an entry comes from is read from Git: it is this branch's when the
  commit of `HEAD` holds it as it is.

It refuses (`IdFix.problem`) and nothing is written when a harness that would be renamed has a
release history (not a draft on either branch, a baseline, a change-log entry or an as-built record
naming it: released IDs never change), when a link that would be renamed is in a baseline, when both
branches let Generate make a harness for the same group (the same connectors, devices or zones), or
when Git's records cannot be read.

No Qt, no `git` program (`core/vcs/gitobjects.py`), no network.
"""

import copy
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harness_design_studio.core.checks import finding_id
from harness_design_studio.core.io import canonical
from harness_design_studio.core.io.layout import DIAGRAM_MARKS_FILE, harness_bytes, list_bytes
from harness_design_studio.core.model import Harness, Link, Project, Waiver
from harness_design_studio.core.model.base import Entity
from harness_design_studio.core.model.review import DiagramMark
from harness_design_studio.core.vcs import gitobjects

__all__ = ["IdFix", "Rename", "handles", "plan_id_fix"]

HARNESS_FILE = re.compile(r"^physical/harnesses/([^/]+)\.json$")
LINKS_FILE = "logical/links.json"
WAIVERS_FILE = "waivers.json"
MARKS_FILE = DIAGRAM_MARKS_FILE
_LISTS: dict[str, tuple[str, type[Entity], str]] = {
    LINKS_FILE: ("links", Link, "link"),
    WAIVERS_FILE: ("waivers", Waiver, "waiver"),
    MARKS_FILE: ("marks", DiagramMark, "diagram mark"),
}
_CHILD_LISTS = (
    "connectors",
    "wires",
    "shields",
    "splices",
    "branch_points",
    "segments",
    "accessories",
)
_HAND = "Resolve it by hand, then run merge-fix again."


def handles(rel: str) -> bool:
    """Whether a file in conflict is one that this part of `merge-fix` may resolve."""
    return bool(HARNESS_FILE.match(rel)) or rel in _LISTS


@dataclass(frozen=True)
class Rename:
    """One ID of the other branch that changes. `parts` are the IDs inside a renamed harness that
    change with it (connectors, wires, shields ...), as (old, new)."""

    kind: str  # "harness" or "link"
    old: str
    new: str
    parts: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "old": self.old,
            "new": self.new,
            "parts": [{"old": o, "new": n} for o, n in self.parts],
        }


@dataclass(frozen=True)
class IdFix:
    """What `plan_id_fix` found: the files in conflict it resolves, the bytes to write for each
    file it changes, the renames, the IDs both branches made with the same content (kept once), the
    other branch's entries that now name a new ID, notes for the person, and why it refuses ('' when
    it does not)."""

    handled: tuple[str, ...] = ()
    writes: tuple[tuple[str, bytes], ...] = ()
    renames: tuple[Rename, ...] = ()
    same: tuple[str, ...] = ()
    moved: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    problem: str = ""
    regenerate: bool = False  # a harness that Generate made was renamed: generate writes the record


class _Refused(Exception):
    pass


def plan_id_fix(folder: Path, conflicts: Iterable[str], project: Project | None = None) -> IdFix:
    """Read-only: how the files in conflict that `handles` names are resolved. `project` is the
    project as it loads now (the files with markers left out); it is loaded when not given."""
    handled = tuple(sorted(c for c in conflicts if handles(c)))
    if not handled:
        return IdFix()
    try:
        return _Plan(folder, handled, project).run()
    except _Refused as exc:
        return IdFix(handled=handled, problem=str(exc))


def _two_sides(folder: Path, rel: str) -> tuple[Any, Any]:
    """Our side and their side of a file with conflict markers, parsed as JSON."""
    from harness_design_studio.core.mergefix import has_markers, take_our_side, take_their_side

    path = folder / rel
    try:
        data = path.read_bytes() if path.is_file() and not path.is_symlink() else b""
    except OSError:
        raise _Refused(f"{rel} cannot be read.") from None
    if not has_markers(data):
        raise _Refused(f"{rel} is in conflict but holds no conflict markers. {_HAND}")
    try:
        return (
            canonical.loads_strict(take_our_side(data)),
            canonical.loads_strict(take_their_side(data)),
        )
    except ValueError as exc:
        raise _Refused(f"{rel}: one side is not valid JSON ({exc}). {_HAND}") from None


def _entries(rel: str, doc: Any, side: str) -> dict[str, dict[str, Any]]:
    """The entries of a list file by ID."""
    key, _model, what = _LISTS[rel]
    if not isinstance(doc, dict) or set(doc) != {key} or not isinstance(doc[key], list):
        raise _Refused(f"{rel} ({side}) is not a list of {what}s. {_HAND}")
    out: dict[str, dict[str, Any]] = {}
    for raw in doc[key]:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or raw["id"] in out:
            raise _Refused(f"{rel} ({side}) has an entry without an ID, or one ID twice. {_HAND}")
        out[raw["id"]] = raw
    return out


def _parts_map(h: Harness, new: str) -> dict[str, str]:
    """The IDs inside harness `h` that start with its ID, with the new ID in its place."""
    old = h.id
    out: dict[str, str] = {}
    for name in _CHILD_LISTS:
        for item in getattr(h, name):
            ident: str = item.id
            if ident.startswith(old) and len(ident) > len(old) and not ident[len(old)].isalnum():
                out[ident] = new + ident[len(old) :]
    return out


def _part_ids(h: Harness) -> set[str]:
    return {item.id for name in _CHILD_LISTS for item in getattr(h, name)}


def _renamed_harness(h: Harness, new: str, parts: dict[str, str]) -> Harness:
    d = h.model_dump(mode="json")

    def m(x: str | None) -> str | None:
        return parts.get(x, x) if x is not None else None

    d["id"] = new
    for c in d.get("connectors", []):
        c["id"] = m(c["id"])
    for w in d.get("wires", []):
        w["id"], w["from_connector"], w["to_connector"] = (
            m(w["id"]),
            m(w["from_connector"]),
            m(w["to_connector"]),
        )
    for g in [*d.get("shields", []), *d.get("splices", [])]:
        g["id"] = m(g["id"])
        g["wire_ids"] = [m(x) for x in g["wire_ids"]]
    for b in d.get("branch_points", []):
        b["id"] = m(b["id"])
    for s in d.get("segments", []):
        s["id"], s["from_node"], s["to_node"] = m(s["id"]), m(s["from_node"]), m(s["to_node"])
    for a in d.get("accessories", []):
        a["id"], a["target"] = m(a["id"]), m(a.get("target"))
    return Harness.model_validate(d)


class _Plan:
    def __init__(self, folder: Path, handled: tuple[str, ...], project: Project | None) -> None:
        if project is None:
            from harness_design_studio.core.io.loader import load_project

            project = load_project(folder).project
        self.folder = folder
        self.handled = handled
        self.p = project
        repo = gitobjects.open_repo(folder)
        if repo is None:
            raise _Refused(
                "The project folder is not in a Git repository that merge-fix can read, so it "
                f"cannot tell which branch added what. {_HAND}"
            )
        self.repo = repo
        try:
            self.stages = gitobjects.stages(repo)
        except gitobjects.GitUnreadable as exc:
            raise _Refused(f"{exc} {_HAND}") from None
        self._head: dict[str, dict[str, dict[str, Any]]] = {}
        self.writes: dict[str, bytes] = {}
        self.same: list[str] = []
        self.moved: list[str] = []
        self.notes: list[str] = []
        self.harness_map: dict[str, str] = {}
        self.part_map: dict[str, str] = {}
        self.link_map: dict[str, str] = {}

    # ---- Git ---------------------------------------------------------------------------------

    def _stage(self, rel: str) -> dict[int, str]:
        found = self.stages.get(rel)
        if not found:
            raise _Refused(
                f"{rel} holds conflict markers, but Git's index does not list it as in conflict, "
                f"so merge-fix cannot tell which branch added what. {_HAND}"
            )
        if not {2, 3} <= set(found):
            raise _Refused(f"{rel} was deleted on one branch and changed on the other. {_HAND}")
        return found

    def _base(self, rel: str, stage: dict[int, str]) -> dict[str, dict[str, Any]]:
        if 1 not in stage:  # both branches added the file
            return {}
        try:
            data = gitobjects.blob(self.repo, stage[1])
            return _entries(rel, canonical.loads_strict(data), "the common version")
        except gitobjects.GitUnreadable as exc:
            raise _Refused(f"{exc} {_HAND}") from None
        except ValueError as exc:
            raise _Refused(f"{rel} (the common version) is not valid JSON ({exc}).") from None

    def _ours_committed(self, rel: str) -> dict[str, dict[str, Any]]:
        """The entries of a list file as the commit of HEAD (this branch) holds them."""
        if rel not in self._head:
            try:
                data = gitobjects.head_file(self.repo, rel)
                doc = canonical.loads_strict(data) if data is not None else None
            except gitobjects.GitUnreadable as exc:
                raise _Refused(f"{exc} {_HAND}") from None
            except ValueError:
                raise _Refused(f"{rel} in the commit of HEAD is not valid JSON. {_HAND}") from None
            self._head[rel] = {} if doc is None else _entries(rel, doc, "this branch's commit")
        return self._head[rel]

    # ---- the plan ------------------------------------------------------------------------------

    def run(self) -> IdFix:
        collisions = self._harnesses()
        lists = {rel: self._three_way(rel) for rel in self.handled if rel in _LISTS}
        link_collisions = lists[LINKS_FILE][1] if LINKS_FILE in lists else []
        renames = self._choose(collisions, link_collisions)
        for rel in sorted(_LISTS):
            if rel in lists:
                self._write_list(rel, lists[rel][0])
            else:
                self._update_list(rel)
        return IdFix(
            handled=self.handled,
            writes=tuple(sorted(self.writes.items())),
            renames=tuple(sorted(renames, key=lambda r: (r.kind, r.old))),
            same=tuple(sorted(self.same)),
            moved=tuple(sorted(self.moved)),
            notes=tuple(sorted(set(self.notes))),
            regenerate=any(theirs.generated for _rel, _ours, theirs in collisions),
        )

    def _harnesses(self) -> list[tuple[str, Harness, Harness]]:
        out: list[tuple[str, Harness, Harness]] = []
        for rel in self.handled:
            m = HARNESS_FILE.match(rel)
            if m is None:
                continue
            if 1 in self._stage(rel):
                raise _Refused(
                    f"{rel} was changed on both branches. merge-fix renames only a harness that "
                    f"both branches added. {_HAND}"
                )
            raw_ours, raw_theirs = _two_sides(self.folder, rel)
            try:
                ours, theirs = Harness.model_validate(raw_ours), Harness.model_validate(raw_theirs)
            except ValidationError:
                raise _Refused(f"{rel}: one side is not a valid harness. {_HAND}") from None
            if ours.id != m.group(1) or theirs.id != m.group(1):
                raise _Refused(f"{rel} holds a harness with another ID. {_HAND}")
            self.writes[rel] = harness_bytes(ours)
            if ours == theirs:
                self.same.append(ours.id)
            else:
                out.append((rel, ours, theirs))
        return out

    def _three_way(self, rel: str) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
        """The entries of a list file in conflict, each with the side it comes from ("ours",
        "theirs" or "both"), and the IDs that both branches added with different content."""
        stage = self._stage(rel)
        base = self._base(rel, stage)
        raw_ours, raw_theirs = _two_sides(self.folder, rel)
        ours = _entries(rel, raw_ours, "this branch")
        theirs = _entries(rel, raw_theirs, "the other branch")
        what = _LISTS[rel][2]
        kept: list[tuple[str, dict[str, Any]]] = []
        both_added: list[str] = []
        for i in sorted(set(base) | set(ours) | set(theirs)):
            b, o, t = base.get(i), ours.get(i), theirs.get(i)
            if o == t:
                if o is not None:
                    kept.append(("both", o))
            elif b is None and o is not None and t is not None:
                both_added.append(i)
                kept.append(("ours", o))
                kept.append(("theirs", t))
            elif o == b:
                if t is not None:
                    kept.append(("theirs", t))
            elif t == b:
                if o is not None:
                    kept.append(("ours", o))
            else:
                raise _Refused(
                    f"The {what} {i} of {rel} was changed on both branches in different ways. "
                    f"{_HAND}"
                )
        return kept, both_added

    def _taken(self, extra: Iterable[str]) -> set[str]:
        from harness_design_studio.core.wires import used_ids

        p = self.p
        ids = used_ids(p) | set(p.links) | set(extra)
        ids |= {b.harness_id for b in p.baselines.values()}
        ids |= {c.harness_id for c in p.changelog.values()}
        ids |= {r.harness_id for r in p.asbuilt.values()}
        ids |= {link.id for b in p.baselines.values() for link in (b.snapshot.links or [])}
        return {i.casefold() for i in ids}

    def _choose(
        self, collisions: list[tuple[str, Harness, Harness]], link_ids: list[str]
    ) -> list[Rename]:
        from harness_design_studio.core.generate.naming import namer_for

        p = self.p
        history = {b.harness_id for b in p.baselines.values()}
        history |= {c.harness_id for c in p.changelog.values()}
        history |= {r.harness_id for r in p.asbuilt.values()}
        extra: set[str] = set()
        for _rel, ours, theirs in collisions:
            extra |= {ours.id} | _part_ids(ours) | _part_ids(theirs)
        if LINKS_FILE in self.handled:
            stage = self.stages.get(LINKS_FILE, {})
            ours_links, theirs_links = _two_sides(self.folder, LINKS_FILE)
            extra |= set(_entries(LINKS_FILE, ours_links, "this branch"))
            extra |= set(_entries(LINKS_FILE, theirs_links, "the other branch"))
            extra |= set(self._base(LINKS_FILE, stage))
        taken = self._taken(extra)
        renames: list[Rename] = []
        namer = namer_for(p)
        start = p.generation.next_harness_number if p.generation is not None else 1
        for rel, ours, theirs in sorted(collisions, key=lambda c: c[1].id):
            hid = ours.id
            if ours.status != "draft" or theirs.status != "draft" or hid in history:
                raise _Refused(
                    f"Both branches made harness {hid} ({rel}), and it has a release history "
                    f"(this branch: {ours.status}, the other branch: {theirs.status}"
                    + (", with a baseline, change-log or as-built record" if hid in history else "")
                    + "). Released IDs never change, so merge-fix renames neither. "
                    + _HAND
                )
            if ours.generated and theirs.generated and ours.group_key == theirs.group_key:
                raise _Refused(
                    f"Both branches let Generate make harness {hid} for the same group "
                    f"({ours.group_key}). Keep one of the two versions of {rel} by hand, then run "
                    "merge-fix again."
                )
            new, parts = self._free_harness(theirs, namer.harness, start, taken)
            ours_ids = {i.casefold() for i in _part_ids(ours)}
            for ident in sorted(_part_ids(theirs) - set(parts)):
                if ident.casefold() in ours_ids:
                    raise _Refused(
                        f"Both branches made harness {hid}, and the ID {ident} inside it does not "
                        f"start with {hid}, so it cannot follow a new harness ID. {_HAND}"
                    )
            taken |= {new.casefold()} | {v.casefold() for v in parts.values()}
            renamed = _renamed_harness(theirs, new, parts)
            self.writes[f"physical/harnesses/{new}.json"] = harness_bytes(renamed)
            self.harness_map[hid] = new
            self.part_map.update(parts)
            renames.append(Rename("harness", hid, new, tuple(sorted(parts.items()))))
            if ours.name.casefold() == theirs.name.casefold():
                self.notes.append(
                    f"Harnesses {hid} and {new} are both called '{ours.name}'. Give one of them "
                    "another name."
                )
        snapshot_links = {link.id for b in p.baselines.values() for link in b.snapshot.links or []}
        for lid in sorted(link_ids):
            if lid in snapshot_links:
                raise _Refused(
                    f"Both branches made link {lid}, and a baseline holds a link {lid}. Released "
                    f"IDs never change, so merge-fix renames neither. {_HAND}"
                )
            n = 1
            while f"l{n}" in taken:
                n += 1
            new = f"L{n}"
            taken.add(new.casefold())
            self.link_map[lid] = new
            renames.append(Rename("link", lid, new))
        return renames

    @staticmethod
    def _free_harness(
        h: Harness, make: Callable[[int], str], start: int, taken: set[str]
    ) -> tuple[str, dict[str, str]]:
        n = max(1, start)
        for _ in range(len(taken) + 2):
            new = make(n)
            n += 1
            parts = _parts_map(h, new)
            if new.casefold() in taken or any(v.casefold() in taken for v in parts.values()):
                continue
            return new, parts
        raise _Refused(f"No free harness ID was found for {h.id}. {_HAND}")  # pragma: no cover

    # ---- the entries that name a renamed ID ----------------------------------------------------

    def _refers(self, rel: str, raw: dict[str, Any]) -> bool:
        return self._mapped(rel, raw) != raw

    def _mapped(self, rel: str, raw: dict[str, Any]) -> dict[str, Any]:
        """An entry of the other branch with every renamed ID it names replaced."""
        out = copy.deepcopy(raw)
        if rel == LINKS_FILE:
            out["id"] = self.link_map.get(out["id"], out["id"])
            if out.get("harness_id"):
                out["harness_id"] = self.harness_map.get(out["harness_id"], out["harness_id"])
        elif rel == MARKS_FILE:
            kind, sep, rest = out["id"].partition(":")
            ident, sep2, tail = rest.partition(":")
            if kind == "pos":
                ident = self.part_map.get(ident, ident)
            elif kind in ("link", "end", "bend"):
                ident = self.link_map.get(ident, ident)
            out["id"] = f"{kind}{sep}{ident}{sep2}{tail}"
        elif rel == WAIVERS_FILE:
            obj = out.get("object_id")
            new = {**self.harness_map, **self.part_map, **self.link_map}.get(obj) if obj else None
            if new is not None:
                out["object_id"] = new
                out["id"] = finding_id(str(out.get("rule", "")), new)
        return out

    def _theirs(self, rel: str, raw: dict[str, Any], side: str) -> bool:
        """Whether an entry is the other branch's: told by the conflict, or, when both sides hold
        it, by whether this branch's commit holds it as it is."""
        if side != "both":
            return side == "theirs"
        if not self._refers(rel, raw):
            return False
        return self._ours_committed(rel).get(raw["id"]) != raw

    def _place(self, rel: str, kept: list[tuple[str, dict[str, Any]]]) -> tuple[list[Entity], bool]:
        """The entries with the other branch's mapped, sorted by ID, and whether any changed."""
        _key, model, what = _LISTS[rel]
        out: dict[str, dict[str, Any]] = {}
        changed = False
        for side, raw in kept:
            entry = raw
            if self._theirs(rel, raw, side):
                entry = self._mapped(rel, raw)
                if entry != raw:
                    changed = True
                    self._say_moved(rel, raw, entry)
            if entry["id"] in out and out[entry["id"]] != entry:
                raise _Refused(
                    f"Both branches made the {what} {entry['id']} of {rel} with different content. "
                    + _HAND
                )
            out[entry["id"]] = entry
        try:
            return [model.model_validate(out[i]) for i in sorted(out)], changed
        except ValidationError:
            raise _Refused(f"{rel}: an entry is not valid after the merge. {_HAND}") from None

    def _say_moved(self, rel: str, old: dict[str, Any], new: dict[str, Any]) -> None:
        what = _LISTS[rel][2]
        if rel == LINKS_FILE:
            if old["id"] != new["id"]:
                return  # said as a rename
            self.moved.append(
                f"{rel}: link {new['id']} made harness {old['harness_id']} of the other branch; "
                f"it names {new['harness_id']} now"
            )
            return
        self.moved.append(f"{rel}: {what} {old['id']} -> {new['id']}")
        if rel == WAIVERS_FILE and new.get("finding_hash"):
            self.notes.append(
                f"The waiver {new['id']} names {new['object_id']} now. It was given for a finding "
                f"that named {old['object_id']}, so check shows it as changed until it is given "
                "again."
            )

    def _write_list(self, rel: str, kept: list[tuple[str, dict[str, Any]]]) -> None:
        items, _changed = self._place(rel, kept)
        self.writes[rel] = list_bytes(_LISTS[rel][0], items)

    def _update_list(self, rel: str) -> None:
        """A list file that merged without a conflict: the other branch's entries that name a
        renamed ID get the new one."""
        if not (self.harness_map or self.link_map):
            return
        path = self.folder / rel
        if not path.is_file() or path.is_symlink():
            return
        try:
            current = _entries(rel, canonical.loads_strict(path.read_bytes()), "the merge")
        except (OSError, ValueError) as exc:
            raise _Refused(f"{rel} cannot be read ({exc}).") from None
        kept = [("both", raw) for _i, raw in sorted(current.items())]
        if not any(self._refers(rel, raw) for _side, raw in kept):
            return
        items, changed = self._place(rel, kept)
        if changed:
            self.writes[rel] = list_bytes(_LISTS[rel][0], items)
