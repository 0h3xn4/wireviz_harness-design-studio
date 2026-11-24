# Design of 5.2.0: every feature reachable

Written on 2026-11-24 from a reading of the code of the 5.1.0 template stack (`c96edcf`, *5.1.0 pull request 7*; the checkout reports `harness 5.0.0`), from a feature audit of the same commit (findings F1 to F13: every feature of the catalogue of the design of 5.1.0 looked for in the menus, the rail, the command palette, the command line and the scripting interface, partly by running the editor offscreen; its notes are not part of the repository, and this page repeats what it uses), and from runs of the command line and of the editor (Qt `offscreen`) on copies of the templates in a scratch folder. It answers the owner's instruction, word for word: *"Make sure that no feature is hidden and that the users can actually use them."* Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the designs of 5.0.0 and 5.1.0 ([`DESIGN_5.0_FORMAT_5.md`](DESIGN_5.0_FORMAT_5.md), [`DESIGN_5.1_FEATURE_TEMPLATES.md`](DESIGN_5.1_FEATURE_TEMPLATES.md)): scope, what exists, a part per item, the format question, edge cases, tests, documents, the decision, the owner questions, the pull requests, what was found on the way and what was not checked. Choices that are the owner's are G1 to G13 (section 16), each with a recommendation first. Every device, harness and person name on this page is made up for the example (`OBC1`, `W002`, `Designer 1`).

**Status:** draft. No code is written. No owner answer yet; the work goes on by the recommendations of section 16 while a question is open. The decision that records the design is D-270 (section 15), proposed; it is the next free number (D-269 is taken). The release decision of 5.2.0 is a later row.

**What comes first.** A pull request of 5.1.0 (branch `feat/reach-fixes`, not merged when this page was written) does the small items of the audit, and this design assumes it is merged: a field for the reason in the Release window when the as-built gate blocks (F1), so that the editor can release under the gate as the command line can with `--accept-asbuilt`; the lines in the manual and in the Engineering values window that name `config --apply-profile` and `settings --set`; *right-click a column heading* for the column *Current (A)* of the pin table; *Go > Go to As-built* in every role and *Go to Devices* in the Go menu of the AIT role; the reasons in the tooltips of the disabled entries (*Show changes of harness…*, *Selected connection*); the names *Versions* and *Releases* brought together, and `…` in place of `...` in four menu entries. Where a part below builds on one of these, it says so.

## 0. The frame

The audit found every feature of the catalogue working: each of the 52 commands ran on a copy of an example, and each menu entry it opened did what the manual says. What it found wrong is **reach**: a feature that exists but that one kind of user cannot get to.

1. **Settings without a field.** 42 of the 78 settings of `core/settings.SETTINGS` can be changed only with `settings DIR --set` or by editing a JSON file (section 2.2): the selectable models, the name patterns, the title-block fields, the as-built tolerances, `pair_suffixes`, `signal_counterparts`, *different people in a release*, the as-built gate, the segregation flags and more. The settings of the harness plans (`config/harness_plan.json`: the colour rule, the colour codes, the note lines) are the other way round: the editor has them, `settings --set` refuses them.
2. **Features only on the command line.** The standard profiles (the Engineering values window says they exist and offers no control), the build-data import, the importers of a plug-in, the parts-library source and date, the run record, the import templates.
3. **Features only in the editor that a script or CI needs.** A waiver of a warning (a deviation of an error has a command, a waiver has none) and the import of an interface table.
4. **Places some roles reach only by Ctrl+K.** The as-built page in the Electrical role, the Devices tab in the AIT role (both made reachable by the pull request of 5.1.0), the drawings and outputs in the Systems role, and the Next step page in Quick mode, which no menu and no Ctrl+K entry reaches at all (section 2.6, a run).
5. **Nothing stops the next feature from arriving hidden.** No test knows the list of features, so a new command, menu entry or setting with no way to it in the other half of the tool passes every check.

5.2.0 answers with five rules, which the parts below build and the tests keep:

1. **Every feature has an entry in the editor**, or a reason written in a registry of features and printed on the manual page *Examples*.
2. **Every feature that changes a project has a command**, or a reason written in the same way.
3. **A role hides tools, never places**: every area of the window is in the Go menu of every role and in Ctrl+K.
4. **One planner per change**: the window, the command and the scripting interface call the same function, so the three refuse the same values with the same words.
5. **No format change.** Settings live in config files, which already hold every key; nothing new is stored in the model (section 11).

## 1. Scope

### 1.1 In scope

| Part | What is built | Audit |
|---|---|---|
| A | **Fill from a standard profile** in the Engineering values window (section 3) | F2 |
| B | **Every setting editable**: one planner for every setting and the three of the harness plans; `settings --set` for every key, `harness_plan.*` included; the name patterns checked when they are set; the page *Settings > All settings*; a button from the Assumptions window to it (section 4) | F3, F4, F13 |
| C | **`waive` and `import-interfaces`**; *Take back…* of a waiver and of a deviation in the editor (section 5) | F8; 18.3 |
| D | **The import wizard and Settings > Project**: the kinds *Build data* and one per plug-in importer; the group *Release rules* (different people, the as-built gate and its two tolerances, the counterpart words); the group *Parts library* (name, version, source, date); *Write a run record* in the Export window (section 6) | F9 |
| E | **Save the import templates…** in File > Import and on the first page of the import wizard (section 7) | F12 |
| F | **Every place from every role**: the Go menu lists every area in every role; a new *Go > Go to Next step*; a test that walks every role and Quick mode (section 8) | F5, F7 |
| G | **The registry of features and its guard**: `core/features.py`, the table of the page *Examples* made from it, tests that fail on a command, a menu entry or a setting that no feature names, and on a feature with no entry and no reason (section 9) | — |
| H | **The command line and the edits**: `import-connections` for connections between devices of the project; the drawn edits stay a known limit, with the reason (section 10) | known limit |

