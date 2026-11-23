# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Schema migrations on the raw JSON tree, one step per version. Lossless: nothing is dropped."""

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from harness_design_studio.core.model import SCHEMA_VERSION

RawFiles = dict[str, Any]
# harness ID -> old revision -> the version a person gives it (`migrate --set-version`)
SetVersions = Mapping[str, Mapping[str, str]]


def _v0_to_v1(files: RawFiles) -> RawFiles:
    """v0: no schema_version, project.json used `tool`, units had `redundant: bool`."""
    out = copy.deepcopy(files)
    meta = out.get("project.json")
    if isinstance(meta, dict):
        if "tool" in meta:
            meta["tool_version"] = meta.pop("tool")
        meta["schema_version"] = 1
    for rel, data in out.items():
        if rel.startswith("logical/units/") and isinstance(data, dict):
            for unit in data.get("units", []):
                if isinstance(unit, dict) and "redundant" in unit and "side" not in unit:
                    flag = unit.pop("redundant")
                    unit["side"] = "redundant" if flag is True else "nominal"
    return out


def _v2_number(files: RawFiles) -> RawFiles:
    """The number: a tool that writes format 2 says so, so that a version 1.x tool opens the project
    read-only instead of setting a harness aside piece by piece."""
    meta = files.get("project.json")
    if isinstance(meta, dict):
        meta["schema_version"] = 2
    return files


def _v2_journal_lines(files: RawFiles) -> RawFiles:
    """The journal (M7a, D-228): `journal.json`, one JSON list, becomes `journal.jsonl`, one entry
    per line, so that Git can keep both sides' entries of a merge. The entries are carried over as
    they are, each with its number and its chain value, so they still verify; an entry added later
    names its parent instead (`core.model.journal`). The part goes by the files, not by the number:
    it does nothing for a project without `journal.json`, and the loader reads a `journal.json`
    in a format 2 project the same way (a build before M7a wrote that). With both files, the
    entries of both, in the order of the files (the reader keeps one copy of an entry)."""
    old = files.pop("journal.json", None)
    if old is None:
        return files
    new = files.get("journal.jsonl")
    if (
        isinstance(new, dict)
        and isinstance(new.get("journal"), list)
        and isinstance(old, dict)
        and isinstance(old.get("journal"), list)
    ):
        files["journal.jsonl"] = {"journal": [*new["journal"], *old["journal"]]}
    elif new is None:
        files["journal.jsonl"] = old
    else:
        files["journal.json"] = old  # a damaged file: left as it is, for the loader to report
    return files


# The parts of the step from format 1 to 2, run in this order on a copy of the files. Format 2 is
# not frozen until 2.0.0 is tagged (D-226): the journal layout of M7a is one more part here, not a
# format 3 (D-228). After the tag, only sparse fields.
V1_TO_V2_PARTS: tuple[Callable[[RawFiles], RawFiles], ...] = (_v2_number, _v2_journal_lines)


def _v1_to_v2(files: RawFiles) -> RawFiles:
    """v1 to v2 (M4, D-201, D-226). Format 2 is the format that may hold a loose cable end (a
    connector with the role `loose` and the part `TBD-CONNECTOR`; its place on the diagram is the
    mark `pos:<connector id>` in `diagram/marks.json`, outside the model hash). Nothing in a
    format 1 project has to change for that: a loose end is new content, and the origin of a
    harness (`interfaces`, `link` or `drawn`) is worked out from `generated` and the connection that
    names it, never stored (`core.origin`), so no harness file, no hash and no output moves; the
    step writes the number and moves the journal to its file of one entry per line (M7a, D-228),
    which is outside every hash and output (`V1_TO_V2_PARTS`). The migration safety net
    (`core.io.upgrade`) proves it changes no hash, finding or output."""
    out = copy.deepcopy(files)
    for part in V1_TO_V2_PARTS:
        out = part(out)
    return out


# ---- format 2 to 3 (D-242, design of 3.0.0 sections 4.5, 5.5 and 5.8) ----------------------------

