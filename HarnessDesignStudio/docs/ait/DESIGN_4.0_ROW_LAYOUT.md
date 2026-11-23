# Design of 4.0.0: the row layout of a connector

Written on 2026-11-19 from a reading of the code at `2d9f2cf` (master: the published 3.0.0, tag `v3.0.0` on `711f204`, and its publication record). The owner's decision that it follows is D-250; the decision that records this design is D-251. It was written as a design only: no file format, key or `SCHEMA_VERSION` changed with the page itself. Paths are relative to `src/harness_design_studio/` unless they start with `docs/` or `tests/`. Its form follows the design of 3.0.0 ([`DESIGN_3.0_HARNESS_PLAN.md`](DESIGN_3.0_HARNESS_PLAN.md)): the decision, what exists, the model, the format step and its proof, the outputs, the editor and the command line, the pull requests, the risks, the owner questions and what was not checked. Choices that are not the owner's are made here and say why; the four choices that are the owner's are L1 to L4 (section 16), each with a recommendation; the owner accepted the four recommendations on 2026-11-19.

**Status (2026-11-20):** pull requests 1 to 6 and R of section 14 are merged on `master`: 1 (*Format 4*) as #294, 2 (*Core*) as #295, 3 (*Outputs*) as #296, 4 (*Command line and imports*) as #297, 5 (*Editor*) as #298, R (the older names of 3.0.x dropped) as #299 and 6 (the end-to-end test and the documents) as #300. Pull request 1 was merged only after 3.0.1 and 3.1.0 were tagged, because `master` writes format 4 from its merge (section 15). Where each differs from this page is under section 14. Pull request 7 is the preparation of 4.0.0, merged as #304 from the branch `release/4.0.0` (decision D-254): the version 4.0.0, the changelog section, the release notes, the decision row and the status pages. 4.0.0 is published (2026-11-20; annotated tag `v4.0.0` on `c0e0250`, the merge of #304, made by the tag workflow of D-227, run 44699479126; release workflow run 44699532086; `compliance/SIGNOFF.md`, *Publication of 4.0.0*), so format 4 is frozen since the tag `v4.0.0`. The patch release 4.0.1 (decision D-255; published 2026-11-20, annotated tag `v4.0.1` on `d45da91`, the merge of #308, made by the tag workflow of D-227, run 44741420907; release workflow run 44741460590; `compliance/SIGNOFF.md`, *Publication of 4.0.1*) writes format 4 unchanged: its one fix, pull request 306, lets every label format pass the export's self-check, and nothing of this design changes. The minor release 4.1.0 (decision D-257; published 2026-11-21, annotated tag `v4.1.0` on `cb43f31`, the merge of #320, made by the tag workflow of D-227, run 44845357892; release workflow run 44845387838; `compliance/SIGNOFF.md`, *Publication of 4.1.0*) writes format 4 unchanged too: its production sheet (decision D-256) shows no row of a pin, and nothing of this design changes. The minor release 4.2.0 (decision D-259; published 2026-11-21, annotated tag `v4.2.0` on `6848510`, the merge of #328, made by the tag workflow of D-227, run 44895952490; release workflow run 44895975583; `compliance/SIGNOFF.md`, *Publication of 4.2.0*) writes format 4 unchanged as well: its electrical rules (decision D-258) read the pins and the nets, not the rows of a face, and nothing of this design changes. The minor release 4.3.0 (decision D-261; published 2026-11-22, annotated tag `v4.3.0` on `20bf8f1`, the merge of #337, made by the tag workflow of D-227, run 45045461615; release workflow run 45045481035; `compliance/SIGNOFF.md`, *Publication of 4.3.0*) writes format 4 unchanged as well: its review checklist (decision D-260) is a free value of `config/naming.json`, and nothing of this design changes. The minor release 4.4.0 (decision D-263; published 2026-11-23, annotated tag `v4.4.0` on `e6eddc0`, the merge of #348, made by the tag workflow of D-227, run 45121731874; release workflow run 45121757018; `compliance/SIGNOFF.md`, *Publication of 4.4.0*) writes format 4 unchanged as well: its two settings (decision D-262) are free values of `config/naming.json`, and nothing of this design changes. The patch release 4.4.1 (decision D-265; prepared, not tagged) writes format 4 unchanged: its one fix, pull request 350, makes the review of a library device compare the ICD fields of a connector and the level of a pin, and nothing of this design changes.

## 0. The owner's decision

The publication of 3.0.0 left three owner questions open (D-249, `compliance/SIGNOFF.md`, *Publication of 3.0.0*). One of them was: *Should the row layout of a connector (for example Micro-D rows 1–11 and 12–21) be stored in the project? Format 3 is frozen, so this needs format 4 and a major release.* On 2026-11-19 the owner answered **yes** (D-250).

What follows from the answer, and frames this design:

1. **The layout is project data**, read and written with the project, in the model hash, under undo and in the journal, like the pin level of format 3.
2. **It needs format 4.** The model refuses unknown keys (`extra="forbid"` in `core/model/base.py`), so a new key is a format change, and format 3 is frozen since the tag `v3.0.0` (D-249). A change of the project format is a major release (the rule of D-226 and D-230; the root `CLAUDE.md`, *Version numbers*): the release that first writes format 4 is **4.0.0**.
3. **Format 4 is frozen at its tag**, as formats 2 and 3 were. Whatever a later 4.x minor release needs to read from the layout must be in format 4 now, or it waits for format 5. Section 4 is written with that in mind: it stores what the face rule of section 8 reads, and nothing more.

## 1. Purpose and scope

### 1.1 What a row layout is

The contacts of a connector sit in its insert in a fixed pattern. The datasheet and the device's interface control document (ICD) show it as a face view: the pin numbers as they stand on the face. For the common rectangular connectors the pattern is rows: a 21-pin Micro-D has the row 1 to 11 and, under it and offset by half a contact, the row 12 to 21. A **row layout** is that pattern written as data: the rows in order from the top of the face, and in each row the pin names in order along the row.

The examples below show the form only. They were not compared with a datasheet (section 17), and the tool ships none of them (L3):

