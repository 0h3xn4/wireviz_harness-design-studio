# Design of 4.1.0: the production sheet

Written on 2026-11-20 from a reading of the code at the prepared 4.0.1 (the version the checkout reports, `harness 4.0.1`; D-255) and from runs of the command line on a copy of the `flatsat` example. It designs milestone E1 of [`ELEC_FEEDBACK_PLAN.md`](ELEC_FEEDBACK_PLAN.md). Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the designs of 3.0.0 and 4.0.0 ([`DESIGN_3.0_HARNESS_PLAN.md`](DESIGN_3.0_HARNESS_PLAN.md), [`DESIGN_4.0_ROW_LAYOUT.md`](DESIGN_4.0_ROW_LAYOUT.md)): scope, what exists, the four parts, what changes in the written files, edge cases, tests, documents, the decision, the owner questions, the pull requests, the corrections to the plan and what was not checked. Choices that are the owner's are P1 to P10 (section 13), each with a recommendation first.

**Status (2026-11-20):** built, not released. Pull requests 1 to 7 of section 14 are written: 1 (*Core*) as #312, 2 (*Shield groups*) as #311, 3 (*The build workbook*) as #314, 4 (*The `.ods` writer*) as #313, 5 (*The plan*) as #317, 6 (*The label format*) as #315, and 7 (the end-to-end test `tests/test_e2e_410.py`, the documents of section 10 and the release notes [`docs/releases/4.1.0.md`](../releases/4.1.0.md)); the step 7 of the proof of 3.0.0 came as #316. The pull requests follow the recommendations of P1 to P10; no owner answer is recorded. Pull request 8 is the preparation of 4.1.0. The decision that records the design is D-256 (section 12); it is a proposal until that pull request writes it into `docs/DECISIONS.md`.

*Written before any code (kept as it was):* draft. No code is written. No owner answer yet.

## 0. The frame

The electrical engineer's top request is production-ready output: which pin goes to which pin, with which wire type, which length and which label where, clear at a glance on paper (points P, Cc, 5, 6, 7 and 1 of the plan). E1 answers it in a minor release:

