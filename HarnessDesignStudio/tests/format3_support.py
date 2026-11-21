# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The comparison of section 5.6 of the design of 3.0.0 (D-242, part 3 of the proof): a written file
of 2.x, from the record `tests/fixtures/format3/before/` (made by `tools.format3_record` with the
code of 2.x), changed by these steps in this order, must equal the file this tool writes for the
same project:

1. the stamp: the tool version, the model hash (and the content hash and the hash of the title block values, which
   follow from it: the step renamed the title block field), paired by their places in
   `export.json`, `manifest.json` and `provenance.json`;
2. the file names: `system/revision_report.md` is `system/version_report.md` (Q31);
3. the fixed list of word changes, `tests/fixtures/format3/word_changes.json`, in its order;
4. what follows from the length of a replaced text: the line of a renamed field in the comparison
   of the version report moves to its place among the fields, which are sorted by name (one narrow
   rule, `_resort_field`); a column width or a cut title block text would be here as well, and none
   changes (the test fails if one does);
5. `manifest.json`: the list of names is the 2.x list with the renamed file, and each hash and size
   is that of the file of 3.0;
6. the step of 4.0.0 (design of 4.0.0 section 11, owner answer L4): `export.json` drops the older
   name `revision` that 3.0.x wrote beside `version` in each harness and has `format_version` 2
   (`drop_older_name`);