And with them: three requirements (REQ-REACH-01: every feature has an editor entry and, if it changes a project, a command, or a reason in the registry; REQ-REACH-02: every area is in the Go menu and in Ctrl+K of every role and of Quick mode; REQ-REACH-03: every setting can be changed in the editor and by `settings --set`), in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`).

### 1.2 Not in scope

- **The small items of the pull request of 5.1.0** on `feat/reach-fixes` (listed under *What comes first*).
- **A change of the project format.** Nothing below needs a key of format 6 (section 11). Where a feature would need one (an import record of a new kind), it does without, and says so.
- **A general edit command** (`edit DIR STEPS.json`, the planners of the editor as a command language): section 10, G7.
- **A command for drawn harnesses, wires, splices, loose ends, joins, groups and *Edit all wires*.** They stay a known limit (section 10).
- **A change of a role's rail.** What the rail lists stays as D-193 and R7 of the design of 4.3.0 decided; only the Go menu changes (section 8).
- **New rules, new outputs, new written files.** No output changes; the output-hash baseline and the numbers snapshot stay.
- **Screenshots of the new pages** beyond the ones `tools.gui_screenshots` makes today.

## 2. What exists at the 5.1.0 template stack

### 2.1 How a feature is reached

The editor has 117 actions whose object name starts with `act-` (counted on `full-connectors`, offscreen). A person reaches one by its menu entry, a key, a button of the top bar or of a page, the rail, or the command palette (Ctrl+K). `MainWindow.palette_entries` lists **every enabled action** of the window, whatever the role, besides the entries for adding a device, connecting with a type and going to a harness, device or interface. A role takes entries out of the menus (`gui/areas.py`: `SYSTEMS_HIDDEN_ACTIONS`, 42 names; `AIT_HIDDEN_ACTIONS`, 30; `ASBUILT_ACTIONS`, 3, hidden for Systems and Electrical) and areas out of the rail (`HIDDEN_AREAS`: Systems leaves out Home, Drawings, Outputs, As-built and Review; Electrical leaves out As-built; AIT leaves out Model). A role is a view, never a permission.

A run that opened a copy of `full-connectors` and switched the role (offscreen, 1440 × 900) counted the named entries visible in the menus and those in Ctrl+K:

| Role | Rail | Named menu entries | Ctrl+K entries | Go menu |
|---|---|---|---|---|
| Electrical | Next step, Home, Model, Checks, Drawings, Outputs, Review, Versions, Settings | 142 | 179 | Checks, Device list, Devices, Diagram, Harness, Home, Interface table, Lists, Releases, Review, Settings |
| Systems | Next step, Model, Checks, Versions, Settings | 87 | 180 | Checks, Devices, Diagram, Home, Releases, Review, Settings |
| AIT | all ten (Model while it is open) | 101 | 179 | As-built, Checks, Harness, Home, Lists, Releases, Review, Settings |

Every action that is in no menu of a role is in its Ctrl+K while it is enabled; the ones in neither are disabled (*Duplicate*, *Align …*, *Create redundant copy* with nothing selected; *Show changes of harness…* without a baseline). **The Next step page has no action at all**: no Go entry, no Ctrl+K entry. It is reached by its rail button, which every role lists, but Quick mode lists only Home, Model and Settings, so in Quick mode the page is reached only by turning Quick mode off (run). The docstring of `areas.py` says the areas a role leaves out *stay in the View and Go menus*; for the Systems role the entries of Drawings and Outputs (`act-go-harness`, `act-go-lists`) are in its hidden list, so they are in Ctrl+K only.

The tests that keep this: `tests/test_ui_systems_menus.py` (every entry the Systems role hides is in Ctrl+K while it is enabled), `tests/test_ux_palette.py` (Ctrl+K lists every enabled action), `tests/test_ui_areas.py` and `areas.unlisted_everywhere()` (every area is on the rail of at least one role). No test walks the AIT and Electrical roles or Quick mode, and no test asks whether a feature has an entry at all.

### 2.2 Settings

`core/settings.SETTINGS` has 78 settings in eight files (`segmentation`, `segregation`, `derating`, `generation`, `emc`, `naming`, `titleblock`, `model`), each with a kind (`number`, `whole`, `choice`, `flag`, `table`, `pairs`, `names`, `text`), a default, a range and a text. Where each can be changed in the editor (a script compared the registry with `configcheck.engineering_values(include_optional=True)` and with the fields of `gui/settings_page.py`):

| Place | Settings |
|---|---|
| *Design > Engineering values…* (`gui/config_dialog.py`) | 29: the derating factors and margins, the ampacity table, the voltage drop, the spare pin fraction, the service loop, the resistivity, the two pin gaps, the mass margin, the shield ends, the test limits, the EMC pairs, the shield bonding, one bundle per EMC class, the category and level pairs |
| *Settings > Project* | 6: `segmentation.mode`, `model.label_format`, `model.length_reference`, `naming.review_checklist`, `naming.far_device_names`, `naming.signal_map` |
| *Edit > Wire colours…* | 1: `generation.wire_colour_by_signal` |
| **none** | **42**: the models `model.bundle_basis`, `length_model`, `cut_allowance_m`, `twist_takeup_fraction`, `drop_model`, `resistivity_temperature_coefficient`, `resistivity_reference_temperature_c`, `mass_model`, `pin_allocation_categories`, `pin_fit_strategy`, `connector_choice`, `readiness_blocking`, `return_path_categories`, `return_path_conductors`, `single_path_conductors`, `service_loops_per_wire`, `bom_wire_allowance_fraction`, `bom_contact_spare_fraction` (18); the custom label templates `model.label_wire_template`, `label_connector_template` (2); the seven name patterns `naming.harness`, `box_connector`, `cable_connector`, `wire`, `shield`, `branch`, `segment`; `naming.signal_counterparts`, `pair_suffixes`, `release_distinct_roles`, `release_requires_asbuilt`; `titleblock.fields`; `segregation.forbid_nominal_with_redundant`, `forbid_pyro_with_other`; `derating.contact_rating_key`, `rf_power_factor`, `partial_load_factor`; `generation.default_gauge_awg`, `wire_part_by_construction`, `asbuilt_cut_tolerance_mm`, `asbuilt_strip_tolerance_mm`; `emc.classes` |

*Help > Assumptions…* (`gui/assumptions_dialog.py`) shows `settings.render(project)`, read-only.

**The planners.** `settings DIR --set FILE.KEY=VALUE` (`cli/settings_cmd.py`) sets any key of the registry with `configcheck.with_value`, then runs `configcheck.validate` on the whole project and refuses everything if an error appears (`Nothing was changed.`, exit 1); a new file is made with `placeholder: false`. `configcheck.plan_set_value` (the Engineering values window and `api.set_config`) takes only the 29 engineering values, reads text as a person types it (`0,5 V`, `20: 5, 22: 3.5`), checks the value by `validate` on a trial project and asks `check_locks`; a new file is made with `placeholder: true`. `configcheck.plan_set_choice` (the combos of Settings > Project) takes any setting of kind `choice`. Five settings have planners of their own: `plan_set_checklist`, `plan_set_far_device_names`, `plan_set_signal_map`, `plan_set_distinct_roles`, `plan_set_counterparts` (the options of `config`). `core/plan_config.py` changes `config/harness_plan.json` for *Settings > Harness plan*, refuses what `configcheck.harness_plan_issues` refuses, and removes the file when every value is back to its default.

**The release freeze.** A release freezes `config/derating.json`, `emc`, `segregation` and `titleblock` whole, and eight keys of `generation` (`core/vcs/snapshot.py`: `FROZEN_CONFIG_FILES`, `FROZEN_GENERATION_KEYS`); `naming`, `model`, `segmentation` and `harness_plan` are not frozen. `History.execute` runs `check_locks`, so every planner above is refused where a release froze the value.

Runs on copies of the templates:

- `settings DIR --set 'harness_plan.colour_rule="pin_code"'` on `first-steps`: `error: '…' is not FILE.KEY=VALUE of a setting (see settings).`, exit 2.
- `settings DIR --set 'model.pin_fit_strategy="bogus"'`: `error: config/model.json: pin_fit_strategy must be one of first_fit, last_fit, spread.` `Nothing was changed.`, exit 1.
- `settings DIR --set 'naming.harness="H"'` on `first-steps`: `1 value(s) set.`; `validate` reports nothing; `generate` then says `warning: [naming] The naming template 'naming.harness' is not valid; the default was used.` and makes `W001` and `W002`. `naming.wire="{harness}"` is accepted in the same way. The range the registry gives (*a pattern that gives a different valid ID for every number*) is checked only when Generate uses the pattern (`generate/engine.py`, `namer.warnings`).
- `settings DIR --set 'naming.harness="H{n:03d}"'` on `released-harness`: set; `generate` changes nothing (`0 added, 0 changed, 2 unchanged`): a pattern names the harnesses made after it, never an existing one.

### 2.3 The standard profiles

`core/standard_profiles.py` holds two profiles: `ecss-q-st-30-11c` (11 values: the contact current factor, the two connector voltage factors, the connector and wire temperature margins, the RF power factor, the wire voltage factor, the bundle factors by count, the factors of partly loaded bundles, the mating cycles, the gap between power and return pins) and `ecss-e-st-20-07c` (2: the shield bonding, one bundle per EMC class). `plan_profile(project, name)` fills only the values that are not set, keeps a value a person set (and lists it as *kept*), and marks every file it changes as a placeholder, also one that was reviewed. `config DIR --apply-profile NAME` (`cli/data.py`) runs it as one step: on a copy of `first-steps` it printed eleven `set …` lines with the requirement each comes from, `Profile ecss-q-st-30-11c: 11 value(s) set, 0 kept.`, the files now marked as placeholders and the engineering values still missing. The Engineering values window says *"the optional standard profiles fill values from a standard"* (`strings.CONFIG_INTRO`) and has no control for them. Two of the eleven values, `derating.rf_power_factor` and `partial_load_factor`, are not among the fields of the window (`configcheck.NEEDS` and `OPTIONAL_NEEDS` do not hold them), so a person who filled the profile in the editor would not see them there.

### 2.4 Waivers and deviations

A waiver is a `Waiver` of `waivers.json`; a deviation is a waiver of an error of an electrical rule (`checks.waive_op` for a warning, `checks.deviate_op` for an error of a rule with `deviation=True`). The editor makes both from the Problems list (*Waive…*, *Accept as deviation…*), the Review page and the Next step page (`controller.waive`, `controller.deviate`, one undo step each). The command line has `deviation DIR` (list), `deviation DIR FINDING --reason TEXT` and `deviation DIR FINDING --remove` (`cli/journal_cmd.py`, `core/change_ops.py`), and the scripting interface `accept_deviation`, `remove_deviation`, `list_deviations`. **There is no command for a waiver** (read-and-fix-problems: *The command line cannot waive a finding*), **and nothing takes a waiver back**: the editor lists a waived finding as a line of text (`waived-<id>` in `gui/panels.py`, the column *Waiver* of the Checks panel) with no button, the command line has no command, and only Undo in the same session or an edit of `waivers.json` removes one. A deviation can be taken back only on the command line (`--remove`) or from a script.

### 2.5 Imports and the import templates

The import wizard (`gui/import_wizard.py`, `gui/import_kinds.py`) has six kinds: interfaces (File > Import > *Import interfaces…* opens the older interface dialog), approved parts, segment lengths, the ampacity table, a device pinout and a KiCad netlist. Each asks the planner the command asks and records the import (`ImportRecord`, `imports/records.json`). The command line has ten ways to import: `import-parts`, `import-lengths`, `import-build-data`, `import-netlist`, `import-pinout`, `import-devices`, `import-subsystem`, `import-asbuilt`, `import-plugin`, and `config --ampacity-csv`, with no `import-interfaces`. `import-build-data` tells the kind of table by its headings (`core/build_data_import.detect_kind`: strip lengths, pin contacts, accessories, part tools, cable ends, shield ends), refuses the whole file when a row is refused, and records it. `import-plugin DIR NAME FILE` runs an importer of an enabled and trusted plug-in (`core/extensions/pluginapi.importer`) as one step and **writes no import record**. `core/imports.plan_interface_import` adds interfaces (never changes one: an ID in use is refused), finds the columns by their headings and, for a field it does not find, takes the column at the field's position (`guess_mapping`); the wizard imports the good rows and skips the others (`partial=True`).

The kinds of an import record are a `Literal` of the model (`core/model/imports.ImportKind`, 15 kinds), part of format 5, which is frozen since `v5.0.0`.

`templates FOLDER` copies 22 files (the CSV templates of the imports, the device pinout and colour code examples, `design-review-checklist.md`, `signal-map.csv`, a netlist, the CI scripts, `config-demo-values/`) into a folder that must not exist or be empty (run: a second call into the same folder says *already exists and is not an empty folder; choose a new one*, exit 2). The editor gives two of them by other ways (the checklist: *Use the template's points*; the colour code: *Use the example colour code…*) and none of the files.

### 2.6 Roles, areas and Quick mode

See 2.1. The areas are `next`, `home`, `model`, `checks`, `drawings`, `outputs`, `asbuilt`, `review`, `revisions`, `settings` (`areas.AREAS`). The Go menu has *Go to Home* (Ctrl+7), *Go to Settings* (Ctrl+,), *Go to As-built*, *Go to Review*, one entry per main tab (*Diagram*, *Harness*, *Lists*, *Checks*, *Releases*, *Devices*, Ctrl+1 to Ctrl+6) and the two side lists (*Interface table*, *Device list*). No entry goes to the Next step page.

### 2.7 The command line and the edits

The editor's edits are pure planners in the core (`edit.ops_add_unit`, `edit.ops_add_interface`, `links.plan_add_link`, `links.plan_create_harness`, `manual_harness.plan_new_harness`, `plan_add_connector`, `plan_cable_from_port`, `plan_add_loose_end`, `plan_plug_loose_end`, `wires.plan_add_wire`, `plan_group_wires`, `plan_bulk_wire_edit`, `splices.plan_add_splice`, `plan_splice_wire` …). The command line reaches some of what they make by files: `import-devices` adds the devices of a device library file (one written by hand, or by `export-devices` or *Save to library…*), `import-subsystem` adds the devices of a subsystem file **with the connections between them**, `add-device` takes a device from a library folder, `import-pinout` and `import-netlist` make the connectors of a device. It has no way to add an interface (until part C), a connection between devices that are already in the project, the harness of a connection, a harness drawn by hand, a wire, a group, a splice, a loose end or a join. The project files are the other way: `schema FOLDER` writes a JSON Schema per kind of file, and `check` refuses a file that does not fit.

## 3. Part A: fill from a standard profile (F2)

**In the window.** Under the introduction of *Engineering values*, one row: *Fill the values that are not set from a standard profile:* a combo with the two profiles by their titles (*ECSS-Q-ST-30-11C: derating of connectors, wires and bundles*, *ECSS-E-ST-20-07C: wiring and shield rules*) and a button *Fill…*. The titles and the list come from `standard_profiles.PROFILES` (a `title` is added to each profile, the docstring's words), so a third profile appears without a change of the window.

**What *Fill…* does.** It calls `standard_profiles.plan_profile(project, name)` and shows a confirmation with three lists: the values it sets (setting, value, the requirement it comes from), the values it keeps because a person set them (*kept: you set 0.6, the profile says 0.5*), and the files that become placeholders. *Fill* runs `ctl.run(f"Apply profile {name}", [SetConfig(c) for c in plan.configs])`, one undo step, the step `config --apply-profile` runs; the fields of the window are then read again. Nothing to fill: the button says so (*Every value of this profile is set already*) and no step is made.

**Rules.**

- **A form with unsaved edits** is not filled: *Fill…* is off while the window has changes, with the reason *Apply or cancel your changes first*, so a profile never mixes with a value a person typed and did not apply (G4).
- **A release froze the file**: `ctl.run` is refused by `check_locks`; the confirmation is not shown, and the line under the row gives the reason the release gives (`plan_profile` fills only unset keys, but a key added to a frozen file changes the frozen values, so it is refused like any other change).
- **The two values the window does not show** (`rf_power_factor`, `partial_load_factor`) are listed in the confirmation with *(shown in Settings > All settings)*, which part B adds.
- **Generate is out of date afterwards** when a value the generator reads was filled: the window says so as `config` says it (*The profile changes values the generator reads … Generate again, then export again*).

The page *Fill in the engineering values* gets the steps in the app beside the command.

## 4. Part B: every setting editable (F3, F4, F13)

### 4.1 One planner for a setting

`configcheck.plan_set_value(project, file, key, value, *, placeholder=None)` becomes **the** planner of one setting, for every key of `SETTINGS` and the three keys of the harness plans (4.2). What changes in it:

- **Every key, by its kind.** The field information (`FIELD_INFO`) of a key that is not an engineering value is made from the registry: the label, the unit, the kind, the choices and the range. Reading text as a person types it works for every kind: a number or a whole number with its unit; a choice by its word; a flag by *yes*/*no*/*true*/*false*; a `names` list one per line or separated by commas; `pairs` as `A=B, C=D` or `A B` per line; a `table` as `key: value, …`; and a ready JSON value. Empty text or None clears the key, so the tool's default applies again.
- **The keys with planners of their own go to them**: `naming.review_checklist`, `far_device_names`, `signal_map`, `release_distinct_roles`, `signal_counterparts`, and `harness_plan.*` (`plan_config.plan_settings_edit`). Their checks and their words stay theirs.
- **The name patterns are checked when they are set** (4.4).
- **A new file** takes the flag its kind of file has today: `placeholder: true` for the files of engineering values (`derating`, `emc`, `generation`, `segregation`), as the Engineering values window does, and `false` for the project's own choices (`naming`, `model`, `segmentation`, `titleblock`, `harness_plan`), as Settings > Project does. A value set in an existing file never changes its flag.
- **Refused where a release froze it**, with the reason of `check_locks`, and refused in a read-only project.

`settings --set`, `api.set_config`, the Engineering values window, the combos of Settings > Project and the page of 4.3 all call it. `plan_set_choice` stays as a thin call of it.

### 4.2 `settings --set` for every key, the harness plans included

- `settings DIR --set FILE.KEY=VALUE` runs `plan_set_value` per item, as one step for all of them (all or nothing, as today), and prints for each the value as stored. The output of a run that sets nothing new is *already set*.
- **`harness_plan.colour_rule`**, **`harness_plan.colour_codes`** and **`harness_plan.notes`** are accepted. They are described in a second table of the registry, `settings.PLAN_SETTINGS` (label, kind, range, text), not in `SETTINGS` (G2): `settings` prints them in a section of their own, *config/harness_plan.json (the harness plans)*, and `--json` gives them under the key `plan`; the settings table of `export-data` (`open_data.settings_table`, which reads `settings.rows`) does not change, so no written file changes. A colour code is a JSON object (`{"name": …, "parts": […], "pins": {"1": "Black", …}}`), the codes a list of them.
- **`--set FILE.KEY=@PATH`** reads the value as JSON from a file, for a long table (a colour code of 37 pins, a signal map). `@@` at the start stands for a value that starts with `@`.
- `settings DIR --unset FILE.KEY` (new) takes a key out, so the tool's default applies again; today that needs `--set FILE.KEY=null`, which works but is not said anywhere.

### 4.3 The page *Settings > All settings*

A new section of the Settings page, after *Project*: **All settings**. It is made from the registry, so a setting added to `SETTINGS` gets a row without a change of the page.

- **One row per setting**, grouped under a heading per file (`config/naming.json`), in the order of the registry, then the three of the harness plans. A row shows the label (and unit), an editor for the value, where the value comes from (*set by the project*, *the tool's own default*, *not set*, with *placeholder* where the file is one), the range as a line under it, and *What it does* as the tooltip (the registry's `what` and `used_by`).
- **The editor by kind**: a field for a number, a whole number or a text; a combo for a choice (with *the tool's default (…)* first) and for a flag (*yes*, *no*, *the tool's default*); a box of lines for a list of names; a small table of two columns, with *Add row* and *Remove row*, for pairs and tables (the keys of `partial_load_factor` are fixed: three rows, no *Add row*).
- **Editing**: a value is applied when the field is left or Enter is pressed, as one undo step *Set naming.harness*; an error stays under the field in the planner's words and nothing is applied. *Reset* on a row takes the key out (the default again).
- **The 36 settings that have a place of their own** (the 29 engineering values, the 6 of Settings > Project, the wire colours) and the harness plans show their value and a link *Change in Engineering values…* / *in Settings > Project* / *in Wire colours…* / *in Settings > Harness plan* that opens that place at that value (`ConfigValueDialog.focus_value`, `SettingsPage.show_section`). They are not edited twice (G1).
- **A filter field** at the top finds a row by its label or its key (`pair`, `naming.wire`).
- **Frozen by a release**: the editor is off and the line under it gives the reason, as the Engineering values window does (`field_lock_reason`).
- **Generate out of date**: after a change of a value the generator reads, the notice of the window says *Generate again*, as after any edit.
- **Object names** `setting-<file>-<key>` on each row, for the tests and for the registry of part G.

**The Assumptions window** (*Help > Assumptions…*) gets a button *Change settings…* that opens this page. The line the pull request of 5.1.0 adds there (*To change a value: …*) names the page instead of the command alone.

### 4.4 The name patterns

`configcheck.validate` gets the check Generate makes of a pattern (`core/ids` and the namer of Generate: the places a pattern may hold, `{n}` present where the pattern numbers, two numbers giving two different IDs that `ID_RE` accepts). Two cases:

- **Setting a pattern** (the page, `settings --set`, a script): `plan_set_value` refuses a pattern Generate would not use, with the reason (*Name of a harness: `H` gives the same ID for every number; put {n} in it, for example H{n:03d}*).
- **A project that already holds such a pattern** gets a **warning** from `validate` (`naming_pattern`), not an error, so `check` keeps its exit code and Generate goes on as today with the default and its warning (G3).

A pattern names the IDs made after it; the page says so under the group (*Existing harnesses keep their IDs*), as the run of 2.2 shows.

### 4.5 What the page does not do

It does not edit the parts, the interface types or the files of a device library; it does not change the placeholder flag of a file (the Engineering values window does, per file); it does not hold the appearance or editing choices of a person (those are not settings of a project).

## 5. Part C: `waive`, take back, and `import-interfaces` (F8)

### 5.1 `waive`

`waive DIR` lists the waivers (ID, rule, the reason, who and when from the journal, and *no longer fits* where the finding changed since). `waive DIR FINDING --reason TEXT` waives an open warning: `checks.waive_op`, through a new `change_ops.waive(project, finding_id, reason)` that the editor's `controller.waive` also calls. `waive DIR FINDING --remove` takes a waiver back (`change_ops.remove_waiver`). The twin of `deviation`, in the same module (`cli/journal_cmd.py`), with the same exit codes: 2 for an unknown finding or a missing reason, 1 for a refusal (*This finding cannot be waived*; an error of an electrical rule: *use `deviation`*; a reason under 10 characters; a released harness), 0 otherwise; `--json`. A waiver of a finding whose waiver no longer fits replaces the old one, as in the editor. The scripting interface gets `waive`, `remove_waiver`, `list_waivers` (`API_VERSION` stays 1; names are added).

### 5.2 Take back a waiver or a deviation in the editor

A waived line in the Problems list (`waived-<id>`) and a row with a waiver in the table of offending objects of the Checks panel get **Take back…**: a question (*Take back the waiver of {id}? The finding is open again. The reason stays in the journal.*), then one undo step (*Take back the waiver {id}*) through `change_ops.remove_waiver` or `remove_deviation`. Off in a read-only project; refused, with the reason, where a release froze the harness the finding is about. A deviation is taken back the same way. The journal keeps the entry (it is append-only); the removal is a new entry.

### 5.3 `import-interfaces`

`import-interfaces DIR FILE [--sheet NAME] [--dry-run] [--skip-bad-rows] [--json]` reads the table as every import does (`imports.read_table`, `read_table_sheet`: CSV, TSV, JSON, XLSX, the size limits), plans with `imports.plan_interface_import`, echoes the columns it read and left out and each row (`row 3: ERROR Unknown interface type 'rs485'`), and records the import with `import_reports.interfaces_report` (kind `interfaces`, which exists). Rules:

- **Headings are required.** The command refuses a file in which a field (ID, type, from, to) is found only by its position, and names the headings it reads (*Interface ID*, *Interface type*, *From device*, *To device*, *Redundancy*, and their aliases); the wizard keeps its column choice, which a person sees (G6).
- **All or nothing by default**, as `import-build-data` and `import-subsystem`: a row with a problem stops the import (`Nothing was changed.`, exit 1). `--skip-bad-rows` imports the good rows and lists the others, which is what the wizard does.
- **Adds, never changes**: an interface ID that is in use is refused, as in the wizard; the template `interfaces.csv` of `templates` is a file the command reads.

## 6. Part D: the import wizard, Settings > Project and the Export window (F9)

### 6.1 Two more kinds in the import wizard

- **Build data.** `KindInfo("build-data", …)`, File > Import > *Import build data…*. After the file is chosen, the kind of table is told by its headings (`build_data_import.detect_kind`) and named on the mapping page (*This is a table of strip lengths*); the columns are those of the headings, so the mapping page shows them and asks for the unit of the lengths (mm, cm, m, in, as `--unit`). The plan is `plan_build_data_import`; the preview lists every row with *added*, *changed*, *unchanged* or the reason it is refused; a refused row stops the whole import, as on the command line; the import is recorded with `build_data_report` (kinds `strip-lengths`, `pin-contacts`, `accessories`, `part-tools`, `cable-ends`, `shield-ends`, which exist). The page *Enter the build data* gets the steps in the app.
- **The importers of a plug-in.** One kind per importer of an enabled and trusted plug-in (`manager.runtime(project).importers`), listed under a heading *From extensions* with the importer's `doc` as its summary and its `suffixes` as the file filter; none is listed while no plug-in is trusted, and the first page says where to trust one (*Help > Extensions…*). The plan is `importer.read(project, path)` (its `rows` are the preview, its `notes` the notes); *Import* runs its `ops` as one step *Import with NAME*. A plug-in that raises is reported in the plug-in's words (*the importer NAME stopped: …*), and the project is not changed. **No import record**, as on the command line (G10): a record needs a kind of `ImportKind`, and a new kind is a format change (section 11).

### 6.2 The group *Release rules* in Settings > Project

Under *Review checklist*, a group **Release rules**:

- **Different people in a release** (a check box): `naming.release_distinct_roles` through `plan_set_distinct_roles`; its text says what `config --distinct-roles` says (three different people, every name typed, the date not earlier than the change log).
- **Release needs complete as-built records** (a check box): `naming.release_requires_asbuilt`; under it the two tolerances of the as-built report, *Cut length tolerance (mm)* and *Strip length tolerance (mm)* (`generation.asbuilt_cut_tolerance_mm`, `asbuilt_strip_tolerance_mm`), each a field with *not set* as its empty state. With the gate on, the Release window of the pull request of 5.1.0 asks for the reason when the records are not complete.
- **Words for the two ends of a line** (`naming.signal_counterparts`): a field in the form `TX=RX, MOSI=MISO`, with *The tool's table* and *None (equal names only)* as the two buttons `config --counterparts default|none` has, through `plan_set_counterparts`.

All of them are in *All settings* too, as links (4.3).

### 6.3 The group *Parts library* in Settings > Project

Four fields: *Name*, *Version*, *Source*, *Date of the data (YYYY-MM-DD)*, through `library_import.library_ops` (what `library DIR --library-name …` sets). The date is typed by a person; the tool never reads the clock into a project. The import of approved parts keeps writing the source (the file name and its SHA-256), as today.

### 6.4 The run record in the Export window

A check box **Write a run record (who and when, kept outside the checked files)** under *Include the open data*, off by default, as `--run-record` is; it writes `run_record.json` beside the outputs with `run_record.write_for` and the operator `run_record.resolve_operator` gives, as `--run-record` does. Its tooltip says what the record holds and that no other file changes.

## 7. Part E: *Save the import templates…* (F12)

**File > Import > Save the import templates…** and a button with the same words on the first page of the import wizard (next to *Earlier imports kept in this project*). It asks for a folder and writes the 22 files of `templates` into a **new folder `import-templates` inside it** (`templates.copy_import_templates`), or `import-templates-2`, `-3` … when that name is taken, since a person picks a folder that exists and the command's rule (*must not exist or be empty*) would refuse most choices (G11). The message names the folder and the `README.md` to start with, and offers *Open the folder*. A failure to write (no space, no right to write) is said in plain words and leaves nothing half written (the copy goes to a temporary folder beside it and is renamed). It changes no project, so it is also there without an open project.

## 8. Part F: every place from every role (F5, F7)

**The rule.** *A role hides tools, never places* (G8). Every area of `areas.AREAS` has one Go entry, and no role's hidden list holds a Go entry of an area:

| Area | Go entry | Today hidden for |
|---|---|---|
| Next step | **new** *Go to Next step* (`act-go-next`; no key: Ctrl+0 is *Real size*) | — (no entry at all) |
| Home | *Go to Home* | — |
| Model | *Go to Diagram*, *Go to Devices* | AIT (`act-go-diagram`; *Go to Devices* by the pull request of 5.1.0) |
| Checks | *Go to Checks* | — |
| Drawings | *Go to Harness* | Systems (`act-go-harness`) |
| Outputs | *Go to Lists* | Systems (`act-go-lists`) |
| As-built | *Go to As-built* | Systems, Electrical (all roles list it after the pull request of 5.1.0) |
| Review | *Go to Review* | — |
| Versions | *Go to Releases* | — |
| Settings | *Go to Settings* | — |

So the Systems role lists *Go to Harness* and *Go to Lists* again, the AIT role *Go to Diagram*, and every role the new *Go to Next step*. The side lists (*Go to Interface table*, *Go to Device list*) open panels, not areas, and stay as the roles have them. The rail does not change; the comment of `areas.py` is corrected to say *the Go menu and the command palette*. Tools stay hidden as today: the drawing tools, the alignment, the harness and wire tools in the Systems role, the editing of the diagram in the AIT role.

**The test** (`tests/test_ui_reach_roles.py`): for each of the three roles, with Quick mode off and on, on a copy of `full-connectors`:

1. every area of `AREAS` is on the rail or has a visible Go entry, and triggering that entry shows the area;
2. every area has a Ctrl+K entry;
3. every action a role leaves out of its menus is in its Ctrl+K once the state that enables it is made (a device selected for *Duplicate* and *Create redundant copy*, two for *Align …*, a harness released for *Show changes of harness…*);
4. no Go entry of an area is in `areas.HIDDEN_ACTIONS` of any role.

It replaces the Systems-only check of `tests/test_ui_systems_menus.py`, which stays for its other checks.

## 9. Part G: the registry of features and its guard

### 9.1 `core/features.py`

A table of the user-visible features, no Qt, made from the catalogue of the design of 5.1.0 (section 3.1) and the rows the audit added (the parts-library source, `explain --all`, `release --date`, the as-built tolerances, `pair_suffixes`, `signal_counterparts`):

```python
@dataclass(frozen=True)
class Feature:
    id: str                       # "waiver"
    title: str                    # "A waiver of a warning"
    page: str                     # "read-and-fix-problems.md"
    templates: tuple[str, ...]    # ("overrides-and-deviations",)
    editor: tuple[str, ...]       # ("act-…", "widget:…", "setting:FILE.KEY")
    commands: tuple[str, ...]     # ("waive",) or ("config --apply-profile",)
    api: tuple[str, ...]          # ("waive", "remove_waiver", "list_waivers")
    no_editor: str = ""           # why there is no entry in the editor
    no_command: str = ""          # why there is no command