1. **Format 4 stays frozen** (D-254). No new key in any project file. The model refuses unknown keys (`extra="forbid"`, `core/model/base.py`), so everything here is read from fields that format 4 already has.
2. **New outputs and new values of existing settings are allowed** (the plan, *What earlier plans and decisions already say*; the precedent is `segmentation.mode` `per_connector_group`, D-243, and its default for new projects, D-247).
3. **Every new text of a written file is worded a second time by the independent verifier**, from its own copy of the rules (`docs/developer/agent/outputs.md`; `core/outputs/verify.py` and `core/outputs/verify_plan.py` import no builder). E0 (#306, D-255) showed what happens otherwise: the label formats of 1.15.0 failed the export's self-check for a year of releases.
4. **The tool invents no value.** A length, a gauge, a part or a shield end that the design does not hold reads *to fill in*, as on the other sheets.

## 1. Scope

### 1.1 In scope

| Part | What is built | Points of the feedback |
|---|---|---|
| A | A sheet **Production** in the build workbook (`<ID>_build.xlsx`) and in the harness plan (`<ID>_plan.ods`): one block per connector, one row per pin and wire, with the far connector and pin, the wire, its part, colour, gauge and length, the label text at this end, and the shield groups with their end here and at the far end | P, Cc, 6, 7 |
| B | A named label format `harness_device_connector` (`W001:MTQ1:J01`) and a template field `{mates_name}` for the name of the device connector (`Connector.name`, `J01`); the format is the default of a new project only | 5 |
| C | The plan's harness sheet printed over several pages at a known scale, with its heading rows repeated and a block kept on one page where it fits, in place of one page scaled to fit | P |
| D | Every length column of the build workbook and of the plan says what the length is measured from, and the Production sheet says for each wire where its length comes from | 1 (stated) |

### 1.2 Not in scope

- **Everything of E2 to E5.** No new rule (twisted pairs, shields, levels, the direction of a hand-drawn wire: E2); no review view (E3); no port by far device name and no ICD importer (E4).
- **Everything that needs a field, so format 5 (E5):** a length reference per cable connector end (face or rear) and a connector depth; the pin a pigtail lands on and the backshell a shield end uses; a current per pin; a checked state of a library device. Section 8 (*Shield drain or pigtail*) says what the Production sheet shows instead while these fields do not exist.
- **The CSV and JSON files keep their headings and keys** (`wirelist.csv`, `segments.csv`, `mass_length.csv`, the `<ID>.xlsx` tables workbook, `system/export.json`): scripts read them (P6).
- **The drawings** (`export --drawings`) keep their texts in 4.1.0 (P6).
- **No face order** on the Production sheet: it lists pins in pin order, as the *Connectors* sheet does. The *Pin row* column of 4.0.0 stays where it is (pinout tables and the plan).
- **No CSV of the production rows.** The rows are a document for people; a script reads `wirelist.csv` and `labels.csv`.
- **No new command, no new option, no screen change** apart from one choice word in *Settings > Project* (section 6.5). The Export window writes the new sheet with the files it writes today.

## 2. What exists at 4.0.1

Checked in the code and by running `generate` and `export --harness-plan` on a copy of `flatsat` (103 files written).

**The build workbook** (`core/outputs/buildsheet.py`, D-169). Sheets `SHEETS = ("Start here", "Cut list", "Connectors", "Parts", "Accessories", "Labels", "Tests", "About")`, with *Routing* after *Cut list* for a harness with a branch point (`sheet_names`) and *As-built* before *About* for a harness with as-built records. Every sheet is A4 landscape, `fitToWidth = 1`, `fitToHeight = 0` (as many pages as needed, `_finish`), the header row repeated on every page (`print_title_rows = "1:1"`), the stamp in the footer and *Page &P of &N*. *Start here* alone is fitted to one page (`one_page=True`). The *Connectors* sheet (`_connector_sheet`, `_pin_rows`) has one block per **cable connector** in ID order (a heading row `W001-P1   ·   EX-MICROD-9-M   ·   male   ·   mates with MTQ1-J01`, then one row per pin, an empty row), the splices last under `SPLICE_BLOCK`, and a manual page break before a block that would pass 42 rows on the page. Its columns are `CONNECTOR_HEADER`: Pin, Signal, Function, Wire, Colour, AWG, Goes to, Termination, Contact size, Contact, Tool and three tick columns. It has no wire part, no length, no label and no shield. The *Cut list* (`_cut_sheet`, `CUT_HEADER`) has part, length and shield group, in cut order (`_wire_sort_key`).

On `flatsat`:

| Harness | Connectors | Pins | Wires | *Connectors* sheet rows | Sheets |
|---|---|---|---|---|---|
| W001 | 18 | 162 | 18 | 198 | 9 (with *Routing*) |
| W002 | 22 | 484 | 26 | 528 | 9 |
| W003 | 2 | 18 | 2 | 22 | 8 |
| W004 | 20 | 330 | 22 | 370 | 9 |
| W005 | 6 | 36 | 7 | 48 | 9 |
| W006 | 14 | 190 | 16 | 218 | 9 |
| W007 | 4 | 62 | 8 | 70 | 9 |
| W008 | 2 | 52 | 4 | 56 | 8 |

In W001 the first block holds 2 wired pins and 7 spare ones: a reader finds 18 wires among 162 pin rows.

**The harness plan** (`core/outputs/harness_plan.py`, D-242). Sheets *Cover*, *Change_Register*, the harness sheet (`harness_sheet_name`), *Notes*, one `CON_<box connector>` per box connector the harness plugs into, *About* (`plan_workbook`). The harness sheet (`_HarnessSheet.build`) has blocks for the **near** connectors only (`plan_sides`); each far connector is one *Pinout* column from T and a device-side group further right. Its page is `Page("A4", landscape=True, fit=True)`, which `ods.py` writes as `style:scale-to-pages="1"`, and its print range is `H6:` to the last far pin column. W001 of `flatsat`: 178 rows, print range `H6:AB178`, 9 near blocks of 9 pins; the other 9 connectors are the columns T to AB. The columns H to AB are 448 mm wide by the widths of `build` (16, 36, 16, 22, 16, 22, 16, 16, 16, 22, 16, 36 and nine times 22). On an A4 landscape page with the writer's margins (277 mm by 190 mm, less the footer) the one-page fit is about 22 % (173 rows of the default 4.5 mm), so text of the reader's default 10 pt prints at about 2 pt. These are estimates from the widths and the default row height; nobody printed the file.

**Labels** (`core/label_format.py`, `outputs/tables.py`). `FORMATS = ("standard", "compact", "descriptive", "custom")`; the connector template fields are `CONNECTOR_FIELDS = ("harness", "connector", "name", "mates", "device")`, where `{mates}` is the box connector's **ID** (`MTQ1-J01`) and `{device}` its `unit_id`. `connector_label_text` makes `W001-P1 mates MTQ1-J01` in `standard`; `{harness}:{device}:{mates}` gives `W001:MTQ1:MTQ1-J01`. There is no field for `Connector.name` of the box connector (`J01`). A box connector always has a name (`Name`, at least one character, unique per device without regard to case: `devices._check_connector_name`; new ones are `J01`, `J02` … from `devices.next_connector_name`; every box connector of the five examples is named `Jnn`). The plan's near block header is `ctype [W001:MTQ1:MTQ1-J01]`, a formula over `N6` and `B1`/`B2` of the `CON_…` sheet (`Connector ID`, the box connector's ID). The verifier words every format again (`verify.py` `_LABEL_*`, `_connector_label_text`, `_wire_label_texts`, `_label_rows`, since #306). The labels reach `labels.csv`, the *Labels* sheet of `<ID>.xlsx` and of the build workbook, and `explain` (`derive_build.connector_label_derivation`).

**Shield ends.** `ShieldGroup` (`core/model/physical.py`) has `kind`, `wire_ids`, `end_a`, `end_b` (`backshell_360`, `pigtail`, `floating`). Generate gives every group the concept `generation.shield_end_a`/`shield_end_b` (`generate/shields.ends_of`; a coax is `backshell_360` at both ends); `flatsat` uses `backshell_360`/`floating`. **Which connector is end A is said in one place only:** `drawing._reference_wire` and the comment above it, *end A is the start of the shield's reference wire (its lowest wire ID in the whole harness)*. No rule, no table and no page of `docs/models/shields.md` says it. A group whose wires end on more than two connectors gets the warning `shield_across_branch` (`integrity.ends_apart`).

**Lengths** (`generate/lengths.py`, `docs/models/wire-length.md`). `wire_length(h, w)` is `Wire.length_m` when set, else the sum of the segments on the one path between the wire's connectors (`path_length`), **without service loops**. Generate stores `generated_length`: the path plus `service_loops_per_wire` × `service_loop_m` (2 × 0.1 m on `flatsat`), with the take-up of twisting and a cut allowance under the model `path_loops_allowance_twist`. A segment runs from the rear of a connector (where the wires leave the body or the backshell) to the centre of a branch point. `derive.wire_length_derivation` tells five cases apart: generated, overridden, entered and locked, stored but not equal to its path plus loops, and segments only. No written file says which reference a length uses.

**The guards of the written files.** `tools/output_hashes.py` hashes every file of `build_outputs(project)` for `first-steps`, `minimal-satellite`, `small-satellite` and `flatsat` (`docs/ui/OUTPUT_HASHES_BASELINE.json`: 41, 149, 305 and 127 files; 45 build workbooks, hashed by their members). Its default has the drawings **on** and the plans **off**, so the plans are not in the baseline. `tools/numbers_snapshot.py` stores the hash of every file of eleven scenarios. The goldens are `tests/fixtures/outputs/*.json` (`mini3`, `sat15`, `sat15_full`, `loose_ends`, `splices`, `row_layout`: every file's hash) and `tests/fixtures/outputs/harness_plan/` (the hash of every plan of seven projects, and the cells of four as text, `tests/plan_support.dump`). `BASE_VERSION` is `2.4.0`; `4.1.0` has as many characters, so the stamp is replaced and nothing moves for the version alone.

## 3. Part A: the production sheet

### 3.1 What is built

One function makes the rows, and both files write them: **`core/outputs/production.py`**, `production_blocks(project, h) -> list[ProductionBlock]`, pure, no file and no style. `buildsheet._production_sheet` writes them into the build workbook; `harness_plan._production_sheet` writes them into the plan. Both files hold the same rows; only the unit of the length (m in the workbook, mm in the plan, as each file has today), the tick column and the styles differ.

- **Build workbook:** sheet `Production`, after *Cut list* (and *Routing*), before *Connectors*. `SHEETS` and `sheet_names` change; *Start here* gets the line `("Production", "one block per connector: where each wire goes, its part, colour, gauge, length, label and shield")` in *How to use this workbook*, before *Connectors*. Print set-up as every sheet (`_finish`: A4 landscape, one page wide, header row 1 on every page), and a manual page break before a block that would pass 42 rows, as `_connector_sheet` does. A tick column **Done (x)** with `_tick_rules`.
- **Harness plan:** sheet `Production`, after the harness sheet, before *Notes*. Plain values only, no formula (section 7.1 of the 3.0.0 design: what the model holds is a value). `Production` joins `_FIXED_NAMES`, so a harness with the ID `Production` gets the sheet `Harness_Production` (`harness_sheet_name`). The page and the breaks are those of section 5 (part C): rows 1 to 3 repeated, a block kept on one page where it fits.

**Why a new sheet and not more columns on *Connectors*.** *Connectors* is the termination sheet (contact, tool, three ticks) and already has 14 columns. The production columns would make 24, which at one page wide prints too small to read on A4. The two sheets answer two questions: *where does each wire go* (Production) and *how is each contact made* (Connectors).

**Why every connector, both ends.** The plan's harness sheet has blocks for the near end only. A builder terminates every connector, so the Production sheet has a block for each cable connector of the harness, and each wire is in two rows: one at each end, each with the label printed at that end. In the plan this is the first place where a far connector is listed pin by pin.

### 3.2 The blocks and their order

Cable connectors in natural ID order (`tables.natural_key`: `W001-P2` before `W001-P10`), then the splices under the heading `SPLICE_BLOCK`, in the same order. The *Connectors* sheet keeps its plain ID order.

The heading row of a block, joined by `   ·   ` as on *Connectors*:

| Connector | Heading |
|---|---|
| plugs into a box connector | `W001-P1 · EX-MICROD-9-M · male · mates MTQ1-J01 (MTQ1:J01) · label W001:MTQ1:J01` — ID, `part_id`, gender, the box connector's ID and, in brackets, its `unit_id` and `name`, then the connector label in the format in force (`tables.connector_label_text`) |
| loose end (role `loose`) | `W009-P2 · TBD-CONNECTOR (loose end) · open end, to fill in · label W009-P2 open end` (the words of D-201) |
| no box connector (`mates_with` empty, or naming no connector of the project) | `W001-P3 · EX-… · male · not plugged into a unit · label …` |
| splice (role `splice`) | `W003-X1 · EX-SPLICE-1 · splice · 1 node` (no label: a splice is inside the sleeve) |

When an accessory of kind `label` targets the connector (`Accessory.target`), its `position` follows: `· label at 50 mm from the P1 end`. Several are joined by `; `.

### 3.3 The columns

| # | Heading (workbook) | Heading (plan) | Source |
|---|---|---|---|
| 1 | Pin | Pin | `Pin.id` of the cable connector, in `Connector.pins` order; a run of spare pins is one row (3.4) |
| 2 | Signal | Signal | `Pin.signal`, else `Wire.signal` (a cable pin of a generated harness has no signal of its own; the *Connectors* sheet shows it empty today) |
| 3 | Wire | Wire | `Wire.id`; `(no wire)` for a pin with a signal or an interface and no wire; `(spare)` for a run of spare pins |
| 4 | Goes to | Goes to | the wire's other end `CONNECTOR.PIN` (`buildsheet._far`), then in brackets what that connector plugs into: `W001-P10.1 (PDU2:J10)`, `W009-P2.1 (open end)`, `W003-X1.2 (splice)`; nothing in brackets for a connector that plugs into nothing |
| 5 | Wire part | Wire part | `Wire.part_id`, else *to fill in* (amber) |
| 6 | Colour | Colour | `Wire.colour` as the cut list writes it (`_wire_colour_cell`, the cell filled with the colour), else *to fill in*; plan: see P8 |
| 7 | AWG | AWG | `Wire.gauge_awg`, else *to fill in* |
| 8 | Length (m), rear to rear | Length [mm] rear to rear | `generate.lengths.wire_length`; m as in the cut list, mm rounded to 0.1 as in the plan's column N (`wire_cells`); else *to fill in* |
| 9 | Length from | Length from | where the length comes from (section 6.3): `on the wire`, `locked`, `segments only, no service loops`; empty when the length is *to fill in* |
| 10 | Label at this end | Label at this end | `tables.wire_label_texts(project, w, h)`: the first text (end A) when this row is the wire's `from` end, the second (end B) when it is the `to` end |
| 11 | Shield group: here / far end | Shield group: here / far end | every group that holds the wire, in natural ID order, joined by `; `, each as `W002-S3 overall shield: here backshell 360, far floating` (section 3.5) |
| 12 | Done (x) | — | a tick, as on the other sheets (workbook only) |

The words of the shield kinds are `twisted pair`, `shielded pair`, `overall shield`, `quad`, `coax` (from `ShieldKind`); the words of the ends are those of the drawing (`drawing._END_WORDS`: `backshell 360`, `pigtail`, `floating`).

A row of `flatsat`, W001, block `W001-P1`:

| Pin | Signal | Wire | Goes to | Wire part | Colour | AWG | Length (m), rear to rear | Length from | Label at this end | Shield group: here / far end |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | (the wire's signal) | W001-017 | W001-P10.1 (PDU2:J10) | EX-WIRE-SINGLE | red (RD) | 24 | (its length) | on the wire | (end A text of W001-017) | (its group) |
| 3 to 9 | | (spare) | | | | | | | | |

### 3.4 Pins without a wire, and pins with several

- **A run of spare pins is one row.** Consecutive pins of `Connector.pins` with no wire, no `signal` and no `interface_id` (the *Connectors* sheet's own test for `(spare)`) are written as one row `3 to 9` with `(spare)`, so the eye goes to the wires. A run of one is its pin alone. `to` and not a dash, because a pin name may hold `-` (`core/ids.py`). On `flatsat` this takes W001 from 162 pin rows to 54, W002 from 484 to 74, W004 from 330 to 64 (counted on the harness files; P2).
- **A pin with a signal or an interface and no wire** is a row of its own, `(no wire)`, never folded: it is what a checker must see.
- **A pin with two or more wires** has one row per wire, in wire ID order, the pin repeated in column 1. One cell with `W001-003; W001-004`, two lengths and two labels cannot be read at a glance (P3). No `flatsat` pin has two wires today; a person can draw one, and a splice node usually has several.

### 3.5 The shield ends at a connector

A new core function names the rule that the drawing already uses: **`core/shield_ends.py`**, `end_at(h, s, connector_id) -> Literal["a", "b"] | None`. End A is the `from_connector` of the group's reference wire, end B its `to_connector`; the reference wire is the group's wire with the lowest ID in the whole harness (`drawing._reference_wire`, which then calls `reference_wire` of the new module; the drawings keep their bytes). `None` when the connector is neither end of the reference wire, which only happens for a group that the warning `shield_across_branch` names; the cell then says `here not defined (the group ends on more than two connectors)`.

At a row of connector C: *here* is the end of `end_at(h, s, C)`, *far* is the other end. A twisted pair has no shield and is written without ends (`W001-S1 twisted pair`). A coax is `backshell 360` at both ends. A wire in a pair inside an overall shield is in two groups and lists both (`W002-S2 twisted pair; W002-S3 overall shield: here backshell 360, far floating`).

### 3.6 How the verifier checks it

A new module of the verifier, **`core/outputs/verify_production.py`**, words every row a second time from the project, imports neither `production.py`, `buildsheet.py`, `harness_plan.py`, `tables.py`, `core/label_format.py` nor `core/shield_ends.py`, and is used by both verifiers:

- `verify.py` `_build_production` reads the sheet with `_xlsx_values` and compares heading, block headings, every row and the totals with `production_rows(project, h)`; code `out_build`, the object the connector or the wire. It checks that **Done (x)** is empty (*ticks before anything was done*, as for the other sheets) and that *Start here* lists the sheet.
- `verify_plan.py` `expected_plan` takes the same rows for the sheet `Production` (code `out_plan`).

Its own copies: the folding of spare runs (3.4), the far end and its brackets, the end of a shield at a connector (`_end_at`, a second copy beside `shield_ends.end_at`), the length (`verify._length_of` exists already), the length origin (section 6.3) and the label texts. The label copy moves from `verify.py` into **`core/outputs/verify_labels.py`** (the constants `_LABEL_*`, `_label_template_usable`, `_fill_label`, `_connector_label_text`, `_wire_label_texts`), because `verify_production.py` needs it and `verify.py` imports `verify_plan.py`, so the label copy cannot stay in `verify.py` without a cycle. `tests/test_label_format_outputs.py` reads the imports of the new module instead.

Tests compare the copies with the core by Hypothesis on the random harnesses of `tests/test_verify_plan.py` (with splices, loose ends and shield groups), and a mutation test changes each column of one row and expects `out_build` and `out_plan`.

### 3.7 What changes in existing outputs

Every build workbook of every project changes: a new sheet, a new line on *Start here*. Every harness plan changes: a new sheet. This is the point of the release, so it is not opt-in (P1). See section 7 for the hashes.

## 4. Part B: the named label format

### 4.1 What is built

- **`core/label_format.py`:** `FORMATS` gets `"harness_device_connector"`, with `FORMAT_TEXT` *harness, device and device connector name (W001:MTQ1:J01); a wire: the standard text*. `CONNECTOR_FIELDS` gets `"mates_name"`, with `FIELD_TEXT` *the name of the device connector it plugs into, as the device calls it (J01)*. `DEFAULT_FORMAT` stays `standard`.
- **`outputs/tables.py` `connector_label_text`:** the branch of the new format, and `{mates_name}` in the values of a template.
- **`core/settings.py`:** the choice and its description (`model.label_format`; *A new project starts in harness_device_connector (since 4.1.0, D-256); a project keeps the format it names, and a file that names none is read as standard*). **`core/configcheck.py`:** `_MODEL_CHOICES["label_format"]`.
- **`core/assumptions.py`:** A-LABEL-FORMAT names the new format.
- **`core/derive_build.connector_label_derivation`:** the inputs of the new format (*Device*: `unit_id` of the box connector; *Device connector name*: `Connector.name` of it) and its equation.
- **`generate/engine._warn_equal_labels`:** runs for `custom` **and** the new format (its text holds no ID, so two plugs of one harness on one device connector read the same; section 8).
- **`samples.start_project`:** a new project gets `config/model.json` with `"label_format": "harness_device_connector"` and `placeholder: false` (a label text is not an engineering value; a placeholder file would show under *Placeholder files* of *Start here* and in `placeholder_config` of `manifest.json`).

### 4.2 The texts

| Cable connector | `harness_device_connector` | `{mates_name}` in a template |
|---|---|---|
| plugs into box connector `MTQ1-J01` named `J01` of device `MTQ1` | `W001:MTQ1:J01` | `J01` |
| loose end `W009-P2` | `W009:W009-P2 open end` | `open end` (as `{mates}`) |
| plugs into nothing, or its `mates_with` names no connector of the project | `W001:W001-P3` (as the plan's header for a connector without a box, `[W001:W001-P3]`) | `-` (as `{mates}`) |
| splice | no label (as in every format) | — |

The person's label of a connector (`Connector.label`, else the box connector's) is **not** part of this format: the form is fixed so that the bench can rely on it. A person who wants both uses `custom` with `{name} {harness}:{device}:{mates_name}`. `explain DIR W001-P1` says so.

A wire's labels in the new format are the standard text (`W001-017 PWR to W001-P10.1`), so only the connector labels differ from `standard` (P5).

### 4.3 A default for new projects is a change of a template, not of the format

The registry default stays `standard`, for the reason D-247 gives for `segmentation.mode`: the default is what a file that names nothing is read as, and every project written before 4.1.0 names nothing (none of the five examples has `config/model.json`; a project made by `new` at 4.0.1 has none either). So:

- **New projects** get the new format through `samples.start_project`: `new FOLDER`, `new FOLDER --template blank` (the blank example, written by `tools/build_examples.py` from `start_project`: its folder gets `config/model.json`), the editor's *New project* (`EditorController.new_project`), `create_project` of the scripting interface (default template `blank`) and the empty project of `tools.usability_setup`. These are the same five ways D-247 lists.
- **Every existing project keeps its labels** byte for byte. A project made from the `flatsat`, `minimal-satellite`, `small-satellite` or `first-steps` template keeps `standard` (it copies the example's files).
- **No new key:** `label_format` is a key of `config/model.json` since 1.15.0 (D-198); only a value is new. This is not a format change by the rule of D-254.

**But a 4.0.x tool cannot work on such a project.** Run with 4.0.1 on a copy of `flatsat` with `"label_format": "harness_device_connector"` in `config/model.json`: `validate` reports `ERROR config_invalid: config/model.json: label_format must be one of standard, compact, descriptive, custom`; `generate` prints the same error and *Not saved: fix the errors above first*; `export` writes the outputs with the **standard** labels and no warning. The same holds for a template with `{mates_name}` (*uses the field {mates_name}, which does not exist*). This differs from `per_connector_group`, which a 2.2 tool read as the old mode. The release notes say: update the whole team at the same time, before anyone starts a new project with 4.1.0 (P4).

### 4.4 How the verifier checks it

`verify_labels.py` (section 3.6) gets `harness_device_connector` in `_LABEL_FORMATS`, `mates_name` in `_LABEL_FIELDS["connector"]` and the branch of section 4.2 in `_connector_label_text`, written from its own words. `_label_rows` serves `labels.csv`, the *Labels* sheets and the Production block headings. `tests/test_label_format_outputs.py` exports every example in every format, the new one included, and compares the copy with the core's by Hypothesis.

### 4.5 The plan's header in the new format

The users' template header is `[<number>:DEV2:J4711]`, where `J4711` is the device's own connector number. While the format in force is `harness_device_connector`, the plan writes it with the name: the `CON_…` sheet gets *Connector Name* in `A4`/`B4` (row 4 is empty today) and the near block header becomes `ctype [W001:MTQ1:J01]`, its formula pointing to `B4` instead of `B2`. In any other format the plan is as today. `verify_plan.py` states the cell and the formula a second time.

### 4.6 What changes in existing outputs

Nothing, for every project that does not name the new format. A new project writes the new connector texts in `labels.csv`, the *Labels* sheets, the Production headings and, with the plan, `B4` of its `CON_…` sheets and the near block headers. The examples, the fixtures and the baseline do not move; the blank example gains one file.

## 5. Part C: the plan's harness sheet over several pages

### 5.1 What is built

**`core/outputs/ods.py`** gets three things, each off by default, so that every sheet that does not use them keeps its bytes (the golden digest of the sample in `tests/test_ods.py` stays):

- `Page.scale: int = 0`: a fixed scale in percent, written as `style:scale-to="62%"` in the page layout (ODF 1.2; read by LibreOffice and by Excel's ODS import). `fit` and `scale` are exclusive (`ValueError`).
- `Sheet.repeat_rows: tuple[int, int] | None = None`: the rows (0-based, first and last) written inside `<table:table-header-rows>`, which a reader repeats at the top of every printed page.
- `Sheet.breaks: tuple[int, ...] = ()`: the rows before which a page starts, each written with a row style `style:table-row-properties fo:break-before="page"`. `_repeat_rows` must not merge a break row with the rows before it.

**`harness_plan._HarnessSheet.build`** then writes the harness sheet with:

- `Page("A4", landscape=True, scale=S)`, where `S` is the largest whole percent at which the print range is one page wide: `min(100, floor(277 / width of the print range in mm × 100))`. For W001 of `flatsat`: 277 / 448 → 61 %. The `CON_…` sheets, *Cover*, *Change_Register* and *Notes* keep `fit=True`. *Change_Register* shares the page style of the harness sheet today; it keeps its own.
- `repeat_rows = (5, 8)`: rows 6 to 9, the system, harness and version line (`H6`, `N6`, `Q6`), the title (`H8`) and the length note of part D (`H9`, section 6.2). Row 9 is empty today; the part tables start in row 10 (`part_tables(9)`).
- `breaks`: a page starts before a near block (its title row) that would not fit in what is left of the page, worked out with one line per row of 4.52 mm at scale `S` and 14 pt for the title rows (`TITLE`); a block longer than a page is split by the reader where it falls. The part tables, *Further wires*, the sums and the reference pinouts get no break of their own.

The print range stays `H6:` to the last far pin column (the device side A to F stays outside it, as today).

What it gives on W001 of `flatsat`, worked out from the widths, not printed: 61 % in place of about 22 %, so 10 pt text prints at about 6 pt; about 60 rows a page, so 173 rows on 3 pages, each with the heading rows. The width grows by 22 mm per far connector, so a harness with many far ends prints smaller; P10 asks about A3. The Production sheet is the sheet to read at the bench; the harness sheet stays the users' layout.

The plan's Production sheet (part A) uses the same three things: `Page("A4", landscape=True, scale=S)` with its own widths (chosen to sum to at most 277 mm, so `S` is 100), `repeat_rows = (0, 2)` (the title, the length note and the column headings) and a break before a block that would not fit.

### 5.2 How the verifier checks it

`verify_plan.py` says today: *Not checked: the styles, the column widths, the print set-up*. Part C is about the print set-up, so it learns that much (code `out_plan`):

- the page layout of the harness sheet and of the Production sheet has no `style:scale-to-pages`, and its `style:scale-to` is the percent worked out from the column widths **as the file states them** (read from the column styles of `content.xml`) and the print range;
- the harness sheet's header rows are rows 6 to 9 and the Production sheet's rows 1 to 3;
- every break is before the title row of a block, and a block that fits on a page is not split (with the verifier's own copy of the row heights above).

The other sheets stay unchecked for print set-up, as today.

### 5.3 What changes in existing outputs

Every plan's `content.xml` and `styles.xml`. No cell value changes through part C alone, so the readable dumps of `tests/fixtures/outputs/harness_plan/*/` move only through parts A and D (`dump` writes cells, not styles), and the digests of every plan move. The plans are not in the output-hash baseline (section 2), so it does not move for part C.

## 6. Part D: every length says its reference

### 6.1 The words

One function in **`generate/lengths.py`**, `reference_text(project) -> str`, worded from the settings in force:

> Lengths run from the rear of a connector (where the wires leave its body or backshell) along the routing segments, through the centre of each branch point, to the rear of the other connector. A wire Generate made adds 2 service loops of 0.1 m. *Locked* is a length a person typed; *segments only* has no service loops.

With `service_loop_m` not set: *… adds no service loop (config/generation.json: service_loop_m is not set)*. With `path_loops_allowance_twist`: *… adds 2 service loops of 0.1 m, the take-up of twisting (0.02) for a twisted pair or quad, and a cut allowance of 0.05 m*. The numbers are the project's (`settings.service_loops`, `settings.number`); none is invented.

### 6.2 Where it goes

| File | Column today | Becomes | And the sentence |
|---|---|---|---|
| build workbook, *Cut list* | `Length (m)` | `Length (m), rear to rear` | in *Start here*, a row **Lengths** under *From the design*, and the last row of *Cut list* |
| build workbook, *Routing* | `Length (m)` (`tables.SEGMENT_HEADER`) | `Length (m), rear or branch centre` (a header of its own; `segments.csv` keeps `SEGMENT_HEADER`) | the last row of *Routing* |
| build workbook, *Production* | — | `Length (m), rear to rear` and *Length from* | the last row of *Production* |
| plan, harness sheet, column N of the blocks and of *Further wires* | `Length [mm]` | `Length [mm] rear to rear` | `H9`, repeated on every page (section 5.1) |
| plan, *used Cable Types*, column S | `Length [mm]` | `Length [mm] rear to rear` | the same |
| plan, *Production* | — | `Length [mm] rear to rear` and *Length from* | row 2, repeated on every page |

The CSV files, `<ID>.xlsx`, `system/export.json` and the drawings keep their words (section 1.2, P6); `docs/OUTPUTS.md` says what their lengths mean.

### 6.3 Where a wire's length comes from

The cell *Length from* answers the question a builder asks first: is this the length to cut? One function, `lengths.length_origin(h, w)`, reads only the wire and the segments:

| Value | When |
|---|---|
| `on the wire` | `Wire.length_m` is set and the wire is not locked: Generate's length with its loops, or an imported one (`explain` tells which) |
| `locked` | `Wire.length_m` is set and the wire is locked (typed in *Edit wire*, or an override of `length_m` with its reason) |
| `segments only, no service loops` | no `Wire.length_m`, and the segments give a path: the length has no loops (`docs/models/wire-length.md`, *A wire with no length of its own is measured from the segments alone*) |
| (empty) | no length: the cell is *to fill in* |

It does not tell *generated* from *imported* apart, because that needs the length model a second time in the verifier and a float comparison; `explain DIR WIRE` keeps that answer (`derive.wire_length_derivation`, *generated: the path through the segments plus two service loops*). `derive.py` calls `length_origin` for its first cut, so the two cannot disagree on the three cases.

### 6.4 How the verifier checks it

`verify_production.py` holds its own copy of the sentence (`_length_reference`, from `settings.effective`, as `verify.py` reads `model.label_format` today) and of `length_origin`. `verify.py` checks the headings of *Cut list* (`_BUILD_CUT_HEADER`), *Routing* and *Production*, the *Lengths* row of *Start here* and the last rows; `verify_plan.py` checks `H9`, the three headings and row 2 of *Production*.

### 6.5 The editor

The editor shows no length reference today and gets none in 4.1.0. *Settings > Project* shows the new choice of `model.label_format` from the registry, with *(a new project's choice)* after it, as D-247 did for the segmentation.

## 7. What changes in the written files, and the guards

| Written file | Part | Which projects | Opt-in? | Guard to renew |
|---|---|---|---|---|
| `<ID>_build.xlsx`: new sheet *Production*, *Start here* lines, length headings and rows | A, D | every project, every harness | no (P1) | `docs/ui/OUTPUT_HASHES_BASELINE.json` (the 45 build workbooks of the four examples), `tests/fixtures/numbers/snapshot.json`, the build workbook digests of `tests/fixtures/outputs/*.json` |
| `<ID>_plan.ods`: new sheet *Production*, `H9`, headings, page set-up | A, C, D | every project that writes plans (`export --harness-plan`) | the plan itself is opt-in, as since 3.0.0 | `tests/fixtures/outputs/harness_plan/*.json` (digests) and the four text dumps |
| `labels.csv`, *Labels* sheets, Production headings, the plan's `B4` and near headers | B | projects that name `harness_device_connector`: new projects only | yes | none: no example or fixture names it |
| blank example `config/model.json` | B | the bundled blank project | — | `tools.build_examples` (the test of the examples) |
| `wirelist.csv`, *Wire list* of `<ID>.xlsx`, *Cut list*: every shield group of a wire | P7 | harnesses with a wire in two groups (`flatsat` W002 and W004 as shipped) | no | the baseline entries of those files |
| CSV, JSON, drawings, `manifest.json` format | — | — | — | unchanged |

The baseline is renewed on purpose, with the reason in `CHANGELOG.md` and the decision row, as for 3.0.0 and 4.0.0 (`tools/output_hashes.py`, its module text). `BASE_VERSION` stays `2.4.0`. To keep the reviews small, each pull request of section 14 that moves a file renews the guards for that one reason, and its diff is read file by file: a cell that changes and is not named by the pull request is a fault.

**The proof of 3.0.0 is a guard too** (`tests/test_format3.py::test_the_written_files_of_3_0_are_those_of_2x_after_the_word_list`, a slow test: it runs on `master` only, not on a pull request). It compares every written file of the recorded projects with the file of 2.x after a list of steps, so each pull request of section 14 that moves a written file gives it a step that states the change a second time. Step 7 (`every_shield_group`, `tests/format3_support.py`) is the change of pull request 2 (P7); it came after #311, whose merge left the test red on `master`. Step 8 (`production_sheet`) is the change of pull request 3 to the build workbook. Pull requests 3 and 5 run this test, and the other slow tests, before they are merged.

## 8. Edge cases found in the code

| Case | Where in the code | What the design does |
|---|---|---|
| **Splice** (role `splice`) | `SPLICE_ROLE`; `buildsheet._connector_sheet` puts splices last; `tables.labels` gives no splice a label; `core/nets.py` | A block per splice after the connectors, a row per node and wire; *Goes to* is the wire's other end, not the net's far end (the cut list's view: each piece is a wire); the wire's label at the splice end is the one `tables.labels` lists today; the block heading has no label. Shield groups through a splice usually end on more than two connectors: `here not defined` |
| **Loose end** (role `loose`) | `tables.is_open_end`, `OPEN_END`, `LOOSE_PART_TAG`; D-201 | Heading `… · open end, to fill in`; the far side of a wire to it reads `W009-P2.1 (open end)`; its connector label in the new format `W009:W009-P2 open end` |
| **Branching harness** (`per_connector_group`, branch points) | `tables.has_branches`; *Routing* sheet; `wire_length` along the one path | Nothing special for the rows: each wire has its own two ends and its own path length. A group across a branch: section 3.5 |
| **Pin with no wire** | `_pin_rows` (`(spare)`, `(no wire)`) | Spare runs folded; a pin with a signal or interface stays a row (3.4) |
| **Pin with two or more wires** | `_attached` | One row per wire (3.4) |
| **Shield drain or pigtail** | `ShieldEnd` `pigtail`; `PinRole` `shield`; no group names a pin | The end reads `pigtail`; the pin where it lands is not in the design (E5). A box pin of role `shield` with no wire is a `(no wire)` row with its signal: the checker sees it, the sheet does not claim which group lands there |
| **Nested groups** (pair in an overall shield) | `ShieldGroup.wire_ids`; `tables.shield_of` keeps one group per wire | Both groups listed (3.5); see section 15 for the fault in the other tables |
| **Several wire parts in one harness** | `Wire.part_id` (W002 of `flatsat`: `EX-WIRE-SINGLE` and `EX-WIRE-TWISTED-SHIELDED`) | The part per row; the plan keeps its *used Cable Types* table; a pair part (`Part.conductors` 2) is named as the part, its conductors are two rows |
| **Wire without part, gauge or length** | `TO_FILL` | *to fill in*, amber, as the cut list |
| **Custom label templates** | `label_format.template_of`, `check_template` | The row label is the template's end A or B text (`{end}`, `{from}`, `{to}`); a template that names no wire ID can give equal texts: `label_not_unique` already warns |
| **Box connector name** | `Connector.name` is required (`Name`, 1 to 200 characters), unique per device ignoring case | Never missing on a box connector. It is missing when the cable connector plugs into nothing, is a loose end, or names a box connector that does not exist (`integrity`: `mates_with` not in `project.connectors`): section 4.2 gives each a text. A name is free text: one with `:` or spaces is printed as it is; no check is added (P4) |
| **Two plugs of one harness on one box connector** | possible in a drawn harness; `box_connector_shared` is across harnesses | The new format gives both the same text; `label_not_unique` warns (4.1) |
| **Label accessories** | `Accessory` of kind `label`, `target`, `position` (D-170) | The position of one that targets the connector goes into the block heading; one that targets a wire stays on the *Accessories* sheet |
| **Pin-code colours in the plan** | `plan_settings`, `colour_rule` `pin_code`, `_HarnessSheet.colour` | The plan's harness sheet may show the pigtail colour of the pin code instead of `Wire.colour`; P8 |
| **A harness named `Production`** | `harness_sheet_name`, `_FIXED_NAMES` | `Harness_Production` |
| **Row heights** | `ods.py` writes no row height; wrapped text grows a row | The breaks of section 5.1 assume one line per row; a reader adds its own breaks where a wrapped cell makes a block taller |

## 9. Tests to write

| File | What it holds |
|---|---|
| `tests/test_production_sheet.py` | The blocks and rows of `flatsat` W001 (counts: 18 blocks, 54 rows), W002 (nested groups), W005 (a coax), the splice fixture (`tests/splice_support.branch_leg_project`), the loose-end fixture (`tests/loose_support.generated_loose`), the branching fixture, a drawn pin with two wires, a wire without part, gauge or length; the sheet order with and without *Routing* and *As-built*; the tick column empty; the page breaks before a block |
| `tests/test_production_verify.py` | The imports of `verify_production.py` and `verify_labels.py` (no builder); Hypothesis: `production_rows` of the verifier equals `production_blocks` on random harnesses; a mutation of each column gives `out_build` and `out_plan` |
| `tests/test_shield_ends.py` | `end_at` against `drawing._reference_wire` on every example; a group across a branch gives `None`; coax; nested groups; the drawings of the examples keep their bytes |
| `tests/test_length_reference.py` | `reference_text` for loops set and unset, both length models; `length_origin` agrees with the basis of `derive.wire_length_derivation` on every wire of every example |
| `tests/test_plan_print.py` | The harness sheet: no `scale-to-pages`, `scale-to` from the widths, header rows 6 to 9, breaks only before block titles, no block that fits split; the `CON_…` sheets, *Cover*, *Change_Register* and *Notes* as before; the verifier refuses a plan whose harness sheet is fitted to one page |
| `tests/test_ods.py` | A new sample with `scale`, `repeat_rows` and `breaks` and its digest; the old sample's digest unchanged; `fit` with `scale` refused |
| `tests/test_label_format_outputs.py` | The new format and `{mates_name}` exported on every example; the four texts of section 4.2; `label_not_unique` for the new format; the copy compared with the core's |
| `tests/test_new_project_labels.py` | `new`, `new --template blank`, `create_project`, the editor's *New project* and `tools.usability_setup` start in the new format; the examples, `mini3`, `sat15` and `custom_device` name none; `config/model.json` of a new project is not a placeholder |
| `tests/test_shield_group_columns.py` | (P7) the wire list and the cut list name every group of a wire; the verifier refuses one group missing |
| `tests/test_e2e_410.py` | One project end to end: `new`, a device library, Generate, the new label format, `export --harness-plan`, `verify --outputs`, the Production sheet of both files read back row by row |

The requirements: **REQ-OUT-13** (the Production sheet in both files, checked by the verifier), **REQ-OUT-14** (every length of a document says its reference), **REQ-OUT-15** (the plan's harness sheet prints over several pages with its headings), **REQ-LABEL-02** (the named format and the default of a new project), in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`).

## 10. Documents to update

- `CHANGELOG.md`, `## Unreleased`: one entry per pull request; the reason for each renewal of the baseline.
- `docs/releases/4.1.0.md`: what is new (the sheet, the format, the print, the lengths); *For scripts*: the sheet names of the build workbook and the plan changed (a script that reads sheets by position breaks), the headings of *Cut list* and *Routing* changed, the CSV files did not; *Upgrade*: the whole team at the same time (section 4.3); *Known limits* (section 16).
- `docs/OUTPUTS.md`: a row *Production* in the table of the build workbook and in the table of the plan; the new headings; the lengths of the CSV files; the new label format in the labels row.
- `docs/developer/agent/outputs.md`: a bullet for the Production sheet (`production.py`, `verify_production.py`, `verify_labels.py`), one for `shield_ends.py`, one for the print set-up of `ods.py`, and the label bullet with the new format.
- User manual: `docs/user-manual/export-the-outputs.md` (the Production sheet, how to print it), `export-the-harness-plans.md` (the sheet, the pages, the scale, P10), `naming-and-title-block.md` (the new format and what a new project starts with), `see-what-the-tool-assumes.md` (the table of `model.label_format`), `enter-the-build-data.md` (the label position in the heading).
- Models: `docs/models/labels-and-colours.md`, `selectable-models.md` (the choice), `wire-length.md` (what the outputs now say, and *Length from*), `shields.md` (which connector is end A; no page says it today).
- `docs/CONFIG.md` (the values of `model.label_format`), `docs/GLOSSARY.md` (*Production sheet*, *End A of a shield*), the in-app guide (`python -m tools.build_guide`).
- `docs/ait/ELEC_FEEDBACK_PLAN.md`: its status (E0 done, E1 designed) and the corrections of section 15.
- Not changed: `docs/FILE_FORMAT.md` (no key), `docs/CLI.md` (no command or option; `python -m tools.gen_cli_docs` is run to show it), `docs/RULES.md` (no rule).

## 11. What does not change

The project format and `SCHEMA_VERSION` (4); `system/export.json` and its `format_version` (2); the CSV files and the tables workbook; the drawings; every rule (39) and every check of `check`; the command line and the scripting interface (`API_VERSION` 1, `tests/fixtures/api_snapshot.json`); the *Connectors* sheet; the cut order; the plan's near and far sides, its formulas, its search boxes and its `CON_…` sheets (outside part B's sparse `B4`).

## 12. Proposed decision D-256

> | D-256 | **Release 4.1.0 is a minor release with the production sheet (milestone E1 of `docs/ait/ELEC_FEEDBACK_PLAN.md`); no format change** (D-254, D-255; design `docs/ait/DESIGN_4.1_PRODUCTION_SHEET.md`). (1) The build workbook and the harness plan get a sheet *Production*: one block per cable connector in natural ID order, splices last; one row per pin and wire, a run of spare pins on one row; the columns Pin, Signal, Wire, Goes to, Wire part, Colour, AWG, Length, Length from, Label at this end, Shield group with its end here and at the far end, and in the workbook Done (x). The rows come from one function (`core/outputs/production.py`); the verifier words them again (`core/outputs/verify_production.py`, with the label copy moved to `verify_labels.py`). End A of a shield group is the `from` end of its wire with the lowest ID, the rule of the drawings, now one function (`core/shield_ends.py`). (2) The label format `harness_device_connector` writes a cable connector's label `HARNESS:DEVICE:CONNECTOR NAME` (`W001:MTQ1:J01`) and a wire's the standard text; the template field `{mates_name}` is the box connector's `Connector.name`. A new project starts in it (`samples.start_project`, as D-247 did for the segmentation); the registry default stays `standard`, so no existing project changes its labels. A 4.0.x tool refuses the value (`config_invalid`; Generate does not save; export writes the standard labels), so a team updates at the same time. (3) The plan's harness sheet prints at a fixed scale, one page wide, with rows 6 to 9 repeated and a page break before a block that would not fit, in place of one page. (4) Every length heading of the build workbook and the plan says *rear to rear* (a segment *rear or branch centre*), and each document states the reference once in words from the project's settings; the CSV and JSON files keep their headings. **Written files:** every build workbook and every plan changes once; the output-hash baseline, the numbers snapshot and the goldens are written again for this reason; labels change only for a project that names the new format. | The owner's answers to P1 to P10. The engineer's feedback of 2026-11-20 (points P, Cc, 1, 5, 6, 7). |

The release decision of 4.1.0 is a later row (D-257), as D-254 followed D-251.

## 13. Owner questions

Each with our recommendation first.

1. **P1. The Production sheet in every build workbook and every plan, with no setting?** Recommended: yes. It is the top request; a setting that is off by default would leave it unfound. The cost is one renewal of the baseline and the goldens, reviewed file by file.
2. **P2. A run of spare pins on one row (`3 to 9`, `(spare)`)?** Recommended: yes. On `flatsat` it takes W002 from 484 rows to 74. The *Connectors* sheet keeps every pin for the termination checks.
3. **P3. One row per wire when a pin has two or more?** Recommended: yes (section 3.4). The alternative is the *Connectors* sheet's joined cell.
4. **P4. The name `harness_device_connector`, the field `{mates_name}`, the default for new projects, and no `Connector.label` in the format?** Recommended: yes to all four. The field sits beside `{mates}` (the ID) as `{name}` sits beside `{connector}`; a person's label stays available through `custom`. We also recommend no new check for a name with a colon: the device names it, and the format prints it as it is.
5. **P5. The wire labels in the new format: the standard text, or the far end by device (`W001-017 PWR to PDU2:J10.1`)?** Recommended: the standard text in 4.1.0. The engineer asked about connector labels; a second wire text is a second format to verify. Ask the engineer after they use 4.1.0.
6. **P6. The length reference in the documents only, not in the CSV headings, the JSON keys or the drawings?** Recommended: yes. Scripts read the CSV headings; the drawings are optional (D-169) and print no column. `docs/OUTPUTS.md` states what every length of every file means. The drawings can get one note line in a later minor release.
7. **P7. Fix the one-group-per-wire fault of the wire list and the cut list (section 15) in 4.1.0?** Recommended: yes, as its own pull request with its own reason for the renewal. It changes `wirelist.csv`, the *Wire list* of `<ID>.xlsx` and the *Cut list* of harnesses with a wire in two groups (W002 and W004 of `flatsat`). Not in 4.0.1, which is prepared and only waits for its tag.
8. **P8. The colour on the plan's Production sheet when the plan uses the pin code (`colour_rule` `pin_code`)?** Recommended: `Wire.colour` in both files, and in the plan a column *Pigtail colour* only while the rule is `pin_code`, from the same lookup as the harness sheet. Two files must not give one wire two colours without saying why.
9. **P9. The plan's near header `[W001:MTQ1:J01]` while the new format is in force (section 4.5)?** Recommended: yes. It is the users' own template form; the change is sparse.
10. **P10. The plan's harness sheet on A4 landscape at about 60 % for W001, or A3 when it has many far connectors?** Recommended: A4 as the engineer asked, with the Production sheet as the bench sheet. If a team prints the harness sheet, A3 for a sheet wider than a set number of columns is a later setting in `config/harness_plan.json`.

## 14. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry.

| PR | Content | Guards |
|---|---|---|
| 1 | **Core, no output change.** `core/shield_ends.py` (`end_at`, `reference_wire`; `drawing.py` calls it), `lengths.reference_text` and `length_origin` (`derive.py` calls it), `core/outputs/production.py` with no caller; `core/outputs/verify_labels.py` (the label copy moved out of `verify.py`, no new word) and `core/outputs/verify_production.py`; the Hypothesis comparisons; `tests/test_shield_ends.py`, `tests/test_length_reference.py` | `output_hashes --check` and `numbers_snapshot --check`: *identical* |
| 2 | **Shield groups (P7).** `tables.shield_groups` (every group, natural order, `; `), used by `wire_list` and `_cut_sheet`; `verify.py` the same on its own; `tests/test_shield_group_columns.py` | renewed for the harnesses with nested groups only |
| 3 | **The build workbook.** `_production_sheet`, `SHEETS`, *Start here* (the line and the *Lengths* row), the headings and last rows of *Cut list* and *Routing*; `verify.py` `_build_production`, `_BUILD_SHEETS`, `_BUILD_CUT_HEADER`; mutation tests; REQ-OUT-13, REQ-OUT-14 | baseline (45 workbooks), numbers snapshot, `tests/fixtures/outputs/*.json` |
| 4 | **The `.ods` writer.** `Page.scale`, `Sheet.repeat_rows`, `Sheet.breaks`; no caller change; `tests/test_ods.py` | the sample's digest unchanged; a new sample |
| 5 | **The plan.** The harness sheet's scale, header rows 6 to 9, breaks, `H9` and the headings; the sheet *Production*; `_FIXED_NAMES`; `verify_plan.py` (the cells, the print set-up of section 5.2); `tests/test_plan_print.py`; REQ-OUT-15 | `tests/fixtures/outputs/harness_plan/` |
| 6 | **The label format.** `label_format.py`, `tables.connector_label_text`, `settings.py`, `configcheck.py`, `assumptions.py`, `derive_build.py`, `engine._warn_equal_labels`, the plan's `B4` and header (P9), `verify_labels.py`; `samples.start_project`; the blank example (`tools.build_examples`); `tests/test_new_project_labels.py`, `tests/test_label_format_outputs.py`; REQ-LABEL-02 | *identical* (no example names the format); the plan goldens unchanged |
| 7 | **End to end and documents.** `tests/test_e2e_410.py`; the pages of section 10; the guide; `docs/releases/4.1.0.md` | — |
| 8 | **The preparation of 4.1.0**: version, changelog section, the decision row D-257, the status pages; after 4.0.1 is tagged | stamp only (`4.1.0` has five characters) |

Order: 1 first; 2 before 3 (so the cut list of 3 is read once with every group); 4 before 5; 6 at any time after 1 (its plan part after 5); then 7; then 8. **4.0.1 is tagged before pull request 3 is merged**, because from 3 on `master` writes other build workbooks than 4.0.1, and a 4.0.x patch from `master` would carry them.

## 15. Corrections to the plan

Checked against the code at 4.0.1 and the runs of section 2.

1. **E0 is done.** The plan's status (*Nothing is built*) and its section *Found during the investigation* predate #306: the verifier words every label format since 4.0.1 (D-255, prepared, not tagged). Its owner question 1 is answered by the fact.
2. **The plan's harness sheet of W001 is 178 rows and 9 blocks, not 143 rows and 18 blocks.** The sheet has blocks for the 9 near connectors only; the other 9 connectors are the far pin columns T to AB. The printed range is `H6:AB178`, about 448 mm wide.
3. **The wire list and the cut list name one shield group per wire, not every group.** `tables.shield_of` (`{wid: s.id for s in h.shields for wid in s.wire_ids}`) keeps the last group of a wire, and `verify.py` checks with the same rule (`_harness_cells`, `_build_cut`), so the self-check cannot see it. On `flatsat`, 14 wires of W002 and 6 of W004 are in a twisted pair inside an overall shield; `wirelist.csv` shows `W002-S3` for `W002-003` and not its pair `W002-S2`. The plan's *Shielding* column lists both (`_HarnessSheet.shields`). The plan's point 7 says the build workbook shows *only the group ID*; it shows only **one** of the groups (P7).
4. **Which connector is end A is not stated anywhere a user reads.** The plan says the ends are *in the drawings and `system/export.json`*. `export.json` holds `end_a` and `end_b` without the connector; only the drawing places them, by a rule in `drawing._reference_wire`. A production sheet must name the connector, so the rule becomes a function (section 3.5).
5. **A new value of a setting is not harmless to an older tool.** The plan counts the label default as *a setting in `config/`* that fits a minor release, as `per_connector_group` did. That holds for the format, but a 4.0.x tool refuses the value as `config_invalid` and will not save after Generate (section 4.3); a 2.2 tool read an unknown mode as the old one.
6. **Some lengths in the outputs have no service loops.** The plan says *backside to backside plus loops is built in*. That is true for a length Generate stored; a wire with no `length_m` (a harness drawn by hand, or after the segments were entered and before Generate) is measured from the segments alone, without loops (`wire_length`, `docs/models/wire-length.md`). *Length from* says so on the sheet (section 6.3).
7. **The *Connectors* sheet's blocks are per cable connector** (`W001-P1 … mates with MTQ1-J01`), so it already covers both ends; what it lacks is part, length, label and shield, as the plan says.

## 16. Risks and what this design does not check

- **No sheet was printed.** The scales, the rows per page and the font sizes of sections 2 and 5 are worked out from the column widths and a default row height of 4.52 mm. LibreOffice and Excel may differ; pull request 5 is read back in LibreOffice offscreen (`soffice --convert-to pdf`) if the CI image has it, else the numbers stay estimates in the release notes.
- **`style:scale-to`, `table:table-header-rows` and `fo:break-before` on a row** are ODF 1.2; how Excel's ODS import treats the breaks was not tried.
- **Nobody at a bench has seen the Production sheet.** The column order, the folding and the `to` of a spare run are this design's; the engineer should see a printout of `flatsat` W002 before 4.1.0 is tagged.
- **The 42-row break of the build workbook** is the *Connectors* sheet's rule, kept; with wrapped label texts a block can still cross a page.
- **The width of the Production sheet** with a long custom label (up to 200 characters) is capped at 46 characters per column (`_Layout.see`), so such a label wraps.
- **The other examples' nested groups:** only the shipped `flatsat` harness files were counted; `minimal-satellite`, `small-satellite` and `first-steps` are generated when hashed, so pull request 2 lists what moves there.
- **The 4.0.x behaviour** of section 4.3 was tried with the prepared 4.0.1; 4.0.0 has the same `validate_model`.
- **No code was written**; the module and function names are the plan, and the pull requests record where they differ.
- **Found by pull request 7, open: *Length from* says `locked` for a wire that an override of another field locked.** `lengths.length_origin` (and the verifier's copy `verify_production._length_origin`) read `Wire.locked`, which an override of `gauge_awg`, `part_id` or `colour` also sets, while Generate still gives such a wire the length of its path. Reproduced on a new project: `import-lengths` of the one segment (1.2 m), `override W001-001 gauge_awg 24`, `generate`: the Production sheets say `locked`, the sentence under them says *"Locked" is a length a person typed*, and `explain DIR W001-001` says *generated: the path through the segments plus two service loops*; after the segment is set to 1.5 m and Generate runs again, the length follows to 1.5 m. Section 6.3 meant `locked` for a length typed in *Edit wire* or an override of `length_m`. The end-to-end test sets the length on purpose (`override … length_m`) and gives no gauge, so it does not depend on this case; the fix (both copies, and the goldens of any project with such a wire) is left to the owner's choice.
