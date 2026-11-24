# Design of 5.1.0: a template for each feature

Written on 2026-11-24 from a reading of the code at 5.0.0 (annotated tag `v5.0.0` on `4c9cea5`, the merge of the preparation, #365; the checkout reports `harness 5.0.0`) and from runs of the command line and of throw-away scripts on copies of the five examples and on small projects built with the tool's own edit functions in a scratch folder. It answers the owner's request of 2026-11-24, word for word: *"I am missing examples/ template projects that cover all features of the tool. meaning it would be great if there is at least one template each per feature. Also I want a template where the connectors are not empty but are fully populated. I also am missing examples that show how to create spliced harnesses."* Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the designs of 4.4.0 and 5.0.0 ([`DESIGN_4.4_NAMES_PORTS.md`](DESIGN_4.4_NAMES_PORTS.md), [`DESIGN_5.0_FORMAT_5.md`](DESIGN_5.0_FORMAT_5.md)): scope, what exists, the catalogue of features, the new templates, the rules they follow, the list and the dialog, the release, edge cases, tests, documents, the decision, the owner questions, the pull requests, what was found on the way and what was not checked. Choices that are the owner's are T1 to T14 (section 13), each with a recommendation first. Every device, part, harness, person and company name on this page is made up for the example (`OBC1`, `TTC1`, `PCDU1`, `EX-SPLICE-1`, `Example Ltd`, `Designer 1`), and so is every number of a length, a depth, a current or a rating.

**Status (2026-11-24):** built and prepared as 5.1.0, not tagged. Pull requests 1 to 7 of section 14 are written, each on the one before, and are merged into `master` one at a time before this preparation: 1 (*The groups and `full-connectors`*), 2 (*The two splice templates*, with part E, the note `isolated`, and item 3 of section 15), 3 (*Routing*), 4 (*Change control*), 5 (*Data in and out*), 6 (*Files beside the model*, part C) and 7 (the page *Examples*, the documents of section 11 and `tests/test_e2e_510.py`). Pull request 8 is the preparation of 5.1.0, with the release notes `docs/releases/5.1.0.md` and the sizes measured. The pull requests follow the recommendations of T1 to T14; no owner answer is recorded. What was built differently is in the commit messages of the pull requests and in D-268. D-268 (section 12) is decided with the preparation, and the release is D-269: a minor release, no format change, no release candidate first. D-267 is the record of the owner's answers to F1 to F16 of the design of 5.0.0 (pull request 367, merged). The text below is the design as it was written.

## 0. The frame

The tool has grown feature by feature since 1.0.0, but its examples have not: the five projects of `harness-design-studio new --list` are the ones of 1.0.0. None of them has a splice, a connection, a released harness, an override, a pin with a signal before Generate runs, a row layout, a pin current, a depth, a place of a shield end or a checked device (section 2.2). A reader of the manual page *Splices* draws a splice by hand on `first-steps`; a reader of *Lengths to the face* adds depths to a copy of `first-steps`; nobody can open a project and look at a finished example of most features.

The answer is a set of small projects, one per feature (or two features where one project shows both naturally), shipped like the five, built by `tools/build_examples.py` with the tool's own edit functions, listed in two groups so that a newcomer still finds `first-steps` first:

1. **One template per feature.** Every user-visible feature of the 37 pages of the user manual, the 43 rules and the fields of format 5 is shown by at least one template, an existing one or a new one (section 3). Fourteen new templates; the five existing ones keep their names, titles and files.
2. **Small.** Two to five devices each, so that every table of the outputs fits on a screen and the feature is not lost in a satellite.
3. **Built, not drawn.** Each template is made by a builder function that calls the edit functions a person's clicks call (`edit.ops_add_unit`, `links.plan_create_harness`, `splices.plan_add_splice`, `vcs.release.plan_release` …), so it is valid by construction and in the current format; a test fails while a shipped folder differs from what the builder writes (`tests/test_examples.py`, as today).
4. **Made up and marked.** Every engineering number in a template is an EXAMPLE, its configuration files stay `"placeholder": true`, its parts are `EX-` parts that nobody approved (D-11, D-12, D-129).
5. **No format change.** 5.1.0 is a minor release. Nothing a template needs is a new key of a project file (section 8).

## 1. Scope

### 1.1 In scope

| Part | What is built |
|---|---|
| A | **Fourteen feature templates** (section 4): `full-connectors`, `names-and-ports`, `splice-by-hand`, `splice-from-connection`, `branching-harness`, `loose-cable-end`, `shields-and-ends`, `lengths-to-the-face`, `released-harness`, `overrides-and-deviations`, `device-library`, `build-data-and-as-built`, `imports-from-files`, `extensions`; their builders (`tools/feature_examples.py`, called by `tools/build_examples.py`) |
| B | **The list in two groups** (section 6): *Start* (the five, unchanged) and *Feature examples*; `TemplateInfo.group`; `new --list` with a heading per group and a name column as wide as the longest name; the New project dialog with a heading per group; the Home page with the *Start* group and one line for the rest; the help of `new` made from the list |
| C | **Files beside the model** (section 5.6): `create_project` copies, besides the project, the folder `extensions/`, the file `device-libraries.json` and the library folders it names inside the template folder; nothing else |
| D | **A pinout template file** `device-pinout-EXAMPLE.csv` in `resources/examples/templates/` (section 4.13): the import templates hold no pinout today |
| E | **The fix of the note `isolated`** (section 15, item 1): a device that a harness drawn by hand plugs into is connected |
| F | **Documents** (section 11): a user manual page *Examples* that lists every feature with its template; one line in each manual page naming its template; `README.md`, `GETTING_STARTED.md`, `FAQ.md`, `docs/examples/README.md`, `FLATSAT_EXAMPLE.md` and the notes for agents where they count or list the examples |

And with them: one test module (`tests/test_feature_examples.py`), one end-to-end test (`tests/test_e2e_510.py`), the API snapshot made again on purpose for the new field of `TemplateInfo`, and two requirements (REQ-EX-01: every template passes `check`, `drc`, `export` and `verify --outputs` with the findings its page names; REQ-EX-02: every feature of the catalogue names a template).

### 1.2 Not in scope

- **A change of the project format.** No template needs a key of format 6 (section 8).
- **A change to the five existing examples.** Their builders, names, titles and files stay; `tools.output_hashes` and `tools.numbers_snapshot` keep their four examples and their baselines, so no written file of an existing example changes.
- **A template for a feature that needs another project or another person** (section 3.2): the upgrade of a project in an older format, `merge-fix` after a Git merge, `compare` of two folders, a Python plug-in that is trusted (the trust is kept in the user's own settings folder, not in the project), a standard profile (its values are a standard's, D-11, D-131). The manual's steps stay the way to see them.
- **A template that ships an open error.** `drc` exits 1 while an error is open; a template that does is a template that fails its own test. An error is shown only accepted as a deviation (`overrides-and-deviations`).
- **A template with a change journal.** A journal holds who and when (`journal.jsonl`); the builders write none, so that the shipped files do not depend on the time or on who ran them (as `create_project` documents today). `new` starts one in the copy, as for every template.
- **Screenshots of each template.** `tools.gui_screenshots` and `tools.flatsat_screenshots` stay as they are.

## 2. What exists at 5.0.0

### 2.1 The templates and who lists them

`core/templates.py` holds `TEMPLATES`, a tuple of `TemplateInfo(name, title, summary)` in the order of `new --list`, and `create_project(dest, template, name=None, *, journal=False, annotate_config=False)`: it loads `resources/examples/projects/<name>/`, refuses a damaged one, sets the name, annotates the config files when asked, saves the project into `dest` with `save_project`, writes `.gitattributes`, and starts a journal when asked. **It copies the model, not the folder**: a file of the template folder that is not part of the project (`extensions/`, `device-libraries.json`, a library folder, `outputs/`) does not reach the copy.

`tools/build_examples.py` holds `PROJECTS` (the same titles and summaries a second time, with *units* where `TEMPLATES` says *devices*) and `BUILDERS` (five functions; `_flatsat` with `_demo_values` and `_demo_lengths`); `build()` writes each folder next to the old one and swaps it in. `core/samples.py` holds `new_project` (segmentation `per_connector_pair`: the base of every example but `blank`; `_flatsat` then sets `per_zone_pair`), `start_project` (`per_connector_group` and the label format `harness_device_connector`, the start of a new project, D-247) and `sat15`.

Every user of the list, found with `grep -rn TEMPLATES`:

| Where | What it does with the list |
|---|---|
| `cli/start.py` | `new --list` prints `f"{t.name:18} {t.summary}"`, a fixed column of 18 characters; the help of `new` names the five templates in a string of its own (*create a new project from an example (blank, first-steps, minimal-satellite, small-satellite, flatsat)*), so `docs/CLI.md`, made from the help, names them too |
| `core/records.py` `template_infos`, `api.list_templates` | the list for `new --list --json` and the scripting interface (`TemplateInfo` in `tests/fixtures/api_snapshot.json`) |
| `gui/new_project_dialog.py` | one `QListView` row per template (`template_title`: *Empty project* for `blank`), its summary as the tooltip and under the list; `setMinimumHeight(theme.px(130))` |
| `gui/pages.py` `_example_infos` | the Home page: one card row per example but `blank` (title, summary, a button *Open this example*; `flatsat` gets the primary button *Try the flatsat example*) |
| `gui/main_window.py` `new_from_example_flow` | opens the dialog with the first template that is not `blank` ticked |
| `tests/test_examples.py`, `tests/test_merge_fix.py` (`test_every_example_ships_the_gitattributes`), `tests/test_new_project_labels.py` | every listed template exists, loads without errors, has its title as name, ships `.gitattributes`, starts in the label format of its kind; the shipped folders are what the builder writes |
| `tests/test_docs.py` | the `new --list` output quoted in `GETTING_STARTED.md` is what the tool prints; `docs/examples/README.md` quotes real runs of the five |

### 2.2 What the five examples hold

Counted with a throw-away script on the shipped folders, and again after `generate` in memory:

| Example | Segmentation | Devices, box connectors, pins | Pins with a signal (shipped) | Full connectors after Generate | Harnesses after Generate, branch points | Links, waivers, baselines, import records, as-built records, accessories |
|---|---|---|---|---|---|---|
| `blank` | `per_connector_group` | 0, 0, 0 | 0 | 0 | 0, 0 | all 0 |
| `first-steps` | `per_connector_pair` | 3, 9, 120 | 0 | 0 of 9 | 2, 0 | all 0 |
| `minimal-satellite` | `per_connector_pair` | 7, 37, 595 | 0 | 0 of 37 | 11, 0 | all 0 |
| `small-satellite` | `per_connector_pair` | 14 (2 redundant), 75, 1204 | 0 | 0 of 75 | 24, 0 | all 0 |
| `flatsat` | `per_zone_pair`, 4 lanes | 23, 109, 1789 | 206 (by Generate; 0 fixed) | 2 of 109 (`TRX1-J03`, `RFSU1-J04`: one-pin SMA) | 8 (shipped generated), 12 | all 0 |

No example has a fixed pin, a port, a row layout, a pin current, a depth, a connection, a splice, a place of a shield end, a checked device, a release, an override, a waiver, a deviation, build data, an as-built record, an import record or a Cover of the harness plans. In `flatsat`, on average 17.6 % of the pins of a device connector carry a signal, and 21 of its 109 device connectors carry none: these are the *empty connectors* of the owner's request. The starter library has no splice, backshell or contact part (`library/contact.json` and `library/backshell.json` of `flatsat` hold `"parts": []`); the only `EX-SPLICE-1` is a row of the import template `splice-parts-EXAMPLE.csv` and of `tests/splice_support.py`.

### 2.3 Runs: what the tool does today with the projects a template needs

Each run is on a project built in a scratch folder with the edit functions named, then saved and driven through the command line.

**Full connectors by Generate.** Three devices (`PCDU1`, `OBC1`, `TTC1`), six box connectors of `EX-MICROD-9-F` or `-M`, every pin fixed and named (power: `MAIN_PWR`, `KA_PWR`, `SURV_PWR`, `HTR+`, `GND`, `MAIN_RTN`, `KA_RTN`, `SURV_RTN`, `HTR-`; data: `TX+`, `TX-`, `RX+`, `RX-`, `GND`, `CANH`, `CANL`, `SIG`, `RTN`), the rows `1–5 / 6–9` on both parts (`row_layout_edit.plan_set_row_layout`), fourteen interfaces with both connectors named (`edit.ops_add_interface`: two `power_primary`, one `power_secondary`, one `heater`, one `ground` per power pair; `rs422`, `can`, `discrete`, `ground` on the data pair). `generate` makes 3 harnesses and 27 wires; `check` says `3 devices, 14 interfaces, 12 connectors, 3 harnesses: 0 error(s), 0 warning(s).`; `system/box_pinouts.csv` has `Spare` `no` on all 54 device pins and the column *Pin row*:

```
OBC1-J01,box,,EX-MICROD-9-M,1,MAIN_PWR,IF-002,W001-003,no,1
OBC1-J01,box,,EX-MICROD-9-M,2,KA_PWR,IF-001,W001-001,no,1
```

So a power port is given in name order of the ports, not by the interface: `IF-001`, the first `power_primary`, took the pins `KA_…`, and `IF-002`, the `power_secondary`, took `MAIN_…` (the rule of 2.1.0: *the first free complete named port in natural order*). The builder of `full-connectors` puts each interface on its port with `devices.ops_assign_port` (the *Assign… Port* of the Devices tab). `drc` gives `Open: 0 error(s), 6 warning(s), 4 note(s).`: two `connector-lookalike` (PCDU1-J01 and J02, TTC1-J01 and J02 are the same part with the same keying) and four `part-unapproved`. `export` writes 44 files and `verify --outputs` says `14 interfaces and 27 wires checked: 0 error(s)`.

**A splice drawn by hand.** `start_project`; `EX-SPLICE-1` put in the library (category `splice`, one node, `unverified`, as `tests/splice_support.splice_part`); three devices with `PWR`, `RTN` on pins 1 and 2 of one `EX-MICROD-9-F` each; `manual_harness.plan_new_harness` *Power Y*, a plug on each device connector (`plan_add_connector(mates_with=…)`), two splices (`splices.plan_add_splice`), six wires (`wires.plan_add_wire`), four segments. `check`: `3 devices, 0 interfaces, 8 connectors, 1 harnesses: 0 error(s), 0 warning(s).`; `generate` changes nothing; `export` writes 26 files; `verify --outputs` 0 errors. `drc` shows, beside the part notes, `OBC1 is not connected to anything yet (isolated.OBC1)` for each of the three devices: the note `isolated` counts interfaces and connections and not a harness drawn by hand, and its text says *Units without interfaces get no wires, so they will not appear in any harness plan*, of devices that are in one (section 15, item 1).

**A splice from a connection.** `start_project`, `EX-SPLICE-1`; `PCDU1-J01` with `PWR` 4 A and `RTN` 4 A on pins 1 and 2, `OBC1-J01` with `PWR` on pins 1 and 2 and `RTN` on 3 and 4, 2 A each (`Pin.current_a`); `links.plan_add_link(p, "PCDU1-J01", "OBC1-J01", [("1","1"), ("1","2"), ("2","3"), ("2","4")])`. `plan_create_harness` without a part refuses: *Link L1 joins pin 1 of PCDU1-J01 to 2 pins of OBC1-J01. Choose a splice part (category splice) for the joint; the harness gets one splice for each junction.* With `EX-SPLICE-1` it makes W001 with `W001-X1` and `W001-X2`; `routing DIR W001` lists `node 1: W001-001, W001-002, W001-003`. `check` 0 errors; `export` 28 files; `verify --outputs` 0 errors. With pins named `SPARE3` … on the other pins, `drc` gives one `link-unpaired` warning for each: the template leaves the unused pins without a name.

**A release.** A copy of `first-steps` with `config-demo-values`, segment lengths of 1200 and 900 mm (a table in the form of `segment-lengths.csv`, by `import-lengths`), `generate`, `export`: `release` of W001 is blocked by `gauge_pending` (the RS-422 wires get no gauge: their interface has no current), so the page *Release a harness* releases W002, the power harness. `review DIR W002 --by "Designer 1" --date 2026-11-24` and `release DIR W002 --by "Checker 1" --comment … --date 2026-11-24 --accept-placeholders … --accept-unapproved-parts …` say `Release W002 version 1.0.0: done.` and write `baselines/W002/W002.1.0.0.json`, `changelog.json` and the harness file; none holds the tool version, and with `--date` none holds today. Saved again without `outputs/` and loaded and saved into a new folder with another name and annotated config files (what `new --name … --annotate-config` does), `check` gives 0 errors and `drc` 0 errors: a released template survives `new`. The release gate needs exported outputs (`outputs_missing`; `vcs.release.plan_release(…, outputs_folder=…)`), so the builder exports into a scratch folder first.

**A branching harness.** `start_project`; `computer`, `transceiver`, `actuator` and `power` devices; RS-422 from `OBC1-J03` to `TRX1` and to `RW1`, power from `PCDU1-J01` to `OBC1` and to `TRX1`. `generate` makes `W001` (`PCDU1-J01` to `OBC1-J02` and `TRX1-J01`, branch point `W001-B1`) and `W002` (`OBC1-J03` to `RW1-J02` and `TRX1-J02`, branch point `W002-B2`); `export` 37 files, `verify --outputs` 0 errors, `drc` nothing beyond the part notes. The branch points are numbered across the project (`W002-B2`, not `W002-B1`).

**A loose cable end.** `start_project`, a computer device, `PWR` and `RTN` on `OBC1-J02`, `manual_harness.plan_cable_from_port(p, "OBC1-J02", name="Bench supply cable")`: W001 with the plug `W001-P1` and the loose end `W001-P2`; `check` 0, `export` 26 files, `verify --outputs` 0 errors; `drc` gives `isolated.OBC1` (the same fault).

**Shield ends.** A copy of `first-steps` with `config-demo-values`, `settings --set generation.shield_end_a="pigtail" --set generation.shield_end_b="backshell_360"`, lengths, `generate`: `check` says `INFO shield_place_not_stated: W001-S1: where the pigtail at W001-P1 lands is not stated.` and the same for `W001-S2` *at W001-P2*: the two pairs of one harness have their end A at different connectors, since end A is the `from` end of a group's lowest wire. A table of shield ends (`Harness,Shield group,End,Pin` with pins 9 and 10) read by `import-build-data` says `2 added, 0 changed, 0 unchanged, 0 refused.` and the infos are gone; `export --harness-plan` writes 37 files and `verify --outputs` 0 errors.

**Overrides and deviations.** On a copy of `first-steps` with `config-demo-values`, `override DIR W002-001 gauge_awg 20 --reason …` sets the gauge and prints its derivation; `drc` then has one error, `verify-mismatch.outputs_outdated` (*The model changed after the harness plans were generated. Generate again before releasing.*) until `generate` runs again: the builder generates after each override. A long run does not give a `voltage-drop` error by itself: with W002-L1 at 12 m, `generate` says `error: [wire_sizing] W002-001: no listed gauge keeps the voltage drop under 0.5 V over 12.1 m.` and `Not saved: fix the errors above first.`, because Generate's gauge search takes the drop into account. At 2 m Generate gives AWG 22; `override DIR W002-001 gauge_awg 24 --reason …` and `generate` make two errors, *Wire W002-001 (AWG 24) carries 2 A but allows 1.44 A after derating* (`current-over-wire.W002-001`) and *Wire W002-001 drops 0.706 V, more than the 0.5 V limit* (`voltage-drop.W002-001`); `deviation DIR current-over-wire.W002-001 --reason …` and the same for `voltage-drop` record two deviations, and `drc` says `Open: 0 error(s), 10 warning(s), 6 note(s). Waived: 0. Deviations: 2.` and exits 0. With a second power interface from `PCDU1-J02`, both identical power connectors of PCDU1 are in use and `drc` gives `connector-lookalike.PCDU1-J01` (with one in use, as in `first-steps`, it does not).

**A device library inside the project.** A copy of `first-steps`, a folder `team-library/` in it, `save-device DIR RW1 --library DIR/team-library`, `libraries DIR --add team-library` (the file `device-libraries.json` with the path `team-library`), `device-checked DIR RW1 --by "Reviewer 1" --icd "ICD-RW EXAMPLE Issue 1" --date 2026-11-24`, `update-device DIR RW1`: all work, and `check` gives 0 errors. But `create_project` would not copy `team-library/` or `device-libraries.json` (2.1).

**Each run that ran `check` got 0 errors, and each that ran `export` got 0 errors from `verify --outputs`** (the run at 12 m aside, which Generate refused to save). What `drc` adds to every project built from example parts and placeholder files: one `part-unapproved` warning per `EX-` part in use (the parts are never approved in an example, D-129), the notes `unchecked-config.*` for each placeholder value a rule needs, and `unconfirmed` for each interface whose connectors the tool chose. These are the *baseline findings* of section 5.3.

### 2.4 How the list looks today

```
harness-design-studio new --list
```

```
blank              An empty project: starter parts and interface types, no devices.
first-steps        Three devices, a power link and an RS-422 link. Nothing is generated yet: start here.
minimal-satellite  Seven devices, nominal only: power, computer, radio, wheel and sun sensor. Adapt it.
small-satellite    14 devices with nominal and redundant chains. Generate it to see a realistic system.
flatsat            A complete bench: 23 flight and ground devices, generated, with example numbers.
```

The name column is 18 characters wide; `overrides-and-deviations` has 24, `build-data-and-as-built` 23 and `splice-from-connection` 22, so their summaries would start out of line. The New project dialog, measured offscreen at its default size (the theme's default scale), shows a list 304 pixels high with rows of 15 pixels: about 20 rows, so nineteen entries fit without a scroll bar there, in one flat list without a word about which one to start from. The Home page shows one row per example (four today, a title, a summary and a button each); nineteen rows push the card far below the fold. Nobody has looked at either on a real display.

### 2.5 Size today

The five shipped folders hold 157 files and 1,543,240 bytes (`blank` 25,106; `first-steps` 56,988; `minimal-satellite` 179,330; `small-satellite` 338,001; `flatsat` 943,815); on disk, in blocks of 4 KiB, about 2.2 MB. A zip of them (one deflate per file, as a wheel stores them) is 92,834 bytes. The six projects of the runs of 2.3 that stand for the new templates (without `outputs/`) hold 23 to 34 files and 38,951 to 100,454 bytes each; their zip is 69,900 bytes. Section 7.2 has the estimate.

### 2.6 What a template cannot carry today

- **Files beside the model**: `extensions/`, `device-libraries.json` and a library folder (2.1). `device-libraries.json` is *not part of the project format: the loader does not read it, a save does not write or delete it* (`core/library_pointer.py`); `extensions/` is read by the loader (`core/extensions/attach`) and written by nobody.
- **A journal** (by choice, 1.2), so the deviation of a template shows no *who and when*, and `journal DIR` of the copy starts with *New project from the example '…'*.
- **A waiver from the command line**: no command waives a warning; the builder uses `checks.waive_op`, as the editor does.
- **An interface or a device drawn from the command line**: no command adds one (a known gap, *command-line versions of the new edits*); the builders call the edit functions, as `_flatsat` does.

## 3. The feature catalogue

### 3.1 Every feature and its template

The features are those of the 37 pages of the user manual (`docs/user-manual/*.md` without the index), the 43 design rules and the four logical rules of [`RULES.md`](../RULES.md), the fields of format 5 ([`FILE_FORMAT.md`](../FILE_FORMAT.md)) and the commands of [`CLI.md`](../CLI.md). *Today* is what a person can open and see after `new` (and `generate` where that is the next step); *5.1.0* is where the feature is shown after this design. A template in bold is new.

| # | Feature | Manual page | Today | 5.1.0 |
|---|---|---|---|---|
| 1 | Roles, the Next step page | [Choose your role](../user-manual/choose-your-role.md) | every example | `first-steps` (a view of the editor, not of a project) |
| 2 | Quick mode, *Export diagram* (SVG, PDF, PNG) | [Quick diagram](../user-manual/quick-diagram.md) | every example | `first-steps`, `minimal-satellite` (no new template: a quick diagram is devices and interfaces, which these are) |
| 3 | Devices, interfaces, lanes, guided and expert mode | [Draw the design](../user-manual/draw-the-design.md) | `first-steps`, `minimal-satellite` | the same |
| 4 | Device looks and the *Kind* | [Telling devices apart](../user-manual/telling-devices-apart.md) | `flatsat` (13 device templates), `minimal-satellite` | the same |
| 5 | Redundant copies, `cross-strap`, zones and lanes | [Redundancy and zones](../user-manual/redundancy-and-zones.md) | `small-satellite` (2 redundant devices), `flatsat` (4 lanes) | the same |
| 6 | Generate: preview, apply, undo, self-check; segmentation `per_connector_pair`, `per_zone_pair` | [Generate harnesses](../user-manual/generate-harnesses.md) | `first-steps`, `flatsat` | the same |
| 7 | Segmentation `per_connector_group` (the start of a new project) | [Generate harnesses](../user-manual/generate-harnesses.md), [Branching harnesses](../user-manual/branching-harnesses.md) | `blank` (empty) | **`branching-harness`** |
| 8 | Findings, fixes, `drc` | [Read and fix problems](../user-manual/read-and-fix-problems.md) | every generated example | the same |
| 9 | A waiver of a warning | [Read and fix problems](../user-manual/read-and-fix-problems.md) | none | **`overrides-and-deviations`** |
| 10 | Engineering values, `config`, demo values | [Fill in the engineering values](../user-manual/fill-in-engineering-values.md) | `flatsat` (EXAMPLE values), `templates/config-demo-values/` | `flatsat` and every new template with numbers (5.2) |
| 11 | Standard profiles (`config --apply-profile`) | [Fill in the engineering values](../user-manual/fill-in-engineering-values.md) | none | none (3.2) |
| 12 | Settings, assumptions, `explain`, the selectable models | [See what the tool assumes](../user-manual/see-what-the-tool-assumes.md) | every example (defaults) | **`lengths-to-the-face`** (`model.length_model` `path_loops_allowance_twist`) |
| 13 | `override`, `deviation`, the journal | [Override a value and keep a history](../user-manual/override-and-keep-a-history.md) | none (journal: started by `new`) | **`overrides-and-deviations`** |
| 14 | The current rules with values (`current-over-wire`, `bundle-current`, `voltage-drop`, `current-over-contact`) | [Fill in the engineering values](../user-manual/fill-in-engineering-values.md) | `flatsat` | `flatsat`, **`overrides-and-deviations`** (a `current-over-wire` and a `voltage-drop` error accepted) |
| 15 | Imports: interfaces (app), parts, lengths, build data; the import record, `imports` | [Import data](../user-manual/import-data.md) | none (the import templates, applied by hand) | **`imports-from-files`** |
| 16 | KiCad netlist, fixed pins, `--signal-map` | [Import KiCad pinouts](../user-manual/import-kicad-pinouts.md) | `wheel-connectors.net`, applied by hand to `first-steps` | **`imports-from-files`** |
| 17 | A device: pins, signals, roles, directions, levels, *Fill*, fixed pins, `import-pinout`, `export-pinout` | [Define a device](../user-manual/define-a-device.md) | none (no pin has a signal before Generate) | **`full-connectors`**, **`imports-from-files`** (a pinout) |
| 18 | **Fully populated device connectors** | [Define a device](../user-manual/define-a-device.md) | none (2 one-pin connectors of `flatsat`) | **`full-connectors`** |
| 19 | Ports (a named port, *Assign… Port*) | [Define a device](../user-manual/define-a-device.md) | none | **`full-connectors`**, **`names-and-ports`** |
| 20 | Ports named after the far device (`naming.far_device_names`), the signal map (`naming.signal_map`) | [Define a device](../user-manual/define-a-device.md), [Connect two connectors](../user-manual/connect-two-connectors.md) | none | **`names-and-ports`** |
| 21 | The row layout of a connector, the *Pin row* column, `pin-rows` | [Pin rows of a connector](../user-manual/pin-rows-of-a-connector.md) | none | **`full-connectors`** |
| 22 | A connection (link): pairing, roles, *Check my connections*, *Create harness*, the connection list | [Connect two connectors](../user-manual/connect-two-connectors.md) | none | **`splice-from-connection`** (one link without and one with a junction) |
| 23 | Wires drawn by hand, several wires on one pin, twisting, labels, pin function | [Edit a wire](../user-manual/edit-a-wire.md) | `flatsat` (generated wires only) | **`splice-by-hand`**, **`overrides-and-deviations`** |
| 24 | Wire colours (`wire_colour_by_signal`, a colour on a drawn wire) | [Set wire colours](../user-manual/set-wire-colours.md) | `flatsat` | `flatsat`, **`splice-by-hand`** |
| 25 | A harness built by hand | [Build a harness by hand](../user-manual/build-a-harness-by-hand.md) | none | **`splice-by-hand`** |
| 26 | The electrical rules of drawn wires (`wire-direction`, `level-conflict`) | [Build a harness by hand](../user-manual/build-a-harness-by-hand.md) | none | **`splice-by-hand`** (pins with directions and levels; the rules quiet; the page's steps make them speak) |
| 27 | A cable with a loose end, *Plug in*, a new leg, `release --accept-loose-ends` | [Build a harness by hand](../user-manual/build-a-harness-by-hand.md), [Branching harnesses](../user-manual/branching-harnesses.md) | none | **`loose-cable-end`** |
| 28 | Branch points, segments, the *Routing* table, `routing` | [Branching harnesses](../user-manual/branching-harnesses.md) | `flatsat` (12 branch points) | `flatsat`, **`branching-harness`** |
| 29 | *Join into one harness* | [Branching harnesses](../user-manual/branching-harnesses.md) | none | none (3.2) |
| 30 | **A splice drawn by hand** (a splice part, *Add splice*, *Splice this wire*, the column *Via*, the tests through a splice) | [Splices](../user-manual/splices.md) | none | **`splice-by-hand`** |
| 31 | **A splice from a connection** (a junction, format 5) | [Splices](../user-manual/splices.md), [Connect two connectors](../user-manual/connect-two-connectors.md) | none | **`splice-from-connection`** |
| 32 | A current per pin (`current_a`), the current of a wire from its pins | [Define a device](../user-manual/define-a-device.md) | none | **`splice-from-connection`** |
| 33 | Lengths to the face (`model.length_reference`, `length_to`), depths (`depth_mm`) | [Lengths to the face](../user-manual/lengths-to-the-face.md) | none | **`lengths-to-the-face`** |
| 34 | Strip lengths, contacts and crimp tools, accessories | [Enter the build data](../user-manual/enter-the-build-data.md) | none | **`build-data-and-as-built`** |
| 35 | Shield groups, the grounding concept, where a shield end lands (`at_a`, `at_b`) | [Enter the build data](../user-manual/enter-the-build-data.md) | `flatsat` (60 groups; 28 ends `backshell_360` with no backshell) | **`shields-and-ends`** |
| 36 | The build workbook, the PDF drawings, the system files | [Export the outputs](../user-manual/export-the-outputs.md) | every generated example | every template |
| 37 | The harness plans (`.ods`), `document` (the Cover), the colour code by pin, the *Production* sheet | [Export the harness plans](../user-manual/export-the-harness-plans.md) | every generated example (no Cover, no colour code) | **`build-data-and-as-built`** |
| 38 | Name patterns, label formats, the title block | [Naming and title block](../user-manual/naming-and-title-block.md) | `blank` (`harness_device_connector`), the others `standard` | **`build-data-and-as-built`** (title block), **`released-harness`** (author, checker) |
| 39 | Review, release, the gates, the review checklist and its ticks, different people | [Release a harness](../user-manual/release-a-harness.md) | none | **`released-harness`** |
| 40 | A new version, `diff`, `log`, the version report | [Change a released harness](../user-manual/change-a-released-harness.md), [Versions](../user-manual/versions.md) | none | **`released-harness`** |
| 41 | `compare` of two folders | [Change a released harness](../user-manual/change-a-released-harness.md) | none | none (3.2) |
| 42 | `.gitattributes`, `check`, a CI script | [Use Git and CI](../user-manual/use-git-and-ci.md) | every example | every template |
| 43 | `merge-fix` | [Use Git and CI](../user-manual/use-git-and-ci.md) | none | none (3.2) |
| 44 | The device library: a library folder, `add-device`, `update-device`, `save-device`, a number of the same device, subsystems | [Use the library](../user-manual/use-the-library.md) | none | **`device-library`** |
| 45 | The checked state of a device (`device-checked`) | [Use the library](../user-manual/use-the-library.md) | none | **`device-library`** |
| 46 | `--json`, the Python interface | [Script the tool](../user-manual/script-the-tool.md) | every example; `docs/examples/scripting/` | the same |
| 47 | `export-data`, the run record | [Export the data](../user-manual/export-the-data.md) | every example; `docs/examples/open-data/` | the same |
| 48 | Extensions: a data rule, a table, a Python plug-in, `extensions`, `trust` | [Extend the tool](../user-manual/extend-the-tool.md) | `docs/examples/extensions/` (copied by hand) | **`extensions`** (the plug-in stays untrusted) |
| 49 | `workflow` | [Follow the workflow](../user-manual/follow-the-workflow.md) | every example | the same |
| 50 | The as-built record (`export-asbuilt`, `import-asbuilt`, `asbuilt`) | [Record what was built](../user-manual/record-what-was-built.md) | `flatsat`, by the page's steps | **`build-data-and-as-built`** (a record shipped) |
| 51 | `migrate`, the editor's upgrade question | [Upgrade a project](../user-manual/upgrade-a-project.md) | none | none (3.2) |
| 52 | What the tool is, for safety, quality and IT | [Using HDS in your organisation](../user-manual/use-hds-in-your-organisation.md) | — | — (not a feature of a project) |
| 53 | The rules of mating halves, look-alike connectors, spare pins, the pin gaps | [Read and fix problems](../user-manual/read-and-fix-problems.md), [`RULES.md`](../RULES.md) | `flatsat` (`connector-lookalike`) | **`full-connectors`** (keying, and two exercises: `spare-pins-low` and `power-return-adjacent` speak once their values are set) |
| 54 | `schema`, `templates`, `new --annotate-config` | [`CLI.md`](../CLI.md) | every example | the same |

### 3.2 What no template shows, and why

- **Standard profiles** (row 11): a template with a profile applied would carry a standard's values in its files (D-11, D-131); the profiles fill unset values when a person asks.
- **`merge-fix`** (row 43) needs two Git branches that both pressed Generate; `tests/test_merge_fix.py` makes real merges and the page shows the steps.
- **`compare`** (row 41) compares two folders; `released-harness` holds one, and the page compares it with a copy.
- **`migrate`** (row 51): `create_project` writes the current format, so a template in format 4 would arrive as format 5; the fixtures of `tests/fixtures/projects/` and `tests/migration_support.as_format` hold older formats for the tests.
- ***Join into one harness*** (row 29): a join needs two harnesses drawn by hand that plug into one device connector; the page's steps draw a second cable from `OBC1-J03` on a copy of `loose-cable-end` and join the two. A template already joined would show the result, not the feature.
- **A trusted plug-in** (row 48): the trust is per user and per SHA-256, kept in the user's settings folder; `extensions` ships the plug-in untrusted, and `trust` is the exercise.
- **An open error** (1.2): `wire-direction` and `level-conflict` are errors; `splice-by-hand` gives its pins directions and levels that fit, and the page *Build a harness by hand* makes the rules speak on a copy.

## 4. The new templates

Each subsection says: the devices and their connectors, the interfaces or connections, what is generated or drawn, what the user looks at and on which manual page, how the builder makes it, the shipped state and the findings `drc` shows beyond the baseline of 5.3. Every builder is a function of `tools/feature_examples.py` that takes nothing and returns a `Project`, written with `History(p).execute(…)` around the edit functions, as `_flatsat` is. *EXAMPLE values* means the four files of `templates/config-demo-values/` copied into the project's config (the builder reads them from `resources/examples/templates/`, so there is one copy of the numbers), every file still `"placeholder": true`.

### 4.1 `full-connectors`: every pin used

- **Title** *Full connectors*; **summary** *Three devices whose connectors have a signal on every pin: fixed pinouts, ports and pin rows; generated.*
- **Devices** `PCDU1` (Power control unit), `OBC1` (On-board computer), `TTC1` (Transceiver), placed by hand on two lanes.
- **Connectors**, all `EX-MICROD-9-F` or `-M`, every pin fixed and named, no spare, nine pins each (section 2.3, run): `PCDU1-J01` and `-J02` (keying `A` and `B`), the power outputs to OBC1 and TTC1; `OBC1-J01` and `TTC1-J01`, the power inputs; `OBC1-J02` and `TTC1-J02` (keying `A` and `B` on TTC1), the data link. Power pins in ports `MAIN`, `KA`, `SURV` (`MAIN_PWR` … `SURV_RTN`), `HTR+`, `HTR-`, `GND`; data `TX+`, `TX-`, `RX+`, `RX-`, `GND`, `CANH`, `CANL`, `SIG`, `RTN`. Roles from the names; `Direction` on the data pins (`TX±` out on OBC1, in on TTC1). The rows `1–5 / 6–9` on both parts (`pin-rows --to-part`), so every device connector reads its rows from its part; the power returns on row 2 under their power pins.
- **Interfaces** (14), each with its two connectors named (no `unconfirmed`) and each put on its port with `devices.ops_assign_port` (the run of 2.3 shows why).
- **Shipped generated**: 3 harnesses, 27 wires, every pin of the six device connectors used; segmentation `per_connector_pair` (`new_project`: one harness per pair of connectors makes the three harnesses easy to read).
- **Look at**: the Devices tab (every pin named, the mode *Fixed*, the port column), `system/box_pinouts.csv` (`Spare` `no` everywhere, *Pin row* 1 or 2), the *Pin row* column of the harness plan, `pin-rows DIR OBC1-J01`, the Production sheet of W001. Pages: *Define a device*, *Pin rows of a connector*.
- **Exercises** on the page: `settings DIR --set derating.spare_pin_fraction=0.1` makes `spare-pins-low` name all six connectors (a full connector has no spare); `--set generation.power_return_gap_pins=1` makes `power-return-adjacent` read the rows.
- **Findings beyond the baseline**: none (the keying takes away the two `connector-lookalike` of the run; pull request 1 confirms that the cable connectors take the keying and `mate-mismatch` stays quiet).

### 4.2 `names-and-ports`: the far device in the pin name

- **Title** *Names and ports*; **summary** *OBC1 talks to TTC1 and TTC2 on one connector; its ports are named after them, and a signal map reads the team's words.*
- **Devices** `OBC1`, `TTC1`, `TTC2` (the case of the design of 4.4.0, section 2.1).
- **Connectors** `OBC1-J01` (`EX-MICROD-9-F`): pins 1 to 8 fixed `TTC1_TX+ TTC1_TX- TTC1_RX+ TTC1_RX- TTC2_TX+ TTC2_TX- TTC2_RX+ TTC2_RX-`, pin 9 role `spare`; `TTC1-J01`, `TTC2-J01`: `TX+ TX- RX+ RX-` and a spare. The pinouts of TTC1 and TTC2 are read by `pinout_import.plan_pinout_import` from tables in the team's words (`TXP`, `TXN`, `RXP`, `RXN`) through the project's signal map (`naming.signal_map` from the import template `signal-map.csv`), so the import records list the renames.
- **Interfaces** two RS-422, made OBC1 to TTC2 first (IF-001), then OBC1 to TTC1, as in the run of 4.4.0, with `naming.far_device_names` on.
- **Shipped generated**: IF-001 on the pins `TTC2_…`. `config DIR --far-device-names off` and `generate` on a copy give IF-001 the pins `TTC1_…` (the first free port in name order), and `verify` names the mismatch (`port_far_device`): the lesson of the template.
- **Look at**: the pin table of OBC1-J01, `explain DIR IF-001`, `imports DIR` (the renames), `config DIR` (the two settings). Pages: *Define a device*, *Connect two connectors*, *Import KiCad pinouts* (the signal map).
- **Findings beyond the baseline**: none.

### 4.3 `splice-by-hand`: a power Y drawn by hand

- **Title** *Splice by hand (EXAMPLE)*; **summary** *A power line drawn by hand from one output to two devices through two splices of an EXAMPLE part.*
- **Devices** `PCDU1`, `OBC1`, `TTC1`; one `EX-MICROD-9-F` each with `PWR` and `RTN` on pins 1 and 2 (roles power and return, direction set), the other pins without a name.
- **Library**: `EX-SPLICE-1` (category `splice`, one node, manufacturer *Example Co.*, description *Crimp splice, one node (EXAMPLE ONLY: not a real part)*, `unverified`), the row of `splice-parts-EXAMPLE.csv`.
- **Drawn**: harness W001 *Power Y* (`manual_harness.plan_new_harness`), a plug on each device connector (`plan_add_connector(mates_with=…)`), two splices `W001-X1` (PWR, crimp) and `W001-X2` (RTN, crimp) (`splices.plan_add_splice`), six wires with a gauge (AWG 22 to the splice, AWG 24 beyond it), the colours red and black (`wires.plan_add_wire`), and four segments with EXAMPLE lengths (0.4, 0.02, 0.6 and 0.8 m) so that each splice is a node of the routing tree. No interface: Generate makes nothing (`0 added, 0 changed`).
- **Look at**: the *Splices* list of the Harness tab, the column *Via* of the wire list, the splice block of the build workbook, the tests through a splice in `tests.csv`, `routing DIR W001`, `explain DIR W001-002`. Pages: *Splices*, *Build a harness by hand*, *Edit a wire*.
- **Findings beyond the baseline**: none once part E (`isolated`) is in; today three `isolated` notes (2.3).

### 4.4 `splice-from-connection`: a junction and the currents of its pins

- **Title** *Splice from a connection (EXAMPLE)*; **summary** *A connection that joins one pin to two (a junction), with pin currents; its harness carries the splices.*
- **Devices** `PCDU1`, `OBC1`.
- **Connectors**: `PCDU1-J01` (`EX-DSUB-9-F`): `PWR` 4 A on pin 1, `RTN` 4 A on pin 2; `OBC1-J01` (`EX-MICROD-9-M`): `PWR` on pins 1 and 2 and `RTN` on pins 3 and 4, 2 A each (`Pin.current_a`, EXAMPLE numbers, written as the ICD of a device that splits a line over two smaller contacts). `PCDU1-J02` and `OBC1-J02`: `TX+ TX- RX+ RX-` for the second connection. Unused pins have no name (the run of 2.3: a named pin that no pair uses is `link-unpaired`).
- **Connections**: L1 *Power of OBC1*, the pairs `(1,1) (1,2) (2,3) (2,4)` (two junctions); L2 *Data of OBC1*, the four pairs proposed by name (`links.propose_pairs`).
- **Harnesses**: W001 from L1 with `EX-SPLICE-1` (`links.plan_create_harness(p, "L1", "EX-SPLICE-1")`: `W001-X1`, `W001-X2`); W002 from L2 (no splice). Gauges set on the wires of W001 (AWG 22 trunk, AWG 24 branches, `wires.plan_wire_edit`), so the current rules judge them.
- **Values**: EXAMPLE values; `contact_current_a` 10 on `EX-DSUB-9-F` and 5 on `EX-MICROD-9-M` (EXAMPLE ratings; with the factor 0.75 of the demo values, `derating.contact_current_factor`: 7.5 A and 3.75 A per contact), so each OBC1 contact (2 A) passes and a single OBC1 contact would not carry the whole 4 A: the reason for the split.
- **Shipped**: the two harnesses made; Generate makes nothing (no interface).
- **Look at**: the Link window (the junction), the connection list (`system/connections.csv`), *Check my connections* (`link_junction`, an info), the *Splices* list with the pin currents of each node, `explain DIR W001-001` (4 A on the trunk) and `W001-002` (2 A on a branch), `system/box_pinouts.csv` (*Current (A)*). Pages: *Connect two connectors*, *Splices* (from a link), *Define a device* (currents).
- **Why pin currents are here and not in a template of their own**: the junction exists because a line is split over contacts; the pin currents are what says the split is right, and the example of the design of 5.0.0 (section 5.2) is this harness. A template of pin currents alone would repeat it without the splice.
- **Findings beyond the baseline**: none (pull request 2 runs `drc` with the EXAMPLE values and lists the notes of the current rules, for example `voltage-drop-wires`: a wire without an interface type gets no voltage drop, item 10 of section 19 of the design of 5.0.0).

### 4.5 `branching-harness`: one connector, two devices

- **Title** *Branching harness (EXAMPLE)*; **summary** *Four devices; Generate makes harnesses that branch where one connector serves two devices.*
- **Devices** `OBC1` (computer), `TRX1` (transceiver), `RW1` (wheel), `PCDU1` (power); `start_project`, so `per_connector_group`.
- **Interfaces**: RS-422 from `OBC1-J03` to TRX1 and to RW1; power from `PCDU1-J01` to OBC1 and to TRX1 (the run of 2.3).
- **Shipped generated**, with EXAMPLE segment lengths (by `branching.plan_set_segment_length`): W001 with `W001-B1`, W002 with `W002-B2`.
- **Look at**: the Harness tab's *Routing* table, `routing DIR W002`, `segments.csv`, the *Routing* and *Segments* sheets, `explain DIR W002-001` (the path through the branch point). Page: *Branching harnesses*.
- **Findings beyond the baseline**: none.

### 4.6 `loose-cable-end`: a cable with nothing on its far end yet

- **Title** *Loose cable end*; **summary** *A cable from a port with its far end loose, and a leg added to it; a release asks for a reason.*
- **Devices** `OBC1`, `PCDU1`; one power interface, generated (W001).
- **Drawn**: W002 *Bench cable* from `OBC1-J03` (a 15-way Micro-D; `TM+`, `TM-`, `TC+`, `TC-` on pins 1 to 4) with its far end loose (`manual_harness.plan_cable_from_port`), then a leg of pins 3 and 4 (`branching.plan_add_leg`): a branch point and a second loose end. The loose ends have the part `TBD-CONNECTOR`.
- **Look at**: the tree and the Inspector (*loose end*), *Edit > Cable ends*, *Plug in* (`manual_harness.propose_plug`), `release DIR W002 …` blocked until `--accept-loose-ends REASON`. Pages: *Build a harness by hand* (A cable with a loose end), *Branching harnesses* (a new leg), *Release a harness*.
- **Findings beyond the baseline**: none (OBC1 has an interface, so no `isolated`).

### 4.7 `shields-and-ends`: where a shield lands

- **Title** *Shields and their ends (EXAMPLE)*; **summary** *A grounding concept, shield groups, pigtails landed on pins and 360-degree ends on backshells.*
- **Devices** `OBC1`, `TTC1`, `RW1`; RS-422 OBC1 to TTC1 and CAN OBC1 to RW1 (shielded pairs). No coax: none of the three carries RF in the starter device kinds, and the coax rule (both ends 360 degrees, `COAX_SHIELD_END`) is shown by `flatsat` (TRX1 to RFSU1).
- **Values**: EXAMPLE values with `generation.shield_end_a` `pigtail` and `shield_end_b` `backshell_360` (an EXAMPLE grounding concept: one end by pigtail, the far end bonded all round; still a placeholder).
- **Library**: `EX-BACKSHELL-MICROD` (category `backshell`, EXAMPLE, `unverified`, `depth_mm` 30, also used by `lengths-to-the-face`).
- **Shipped generated**, then: a backshell accessory on each cable connector at end B (`build_data.plan_set_accessory`), the place of each end B on it, and the place of end A of each group but one on a pin of the cable connector whose device pin has the role `shield` (`wires.plan_set_shield_place`); one group is left without a place on purpose.
- **Look at**: the window *Change group*, the shield cell of the Production sheet (*here pigtail to pin 9, far backshell 360 (W001-A1)*), the row of the pin a pigtail lands on, the *Connectors* sheet (*Goes to: pigtail of W001-S1*), `check DIR` (`shield_place_not_stated` for the one group), and that end A of the two pairs of one harness can sit at different connectors (2.3). Page: *Enter the build data* (3a).
- **Findings beyond the baseline**: none in `drc`; one info of `check` (`shield_place_not_stated`), which is the feature.

### 4.8 `lengths-to-the-face`: lengths measured from the mating face

- **Title** *Lengths to the face (EXAMPLE)*; **summary** *Segments measured to the mating face; the depth of each connector and backshell is taken off each wire.*
- **Devices** `PCDU1`, `RW1` (power and RS-422, as in `first-steps`).
- **Values**: EXAMPLE values; `model.length_reference` `face`; `model.length_model` `path_loops_allowance_twist` with EXAMPLE `twist_takeup_fraction` and `cut_allowance_m` (the selectable length model of 1.15.0: two features about one length, so they are together); `depth_mm` on the parts in use (EXAMPLE: 18 mm for a 9-way, 20 mm for a 21-way) by `build_data.plan_set_part_depth`, and on `EX-BACKSHELL-MICROD` (30 mm) as an accessory on W001-P1; W002-P2 set back to `rear` (`set_length_reference`, the table of cable ends).
- **Shipped generated** with EXAMPLE segment lengths.
- **Look at**: the length note (the fifth sentence, *… but at W002-P2 …*), the `(face)` marks of `segments.csv` and the *Routing* sheet, `explain DIR W001-001` (*Path from rear to rear*), `settings DIR`. Exercise: take the depth off `EX-MICROD-21-M` and `check` names `length_depth_missing`. Pages: *Lengths to the face*, *See what the tool assumes*.
- **Findings beyond the baseline**: none.

### 4.9 `released-harness`: a release and its next version

- **Title** *Released harness (EXAMPLE)*; **summary** *A harness reviewed and released with a checklist, then its next version started: diff, log and the version report.*
- **Devices** `PCDU1`, `OBC1`, `RW1` (the devices of `first-steps`, made by the same calls), EXAMPLE values and lengths (`segment-lengths.csv`).
- **Settings**: the review checklist of the template `design-review-checklist.md` (`config --review-checklist`), different people on (`config --distinct-roles on`).
- **Shipped**: generated; W002 (power) reviewed by *Designer 1* on 2026-01-12, released as 1.0.0 by *Releaser 1* with the checker *Checker 1* on 2026-01-15, ticks `1-20`, the two reasons (*EXAMPLE values for learning*, *EXAMPLE parts for learning*); then a new version of W002, kind `minor` (1.1.0, draft) on 2026-01-20 with one change (a segment length), so `diff DIR W002` and `log DIR W002` show something. W001 (RS-422) stays a draft. Fixed dates in the builder (`EXAMPLE_DATES`), not today's.
- **Look at**: `log DIR W002`, `diff DIR W002`, `system/version_report.md`, the *Review* page and sheet, the title block of the drawing, `check` with the released harness frozen (a change to a pin W002 uses is refused). Pages: *Release a harness*, *Change a released harness*, *Versions*, *Naming and title block*.
- **Findings beyond the baseline**: none.

### 4.10 `overrides-and-deviations`: three ways to accept

- **Title** *Overrides and deviations (EXAMPLE)*; **summary** *A value set by hand with its reason, a warning waived and two errors accepted as deviations.*
- **Devices** `PCDU1`, `RW1`, `OBC1` (the devices of `first-steps`), with a second power interface from `PCDU1-J02` to OBC1, so that both identical power connectors of PCDU1 are in use and give the warning `connector-lookalike` (run of 2.3).
- **Values**: EXAMPLE values and lengths (W002-L1 EXAMPLE 2 m).
- **Shipped generated**, then: an override of the gauge of the power wire W002-001 from the AWG 22 Generate chose to AWG 24 (`wires.plan_override`, reason *EXAMPLE: the thinner wire of a bench cable*), generated again, which makes the errors `current-over-wire.W002-001` and `voltage-drop.W002-001`; both accepted as deviations (`change_ops.accept_deviation`, *EXAMPLE: the bench cable carries the load for minutes only*); the `connector-lookalike` of PCDU1 waived (`checks.waive_op`, *EXAMPLE: the two connectors are keyed differently on the real unit*). The run of 2.3 made the same override and deviations from the command line. Generate cannot be made to ship the error by a long run alone: its gauge search refuses (2.3).
- **Look at**: `override DIR` (the list), `deviation DIR` (the deviation, with *who and when* not recorded: the template has no journal; `new` starts one, and every later change is in it), `drc` (one waived warning, two deviations), the *flags* on the wire list. Pages: *Override a value and keep a history*, *Read and fix problems*, *Edit a wire*.
- **Findings beyond the baseline**: the waived `connector-lookalike` and the two deviations, shown as accepted; `drc` says `Deviations: 2.` and exits 0 (run of 2.3).

### 4.11 `device-library`: devices from a library folder

- **Title** *Device library*; **summary** *Devices taken from a library folder in the project: one copy, one checked, one the library has changed.*
- **Folder**: `team-library/` inside the template (a `NAME.device.json` file per device and a subsystem file), and `device-libraries.json` with the path `team-library` (part C copies both).
- **Devices** `OBC1` (from the library, checked: `device-checked` by *Reviewer 1* on 2026-01-15 against *ICD-OBC EXAMPLE Issue 2*), `TTC1` and its copy `TTC2` (*a number of the same device*, `copies.plan_copies`), `PCDU1` (from the subsystem file); the library's `TTC1` has one pin function changed after it was added, so `update-device DIR TTC1` lists a difference and the Library window shows *library changed*.
- **Shipped generated** (RS-422 OBC1 to TTC1 and TTC2, power from PCDU1).
- **Look at**: `libraries DIR`, `libraries DIR --devices`, `update-device DIR TTC1` (and `--apply` on a copy), the Review page's *checked* line, `check` after an edit of OBC1 (`device_check_stale`). Page: *Use the library*.
- **Findings beyond the baseline**: none.

### 4.12 `build-data-and-as-built`: from the design to the bench

- **Title** *Build data and as-built (EXAMPLE)*; **summary** *Strip lengths, contacts, accessories, a pin colour code and a Cover for the plans; then a record of what was built.*
- **Devices** `PCDU1`, `OBC1`, `RW1` (first-steps), EXAMPLE values and lengths, the label format `harness_device_connector`.
- **Library**: `EX-CONTACT-22` (category `contact`, EXAMPLE, `unverified`).
- **Build data**: strip lengths on every wire (`build_data.plan_set_strip`; EXAMPLE 6 mm and 5 mm), the contact `EX-CONTACT-22` on the device pins (the column *Cable contact*) with an EXAMPLE crimp tool on the part (`build_data.plan_set_part_tool`), accessories (sleeving, heat shrink, a label, a backshell; `plan_set_accessory`), the colour code `example` of `pigtail-colour-code-EXAMPLE.csv` for the Micro-D parts (`templates.example_colour_code`, `"example": true`), the Cover (`document`: system *EX-SAT*, title, company *Example Ltd*, two EXAMPLE contact lines; plan number of W001), the title block names.
- **As-built**: a record of W001 read from an EXAMPLE sheet (`asbuilt.plan_asbuilt_import`): measured lengths, a continuity and an isolation value per test, and an EXAMPLE cut-length tolerance (`generation.asbuilt_cut_tolerance_mm`) that one measured length is outside of, so that `asbuilt DIR` shows one value out of its limit.
- **Shipped generated**.
- **Look at**: `export --harness-plan` (the Cover, the colour of each end by its pin, the *Production* sheet, the labels), the *Cut list* and *Connectors* sheets of the build workbook, `export-asbuilt`, `asbuilt DIR`. Pages: *Enter the build data*, *Export the harness plans*, *Export the outputs*, *Naming and title block*, *Record what was built*.
- **Why together**: the build data is what the bench builds from, and the as-built record is what it reports back about the same harness; one project follows one harness from the drawing to the bench, the way the AIT engineer's role reads it.
- **Findings beyond the baseline**: none in `drc`; `asbuilt` names the one value out of its limit (the release gate `asbuilt` would ask for `--accept-asbuilt`).

### 4.13 `imports-from-files`: a project made from files

- **Title** *Imports from files (EXAMPLE)*; **summary** *first-steps built from the import templates: parts, lengths, build data, a netlist and a pinout, each import recorded.*
- **Devices** `PCDU1`, `OBC1`, `RW1` (first-steps) and `GYRO1`, a fourth device made by `import-pinout --new-device` from the new import template `device-pinout-EXAMPLE.csv` (part D: *Connector, Pin, Signal, Mode, Direction, Level, Current, Pin row*, one connector of nine pins, every column the import reads, EXAMPLE values).
- **Imports**, each by its plan function and each with its import record, from the shipped import templates: `approved-parts.csv` (`library_import.plan_parts_import`, every status mapped to *Review*, so no part of an example reads as approved, D-129), `wheel-connectors.net` (`kicad.plan_netlist_import`, RW1, the options of `templates/README.md`), `signal-map.csv` (the project's signal map), `device-pinout-EXAMPLE.csv`, then Generate, then `segment-lengths.csv` (`import-lengths`), `strip-lengths.csv` and `accessories.csv` (`build_data_import.plan_build_data_import`).
- **Shipped generated**.
- **Look at**: `imports DIR` (every record: file name, SHA-256, rows, columns), the fixed pins of RW1, the import window of the editor on the same files (`templates FOLDER` copies them). Pages: *Import data*, *Import KiCad pinouts*, *Define a device* (`import-pinout`).
- **Findings beyond the baseline**: none.

### 4.14 `extensions`: a project that adds a rule

- **Title** *Extensions (EXAMPLE)*; **summary** *A rule and a table in data files, and a Python plug-in that stays off until you trust it.*
- **Project**: `first-steps`, generated with EXAMPLE values, and the folder `extensions/` with the files of `docs/examples/extensions/` (`enabled.json`, `minimum-wire-gauge-power.json`, `power-wire-table.json`, `plugins/duplicate-signal-wires.py`), copied by part C.
- **Look at**: `extensions DIR` (the data files enabled, the plug-in *untrusted*), `drc` (the finding or the silence of the `x-` rule), *Help > Extensions…*, `trust DIR duplicate-signal-wires` as the exercise. Page: *Extend the tool*.
- **Findings beyond the baseline**: what the `x-` data rule says on the EXAMPLE gauges; pull request 6 records it on the page.

### 4.15 Templates considered and not made

- **`pin-currents`**: inside `splice-from-connection` (4.4).
- **`quick-diagram`**: `first-steps` and `minimal-satellite` are a quick diagram (devices and interfaces, nothing generated); Quick mode is a layout of the editor, not data of a project.
- **`electrical-checks`**: the four rules of 4.2.0 need an open finding to be seen; two of them are errors (1.2). `splice-by-hand` carries the directions and levels that make them speak in the page's steps.
- **`naming-and-title-block`**: in `build-data-and-as-built` (the title block, the label format) and `released-harness` (the author and checker); a template with its own name patterns (`HAR-001` for `W001`) would make every other page's IDs differ from what that template shows.
- **`redundancy-and-zones`**, **`device-looks`**: `small-satellite` and `flatsat` show them already.

## 5. The rules every template follows

### 5.1 Names

Every device, part, harness, person and company name is made up, in the style of the examples: devices `PCDU1`, `OBC1`, `TTC1`, `TTC2`, `RW1`, `TRX1`, `GYRO1`; parts `EX-…`; people *Designer 1*, *Checker 1*, *Releaser 1*, *Reviewer 1*; the company *Example Ltd* (and *Example Co.* where a template row already says it); ICDs *ICD-OBC EXAMPLE Issue 2*. The project name of a template is its title (`tests/test_examples.py` checks it), and it ends with *(EXAMPLE)* when the template carries an engineering number (T6), so every title block of its outputs says so.

### 5.2 Numbers and parts

- **Engineering values** come only from `templates/config-demo-values/` (the four files) and stay `"placeholder": true` (D-129); a template adds its own EXAMPLE numbers only where the feature needs one the demo files lack (a depth, a pin current, a contact rating, a long segment, a tolerance), and the page of the template lists each.
- **Parts**: the starter parts and three new EXAMPLE parts that the templates put in their own libraries, `EX-SPLICE-1`, `EX-BACKSHELL-MICROD` and `EX-CONTACT-22`, and EXAMPLE contact ratings on two starter connector parts in the library of `splice-from-connection` (4.4); the starter library itself does not change. Each new part is `unverified`, its description says *EXAMPLE ONLY: not a real part*, and no part of a template is approved (T5). `part-unapproved` therefore stays in every `drc`, as in `flatsat`.
- **No standard value**: no template applies a profile (3.2).

### 5.3 The checks every template passes

For every template, in `tests/test_feature_examples.py` (pull request 1, extended by each later one):

1. the shipped folder is what `tools/build_examples.py` writes (the existing test);
2. `new DIR --template NAME` (with a journal, as a person runs it), then `check DIR` exits 0 with 0 errors and 0 warnings; an info only where the template's page names it (`shield_place_not_stated` in `shields-and-ends`);
3. `generate DIR` changes nothing (`0 added, 0 changed`) for a template shipped generated;
4. `drc DIR --json`: no open error; the open findings are the **baseline** (`part-unapproved` per `EX-` part, `unchecked-config.*`, no `unconfirmed`, no `isolated`) plus the findings section 4 names for the template, compared as a set of rule IDs;
5. `export DIR` (and `--harness-plan` for `build-data-and-as-built`), then `verify DIR --outputs` with 0 errors;
6. a second `export` into another folder is byte-identical (determinism).

### 5.4 Deterministic builds

No time, no user name and no path in a shipped file: the builders give every date (`EXAMPLE_DATES` in `tools/feature_examples.py`), write no journal, keep import records (file name, SHA-256, rows: the same for the same file), as-built records (they hold neither who nor when), and the check of a device (`on` given). `project.json` carries the tool version (`tool_version`), as every example does; the preparation of each release builds the examples again, as today.

### 5.5 The shipped state

Generated where Generate has something to make (every template but `splice-by-hand` and `splice-from-connection`, which have no interface), so that the Harness tab and every output have content on opening, as `flatsat` (T10). `released-harness` ships released, `device-library` checked, `build-data-and-as-built` with its as-built record. No template ships `outputs/`: a person exports.

### 5.6 Files beside the model (part C)

`create_project` gets one more step after `save_project`: copy, from the template folder into `dest`, the folder `extensions/` and the file `device-libraries.json` with the folders it names that lie inside the template folder (a path with `..` or outside is not copied; the shipped templates have none). Nothing else is copied: the model is still written by `save_project`, so a template cannot carry a stale file into a project. `tools/build_examples.py` writes these files from `docs/examples/extensions/` and from the builder of `device-library` (`device_library.save_devices_to_file`, `subsystem_library.export_subsystem`, `library_pointer.write_pointer`), so the test of 5.3 (1) covers them. Without part C the two templates `device-library` and `extensions` are left out (T7).

## 6. The list, the dialog and the Home page

- **Groups** (T1): `TemplateInfo` gets `group`, `"start"` or `"feature"`. *Start*: `blank`, `first-steps`, `minimal-satellite`, `small-satellite`, `flatsat`, in this order (the first non-blank is still `first-steps`, which *New project from an example…* ticks). *Feature examples*: the fourteen of section 4 in the order of the manual (4.1 to 4.14). `tools/build_examples.py` reads titles and summaries from `TEMPLATES` instead of its own `PROJECTS` (one list, not two).
- **`new --list`** prints a heading line per group and pads the name to the longest name plus two:

  ```
  Start:
  blank                     An empty project: starter parts and interface types, no devices.
  first-steps               Three devices, a power link and an RS-422 link. Nothing is generated yet: start here.
  …
  Feature examples (small projects, one feature each; the manual page Examples lists them):
  full-connectors           Three devices whose connectors have a signal on every pin: fixed pinouts, ports and pin rows; generated.
  …
  ```

  `new --list --json` adds `"group"` to each entry (scripts read JSON, not the text). The help of `new` says *create a new project from an example (`new --list` shows them)* instead of naming five; `docs/CLI.md` is made again. `Unknown template 'x'. Choose one of: …` stays.
- **The New project dialog**: a heading row per group (not selectable, skipped by the arrow keys, its own accessible name), the entries under it; the list's minimum height grows to show the *Start* group and the heading of the second without a scroll; the summary under the list as today.
- **The Home page** (T9): the card *Examples* lists the *Start* group as today and ends with one line, *14 feature examples, one per feature: File > New project from an example…*, with a button that opens the dialog with the first feature example ticked.
- **Not watched on a real display**: pull request 1 adds a layout test of the dialog with 19 entries (`tests/layout_cases.py`, offscreen and on the real-platform lane) and a screenshot in `docs/ux/qt/`.

## 7. The build and the package

### 7.1 The builders

`tools/feature_examples.py` (new; the two SPDX lines): one function per template, the shared helpers (`_device(p, uid, name, x, y, connectors)`, `_demo_values(p)` read from the template files, `EXAMPLE_DATES`, the EXAMPLE parts), and `BUILDERS`, which `tools/build_examples.py` merges into its own. Every edit goes through `History(p).execute`, as in `_flatsat`. A builder that ends with an open error in `drc` stops the build (as `_flatsat` does), so a template cannot ship one by mistake. Building the examples takes under a second today (`test_example_projects_are_what_the_build_script_writes`: 0.65 s); fourteen projects of two to five devices add a few seconds.

### 7.2 Size

Measured on the runs of 2.3 (without `outputs/`): 23 to 34 files and 39 to 100 KB per small project; a zip of six of them is 70 KB. For fourteen templates: about **0.9 MB in about 400 files** (from 1.54 MB in 157 files to about 2.5 MB in about 560), about **170 KB more in a wheel or zip** (from 93 KB), and about 1.6 MB more on a disk with blocks of 4 KiB. `team-library/` and `extensions/` add a few kilobytes. The source tree of the package is 17 MB today, so the growth is under a tenth. Pull request 8 measures the wheel, the `.deb` and the Windows zip and writes the numbers into the release notes.

## 8. Release 5.1.0: no format change

5.1.0 is a minor release (new features, nothing breaks). Checked against the keys a template needs:

- **No new key in a project file.** Every field a template uses exists in format 5 (`fixed`, `row_layout`, `current_a`, `length_to`, `depth_mm`, `at_a`, `at_b`, `checked`, links with junctions, splices, accessories, baselines, waivers, waivers of errors (a deviation is a waiver of an error, `checks.deviate_op`), overrides (`Wire.overrides`), import and as-built records, `document`). The loader refuses unknown keys (`extra="forbid"`), so a template built by the 5.1.0 builders loads in 5.0.0 as it loads in 5.1.0 (pull request 7 opens each with the code of `v5.0.0`).
- **`device-libraries.json` and `extensions/`** are not part of the project format (2.6); copying them changes no format.
- **`TemplateInfo.group`** is a field of a record of the scripting interface, not of a file: `API_VERSION` stays 1 (a field is added), the API snapshot is made again on purpose, and the release notes say so under *For scripts*. `new --list --json` gains a key.
- **The fix of `isolated`** (part E) changes the findings of a project whose devices are joined only by a harness drawn by hand: one note less per such device in `drc`, `system/drc_findings.csv` and the DRC report. No example and no project of the output-hash baseline is such a project, so `tools.output_hashes --check` and `tools.numbers_snapshot --check` stay *identical*; no file of `tests/fixtures/` holds the text of the note and no test asserts it (searched), so no golden changes either.

## 9. Edge cases

| Case | Where in the code | What the design does |
|---|---|---|
| **A power port taken in name order**, not by the interface | `generate/pins._allocate_fixed`, step 4 | `full-connectors` puts each interface on its port (`ops_assign_port`), and its page says why |
| **Identical connectors on one device** | rule `connector-lookalike` | Keying `A`/`B` in `full-connectors`; kept and waived in `overrides-and-deviations` |
| **A named pin that no pair uses** | rule `link-unpaired` | Unused pins of `splice-from-connection` have no name |
| **A device joined only by a drawn harness** | `checks.find` (`isolated`) | Part E counts the plugs of a harness drawn by hand |
| **The release gate reads the outputs folder** | `vcs.release.release_blockers` (`outputs_missing`) | The builder exports into a scratch folder, releases, and ships no `outputs/` |
| **A released template copied with `--name` and `--annotate-config`** | `create_project` | Run in 2.3: `check` 0 errors; a test keeps it |
| **The ends of a shield group at different connectors** | `shield_ends.end_at` | Shown on purpose in `shields-and-ends`, with the sentence of 2.3 |
| **A gauge explanation that asks for an interface current** on a wire of a connection | `derive_gauge` (*Gauge the search gives now = not decided … interface current*) | Item 3 of section 15; the page of `splice-from-connection` says the gauge of such a wire is set by hand (F5 of the design of 5.0.0) |
| **Branch points numbered across the project** (`W002-B2`) | `naming`, `used_ids` | Kept; the page of `branching-harness` does not promise `W002-B1` |
| **A template name longer than 18 characters** | `cli/start.py` | The column is as wide as the longest name |
| **20 entries in the dialog and on Home** | `gui/new_project_dialog.py`, `gui/pages.py` | Section 6 |
| **A library folder or `extensions/` not copied by `new`** | `create_project` | Part C |
| **An electrical error that Generate will not make** | the gauge search (`wire_sizing`: *no listed gauge keeps the voltage drop under …*, *Not saved*) | `overrides-and-deviations` makes its errors by an override to a thinner gauge (run of 2.3) |
| **A deviation without a journal** | `deviation DIR` reads who and when from the journal | The page says *not recorded* is expected in the template; `new` starts the journal for what follows |
| **A template with a plug-in** opened in the editor | the trust window | The plug-in stays untrusted; the window explains it (as for any project) |
| **Imported parts that the template file marks *Approved*** | `import-parts --approved` | Every status is mapped to *Review* in `imports-from-files` (D-129) |
| **The tests that run over every template** | `tests/test_merge_fix.py`, `tests/test_new_project_labels.py` | They run 19 cases; both together take about 9 s today for five |

## 10. Tests

| File | What it holds |
|---|---|
| `tests/test_feature_examples.py` (pull request 1, grown by 2 to 6) | The checks of 5.3 for every template: shipped equals built; `new`, `check`, `generate` unchanged, `drc --json` rule set, `export`, `verify --outputs` 0 errors, a second export byte-identical. Per template, the facts of section 4: in `full-connectors` every device pin has a signal and a wire and *Spare* is `no` on every row of `box_pinouts.csv`; in `splice-by-hand` two splices and the column *Via*; in `splice-from-connection` a junction, two splices, 4 A and 2 A from `explain`; and so on |
| `tests/test_examples.py` | The list of templates equals the folders (as today); `TemplateInfo.group`; the order (*Start* first, `first-steps` the first non-blank); every title of a template with numbers ends with *(EXAMPLE)* |
| `tests/test_cli_new_list.py` (pull request 1) | `new --list` headings and column, `--json` with `group`, the help of `new` names no template |
| `tests/test_ux_rel_newproject.py`, `tests/layout_cases.py` | The dialog's headings are not selectable, the arrow keys skip them, *New project from an example…* ticks `first-steps`; the layout with 19 entries; the Home page lists five and the line |
| `tests/test_isolated_drawn.py` (pull request 2) | A device joined only by a drawn harness, by a loose cable, by a connection: no `isolated`; a device with nothing: `isolated` as today |
| `tests/test_template_files.py` (pull request 6) | `create_project` copies `extensions/`, `device-libraries.json` and the library folders inside the template, refuses to follow a path out of it, copies nothing else |
| `tests/test_e2e_510.py` (pull request 7) | One walk: `new --list`; each template through `new`, the commands its manual page names (for example `routing`, `explain`, `update-device`, `asbuilt`, `release --accept-loose-ends`), the exercises of section 4 on copies (the depth taken off, the far-device setting off, the spare fraction set), and the code of `v5.0.0` opening each template (no new key) |
| `tests/test_docs.py` | The quoted `new --list` of `GETTING_STARTED.md`; every manual page names a template that exists (part F) |

Requirements: **REQ-EX-01** and **REQ-EX-02** (1.1), in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`).

## 11. Documents

- **New page `docs/user-manual/examples.md`** (*Examples: one project per feature*): the catalogue of section 3 as a table *Feature, template, page*, the two groups, the commands to make each (`harness-design-studio new my-copy --template splice-by-hand`), and what is not a template (3.2). Linked from the index of the manual (*Which page do I need?* and the list of pages) and from `docs/README.md`.
- **One line in each manual page**, under its title: *Example:* `harness-design-studio new practice --template NAME` (see the page *Examples*, `examples.md`). For pages whose feature needs no project of its own, the line names `first-steps` or `flatsat`; for *Using HDS in your organisation*, none.
- **`docs/user-manual/splices.md`**: its walk keeps `first-steps` (it teaches the drawing) and adds *the finished result is the template `splice-by-hand`*; the section on a splice from a link names `splice-from-connection`.
- **`README.md`** (*five projects* in the table of where to start), **`docs/GETTING_STARTED.md`** (Part 1: *The tool ships five examples*, the quoted `new --list`, the note on 0.1.0), **`docs/FAQ.md`** (*Which example should I start with?*), **`docs/FLATSAT_EXAMPLE.md`** (*shows five examples on 1.0.0*), **`docs/examples/README.md`** (the five with their runs stay; a section *Feature examples* with the table and a link to the manual page; *The 19 template files* become 20 with `device-pinout-EXAMPLE.csv`), **`docs/CHEATSHEET.md`** (unchanged; it says `new --list` shows them), **`docs/developer/agent/examples-and-docs.md`** (the builders, the groups, part C), `resources/examples/templates/README.md` (the new `device-pinout-EXAMPLE.csv`).
- **`docs/CLI.md`** made again (`python -m tools.gen_cli_docs`); the in-app guide made again where it names the examples (`python -m tools.build_guide`).
- **`CHANGELOG.md`**, `## Unreleased`: one entry per pull request. **`docs/releases/5.1.0.md`**: the templates, the groups, *For scripts* (`group`, `new --list` headings), *Which written files change* (none of an existing example; the `isolated` note), the sizes of 7.2.
- Not changed: `docs/FILE_FORMAT.md` (no format change), `docs/SPEC.md` beyond a line that the examples cover each feature, `docs/RULES.md` (no rule is added; its table of the logical rules is made again by `python -m tools.gen_rule_docs` only if pull request 2 changes the words of `isolated`, *It will not appear in any harness*).

## 12. Proposed decision D-268

> | D-268 | **Release 5.1.0 is a minor release with a template for each feature: fourteen small example projects, listed in a second group *Feature examples* after the five of *Start*; no format change** (D-11, D-12, D-129, D-247, D-264; the owner's request of 2026-11-24; design `docs/ait/DESIGN_5.1_FEATURE_TEMPLATES.md`). (1) **The templates**: `full-connectors` (every pin of every device connector carries a signal and a wire: fixed pinouts, ports, pin rows; generated), `names-and-ports`, `splice-by-hand` (a harness drawn by hand with two splices of the EXAMPLE part `EX-SPLICE-1`), `splice-from-connection` (a connection with a junction and pin currents; its harness has the splices), `branching-harness`, `loose-cable-end`, `shields-and-ends`, `lengths-to-the-face`, `released-harness`, `overrides-and-deviations`, `device-library`, `build-data-and-as-built`, `imports-from-files`, `extensions`; two to five devices each, built by `tools/build_examples.py` with the tool's edit functions, shipped generated where Generate has something to make, every one passing `check`, `drc` (no open error; the baseline findings and the ones its page names), `export` and `verify --outputs` with 0 errors, and built byte for byte the same each time. (2) **Marked as examples**: every engineering number is an EXAMPLE from `templates/config-demo-values/` or named on the template's page, every config file stays a placeholder, every part is an unverified `EX-` part that no template approves, and a template with numbers says *(EXAMPLE)* in its name. (3) **The list**: `TemplateInfo.group` (`start`, `feature`); `new --list` prints a heading per group with a column as wide as the longest name, `--json` gives the group; the New project dialog has a heading per group; the Home page lists the *Start* group and one line to the rest. (4) **`create_project` copies `extensions/`, `device-libraries.json` and the library folders it names inside the template**, nothing else. (5) **The note `isolated`** counts a harness drawn by hand. (6) **Documents**: a manual page *Examples* with every feature and its template, and one line in each manual page. Not templates: standard profiles, `merge-fix`, `compare`, `migrate`, a trusted plug-in, an open error. **Written files**: none of an existing example changes; the output-hash baseline and the numbers snapshot stay. | The owner's answers to T1 to T14. The owner's request of 2026-11-24. |

The release decision of 5.1.0 is a later row.

## 13. Owner questions

Each with our recommendation first. While a question is open, the pull requests follow the recommendation.

1. **T1. Two groups, *Start* (the five, unchanged and first) and *Feature examples* (the new ones), in `new --list`, the dialog and the scripting record?** Recommended: yes. A newcomer still meets `first-steps` first, and a reader of a manual page finds its template in the second group. Alternative: one flat list of nineteen (the dialog fits it at the default size, 2.4, but says nothing about where to start).
2. **T2. The fourteen templates of section 4, with the merges said there (pin currents in `splice-from-connection`; release, versions and the checklist in `released-harness`; overrides, waivers and deviations in one; build data, the plans' Cover and colour code and the as-built record in one), and none for the features of 3.2 and 4.15?** Recommended: yes. Every feature of the catalogue names a template; a merge is made only where one project shows both features with the same harness.
3. **T3. Names of the feature, in lowercase with hyphens, no number and no prefix (`splice-by-hand`, not `ex05-splices`)?** Recommended: yes. A name is what a person types after `--template`, and the manual page names it.
4. **T4. `full-connectors` made by Generate from fixed pinouts, with parts whose pin count is the number of signals (nine-way Micro-D throughout) and each interface put on its port?** Recommended: yes. *Generated* is how most harnesses are made, and a full connector is what a team's ICD gives; a connection that pairs every pin is shown by `splice-from-connection`. Alternative: a connection that pairs every pin of full connectors (no Generate).
5. **T5. Three EXAMPLE parts in the templates' own libraries (`EX-SPLICE-1`, `EX-BACKSHELL-MICROD`, `EX-CONTACT-22`) and EXAMPLE contact ratings on two connector parts of one template, unverified, none approved?** Recommended: yes. The starter library has no splice, backshell or contact part, and the features need one; the starter library itself does not change (D-12).
6. **T6. A template with an engineering number has *(EXAMPLE)* in its name, so every title block of its outputs says so?** Recommended: yes, as `flatsat` (*EXAMPLE numbers, not engineering data*) does. Alternative: only the summary and the description say it (shorter titles, but a printed drawing does not say it).
7. **T7. `create_project` copies `extensions/`, `device-libraries.json` and the library folders it names inside the template, and nothing else, so that `device-library` and `extensions` can be templates?** Recommended: yes. Without it the two features stay outside the list (`docs/examples/extensions/` copied by hand, a library made with `save-device`). Alternative: leave the two templates out.
8. **T8. The note `isolated` counts a harness drawn by hand, in 5.1.0 (part E), since two templates would otherwise carry a note that says something untrue of them?** Recommended: yes. It changes the findings of projects joined only by drawn harnesses (one wrong note less), which the release notes say. Alternative: a patch 5.0.1 first.
9. **T9. The Home page lists the *Start* group and one line with a button for the feature examples?** Recommended: yes. Nineteen rows push everything else off the page. Alternative: all nineteen.
10. **T10. Shipped generated where Generate has something to make, released in `released-harness`, with no journal and no `outputs/`?** Recommended: yes, as `flatsat`. A person sees the feature on opening; `new` starts the journal.
11. **T11. A new import template `device-pinout-EXAMPLE.csv` with every column `import-pinout` reads (part D)?** Recommended: yes. The import templates have none for the most used import of a device, and `imports-from-files` needs a file a person can run again.
12. **T12. `imports-from-files` maps every approval status of `approved-parts.csv` to *Review*, so no part of an example reads as approved?** Recommended: yes (D-129). The page *Import data* keeps its own walk with `--approved Approved` on a practice copy.
13. **T13. 5.1.0, a minor release, no format change, no release candidate?** Recommended: yes (section 8).
14. **T14. One manual page *Examples* and one line per manual page, rather than a section per template in `docs/examples/README.md`?** Recommended: yes. A reader starts from the job (the manual page) and needs the template's name; `docs/examples/README.md` keeps its runs of the five and links to the page.

## 14. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry and the quoted `new --list` of `GETTING_STARTED.md` brought up to date (the list grows with each).

| PR | Content | Guards |
|---|---|---|
| 1 | **The groups and `full-connectors`.** `TemplateInfo.group`; `new --list` headings and width, `--json` `group`, the help of `new`; the dialog's headings, the Home page's line; `tools/build_examples.py` reads `TEMPLATES`; `tools/feature_examples.py` with `full-connectors`; `tests/test_feature_examples.py`, `tests/test_cli_new_list.py`, the layout case; `docs/CLI.md`; the API snapshot made again; REQ-EX-01 | `output_hashes --check` *identical* |
| 2 | **The two splice templates.** `splice-by-hand`, `splice-from-connection` (with the EXAMPLE parts and ratings); part E (`isolated`) with `tests/test_isolated_drawn.py` (no golden holds the note, section 8) | *identical* for the four examples |
| 3 | **Routing.** `branching-harness`, `loose-cable-end`, `shields-and-ends`, `lengths-to-the-face` (`EX-BACKSHELL-MICROD`) | *identical* |
| 4 | **Change control.** `released-harness`, `overrides-and-deviations` | *identical* |
| 5 | **Data in and out.** `names-and-ports`, `imports-from-files` with `device-pinout-EXAMPLE.csv` (part D), `build-data-and-as-built` (`EX-CONTACT-22`) | *identical* |
| 6 | **Files beside the model.** Part C in `create_project` with `tests/test_template_files.py`; `device-library`, `extensions` | *identical* |
| 7 | **The examples page and the end-to-end test.** `docs/user-manual/examples.md`, the line in each manual page, the documents of section 11, `tests/test_e2e_510.py`, REQ-EX-02, the screenshot of the dialog | — |
| 8 | **The preparation of 5.1.0**: the version, the changelog section, the decision rows D-268 (as decided, with what was built where it differs) and the release row, `docs/releases/5.1.0.md` with the sizes measured, the status pages, the records made again (a stamp-only renewal: `5.1.0` has five characters, as `5.0.0`), the examples built again | stamp only |

Order: 1 first (the groups and the test module the others extend); 2 to 5 after 1, in any order; 6 after 1; 7 after 2 to 6; 8 last. No pull request changes a written file of an existing example or a golden; pull request 2 changes the findings of a project whose devices are joined only by drawn harnesses, on purpose.

## 15. Found on the way

1. **The note `isolated` is wrong for a device joined only by a harness drawn by hand** (runs of 2.3, `splice-by-hand` and `loose-cable-end`). `checks.find` adds the devices of interfaces and of connections to `connected`, not those a harness drawn by hand plugs into, and says *Units without interfaces get no wires, so they will not appear in any harness plan* of devices that are in one. The rule's table in `RULES.md` reads *It will not appear in any harness*. Part E (T8).
2. **The help of `new` names the five templates by hand**, and `tools/build_examples.py` repeats every title and summary (`PROJECTS`, with *units*); a sixth template would be missing from the help and from `docs/CLI.md`. Section 6.
3. **The explanation of the gauge of a wire made from a connection asks for an interface current** (*Gauge the search gives now = not decided [not decided yet, because these are not set: interface current (set Max current on the interface)]*, `explain DIR W001-001` in the run of `splice-from-connection`), though the wire has no interface and its pins have currents. Generate does not size such a wire (F5 of the design of 5.0.0), so the line describes a search that never runs for it. Small; pull request 2 words it as *drawn wires are not sized; set the gauge* and adds the case to the test of `explain`.
4. **`new --list` has a fixed name column of 18 characters** (2.4), so the summaries of names longer than 17 would not line up.
5. **Generate gives a named power port in name order, not by the interface** (2.3): with several interfaces of one type on a fixed pinout and no far-device names, the interface *main power* can land on the pins `KA_…`. This is the rule of 2.1.0 as designed (and *Choose port…* or `ops_assign_port` sets it); the page of `full-connectors` says so, and no change is proposed.
6. **The import templates have no pinout file**, though `import-pinout` is the import a device is most often made with. Part D.
7. **A template cannot carry `extensions/` or a library folder** (2.1, 2.6). Part C.

## 16. Risks and what this design does not check

- **Nineteen entries have not been looked at on a real display**, neither in the dialog nor on the Home page; the offscreen measure of 2.4 is at the default scale only. Pull request 1 adds the layout case to the real-platform lane.
- **The findings of section 4 for `shields-and-ends`, `lengths-to-the-face`, `device-library`, `build-data-and-as-built`, `imports-from-files` and `extensions` come from the rules as read and from the end-to-end test of 5.0.0, not from runs of those exact projects**; the runs of 2.3 cover their mechanisms (places by import, an override and two deviations, the release, the drawn harnesses, the library folder). Each pull request runs its template and corrects the page where `drc` says otherwise.
- **Every template is a little more to keep up to date**: a change of an output or a rule now meets fourteen more projects in the tests. The projects are small, and the test of 5.3 says which one moved.
- **EXAMPLE numbers in more places** (depths, currents, ratings, tolerances) could be copied into a real design. Each is marked on the template's page, the files stay placeholders, the titles say *(EXAMPLE)*, and no part is approved.
- **The package grows by about 0.9 MB** (7.2), measured on stand-ins, not on the built templates.
- **Not tried:** a template opened by the code of `v5.0.0` (section 8 follows from the loader's rule and the absence of new keys; pull request 7 runs it); the dialog with group headings (not built); the screen reader on the headings.
- **No code was written**; the module and function names are the plan, and the pull requests record where they differ.