```

An editor entry is the object name of an action (`act-values`), the object name of a widget in a place the test opens (`widget:settings-segmentation` in Settings > Project, `widget:value-derating-spare_pin_fraction` in the Engineering values window, `widget:waive` on a card of the Problems list, `widget:import-kind-build-data` in the wizard), or a row of *All settings* (`setting:naming.harness`). A context menu entry of the diagram (*Join into one harness…*) is named by its string (`string:JOIN_MENU`), checked to be used by the code that builds the menu.

A reason is one sentence for a person, printed on the page *Examples*: `compare` (*no editor entry: it compares two project folders, and the editor opens one*), `merge-fix` (*after a Git merge, outside the editor*), `schema` (*for people who edit the files in a text editor*), the drawn edits (*no command: section 10 of the design of 5.2.0; a script writes the project files*). While part B to part H are being built, each gap of the audit is a reason that names the pull request that closes it; that pull request deletes the reason and adds the entry, and the test then requires the entry to exist.

### 9.2 The guard

`tests/test_feature_reach.py`:

1. **Every command** of the parser (52 today, 55 with `waive`, `import-interfaces` and `import-connections`) is named by a feature, or in `features.NOT_FEATURES` with a reason (none is expected).
2. **Every action** `act-*` of the window is named by a feature, or in `features.WINDOW_ACTIONS` (Undo, Redo, the zoom, the panes, Reset layout, the role switches …) with a reason per group.
3. **Every setting** of `SETTINGS` and `PLAN_SETTINGS` has a row on *All settings* (`setting-<file>-<key>`) and is accepted by `settings --set` (part B).
4. **Every editor entry a feature names exists** (the window, the Settings sections, the Engineering values window, the import wizard, the Export window and a Problems card are opened on a copy of `overrides-and-deviations`), every command it names exists, every function of `api` it names is in `api.__all__`, its page exists, its templates are in `templates.TEMPLATES`.
5. **Every feature has an editor entry or a reason, and a command or a reason** (a feature that changes nothing, such as `drc`, needs no command beyond the one that reads).
6. **The table of the page *Examples*** (*Every feature and its example*) is what `python -m tools.gen_feature_docs` writes from the registry, with two columns more, *In the app* and *On the command line*, each the entry's words or the reason (the menu path comes from the action's menu; G9). `tests/test_docs.py` fails while the page is stale, as for `docs/RULES.md` and `docs/CLI.md`.

So a new command, a new menu entry or a new setting fails the tests until the person who adds it says where its other half is, or why it has none; and that answer is on the page a user reads.

## 10. Part H: the command line and the edits (the known limit)

What a script needs, and what each would take:

| Edit | A command | What this design does |
|---|---|---|
| A device from nothing | a device file and `import-devices` (exists) | The page *Script the tool* and *Use the library* say so with a minimal device file |
| Devices with the connections between them | a subsystem file and `import-subsystem` (exists) | The same pages say so |
| An interface | `import-interfaces` (part C) | Built |
| A connection between devices of the project, its pairs, a junction | `import-connections DIR FILE` | Built (G7): one row per pair (*From connector*, *From pin*, *To connector*, *To pin*, an optional *Connection* name); the rows of one pair of connectors are one connection, planned by `links.plan_add_link`; junctions as the Link window allows them; all or nothing; `--dry-run`, `--json`; no import record (a kind `connections` would be new in `ImportKind`, section 11) |
| The harness of a connection | `import-connections … --create-harness [--splice-part PART]` | Built with it: `links.plan_create_harness` per connection, the splice part asked for when a connection has a junction, as the Link window asks |
| A harness drawn by hand, its connectors, wires, groups, splices, a loose end, a leg, a join, *Edit all wires* | — | **Stays a known limit** |

**Why the drawn edits stay a limit.** Each is a chain of choices on a harness that the editor checks at every click: which connector the cable plugs into, which pin of which plug a wire takes, which wire a splice cuts, which end is loose. A command for them is either one command per edit (about twenty-five, each with the IDs of the step before) or a language of steps; both are a second way to draw that has to stay in step with the planners, and nobody has asked for it. The way a script makes a drawn harness today is the file the editor writes (`physical/harnesses/W001.json`, with its JSON Schema from `schema`), which `check` and `validate` refuse when it does not fit. The manual says this in one place (*Script the tool*) and the known-limit line of the documents says *the command line cannot draw a harness by hand, a wire, a splice, a loose end or a join; it can make devices, interfaces and connections* (section 14).

**Not proposed: `edit DIR STEPS.json`**, a list of planner calls run as one step. It would close the limit for scripts, at the price of a command language whose words are the planners' arguments, kept stable across releases. A later design can take it up when a team needs it (G7).

## 11. Release 5.2.0: no format change

5.2.0 is a minor release. Checked against what each part stores:

- **Settings** (parts A, B, D): every key that a page or a command sets is a key of `SETTINGS` or of `config/harness_plan.json` that format 5 already holds; a config file holds its values as a free table that the loader reads as it is, and `configcheck.validate` checks them. `PLAN_SETTINGS` is a table of the program, not of a file.
- **Waivers** (part C): the `Waiver` of format 5; taking one back deletes it, as `deviation --remove` and Undo do today.
- **Import records** (parts C, D): only kinds that exist (`interfaces`, the six kinds of build data). The importers of a plug-in and `import-connections` write no record, because a new `ImportKind` would be new in format 5 (frozen since `v5.0.0`); the release notes say so, and a later format can add the kinds.
- **The parts-library source and date** (part D): the `library_info` of format 5, set by the planner `library` uses.
- **The run record** (part D): a file beside the outputs, outside every hash, as today.
- **The registry and the roles** (parts F, G): the program only.
- **No written output changes**: the settings table of `export-data` keeps its rows (G2), and no rule, table or drawing changes; `tools.output_hashes --check docs/ui/OUTPUT_HASHES_BASELINE.json` and `tools.numbers_snapshot --check` stay *identical*.
- **The scripting interface** gains names (`waive`, `remove_waiver`, `list_waivers`, `import_interfaces`, `import_connections`; `set_config` takes every setting); `API_VERSION` stays 1 and the snapshot is made again on purpose. `settings --json` gains the key `plan`; the two new commands have their keys in `cli/jsonout.py`.

So a project saved by 5.2.0 opens in 5.0.0 and 5.1.0 as it opens in 5.2.0; pull request 11 opens the end-to-end project with the code of `v5.0.0`.

## 12. Edge cases

| Case | Where in the code | What the design does |
|---|---|---|
| **A profile that would add a key to a file a release froze** | `check_locks`, `FROZEN_CONFIG_FILES` | Refused with the release's reason; nothing is filled (part A) |
| **A profile filled while the form has unsaved edits** | `ConfigValueDialog` | *Fill…* is off with the reason (part A, G4) |
| **Two values a profile fills that the Engineering values window does not show** | `NEEDS`, `OPTIONAL_NEEDS` | Named in the confirmation; shown in *All settings* |
| **A name pattern Generate would not use** set by `--set` | `settings_cmd._set`, the namer | Refused by the planner; an existing one is a warning of `validate` (4.4, G3) |
| **A pattern changed after harnesses exist** | the namer | Existing IDs stay; the page says so (run of 2.2) |
| **A new config file and its placeholder flag** | `plan_set_value` (true), `settings --set` and `plan_set_choice` (false) | By the kind of file (4.1); `settings --set` on a new `derating.json` no longer says it was reviewed |
| **`--set` of a value that starts with `@`** | 4.2 | `@@` |
| **The colour codes as JSON on a command line** | `plan_config` | `--set harness_plan.colour_codes=@codes.json`; `plan_settings_edit` removes the file when every value is back to its default, as the editor does |
| **The harness plans and the settings table of `export-data`** | `open_data.settings_table` | Kept out (G2): no written file changes |
| **A setting with a place of its own, shown on *All settings*** | 4.3 | A link, not a second editor (G1) |
| **`partial_load_factor`, a table with fixed keys** | `standard_profiles.validate` | Three fixed rows, no *Add row* |
| **Waiving an error** | `checks.waive_op` | Refused with *use `deviation`*; `deviation` refuses a warning with *use `waive`* |
| **A waiver that no longer fits** | `checks.with_waiver` | `waive` replaces it; `waive DIR` marks it |
| **Taking back a waiver of a released harness's finding** | `check_locks` on `waivers` | Refused with the reason, in the editor and on the command line |
| **An interface table without headings** | `imports.guess_mapping` (positions) | `import-interfaces` refuses it and names the headings (G6); the wizard keeps its column choice |
| **A row of an interface table with a problem** | `plan_interface_import` | All or nothing, or `--skip-bad-rows` |
| **A plug-in importer that raises or hangs in the editor** | `importer.read` | Raises: reported, nothing changed. Hangs: the editor hangs, as the command does today; section 19 |
| **No trusted plug-in** | `manager.runtime` | No plug-in kind is listed; the first page says where trust is given |
| **A plug-in import and the import record** | `ImportKind` | None, as on the command line (G10) |
| **Saving the templates into a folder that exists** | `copy_import_templates` | A new folder `import-templates` (or `-2`) inside it (part E, G11) |
| **The Next step page in Quick mode** | `areas.QUICK_LISTED` | *Go > Go to Next step* (part F) |
| **A disabled action that a role hides** | `palette_entries` (enabled only) | The test makes the state that enables it (part F) |
| **A connection table that joins one pin to two** | `links.plan_add_link` | A junction, as in the Link window; `--create-harness` then needs `--splice-part` (part H) |
| **A feature whose editor entry is a context menu** | the diagram | `string:NAME` in the registry, checked to be used (part G) |

## 13. Tests

| File | What it holds |
|---|---|
| `tests/test_feature_reach.py` (pull request 1, grown by every later one) | The guard of 9.2: every command, action and setting named; every named entry, command, function, page and template exists; every feature has an entry or a reason; the page *Examples* is what the registry writes |
| `tests/test_settings_edit.py` (pull request 2) | `plan_set_value` for every key of `SETTINGS` and `PLAN_SETTINGS`: a good value, a value out of range (refused with the registry's words), empty text (the default again), a frozen file, a read-only project, the placeholder flag of a new file by kind; the name patterns (refused when set; a warning from `validate` for one already in a file); `settings --set` for each kind, `@FILE`, `@@`, `--unset`, `harness_plan.*`, the section and the key `plan` |
| `tests/test_ui_all_settings.py` (pull request 3) | One row per setting with its object name; an edit is one undo step; an error stays under the field; *Reset*; the links open the place at the value; a frozen value is off with the reason; the filter; the layout at 1024 × 700 and 1440 × 900, both themes (`tests/layout_cases.py`) |
| `tests/test_ui_release_rules.py` (pull request 4) | The three switches and the counterpart words, each one undo step through its planner; the parts-library fields; the run record of the Export window (written only when ticked, outside the hashed files) |
| `tests/test_ui_profile_fill.py` (pull request 5) | *Fill…* on a copy of `first-steps`: the confirmation lists eleven values with their requirements, one step, Undo takes it back; *kept* values; off with unsaved edits; refused on a frozen file; nothing to fill |
| `tests/test_cli_waive.py`, `tests/test_ui_take_back.py` (pull request 6) | `waive` list, record, `--remove`, the exit codes, an error refused, `--json`; *Take back…* of a waiver and of a deviation, the journal entry, a frozen harness |
| `tests/test_cli_import_interfaces.py` (pull request 7) | The template `interfaces.csv` imported; headings required; all or nothing and `--skip-bad-rows`; the record; `--dry-run` changes nothing; the same rows give the same interfaces as the wizard |
| `tests/test_import_wizard_kinds.py` (pull request 8) | *Build data* for each of the six tables of build data, the unit, a refused row, the record; a plug-in kind listed only while trusted, a plug-in that raises; *Save the import templates…* into an existing folder, into a taken name, without a project |
| `tests/test_ui_reach_roles.py` (pull request 9) | The walk of section 8 |
| `tests/test_cli_import_connections.py` (pull request 10) | Pairs, a junction, `--create-harness` with and without `--splice-part`, all or nothing, no record |
| `tests/test_e2e_520.py` (pull request 11) | One walk on a copy of each of `first-steps`, `overrides-and-deviations`, `build-data-and-as-built`, `extensions` and `released-harness`: every setting changed once in the editor and once by `settings --set`, the same file results; a profile filled in the window gives the files `config --apply-profile` gives; `waive` and *Take back…*; `import-interfaces` and the wizard give the same interfaces; the code of `v5.0.0` opens the result (no new key) |

## 14. Documents

- **`docs/user-manual/examples.md`**: the table *Every feature and its example* made from the registry, with the columns *In the app* and *On the command line* (part G); its line on standard profiles names the window.
- **`fill-in-engineering-values.md`**: *Fill from a standard profile* in the app. **`see-what-the-tool-assumes.md`**: *Settings > All settings*, `settings --set` for every key, `--unset`, `@FILE`. **`naming-and-title-block.md`**: the fields of *All settings* in place of editing JSON with the editor closed; the check of a pattern. **`export-the-harness-plans.md`**: `settings --set harness_plan.*`. **`release-a-harness.md`** and **`record-what-was-built.md`**: the group *Release rules*. **`read-and-fix-problems.md`**: `waive`, *Take back…* (the sentence *The command line cannot waive a finding* goes). **`override-and-keep-a-history.md`**: *Take back…* of a deviation. **`import-data.md`**: `import-interfaces`, *Build data* in the wizard (the sentence *There is no window for this import* goes), *Save the import templates…*. **`enter-the-build-data.md`**: the wizard. **`extend-the-tool.md`**: the importers of a plug-in in the wizard. **`export-the-data.md`**: the run record in the Export window. **`connect-two-connectors.md`** and **`script-the-tool.md`**: `import-connections`, the device file and the subsystem file as the command-line way to devices and connections, and what stays a limit. **`use-git-and-ci.md`**: `waive` in a CI script. **`choose-your-role.md`**: *A role hides tools, never places*; the Go menu of each role.
- **`docs/CLI.md`** made again (`python -m tools.gen_cli_docs`); the in-app guide made again (`python -m tools.build_guide`).
- **`docs/developer/agent/gui.md`**: the rule of part F. **`docs/developer/agent/examples-and-docs.md`**: a new command, menu entry or setting needs a row in `core/features.py`, or the tests fail.
- **`CHANGELOG.md`**, `## Unreleased`: one entry per pull request. **`docs/releases/5.2.0.md`**: the parts, *For scripts* (the new commands, `settings --json` key `plan`, the API names), *Which written files change* (none), *Not in this release* (the drawn edits on the command line, import records for plug-in imports and connections).
- **`CLAUDE.md`** of the project and **`docs/STATUS.md`**: *Not built: … command-line versions of the new edits* becomes *the drawn edits on the command line* (pull request 11).
- Not changed: `docs/FILE_FORMAT.md` (no format change), `docs/RULES.md` (no rule changes; the code `naming_pattern` is a check of `validate`, listed in the section *What is checked (ranges)* of [`CONFIG.md`](../CONFIG.md)).