VERSIONS_FORMAT = 3  # the first format whose harnesses carry versions MAJOR.MINOR.PATCH (D-242)
OLD_KEY = "revision"  # the key of a harness version in format 2, where it is a letter
NEW_KEY = "version"
OLD_KIND, NEW_KIND = "new_revision", "new_version"
TITLEBLOCK_OLD, TITLEBLOCK_NEW = "revision", "version"  # the field name of `config/titleblock.json`


@dataclass(frozen=True)
class RevisionUse:
    """One place a format 2 file holds a revision: the harness it belongs to, the value, and where
    (`harness W001`, `baseline W001.A`, `change log C0003`)."""

    harness_id: str
    value: str
    where: str
    file: str


def revision_uses(files: Mapping[str, Any]) -> list[RevisionUse]:
    """Every revision of a format 2 file tree: of each harness, each baseline (and the harness in
    its snapshot) and each change-log entry, in the order of the files. A value that is not text is
    left out (the loader reports such a file as damaged)."""
    out: list[RevisionUse] = []

    def add(hid: object, value: object, where: str, rel: str) -> None:
        if isinstance(hid, str) and isinstance(value, str):
            out.append(RevisionUse(hid, value, where, rel))

    for rel in sorted(files):
        data = files[rel]
        if not isinstance(data, dict):
            continue
        if rel.startswith("physical/harnesses/"):
            add(data.get("id"), data.get(OLD_KEY), f"harness {data.get('id')}", rel)
        elif rel == "changelog.json" and isinstance(data.get("changelog"), list):
            for e in data["changelog"]:
                if isinstance(e, dict):
                    add(e.get("harness_id"), e.get(OLD_KEY), f"change log {e.get('id')}", rel)
        elif rel.startswith("baselines/"):
            bid = data.get("id")
            add(data.get("harness_id"), data.get(OLD_KEY), f"baseline {bid}", rel)
            snap = data.get("snapshot")
            for h in snap.get("harnesses", []) if isinstance(snap, dict) else []:
                if isinstance(h, dict):
                    add(h.get("id"), h.get(OLD_KEY), f"baseline {bid}, its snapshot", rel)
    return out


def version_of(harness_id: str, revision: str, set_versions: SetVersions | None) -> str | None:
    """The version an old revision of a harness becomes (section 5.5, Q18): the one a person gave
    (`--set-version`), else the mapping of `versions.letter_to_version` (`A` is `1.0.0`, `B` is
    `2.0.0`, a version is kept); None for any other value, which is not guessed."""
    from harness_design_studio.core.vcs.versions import letter_to_version

    given = (set_versions or {}).get(harness_id, {}).get(revision)
    return given if given is not None else letter_to_version(revision)


def version_map(
    files: Mapping[str, Any], set_versions: SetVersions | None = None
) -> tuple[dict[str, dict[str, str]], list[RevisionUse]]:
    """(harness -> old revision -> version, the uses whose revision has no version). Every use of
    one value in one harness gets the same version."""
    mapping: dict[str, dict[str, str]] = {}
    missing: list[RevisionUse] = []
    for use in revision_uses(files):
        new = version_of(use.harness_id, use.value, set_versions)
        if new is None:
            missing.append(use)
        else:
            mapping.setdefault(use.harness_id, {})[use.value] = new
    return mapping, missing


MAX_ID = 64  # the longest ID (`core.ids`): a baseline ID is `<harness>.<version>`