7. the step of 4.1.0 (design of 4.1.0, P7, #311): the shield-group column of `wirelist.csv`, of
   the *Wire list* of `<ID>.xlsx` and of the *Cut list* of `<ID>_build.xlsx` names every shield
   group of a wire in natural ID order, joined by `;`, where 2.x named one of them; the width of
   the *Cut list* column follows (the longest text plus 2, at most 46). The groups come from the
   project with the rule stated here a second time (`shield_groups`), and a cell is changed only
   when the 2.x text is one of the groups the step puts in its place (`every_shield_group`);
8. the step of 4.1.0 for the build workbook (design of 4.1.0 parts A and D, pull request 3):
   `<ID>_build.xlsx` has the new sheet *Production*, taken as the file of 4.1.0 has it (2.x has no
   such sheet; its own tests and the independent check of the outputs read it), and the members
   that list the sheets and the styles (`BUILD_SHEET_MEMBERS`) follow; *Start here* has the row
   *Lengths* with the four sentences after *Released on* and the line *Production* in *How to use
   this workbook* after *Cut list* (and *Routing*); the length heading of *Cut list* is
   `Length (m), rear to rear` and of *Routing* `Length (m), rear or branch centre`, each column as
   wide as its heading plus 2, and both sheets end with the four sentences after an empty row
   below their last row. The first, second and fourth sentences are
   stated here; the third names the service loops of the project, so it is taken from the file of
   4.1.0 when it has the form stated here (`production_sheet`);
9. the step of 4.2.0 (design of 4.2.0, section 8, pull request 4): the line `Rules run: 39.` of
   `system/drc_report.md` (the line that starts with `Model hash:`) reads `Rules run: N.` with N
   the number of rules of this tool (`drc.RULES`, 43), and nothing else of the report changes; no
   recorded project has a finding of the four new rules (`rule_count`).

Workbooks are compared cell by cell with their column widths and the hash of each member that
holds no cell (styles, workbook); drawings by their text items and positions; JSON files by their
content; every other file as text. Any other difference is reported."""

import copy
import csv
import fnmatch
import hashlib
import io
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from harness_design_studio import __version__
from harness_design_studio.core.vcs.versions import letter_to_version
from tests.helpers import FIXTURES

BEFORE = FIXTURES / "format3" / "before"
WORD_CHANGES = FIXTURES / "format3" / "word_changes.json"
OLD_REPORT, NEW_REPORT = "system/revision_report.md", "system/version_report.md"
_HEX = re.compile(r"(?<![0-9a-f])[0-9a-f]{12,64}(?![0-9a-f])")
_LETTER = r"([A-Z]{1,3})(?![A-Za-z0-9])"

Files = dict[str, dict[str, Any]]


def recorded() -> list[str]:
    return sorted(
        p.stem for p in BEFORE.glob("*.json") if not p.stem.startswith(("golden-", "numbers-"))
    )


def record(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads((BEFORE / f"{name}.json").read_text(encoding="utf-8"))
    return doc


def word_changes() -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = json.loads(WORD_CHANGES.read_text(encoding="utf-8"))["changes"]
    return changes


# ---- step 1: the stamp --------------------------------------------------------------------------


def _pairs(old: Any, new: Any, path: str, out: dict[str, str]) -> None:
    """The hashes that follow from the model hash, at the same places in both files."""
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old.keys() & new.keys():
            _pairs(old[k], new[k], f"{path}/{k}", out)
    elif isinstance(old, str) and isinstance(new, str) and old != new and _HEX.fullmatch(old):
        stamp = path.endswith(("/model_hash", "/content_hash")) or path == (
            "provenance.json/settings/titleblock/values_sha256_16"  # the renamed field (Q28)
        )
        if stamp and _HEX.fullmatch(new):
            out[old] = new


def stamp_map(old: Files, new: Files) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in ("system/export.json", "manifest.json", "system/provenance.json"):
        if rel in old and rel in new:
            _pairs(old[rel]["json"], new[rel]["json"], rel.removeprefix("system/"), out)
    model = {o: n for o, n in out.items() if len(o) == 64}
    out.update({o[:12]: n[:12] for o, n in model.items()})  # the 12 characters of the stamp
    return out


def _map_strings(value: Any, fn: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [_map_strings(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: _map_strings(v, fn) for k, v in value.items()}
    return value


def apply_stamp(files: Files, hashes: dict[str, str]) -> Files:
    if not hashes:
        return files
    pattern = re.compile("|".join(re.escape(h) for h in sorted(hashes, key=len, reverse=True)))

    def fix(text: str) -> str:
        return pattern.sub(lambda m: hashes[m[0]], text)

    out: Files = {}
    for rel, entry in files.items():
        entry = dict(entry)
        for key in ("text", "items", "json", "sheets", "texts"):
            if key in entry:
                entry[key] = _map_strings(entry[key], fix)
        out[rel] = entry
    return out


# ---- step 3: the word list ----------------------------------------------------------------------


def _compile(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{L\}|\{L2\}|\{\*\}|\{field\}|\{\^\})", template)
    out = []
    for p in parts:
        out.append(
            {
                "{L}": _LETTER,
                "{L2}": _LETTER,
                "{*}": "(.*?)",
                "{field}": "([^,\n]*)",
                "{^}": "^",
            }.get(p, re.escape(p))
        )
    return re.compile("".join(out), re.M)


def _replacer(old: str, new: str) -> Callable[[re.Match[str]], str]:
    """The replacement of one match: {V} and {V2} are the versions of the letters, {*} and {field}
    the kept texts, in the order they appear."""
    slots = re.findall(r"\{L\}|\{L2\}|\{\*\}|\{field\}", old)

    def repl(m: re.Match[str]) -> str:
        values = {s: g for s, g in zip(slots, m.groups(), strict=True) if s in ("{L}", "{L2}")}
        kept = iter(g for s, g in zip(slots, m.groups(), strict=True) if s in ("{*}", "{field}"))

        def one(token: re.Match[str]) -> str:
            t = token[0]
            if t in ("{V}", "{V2}"):
                letter = values["{L}" if t == "{V}" else "{L2}"]
                version = letter_to_version(letter)
                assert version is not None, letter
                return version
            if t in ("{*}", "{field}"):
                return next(kept)
            return "" if t == "{^}" else t

        return re.sub(r"\{V\}|\{V2\}|\{\*\}|\{field\}|\{\^\}", one, new)

    return repl


def _apply_one(
    change: dict[str, Any], rel: str, entry: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    pattern, repl = _compile(change["old"]), _replacer(change["old"], change["new"])
    count = 0
    entry = copy.deepcopy(entry)
    scope = change["scope"]
    if scope == "text" and "text" in entry:
        entry["text"], count = pattern.subn(repl, entry["text"])
    elif scope == "item" and "items" in entry:
        index = -1  # the text is the last part of an item (SVG: attributes, text; PDF: ..., text)
        previous = None
        for item in entry["items"]:
            text = item[index]
            m = pattern.fullmatch(text)
            if m and (change.get("after") is None or previous == change["after"]):
                item[index] = repl(m)
                count += 1
            previous = item[index]
    elif scope == "cell" and "sheets" in entry:
        for name, sheet in entry["sheets"].items():
            if change.get("sheets") and name not in change["sheets"]:
                continue
            for ref, value in sheet["cells"].items():
                m = pattern.fullmatch(value)
                if m:
                    sheet["cells"][ref] = repl(m)
                    count += 1
    elif scope == "export" and "json" in entry:
        for h in entry["json"].get("harnesses", []):
            letter = h.get("revision")
            version = letter_to_version(letter) if isinstance(letter, str) else None
            if version is not None and version != letter:
                h["revision"] = version
                h["version"] = version  # the key of format 3, written beside the older name (Q29)
                count += 1
    return entry, count


def apply_word_changes(files: Files, used: list[int]) -> Files:
    out = dict(files)
    for n, change in enumerate(word_changes()):
        for rel in sorted(out):
            if any(fnmatch.fnmatchcase(rel, p) for p in change["files"]):
                out[rel], count = _apply_one(change, rel, out[rel])
                used[n] += count
    return out


# ---- step 4: what follows from the length of a replaced text ----------------------------------------


_FIELD_LINE = re.compile(r"  - ([a-z_]+): ")


def _resort_field(text: str, field: str = "version") -> str:
    """The comparisons of the version report list the changed fields of an object sorted by name.
    The field `revision` is `version` in format 3 (Q28), so after the word list its line is out of
    that order: put that one line back at its place in the run of field lines it belongs to. Only
    a run that holds a line of `field` is touched, and only that line moves."""
    lines = text.split("\n")
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        names = [m[1] for line in run if (m := _FIELD_LINE.match(line))]
        if field in names:
            line = run.pop(names.index(field))
            rest = [_FIELD_LINE.match(x)[1] for x in run]  # type: ignore[index]
            at = next((i for i, name in enumerate(rest) if name > field), len(run))
            run.insert(at, line)
        out.extend(run)
        run.clear()

    for line in lines:
        if _FIELD_LINE.match(line):
            run.append(line)
            continue
        flush()
        out.append(line)
    flush()
    return "\n".join(out)


# ---- the comparison -----------------------------------------------------------------------------


# ---- step 6: the older name dropped in 4.0.0 --------------------------------------------------------


EXPORT = "system/export.json"


def drop_older_name(files: Files) -> Files:
    """`export.json` as 4.0.0 writes it from the file of 3.0 after the word list: each harness
    without the key `revision`, which the list keeps beside `version` as 3.0.x wrote it, and
    `format_version` 2."""
    if EXPORT not in files or "json" not in files[EXPORT]:
        return files
    doc = copy.deepcopy(files[EXPORT]["json"])
    for h in doc.get("harnesses", []):
        h.pop("revision", None)
    doc["format_version"] = 2
    return {**files, EXPORT: {**files[EXPORT], "json": doc}}


# ---- step 7: every shield group of a wire, 4.1.0 -------------------------------------------------

SHIELD_HEADING, WIRE_HEADING = "Shield group", "Wire"
_CUT_WIDTH_CAP = 46.0  # the cap of the build workbook's column widths
_DIGITS = re.compile(r"(\d+)")


def _natural(text: str) -> list[Any]:
    return [int(p) if p.isdigit() else p for p in _DIGITS.split(text)]


def shield_groups(name: str) -> dict[str, dict[str, str]]:
    """For each harness of a recorded project, each wire's shield groups in natural ID order,
    joined by `;` (the rule of 4.1.0, stated here a second time; never imported from the tool)."""
    import tempfile

    from tools.format3_record import projects

    with tempfile.TemporaryDirectory() as tmp:
        project = projects(FIXTURES)[name](Path(tmp))
    out: dict[str, dict[str, str]] = {}
    for h in project.harnesses.values():
        seen: dict[str, list[str]] = {}
        for s in sorted(h.shields, key=lambda x: _natural(x.id)):
            for wid in s.wire_ids:
                if s.id not in seen.setdefault(wid, []):
                    seen[wid].append(s.id)
        out[h.id] = {wid: ";".join(ids) for wid, ids in seen.items()}
    return out


def _takes(old: str, new: str) -> bool:
    """A 2.x cell the step may change: it named one of the groups now listed."""
    return old != new and old in new.split(";")


def _csv_groups(text: str, groups: dict[str, str]) -> str:
    lines = text.split("\n")
    head: list[str] | None = None
    for n, line in enumerate(lines):
        if not line or line.startswith("#"):
            continue
        row = next(csv.reader([line.rstrip("\r")]))
        if head is None:
            head = row
            continue
        if SHIELD_HEADING not in head or WIRE_HEADING not in head or len(row) != len(head):
            continue
        k, w = head.index(SHIELD_HEADING), row[head.index(WIRE_HEADING)]
        if w in groups and _takes(row[k], groups[w]):
            row[k] = groups[w]
            buf = io.StringIO()
            csv.writer(buf, lineterminator="").writerow(row)
            lines[n] = buf.getvalue() + ("\r" if line.endswith("\r") else "")
    return "\n".join(lines)


def _sheet_groups(sheet: dict[str, Any], groups: dict[str, str], widen: bool) -> dict[str, Any]:
    cells = dict(sheet["cells"])
    cols = {
        v: k.rstrip("0123456789")
        for k, v in cells.items()
        if k.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == "1"
    }
    if SHIELD_HEADING not in cols or WIRE_HEADING not in cols:
        return sheet
    sc, wc = cols[SHIELD_HEADING], cols[WIRE_HEADING]
    widths = dict(sheet["widths"])
    for ref, wid in sheet["cells"].items():
        if ref.rstrip("0123456789") != wc or ref[len(wc) :] == "1" or wid not in groups:
            continue
        at = f"{sc}{ref[len(wc) :]}"
        if _takes(cells.get(at, ""), groups[wid]):
            cells[at] = groups[wid]
            if widen and sc in widths:
                widths[sc] = min(_CUT_WIDTH_CAP, max(widths[sc], len(groups[wid]) + 2.0))
    return {**sheet, "cells": cells, "widths": widths}


def every_shield_group(files: Files, groups: dict[str, dict[str, str]]) -> Files:
    """The files of 3.0 after the step of 4.1.0 (step 7 of the module text)."""
    out = dict(files)
    for rel, entry in files.items():
        parts = rel.split("/")
        if len(parts) != 3 or parts[0] != "harnesses" or parts[1] not in groups:
            continue
        hid, g = parts[1], groups[parts[1]]
        if parts[2] == "wirelist.csv" and "text" in entry:
            out[rel] = {**entry, "text": _csv_groups(entry["text"], g)}
        for fname, sheet, widen in ((f"{hid}.xlsx", "Wire list", False),
                                    (f"{hid}_build.xlsx", "Cut list", True)):  # fmt: skip
            if parts[2] == fname and sheet in entry.get("sheets", {}):
                sheets = {**entry["sheets"], sheet: _sheet_groups(entry["sheets"][sheet], g, widen)}
                out[rel] = {**entry, "sheets": sheets}
    return out


# ---- step 8: the Production sheet and the length reference, 4.1.0 --------------------------------

PRODUCTION = "Production"
PRODUCTION_LINE = (
    "one block per connector: where each wire goes, its part, colour, gauge, length, label and "
    "shield"
)
LENGTH_LINES = (
    "Lengths run from the rear of a connector, where the wires leave its body or backshell.",
    "They follow the routing segments through the centre of each branch point to the rear of the "
    "other connector.",
    None,  # "A wire Generate made adds …." with the project's service loops
    '"Locked" is a length a person typed; "segments only" has no service loops.',
)
LOOPS_LINE = ("A wire Generate made adds ", ".")
LENGTH_HEADINGS = {
    "Cut list": ("Length (m)", "Length (m), rear to rear"),
    "Routing": ("Length (m)", "Length (m), rear or branch centre"),
}
BUILD_SHEET_MEMBERS = (
    "[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/styles.xml",
)  # fmt: skip
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _row(ref: str) -> int:
    return int(ref.lstrip(_LETTERS))


def _col(ref: str) -> str:
    return ref.rstrip("0123456789")


def _insert_rows(cells: dict[str, str], at: int, n: int) -> dict[str, str]:
    """The cells with every row from `at` on moved down by `n` rows."""
    return {(f"{_col(k)}{_row(k) + n}" if _row(k) >= at else k): v for k, v in cells.items()}


def _length_lines(new_entry: dict[str, Any]) -> list[str] | None:
    """The four sentences, the third read from the cut list of 4.1.0 when it has its form."""
    cells = new_entry.get("sheets", {}).get("Cut list", {}).get("cells", {})
    last = max((_row(k) for k in cells if _col(k) == "A"), default=0)
    third = cells.get(f"A{last - 1}", "")
    head, tail = LOOPS_LINE
    if not (third.startswith(head) and third.endswith(tail) and len(third) > len(head + tail)):
        return None
    return [line if line is not None else third for line in LENGTH_LINES]


def _start_here(cells: dict[str, str], lines: list[str]) -> dict[str, str]:
    at = next((_row(k) for k, v in cells.items() if _col(k) == "A" and v == "Released on"), None)
    if at is None:
        return cells
    cells = _insert_rows(cells, at + 1, len(lines))
    for n, line in enumerate(lines):
        if n == 0:
            cells[f"A{at + 1}"] = "Lengths"
        cells[f"B{at + 1 + n}"] = line
    after = [_row(k) for k, v in cells.items() if _col(k) == "A" and v in ("Cut list", "Routing")]
    if after:
        at = max(after)
        cells = _insert_rows(cells, at + 1, 1)
        cells[f"A{at + 1}"], cells[f"B{at + 1}"] = PRODUCTION, PRODUCTION_LINE
    return cells


def _ends_with_lines(sheet: dict[str, Any], name: str, lines: list[str]) -> dict[str, Any]:
    old, new = LENGTH_HEADINGS[name]
    cells, widths = dict(sheet["cells"]), dict(sheet["widths"])
    at = next((k for k, v in cells.items() if _row(k) == 1 and v == old), None)
    if at is None:
        return sheet
    cells[at] = new
    if _col(at) in widths:
        widths[_col(at)] = min(_CUT_WIDTH_CAP, max(widths[_col(at)], len(new) + 2.0))
    first = max(_row(k) for k in cells) + 2  # after an empty row
    for n, line in enumerate(lines):
        cells[f"A{first + n}"] = line
    return {**sheet, "cells": cells, "widths": widths}


def production_sheet(old: Files, new: Files) -> Files:
    """The files of 3.0 after the step of 4.1.0 for the build workbook (step 8 of the module
    text)."""
    out = dict(old)
    for rel, entry in old.items():
        if not rel.endswith("_build.xlsx") or rel not in new or "sheets" not in entry:
            continue
        lines = _length_lines(new[rel])
        if lines is None or PRODUCTION not in new[rel].get("sheets", {}):
            continue
        sheets = dict(entry["sheets"])
        if "Start here" in sheets:
            here = sheets["Start here"]
            sheets["Start here"] = {**here, "cells": _start_here(dict(here["cells"]), lines)}
        for name in LENGTH_HEADINGS:
            if name in sheets:
                sheets[name] = _ends_with_lines(sheets[name], name, lines)
        sheets[PRODUCTION] = new[rel]["sheets"][PRODUCTION]
        members = dict(entry.get("members", {}))
        for m in BUILD_SHEET_MEMBERS:
            if m in members and m in new[rel].get("members", {}):
                members[m] = new[rel]["members"][m]
        out[rel] = {**entry, "sheets": sheets, "members": members}
    return out


# ---- step 9: the number of rules, 4.2.0 ---------------------------------------------------------

DRC_REPORT = "system/drc_report.md"
RULES_BEFORE = 39  # the number of design rules of 2.x, which the record holds
_RULES_LINE = re.compile(r"(?m)^(Model hash: `[0-9a-f]{12}`\. Rules run: )(\d+)(\.)$")


def rule_count(files: Files, rules: int | None = None) -> Files:
    """The files of 3.0 after the step of 4.2.0 (step 9 of the module text): the one line
    `Model hash: `...`. Rules run: 39.` of the DRC report says `rules` (the number of rules of this
    tool) in place of 39. A report without exactly one such line, or with another number, is left
    as it is, so the comparison reports it."""
    if DRC_REPORT not in files or "text" not in files[DRC_REPORT]:
        return files
    if rules is None:
        from harness_design_studio.core.drc import RULES

        rules = len(RULES)
    text = files[DRC_REPORT]["text"]
    found = _RULES_LINE.findall(text)
    if len(found) != 1 or found[0][1] != str(RULES_BEFORE):
        return files
    text = _RULES_LINE.sub(lambda m: f"{m.group(1)}{rules}{m.group(3)}", text)
    return {**files, DRC_REPORT: {**files[DRC_REPORT], "text": text}}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def comparable(entry: dict[str, Any]) -> dict[str, Any]:
    """What is compared of one file: its readable content, and for a workbook the hash of each
    member that holds no sheet (its sheets are compared by their cells and widths)."""
    out: dict[str, Any] = {
        k: entry[k] for k in ("text", "items", "json", "sheets", "texts") if k in entry
    }
    if "members" in entry:  # the others: the styles, the workbook, the relations
        out["members"] = {
            n: h
            for n, h in entry["members"].items()
            if not n.startswith("xl/worksheets/") and n != "docProps/core.xml"
        }
    if not out:  # a file of another kind: by its digest
        out["sha256"] = entry["sha256"]
    return out


def compare(
    old: Files,
    new: Files,
    raw: dict[str, bytes],
    used: list[int],
    old_version: str = "",
    groups: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """The differences that are left after the steps of section 5.6, one line each."""
    hashes = stamp_map(old, new)  # 1
    if old_version and old_version != __version__:
        # the tool version of the stamp, where the record keeps it as written (cells and the text
        # items of drawings; the texts are kept with the version read as the base version)
        hashes[f"harness-design-studio {old_version}"] = f"harness-design-studio {__version__}"
    old = apply_stamp(old, hashes)
    if OLD_REPORT in old:  # 2
        old[NEW_REPORT] = old.pop(OLD_REPORT)
    old = apply_word_changes(old, used)  # 3
    if NEW_REPORT in old:  # 4
        old[NEW_REPORT] = {**old[NEW_REPORT], "text": _resort_field(old[NEW_REPORT]["text"])}
    old = drop_older_name(old)  # 6
    if groups is not None:  # 7
        old = every_shield_group(old, groups)
    old = production_sheet(old, new)  # 8
    old = rule_count(old)  # 9
    problems: list[str] = []
    if "manifest.json" in old and "manifest.json" in new:  # 5
        a, b = copy.deepcopy(old["manifest.json"]["json"]), new["manifest.json"]["json"]
        for f in a["files"]:
            if f["path"] == OLD_REPORT:
                f["path"] = NEW_REPORT
        a["files"] = sorted(a["files"], key=lambda f: f["path"])
        for f in b["files"]:
            data = raw.get(f["path"])
            if data is None or (f["sha256"], f["bytes"]) != (_sha(data), len(data)):
                problems.append(f"manifest.json: {f['path']}: the hash or size is not the file's")
        strip = [{k: v for k, v in f.items() if k not in ("sha256", "bytes")} for f in b["files"]]
        if [
            {k: v for k, v in f.items() if k not in ("sha256", "bytes")} for f in a["files"]
        ] != strip:
            problems.append("manifest.json: the list of files is not the list of 2.x")
        a, b = {**a, "files": None}, {**b, "files": None}
        if a != b:
            problems.append("manifest.json differs")
        old.pop("manifest.json")
    for rel in sorted(set(old) | set(new)):
        if rel == "manifest.json":
            continue
        if rel not in new or rel not in old:
            problems.append(f"{rel}: {'missing in 3.0' if rel not in new else 'new in 3.0'}")
        elif comparable(old[rel]) != comparable(new[rel]):
            problems.append(f"{rel}: differs")
    return problems


def dump_now(name: str) -> tuple[Files, dict[str, bytes]]:
    """The files this tool writes for a recorded project, dumped as the record holds them, and
    their bytes."""
    import tempfile

    from tools.format3_record import dump_file, projects, written_files

    with tempfile.TemporaryDirectory() as tmp:
        project = projects(FIXTURES)[name](Path(tmp))
        files = written_files(project, Path(tmp))
    return {r: dump_file(r, d) for r, d in files.items()}, files
