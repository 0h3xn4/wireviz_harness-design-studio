# Design of 2.2.0: the device library

Written on 2026-11-17 from a reading of the code at 2.1.1 (prepared). Decision D-240 records it; D-234 is the owner decision it implements, D-235 the order of the 2.x releases. *Added 2026-11-17, later:* pull request 1 of section 6 is built (D-240): `core/device_file.py`, the checks across the folder in `core/library_folder.py`, `core/library_git.py`, `core/library_pointer.py` and the two schemas. *Added 2026-11-17, later:* pull request 2 is built: `core/library_link.py` (the libraries of a project, the states, add with the record, the diff, the update plan, the save that links), and the editor's two ways of adding a device write the record through it. *Added 2026-11-17, later:* pull request 3 is built: the commands `libraries`, `add-device`, `update-device` and `save-device` (`cli/library.py`), `imports` with the project's libraries, `explain DIR DEVICE`, their JSON keys and `docs/CLI.md`; `import-devices` is unchanged. *Added 2026-11-17, later:* pull request 4 is built: the editor screens of section 3 item 5 (`gui/library_review.py`: the *Status* column and the source line of the library window, the chip on a device, the notice when a project opens, the review dialog, the choices for a taken ID, *From library* in the pickers and on Ctrl+K, *Settings > Project > Device libraries of this project*, *Save As* with `device-libraries.json`). *Added 2026-11-17, later:* pull request 5 is built: the end-to-end test of section 5 (`tests/test_e2e_device_library.py`), the library window's list of the project's libraries (it showed only the person's folder), the advice of `imports` for a changed device file, and the documents (`docs/FILE_FORMAT.md`, `docs/IMPORTS.md`, `docs/user-manual/use-the-library.md`, the in-app guide, the changelog). The end-to-end test found the design held, with two notes: the same sequence in two folders gives byte-identical project files except `journal.jsonl`, whose entries carry the time of each change by design (they are equal without it); and `imports --check` told a person to import a changed device file again, which `import-devices` would do under a new ID, so it now names `update-device`. Pull requests 1 to 5 are built; only pull request 6, the preparation of 2.2.0, is left. *Added 2026-11-17, after the publication of 2.1.1:* 2.1.1 is published as the latest full release (annotated tag `v2.1.1` on `5e99d3d`; `compliance/SIGNOFF.md`, *Publication of 2.1.1*); its program is the one this design was read from. *Added 2026-11-17, later:* pull request 6 prepares version 2.2.0 (decision D-244: a minor release, no format change, no release candidate first); it is not tagged yet. Paths are relative to `src/harness_design_studio/` unless they start with `docs/` or `tests/`.

## 1. What exists

About three quarters of D-234 is in the program already.

| Area | What is there | Use in 2.2.0 |
|---|---|---|
| Device file | `core/device_library.py`: format `harness-device-library`, version 1 (D-165); size and count caps; `read_library` and `check_library` (strict JSON, a newer version refused); `write_library`; `export_devices` brings the parts, mating parts, contact parts and carried interface types, so a device is complete on its own; `_portable` leaves out `interface_id`, `locked` and allocated signals; `find_conflicts`; `merge_with_notes` (never lowers a part's approval); `plan_device_import` (a taken ID gets the next free one; the project's parts and types are kept, with a note) | It is already the format of `NAME.device.json`; it gets a one-device rule and a file name |
| Library folder | `core/library_folder.py`: `scan_folder` never raises (every bad file is a `LibraryProblem`); JSON files of another format are skipped; hidden folders and links are not followed; depth 3; at most 2000 files; `save_devices`, `describe_entry` | Scan, preview and save, with the rules of section 2 |
| The person's folder | the editor's setting `library/folder` (`gui/library_window.py`, `gui/main_window.py`, `gui/app.py`) | Stays the editor's own; the command line does not read user settings |
| Import record | `core/model/imports.py` `ImportRecord` (kind `devices` exists in format 2; `source_name`; `source_path` only inside the project; `sha256`; `notes`); id `<kind>:<file name>`; `core/import_record.py` `record_ops`, `check_sources`, `CachedHasher`; outside the model hash (`core/io/layout.py`) | The record of where a device came from; `import-devices` writes it already |
| A gap | The editor's two ways of adding a device from a library (`gui/library_window.py` `plan_add`/`add_flow`, `gui/main_window.py` `add_from_library_flow`) write no import record | One core function adds a device and writes the record, for the command line and the editor |
| Git without `git` | `core/vcs/gitinfo.py` `last_commit`; `core/vcs/gitobjects.py` `open_repo`, `head_file` | The library's commit, and whether the device file equals the file in HEAD |
| Locks | `core/vcs/locks.py` `check_locks` (run by `History.execute`); `COSMETIC_UNIT_FIELDS`; `core/devices.py` `pin_set_frozen`, `pin_lock_reason`, `connector_delete_impact`, `pin_impact` | The update shows locked rows and refuses them |
| Copies | `core/copies.py` (`ID-R`, `ID-3`) | Copies follow their library device |
| Pickers | `edit.TEMPLATES`, `ops_add_unit`; the pickers of the diagram, the main window and the device dialogs | A *From library* section |
| Project files | The loader reads only the managed files; the saver deletes only managed files; `.gitattributes` and `extensions/` are outside the project format (`docs/FILE_FORMAT.md`) | A top-level `device-libraries.json` is never read, deleted or hashed by 2.0, 2.1 or 2.2's project code (not in `library/`, which holds parts files, nor in `extensions/`) |

## 2. The library

A library folder holds `NAME.device.json` files in the folder and up to two levels below it. It may also hold the multi-device files and subsystem files of 2.1, which are still read. The folder is not part of a project; its file formats are versioned on their own.

**`NAME.device.json`** is a `harness-device-library` file, version 1, unchanged, so a 2.1 tool reads a 2.2 library. The rules of 2.2:

- `devices` holds exactly one device, and `NAME` equals `unit.id`. Case counts, but two names that differ only in case are refused (Windows).
- Every connector has `role: "box"`, `unit_id` equal to the device, and an ID `<device>-<tail>`.
- The file is complete on its own: every part, contact part and mating part it names, and every interface type its connectors carry, is in the file.
- No `interface_id`, no `locked: true`, no `zone`; no unknown top-level key; values checked with the strict models.
- What a device carries: the unit (id, name, subsystem, side, `mass_relevant`, notes, `kind` for its look) and its connectors with every pin (signal, the port names of 2.1.0 included, `fixed`, function, contact size, termination, contact part, role, direction), the parts and the interface types.

**`library.json`** (optional) gives the library a stable name across clones: `{"format": "harness-device-library-folder", "version": 1, "name": "ACME devices", "description": "…"}`. Without it, the name is the folder's name.

**Checks across the folder:** a device ID in two files refuses both, and the message names both files; two files with the same file name in different subfolders are refused (the record is keyed by file name); one part ID with different data in two files is a warning that names the fields.

**Trust:** the folder is data. Only `*.json` is read; nothing is imported or run. The caps stay (8 MB per file, 2000 files, depth 3, no links, no hidden folders). JSON is read strictly (a key twice, NaN, lone surrogates refused). Every bad file is one sentence, and the other files are still offered. `.git` is read only through the capped readers.

**Schemas:** `schema DIR` also writes `device-file.schema.json` and `device-libraries.schema.json`.

**How a library is found**, in this order:

1. `--library FOLDER` on the command line (repeatable; replaces the rest);
2. the project's `device-libraries.json`: `{"format": "harness-project-libraries", "version": 1, "device_libraries": [{"path": "../acme-device-library"}]}` (relative paths with `/`; absolute paths and `~` refused; at most 8 entries; unknown keys refused; a library inside the project folder, such as a Git submodule, is allowed);
3. in the editor only, the person's library folder.

A device found in two libraries is refused as ambiguous, never chosen.

## 3. Workflows

**What links a project device to the library** (no new field): the project has an import record `devices:<file>`, that file holds device `D` in one of the project's libraries, and the device's ID is `D` or a copy of `D` (`D-R`, `D-3`). A device added under another ID is an unlinked copy.

**States** (a pure function): not in the project; up to date (same SHA-256 and the same library-owned fields); library changed (SHA-256 differs and fields differ); changed here (same SHA-256, fields differ); same ID, not from the library (no record); source not found. Library-owned fields: the connectors with their pins in portable form, and `kind`, `mass_relevant`, `notes`. Project-owned fields (never shown as differences): name, subsystem, zone, side, the placement, and on each pin `interface_id`, `locked` and allocated signals. With no common base, "changed on both sides" cannot be told apart; the diff shows both sides.

1. **Save a device to the library** (`save-device DIR D [--library F] [--replace]`; *Save to library…*): into the file that holds `D`, else `<D>.device.json` at the library root. A different device of the same ID is refused unless `--replace` or a new ID. The project then gets the record of the written file (with the note *not committed*). The tool never commits.
2. **Add a device from the library** (`add-device DIR NAME… [--count N] [--as ID] [--dry-run]`; the library window; *From library* in the pickers): NAME is the device ID or a unique `unit.name`. One undo step: the device, its connectors, the parts and types the project lacks, the placement, copies and the record, from the same core function for the command line and the editor. A taken ID: linked, it says so (use `--count` for copies); not linked, it is refused with the diff and the choices *adopt* or `--as NEWID`.
3. **Update** (`update-device DIR [NAME…|--all] [--apply] [--check] [--adopt] [--json]`; *Review library changes…*): without `--apply` it only shows the diff and changes nothing; `--check` ends with exit code 1 while a linked device differs. The diff has one row per changed field (connector, pin, field, in this project, in the library, locked by), and the impacts (interfaces, wires and links on removed pins; *Generate again* for drafts). Applying is all or nothing per device: it changes the device and its copies, keeps the project-owned fields and the allocations of pins that still exist, adds missing parts and types, and replaces the record. A change that a released harness locks refuses the whole device and names the harness (`revise`); `check_locks` is the last check.
4. **Conflicts:** the project's part is always kept; a different `category` or `pin_count` refuses the add or update; other differences are notes; approvals never change; project-wide parts and interface types are never replaced (D-12, D-165).
5. **Editor:** a *Status* column and the source line in the library window; a chip on the device (*From ACME devices, PCDU00.device.json, up to date*); a notice when a project opens and a library has a newer version (it never applies anything); the review dialog (*Take the library's version*, *Keep this project's*, *Save this project's to the library…*); *Settings > Project > Device libraries* writes `device-libraries.json` at once, outside undo, and says so; *Save As* copies it and rewrites the paths.
6. Generate, export, verify and the checks never read a library folder. `imports DIR` checks `devices` records against the project's libraries; `explain DIR D` names the record.

New commands: `libraries DIR [--add F] [--remove F] [--devices] [--json]`, `add-device`, `update-device`, `save-device` (a new module `cli/library.py`). `api.__all__` is unchanged.

## 4. No format change

| What | Where | Why it is not a format change |
|---|---|---|
| The library file | outside the project | It has its own version (D-165) and stays at 1 |
| Name of the library device | `ImportRecord.id` (`devices:PCDU00.device.json`), `source_name` | Existing fields, existing meaning (the file name) |
| Version of the device | `ImportRecord.sha256` of the file | Meaning unchanged; `check_sources` already uses it |
| Path | `source_path` only for a library inside the project, relative; else a note | Meaning unchanged: never absolute |
| Commit, library name, path in the library, *not committed* | `ImportRecord.notes`, fixed-form lines | `notes` holds "other things the import read from the source"; the program never parses notes: the link uses only the id, `source_name` and `sha256` |
| The project's libraries | `device-libraries.json` at the project root | Not managed, not hashed, not deleted by a save; older tools never see it |
| The record | `imports/records.json` | Outside the model hash and every output; the kind `devices` exists in format 2; no new kind (the kind list is checked) |

Only a format 3 would allow linking a device that the project names differently from the library (PCDU1 from PCDU00), or a revision per device. The smallest option is a sparse `Unit.library` field. It is left for later (owner question Q1). Existing projects have no record and no pointer file, so the same bytes, model hash and outputs.

## 5. Tests first

- `tests/test_device_folder.py`: the one-device and name rules, completeness, unknown keys, a device in two files, a file name twice, a part conflict across files, `library.json`, caps, links, hidden folders, a key twice, NaN, a version-2 file, `.py` files ignored (nothing imported), one bad file never hides the good ones, a 2.1 multi-device file still offered.
- `tests/test_library_pointer.py`: read and write of `device-libraries.json`, relative paths only, refusals; a project with the file loads with the same model hash and no issue; a save leaves the file byte-identical; Save As rewrites the paths.
- `tests/test_library_link.py`: every state; add writes the record; the diff of each kind of field; project-owned fields kept; copies follow; adopt; an ambiguous name; a `pin_count` conflict refuses; approval never changes; a locked pin refuses with the harness named; a removed pin used by a link names the link; undo restores the device and the record.
- `tests/test_library_git.py` (skips without `git`): the commit and branch note; *not committed*; a damaged `.git` reads as *not readable*, never an error.
- `tests/test_schemas.py`, `tests/test_ui_device_library.py`, `tests/test_ui_library_window.py`.
- **End-to-end through the command line** (`tests/test_e2e_device_library.py`): save two devices into a library folder, `git init` and commit; a blank project points to the library; `add-device`; an interface; `generate`, `export`, `verify --outputs`; change a device in the library and commit; `libraries --devices` shows *library changed*; `update-device` shows the rows and changes no byte; `--check` exits 1; `--apply` changes the device and the record; the next `--check` exits 0; a second Generate changes nothing; two exports are byte-identical; the same sequence in two folders gives identical project files; after a release, a change of a used pin is refused.
- Guards: the output-hash baseline stays identical; the security tests (no network, no subprocess in the core); the command-line docs and the JSON keys stay in sync.

## 6. Pull requests

| PR | Content |
|---|---|
| 1 | Folder rules, strict checks across the folder, `library.json`, the Git state of a library, `device-libraries.json` read and write, two schemas, `save_devices` writing `.device.json`; this page; D-240. No caller yet |
| 2 | `core/library_link.py`: add with the record, the states, the diff, the update plan (locks, impacts, copies, adopt), the save that links |
| 3 | Command line: `libraries`, `add-device`, `update-device`, `save-device`; `imports` and `explain`; JSON keys; `docs/CLI.md` |
| 4 | Editor: status and source, the chip, the notice, the review dialog, *From library* in the pickers, the record from both ways of adding, the Settings list, Save As |
| 5 | The end-to-end test; `FILE_FORMAT.md`, `IMPORTS.md`, a user manual page, the in-app guide, CHANGELOG; the project's libraries in the library window |
| 6 | The preparation of 2.2.0 |

Pull requests 1 to 5 are built (D-240); 6 is the preparation of the release, with its own decision. *Added 2026-11-17, later:* 6 is done, with decision D-244.

## 7. Risks

- **No common base:** "changed on both sides" cannot be detected; nothing is applied without a request. Later: find the base in the library's Git history by its SHA-256. *What the tests showed:* `update-device` without `--apply` left every file of the project as it was, and `--check` ended with 1 until `--apply` (`tests/test_e2e_device_library.py`); a change on both sides is shown as *library changed* with both values in the row; no test can give it a base.
- **The record is keyed by file name:** duplicate file names are refused at the scan. *What the tests showed:* two files of the same name in two subfolders, and two names that differ only in case, are both refused (`tests/test_device_folder.py`).
- **A 2.1 tool can save `<ID>.json` next to `<ID>.device.json`:** 2.2 refuses the device in two files and names both; the release notes say to update the team. *What the tests showed:* a device in two files is offered from neither and both files are named, and a 2.1 file of several devices is still offered (`tests/test_device_folder.py`).
- **`.bak` files** that `write_library` keeps: the user manual suggests `*.bak` in the library's `.gitignore`. *What the tests showed:* the end-to-end library has that `.gitignore` and is committed with Git; whether a `.bak` stays out of a commit is Git's, so no test of ours checks it.
- **A hostile library:** caps, strict checks, data only, capped Git readers; tested. *What the tests showed:* the caps hold, links and hidden folders are not followed, a `.py` file is never imported, a key twice, NaN and a lone surrogate are refused, one bad file never hides the good ones (`tests/test_device_folder.py`, `tests/test_library_trust_181.py`), and a damaged `.git` reads as *not readable*, never an error (`tests/test_library_git.py`).
- **A hand-edited `records.json`** can break a link; the device then shows as *same ID, not from the library*, never as a wrong update. *What the tests showed:* a device of the library's ID without a record is *same ID, not from the library*, and `--apply` without `--adopt` refuses it and changes nothing (`tests/test_library_link.py`, `tests/test_library_cli.py`).

## 8. Owner questions (answered by the recommendation)

- **Q1. Which project devices follow the library?** The device whose ID is the library name, and its copies. A device added under another ID is an unlinked copy in 2.2.0. The alternative is a sparse `Unit.library` field in a format 3.
- **Q2. May a project hold `device-libraries.json`?** Yes: relative paths, outside the project format, not undoable, ignored by older tools. The person's folder stays for the editor; `--library` covers the command line.