def version_problems(
    files: Mapping[str, Any], set_versions: SetVersions | None = None
) -> list[str]:
    """Why the revisions of a format 2 file tree cannot be mapped to versions as they are (section
    5.5), one sentence each; empty when they can. Refused: a value that is neither a letter nor a
    version and that no `--set-version` gives; a version given with `--set-version` that is not
    MAJOR.MINOR.PATCH; two old revisions of one harness that would give the same version; a mapping
    that puts the releases of a harness in another order than its change log; a baseline whose new
    ID would be longer than an ID may be."""
    from harness_design_studio.core.model.base import VERSION_RE
    from harness_design_studio.core.vcs.versions import version_key

    out: list[str] = []
    for hid, given in sorted((set_versions or {}).items()):
        for old, new in sorted(given.items()):
            if VERSION_RE.fullmatch(new) is None:
                out.append(
                    f"--set-version {hid}:{old}={new}: '{new}' is not a version MAJOR.MINOR.PATCH "
                    "(such as 1.1.0)."
                )
    mapping, missing = version_map(files, set_versions)
    seen: set[tuple[str, str]] = set()
    for use in missing:
        if (use.harness_id, use.value) in seen:
            continue
        seen.add((use.harness_id, use.value))
        out.append(
            f"{use.where}: revision '{use.value}' is not a letter, so its version is not guessed. "
            f"Give it with --set-version {use.harness_id}:{use.value}=VERSION."
        )
    for hid, values in sorted(mapping.items()):
        by_version: dict[str, list[str]] = {}
        for old, new in values.items():
            by_version.setdefault(new, []).append(old)
        for new, olds in sorted(by_version.items()):
            if len(olds) > 1:
                shown = " and ".join(f"'{o}'" for o in sorted(olds, key=version_key))
                out.append(
                    f"{hid}: the revisions {shown} would both become version {new}. Give one of "
                    f"them another version with --set-version {hid}:OLD=VERSION."
                )
        if len(hid) + 1 + max((len(v) for v in values.values()), default=0) > MAX_ID:
            out.append(
                f"{hid}: a baseline ID '<harness>.<version>' would be longer than {MAX_ID} "
                "characters. Rename the harness with a version of format 2 first."
            )
    log = files.get("changelog.json")
    entries = log.get("changelog", []) if isinstance(log, dict) else []
    releases: dict[str, list[str]] = {}
    for e in sorted((e for e in entries if isinstance(e, dict)), key=lambda e: str(e.get("id"))):
        harness, revision = e.get("harness_id"), e.get(OLD_KEY)
        if e.get("kind") == "release" and isinstance(harness, str) and isinstance(revision, str):
            mapped = mapping.get(harness, {}).get(revision)
            if mapped is not None:
                releases.setdefault(harness, []).append(mapped)
    for hid, versions in sorted(releases.items()):
        keys = [version_key(v) for v in versions]
        if any(b < a for a, b in zip(keys, keys[1:], strict=False)):
            out.append(
                f"{hid}: the versions {', '.join(versions)} would put its releases in another "
                "order than its change log. Give them versions in that order with "
                f"--set-version {hid}:OLD=VERSION."
            )
    return out


def _v3_number(files: RawFiles) -> RawFiles:
    """The number: a 2.x tool opens a format 3 project read-only (the rule of D-226)."""
    meta = files.get("project.json")
    if isinstance(meta, dict):
        meta["schema_version"] = 3
    return files


def _renamed(data: dict[str, Any], hid: object, set_versions: SetVersions | None) -> None:
    """The key `revision` of one object becomes `version`, with its value mapped. A value with no
    version is carried over as it is under the new key: the model refuses it, so the loader names
    it, and `migrate` refuses before it writes (`upgrade.plan_upgrade`)."""
    if OLD_KEY not in data or NEW_KEY in data:
        return
    old = data.pop(OLD_KEY)
    new = (
        version_of(hid, old, set_versions)
        if isinstance(hid, str) and isinstance(old, str)
        else None
    )
    data[NEW_KEY] = new if new is not None else old


