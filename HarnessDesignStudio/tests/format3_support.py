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
   is that of the file of 3.0.

Workbooks are compared cell by cell with their column widths and the hash of each member that
holds no cell (styles, workbook); drawings by their text items and positions; JSON files by their
content; every other file as text. Any other difference is reported."""

import copy
import fnmatch
import hashlib
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
    old: Files, new: Files, raw: dict[str, bytes], used: list[int], old_version: str = ""
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