| Connector | Row layout (rows separated by `/`) |
|---|---|
| D-sub or Micro-D, 9 contacts | `1–5 / 6–9` |
| Micro-D, 21 contacts (the owner's example) | `1–11 / 12–21` |
| High-density D-sub, 15 contacts | `1–5 / 6–10 / 11–15` |
| A header of two rows numbered odd and even | `1 3 5 7 9 / 2 4 6 8 10` |
| RJ45 | `1–8` |
| A circular insert with an outer and an inner ring | `1–8 / 9–12`, marked as rings |

So a row is a **list of pin names**, not a range: the header shows that the order along a row need not be the order of the numbers, and the names are those of the connector's pins (`A1` and `12` alike). A circular insert has rings in place of rows; section 4 gives a layout one mark for that (`rings`), so that the last pin of a ring is next to its first.

### 1.2 Why users need it

- **The harness plan.** The users' template names a connector by its kind and size (`CON_…` sheets, *Connector Type*, *Number of Pins*); the face is in the ICD the sheet links to. The plan of 3.0.0 lists the device side pin by pin in the connector's pin order. With the layout, the plan shows the row of each pin and lists the pins row by row, so a reader sees the face in the table (section 7).
- **The pinout files.** `system/box_pinouts.csv`, the pinout of each harness and `export-pinout` are what a team checks against the ICD and hands to the bench. A *Pin row* column there says where the contact sits (section 7).
- **The check of power and return pins.** The rule `power-return-adjacent` (ECSS-Q-ST-30-11C 6.11.3 a) warns when a power and a return pin have fewer free contacts between them than `generation.power_return_gap_pins` asks. Today *between* and *neighbour* mean the order of the pin list (`core/drc/standard_rules.py` `_power_pairs`; the assumptions A-PIN-ORDER and A-RETURN-GAP say *Neighbours are neighbours in the list of pins*). The transparency audit names the gap (`docs/transparency_audit/rules-and-warnings.md`, DRC-C2-006: *wrong for connectors whose insert layout is not sequential (Micro-D staggered rows, circular)*). In a 21-pin Micro-D, pin 12 sits between pins 1 and 2 and far from pin 11, while the list puts it next to 11. With the layout, the rule can count the neighbours on the face (section 8, L1).

### 1.3 In scope

The layout on a connector part and, where a device's connector differs from its part, on the box connector (section 3); format 4 and the step from 3 to 4 with its proof (sections 4 and 5); the device library file and the subsystem file (section 5.5); the entry of a layout in the editor, by `import-pinout`, by a new command `pin-rows` and by the scripting interface (sections 6, 9, 10); the *Pin row* column of the pinout tables and of the harness plan, and the order of the plan's near rows (section 7); the rule `power-return-adjacent` on the face (section 8); three checks of `check` (section 4.3).

### 1.4 Not in scope of 4.0.0

- **No picture of the face.** The drawings (SVG, PDF) keep their connector pictures, whose dots follow the pin count; no face view is drawn, and the build workbook, the labels, the BOM and the WireViz file do not change. A face view is a later minor release: the rows, the order in a row and the rings are enough to draw a schematic face, and that needs no format change.
- **No coordinates.** No pitch, no position in millimetres, no clocking of a circular insert, no keying. The face rule of section 8 works from the rows alone and says what it assumes.
- **Generate does not read the layout.** The pin assignment keeps the order of the pin list (A-PIN-FIRST-FIT); whether it should place pins by the face is L2.
- **The far side of the plan** (the column groups `W:AA` …) and its reference pinouts keep their seven columns; the `CON_…` sheet of the far connector shows the rows.
- **`import-parts`** gets no column for the layout (a parts list rarely holds one; the layout of a part is entered in the editor, by `pin-rows` or through a device file).
- **The starter library** gets no layout (L3).

## 2. What exists at 3.0.0

- **The connector part.** `Part` (`core/model/library.py`) of category `connector` has `pin_count`, `mates_with` (the mating part), `description`, `link` (format 3), but no pin names: the part says how many contacts it has, not what they are called.
- **The connector and its pins.** `Connector` (`core/model/physical.py`) has `part_id`, `unit_id` (box connectors only), `mates_with` (a cable connector: the box connector it plugs into), `pins` (an ordered list of `Pin`), and the format 3 source fields. A pin's ID is a `PinId` (`core/ids.py`: letters, digits, `_`, `.`, `-`, up to 16 characters). A new connector from a part gets the pins `1` to `N` (`core/first_connector.py`, `edit.py`). A cable connector of a generated harness gets the pin IDs of the box connector it plugs into, and pins mate by ID.
- **The order of the pins** is the order of `Connector.pins`. Generate's pin assignment (`core/generate/pins.py`), the rule `power-return-adjacent` and the pinout tables read it as the physical order.
- **The device file and the library.** A device library file (`harness-device-library`, `core/device_library.py`) holds devices, their box connectors, and every part they name; since 3.0.0 a file is written as version 2 only when one of its devices uses a field of format 3, else as version 1 (`content_version`). A `NAME.device.json` file is such a file with one device (`core/device_file.py`, D-240). The project names its libraries in `device-libraries.json` (outside the format); the import record of kind `devices` links a device to its file (`core/library_link.py`). The subsystem file (`harness-subsystem-library`, version 1, `core/subsystem_library.py`) carries devices and parts the same way.
- **The pinout import and export.** `import-pinout` (`core/pinout_import.py`) reads a sheet with the headings of `_ALIASES` (Connector, Pin, Signal, Function/Description, Direction, Level, Source …); the columns of a connector, not of a pin, are in `CONNECTOR_COLUMNS`. `export-pinout` writes the rows of `system/box_pinouts.csv` for one device, plus Level and the source columns while used (`devices.pinout_sheet`, `PINOUT_EXTRA_COLUMNS`), so that the file reads back.
- **The pinout tables.** `outputs/tables.py` `box_pinouts` and `pinouts` (one per harness) add a sparse column (Function, Termination, Contact, Direction) only while some pin of the project uses it; `core/outputs/verify.py` derives every row a second time (`_pin_rows`, `_pinout_header`).
- **The harness plan.** `core/outputs/harness_plan.py`: the near block of a box connector lists its pins in pin order (`near_rows`), with the device side in columns B to F and the harness side in H to U (the template's print range is `H6:U64`; column A is empty); the `CON_…` sheet has the pin table in columns A to E from row 18. `core/outputs/verify_plan.py` states every cell a second time.
- **The upgrade.** `core/io/migrate.py` holds the steps (`MIGRATIONS = {0: …, 1: _v1_to_v2, 2: _v2_to_v3}`); `core/io/upgrade.py` is the safety net (D-202): `plan_upgrade` is the dry run (`migrate --dry-run`), `upgrade_project` copies every file into `.migration-backup-v<N>/`, writes `MIGRATION.json`, writes the project, reloads it and checks: the same model hash (which does not read the format number, `layout.schema_one`), the same findings of `validate` and `check`, the baselines untouched, and an in-memory export of the old and the new reading, byte for byte; any difference puts every file back. The step from 2 to 3 had its own proof (`prove_versions_step`, section 5.6 of the 3.0.0 design), because it changed the model hash once.
- **Older tools.** The loader opens a project of a newer format read-only (`core/io/loader.py`: `version > SCHEMA_VERSION` gives `newer_version` and `project.read_only`). 3.0.0 already has this check, so a 3.0.x tool opens a format 4 project read-only without any change to 3.0.x.

## 3. Where the layout lives

**On the connector part, shared by every connector of that part; and on a box connector, as its own layout, where that connector differs.** The layout of a connector is worked out by one function, in this order:

1. A **box connector**: its own layout (`Connector.row_layout`) when it has one; else the layout of its part; else none.
2. A **cable connector**: the layout of its part; else the layout of the box connector it plugs into (`mates_with`, by rule 1); else none. Pins mate by ID, so the rows of the box connector are the rows of the plug, seen from the mating face.

In each case, a name that is not a pin of the connector is left out (and `check` says so, section 4.3); a pin that is in no row is listed after the rows, without a row.

**Why the part.** The face is a fact of the insert, and the insert is fixed by the part number: the eleven identical Micro-D 9 connectors of a power distribution unit (`docs/FLATSAT_EXAMPLE.md`) have one face, entered once. The part travels with every device that names it, into the device library file (which carries its parts, section 2) and into a subsystem file. Two mating parts (`Part.mates_with`) can be compared (section 4.3).

**Why also on the box connector.** Three cases need it, and none is rare enough to leave out: (a) a project uses one generic part for connectors whose inserts differ (the starter parts are generic: `EX-MICROD-21-F` names no insert arrangement); (b) a device's ICD names the pins otherwise than the part's numbering (`A1` …), and the layout must name the pins the connector has; (c) `import-pinout` reads the rows of one connector from its ICD (section 6.2), and must not change the part of every other connector. An own layout is allowed **only on a box connector** (one with `unit_id`): a cable connector gets its rows from its part or from the box connector it plugs into, so Generate never has to write a layout and a regenerated harness cannot lose one.

**Not chosen: the box connector only.** Every identical connector would repeat the rows, and a part from a device file would not carry them. **Not chosen: the part only.** Cases (a) to (c) would need a part per connector or a refused import.

A layout is design data: it is in the model hash, so setting one makes the outputs *out of date* and asks for an export, as any edit does. It is device and library data, not harness data: the release freeze of a harness does not lock it, as it does not lock a pin's level (format 3).

## 4. Format 4

### 4.1 The keys

One new key, `row_layout`, in two places, each sparse (left out of the file while unset, so a project without a layout writes the same bytes as in format 3 apart from the number in `project.json`):

| Where | File | Key | Type, default |
|---|---|---|---|
| a part of category `connector` | `library/connector.json` (the file of its category) | `row_layout` | `RowLayout \| None`, `None` |
| a box connector | its file under `physical/connectors/`, as for every box connector | `row_layout` | `RowLayout \| None`, `None` |

`RowLayout` is a new sparse model in `core/model/physical.py` (the library imports it):

| Key | Type | Default | Rule |
|---|---|---|---|
| `rows` | list of rows; a row is a list of `PinId` | (required) | 1 to 64 rows; each row 1 or more pins; at most `MAX_PIN_COUNT` (1000) pins in all |
| `rings` | `bool` | `false`, left out while false | true: each row is a ring of a circular insert, listed from the outer ring inwards, its pins in order round the ring; the last pin of a ring is next to its first |

A part of the owner's example, as it would stand in `library/connector.json`:

```json
{
  "id": "EX-MICROD-21-F",
  "category": "connector",
  "pin_count": 21,
  "row_layout": {
    "rows": [
      ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
      ["12", "13", "14", "15", "16", "17", "18", "19", "20", "21"]
    ]
  }
}
```

A box connector with its own layout carries the same object under the same key. The file holds explicit lists only; the short text form `1–11 / 12–21` of section 6.1 is for the screen and the command line.

**Why one object and not two keys.** The rows and the ring mark are read together, checked together and changed together; one key is one value in a diff and one field of the editor. **Why no offsets or coordinates.** The face rule needs only which pins are next to each other. Section 8 derives that from the rows with one stated assumption (rows centred on each other); a row offset field would hold a number that nobody can check against the tool's output. If the owner wants a drawn face with true offsets later, it is a field of format 5 (section 15).

### 4.2 The rules of the files

Each rule is checked when the file is read. A part or a connector that breaks one is set aside (quarantined) with the reason, as any invalid object of the project files is today (`core/io/loader.py`):

1. `rows` has 1 to 64 rows, and no row is empty. An empty layout is written as no key, never as `"rows": []`.
2. Every name is a valid `PinId`.
3. **Every pin at most once** in the whole layout, over all rows: *pin 7 is in row 1 and in row 2*.
4. At most 1000 names in all (`MAX_PIN_COUNT`).
5. On a part: only a part of category `connector`; and when the part has a `pin_count`, at most that many names (*the layout names 22 pins; the part has 21*).
6. On a connector: only a box connector (`unit_id` set); and **every name is a pin of that connector** (*the layout names pin 22; J1 has no pin 22*).
7. `rings` is a boolean; `true` needs no other key.

Not a rule of the files: that every pin of a connector is in a row. A connector with a spare contact outside the rows, or a layout entered for the main rows only, is allowed; `check` notes it (section 4.3).

A part names no pins, so rule 6 cannot hold for a part; what it would say is a check of `check` instead (section 4.3).

### 4.3 The checks of `check`

Three new codes of `core/integrity.py`, worked out from the layout of each connector as section 3 resolves it:

| Code | Severity | When |
|---|---|---|
| `row_layout_pin_missing` | warning | the layout of a part names a pin that a connector of that part does not have; the pin is left out of that connector's rows. Typical cause: the connector's pins were renamed, or the part is used for an insert it does not have |
| `row_layout_pins_outside` | info | a connector has pins in no row of its layout; they are listed after the rows, without a row, and the face rule judges them in list order (section 8) |
| `row_layout_mate_differs` | warning | two connectors that mate (a cable connector and the box connector it plugs into, or two parts linked by `mates_with`) both have a layout, and the pins of one row of one are not the pins of one row of the other. The order inside a row is not compared, since a mating face is seen mirrored |

None is an error: a layout is a person's information, and a project with an odd one still generates and exports.

## 5. The step from 3 to 4

### 5.1 What it writes

`_v3_to_v4` in `core/io/migrate.py`, the list `V3_TO_V4_PARTS = (_v4_number,)`, and `MIGRATIONS[3] = _v3_to_v4`: **the number 4 in `project.json`, and nothing else.** The new key is sparse and nobody has a layout before format 4, so no file but `project.json` changes, and `project.json` only in the number. `SCHEMA_VERSION` becomes 4 (`core/model/project.py`). The backup folder is `.migration-backup-v3/`, the record `MIGRATION.json`, the journal entry *migrated from format 3*, all as for the earlier steps. `migrate DIR --dry-run` shows the one change and writes nothing; the editor's upgrade question shows the same. A format 2 project goes through 2 to 3 and 3 to 4 in one upgrade, with `--set-version` where the step 2 to 3 needs it and its proof as in 3.0.0; a format 1 project through all three steps. `VERSIONS_FORMAT` stays 3.

### 5.2 The proof

The step from 2 to 3 changed the model hash once and needed a proof of its own (section 5.6 of the 3.0.0 design). This step is like the step from 1 to 2: it changes no hash, so the safety net of D-202 is the whole proof, and every part of it applies without an exception list. Its three parts, as section 5.6 of the 3.0.0 design sets them out:

1. **Nothing but the number** (the run-time check of every `migrate`, `core/io/upgrade.py`, no new code). The format 3 files read as format 3 (`migrate=False`) and the format 4 files the step writes give the same model hash, the same findings of `validate` and `check` (by code, object and message), the same consistency of the released harnesses, the baselines byte for byte, and the same in-memory export, byte for byte, with and without the harness plans. A format 3 tree is a valid format 4 tree apart from the number, so the old reading needs no neutral form (unlike `neutral_tree` of the step 2 to 3). Any difference: every file is put back.
2. **No layout appears.** A test (`tests/test_format4.py`) checks, for every fixture project and example, that after the step no part and no connector has `row_layout`, that `project.json` differs in the number only, and that every other project file is byte-identical.
3. **The written files.** The output-hash baseline (`docs/ui/OUTPUT_HASHES_BASELINE.json`), the output goldens and the numbers snapshot stay as they are: `python -m tools.output_hashes --check` and `python -m tools.numbers_snapshot --check` say *identical* after pull request 1, since `4.0.0` has as many characters as `3.0.0` and the tool replaces the stamp. Nothing is written again. If a test finds any other difference, the step is wrong, not the baseline.

The new fields change outputs only once a person sets a layout. Each output that reads it is sparse (section 7), so the baseline stays *identical* through every pull request of section 14; the outputs with a layout get goldens of their own (section 13).

### 5.3 What older tools do

- **3.0.x opens a format 4 project read-only** (the loader's check, already in 3.0.0). Nothing in 3.0.x changes for this. A part or a box connector with `row_layout` breaks the strict models of 3.0.x, so in that read-only view it is set aside (quarantined) with the unknown key named; the rest of the project shows. The read-only banner says that a newer version saved it. So the whole team updates at the same time, as with formats 2 and 3, and the user manual page *Upgrade a project* says so for format 4.
- **2.x and 1.x** open it read-only too (their own check of the number).
- **4.0.0 writes format 4** for every project it saves after the upgrade, with or without a layout, as 2.0.0 and 3.0.0 did with their formats. `save_project` keeps refusing to write a project of an older format over its own folder unless the upgrade does it.

### 5.4 Merges across the upgrade

A branch still in format 3, merged into a branch in format 4, brings files that are valid format 4 (no key was renamed, unlike the step from 2 to 3). Git keeps the number 4 in `project.json` unless both branches changed that line. So no rewrite after a merge is needed and `merge-fix` does not change; the user manual still says to upgrade the main branch first and bring the other branches up to date before they merge, so that no person on a format 3 branch edits a layout that format 3 cannot hold.

### 5.5 The device library file and the subsystem file

- **The device library file** (`harness-device-library`) gets **version 3**, written only when a part or a box connector of the file has `row_layout`; else version 2 or 1 by the rule of 3.0.0 (`content_version`). So a 3.0 tool refuses only such a file, with *a newer version*, and still offers the others (the folder rules of D-240). A `NAME.device.json` file keeps its rules; a connector's own layout is allowed in it (it is a box connector), and the parts it carries carry their layouts.
- **The subsystem file** (`harness-subsystem-library`) gets **version 2** by the same rule. (At 3.0.0 it stays version 1 also when it holds a format 3 field; this design does not change that for the format 3 fields, section 17.)
- **The library update** of 2.2.0 (`update-device`, the editor's review) compares the portable form: a layout is library-owned, and a difference shows in its diff like any other field of a part or a connector.

## 6. Entering a layout, imports and exports

### 6.1 The short text form

The editor and the command line show and take a layout as one line of text: rows separated by `/`, the pins of a row separated by spaces or commas, and a run of whole-number pins written as `1–11` (an en dash) or `1:11`. `1–11 / 12–21` is the owner's example. Neither `/`, `–` nor `:` can be part of a pin ID (`core/ids.py`), so the form is never ambiguous; `-` and `..` can, so they are not range marks. A run counts up or down (`11–1`). The tool writes the form with `–`, using runs wherever three or more whole-number pins follow each other. The mark `(rings)` at the end stands for `rings: true`. The parser and the writer are one module, `core/row_layout.py` (section 14), with a round-trip test.

**From row lengths.** The common case, rows numbered one after the other, is entered as the lengths of the rows: `11, 10` gives `1–11 / 12–21` on a part, and on a connector takes its pins in pin order, eleven then ten. The editor and `pin-rows --lengths` offer it.

### 6.2 `import-pinout`

- A new optional column **Pin row** (headings `Pin row`, `Row`, `Contact row`, compared as today without case, spaces and signs): a whole number from 1, the row of the pin on that line. The pins of a row are in the order of the lines. An empty cell leaves the pin out of the rows.
- What the import does with it, per connector of the sheet: it builds the rows and compares them with the layout the connector has now (section 3), row by row as sets of pins. **Equal:** nothing changes (the order inside a row stays as stored, so an export read back is no change). **Different, or no layout yet:** the rows become the connector's own layout, keeping the `rings` mark of the layout it had. The import record lists the connector under *row layouts set*, and when the part has no layout of its own it adds a note: *the rows are stored on J1 only; to use them for every connector of part EX-MICROD-21-F, choose Use for every connector of this part in the Devices tab, or run `pin-rows --to-part`*.
- A cell that is not a whole number from 1 refuses that line with its row number, as an unreadable cell of another column does today. A number that leaves a gap (rows 1 and 3, no 2) is closed up and noted.
- A sheet without the column leaves every layout as it is.

### 6.3 `export-pinout` and the other files

- **`export-pinout`** writes the *Pin row* column while a connector of the device has a layout (section 7), in the rows of `box_pinouts.csv`, so the file reads back through `import-pinout` without a change (6.2, *Equal*).
- **`save-device`, `add-device`, `update-device`** carry the parts and the box connectors with their layouts (section 5.5). `import-devices` and `export-devices`, which use the same file, do the same.
- **`import-parts`** does not read a layout (section 1.4). **`import-netlist`** (KiCad) does not either.
- **`system/export.json`** carries `row_layout` of a part or a connector while set, as it carries the other sparse fields; its `format_version` is not raised for an added key (but see L4).

## 7. The outputs

Every output below is **sparse**: it changes only for a project in which some connector has a layout (section 3), so the output-hash baseline of the projects without one stays *identical*. Each output that has a second derivation in a verifier gets the same change there, written on its own (the rule of `docs/developer/agent/core.md`: every output wording exists twice).

| Output | Change | Verifier |
|---|---|---|
| `system/box_pinouts.csv`, the Devices tab's pinout table (the same rows) | a column **Pin row** after the last column, while some box connector of the project has a layout: the row of the pin (1, 2 …), empty for a pin in no row. The rows stay in pin order | `outputs/verify.py` `_pin_rows`, `_pinout_header` |
| `harnesses/<ID>/pinout.csv` and the pinout sheet of `<ID>.xlsx` (`tables.pinouts`) | the same column, for the cable connectors, with the layout of section 3 (the part's, else the mated box connector's) | the same |
| `export-pinout` | the column, as above, through `pinout_table` | — (read back by `import-pinout`) |
| harness plan, `CON_…` sheet | a column **Pin row** in F after *Description*, heading in row 18 beside the others, while that box connector has a layout; width as column C | `verify_plan.py` `expected_plan` |
| harness plan, near block of a box connector with a layout | the pins **row by row**, in the order of the layout, then the pins in no row in pin order (`near_rows`); a column **Pin row** in A, left of *Pin No.*, each cell a reference to the `CON_…` cell (`=[$'CON_…'.F19]`) with its value, as the other device-side cells; the heading *Pin row* beside *Pin No.* | `verify_plan.py`, with its own copy of the order |
| `system/export.json` | `row_layout` of parts and connectors while set | `outputs/verify.py` (the model fields it compares) |
| findings (`drc_findings.csv`, `drc_report.md`, the editor) | the rule of section 8 judges the face of a connector with a layout | — |

The plan's column A is outside the template's print range `H6:U64`, like the whole device side; the printed harness side keeps its columns. The word *Pin row* and not *Row* keeps it apart from the plan's *Used in Row* (a spreadsheet row).

**Not changed:** the drawings, the build workbook, the labels, the BOM, the mass and length tables, the connection list, the traceability table, the version report, the WireViz file, the plan's far side and reference pinouts (section 1.4).

## 8. The face rule: `power-return-adjacent` on the face

**No new rule; the rule `power-return-adjacent` reads the face where a connector has a layout** (L1). The rule count stays 39, the rule ID, its setting `power_return_gap_pins` and its source (ECSS-Q-ST-30-11C 6.11.3 a, requirement 0140052) stay.

**Neighbours on the face.** For a layout of rows (`rings` false), number the rows from 0, the places in a row from 0, and let `L` be the length of the longest row. A pin at place `i` of a row of length `n` sits at `x = i + (L − n) / 2`: rows are taken as centred on each other. Two pins are **neighbours on the face** when they are in the same row at places next to each other, or in rows next to each other with `|x − x'| ≤ 1`. For the 21-pin Micro-D, pin 12 (`x = 0.5`) is next to pins 1 and 2, and pin 21 (`x = 9.5`) to 10 and 11, which is the staggered face. For rows of equal length the rule takes the pin straight across and both diagonal pins, which may be one more than the real face has: it warns more, never less, than a face of centred rows. For a layout of rings, two pins are neighbours when they are next to each other in one ring, the last next to the first; **pins of different rings are not judged**, because the rows alone do not say which contacts of two rings face each other.

**What the rule does with that**, for two power or ground pins of different signals on one connector (the pins it looks at today):

- **Both in rows of the layout:** in the same row, it counts the unassigned contacts between them along the row (the shorter way round a ring) and warns when they are fewer than the gap, as today along the list; in rows next to each other and neighbours on the face, there is no contact between them, so it warns whenever a gap is set; otherwise it does not judge the pair. The list order is not read for such a pair.
- **At least one in no row:** as today, in the order of the pin list.

The finding keeps its ID (`<connector>.<pin>+<pin>`). The text of a pair across rows says so: *J1: +28V (pin 1) and RTN (pin 12) are neighbours on the face of the connector (rows 1 and 2), with no unassigned contact between them*. The help of the rule (*Leave at least one contact unassigned between them (regenerate the harness)*) gets a second sentence: *On a connector with a row layout, a neighbour in the next row counts too; move one pin or lock the pins (Generate does not read the rows)* (L2).

**What it judges no longer, what it judges now.** For the Micro-D 21 the list pair 11 and 12 is not a pair on the face, and the face pairs 1 and 12, 2 and 12 … were never judged. For rings, the cross-ring pairs that the list order happened to make neighbours are not judged; `unchecked-config` gets a line for each connector with rings (*J4: power and return pins of different rings of a circular insert were not checked: the row layout does not say which contacts of two rings face each other*), so the gap in the check is written down and not silent.

**What changes for existing projects:** nothing. No project has a layout until a person enters one (section 5.2), so every finding of every project stays as at 3.0.0 after the upgrade. The findings change on a connector the moment a person gives it a layout, and the editor shows them as any change of findings.

**The texts that name the rule's notion of neighbour** change with it: the assumptions A-RETURN-GAP and A-PIN-ORDER (`core/assumptions.py`: *Neighbours are neighbours in the list of pins, or on the face where the connector has a row layout*), the explanation of the rule (`core/derive_rules.py` `_power_return`), `docs/RULES.md` and `docs/models/pin-allocation.md` made again by their tools. These texts are in no written output file of `export`.

**Not changed:** every other rule. The neighbour of a pair of a twisted pair (A-PIN-FIRST-FIT: *a pair sits on neighbouring pins*) is Generate's, and Generate does not read the face (L2). `connector-lookalike`, `pin-shared`, `signal-unassigned` and the rest do not read rows.

## 9. The editor

- **Devices tab, the details of a box connector:** a row *Pin rows* that shows the layout in the text form and where it comes from (*1–11 / 12–21, from part EX-MICROD-21-F*, or *own rows*, or *none*), with **Edit rows…**. The dialog *Pin rows of J1* has a text box with one line per row (the form of 6.1 without `/`), a field *Row lengths* with **Fill**, a check box *Rings of a circular insert*, a line that shows a mistake in words and keeps **OK** off (*pin 22 is not a pin of J1*, *pin 7 is in two rows*), and three buttons: **Use for every connector of this part** (moves the rows to the part and clears the own rows of each connector of that part that equal them; one undo step), **Back to the part's rows** (clears the own rows) and **Clear**. Each change is one undo step and goes into the journal.
- **Devices tab, the pin table:** a column *Pin row* while the connector has a layout (the rows of `box_pinouts.csv`, as the table shows today).
- **The Inspector of a part** of category `connector`: *Pin rows*, the same dialog without the connector's pins (it checks the rules of 4.2 for a part; it names the connectors of that part that `row_layout_pin_missing` would warn about).
- **The Inspector of a cable connector** and the connector editor of a harness: *Pin rows* read-only, with where they come from (*from part …* or *from DEV2-J1, the device connector it plugs into*). A cable connector has no own rows (section 3).
- **The Problems panel** shows the three checks of 4.3 and the findings of section 8, with **Show** going to the connector.
- **Strings** in `gui/strings.py`; the in-app guide and a user manual page *Pin rows of a connector*; the screenshots of the Devices tab made again with `python -m tools.gui_screenshots`.

## 10. The command line and the scripting interface

- **`pin-rows DIR (--part ID | --connector ID) [--set TEXT | --lengths N,N… | --clear] [--rings | --no-rings] [--to-part] [--json]`**, new, in `cli/` beside `document` (3.0.0). Without an option it shows the layout and its source; for a cable connector, the layout section 3 gives it, read-only. `--set` takes the text form of 6.1, `--lengths` the row lengths, `--clear` removes the part's or the connector's own layout. `--to-part` (with `--connector`) moves a connector's own rows to its part, refuses when the part has other rows, and clears the equal own rows of the other connectors of that part. A read-only project refuses with the reason. The change is journaled, as an edit in the editor is. `--json` prints `{"object", "kind", "rows", "rings", "source", "text"}`; `docs/CLI.md` is made again from the parser.
- **`import-pinout`** and **`export-pinout`**: section 6; the help names the column *Pin row*.
- **`check`**: the three codes of 4.3. **`drc`**: section 8. **`explain J1`**: names the layout and its source in the connector's lines.
- **`migrate`**: the step of section 5, with `--dry-run`. No new option.
- **The scripting interface** (`harness_design_studio.api`) only adds: `Part.row_layout` and `Connector.row_layout` on the models it returns; `row_layout_of(source, connector_id)` (the layout of section 3 with its source); `set_row_layout(folder, *, part=None, connector=None, rows, rings=False, author=None)` and `clear_row_layout(...)`, both through the same plans as the editor. `API_VERSION` stays 1 (as in 3.0.0, an interface that only adds keeps its number); the API snapshot (`python -m tools.gen_api_snapshot`) is made again on purpose in the pull request that adds them.

## 11. The older names of 3.0.x

The owner's answer to Q29 of the 3.0.0 design (D-242) keeps `revision` beside `version` in `system/export.json` and `log --json`, and `harness.revision` beside `harness.version` in the expression field, through 3.0.x, and says that *the next minor release* drops them and raises `format_version` of `export.json` to 2; `docs/releases/3.0.0.md` tells scripts the old names work *through 3.0.x*. The command `revise` stays as the older name of `new-version` and *is not removed in 3.x* (Q30). The release after 3.0.x is now 4.0.0, a major release, not a minor one; whether 4.0.0 drops the old names is **L4**, and the owner answered yes (2026-11-19). So it is a pull request of its own (R in section 14), with its own record: `export.json` changes in every project, so the output-hash baseline and the numbers snapshot are written again once, with that one reason, and the release notes say it under *For scripts*. It is kept out of pull request 1, so that the proof of section 5.2 stays *identical*.

## 12. What does not change

- Every project without a layout: its files (apart from the number in `project.json`), its model hash, its findings and every written output apart from the stamp.
- Generate and the pin assignment (L2); the harnesses it makes; the independent verifier `core/verify.py`.
- The versions, the release freeze, the journal, `merge-fix`, the change log, the baselines.
- The drawings, the build workbook, the labels, the BOM, the WireViz file (section 1.4).
- The number of design rules (39) and every rule but `power-return-adjacent`.
- `import-parts`, `import-netlist`, `import-lengths`, `import-build-data`, the as-built files.
- The starter library and the example projects (L3); their goldens.
- `API_VERSION` (1); the scripting functions that exist.
- `device-libraries.json` (outside the format); the folder rules of the device library.

## 13. Tests

- **Format 4** (`tests/test_format4.py`, REQ-MIGRATE-09): the step on every fixture and example: `project.json` changed in the number only, every other file byte-identical, no layout anywhere, the safety net's checks pass (the same model hash, findings, release consistency, baselines, in-memory export with and without plans); format 2 and format 1 projects through all steps in one upgrade, with `--set-version` where needed; the step run twice gives the same files; `--dry-run` writes nothing; a format 4 project read by a reader of format 3 is read-only (the loader's check, with a fake format one ahead as `install_fake_format` does); `tools.output_hashes --check` and `tools.numbers_snapshot --check` *identical*.
- **The model** (`tests/test_row_layout.py`, REQ-PIN-05): each rule of 4.2 refused with its message (an empty row, a pin twice, more than `pin_count`, a layout on a wire part, an own layout on a cable connector, a name that is not a pin of the connector, 65 rows); a valid layout round-trips and is left out while unset; `rings` left out while false; the resolution of section 3 in every case (own, part, mated box, none, names left out, pins in no row); the text form of 6.1 round-trips (Hypothesis: random layouts of whole and other pin names), refuses `-` and `..` as range marks, and takes `:` and `–`; `--lengths` on a part and on a connector.
- **The edits:** renaming a pin of a box connector renames it in its own layout; deleting it removes it (and an empty row); *Use for every connector of this part* and `--to-part`; each edit one undo step, journaled; a released harness on the connector does not block an edit of its box connector's rows (section 3).
- **The checks** (`check`): each code of 4.3 on a small project, and none on the fixtures.
- **The face rule:** the Micro-D 21 case (1 and 12 warned, 11 and 12 not), the D-sub 9, three equal rows, a ring with its last and first pin, two rings with the `unchecked-config` line, a pin in no row judged in list order, a gap of 2 counted along a row; every fixture and example gives the same findings as at 3.0.0 (the DRC golden unchanged).
- **The outputs:** the *Pin row* column in `box_pinouts.csv`, the harness pinouts and `export-pinout`, present only with a layout; the plan's `CON_…` column F and the near block in the order of the layout with column A, on a project with a layout; `verify --outputs` 0 errors, and mutation tests: a wrong row number, a pin in the wrong order in the plan, a missing column, an extra column on a project without a layout; goldens for one project with a layout (`tests/fixtures/outputs/row_layout/`); the output-hash baseline unchanged for the others.
- **Imports:** `import-pinout` with *Pin row* (equal: no change; different: own rows and the note; a gap closed; a bad cell refused with its line); `export-pinout` read back as no change; a device file with a layout written as version 3, one without as before, and a 3.0 reader refusing only the version 3 file (simulated by the version check); the library update showing a layout change in its diff.
- **The editor** (offscreen): the dialog's mistakes keep OK off; the three buttons; the read-only view of a cable connector; the pin table column.
- **End to end through the command line** (`tests/test_e2e_400.py`): a format 3 project of 3.0.0 (made by the 3.0 fixtures), `migrate --dry-run`, `migrate`; `pin-rows --part EX-MICROD-21-F --lengths 11,10`; a pinout imported with *Pin row* for another connector; `check` and `drc` with the face finding; `export --harness-plan`; `verify --outputs` with 0 errors; a second export byte-identical; `export-pinout` read back as no change.
- **Guards:** the offline test, the security tests, `docs/CLI.md` and the JSON keys in sync, the promise words, `tests/test_claude_md_split.py`.

## 14. Pull requests

| PR | Content |
|---|---|
| 1 | **Format 4.** `SCHEMA_VERSION` 4, `_v3_to_v4` (`V3_TO_V4_PARTS`, the number only), `MIGRATIONS[3]`; `RowLayout` and the sparse fields `Part.row_layout` and `Connector.row_layout` with the rules of 4.2; the schemas (`core/schemas.py`, `schema DIR`), `docs/FILE_FORMAT.md`; the device library file version 3 and the subsystem file version 2 rule (5.5); `core/row_layout.py` with the resolution of section 3 and the text form of 6.1; the edits of a pin that keep the own layout in step (`connector_edit.py`); `tests/test_format4.py`, `tests/test_row_layout.py`; REQ-MIGRATE-09 and REQ-PIN-05 in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`); this page's status. No output changes, no rule changes, no screen. **Merged only when no 3.0.x patch release is wanted from `master` any more**, because `master` writes format 4 from its merge (as pull request 274 of 3.0.0 was merged only after 2.4.0 was tagged) |
| 2 | **Core.** The three checks of 4.3 (`core/integrity.py`); the face rule of section 8 (`core/drc/standard_rules.py`, `unchecked`, `core/derive_rules.py`, the assumptions); `docs/RULES.md` and `docs/models/` made again; the plans `plan_set_row_layout`, `plan_share_with_part`, `plan_clear_row_layout`; the scripting functions of section 10 and the API snapshot |
| 3 | **Outputs.** The *Pin row* column of the pinout tables and of `export-pinout`; the plan's `CON_…` column F, the near block's order and column A; `export.json`; each in its verifier (`outputs/verify.py`, `verify_plan.py`) with the mutation tests; the goldens of the project with a layout; the output-hash baseline unchanged |
| 4 | **Command line and imports.** `pin-rows`; `import-pinout` with *Pin row* and the note; the device library commands and the subsystem file carrying layouts; `explain`; `docs/CLI.md` |
| 5 | **Editor.** The Devices tab's *Pin rows* row and dialog, the pin table column, the Inspector of a part and of a cable connector, the Problems panel, the strings, the screenshots |
| 6 | **The end-to-end test and the documents.** `tests/test_e2e_400.py`; the user manual pages *Pin rows of a connector* and *Upgrade a project* (format 3 to 4), the in-app guide (`python -m tools.build_guide`), `docs/OUTPUTS.md`, the glossary entry *Row layout*; the changelog entries of pull requests 1 to 5 under *Unreleased*; the release notes `docs/releases/4.0.0.md` with *For scripts* (the new key in `export.json`, the new column, the new command) |
| R | **The owner answered L4 with yes (2026-11-19):** the older names of 3.0.x dropped (section 11), with the output-hash baseline and the numbers snapshot written again once for that reason; before the preparation |
| 7 | **The preparation of 4.0.0** as a pull request of its own, as the preparation of 3.0.0 was: the version, the changelog section, the decision row of the release, the status pages; format 4 frozen at the tag |

Order: 1 first; then 2; then 3, 4 and 5 in any order (5 needs 2 for its plans); then 6; R at any time after 1 and before 7; then 7. Pull requests 1 and 2 already make a tool that stores, checks and judges layouts; the outputs and the screen follow.

### What pull request 1 changed

Pull request 1 is built as row 1 says, with these differences, each for the reason given:

- **The pin edits are in `core/devices.py`, not `core/connector_edit.py`.** `connector_edit.py` edits the cable connectors of a harness, which hold no own layout (section 3); the pins of a box connector are renamed, deleted, replaced and resized by `devices.ops_rename_pin`, `ops_delete_pins`, `ops_set_pinout` and `ops_change_part`, so these keep the own layout in step (`row_layout.follow_pins`: a renamed pin keeps its place, a pin that goes leaves its row, an empty row goes, a layout with no row left is cleared). `devices.ops_update_part` refuses a pin count below the names of the part's layout, which rule 5 of section 4.2 would otherwise refuse on the next load.
- **Duplicate pins (rule 3) are compared without regard to case**, as the pin IDs of a connector are (*names are the same ignoring case*); rule 6 compares the names exactly with the connector's pin IDs.
- **A row keeps its number when names of it are left out** (section 3): `layout_of` keeps such a row in place, empty if none of its names is a pin, so the row of a pin is the row of the layout. `-` and `..` are read as part of a pin name (`1-11` is one pin), not refused (section 6.1); a run is two whole numbers without a leading zero, and the writer runs only such numbers, so `parse_text(layout_text(x)) == x` holds for every layout.
- **The loader still names a key or a letter of format 2 in a format 3 project** (`revision_not_version`), and `merge-fix` rewrites them there too and keeps the number: at 3.0.0 both acted on the current format only, which would have left a format 3 project with such a leftover neither upgradable nor fixable by a format 4 tool. `VERSIONS_FORMAT` (3) moved to `core/io/migrate.py` for it; `upgrade.VERSIONS_FORMAT` names the same number.
- **The export with the harness plans** of section 5.2 is compared in `tests/test_format4.py`; the run-time check of `upgrade` keeps its export without the plans, unchanged (section 5.2 asks for no new code there).

### What pull request 2 changed

Pull request 2 is built as row 2 says, with these differences, each for the reason given:

- **The plans are in a module of their own, `core/row_layout_edit.py`**, not in `core/row_layout.py`: that module only reads a project, and `core/devices.py` imports it, so plans there that need the editing helpers would make a cycle of imports. The names are those of row 2.
- **The checks of section 4.3 are part of `check_integrity`**, so `validate` reports them as well as `check`, and so does the editor's load. The two warnings are also findings of the rule `model-inconsistent`, as every warning of `check_integrity` is (that is how the Problems panel shows them); the note `row_layout_pins_outside` is not, because that rule now takes the warnings only (`check_integrity` had no notes before, so nothing else changes). `row_layout_mate_differs` compares row 1 with row 1, row 2 with row 2 and so on (a mirrored face keeps its top row on top); `row_layout_pin_missing` also speaks for the rows a cable connector takes from the box connector it plugs into.
- **The line of `unchecked-config` for rings** is written only for a connector on which two power or ground pins of different signals sit in different rings, and it names those pairs (*J4: power and return pins of different rings of a circular insert were not checked (pins 1 and 9): …*); a connector with rings and no such pair has nothing unjudged. Its object is `power-return-rings`, one line per connector (the finding key carries the connector), listed under `power-return-adjacent` in the Checks view (`drc/by_rule.NOTES`).
- **Along a row the rule keeps the window of the list:** a pair with more than the gap contacts between it along the row is not judged, as a pair further apart in the list was not; the pins between are judged against their own neighbours. Round a ring the shorter way is counted, and on a tie the way with fewer free contacts. A finding along a row says so: *have 1 unassigned contact(s) between them along row 1 of the face, fewer than the 2 required*. Positions on the face are worked out from the rows as section 3 resolves them (only the pins of the connector).
- **The help of the rule** gets the second sentence of section 8. It is part of the *To fix it* text of every finding of the rule, also on a connector without a layout; the finding's ID and title (and so a waiver's hash) do not change, and no example or golden sets `power_return_gap_pins`, so no golden and no line of the output-hash baseline changes.
- **A-PIN-ORDER** is Generate's order of the pins, which does not read the rows (L2): it now says so, instead of the sentence on neighbours, which is in A-RETURN-GAP. The explanation of the rule (`derive_rules._power_return`) gives, for a pair on the face, where the pins sit, the contacts between them or why the pair is not judged, through the function the rule calls (`standard_rules.face_gap`).
- **A release does not lock the rows of a part** (section 3): `row_layout` joined the fields of a part that a release leaves editable (`vcs/locks.COSMETIC_PART_FIELDS`); a box connector's own rows were not locked already.
- **The scripting interface:** `RowLayoutRecord` carries `source_id` (the part or connector the rows come from) beside the six keys of section 10's `--json`; `set_row_layout` takes `rows` as lists of pin names or in the text form of 6.1.

### What pull request 3 changed

Pull request 3 is built as row 3 says, with these differences, each for the reason given:

- **The pinout table of a harness has the column while a connector of that harness has a layout** (section 3: its part's, else the mated box connector's); section 7 says *the same column* without a condition. A condition per harness keeps the pinouts of every other harness of the project as they were; `box_pinouts.csv` keeps the condition of section 7 (some box connector of the project).
- **`export-pinout` drops the column again** for a device none of whose connectors has a layout (`devices.pinout_sheet`), so such a device writes the file of 3.0.0 (section 6.3), while the Devices tab's table keeps the rows of `box_pinouts.csv` as they are (section 7). Reading the column back (`import-pinout`, section 6.2) is pull request 4; until then `import-pinout` passes over the column as over any heading it does not know.
- **`system/export.json` needed no new code:** `row_layout` is a sparse field of the models since pull request 1, so the file carries it where it is set, and `verify.py` already compares the parts and box connectors with the model. Pull request 3 adds its tests (the rows where set, nowhere else, a missing one refused) and the golden.
- **One reading of the rows for both verifiers:** `verify_plan.face_rows` (a second copy of the resolution of section 3) is used by `verify_plan.py` and by `verify.py` (`_faces`), since `verify.py` already imports `verify_plan.py` and the other way round would be a cycle; neither imports `core/row_layout.py` (a test reads their imports), and a Hypothesis test compares the copy with `layout_of`.
- **Column A of the harness sheet** is 16 wide (as column B) when a near block has a layout, so that *Pin row* fits; the widths are not checked by the verifier (as before).
- **The golden project** is `tests/row_layout_support.row_layout_project` (mini3 with the rows `1 3 / 2` on the part `EX-MICROD-9-F` and own rows `5 4 / 1` on `RW1-J02`): `tests/fixtures/outputs/row_layout.json` and `row_layout/` (the pinout tables and `export.json`), and its plans in `harness_plan/row_layout*` among the plan goldens. The requirement is REQ-OUT-12.

### What pull request 4 changed

Pull request 4 is built as row 4 says, with these differences, each for the reason given:

- **`pin-rows` is `cli/pin_rows_cmd.py`**, a module of its own beside `cli/document_cmd.py`, and calls the plans of pull request 2 (not the scripting functions, which take the project lock that the command line has taken already). Its `--json` has `ok` and `changed` first, as the other commands that change a project, and `source_id` beside the six keys of section 10, so that it is the record of `row_layout_of` (`docs/CLI.md`). `--rings` or `--no-rings` alone changes the ring mark of the part's or the connector's own rows; `--to-part` goes with `--set`, `--lengths` or a ring mark in one undo step, and not with `--clear`.
- **`import-pinout`:** the note names the whole command, `pin-rows --connector J1 --to-part`. Rows are equal also when the column's numbers equal them once a gap is closed up, so a file with a gap reads back as no change and the gap is noted only when rows are stored. A connector whose cells of the column are all empty keeps its rows (the column gives it none). The rows the import stores are compared with the rows the connector has by section 3, so a file with the part's rows changes nothing. The document of the command has the key `row_layouts` (the connectors given rows of their own) before `import`, and the import record has the lines of section 6.2 in its `notes` (no new key).
- **The device library commands needed no change to carry the rows:** `export_devices`, `plan_device_import`, `plan_update_device` and the subsystem file write and read the models of pull request 1 as they are. A part's rows reach a project with a part the project lacks; a part the project has is kept, as before, and the existing note says that it differs from the library's. The diff of `update-device` (and of the editor's review) lists `row_layout` of a device connector as a field, in the short form (`library_link.CONNECTOR_FIELDS`).
- **`explain`** names the rows as an input *Pin rows* of the connector's choice, with the source (*part EX-MICROD-9-F: row_layout (the rows of its part)*), only while the connector has rows, so the explanation of a connector without rows reads as at 3.0.0.
- **The help of `export-pinout`** is left to pull request 3, which writes the column; `import-pinout`'s help and `docs/IMPORTS.md` name it. REQ-PIN-07 records what this pull request holds (`tests/test_row_layout_cli.py`).

### What pull request 5 changed

Pull request 5 is built as row 5 says, with these differences, each for the reason given:

- **The dialog is `gui/row_layout_dialog.py`** (`PinRowsDialog`, with `rows_words`, the words of the row *Pin rows*). While typing it asks the plans of `core/row_layout_edit.py` and shows their sentence (*The rows cannot be stored on J1: the row layout names pin 22; J1 has no pin 22*); the window runs what it ends with through the controller (`set_row_layout`, `clear_row_layout`, `share_rows_with_part`), one undo step each, journaled on save as every edit.
- **Clear empties the box**; **Set rows** with an empty box then removes the rows (of a part, or the own rows of a connector, as *Back to the part's rows*). A connector cannot have no rows while its part has some (section 3), so a third action that removes rows would do what *Back* does.
- **Set rows with the rows of the part** on a connector without rows of its own stores nothing: the dialog opens with the rows the connector takes, and OK as it opened is no change. **Use for every connector of this part** takes the rows in the box, also when they were changed in the dialog: the plan `plan_share_with_part` is asked about the project as it would be with those rows on the connector, so the change stays one undo step.
- **The note `row_layout_pins_outside`** is not a finding (pull request 2), so the Problems list adds it from `EditorController.layout_notes()` as a row of severity Info, and the window's Problems button counts it, so the two numbers agree. A click on any of the three checks goes to the connector (`MainWindow.show_connector`: the Devices tab for a device connector, the Inspector for a cable connector or a part); section 9 names no fix, so the row menu offers *Edit the pin rows of …* where the rows come from (`problems_panel.rows_target`: a device connector itself, a cable connector's part or mated device connector, a part). The findings of the face rule (section 8) are findings of `power-return-adjacent` and go where they went.
- **The rows are on the line of the pin table, not a row of the connector card** (section 9 says *a row Pin rows* of the details): *Pins of J1  Rows: 1–11 / 12–21, from part …* then **Edit rows…** before **Add pin**, the text cut when the pane is narrow (the whole of it is the tooltip) and the button shown as its icon when the pane has no room for every button's text. A card row made the card taller and left the pin table one row high at 1440 x 900; for the same reason the count of the pins and the notes share one line under the table and *Source version* sits beside *Source*, and a test holds four rows of the pin table at that size, with the side panels open and closed.
- **The column *Pin row* of the pin table** is next to *Pin*, not last as in `box_pinouts.csv`: the table scrolls sideways at 1440 x 900, and a last column would be out of view. The saved widths of the table start again (`devices-pins-4`).
- **The connector editor of a harness** is not changed: row 5 names the Inspector of a cable connector, which shows the rows it takes (kind `cable_end`, any cable connector).
- **The screenshots** had no picture of the Devices tab; two are added (`docs/ux/qt/29-devices-pin-rows.png`, `30-pin-rows-dialog.png`), on the flatsat example with rows `1–5 / 6–9` that are an example of the form. The in-app guide and the user manual page are pull request 6.

### What pull request R changed

Pull request R is built as row R and section 11 say, with these differences, each for the reason given:

- **Three older names went, as Q29 listed them:** `revision` of each harness in `system/export.json` (`outputs/exports.py`, whose `JSON_VERSION` is 2), `revision` of each entry of `log --json` (`cli/changes.py`) and the expression field `harness.revision` (`core/extensions/fields.py`). A rule or table that names the field is refused by the existing check, *unknown field 'harness.revision' (did you mean harness.version?)*. `revise` stays (Q30), as do `diff --from` reading an old letter, `revision_not_version` with `merge-fix`, and the step from format 2: none of them was promised *through 3.0.x* only.
- **The verifier** compares each harness of `export.json` with the model as saved and asks for `format_version` 2 (`outputs/verify.py`, its own constant), so an export of 3.0.x reads `out_json` until it is written again; it checked before that the two names agreed.
- **The proof of 3.0.0** (`tests/format3_support.py`) has a sixth step, `drop_older_name`, after the word list of 3.0.0, which is kept as the record of what 3.0.0 changed.
- **`format_version` of the extension data files stays 1,** though `docs/developer/extensions.md` said that no field is removed without a new one: `harness.revision` was announced for 3.0.x only, and a new number would refuse every data file for a field that few name. The page says so. `PLUGIN_API_VERSION` and `API_VERSION` stay 1; the scripting interface had no older name.
- **Only `system/export.json` moved:** 4 entries of the output-hash baseline, 11 of the numbers snapshot and the goldens' entries of that file, written again once with the tools (`docs/changes.md`). The release notes of 4.0.0 (pull request 6) say it under *For scripts*.

### What pull request 6 changed

Pull request 6 is built as row 6 says, with these differences, each for the reason given:

- **The format 3 project of `tests/test_e2e_400.py`** is the sample `mini3`, generated and saved, with the number 3 written back (`tests/migration_support.as_format`), not a project made by the 3.0 fixtures: the step from 3 to 4 writes the number only (section 5.1), so these are the bytes a 3.0.x tool writes. The walk goes through the command line only: `migrate --dry-run` and `migrate` (every other file unchanged, but the journal's entry and the copy `project.json.bak` of the save), then, before any row, an export that is the golden set of `mini3` (which differs from the set of 3.1.0 in `system/export.json` only) and an `export.json` that is the file of 3.0.0 byte for byte once `revision` is put back, `format_version` 1 read and the version and the model hash read as 3.0.0's (the generation record names the version, so the model hash of a generated project changes with it; the SHA-256 of 3.0.0's golden and its model hash are in the test): so *a project without a layout writes what 3.0.x wrote, apart from the names R dropped* is checked, not only said. Then `settings --set generation.power_return_gap_pins=1` and `generate` (a setting of the generation and the rows are design data, so the generation is out of date before an export); `pin-rows --lengths 5,4` on `EX-MICROD-9-F` (`row_layout_pin_missing` on its connectors of three pins), `--set "1 3 / 2"` on the part and own rows `1 / 3 / 2` on `RW1-J01` (`row_layout_mate_differs` with its plug); `drc` with the pair of `PCDU-J01` across the rows and without the list pair of `RW1-J01`, whose pins are two rows apart; `export-pinout` read back as no change, and the same sheet with *Pin row* edited for `PCDU-J02` (`row_layout_pins_outside`); `explain`; `export --harness-plan --drawings`, `verify --outputs`, the column, column F, the near block and `export.json`; a second export byte-identical. It takes about 2 s, so it is not marked `slow`.
- **The read-only view of 3.0.x was tried** (section 17 said it was not): with the code of the tag `v3.0.0` (`git archive`, run in place of this version) on a format 4 project. Without rows, 3.0.0 opens it read-only (`newer_version`; `generate` and `export` refuse with *this project is read-only*, exit code 2). With rows, 3.0.0 sets each part and box connector that has them aside (*quarantined: … row_layout: Extra inputs are not permitted*), the connectors of such a part then name a part it lacks (`unknown_part`), and `generate` and `export` refuse the project as damaged (exit code 2) and write nothing. The user manual and the release notes say so. Which outputs 3.0.0 would write from that view is moot: it writes none.
- **The manual page** is `docs/user-manual/pin-rows-of-a-connector.md`, with output of this version on the practice project `wheel-link`; `define-a-device.md` links it from the pinout columns. *Upgrade a project* keeps its title and gets section 8 (format 3 to 4) beside section 7, as 3.0.0 added section 7; the manual's README names the page *Upgrade a project*. The glossary has *Pin row* beside *Row layout*, and `docs/OUTPUTS.md` a section *A row layout* in the form of *A splice*.
- **The changelog entries** of pull requests 1 to 5 and R keep their facts and order; four sentences written before the later pull requests were put right: *Nothing reads a layout yet* (pull request 1), *will call* (pull request 2), *reading it back with `import-pinout` comes with pull request 4* and *its `format_version` stays 1* (pull request 3; R made it 2). The entries name no pull request numbers, since none is merged.
- **The release notes** `docs/releases/4.0.0.md` are a draft in the form of the 3.0.0 draft, which its preparation finished (it added, for instance, the sentence that the format is frozen with the release). `python -m tools.release_notes check v4.0.0` and `notes` pass on a copy in which the preparation's two changes are made (the version 4.0.0 in `pyproject.toml` and `## Unreleased` named `## 4.0.0 (…)`), as for the 3.0.0 draft; in the tree itself `check` fails while `## Unreleased` has text, as it did then.

### What pull request 7 changed

Pull request 7 is built as row 7 says, with these differences, each for the reason given:

- **The read-only view was tried again with 3.1.0**, the latest release (the code of the tag `v3.1.0`, run in place of this version, on a project of this version made with `new --template first-steps` and `generate`). It does what pull request 6 found for 3.0.0: without rows, `validate` warns `newer_version`, `generate` and `export` refuse with *this project is read-only* (exit code 2) and `drc` reads the project; with the rows of a part, or own rows on a device connector, the part or the connector is set aside (*row_layout: Extra inputs are not permitted*), the connectors of such a part name a part it lacks (`unknown_part`), `validate` exits with 1, and `generate`, `export` and `drc` refuse the project as damaged (exit code 2) and write nothing. The loader, the models and the command line of 3.1.0 are those of 3.0.0. So the user manual and the release notes say *3.x* where they said *3.0.0*, and name `drc` beside `generate` and `export`.
- **The changelog entries** name their pull requests (#294 to #300), as the preparation of 3.0.0 did for its entries.
- **The records of 4.0.0** (the example projects, the fixtures, the goldens, the migration hashes, the inventories and the SBOMs) are made again with the repository's tools, as for 3.1.0 (D-254).

## 15. Risks

- **`master` writes format 4 from the merge of pull request 1.** A fault of 3.0.0 found later cannot then be released from `master` as 3.0.x: it goes into 4.0.0, or a branch from `v3.0.0` is released (whether the tag workflow takes a commit that is not on `master` was not checked, section 17). Held by merging pull request 1 last of the pieces that can wait, or after a 3.0.x patch release if one is due.
- **One more upgrade for every team, the second within days.** A 3.x tool opens a format 4 project read-only, so a team updates together. Held by a step that changes nothing but the number (section 5.2) and by the editor's upgrade question with its backup.
- **The face rule warns about Generate's own pin choices.** Generate keeps the list order (L2), so on a connector with a layout it may place power and return pins in rows next to each other, and the rule warns. The warning is about a real pair of contacts, which the list order did not show. The help says what to do; L2 is where the owner decides whether Generate follows.
- **Rows centred on each other is an assumption.** A face whose rows are offset otherwise (a high-density D-sub, a header) is judged with the pin across and both diagonals, which can give a warning that the real face does not need; it never gives fewer than a face of centred rows. A connector whose second row is offset by more than one contact would be judged wrong. The assumption is written in A-RETURN-GAP and in the user manual page. True offsets would be a field of format 5 (section 4.1).
- **Rings are judged within a ring only.** Pairs across rings are listed in `unchecked-config`, not judged.
- **An own layout drifts from the part's.** After *Use for every connector of this part* or a later change of the part, a connector may keep own rows that differ. `row_layout_mate_differs` covers mating pairs only; the Devices tab shows the source (*own rows*) beside the part's rows.
- **A person types the rows wrong.** Nothing in the project can check a layout against the real face. The checks of 4.3 catch names that do not fit; the plan's `CON_…` sheet and the pinout files show the rows for review against the ICD.
- **`import-pinout` stores rows on the connector,** not on the part, so a team that imports every device's pinout gets many own layouts. Held by the note of 6.2 and the button that moves them to the part.
- **Scripts.** A script that reads `box_pinouts.csv` or a harness pinout by position meets a new last column only in a project with a layout; one that reads `export.json` meets a new key only where set. The release notes say so.

## 16. Owner questions

Each with this design's recommendation. Everything else is chosen in the sections above, with its reason. The owner answered on 2026-11-19: *Continue as per your recommendations*; the four answers below follow from that.

- **L1. Does the rule `power-return-adjacent` read the face of a connector with a layout in 4.0.0?** Recommended: yes, as section 8 sets out, under the same rule ID and setting: on such a connector the neighbours across rows count and the list pairs that are not neighbours on the face do not; findings of existing projects do not change until a person enters a layout. Reason: the rule exists to keep power and return contacts apart on the real face, and the audit (DRC-C2-006) names the list order as wrong for staggered rows; one rule and not two keeps one finding per pair. Alternative A: a new rule `power-return-face` beside the old one, which stays on the list order (two findings for one pair on a connector with a layout; 40 rules). Alternative B: no rule reads the layout in 4.0.0; the layout is shown only. Then format 4 still holds everything a later rule needs (section 4.1).
  Answered 2026-11-19: yes. The rule `power-return-adjacent` reads the face of a connector with a layout in 4.0.0, under the same rule ID and setting, as section 8 sets out (pull request 2).
- **L2. Does Generate place pins by the face in 4.0.0?** Recommended: no; a later minor release (4.1.0), which needs no format change. Reason: it changes the generated pins of every connector that has a layout, needs the generator and the independent verifier changed together, and its proof is a release of its own; 4.0.0 stays a release of data, display and one check. The cost until then: the face rule may warn about Generate's choices on a connector with a layout (section 15). Alternative: in 4.0.0, as one more pull request after 2.
  Answered 2026-11-19: no. Generate does not place pins by the face in 4.0.0; it keeps the order of the pin list, and the help of the face rule says so (section 8). Placing by the face is for a later minor release.
- **L3. Does the starter library ship the layouts of its Micro-D and D-sub parts?** Recommended: no. Reason: the tool ships no standard values (D-11, D-12; *never invent standard values*), the starter parts are unverified examples, and a layout on them would change the outputs of every new project and example (a *Pin row* column) and their goldens. The row lengths of 6.1 make a Micro-D 21 a matter of typing `11, 10`. Alternative: the layouts of the starter connector parts as unverified example data, with the outputs and goldens of the examples made again once, in pull request 6.
  Answered 2026-11-19: no. The starter parts ship no layouts; the examples and their goldens do not change for a layout.
- **L4. Does 4.0.0 drop the older names that 3.0.x kept for scripts** (`revision` in `export.json` and `log --json`, `harness.revision` in the expression field; D-242 Q29)? Recommended: yes, in pull request R, with `format_version` 2 of `export.json`. Reason: the release notes of 3.0.0 promised them through 3.0.x only, and a major release is where scripts expect such a change; doing it in a 4.x minor release would break scripts in a minor release. `revise` stays as the older name of `new-version` (Q30: not removed in 3.x; it changes no written file and costs nothing). Alternative: keep the old names through 4.x and drop them with a later major release.
  Answered 2026-11-19: yes. 4.0.0 drops the older names of 3.0.x in pull request R, with `format_version` 2 of `export.json`; `revise` stays.

## 17. What this design does not check

- **No datasheet was read.** The layouts of section 1.1 are examples of the form; the rows of a real 9, 15, 21, 25 or 31 contact Micro-D or D-sub, of a high-density D-sub and of any circular insert were not compared with a manufacturer's drawing or a standard.
- **The centred-row assumption** of section 8 was not compared with real faces beyond the two-row staggered case it was drawn from.
- **No user** has seen a layout in the tool, and nobody asked the users which outputs they read rows in; the choice of the plan, the pinout files and the face rule is this design's.
- **The read-only view of 3.0.x** of a format 4 project with a layout (quarantined parts or connectors under the read-only banner) was not tried, nor what an export from that view writes. (Tried on the command line by pull request 6, section 14; the banner of the editor was not.)
- **Whether the tag workflow** (`harness-tag.yml`) takes a commit that is not on `master`, for a 3.0.x patch after pull request 1 (section 15).
- **The subsystem file at 3.0.0** stays version 1 with format 3 fields in it (section 5.5); how a 2.x tool words its refusal of such a file was not looked at.
- **Readers of the plan:** that column A of the harness sheet shows in LibreOffice and in Excel as the other device-side columns do was not tried; the printed page is the template's `H6:U64` and does not show it.
- **No code was written** for this page; the module and function names of sections 9, 10 and 14 are the plan, and the pull requests may name them otherwise, as the pull requests of 3.0.0 recorded where they differed from their design.