def _v3_versions(files: RawFiles, set_versions: SetVersions | None = None) -> RawFiles:
    """The versions (section 5.5): each revision of a harness, of its baselines (and the harness in
    each snapshot) and of its change-log entries becomes its version under the key `version`; the
    change-log kind `new_revision` becomes `new_version`; each baseline is named and stored by its
    new ID `<harness>.<version>`. Its `content_hash` stays the value recorded at the release."""
    for rel in [r for r in files if r.startswith("physical/harnesses/")]:
        data = files[rel]
        if isinstance(data, dict):
            _renamed(data, data.get("id"), set_versions)
    log = files.get("changelog.json")
    if isinstance(log, dict) and isinstance(log.get("changelog"), list):
        for e in log["changelog"]:
            if isinstance(e, dict):
                _renamed(e, e.get("harness_id"), set_versions)
                if e.get("kind") == OLD_KIND:
                    e["kind"] = NEW_KIND
    for rel in sorted(r for r in files if r.startswith("baselines/")):
        data = files[rel]
        if not isinstance(data, dict):
            continue
        hid, bid, old = data.get("harness_id"), data.get("id"), data.get(OLD_KEY)
        _renamed(data, hid, set_versions)
        snap = data.get("snapshot")
        for h in snap.get("harnesses", []) if isinstance(snap, dict) else []:
            if isinstance(h, dict):
                _renamed(h, h.get("id"), set_versions)
        if isinstance(snap, dict) and isinstance(snap.get("config"), dict):
            _titleblock_fields(snap["config"].get("titleblock"))
        new = data.get(NEW_KEY)
        if isinstance(hid, str) and isinstance(bid, str) and bid == f"{hid}.{old}":
            data["id"] = f"{hid}.{new}"
            folder, _, name = rel.rpartition("/")
            if name == f"{bid}.json":
                files.pop(rel)
                files[f"{folder}/{data['id']}.json"] = data
    return files


def _titleblock_fields(values: object) -> None:
    """The field name `revision` of a title block's `fields` becomes `version` (Q28)."""
    if isinstance(values, dict) and isinstance(values.get("fields"), list):
        values["fields"] = [TITLEBLOCK_NEW if f == TITLEBLOCK_OLD else f for f in values["fields"]]


def _v3_titleblock(files: RawFiles) -> RawFiles:
    """`config/titleblock.json`: the field name `revision` in `fields` becomes `version`. A file
    that does not list it is not touched."""
    cfg = files.get("config/titleblock.json")
    if isinstance(cfg, dict):
        _titleblock_fields(cfg.get("values"))
    return files


# ---- a format 2 key or letter in a format 3 project, after a merge (section 5.6) ----------------
#
# A branch still in format 2, merged into a branch in format 3, can bring a key `revision` and a
# letter into a format 3 file: a harness it made, a change-log entry, a baseline. The loader refuses
# such an object (the model knows no key `revision` and no letter) and names it with the code
# `revision_not_version` and the version the letter maps to; `merge-fix` rewrites such keys and
# letters by the rule of section 5.5 (`rewrite_leftovers`).

LEFTOVER_CODE = "revision_not_version"


@dataclass(frozen=True)
class Leftover:
    """One object of a format 3 file that still holds a key or a letter of format 2: the file,
    where in it (`harness W002`, `change log C0007`, `baseline W002.A`, `the title block`), the old
    value and the version it maps to (None when it is not a letter, which is not guessed)."""

    file: str
    where: str
    value: str
    version: str | None

    def line(self) -> str:
        """What `merge-fix` rewrites here, in one line."""
        if self.where == "the title block":
            return f"{self.file}: the title block field 'revision' -> 'version'"
        if self.value == OLD_KIND:
            return f"{self.file}: {self.where}: the kind '{OLD_KIND}' -> '{NEW_KIND}'"
        return f"{self.file}: {self.where}: revision '{self.value}' -> version {self.version}"

    def message(self) -> str:
        """The sentence of the loader's finding `revision_not_version`."""
        if self.where == "the title block":
            return (
                f"{self.where} lists the field 'revision' of format 2; in format 3 it is called "
                "'version'. `harness-design-studio merge-fix DIR` rewrites it."
            )
        if self.version is None:
            return (
                f"{self.where} holds the revision '{self.value}' of format 2, which is not a "
                "letter, so its version is not guessed: write a version MAJOR.MINOR.PATCH under "
                "the key 'version' by hand. A branch in format 2 was merged into a project in "
                "format 3; upgrade the other branches before they merge."
            )
        return (
            f"{self.where} holds the revision '{self.value}' of format 2; in format 3 that is "
            f"version {self.version}. A branch in format 2 was merged into a project in format 3: "
            "`harness-design-studio merge-fix DIR` rewrites the key and the letter."
        )


