# Design of 5.0.0: format 5

Written on 2026-11-23 from a reading of the code at 4.4.0 (annotated tag `v4.4.0` on `e6eddc0`, the merge of the preparation, #348; the checkout reports `4.4.0`) and from runs of the command line on copies of the `first-steps` example. It designs milestone E5 of [`ELEC_FEEDBACK_PLAN.md`](ELEC_FEEDBACK_PLAN.md) (points 1, 3, 7 and Ca of the feedback: *how lengths are defined: connector face to connector face, connector backside to connector backside, or mixed*; *solder joints and their positions: signal or power lines merged or split inside the harness (not enough single wires, or current limit rules)*; *shielding and backshell: where the shield is connected and where not*; *the effort to create the database and to check it*). Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the design of 4.0.0, the last change of the format ([`DESIGN_4.0_ROW_LAYOUT.md`](DESIGN_4.0_ROW_LAYOUT.md)), for the format step and its proof, and the designs of 4.1.0 to 4.4.0 ([`DESIGN_4.4_NAMES_PORTS.md`](DESIGN_4.4_NAMES_PORTS.md) the latest) for the rest: scope, what exists, the format, one part per field group, what changes in the written files, edge cases, tests, documents, the decision, the owner questions, the pull requests, the corrections to the plan and what was not checked. Choices that are the owner's are F1 to F16 (section 17), each with a recommendation first. Every device, part, harness and file name on this page is made up for the example (`OBC1`, `TTC1`, `PCDU1`, `EX-SPLICE-1`, `Example Ltd`), and so is every number of a depth or a current.

**Status (2026-11-24):** built; all its pull requests are merged, and 5.0.0 is published (annotated tag `v5.0.0` on `4c9cea5`, the merge of the preparation, #365, made by the tag workflow of D-227, run 45367163869; release workflow run 45367229630; `compliance/SIGNOFF.md`, *Publication of 5.0.0*). Pull requests 1 to 8 of section 18 are merged: 1 (*Format 5*, #353, after 4.4.1 was published on 2026-11-23, annotated tag `v4.4.1` on `27a3736`; `compliance/SIGNOFF.md`, *Publication of 4.4.1*), 2 (*Lengths*, #357), 3 (*Currents*, #359), 4 (*Splices from a connection*, #360), 5 (*Shield end places*, #361), 6 (*Checked devices*, #362), 7 (*The editor*, #363) and 8 (the end-to-end test `tests/test_e2e_500.py` with the documents of section 14, #364). Pull request 0, part F, is in 4.4.1 (#350). Pull request 9 is the preparation of 5.0.0 (#365), with the release notes `docs/releases/5.0.0.md` that row 8 of section 18 names (moved to pull request 9). The pull requests follow the recommendations of F1 to F16, and the owner answered yes to all of them on 2026-11-24 (D-267); the test row for a pigtail (F16) and an ICD importer (plan question 9) wait for inputs from a team. What was built differently and what was found on the way is at the end of section 19 (items 9 to 16). D-264 (section 16) is decided with the preparation, and the release is D-266: a major release, no release candidate first, format 5 frozen at the tag `v5.0.0`. *Added 2026-11-24, with the preparation of 5.1.0:* the minor release 5.1.0 (decision D-269; prepared, not tagged) writes format 5 unchanged, and format 5 stays frozen; its feature examples show the fields of format 5 (`splice-from-connection` the pin currents and a junction, `shields-and-ends` the places of the shield ends, `lengths-to-the-face` the face ends and depths, `device-library` a checked device; decision D-268).

*Written before any code (kept as it was):* draft. No code is written. No owner answer yet; the owner has said that the work goes on by the recommendations, so each question of section 17 has the answer the pull requests follow while it is open. The decision that records the design is D-264 (section 16), proposed. The release decision of 5.0.0 is a later row.

## 0. The frame

Four points of the feedback need data that format 4 cannot hold: where a length is measured to at each end and how deep a connector is (point 1); the current through each contact, so that a line split over several wires or joined in a splice can be checked (point 3); the pin a shield's pigtail lands on and the backshell a shield end uses (point 7); and whether a device of the library was checked, by whom, when and against which ICD (Ca). E0 to E4 did what format 4 allows: every length column says *rear to rear* (4.1.0), the Production sheet says *pigtail* where the pin is unknown (4.1.0), and the Review page shows the library state of a device (4.3.0). E5 adds the fields, together, so that the format changes once:

1. **One step of the format.** Format 4 is frozen since the tag `v4.0.0` (D-254); the model refuses unknown keys (`extra="forbid"`, `core/model/base.py`), so a new key is a new format, and a new format is a major release (D-226, D-230): **5.0.0**. Format 5 is frozen at its tag, as formats 2, 3 and 4 were.
2. **The step writes the number and nothing else.** Every new key is sparse (left out of the file while it has its default), and nobody has one before format 5, so the step from 4 to 5 is the step from 3 to 4 again: the number in `project.json`, the same model hash, the same findings, the same outputs (section 3).
3. **A missing value stays missing and is said** (D-11, D-84, D-88). No step, no default and no generator writes a depth, a current, a pin or a check that a person or an import did not give. Where a value is needed and absent, a check says so and the dependent number is *not known*, never zero.
4. **A format 4 project keeps its outputs.** Every new output text, column and finding appears only where a field of format 5 is set. With none set, a project's written files are those of 4.4.0 apart from the stamp `5.0.0`, which has as many characters as `4.4.0`; no new design rule is registered, so `Rules run: 43.` stays (section 11).
5. **The tool proposes and the person confirms** (D-172); **Generate makes no splice** (owner answer B8 of the design of 2.3.0).

## 1. Scope

### 1.1 In scope

| Part | What is built | Points |
|---|---|---|
| A | **Where a length is measured to, and the depth of a connector.** A cable connector says whether the segments that end at it are measured to its rear (where the wires leave the body or backshell; the meaning of every length of formats 1 to 4) or to its mating face (`Connector.length_to`); a project setting gives the default (`model.length_reference`, `rear`). A connector part and a backshell part get a depth (`Part.depth_mm`). At a face end the tool takes the depth of the connector and of its backshell off the path of each wire, so every wire length stays a length from rear to rear. No depth: the wire's length is not known, and `check` says why | 1 |
| B | **A current per pin.** A device pin gets the current through its contact (`Pin.current_a`, from the ICD; `import-pinout` reads a *Current* column). A wire's current comes from the pin currents of its net when every end has one and they add up, else from its interface as in 4.4.0, else it is not known. `current-over-wire`, `bundle-current`, `voltage-drop` and `current-over-contact` read it, so the wires of a harness made from a connection or drawn by hand are checked for the first time | 3 |
| C | **A splice in a harness made from a connection.** A link may pair one pin with several pins (a *junction*) and may repeat a pair (parallel wires); the harness made from such a link gets a splice for each junction, of a splice part the person chooses. The verifier compares a link with its harness net by net. Generate still makes no splice (B8) | 3 |
| D | **Where a shield end lands.** Each end of a shield group may name its place (`ShieldGroup.at_a`, `at_b`): the connector, the pin a pigtail lands on, the backshell (an accessory of kind `backshell` on that connector). The Production sheet, the build workbook, the plan, the drawing and `system/export.json` show it; `check` names a place that does not fit | 7 |
| E | **The checked state of a library device.** A device gets *checked by, on, against* (`Unit.checked`: the person, the date, the ICD and its version, and the SHA-256 of what was checked). The library file carries it; `check` says when the device changed since; the Review page and sheet, the Library window and the Devices tab show it | Ca |
| F | **The library update compares the ICD fields** (found on the way, section 2.6): `update-device` does not compare a connector's `source_doc`, `source_version`, `source_link` or a pin's `level`, so a library device whose only change is a new ICD version reads *up to date*, and `--apply` does not take it. A patch 4.4.1 before E5 (F14) | Ca |

And with them: the step `_v4_to_v5`, one setting (`model.length_reference`), eleven codes of `check`, three assumptions (`A-LENGTH-TO`, `A-ONE-SOURCE`, `A-PARALLEL-SHARE`), one command (`device-checked`), two kinds of `import-build-data`, one column of `import-parts` and of `import-pinout`, the device library file version 4 and the subsystem file version 3, and seven requirements (REQ-MIGRATE-10, REQ-WIRE-09, REQ-WIRE-10, REQ-HARN-05, REQ-OUT-17, REQ-LIB-08, REQ-GUI-33; REQ-LIB-09 for part F).

### 1.2 Not in scope

Every item that an earlier design or release deferred to format 5 or to E5 is listed here or in 1.1 (collected from `docs/ait/`, `docs/DECISIONS.md` and `docs/releases/`):

| Deferred item | Where it was deferred | In 5.0.0 |
|---|---|---|
| A length reference per cable connector end and a connector depth | plan E5; design of 4.1.0, section 1.2; D-257 | yes, part A |
| The pin a pigtail lands on, the backshell of a shield end | plan E5; design of 4.1.0, sections 1.2 and 8; D-257 | yes, part D |
| A current per pin, a split over parallel wires, splices of a harness made from a connection | plan E5 and question 6; design of 4.2.0, section 1.2 | yes, parts B and C |
| A checked state of a library device | plan E5; design of 4.3.0, sections 1.2 and 17 (item 5); `docs/releases/4.3.0.md` | yes, part E |
| The reviewer's ticks stored in the project | plan question 8; design of 4.3.0, section 1.2; D-261; `docs/releases/4.3.0.md` | **no** (F15): the plan recommends the sheet and the comment first, and no team has asked since 4.3.0 |
| A shield demand per signal or per pin | design of 4.2.0, sections 1.2 and 4.1; D-259 | **no** (F15): the feedback's example is answered by the interface type (E2); a field would need Generate and the verifier to shield per signal |
| True offsets of the rows of a connector face (a drawn face) | design of 4.0.0, sections 4.1 and 15 | **no** (F15): no face view is asked for |
| The release keys and the checklist in a config file of their own | design of 4.3.0, R1 | **no** (F15): moving keys changes every project's model hash, which the step of section 3 must not |

Also not in scope:

- **Generate's gauge from the pin currents.** Generate sizes a wire from its interface's current as in 4.4.0 (`generate/engine.py`); the rules judge the wire with the pin currents (F5).
- **Splices made by Generate** (B8), and splices placed by hand in a harness made from a connection: a splice there comes from a junction of the link (F8).
- **A test row per pigtail** in `tests.csv` (F16).
- **A face view or a formboard drawing to scale.**
- **Currents in the build workbook, the Production sheet or the labels.** They are for sizing, not building.
- **Everything of E4** (4.4.0) and the ICD importer that waits for an example (plan question 9).

## 2. What exists at 4.4.0

### 2.1 The format and its steps

`SCHEMA_VERSION = 4` (`core/model/project.py`). `core/io/migrate.py` holds the steps, `MIGRATIONS = {0: _v0_to_v1, 1: _v1_to_v2, 2: _v2_to_v3, 3: _v3_to_v4}`; `_v3_to_v4` runs `V3_TO_V4_PARTS = (_v4_number,)`, which writes the number 4 in `project.json` and nothing else. `core/io/upgrade.py` is the safety net (D-202): `plan_upgrade` for `migrate --dry-run`; `upgrade_project` copies every file into `.migration-backup-v<N>/`, writes `MIGRATION.json`, writes the project, reloads it and compares the model hash (which reads every format number as 1, `layout.schema_one`, `HASH_SCHEMA_VERSION`), the findings of `validate` and `check`, the baselines and an in-memory export; any difference puts every file back. The loader opens a newer format read-only (`core/io/loader.py`: *This project was saved by a newer version of the tool (format 5; this tool understands up to 4). It is opened read-only.*) and reads an older one in memory (`migrated`); `save_project` refuses to write an older format over its folder until it is upgraded (`core/io/saver.py`). A part, a connector, a unit or a harness with a key the models do not know is set aside (*quarantined*). The design of 4.0.0 (pull requests 6 and 7) tried a 3.x tool on a format 4 project: read-only without the new key; with it, the objects that carry it are set aside, the connectors of a set-aside part name a part it lacks, and `generate`, `export` and `drc` refuse the project as damaged.

Sparse keys: `SparseEntity.OMIT_WHEN_DEFAULT` (`core/model/base.py`) leaves a field out of every dump while it has its default, so a project that does not use it keeps its bytes, its model hash and its outputs.

The device library file (`core/device_library.py`) is written as the lowest version that holds its content (`content_version`): 3 while a box connector or a part has `row_layout`, 2 while a field of format 3 is used, else 1; a reader refuses a higher version (*The file is version 4; this program reads version 3. Use a newer program to read it.*). The subsystem file (`core/subsystem_library.py`) is version 2 while it holds a row layout, else 1.

### 2.2 Lengths

`generate/lengths.py`: `path_length(h, start, end)` sums the segments of the one path through the tree between two nodes; `wire_length(h, w)` is the wire's own `length_m`, else that path (the one function every table, the mass, the rules and the release gate ask); `generated_length` adds `model.service_loops_per_wire` loops of `generation.service_loop_m` (and, under the length model `path_loops_allowance_twist`, the take-up of twisting and a cut allowance); `length_origin` says *on the wire*, *locked* or *segments only, no service loops*. A segment runs between two nodes (a connector of the harness or a branch point); `docs/models/wire-length.md` says that a segment runs from the rear of a connector, *where the wires leave its body or backshell*, to the centre of a branch point.

Since 4.1.0 every length column says so: the Production sheet's *Length (m), rear to rear* (`outputs/production.py` `HEADER`), the plan's *Length [mm] rear to rear* (`outputs/harness_plan.py` `LENGTH_HEAD`), and the four sentences of `lengths.reference_lines` in `H9` of the plan, row 2 of the Production sheet and the *Cut list* and *Routing* sheets of the build workbook (`outputs/buildsheet.py`). The verifier has its own copies (`outputs/verify_production._length`, `_length_origin`, `_length_lines`). `segments.csv` and the *Routing* sheet name the two nodes of each segment (`outputs/tables.segments`).

A connector part has no depth. `Part.ratings` (a free table of numbers, `core/model/library.py`) could hold one, but nothing reads it and `import-parts` reads only the rating names of `library_import.RATING_KEYS` and the contact rating key (`rating_keys`). A cable connector is rebuilt by Generate on each run (`generate/engine._build_harness`), which keeps its `label` and, for a connector a person edited (`locked`), its part, gender, keying and pins (`_keep_edited_connector`).

### 2.3 Currents

`InterfaceInstance.max_current_a` (`core/model/logical.py`) is the only current. The rules take it for each wire of the interface: `current-over-wire` (`core/drc/rules._current_over_wire`), `bundle-current` (`core/drc/standard_rules._bundle_current`), `voltage-drop`, and the explanations (`core/derive.wire_current_limit_derivation`, `wire_voltage_drop_derivation`); `current-over-contact` (`rules._current_over_contact`) compares the whole interface current with the rating of *each* contact of each connector it ends on (`Part.ratings[derating.contact_rating_key]` × `contact_current_factor`). So a power interface carried on three parallel contacts is judged as if each contact carried all of it. The ampacity is the project's own table (`derating.ampacity_a_by_awg`; empty by default, D-11), derated by the bundle and temperature factors (`sizing.wire_current_limit`).

A wire with no interface (drawn by hand, or made from a connection) carries no current: `rules._wires_without_interface` writes one note, *Current, voltage-drop and bundle checks did not run for N wire(s) of harness W003: they have no interface to take a current from*. A pin has no current. `import-pinout` names a *Current* column among the headings it does not store (`pinout_import._UNSTORED`: *remarks, notes, comment, voltage, current, class*) and warns.

### 2.4 Splices and links

A splice (format 3, `core/splices.py`) is a connector of role `splice` whose part is of category `splice`; each pin is a node that joins every wire on it (`core/nets.py`: `harness_nets`, `Net.ends`, `Net.splices`, `end_pairs`, `path_wires`; the verifier and the output check each have their own copy, compared by `tests/test_nets.py`). `splices._drawn` refuses a harness Generate made (*makes no splice*), a released one, and one made from a connection: *W003 was made from the connection L1, which owns its pairs of pins, so it takes no splice.* The starter library has no splice part (and no backshell part: section 2.7).

A link (`Link`, `PinPair`) pairs a pin of one device connector with a pin of the other. The link review (`links._check_link`) makes a pin in two pairs of one link, or in two links, the error `link_pin_reused` (*Pin 1 of PCDU1-J01 is in two pairs of link L1. Keep one pair for it.*), and `links.plan_create_harness` refuses a link with that error. So a link cannot say *pin 1 of PCDU1 goes to pins 1, 2 and 3 of OBC1*. The harness made from a link has one wire per pair, no gauge, colour or length. The verifier (`core/verify.link_issues`) counts the wires between the two cable connectors pin by pin and reports any difference from the pairs as `link_wire_mismatch`; a wire through a splice would be *a wire which link L1 does not pair*.

### 2.5 Shield ends and backshells

`ShieldGroup` (`core/model/physical.py`) has `kind`, `wire_ids`, `end_a` and `end_b` (`backshell_360`, `pigtail`, `floating`) and names no connector. End A is the `from` end of the group's wire with the lowest ID, end B its `to` end (`core/shield_ends.end_at`; the verifier's copy is `verify_production._end_at`). Generate gives every group it makes the ends of the grounding concept (`generation.shield_end_a`, `shield_end_b`; a coax both `backshell_360`; `generate/shields.ends_of`), also a `twisted_pair`, which has no shield; a person sets the ends of a group they made (`wires.plan_regroup`, `plan_set_group_ends`, the window *Change group*, `gui/harness_edit_dialogs.ChangeGroupDialog`). The rules `shield-unterminated`, `shield-wrong-end`, `shield-bonding` and `shield-parts` read the ends and the parts. The Production sheet writes *W001-S9 shielded pair: here pigtail, far floating* (`production._shield_text`); for a pigtail it cannot say where it lands (design of 4.1.0, section 8). A backshell is an accessory of kind `backshell` on a connector (`Accessory.target`, 1.7.0), listed by the plan under *used Backshells*; nothing ties it to a shield end. A pin may have the role `shield`; no group points to it.

### 2.6 Devices of the library, and the ICD fields

A device library file (`harness-device-library`) and a `NAME.device.json` file (D-240) carry a device, its box connectors with their pins and the parts they name. A connector names the ICD it came from (`Connector.source_doc`, `source_version`, `source_link`, format 3). `core/library_link.py` keeps a project device in step with the library: `link_state` (*up to date*, *library changed*, *changed here* …) and `update-device` compare the library-owned fields `UNIT_FIELDS` (`kind`, `mass_relevant`, `notes`), `CONNECTOR_FIELDS` (`name`, `part_id`, `gender`, `keying`, `carries`, `notes`, `label`, `row_layout`) and `PIN_FIELDS` (`signal`, `fixed`, `function`, `contact_size`, `termination`, `contact_part`, `role`, `direction`). Parts have an approval (`Part.approval`, `unverified`); a device has nothing of the kind.

**Run** (a copy of `first-steps`; `save-device p RW1 --library lib`; in `lib/RW1.device.json` the connector RW1-J01 given `source_doc` `ICD-RW`, `source_version` `Issue 2` and pin 1 the level `3V3`): `update-device p RW1 --library lib` says *RW1: up to date.*, and with `--apply` the project's connector file holds neither `Issue 2` nor `3V3`. With the function of pin 1 changed as well, the diff lists only `function`, and `--apply` takes the whole connector, the ICD fields and the level with it. So `_family_rows` leaves out the four fields of format 3, `link_state` reads *up to date* when only they differ, and `plan_update_device` takes nothing (`if not rows: ops = []`). A device whose ICD moved to a new issue looks current. Part F fixes this, and part E needs it.

### 2.7 What the examples hold

Counted with a throw-away script on the five examples and the three fixture projects:

| Project | Devices, connectors, pins | Harnesses (wires) | Shield groups | Ends of a shield: pigtail, backshell 360 | Backshell accessories, parts | Splices, links | Interfaces with a current |
|---|---|---|---|---|---|---|---|
| `blank` | 0, 0, 0 | 0 | 0 | 0, 0 | 0, 0 | 0, 0 | 0 of 0 |
| `first-steps` | 3, 9, 120 | 0 (generated on demand) | 0 | 0, 0 | 0, 0 | 0, 0 | 1 of 2 |
| `minimal-satellite` | 7, 37, 595 | 0 | 0 | 0, 0 | 0, 0 | 0, 0 | 6 of 11 |
| `small-satellite` | 14, 75, 1204 | 0 | 0 | 0, 0 | 0, 0 | 0, 0 | 0 of 24 |
| `flatsat` | 23, 109, 1789 | 8 (103) | 60 (33 twisted pairs, 16 shielded pairs, 10 overall, 1 coax) | 0, 28 | 0, 0 | 0, 0 | 20 of 44 |
| fixtures `mini3`, `sat15`, `custom_device` | 3, 8, 28; 14, 75, 1204; 3, 18, 183 | 1 (2); 24 (54); 2 (4) | 0; 32; 3 (all ends floating) | 0, 0 | 0, 0 | 0, 0 | 0 |

No pin of any example or fixture has the role `shield` stored or a `source_version`; the starter library has no backshell and no splice part; the 24 connector parts of `flatsat` carry ratings. So no example or fixture can use a field of format 5 without a person adding data, and the 28 backshell ends of `flatsat` name no backshell (none exists). The output goldens `splices` and `row_layout` (`tests/fixtures/outputs/`) are made by `tests/splice_support.splice_project` and `tests/row_layout_support`.

## 3. Format 5 and the step from 4 to 5

### 3.1 The keys

Six keys, each sparse, none written by the step:

| Where | File | Key | Type, default | Part |
|---|---|---|---|---|
| a cable connector | its harness file (`physical/harnesses/…`) | `length_to` | `"face"` or `"rear"`, `None` (the project's setting) | A |
| a part of category `connector` or `backshell` | `library/<category>.json` | `depth_mm` | `LengthMm` > 0, ≤ 1000, `None` | A |
| a pin of a box connector | `physical/connectors/…` | `current_a` | number > 0, ≤ 1000 (amperes), `None` | B |
| a shield group | its harness file | `at_a`, `at_b` | `ShieldEndPlace`, `None` | D |
| a device | `logical/units/…` | `checked` | `DeviceCheck`, `None` | E |

`ShieldEndPlace` (new sparse model, `core/model/physical.py`): `connector` (an ID, required), `pin` (a `PinId`, `None`), `backshell` (the ID of an accessory, `None`). `DeviceCheck` (new model, `core/model/logical.py`): `by` (`Name`, required), `on` (`IsoDate`, required), `icd` (`Name`, required: the ICD and its version as the person names it), `sha256` (64 hexadecimal characters, required: what was checked, section 8.1).

A shield group of `flatsat` with a pigtail stated, and a checked device, as they would stand in the files:

```json
{"id": "W001-S2", "kind": "shielded_pair", "wire_ids": ["W001-003", "W001-004"],
 "end_a": "pigtail", "end_b": "floating", "at_a": {"connector": "W001-P1", "pin": "9"}}

{"id": "TTC1", "name": "Transceiver 1", "subsystem": "ttc", "side": "nominal",
 "checked": {"by": "Reviewer 1", "on": "2026-11-23", "icd": "ICD-TTC Issue 3",
             "sha256": "5f1c…"}}
```

**Why `length_to` can be unset.** Unset means *the project's setting* (`model.length_reference`, default `rear`, section 4.2). A team that measures every end to the face says so once; a connector that differs says so on its own. With no setting and no key, every length means what it meant in formats 1 to 4 (rear), which is the tool's own definition (`docs/models/wire-length.md`), not a value it assumes about a team's data (F2).

**Why the place of a shield end names its connector.** A group names no connector, and its end A follows its lowest wire ID (2.5): deleting or renaming a wire can swap the ends. A pin alone (`"9"`) could then be read on the other connector, which may have a pin 9 too. With the connector stored, a swap is found (`shield_end_moved`, section 10.2).

**Why the check stores a hash and not a copy.** The check must notice any later change of what was checked (a pin's direction, a new ICD issue), and a copy of every field of the device would double the device in the file. The hash is of the library-owned fields (8.1); the message says *changed since* and points to the journal and to `update-device`, which show what.

### 3.2 The rules of the files

Each rule is checked when a file is read; an object that breaks one is set aside with the reason, as any invalid object today.

1. `current_a` only on a pin of a box connector (`unit_id` set); > 0 and ≤ 1000.
2. `length_to` only on a connector of role `cable`.
3. `depth_mm` only on a part of category `connector` or `backshell`; > 0 and ≤ 1000.
4. `at_a`, `at_b`: not on a group of kind `twisted_pair` (it has no shield); a `pin` only with the end `pigtail`; a `backshell` only with the end `backshell_360` or `pigtail` (F9); at least one of `pin` and `backshell`; none with the end `floating`.
5. `checked`: all four keys; `on` a date; `sha256` 64 hexadecimal characters.

Not rules of the files, because they relate one object to another: that the connector of `at_a` is the connector at end A, that the pin and the backshell exist there, that the depth of a face end is known, that the pin currents of a net add up, that a check is current. These are codes of `check` (section 10.2), so a stale value never sets a whole harness aside.

### 3.3 The step

`_v4_to_v5` in `core/io/migrate.py`, `V4_TO_V5_PARTS = (_v5_number,)`, `MIGRATIONS[4] = _v4_to_v5`, `SCHEMA_VERSION = 5`: **the number 5 in `project.json`, and nothing else.** The backup folder is `.migration-backup-v4/`, the record `MIGRATION.json`, the journal entry *migrated from format 4*, as for the earlier steps; `migrate DIR --dry-run` and the editor's upgrade question show the one change. A format 3 project goes through 3 to 4 and 4 to 5 in one upgrade, a format 2 project through three steps (with `--set-version` where the step from 2 to 3 needs it).

What the step does to each new field:

| Field | After the step | Read as | Said where |
|---|---|---|---|
| `length_to` | absent | the setting, absent: rear (the meaning of format 4) | nowhere: no length changes |
| `depth_mm` | absent | not known | only when a face end needs it (`length_depth_missing`) |
| `current_a` | absent | not known; the interface's current applies as in format 4 | nowhere: no check changes |
| `at_a`, `at_b` | absent | not stated | `check` (an info) for a pigtail end only (F11) |
| `checked` | absent | not checked | the Review page and the Devices tab say *not checked* once any device of the project is checked |

### 3.4 The proof

The step changes no hash, so the safety net of D-202 is the whole proof, as for the step from 3 to 4 (design of 4.0.0, section 5.2):

1. **Nothing but the number** (the run-time check of every `migrate`, no new code): the same model hash, the same findings of `validate` and `check`, the same release consistency, the baselines byte for byte, the same in-memory export.
2. **No key appears.** `tests/test_format5.py` checks, for every fixture project and example, that after the step no pin has `current_a`, no connector `length_to`, no part `depth_mm`, no group `at_a` or `at_b`, no unit `checked`, that `project.json` differs in the number only and that every other file is byte-identical.
3. **The written files.** The export of each example and fixture read as format 4 by 4.4.0 rules (in memory) and after the upgrade is the same, byte for byte, with and without the harness plans; `tools.output_hashes --check` and `tools.numbers_snapshot --check` say *identical*, since `5.0.0` has five characters and the tool replaces the stamp (`as_in_base_version`), and `Rules run` stays 43.

### 3.5 What older tools do

- **4.x opens a format 5 project read-only** (the loader's check). Without a new key, `validate` warns `newer_version` and `generate` and `export` refuse with *this project is read-only*. With one, the objects that carry it are set aside: a box connector with a pin current (so its device loses the connector, and the cable connectors that mate with it name a connector that is gone), a harness with a cable connector's `length_to` or a group's place, a part with a depth (its connectors then name a part it lacks), a unit with a check. `generate`, `export` and `drc` then refuse the project as damaged and write nothing, as 3.x did with format 4. The release notes and *Upgrade a project* say: the whole team updates at the same time. Nothing in 4.4.x changes for this.
- **A device library file of version 4** (section 3.7) is refused by 4.x with *The file is version 4; this program reads version 3. Use a newer program to read it.*; the other files of the folder are still offered (the folder rules of D-240).
- **5.0.0 writes format 5** for every project it saves after the upgrade.

### 3.6 Merges across the upgrade

As for format 4 (design of 4.0.0, section 5.4): a branch in format 4 brings valid format 5 files; Git keeps the number 5 unless both branches changed the line. `merge-fix` does not change. The manual says to upgrade the main branch first.

### 3.7 The library files

- **The device library file** gets **version 4**, written only when a part has `depth_mm`, a pin `current_a`, or a device `checked` (`FORMAT5_KEYS`, checked before `FORMAT4_KEYS` in `content_version`); else 3, 2 or 1 as today. A `NAME.device.json` file keeps its rules and may carry all three.
- **The subsystem file** gets **version 3** by the same rule.
- `length_to` and `at_a`, `at_b` belong to harnesses, which no library file carries.

## 4. Part A: where a length is measured to, and the depth of a connector

### 4.1 What a face end means

A segment that ends at a cable connector ends at its rear (today) or at its mating face. The mating face of a cable connector meets the face of the device connector it plugs into, so a length from a mechanical model of the boxes is often a length to the face. The wires leave the connector at its rear, or, with a backshell, where they leave the backshell: that is the **depth** of the end, from the face back to where the wires come out.

The depth of an end is the `depth_mm` of the cable connector's part, plus the `depth_mm` of the part of each accessory of kind `backshell` on that connector (`Accessory.target`): for a backshell part, `depth_mm` is what it adds behind the rear of the connector (F3). A face end with a backshell that has no part, or a part without a depth, has no depth.

A wire's path from rear to rear is then

`path = (sum of the segments between its two nodes) − depth(from end, if face) − depth(to end, if face)`

and everything else stays as it is: the service loops, the take-up and the cut allowance are added to this path (`generated_length`), and every length column stays *rear to rear* (F4). An end on a splice, a branch point or a connector of another role has no face.

**Example** (made-up numbers): harness W001 with one segment W001-L1 of 1.200 m between W001-P1 and W001-P2, both measured to the face; the part of both, `EX-MICROD-9-M`, has `depth_mm` 25; a backshell `EX-BACKSHELL-9` with `depth_mm` 30 sits on W001-P1. Path from rear to rear: 1.200 − 0.055 − 0.025 = 1.120 m; with two loops of 0.1 m Generate stores 1.320 m.

### 4.2 Where it is set

- **The project's default:** `model.length_reference`, `rear` (default) or `face` (section 10.1). Generate reads it, so it is an input of generation.
- **A cable connector:** `length_to` `face` or `rear` overrides it; unset follows the setting. Generate keeps it on a regenerated cable connector, as it keeps the label (`_build_harness`: `old_cables[box_id]`), and on a cable connector taken over from a joined group (`taken_cables`).
- **A part:** `depth_mm`, in the parts list (Inspector of a part), by `import-parts` (a column *Depth (mm)*, headings `Depth`, `Depth (mm)`, `Connector depth`, in millimetres) and through a device file (a part travels with its connectors).
- **`import-build-data`**: a new kind told by its headings, *cable ends*: `Connector` and `Lengths to` (`face` or `rear`), `Harness` optional while the connector ID is unique; an empty cell leaves the value as it is, `project` sets it back to the setting.

### 4.3 Who reads it

One function, `lengths.end_depths(project, h) -> EndDepths` (the depth in metres of each face end of the harness, and for each face end without one the reason), and `lengths.wire_length(h, w, ends=None)`: with `ends` empty or `None`, the function of 4.4.0. Every caller that has the project passes `end_depths` (the tables, `production.py`, `harness_plan.py`, `buildsheet.py`, the mass, the rules, the release gate, `derive.wire_length_derivation`); a wire with a stored length (`length_m`) is not touched (Generate's lengths already have the depth taken off). Generate (`engine`, where it sets `length_m`) takes the depths off the path before `generated_length`; when a face end has no depth it stores no length and notes `length: W001-001 has no length: W001-P1 is measured to its face and part EX-MICROD-9-M has no depth (library: depth_mm)`. The cache of paths (`_PATHS`) is keyed as today; the depths are taken off after it.

The verifier's copy (`verify_production._length`) gets its own copy of `end_depths`, compared with the core's by a Hypothesis test, as the copies of the nets are.

### 4.4 The outputs

All sparse: they change only for a harness with a face end, or a project whose setting is `face`.

| Output | Change | Verifier |
|---|---|---|
| the length note (`lengths.reference_lines`: `H9` of the plan, row 2 of the Production sheet, the *Cut list* and *Routing* sheets) | a fifth sentence: *At W001-P1 and W001-P2 the segments run to the mating face; the depth of the connector and its backshell is taken off each wire there.* With the setting `face`: *The segments run to the mating face of each connector (model.length_reference), but at W001-P3; the depth of the connector and its backshell is taken off each wire.* | `verify_production._length_lines` |
| `segments.csv`, the *Segments* sheet, the *Routing* sheet | the node of a face end reads `W001-P1 (face)` | `outputs/verify._segment_rows` |
| the wire lengths (wire list, cut list, Production sheet, plan, mass, voltage drop) | the depths taken off, where the path is used | the copies of `_length` |
| `explain DIR W001-001` | inputs *Depth of part EX-MICROD-9-M (W001-P1, measured to its face)* and of the backshell; a step *Path from rear to rear* | — |
| the drawing (`export --drawings`) | the connector's caption gets *lengths to the face* | — |
| `system/export.json` | `length_to` and `depth_mm` where set; `field_units` names `depth_mm` in mm | `outputs/verify.py` (the model fields) |

The headings *Length (m), rear to rear* and *Length [mm] rear to rear* do not change: they stay true.

### 4.5 The editor and the command line

- **Cable end** (`gui/cable_end_dialog.py`, the Inspector of a cable connector): *Lengths measured to: the project's (rear) / rear / face*, one undo step, refused in a released harness.
- **Inspector of a part** of category `connector` or `backshell`: *Depth (mm)*.
- **Settings > Model**: the setting.
- `settings DIR --set model.length_reference=face`; `import-parts` and `import-build-data` as above. No new command.
- Scripting: `set_length_reference(folder, harness, connector, to)` (`"face"`, `"rear"` or `None`).

## 5. Part B: a current per pin

### 5.1 The field and where it comes from

`Pin.current_a`: the current through the contact in operation, in amperes, as the device's ICD states it. Only on a pin of a device connector (rule 1). It is entered in the Devices tab's pin table (a column *Current (A)*, shown while a pin of the connector has one, and from the column menu), read by `import-pinout` (section 5.5), carried by device files, and compared by `update-device` (part F adds it to `PIN_FIELDS`). Generate does not read it (F5) and copies it to no cable pin.

### 5.2 The current of a wire

One function, **`core/currents.py`** `wire_currents(project, h) -> dict[str, WireCurrent]` (`value`, `source` `pins`, `interface` or empty, the words of its reason), pure, used by every rule and explanation that today reads `i.max_current_a` for a wire:

1. For each net of the harness (`nets.harness_nets`), the **current of each end**: the pin current of the device pin the end is (a wire on a device connector) or mates with (a cable connector's `mates_with` and the pin of the same ID). An end on a splice is no end (`Net.ends`); an end on a loose end or a test connector has no current.
2. **When every end of the net has a current** and they **add up** (the largest equals the sum of the others, within the tolerance of `exceeds`; `A-ONE-SOURCE`): join the wires between the same two pins into one branch. If the branches form a tree, the current of a branch is the smaller of the sums of the ends on its two sides; a branch of k wires shares it equally when the k wires have the same gauge and the same length (`A-PARALLEL-SHARE`), else its wires are not worked out. If the branches do not form a tree, no wire of the net is worked out.
3. **Else** the current of the wire's interface (`max_current_a`), as in 4.4.0; else none.

In a project with no pin current, step 2 never runs and every wire gets what 4.4.0 gives it. For a net with one source the smaller sum is the current through the branch: the source's side holds the source and the loads beyond it, so it is the larger.

**Example** (made-up numbers): PCDU1-J01 pin 1 gives 6 A; OBC1-J01 pins 1, 2 and 3 take 2 A each (the OBC's contacts are rated 3 A, so the line is split). Harness W003 joins them in splice W003-X1 (part C): W003-001 from W003-P1.1 to W003-X1.1 carries min(6, 2 + 2 + 2) = 6 A; W003-002 from W003-X1.1 to W003-P2.1 carries min(2, 6 + 2 + 2) = 2 A, and so W003-003 and W003-004. The net adds up (6 = 2 + 2 + 2). Two wires in parallel from W003-P1.1 to W003-P2.1, of one gauge and length, with 6 A at both pins, carry 3 A each.

### 5.3 The rules and checks that read it

No rule is added (F7). With pin currents set:

- `current-over-wire`, `bundle-current` and `voltage-drop` take `wire_currents` in place of `i.max_current_a`; their texts and IDs stay. The wires of a harness made from a connection or drawn by hand get a current from their pins and are judged for the first time.
- `current-over-contact` judges a pin with a current on its own: the finding `OBC1-J01.1`, *Pin 1 of OBC1-J01 carries 2 A but its contacts allow 1.5 A after derating*. The finding per interface and connector of 4.4.0 stays for the pins of that interface at that connector that have no current.
- The note of `rules._wires_without_interface` reads, while some pin of the project has a current, *… they have no interface and no current on their pins to take a current from*; else the text of 4.4.0.
- `check` gets `current_unbalanced` (warning: *The pin currents of the net of W003-001 do not add up: 6 A at PCDU1-J01.1; 2 A, 2 A and 1.5 A at OBC1-J01.1, .2 and .3. Its wires were not checked for current. Correct the currents of the pins.*) and `current_not_worked_out` (info: a net with a loop other than equal parallel wires). The warning reaches the DRC as `model-inconsistent`, as every warning of `check_integrity` does.
- The explanations (`derive.wire_current_limit_derivation`, `wire_voltage_drop_derivation`, `contact_current_derivation`) name the pin currents of the net, the branch, the share and the assumptions; `explain DIR W003-002` shows the example above.
- The extension field `wire.current_a` (`core/extensions/fields.py`) and the wires table of `export-data` (`core/open_data.py`) take `wire_currents`; their values do not change where no pin has a current.

### 5.4 The outputs

| Output | Change | Verifier |
|---|---|---|
| `system/box_pinouts.csv`, the Devices tab's pinout table | a column **Current (A)** after the last column while some device pin of the project has a current | `outputs/verify._pin_rows`, `_pinout_header` |
| `export-pinout` | the column while a pin of the device has one, so that the file reads back | — (read back by `import-pinout`) |
| harness plan, `CON_…` sheet | a column **Current [A]** after *Description* (and after *Pin row* when there is one) while that connector has a pin current | `verify_plan.expected_plan` |
| `system/export.json` | `current_a` where set; `field_units` names it in A | `outputs/verify.py` |
| findings | section 5.3 | — |

Not changed: the harness pinouts (`harnesses/<ID>/pinout.csv`: cable pins carry no current), the build workbook, the Production sheet, the labels, the BOM.

### 5.5 `import-pinout`

A column **Current** (headings `Current`, `Current (A)`, `Pin current`, `Max current`, compared as today without case, spaces and signs; `Current (mA)` in milliamperes): a number, or a number followed by `A` or `mA`. `current` leaves `_UNSTORED`. Every conversion is listed in the import record (`import_record.Conversion`), as lengths are. A cell that is not a positive number refuses its line with the row number. A sheet that 4.4.0 read with a *Current* column, read again by 5.0.0, now writes the currents: the preview shows them, as any change.

## 6. Part C: a splice in a harness made from a connection

### 6.1 Junctions and parallel pairs in a link

The owner's question 6 recommends a splice on a harness made from a connection, with a current per pin. A link cannot ask for one today (2.4). In format 5 a link may hold:

- **a junction**: one pin in several pairs of the link (`(1, 1)`, `(1, 2)`, `(1, 3)`): the pin is joined to each of the other pins. A junction may be on either side; a net with m pins of one connector and n of the other joins every pair of them.
- **a parallel pair**: the same pair twice: two wires between the same two pins.

`link_pin_reused` stays an error for a pin in two links, and for a pin in two pairs of one link when the pairs make a net that joins two pins of the same connector to each other without a pin of the other side (it cannot carry anything across). The link review gets `link_junction` (info: *Pin 1 of PCDU1-J01 is joined to pins 1, 2 and 3 of OBC1-J01 (a junction); the harness made from the link joins them in a splice.*). The Link window (`gui/link_dialog.py`) lets a person pair a pin again by hand and shows the junction; the proposal (`propose_pairs_between`) still proposes one pair per pin.

A 4.x tool reads such a link as `link_pin_reused`. No key is new, but the reading of the pairs is, which is why it is in format 5 (section 19, item 3).

### 6.2 The harness made from such a link

`links.plan_create_harness(project, link_id, splice_part=None)`:

- A link without a junction: as today, one wire per pair; a parallel pair gives two wires on the same two cable pins (the rule `pin-shared` warns, as for any pin with two wires: the person checks the contact takes two).
- A link with a junction and no `splice_part`: refused, *Link L1 joins pin 1 of PCDU1-J01 to 3 pins of OBC1-J01. Choose a splice part (category splice) for the joint; the harness gets one splice for each junction.*
- With `splice_part` (a part of category `splice`, `splices.splice_part`): one splice per junction (`W003-X1`, `W003-X2`, … by `naming`), node 1 of each, a wire from each pin of the junction to the node. No gauge, colour, length or segment, as for every wire of a harness made from a link; the position of the splice is the segments a person draws (`core/branching.py` allows branch points and segments in such a harness; only a new leg and a join are refused).

Generate does not read links and makes no splice (B8). The splice part is the person's choice, never the tool's: the starter library has none (2.7), so a team adds its own. `splices._drawn` keeps refusing a splice placed by hand in a harness made from a connection: there the link owns the pins, and a splice comes from its junction (F8).

### 6.3 The verifier and the review

`core/verify.link_issues` compares by nets (its own copy of the nets, as for the splice outputs): each net of the harness, its ends mapped through the two cable connectors to device pins, joins the pairs of its ends across the two sides; the link's pairs, as a multiset, must be those pairs, with a parallel pair counted once per wire between the two pins. The texts stay (`link_wire_mismatch`), with one more: *Harness W003 joins pin 1 of PCDU1-J01 and pin 2 of OBC1-J01 through W003-X1, which link L1 does not pair.* A harness without a splice and a link without a junction give the result of 4.4.0, word for word (`tests/test_links_same_as_181.py` stays green; a new test compares the old and the new `link_issues` on random links without junctions).

### 6.4 The editor and the outputs

The *Splices* list (`gui/splice_panel.py`) shows, for each node, the pin currents of its net and whether they add up. The splice outputs of 2.3.0 (the column *Via* of the wire list, the splice block of the build workbook, a test per pair of ends of a net) apply to a harness made from a link with a splice as they apply to a drawn one; they already exist only for a harness with a splice (`nets.has_splices`).

## 7. Part D: where a shield end lands

### 7.1 The place of an end

`at_a` and `at_b` say where end A and end B land (3.1):

- **a pigtail to a pin**: `{"connector": "W001-P1", "pin": "9"}`: the drain or braid is led out and crimped or soldered into contact 9 of W001-P1, which mates with pin 9 of the device connector (often of role `shield`);
- **a pigtail to a backshell**: `{"connector": "W001-P1", "backshell": "W001-A1"}`: to the lug or the clamp of the backshell (F9);
- **a 360° bond in a backshell**: end `backshell_360` with `{"connector": "W001-P1", "backshell": "W001-A1"}`.

Several groups may land on one pin (the drains of several pairs into one shield contact).

### 7.2 Who sets it

A person: the window *Change group* (section 7.5), the scripting function `set_shield_end(folder, harness, group, end, pin=None, backshell=None)`, and `import-build-data` with a new kind told by its headings, *shield ends*: `Harness`, `Shield group`, `End` (`A` or `B`), `Pin` and/or `Backshell`. The plan `wires.plan_set_shield_place` works on a group Generate made and on one a person made, since the grounding concept decides the kind of end, not where it lands; it refuses a released harness and a twisted pair. `plan_set_group_ends` and `plan_regroup` clear the place of an end that becomes `floating`, and the pin of an end that becomes `backshell_360`. `build_data.plan_delete_accessory` clears every place that names the accessory and says so.

**Generate never fills a place** (F10), even where the device connector has exactly one pin of role `shield`. It keeps the place of a regenerated group whose wires and ends are the same as before (`engine._shields`, matched by its wire IDs), and notes a place it drops (*shielding: the pigtail of W001-S2 at W001-P1 pin 9 was not kept: the wires of the group changed*).

### 7.3 Checks

Codes of `check` (warnings reach the DRC as `model-inconsistent`; F7):

- `shield_end_moved` (warning): *W001-S2: end A is now at W001-P2 (its lowest wire changed), but its place names W001-P1. State the place again.*
- `shield_pin_missing` (warning): the pin is not a pin of that connector.
- `shield_pin_wired` (warning): a wire ends on the pin a pigtail lands on.
- `shield_pin_role` (warning): the device pin it mates with has the role `power`, `return`, `signal` or `signal_ground` set (a role read from the name is not judged).
- `shield_backshell_missing` (warning): the accessory is not of kind `backshell`, or not on that connector.
- `shield_place_not_stated` (info): an end `pigtail` with no place: *W001-S2: where the pigtail at W001-P1 lands is not stated.* Not a finding, so a format 4 project's outputs do not change (F11); the editor's Problems list shows it as an Info row, as `row_layout_pins_outside` (4.0.0).

The rules `shield-unterminated`, `shield-wrong-end`, `shield-bonding` and `shield-parts` do not change.

### 7.4 The outputs

| Output | Change (only for a group with a place) | Verifier |
|---|---|---|
| Production sheet (build workbook and plan), the shield cell | *W001-S2 shielded pair: here pigtail to pin 9, far floating*; *here backshell 360 (W001-A1)*; *here pigtail to backshell W001-A1* | `verify_production.production_rows` |
| Production sheet, the row of the pin a pigtail lands on | a row of its own (not in a run of spares, not *(no wire)*): the *Wire* cell *pigtail*, the shield cell *W001-S2 shielded pair: pigtail lands here* | the same |
| build workbook, *Connectors* sheet | *Goes to* of that pin: *pigtail of W001-S2* | `outputs/verify.py` |
| the drawing | the end's mark names the pin or the backshell | — |
| `system/export.json` | `at_a`, `at_b` where set | `outputs/verify.py` |

### 7.5 The editor

The window *Change group* gets, under each end, *Lands on pin* (the pins of the connector at that end, by `shield_ends.end_at`) and *Backshell* (the backshell accessories on that connector, and *Add a backshell…*), shown for a group Generate made as well, with its kind of end read-only there. The Inspector of a shield group shows the places; the Problems list shows the codes of 7.3.

## 8. Part E: the checked state of a library device

### 8.1 What is stored

`Unit.checked` (3.1): who checked the device, on which day, against which ICD, and the SHA-256 of what was checked. **What was checked** is the device's library-owned fields after part F: the unit's `kind` and `mass_relevant`; for each box connector, by its tail (`device_library.connector_tail`, `J01`, so a copy `OBC1-R` reads as `OBC1`), `name`, `part_id`, `gender`, `keying`, `carries`, `row_layout`, `source_doc`, `source_version`, `source_link`; for each pin `signal`, `fixed`, `function`, `contact_size`, `termination`, `contact_part`, `role`, `direction`, `level` and `current_a`; in canonical JSON (`core/io/canonical`), connectors and pins in natural order. Notes and labels are left out: a note does not change what a device is. One function, `core/device_check.py` `checked_sha256(project, unit_id)`.

### 8.2 How it is set

- **`device-checked DIR DEVICE --by NAME [--icd TEXT] [--date YYYY-MM-DD] [--json]`** and **`device-checked DIR DEVICE --clear`**. `--by` is required: no name is taken from Git or the computer, as for `release`. `--date` defaults to today. `--icd` may be left out only while every box connector of the device names one ICD and version (`source_doc` and `source_version`), which the command then uses and prints (*against ICD-TTC Issue 3, the ICD its connectors name*); otherwise it is refused with *name the ICD with --icd*. One undo step, journaled. A read-only project refuses.
- **The editor:** *Mark as checked…* in the Devices tab and the Library window (`gui/library_window.py`): who, the date, the ICD (proposed from the connectors, as above), *OK*; *Clear the check*.
- **Scripting:** `set_device_checked(folder, device, *, by, icd=None, on=None)`, `clear_device_checked(folder, device)`.
- **Never** by an import, Generate or any other command. A library update brings the library's check (8.4).

### 8.3 When the check is stale

`check` gets `device_check_stale` (warning): *TTC1 was checked by Reviewer 1 on 2026-11-23 against ICD-TTC Issue 3; its connectors or pins changed since. Check it again (device-checked), or see what changed (the journal, update-device).* It reaches the DRC as `model-inconsistent` and does not block a release. The check is not cleared by the change: the record of who checked what stays, marked stale.

A release does not lock it (`vcs/locks.COSMETIC_UNIT_FIELDS` gets `checked`), Generate does not read it (`generation_status.input_hash` leaves it out of the units), and it is in the model hash (it is a recorded fact of the design), so marking a device checked makes the written files out of date, as any edit does.

### 8.4 The library

`save-device` writes the check with the device (file version 4); `add-device` and `import-devices` bring it. `update-device` compares it as a field of the unit (`checked`, shown as *Reviewer 1, 2026-11-23, ICD-TTC Issue 3*) and `--apply` takes the library's, also the library's *not checked*. So the library holds the statement; a project that checks a device saves it to the library to share it. A check made against one library version of a device and carried to a project whose copy differs is stale there at once (8.3).

### 8.5 Where it shows

| Place | What |
|---|---|
| Devices tab (card of a device), Library window (a column *Checked*) | *Checked by Reviewer 1 on 2026-11-23 against ICD-TTC Issue 3*, *changed since the check*, or *not checked* |
| Review page and *Review* sheet (`core/review._sources_block`) | one row per device of the harness, *Device*, its ID, the check or *not checked*, only while some device of the project has a check (sparse) |
| `system/export.json` | `checked` of each unit where set |
| `export-data` devices table | three columns *Checked by*, *Checked on*, *Checked against* (not a file of `export`; listed in the release notes) |

The harness plan and the build workbook do not show it.

## 9. Part F: the library update compares the ICD fields

`library_link.CONNECTOR_FIELDS` gets `source_doc`, `source_version` and `source_link`, and `PIN_FIELDS` gets `level` (and, in 5.0.0, `current_a`); `UNIT_FIELDS` gets `checked` in 5.0.0. Then `link_state` reads *library changed* when only they differ, the diff lists them, and `--apply` takes them; the run of 2.6 gives `RW1-J01  source_version  -  Issue 2` and `RW1-J01  1  level  -  3V3`. Nothing else changes: the rows of a device whose library-owned fields are equal are the rows of 4.4.0. It needs no format change (the fields are of format 3), so it is recommended as a patch **4.4.1** made before pull request 1 of E5 (F14); 5.0.0 adds the fields of format 5 to the lists. A test reads a library file whose only change is each of the four fields.

## 10. Settings, checks, assumptions

### 10.1 One setting (`core/settings.py`)

`Setting("model", "length_reference", "Segments are measured to", "", "choice", "rear", "Where a routing segment ends at a cable connector: its rear, where the wires leave the body or backshell, or its mating face. At a face end the depth of the connector and its backshell (library: depth_mm) is taken off each wire. A cable connector may say otherwise (Lengths measured to).", "wire lengths, Generate, the length note", _PROJECT, "rear or face", choices=("rear", "face"), assumption="A-LENGTH-TO")`. The default is the meaning of formats 1 to 4. `configcheck` validates the choice. `settings DIR` and `export-data` list one setting more.

### 10.2 Codes of `check` (`core/integrity.py`)

| Code | Severity | Part |
|---|---|---|
| `length_depth_missing` | warning: *W001-P1 is measured to its face, but part EX-MICROD-9-M has no depth (library: depth_mm), so the wires there have no length* | A |
| `length_below_depth` | warning: the segments of a wire are shorter than the depths taken off; its length is not known | A |
| `current_unbalanced` | warning (5.3) | B |
| `current_not_worked_out` | info (5.3) | B |
| `shield_end_moved`, `shield_pin_missing`, `shield_pin_wired`, `shield_pin_role`, `shield_backshell_missing` | warning (7.3) | D |
| `shield_place_not_stated` | info (7.3) | D |
| `device_check_stale` | warning (8.3) | E |

Each fires only on data of format 5 (a face end, a pin current, a place, a check), but `shield_place_not_stated`, which fires on a pigtail end of any project and is an info, so it reaches no written file. The link review gets `link_junction` (info, 6.1).

### 10.3 Assumptions (`core/assumptions.py`)

- **`A-LENGTH-TO`** (kind *setting*): *A segment that ends at a cable connector runs to its rear, where the wires leave the body or backshell, unless the project (model.length_reference) or the connector says the face; at a face end the depth of the connector part and of each backshell on it is taken off each wire. A depth is never assumed: without one the wire has no length.* Where: `generate/lengths.py (end_depths, wire_length)`. `A-PATH-UNIQUE` and `A-SERVICE-LOOP` keep their texts.
- **`A-ONE-SOURCE`** (built in): *The pin currents of a net describe one source and its loads: the largest is the sum of the others. A net whose currents do not add up is not worked out, and check says so.* Where: `core/currents.py`.
- **`A-PARALLEL-SHARE`** (built in): *Wires between the same two pins, of one gauge and one length, share the current equally; contact resistance is not counted. Parallel wires that differ are not worked out.* Where: `core/currents.py`.

## 11. What changes in the written files, and the guards

| Written file | Change | Which projects | Guard |
|---|---|---|---|
| every file of `export`, the harness plans | the stamp `5.0.0` only | every project without data of format 5: every example, template and fixture, read as format 4 or upgraded | `python -m tools.output_hashes --check docs/ui/OUTPUT_HASHES_BASELINE.json` *identical*; `python -m tools.numbers_snapshot --check` *identical*; the goldens of `tests/fixtures/outputs/`, `tests/fixtures/drc/` and the plan goldens unchanged; `tests/test_format5.py` |
| the length note, `segments.csv`, *Routing*, wire lengths, drawings | 4.4 | a harness with a face end | goldens of a new fixture `format5` (`tests/fixtures/outputs/format5.json` and `format5/`, `tools.gen_output_goldens`) |
| `box_pinouts.csv`, `export-pinout`, `CON_…` sheets, findings | 5.3, 5.4 | a project with a pin current | the same goldens |
| the splice outputs | 6.4 | a harness made from a link with a junction | the same goldens |
| Production sheet, *Connectors* sheet, plan, drawing | 7.4 | a group with a place | the same goldens |
| *Review* sheet | 8.5 | a project with a checked device | the same goldens |
| `system/drc_findings.csv`, the DRC report, *DRC findings* | `model-inconsistent` findings of 10.2; the per-pin findings of `current-over-contact`; the changed note of `_wires_without_interface` | a project with such data | the same goldens |
| `system/export.json` | the new keys where set | such a project | the same goldens |
| `settings DIR`, `export-data` | one setting more; the columns of 8.5 | every project | not a file of `export`; listed in the release notes |

**Byte-identical by design, and which guard shows it.** Every new code path is behind one of five tests, each false for a format 4 project: a face end (none: `length_to` absent and the setting `rear`), a pin current, a junction or parallel pair in a link, a place of a shield end, a checked device. (1) Lengths: with no face end `end_depths` is empty and `wire_length` is the function of 4.4.0; `tests/test_lengths_compat_440.py` compares them on random harnesses (Hypothesis). (2) Currents: with no pin current `wire_currents` gives the interface current of every wire; a test compares the findings of the four current rules with a word-for-word copy of the 4.4.0 functions (`tests/reference/currents_440.py`, not to be edited) on random projects. (3) Links: without a junction or a parallel pair, `link_issues` and `plan_create_harness` are those of 4.4.0 (6.3). (4) Shields: with no place, `_shield_text` and the *Connectors* rows are those of 4.4.0. (5) The check: the Review rows appear only while some device is checked. **No new design rule** (F7), so `Rules run: 43.` stays and no golden moves for the count. The format number is in no written file (`schema_one` reads it as 1 for the model hash; `export.json` has its own `format_version` 2, which does not change for added keys). So no pull request renews the baseline, the snapshot or a golden; each runs `output_hashes --check` and `numbers_snapshot --check`, both *identical*.

**The proof of 3.0.0** (`tests/format3_support.py`) needs no step: no written file of a recorded project changes.

**How 4.0.0 did it**, for comparison: the same (design of 4.0.0, section 5.2): the step wrote the number, each output was sparse, and the baseline stayed *identical* through every pull request but R, which dropped the older names on purpose (owner answer L4). 5.0.0 has no such pull request.

## 12. Edge cases found in the code

| Case | Where in the code | What the design does |
|---|---|---|
| **The ends of a shield group swap** when its lowest wire changes | `shield_ends.reference_wire` | The place names its connector; `shield_end_moved` (7.3) |
| **A twisted pair has ends** (`flatsat`: 33 groups with end A `backshell_360`) | `generate/shields.ends_of` gives every kind the concept's ends | A place on a twisted pair is refused (rule 4); its ends stay as they are |
| **28 backshell ends of `flatsat` and no backshell** in any example | the starter library has no backshell part | Nothing is said about a `backshell_360` end without a place (F11); `shield-bonding` judges the end as today |
| **A pin in two pairs is an error** | `links._check_link`, `link_pin_reused` | A junction or a parallel pair is allowed in format 5 (6.1) |
| **The verifier counts wires pin by pin** | `verify.link_issues` | By nets (6.3) |
| **The update ignores the ICD fields and the level** | `library_link.PIN_FIELDS`, `CONNECTOR_FIELDS`, `plan_update_device` (`if not rows`) | Part F (run in 2.6) |
| **The interface's current on each contact** | `rules._current_over_contact` | Per pin where the pin has a current (5.3) |
| **Wires without an interface carry no current** | `rules._wires_without_interface` | Their pins' currents (5.2) |
| **`import-pinout` drops a *Current* column with a warning** | `pinout_import._UNSTORED` | Read (5.5); a file read again changes pins |
| **A depth could sit in `Part.ratings`** | `Part.ratings` is a free table; `import-parts` reads only known rating names | A field (F3); a rating named `depth_mm` that a project has is not read and stays where it is |
| **Generate rebuilds cable connectors** | `engine._build_harness` | `length_to` kept as the label is (4.2) |
| **Generate rebuilds shield groups** | `engine._shields` | The place kept by the group's wires (7.2) |
| **A copy of a device** (`OBC1-R`, `copies.copy_ids`, `add-device --as`) | connector IDs differ | The hash reads connectors by tail (8.1), so a copy of a checked device is checked |
| **A device renamed** (`edit.ops_rename_unit`) | connector IDs change | The same: by tail; the check stays current |
| **A cable connector of another role** (`loose`, `inline`, `test`) | `Role` | No `length_to` (rule 2): a loose end has the part `TBD-CONNECTOR`, which has no depth |
| **A face end at a branch point or splice** | segments end at any node | Only a cable connector has a face |
| **The depths longer than the path** | — | `length_below_depth`; no length (10.2) |
| **A locked length** | `lengths.length_is_kept` | Not touched: a person's length is a cut length |
| **Two harnesses on one device pin** with a current | a device pin may mate with two cable connectors | Each harness reads the same pin current |
| **A net with a loose end or a test connector** | no device pin | Not every end has a current: the interface's current, as today |
| **A pin current and the interface current differ** | — | The pins win for the wire; `explain` names both |
| **A link with a junction made before the splice part exists** | `splices.splice_part` | `plan_create_harness` refuses with the sentence of 6.2 |
| **A link edited after its harness was made** | `_refuse_if_built` | As today: the verifier reports the difference |
| **An accessory deleted that a place names** | `build_data.plan_delete_accessory` | The place's backshell is cleared, with a note (7.2) |
| **A read-only project** (newer format) | `project.read_only` | Every plan refuses, as today |
| **A format 4 project read in memory by 5.0.0** | the loader's `migrated` | Its export equals 4.4.0's but the stamp (3.4); saving needs `migrate` |

## 13. Tests

| File | What it holds |
|---|---|
| `tests/test_library_icd_fields.py` (pull request 0) | Part F: a library change of each of `source_doc`, `source_version`, `source_link`, `level` alone: *library changed*, the diff row, `--apply` takes it; equal fields: the rows of 4.4.0 |
| `tests/test_format5.py` (pull request 1) | The step on every fixture and example: `project.json` in the number only, every other file byte-identical, no key of 3.1, the safety net passes; format 2, 3 and 4 projects through every step; `--dry-run` writes nothing; the step twice gives the same files; a format 5 project read by a reader of format 4 is read-only (`install_fake_format`); the export of each example as format 4 in memory and after the upgrade byte-identical, with and without plans; `output_hashes --check` and `numbers_snapshot --check` *identical* |
| `tests/test_length_reference.py` (pull request 2) | The rules of the files for `length_to` and `depth_mm`; `end_depths` (connector, backshell, a missing depth, a backshell without a part); the example of 4.1; Generate keeps `length_to`; the note of a missing depth; `length_below_depth`; the five sentences; `segments.csv` marks; `import-parts` *Depth*; `import-build-data` *cable ends*; `explain` |
| `tests/test_lengths_compat_440.py` and `tests/reference/lengths_440.py` (pull request 2) | With no face end, `wire_length` equals the 4.4.0 copy on random harnesses; the verifier's copy equals the core's |
| `tests/test_pin_currents.py` (pull request 3) | The rule of the file; `wire_currents`: two ends, a splice star, parallel wires (equal, unequal), a loop, unbalanced, a loose end, the fallback; the four rules with pin currents; `current_unbalanced`; the note; `import-pinout` *Current* (A, mA, a bad cell); `export-pinout` read back; the columns of 5.4 |
| `tests/test_currents_compat_440.py` and `tests/reference/currents_440.py` (pull request 3) | With no pin current, the findings of the current rules equal the 4.4.0 copy (Hypothesis) |
| `tests/test_link_junctions.py` (pull request 4) | Junctions and parallel pairs in the review; `plan_create_harness` with and without a splice part; `link_issues` by nets; the old and new `link_issues` equal without junctions; the currents of the example of 5.2 through the made harness |
| `tests/test_shield_places.py` (pull request 5) | The rules of the files; `plan_set_shield_place` on a generated and a person's group; Generate keeps and drops; the codes of 7.3; the Production cell and row; the *Connectors* sheet; `import-build-data` *shield ends*; the accessory deleted |
| `tests/test_device_check.py` (pull request 6) | `checked_sha256` (a copy, a rename, a note left out, each field in); `device-checked` (`--by` required, `--icd` proposed or refused, `--clear`, `--json`); stale; the library file version 4; `update-device` with `checked`; the Review rows |
| `tests/test_ui_format5.py` (pull request 7) | The cable end choice, the part's depth, the pin table column, *Change group* places, *Mark as checked…*, the Link window junction, the Splices list currents (offscreen) |
| `tests/test_e2e_500.py` (pull request 8) | One walk through the command line, section 18 |

Each output that has a second derivation gets mutation tests (a wrong current in a column, a face mark missing, a pigtail cell wrong) and `verify --outputs` with 0 errors on the `format5` fixture. The requirements, in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`): **REQ-MIGRATE-10** (format 5 and the step that writes the number only), **REQ-WIRE-09** (lengths with face ends and depths; a missing depth leaves the length unknown), **REQ-WIRE-10** (a wire's current from the pin currents of its net), **REQ-HARN-05** (a splice in a harness made from a link with a junction), **REQ-OUT-17** (the place of a shield end on the production outputs), **REQ-LIB-08** (the checked state of a device), **REQ-GUI-33** (the editor of the five fields), **REQ-LIB-09** (part F).

## 14. Documents to update

- `CHANGELOG.md`, `## Unreleased`: one entry per pull request, each saying that a project without data of format 5 keeps its files.
- `docs/releases/5.0.0.md`: *Format 5* and the upgrade (the whole team updates together; what 4.x does with a format 5 project); the five parts; *Which written files change* (section 11); *For scripts* (`export.json` keys, the columns, `device-checked`, the scripting functions, `wire.current_a`); *Known limits* (section 20); *Not in 5.0.0* (1.2).
- `docs/FILE_FORMAT.md` (format 5, the keys and the rules of 3.2), `docs/IMPORTS.md` (*Current*, *Depth (mm)*, the two kinds of build data), `docs/CONFIG.md` (the setting), `docs/CLI.md` (`python -m tools.gen_cli_docs`), `docs/OUTPUTS.md` (sections *A face end*, *A pin current*, *The place of a shield end*, *A checked device*), `docs/models/wire-length.md` (the face end and the depth), `docs/models/wire-sizing.md` and `contact-current.md` (the current from pins), a new `docs/models/wire-current.md` (5.2, with the example), `docs/models/shields.md` (places), `docs/REQUIREMENTS.md`, `docs/GLOSSARY.md` (*Face end*, *Depth*, *Pin current*, *Junction*, *Place of a shield end*, *Checked device*).
- `docs/developer/agent/core.md` (`currents.py`, `device_check.py`, `end_depths`, the verifier copies and their tests), `docs/developer/agent/gui.md`.
- User manual: `upgrade-a-project.md` (a section 9, format 4 to 5), `splices.md` (from a link), `define-a-device.md` (currents, the check), `use-the-library.md` (the check, the update of ICD fields), a new page *Lengths to the face*; the in-app guide (`python -m tools.build_guide`).
- `docs/ait/ELEC_FEEDBACK_PLAN.md`: E5 designed, and the corrections of section 19 (a later change; this page does not edit the plan).
- Not changed: `docs/RULES.md` (no rule; the texts of the rules do not change), the templates' files.

## 15. What does not change

The 43 rules, their IDs and the *Rules run* count; `system/export.json` `format_version` 2; every written file of a project without data of format 5 but the stamp; the model hash of every project through the step; Generate's pin allocation, gauge choice (from the interface's current), shields and segments; B8; the label formats; ports, the far-device setting and the signal map (4.4.0); the reading of a row layout (4.0.0); the scripting interface's existing functions and `API_VERSION` 1 (only functions are added; the API snapshot is made again on purpose); `device-libraries.json`; `merge-fix`; the release freeze and the baselines.

## 16. Proposed decision D-264

> | D-264 | **Release 5.0.0 is a major release with format 5 (milestone E5 of `docs/ait/ELEC_FEEDBACK_PLAN.md`): the fields that need a new format, together** (D-11, D-226, D-230, D-251, D-254, D-262; plan questions 4, 6 and 8; design `docs/ait/DESIGN_5.0_FORMAT_5.md`). (1) **Format 5**: `SCHEMA_VERSION` 5; the step `_v4_to_v5` writes the number only; every new key is sparse, so the model hash, the findings and the written files of a project without them do not change but for the stamp; 4.x opens a format 5 project read-only; the device library file version 4 and the subsystem file version 3 while they hold a key of format 5; format 5 is frozen at the tag. (2) **Lengths**: `Connector.length_to` (`face`, `rear`; unset: the setting `model.length_reference`, default `rear`, the meaning of formats 1 to 4) on a cable connector, and `Part.depth_mm` on a connector or backshell part; at a face end the depth of the connector and its backshells is taken off each wire, so every length stays rear to rear; no depth, no length, and `check` says so. (3) **Currents**: `Pin.current_a` on a device pin (from the ICD; `import-pinout` *Current*); a wire's current from the pin currents of its net when every end has one and they add up (one source; equal parallel wires share equally), else from its interface as in 4.x; the rules `current-over-wire`, `bundle-current`, `voltage-drop` and `current-over-contact` (per pin) read it; Generate does not. (4) **Splices from a connection**: a link may hold a junction and a parallel pair; the harness made from it gets a splice per junction of a splice part the person chooses; the verifier compares by nets; Generate makes no splice (B8). (5) **Shield ends**: `ShieldGroup.at_a`, `at_b` (connector, pigtail pin, backshell accessory), set by a person, kept by Generate for an unchanged group, never filled by it; on the Production sheet, the *Connectors* sheet, the plan, the drawing and `export.json`. (6) **Checked devices**: `Unit.checked` (by, on, ICD, the SHA-256 of the library-owned fields), set by `device-checked` or the editor only, carried by the library, stale when the device changed. (7) No new design rule: the new checks are codes of `check` (warnings as `model-inconsistent`). Not in 5.0.0: the ticks of a review, a shield per signal, row offsets, a config file for the release keys. **Written files:** none change for a project without data of format 5; the output-hash baseline, the numbers snapshot and the goldens stay. | The owner's answers to F1 to F16. The engineer's feedback of 2026-11-20 (points 1, 3, 7, Ca). |

The patch 4.4.1 (part F, F14) is a decision row of its own if the owner takes it; the release decision of 5.0.0 is a later row.

## 17. Owner questions

Each with our recommendation first. While a question is open, the pull requests follow the recommendation.

*Added 2026-11-24, after the publication of 5.0.0:* the owner answered "yes to all except where you need dedicated inputs (files, team inputs, etc.)" (decision D-267). F1 to F16 are decided as recommended. F16 is yes for 5.0.0; the test row for a pigtail comes as a minor release once a team states its test method and limits for a drain.

1. **F1. All four field groups in one major release 5.0.0, with a step that writes the number only?** Recommended: yes. The plan asks for one change of the format (question 2); every key is sparse, so no project changes until a person uses one, and a team updates once.
2. **F2. Where a length ends: a key on the cable connector (`length_to`), unset meaning the project's setting, which defaults to `rear`?** Recommended: yes. *Mixed per end* needs a key per end; a team that measures all ends to the face says so once; the default is the meaning of every existing length. Alternatives: a key per segment end (more places to set the same fact); a key per harness (cannot say *mixed*).
3. **F3. The depth on the part (`depth_mm` on a connector or a backshell part, the backshell's adding to the connector's), and no depth means no length?** Recommended: yes. The depth is a fact of the part number, like the row layout (D-251). Alternatives: in `Part.ratings` (no format change, but a rating is a limit a rule compares, and no import reads it); a depth on the cable connector itself (repeated for every connector of a part).
4. **F4. Every length output stays rear to rear (the cut length), with the face ends named in the length note and the routing tables?** Recommended: yes. A second column *face to face* doubles every length table; the person who lays out the harness reads the routing with its marks. Revisit if a team's drawing must state face-to-face lengths.
5. **F5. The current per pin is on device pins only and Generate does not size from it?** Recommended: yes. The ICD states a contact's current; a cable pin mates with it. Sizing from pins would change Generate and its verifier in the same release as the format; the rules judge the gauge Generate chose, and a person locks another.
6. **F6. A wire's current from the pins of its net when every end has a current and they add up (one source; equal parallel wires share equally), else from the interface, else not known?** Recommended: yes. It is the current a balanced single-source net carries, and it guesses nothing: a net that does not add up is said, not worked out. Revisit for nets with two sources (supplies in parallel).
7. **F7. No new design rule: the new checks are codes of `check`, whose warnings reach the DRC as `model-inconsistent`?** Recommended: yes. They are mismatches of stated data (two ICDs, a place and its connector), which is what that rule reports; a new rule changes *Rules run* in every report and every golden (design of 4.2.0, C9). Alternative: rules `current-balance` and `shield-place`, with one renewal of the goldens.
8. **F8. A junction and a parallel pair in a link; the harness made from it gets one splice per junction, of a splice part the person chooses; no splice placed by hand in such a harness?** Recommended: yes. The link owns the pins (D-201); the junction says *these pins are joined*, the person's part says *how*. Generate keeps B8. Alternative: the person places the splice by hand in the made harness and the verifier reads nets (the link then does not say what the harness holds).
9. **F9. The place of a shield end names its connector, a pin for a pigtail, and a backshell for a 360° bond or for a pigtail to the backshell's lug?** Recommended: yes. Both ways of landing a pigtail are common; the connector makes a swap of ends visible (12).
10. **F10. Generate never fills a place, even when the device connector has one pin of role `shield`, and keeps a person's place on an unchanged group?** Recommended: yes. A role is a person's statement about the device, not about where this harness lands its drain; filling it would change the harness files of a regenerated project. Alternative: fill from the only stored `shield` pin, with a note.
11. **F11. An end `pigtail` without a place is an info of `check`, not a finding; an end `backshell_360` without a backshell is not reported?** Recommended: yes. A finding would change the outputs of every format 4 project with such ends (28 ends in `flatsat`). The Production sheet still says *pigtail* where nothing more is known.
12. **F12. The check of a device: by, on, ICD and a hash of the library-owned fields, stale when they change, carried and taken by the library?** Recommended: yes. Without the hash a check says nothing once the device is edited; the library holds the device, so it holds the statement.
13. **F13. Anyone may mark a device checked, with a typed name; no rule of different persons (`release_distinct_roles`) applies?** Recommended: yes in 5.0.0. Revisit when teams ask for a second person.
14. **F14. Part F as a patch 4.4.1 before E5?** Recommended: yes, as E0 was 4.0.1. It is a fault of format 4 (a new ICD issue goes unnoticed); a team on 4.4.x needs it whether or not it upgrades.
15. **F15. Not in 5.0.0: the review ticks in the project (plan question 8), a shield per signal (design of 4.2.0), row offsets (design of 4.0.0), the release keys in a config file of their own (design of 4.3.0, R1)?** Recommended: yes, none. Each would wait for format 6. Say now if one is wanted: it is cheaper in this step than in the next.
16. **F16. No test row for a pigtail in `tests.csv` in 5.0.0?** Recommended: yes. A shield continuity test needs a test method and limits the team states (D-11); it is a minor release once a team says how it tests a drain.

## 18. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry.

| PR | Content | Guards |
|---|---|---|
| 0 | **Patch 4.4.1** (F14, on a branch from `v4.4.0`, and on `master`): part F; `tests/test_library_icd_fields.py`; REQ-LIB-09 | *identical* |
| 1 | **Format 5.** `SCHEMA_VERSION` 5, `_v4_to_v5` (`V4_TO_V5_PARTS`, the number only), `MIGRATIONS[4]`; the version rule of the library files (`FORMAT5_KEYS`, empty until the keys come); `docs/FILE_FORMAT.md`; `tests/test_format5.py`; REQ-MIGRATE-10; this page's status. **Merged only when no 4.4.x patch is wanted from `master` any more**, because `master` writes format 5 from its merge | *identical* |
| 2 | **Lengths** (part A). `Connector.length_to`, `Part.depth_mm` and their rules; `model.length_reference`; `lengths.end_depths`, `wire_length`; Generate; the verifier's copies; the outputs of 4.4; the codes; `A-LENGTH-TO`; `import-parts`, `import-build-data`; `explain`; the scripting function; the editor's two fields; the `format5` fixture started; REQ-WIRE-09 | *identical*; goldens of `format5` |
| 3 | **Currents** (part B). `Pin.current_a`; `core/currents.py`; the four rules, the note, the codes; the outputs of 5.4; `import-pinout`, `export-pinout`; `wire.current_a`, `export-data`; the pin table column; `A-ONE-SOURCE`, `A-PARALLEL-SHARE`; REQ-WIRE-10 | *identical*; `currents_440` |
| 4 | **Splices from a connection** (part C). The link review, `plan_create_harness`, `verify.link_issues`, the Link window, the Splices list; REQ-HARN-05 | *identical*; `test_links_same_as_181.py` green |
| 5 | **Shield end places** (part D). `ShieldEndPlace`, `at_a`, `at_b`; the plans; Generate keeps them; the codes; the outputs of 7.4 and their verifier; `import-build-data`; *Change group*; REQ-OUT-17 | *identical* |
| 6 | **Checked devices** (part E). `Unit.checked`, `core/device_check.py`, `device-checked`, the library file and `update-device`, the Review rows, the Devices tab and Library window; REQ-LIB-08 | *identical* |
| 7 | **The editor**, the rest: the strings in a block *5.0.0 E5* of `gui/strings.py`, the Problems list rows, the screenshots of the Devices tab and *Change group*; REQ-GUI-33 | *identical*: no written file |
| 8 | **End to end and documents.** `tests/test_e2e_500.py`: a format 4 project (`mini3`, the number written back, `migration_support.as_format`), `migrate --dry-run`, `migrate`, an export that is the golden set but the stamp; `settings --set model.length_reference=face`, a depth by `import-parts`, `generate`, the lengths and the note; currents by `import-pinout`; a link with a junction through the core and its harness with `EX-SPLICE-1`; `drc` with the balance; a pigtail place by `import-build-data`; `device-checked`, an edit, `check` with the stale warning; `export --harness-plan --drawings`, `verify --outputs` 0 errors, a second export byte-identical; the documents of section 14; `docs/releases/5.0.0.md` | — |
| 9 | **The preparation of 5.0.0**: the version, the changelog section, the decision rows D-264 (as decided, with what was built where it differs) and the release row, the status pages, the records made again (a stamp-only renewal: `5.0.0` has five characters); format 5 frozen at the tag | stamp only |

Order: 0 first (and tagged as 4.4.1 if the owner takes F14); 1 after 0; 2, 3, 5 and 6 after 1, in any order; 4 after 3 (its node currents); 7 after 2 to 6; 8 after 7; 9 last. **No pull request changes a written file of a project without data of format 5**, so none renews the baseline, the snapshot or a golden; each adds goldens of the `format5` fixture for what it writes.

Why the keys come with their readers and not all in pull request 1: each key is checked, read and written by its group's code, and a key that nothing reads would be a field of the format without a test of its meaning. Format 5 is not frozen until the tag, so the keys may arrive one pull request after another, as long as each is sparse; pull request 1 makes the step and its proof, which the later keys do not change.

## 19. Corrections to the plan, and what was found on the way

Checked against the code at 4.4.0 and the runs of section 2.

1. **The library update ignores the ICD fields and the pin level** (2.6, run). The plan (Ca) says *`update-device` shows what the library changes before it is taken*; for `source_doc`, `source_version`, `source_link` and `level` it does not, and it does not take them alone. A *checked against which ICD version* needs this first: part F, a patch 4.4.1.
2. **A link cannot ask for a splice.** The plan (question 6) recommends allowing a splice on a harness made from a connection; the refusal in `splices._drawn` is not the only obstacle: a link cannot pair one pin with several (`link_pin_reused`), and the verifier compares wires pin by pin. Part C changes both.
3. **The splice from a connection needs no new key.** It is in format 5 because a 4.x tool reads a link with a junction as an error, not because a field is new.
4. **`current-over-contact` gives each contact the whole interface current** (`rules._current_over_contact`). The plan names the missing current per wire; the contact check over-reports a line split over contacts for the same reason. Part B judges per pin.
5. **A depth could be stored in format 4** (`Part.ratings` is a free table of numbers), unread. The plan says *a connector part has no depth*; it has no field the tool reads. The design takes a field (F3).
6. **Generate gives a twisted pair the ends of the grounding concept** (33 groups of `flatsat` with end A `backshell_360`), though it has no shield. Harmless for the rules, which pass over twisted pairs; a place is refused on one.
7. **The 28 backshell ends of `flatsat` name no backshell, and the starter library has no backshell or splice part.** A team adds its own parts before it can use parts C and D.
8. **The ends of a shield group follow its lowest wire ID**, so they can swap; the plan's *the pin a pigtail lands on* needs the connector stored with the pin (3.1).

*Added by pull request 8, after pull requests 1 to 7 were built:* what was built differently from the text above, and what the end-to-end walk found. Each pull request records its choices where this page is silent in its commit message; the ones a reader of this page needs are here.

9. **Lengths (pull request 2).** A wire whose segments are not longer than the depths has no length (`length_below_depth`); a backshell counts once whatever its quantity; Generate keeps `length_to` without locking the connector; the setting's place in the editor came with pull request 7, under *Settings > Project* (section 4.5 names *Settings > Model*, which the page does not have).
10. **Currents (pull request 3).** A net needs two ends or more to be worked out; parallel wires share only with a known, equal gauge and length; an unbalanced net leaves its wires without a current (not the interface's); a wire with a current from its pins and no interface type is not judged for its voltage drop and is named in the note `voltage-drop-wires`, because without a type the tool does not know how many conductors carry the way back. So a harness made from a connection gets `current-over-wire`, `bundle-current` and `current-over-contact` from its pin currents, and no voltage drop.
11. **Splices (pull request 4).** A junction must pair each pin of one side with every pin of the other, once; a pair missing or given twice inside a junction is `link_pin_reused`, so every link the review accepts makes a harness `link_issues` accepts. One splice per junction, all of the person's one part.
12. **Shield places (pull request 5).** A place shows in the outputs only while it names the connector at its end. The import record of the table of cable ends of pull request 2 had no kind, so the command line refused that table; pull request 5 added the kinds `cable-ends` and `shield-ends`.
13. **Checked devices (pull request 6).** The hashed pin signal is the portable one, so an allocation by Generate does not make a check stale. `export-data` had no table of devices, so one is added: it writes **37 files** for every project (35 before: the table is a CSV and a JSON file), a project without a check included. The release notes of pull request 9 say so under *Which written files change*.
14. **The editor (pull request 7).** `core.drc.locate` is not changed for a shield group (it also picks the findings of the Review sheet and the release gate, so a written file would change); the window shows a group itself.
15. **Found by pull request 8, and fixed: the help of `import-build-data` did not name the table of shield ends** that pull request 5 added, so `docs/CLI.md` (made from the help) did not either. The help and the description now name it, with a regression test in `tests/test_shield_places.py`. No other fault of pull requests 1 to 7 was found: the walk of `tests/test_e2e_500.py` (section 18, row 8, on `mini3`, through the command line and the editor) gives the results the sections above state. Two pages said what part B made untrue: `connect-two-connectors.md` (the wires of a harness made from a connection get no current check) and `branching-harnesses.md` (nothing reads the depth of a connector); pull request 8 corrected them.
16. **The read-only view of 4.4.0 tried** (section 20, *Not tried*). Run with the code of `v4.4.0` on the project of the walk: `validate` warns `newer_version` and lists each object with a key of format 5 as set aside (*connectors.1.length_to: Extra inputs are not permitted*, `depth_mm` of the parts, `current_a` of the device connectors, `checked` of the device, the import records of the kinds `cable-ends` and `shield-ends`) with the errors that follow from them, and the connection as `link_pin_reused`; `generate`, `export` and `drc` refuse the project as damaged (exit code 2). A project with the number 5 and no key of format 5 is only read-only. `docs/user-manual/upgrade-a-project.md` section 9 states both.

## 20. Risks and what this design does not check

- **Nobody on a team has entered a depth, a pin current or a place in this tool.** The definitions (a backshell's depth adds to the connector's; a pin current is the operating current of the contact) are this design's; the engineer should read sections 4.1, 5.1 and 7.1 before pull request 2 is merged.
- **A team's existing lengths may already be to the face.** Format 4 said *rear* since 4.1.0, but a project begun before may hold face lengths. The step cannot know (it writes no `length_to`); the release notes ask each team to look at its length note after the upgrade.
- **Unbalanced currents are common in real ICDs** (rounding, a maximum on one side and a typical value on the other). Then wires are not checked and `current_unbalanced` says so; a team may find that noisy (F6).
- **One more upgrade for every team**, and the whole team at once: a 4.x tool sets aside every object with a key of format 5. Held by a step that writes the number only, its backup, and the release notes.
- **`master` writes format 5 from the merge of pull request 1.** A fault of 4.4.x found later goes into 5.0.0 or a branch from the tag (pull request 0 comes first for that reason).
- **Two copies** of the depths, the nets of a link and the shield texts (the core's and the verifier's) must agree; Hypothesis tests hold them together, as for the nets and the row layout.
- **The results of sections 5.2 and 6.3 come from the rules as written here**, not from code; pull requests 3 and 4 run the same cases as tests.
- **Not tried:** the read-only view of 4.4.0 on a format 5 project with each key (section 3.5 follows what pull requests 6 and 7 of 4.0.0 found for 3.x); a real ICD with a current column; a real connector datasheet's depth.
- **No code was written**; the module and function names are the plan, and the pull requests record where they differ.
