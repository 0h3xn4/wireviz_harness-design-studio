# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Versions of a harness: the order of revisions and versions, the next version, the mapping of an
old letter, and the pinout test (design of 3.0.0, `docs/ait/DESIGN_3.0_HARNESS_PLAN.md` section 5).

Format 2 names a harness revision by upper-case letters (A, B … Z, AA, AB …, `release.next_revision`);
format 3 will name it by a version MAJOR.MINOR.PATCH (section 5.2, D-242, Q9). This module is
prepared before format 3 (pull request R1 of section 12): `version_key` is the one order of
revisions that `report.baselines_of`, the editor's top bar and `describe.harness_state` use, and it
keeps the letter order of format 2 exactly; `bump`, `letter_to_version` and the pinout test have no
caller yet. Nothing here is shown, and nothing here writes a file.

Pure: no Qt, no file, no clock.
"""

import re
from collections.abc import Iterable
from typing import Literal

from harness_design_studio.core.model import Snapshot
from harness_design_studio.core.model.base import FIRST_VERSION as FIRST_VERSION_OF_MODEL
from harness_design_studio.core.model.base import VERSION_RE

from .diff import Flat, ObjectChange, diff_flat, flatten_snapshot

VersionKind = Literal["major", "minor", "patch"]
KINDS: tuple[VersionKind, ...] = ("major", "minor", "patch")

# The revision a new harness gets in format 2 (the model's default and generation's value); a
# harness at any other revision is a later one (`describe.harness_state`).
FIRST_REVISION = "A"
FIRST_VERSION = FIRST_VERSION_OF_MODEL  # the version a new harness starts at in format 3

MAX_PART = 9999  # each of the three numbers of a version, section 5.2

# Section 5.2: three whole numbers from 0 to 9999, without a leading zero and without a prefix, so
# there is one way to write each version and two equal versions are equal text.
_VERSION = VERSION_RE  # the type `Version` of the model checks the same pattern
_LETTERS = re.compile(r"[A-Z]+")

type VersionKey = tuple[int, tuple[int, int, int], str]


def is_version(text: str) -> bool:
    """True for a version as section 5.2 writes it: `1.0.0`, `1.10.2`; not `01.0.0`, `v1.0.0`,
    `1.0` or `10000.0.0`."""
    return _VERSION.fullmatch(text) is not None


def _parts(version: str) -> tuple[int, int, int]:
    m = _VERSION.fullmatch(version)
    if m is None:
        raise ValueError(f"'{version}' is not a version MAJOR.MINOR.PATCH")
    return int(m[1]), int(m[2]), int(m[3])


def letter_number(text: str) -> int | None:
    """The place of a revision of upper-case letters in the letter order of format 2 (section 5.5):
    A is 1, Z is 26, AA is 27, AZ is 52, ZZ is 702, AAA is 703. `None` for any other text.

    The letters count as `release.next_revision` counts them (spreadsheet columns), so the order of
    the numbers is the letter order of format 2: shorter first, then alphabetical."""
    if _LETTERS.fullmatch(text) is None:
        return None
    n = 0
    for ch in text:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n


def version_key(text: str) -> VersionKey:
    """The one sort key of revisions and versions (section 5.2: *one function does it, wherever
    versions are sorted*; section 5.7).

    - A version sorts by its three numbers, never as text: `1.0.0 < 1.2.0 < 1.9.0 < 1.10.0 <
      2.0.0`.
    - A letter of format 2 sorts as the version it maps to (section 5.5: `A` is `1.0.0`, `B` is
      `2.0.0`, `AA` is `27.0.0`), so the letters keep the order of format 2 exactly (shorter first,
      then alphabetical: `A < B < Z < AA < AB < ZZ < AAA`), the order `report.baselines_of` gave
      by length and text before this function, and a letter and a version are in the order the
      migration of section 5.5 gives them.
    - Any other text (only a hand-edited file or a merge holds one: `b`, `A1`, `-`, `1.0`) sorts
      after every letter and version, by length and then as text, as `baselines_of` sorted it.

    The text is the last part of the key, so the order is total and the same on every computer: a
    letter and the version it maps to (`B` and `2.0.0`, which only a hand-edited file can hold
    together) are next to each other, the version first, and two keys are equal only for equal
    texts."""
    n = letter_number(text)
    if n is not None:
        return (0, (n, 0, 0), text)
    if is_version(text):
        return (0, _parts(text), text)
    return (1, (len(text), 0, 0), text)


def sort_versions(texts: Iterable[str]) -> list[str]:
    """The revisions or versions in the order of `version_key`, lowest first."""
    return sorted(texts, key=version_key)


def is_first(version: str) -> bool:
    """True for the version a new harness starts at (`FIRST_VERSION`, `1.0.0`, format 3; it was the
    letter `A` in format 2, which the migration maps to `1.0.0`). Any other version is a later one,
    as `describe.harness_state` reads it."""
    return version_key(version) == version_key(FIRST_VERSION)


def letter_to_version(revision: str) -> str | None:
    """The version of an old revision by the mapping of section 5.5 (Q18), for the migration of
    format 2 to 3 (pull request 1 of section 12; no caller yet).

    - An upper-case letter becomes `N.0.0`, N its place in the letter order: `A` → `1.0.0`, `B` →
      `2.0.0`, `Z` → `26.0.0`, `AA` → `27.0.0`.
    - A revision that is already a version (`1.2.0`) is kept.
    - Any other value (`b`, `A1`, `01`, `-`, `1.0`) is not guessed: `None`, and the migration asks a
      person for the version (`migrate --set-version`). So is a letter whose place is above 9999
      (`NTP`, the 10000th, and later), because `N.0.0` would not be a version (section 5.2)."""
    if is_version(revision):
        return revision
    n = letter_number(revision)
    if n is None or n > MAX_PART:
        return None
    return f"{n}.0.0"


def bump(version: str, kind: VersionKind) -> str:
    """The next version of a released `version` (section 5.3): from `1.4.2`, major gives `2.0.0`,
    minor `1.5.0` and patch `1.4.3`.

    `ValueError` for a `version` that is not MAJOR.MINOR.PATCH (a letter is mapped first, by
    `letter_to_version`), for a kind other than major, minor and patch, and for a number that
    would go above 9999."""
    major, minor, patch = _parts(version)
    if kind == "major":
        major, minor, patch = major + 1, 0, 0
    elif kind == "minor":
        minor, patch = minor + 1, 0
    elif kind == "patch":
        patch += 1
    else:
        raise ValueError(f"'{kind}' is not a kind of version (major, minor or patch)")
    if max(major, minor, patch) > MAX_PART:
        raise ValueError(f"The {kind} version after {version} would have a number above {MAX_PART}")
    return f"{major}.{minor}.{patch}"


# ---- the pinout test of section 5.3 (Q20) -------------------------------------------------------

# What section 5.3 counts as a change at an end that plugs into a device: the cable connector's
# part, gender or keying, and the box connector it mates with (`mates_with`).
PINOUT_FIELDS = frozenset({"part_id", "gender", "keying", "mates_with"})
_WIRE_ENDS = (("from_connector", "from_pin"), ("to_connector", "to_pin"))


def _device_ends(flat: Flat) -> set[str]:
    """The cable connectors that plug into a device: those that mate with a box connector."""
    return {
        cid
        for (kind, cid), data in flat.items()
        if kind == "cable_connector" and data.get("mates_with")
    }


def _wire_ends(data: dict[str, object]) -> list[tuple[object, object]]:
    return [(data.get(c), data.get(p)) for c, p in _WIRE_ENDS]


def _is_pinout_change(
    c: ObjectChange, before: Flat, after: Flat, ends_before: set[str], ends_after: set[str]
) -> bool:
    key = (c.kind, c.id)
    if c.kind == "cable_connector":
        if c.change == "added":
            return c.id in ends_after
        if c.change == "removed":
            return c.id in ends_before
        return (c.id in ends_before or c.id in ends_after) and any(
            f.name in PINOUT_FIELDS for f in c.fields
        )
    if c.kind == "wire":
        if c.change == "added":
            return any(conn in ends_after for conn, _pin in _wire_ends(after[key]))
        if c.change == "removed":
            return any(conn in ends_before for conn, _pin in _wire_ends(before[key]))
        old, new = _wire_ends(before[key]), _wire_ends(after[key])
        return any(
            o != n and (o[0] in ends_before or n[0] in ends_after)
            for o, n in zip(old, new, strict=True)
        )
    return False


def pinout_changes(before: Snapshot, after: Snapshot) -> list[ObjectChange]:
    """The changes of the diff from `before` (the last baseline) to `after` (the working design)
    that section 5.3 counts as a change of the pinout at a device (Q20), in the order of the diff.

    An end that plugs into a device is a cable connector that mates with a box connector
    (`mates_with` is set), in either snapshot. Counted, as section 5.3 lists them and nothing else:

    - such a cable connector whose part, gender or keying changed, or the box connector it mates
      with (`mates_with`: another one, or none any more, or one where it had none); a cable
      connector added or removed that mates with a box connector is counted the same way, because
      it changes what plugs into that box connector;
    - a wire added or removed with an end at such a connector, or a wire whose end moved (another
      connector or another pin) at such a connector, before or after the move.

    Not counted (conservative reading of section 5.3, which names no more): a change of a cable
    pin's own fields, of a wire's gauge, colour, part or length, of a connector that plugs into no
    device (an inline or a loose end), and of the box connector itself, which belongs to the
    device, not to the harness. Between minor and patch nothing is decided here (section 5.3)."""
    flat_before, flat_after = flatten_snapshot(before), flatten_snapshot(after)
    ends_before, ends_after = _device_ends(flat_before), _device_ends(flat_after)
    return [
        c
        for c in diff_flat(flat_before, flat_after).changes
        if _is_pinout_change(c, flat_before, flat_after, ends_before, ends_after)
    ]


def pinout_note_due(kind: VersionKind, changes: list[ObjectChange]) -> bool:
    """Whether review and release show the note of section 5.3 (Q20): the diff changes the pinout
    at a device (`pinout_changes`) and the kind is minor or patch, which says *compatible*. The
    template calls such a change incompatible. A major version needs no note; the note changes no
    version and blocks nothing."""
    if kind not in KINDS:
        raise ValueError(f"'{kind}' is not a kind of version (major, minor or patch)")
    return bool(changes) and kind != "major"


__all__ = [
    "FIRST_REVISION",
    "FIRST_VERSION",
    "KINDS",
    "MAX_PART",
    "PINOUT_FIELDS",
    "VersionKey",
    "VersionKind",
    "bump",
    "is_first",
    "is_version",
    "letter_number",
    "letter_to_version",
    "pinout_changes",
    "pinout_note_due",
    "sort_versions",
    "version_key",
]