def _leftover_value(data: dict[str, Any]) -> str | None:
    """The old value an object of format 3 still holds: any value under the key `revision`, or an
    upper-case letter under the key `version`. None for a clean object (and for any other text under
    `version`, which the model names as it names any wrong value)."""
    from harness_design_studio.core.vcs.versions import letter_number

    if OLD_KEY in data:
        old = data[OLD_KEY]
        return old if isinstance(old, str) else str(old)
    new = data.get(NEW_KEY)
    if isinstance(new, str) and letter_number(new) is not None:
        return new
    return None


def _objects(files: Mapping[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(file, where, object) for every harness, change-log entry, baseline and harness of a
    baseline's snapshot of a file tree, in the order of the files."""
    out: list[tuple[str, str, dict[str, Any]]] = []
    for rel in sorted(files):
        data = files[rel]
        if not isinstance(data, dict):
            continue
        if rel.startswith("physical/harnesses/"):
            out.append((rel, f"harness {data.get('id')}", data))
        elif rel == "changelog.json" and isinstance(data.get("changelog"), list):
            out += [
                (rel, f"change log {e.get('id')}", e)
                for e in data["changelog"]
                if isinstance(e, dict)
            ]
        elif rel.startswith("baselines/"):
            out.append((rel, f"baseline {data.get('id')}", data))
            snap = data.get("snapshot")
            for h in snap.get("harnesses", []) if isinstance(snap, dict) else []:
                if isinstance(h, dict):
                    out.append((rel, f"baseline {data.get('id')}, its snapshot", h))
    return out


def _titleblocks(files: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(file, values) of the title block of `config/titleblock.json` and of each baseline's frozen
    copy."""
    out: list[tuple[str, dict[str, Any]]] = []
    cfg = files.get("config/titleblock.json")
    if isinstance(cfg, dict) and isinstance(cfg.get("values"), dict):
        out.append(("config/titleblock.json", cfg["values"]))
    for rel in sorted(r for r in files if r.startswith("baselines/")):
        data = files[rel]
        snap = data.get("snapshot") if isinstance(data, dict) else None
        config = snap.get("config") if isinstance(snap, dict) else None
        tb = config.get("titleblock") if isinstance(config, dict) else None
        if isinstance(tb, dict):
            out.append((rel, tb))
    return out


def leftovers(files: Mapping[str, Any]) -> list[Leftover]:
    """Every key or letter of format 2 in a format 3 file tree (section 5.6, *Merges across the
    upgrade*): an object with the key `revision`, a letter under the key `version`, a change-log
    entry of the kind `new_revision`, and the title block field `revision`. Empty for a clean
    tree. Read only."""
    from harness_design_studio.core.vcs.versions import letter_to_version

    out: list[Leftover] = []
    for rel, where, data in _objects(files):
        value = _leftover_value(data)
        if value is not None:
            out.append(Leftover(rel, where, value, letter_to_version(value)))
        elif data.get("kind") == OLD_KIND:
            out.append(Leftover(rel, where, OLD_KIND, NEW_KIND))
    for rel, values in _titleblocks(files):
        fields = values.get("fields")
        if isinstance(fields, list) and TITLEBLOCK_OLD in fields:
            out.append(Leftover(rel, "the title block", TITLEBLOCK_OLD, TITLEBLOCK_NEW))
    return out


def rewrite_leftovers(files: Mapping[str, Any]) -> tuple[RawFiles, dict[str, str]]:
    """The file tree with every key and letter of format 2 that `leftovers` finds rewritten by the
    rule of section 5.5 (`A` is `1.0.0`, `B` is `2.0.0`; a version is kept), and the baselines that
    move to their new name (old file -> new file). A key `revision` beside a key `version` is
    dropped (the version is the format 3 side). A value that is not a letter is left as it is: it
    is not guessed, and the loader still names it. Works on a copy."""
    from harness_design_studio.core.vcs.versions import (
        is_version,
        letter_number,
        letter_to_version,
    )

    out = copy.deepcopy(dict(files))
    for _rel, _where, data in _objects(out):
        if OLD_KEY in data:
            old = data.pop(OLD_KEY)
            data.setdefault(NEW_KEY, old)
        value = data.get(NEW_KEY)
        if isinstance(value, str) and not is_version(value):
            mapped = letter_to_version(value)
            if mapped is not None and letter_number(value) is not None:
                data[NEW_KEY] = mapped
        if data.get("kind") == OLD_KIND:
            data["kind"] = NEW_KIND
    for _rel, values in _titleblocks(out):
        fields = values.get("fields")
        if isinstance(fields, list) and TITLEBLOCK_OLD in fields:
            renamed = [TITLEBLOCK_NEW if f == TITLEBLOCK_OLD else f for f in fields]
            values["fields"] = [f for i, f in enumerate(renamed) if f not in renamed[:i]]
    moved: dict[str, str] = {}
    for rel in sorted(r for r in out if r.startswith("baselines/")):
        data = out[rel]
        if not isinstance(data, dict):
            continue
        hid, bid, version = data.get("harness_id"), data.get("id"), data.get(NEW_KEY)
        if not (isinstance(hid, str) and isinstance(bid, str) and isinstance(version, str)):
            continue
        old = bid.removeprefix(f"{hid}.") if bid.startswith(f"{hid}.") else None
        if old is None or old == version or letter_to_version(old) != version:
            continue
        data["id"] = f"{hid}.{version}"
        folder, _, name = rel.rpartition("/")
        if name == f"{bid}.json":
            target = f"{folder}/{data['id']}.json"
            if target not in out:
                out[target] = out.pop(rel)
                moved[rel] = target
    return out, moved


# The parts of the step from format 2 to 3, run in this order on a copy of the files. Every new
# field of format 3 is absent, so it has its default: no pin gets `signal_ground`, no config file is
# created, and `project.json` changes in its number only (`ProjectMeta` is sparse for `document`).
V2_TO_V3_PARTS: tuple[Callable[[RawFiles], RawFiles], ...] = (
    _v3_number,
    _v3_versions,
    _v3_titleblock,
)


def _v2_to_v3(files: RawFiles, set_versions: SetVersions | None = None) -> RawFiles:
    """v2 to v3 (D-242, design of 3.0.0 sections 4.5 and 5.5). Format 3 names a harness version by
    MAJOR.MINOR.PATCH under the key `version` and holds the new fields of the harness plan (all
    sparse). The step writes the number, maps every revision to its version and renames the keys
    (`revision` to `version`, the kind `new_revision` to `new_version`, the title block field
    `revision` to `version`); it adds nothing. Unlike the steps before it, it changes the model hash
    once, because the versions are in the design files: the migration safety net
    (`core.io.upgrade`) proves that nothing else changes (section 5.6)."""
    out = copy.deepcopy(files)
    for part in V2_TO_V3_PARTS:
        out = _v3_versions(out, set_versions) if part is _v3_versions else part(out)
    return out


# ---- format 3 to 4 (D-251, design of 4.0.0 section 5) --------------------------------------------


def _v4_number(files: RawFiles) -> RawFiles:
    """The number: a 3.x tool opens a format 4 project read-only (the rule of D-226)."""
    meta = files.get("project.json")
    if isinstance(meta, dict):
        meta["schema_version"] = 4
    return files


# The parts of the step from format 3 to 4. The one new key of format 4, `row_layout` of a connector
# part and of a box connector, is sparse and nobody has a layout before format 4, so the step
# writes the number and nothing else: no other file changes, and `project.json` in its number only.
V3_TO_V4_PARTS: tuple[Callable[[RawFiles], RawFiles], ...] = (_v4_number,)


def _v3_to_v4(files: RawFiles) -> RawFiles:
    """v3 to v4 (D-250, D-251, design of 4.0.0 section 5). Format 4 holds the row layout of a
    connector (`Part.row_layout`, `Connector.row_layout`, both left out of the files while unset).
    A format 3 tree is a valid format 4 tree apart from the number, so the step writes the number
    (`V3_TO_V4_PARTS`) and changes no hash: like the step from 1 to 2, the migration safety net
    (`core.io.upgrade`) is its whole proof (the same model hash, findings, baselines and export)."""
    out = copy.deepcopy(files)
    for part in V3_TO_V4_PARTS:
        out = part(out)
    return out


# ---- format 4 to 5 (D-264, design of 5.0.0 section 3) --------------------------------------------


def _v5_number(files: RawFiles) -> RawFiles:
    """The number: a 4.x tool opens a format 5 project read-only (the rule of D-226)."""
    meta = files.get("project.json")
    if isinstance(meta, dict):
        meta["schema_version"] = 5
    return files


# The parts of the step from format 4 to 5. Every new key of format 5 (design of 5.0.0 section 3.1:
# `length_to` of a cable connector, `depth_mm` of a part, `current_a` of a pin, `at_a` and `at_b` of
# a shield group, `checked` of a device) is sparse and nobody has one before format 5, so the step
# writes the number and nothing else: no other file changes, and `project.json` in its number only.
V4_TO_V5_PARTS: tuple[Callable[[RawFiles], RawFiles], ...] = (_v5_number,)


def _v4_to_v5(files: RawFiles) -> RawFiles:
    """v4 to v5 (D-264, design of 5.0.0 section 3.3). Format 5 holds the fields of milestone E5
    (where a length is measured to and the depth of a connector, a current per pin, the place of a
    shield end, the checked state of a device), each left out of the files while unset. A format 4
    tree is a valid format 5 tree apart from the number, so the step writes the number
    (`V4_TO_V5_PARTS`) and changes no hash: as for the step from 3 to 4, the migration safety net
    (`core.io.upgrade`) is its whole proof (the same model hash, findings, baselines and export)."""
    out = copy.deepcopy(files)
    for part in V4_TO_V5_PARTS:
        out = part(out)
    return out


# `MIGRATIONS[n]` takes a project from format n to n + 1; there is one for every format before the
# one this tool writes (`SCHEMA_VERSION`).
MIGRATIONS: dict[int, Callable[[RawFiles], RawFiles]] = {
    0: _v0_to_v1,
    1: _v1_to_v2,
    2: _v2_to_v3,
    3: _v3_to_v4,
    4: _v4_to_v5,
}
# The steps that take the versions a person gave for the revisions the mapping cannot guess.
TAKES_VERSIONS = frozenset({2})


def current_version() -> int:
    """The format this tool writes."""
    return SCHEMA_VERSION


def schema_version_of(files: RawFiles) -> int:
    meta = files.get("project.json")
    if isinstance(meta, dict):
        value = meta.get("schema_version", 0)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return SCHEMA_VERSION  # unreadable project.json: assume current and report the real problem


def migrate_raw(
    files: RawFiles,
    from_version: int,
    *,
    set_versions: SetVersions | None = None,
    to_version: int | None = None,
) -> RawFiles:
    """The files of format `from_version` brought to `to_version` (default: the format of this
    tool), step by step. `set_versions` are the versions a person gave for revisions that the step
    from 2 to 3 cannot map (`migrate --set-version`)."""
    version = from_version
    target = current_version() if to_version is None else to_version
    while version < target:
        step = MIGRATIONS[version]
        if version in TAKES_VERSIONS and set_versions:
            files = step(files, set_versions)  # type: ignore[call-arg]
        else:
            files = step(files)
        version += 1
    return files