## 15. Proposed decision D-270

> | D-270 | **Release 5.2.0 is a minor release that makes every feature reachable: in the editor and on the command line, from every role, with a registry of features that the tests hold every command, menu entry and setting to; no format change** (D-131, D-176, D-191, D-193, D-268; the owner's instruction of 2026-11-24 *"Make sure that no feature is hidden and that the users can actually use them."*; design `docs/ait/DESIGN_5.2_EVERY_FEATURE_REACHABLE.md`). (1) **Settings**: one planner for one setting (`configcheck.plan_set_value`) for every key of `core/settings.SETTINGS` and the three of `config/harness_plan.json` (`settings.PLAN_SETTINGS`, kept out of the settings table of `export-data`); `settings --set` for every key, `--unset`, `@FILE`; a name pattern Generate would not use is refused when set and a warning of `validate` when found; the page *Settings > All settings*, made from the registry, edits the 42 settings with no other place and links the others to theirs; the Assumptions window opens it. (2) **Standard profiles** in the Engineering values window (*Fill…*, one step, with what is set, kept and marked). (3) **`waive`** (list, record, `--remove`), the twin of `deviation`; *Take back…* of a waiver and of a deviation in the editor. (4) **`import-interfaces`** (headings required, all or nothing, `--skip-bad-rows`) and **`import-connections`** (with `--create-harness`, `--splice-part`); the drawn edits (a harness by hand, wires, groups, splices, loose ends, joins, *Edit all wires*) stay a known limit: a script writes the project files. (5) **The import wizard** gains *Build data* and the importers of trusted plug-ins (no import record, as on the command line); *Save the import templates…*; Settings > Project gains *Release rules* (different people, the as-built gate and its tolerances, the counterpart words) and *Parts library*; the Export window *Write a run record*. (6) **A role hides tools, never places**: every area has a Go entry in every role (*Go to Next step* new); a test walks every role and Quick mode. (7) **`core/features.py`**: every user-visible feature with its editor entries, commands, functions, page and templates, or a reason; tests fail on a command, an action or a setting no feature names; the table of the manual page *Examples* is made from it. **Written files**: none changes; the output-hash baseline and the numbers snapshot stay; `API_VERSION` stays 1. | The owner's answers to G1 to G13. The owner's instruction of 2026-11-24. |

The release decision of 5.2.0 is a later row.

## 16. Owner questions

Each with our recommendation first. While a question is open, the pull requests follow the recommendation.

1. **G1. One page *Settings > All settings* that lists every setting, edits the 42 that have no other place, and links the 36 that have one (Engineering values, Settings > Project, Wire colours) to it?** Recommended: yes. One place to find any setting, and one editor per value, so a table such as the ampacity or the signal map keeps its own form with its file import. Alternative: edit all 78 on the page (two editors for 36 values), or hand-made fields per group (more to build, and a new setting needs a new field).
2. **G2. The three settings of the harness plans reachable by `settings --set` and listed by `settings`, but kept out of the settings table of `export-data`?** Recommended: yes: no written file of any project changes. Alternative: in `SETTINGS` like the others (`export-data` gains three rows for every project, and the output-hash baseline is made again).
3. **G3. A name pattern that Generate would not use is refused when it is set, and a warning of `validate` (not an error) when a project already holds one?** Recommended: yes: a person learns it at the field, and no existing project starts to fail `check`. Alternative: an error of `validate` (stricter; such a project fails `check` after the update).
4. **G4. *Fill…* from a standard profile is its own step, with a confirmation of what it sets, keeps and marks, and is off while the window has unsaved edits?** Recommended: yes, the same step as `config --apply-profile`. Alternative: the profile's values put into the form as edits that *Apply* saves (one step with the person's edits, but the placeholder marks of the profile would then ride on the person's step).
5. **G5. `waive` as the twin of `deviation` (list, record, `--remove`, an error refused), and *Take back…* in the editor for a waiver and a deviation?** Recommended: yes. Today nothing takes a waiver back but Undo in the same session (section 18).
6. **G6. `import-interfaces` reads headings only (no column by position) and is all or nothing unless `--skip-bad-rows`?** Recommended: yes, as the other commands that import tables; the wizard keeps its column choice and its partial import, which a person sees before *Import*.
7. **G7. On the command line, devices and connections by files and imports (`import-devices`, `import-subsystem`, the new `import-interfaces` and `import-connections` with `--create-harness`); the drawn edits stay a known limit with the reason of section 10; no `edit DIR STEPS.json` in 5.2.0?** Recommended: yes. It covers what a script or a CI job makes from an ICD (devices, interfaces, connections, their harnesses) with planners that exist, and leaves the drawing to the editor. Alternatives: no `import-connections` either (the limit stays wider); or `edit DIR STEPS.json` (L, a command language to keep stable).
8. **G8. *A role hides tools, never places*: every area has a Go entry in every role (the Systems role lists *Go to Harness* and *Go to Lists* again, the AIT role *Go to Diagram*), a new *Go to Next step*, the rails unchanged?** Recommended: yes. It reverses the part of D-193 and R7 of 4.3.0 that took the Go entries of the detail areas out of the Systems menus; the rail, where the role's daily work is, stays lean. Alternative: also list As-built on the rail of the Electrical role.
9. **G9. A registry of features in the package (`core/features.py`), the table of the page *Examples* made from it with *In the app* and *On the command line*, and tests that fail on a command, an action or a setting that no feature names, and on a feature with no entry and no reason; built first, with today's gaps as reasons that each later pull request removes?** Recommended: yes. It is the standing guard of the owner's instruction, and the page then says, for every feature, where to find it.
10. **G10. The importers of a plug-in in the wizard, listed only while the plug-in is trusted and enabled, with no import record, as on the command line?** Recommended: yes; a record of a new kind is a format change (section 11).
11. **G11. *Save the import templates…* in File > Import and on the wizard's first page, writing into a new folder `import-templates` inside the folder a person picks?** Recommended: yes. Alternative: the command's rule (an empty or new folder only), which a folder dialog makes awkward.
12. **G12. *Release rules* and *Parts library* as groups of Settings > Project, and *Write a run record* in the Export window, off by default?** Recommended: yes: each sits where the work it changes is done.
13. **G13. 5.2.0, a minor release, no format change, no release candidate?** Recommended: yes (section 11).

## 17. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry, each deleting from `core/features.py` the reasons it closes. Estimates: S is under half a day, M one to three days, L more.

| PR | Content | Guards | Estimate |
|---|---|---|---|
| 1 | **The registry and its guard** (part G): `core/features.py` with every feature of the catalogue and today's gaps as reasons; `tests/test_feature_reach.py`; `tools/gen_feature_docs.py` and the table of `examples.md` with its two new columns; REQ-REACH-01 | *identical* | M (2 days) |
| 2 | **One planner for a setting** (4.1, 4.2, 4.4): `plan_set_value` for every key; `PLAN_SETTINGS`; `settings --set` for every key, `--unset`, `@FILE`; the name patterns; `api.set_config` for every key; `docs/CLI.md`; REQ-REACH-03 | *identical* | M (2 to 3 days) |
| 3 | **Settings > All settings** (4.3, 4.5) and the button of the Assumptions window | *identical* | L (3 to 4 days) |
| 4 | **Release rules, Parts library, the run record** (6.2 to 6.4) | *identical* | M (2 days) |
| 5 | **Fill from a standard profile** (part A) | *identical* | M (1 to 2 days) |
| 6 | **`waive` and *Take back…*** (5.1, 5.2); the API names; the snapshot made again | *identical* | M (2 days) |
| 7 | **`import-interfaces`** (5.3) | *identical* | M (1 to 2 days) |
| 8 | **The import wizard**: *Build data*, the plug-in importers (6.1); *Save the import templates…* (part E) | *identical* | M (2 to 3 days) |
| 9 | **Every place from every role** (part F): the Go entries, *Go to Next step*, `tests/test_ui_reach_roles.py`; REQ-REACH-02 | *identical* | S to M (1 day) |
| 10 | **`import-connections`** with `--create-harness` (part H, if G7 is yes); the documents of section 14 on devices and connections | *identical* | M (2 days) |
| 11 | **The preparation of 5.2.0**: the version, the changelog section, the decision rows D-270 (as decided, with what was built where it differs) and the release row, `docs/releases/5.2.0.md`, the status pages and `CLAUDE.md`, the records made again (a stamp-only renewal), `tests/test_e2e_520.py`, the code of `v5.0.0` opening its project | stamp only | M (1 to 2 days) |

About 19 to 25 working days in all. Order: 1 first (the guard the others report to); 2 before 3, 4 and 5; 6 to 10 after 1, in any order; 11 last. No pull request changes a written file of an example or a golden.

## 18. Found on the way

1. **42 settings have no editor field, not 37** (the audit's number). The 78 settings less the 29 of the Engineering values window, the 6 of Settings > Project and the wire colours leave 42; the audit's own list of them (F3) has 42 names. Section 2.2.
2. **A name pattern Generate will not use is accepted when it is set.** `settings --set 'naming.harness="H"'` and `naming.wire="{harness}"` say `1 value(s) set.`, `validate` reports nothing, and Generate then warns and uses the default (run, 2.2). Part B, 4.4.
3. **Nothing takes a waiver back**: no button in the editor, no command, no function of the scripting interface; only Undo in the same session, or an edit of `waivers.json`. A deviation can be taken back only by the command line or a script. Part C, 5.2.
4. **The Next step page has no Go entry and no Ctrl+K entry**, so in Quick mode (whose rail does not list it) it is reached only by turning Quick mode off (run). Part F.
5. **The docstring of `gui/areas.py` says the areas a role leaves out stay in the View and Go menus**; the View menu lists no area, and the Go entries of Drawings and Outputs are in the hidden list of the Systems role (Ctrl+K only). Part F corrects the code and the comment.
6. **The known limit is wider in its words than in the tool.** *The command line cannot make devices, interfaces, connections …*: it can make a device from a device file (`import-devices`) and devices with the connections between them from a subsystem file (`import-subsystem`). Section 10 and the documents of section 14 say what it can.
7. **Two values of a standard profile are not in the Engineering values window** (`rf_power_factor`, `partial_load_factor`; 2.3). Part A names them; part B shows them.
8. **`settings --set` makes a new config file as reviewed** (`placeholder: false`), also a `derating.json` of engineering values, while the Engineering values window makes it a placeholder. Part B, 4.1.
9. **The importers of a plug-in write no import record**, unlike every other import, and a record of their own needs a new kind of format 5's `ImportKind`. Kept, said in the release notes (G10).

## 19. Risks and what this design does not check

- **Nothing was looked at on a real display.** The page *All settings* (78 rows plus 3, eight headings) and the two groups of Settings > Project were not built; the layout cases of pull requests 3 and 4 measure them offscreen at two sizes, and the real-platform lane runs them.
- **The menus were counted on one template** (`full-connectors`) at one size; a project with a released harness or a selection enables more entries. The walk of part F builds those states.
- **A plug-in importer runs in the editor's process**: one that hangs hangs the editor, as it hangs the command today. The trust gate (only trusted plug-ins run) is the protection; running importers in a worker is not designed here.
- **The registry is a list someone keeps**: the guard catches a new command, action or setting, but not a new widget inside an existing window, nor a feature whose entry exists and does nothing. The end-to-end test of pull request 11 drives each named entry once.
- **The audit's runs are of one call per command on one example**, and of the context menus by reading the code; this design repeated the runs it quotes (2.2, 2.3, 2.5, 2.6) on copies of `first-steps`, `released-harness` and `full-connectors`, not the rest.
- **The pull request of 5.1.0 on `feat/reach-fixes` is assumed merged**; where it lands differently (for example *Go to As-built* only in some roles), part F's table changes with it.
- **No code was written**; the module, function and object names are the plan, and the pull requests record where they differ.
