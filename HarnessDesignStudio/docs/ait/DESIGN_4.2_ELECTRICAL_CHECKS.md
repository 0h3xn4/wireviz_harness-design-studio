# Design of 4.2.0: electrical checks

Written on 2026-11-21 from a reading of the code at the prepared 4.1.0 (the version the checkout reports, `harness 4.1.0`; `master` at `cb43f31`, D-257) and from runs of the rules, written as a throw-away script, on the five examples, on the projects of the output goldens and on a project made pinout first. It designs milestone E2 of [`ELEC_FEEDBACK_PLAN.md`](ELEC_FEEDBACK_PLAN.md) (points 2 and 8 of the feedback). Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the design of 4.1.0 ([`DESIGN_4.1_PRODUCTION_SHEET.md`](DESIGN_4.1_PRODUCTION_SHEET.md)): scope, what exists, one part per rule, the settings and the explanations, what changes in the written files, edge cases, tests, documents, the decision, the owner questions, the pull requests, the corrections to the plan and what was not checked. Choices that are the owner's are C1 to C10 (section 14), each with a recommendation first.

**Status (2026-11-21):** built and published as 4.2.0 (annotated tag `v4.2.0` on `6848510`, the merge of the preparation, #328, made by the tag workflow of D-227, run 44895952490; release workflow run 44895975583; `compliance/SIGNOFF.md`, *Publication of 4.2.0*). Pull requests 1 to 5 of section 15 are written: 1 (*Generate: the overall shield of a `single` type*) as #323; 2 (*Pairs and shields, not registered*) as #324, 3 (*Levels and directions, not registered*) as #325 and 4 (*The four rules registered*, 39 to 43 rules) as #326; and 5, the end-to-end test `tests/test_e2e_420.py`, the documents of section 11 and the release notes [`docs/releases/4.2.0.md`](../releases/4.2.0.md), as #327. The pull requests follow the recommendations of C1 to C10; no owner answer is recorded. Pull request 6 is this preparation of 4.2.0, on the branch `release/4.2.0` (decision D-259): the version 4.2.0, the changelog section, the decision rows, the status pages and the records made again with the repository's tools (a stamp-only renewal: `4.2.0` has five characters, as `4.1.0` and `2.4.0` have). The decision that records the design is D-258 (section 13); this preparation writes it into `docs/DECISIONS.md` as decided, on the recommendations of C1 to C10, with a note of what was built where it differs from section 13. 4.2.0 was published on 2026-11-21. *Added 2026-11-21, with the preparation of 4.3.0:* the minor release 4.3.0 (decision D-261; prepared, not tagged) runs the four rules of this design unchanged; the *Review* sheet and page of 4.3.0 (decision D-260) list their findings for each harness. *Added 2026-11-22, after the publication of 4.3.0:* 4.3.0 is published as the latest full release (annotated tag `v4.3.0` on `20bf8f1`, the merge of the preparation, #337; `compliance/SIGNOFF.md`, *Publication of 4.3.0*). *Added 2026-11-23, with the preparation of 4.4.0:* the minor release 4.4.0 (decision D-263; prepared, not tagged) runs the four rules of this design unchanged; the pairing that reads the far device off a pin name (decision D-262) is opt-in, and with it off a connection pairs as in 4.3.0. *Added 2026-11-23, after the publication of 4.4.0:* 4.4.0 is published as the latest full release (annotated tag `v4.4.0` on `e6eddc0`, the merge of the preparation, #348; `compliance/SIGNOFF.md`, *Publication of 4.4.0*). *Added 2026-11-23, after the publication of 4.4.1:* 4.4.1 is published as the latest full release (annotated tag `v4.4.1` on `27a3736`, the merge of #356; `compliance/SIGNOFF.md`, *Publication of 4.4.1*).

*Written before any code (kept as it was):* draft. No code is written. No owner answer yet; the owner has said that the work goes on by the recommendations, so each question of section 14 has the answer the pull requests follow while it is open. The decision that records the design is D-258 (section 13), proposed.

## 0. The frame

The engineer asked for two things in points 2 and 8: an RS422 pair must be twisted and some analog signals need their own shield; a VBUS-level signal must not meet a 3.3 V signal, and two inputs must not be joined. E2 answers them with four new design rules in a minor release:

1. **Format 4 stays frozen** (D-254). The rules read fields that format 4 has: `SignalDef.pair`, `InterfaceType.construction` and `shielding`, `ShieldGroup`, `Pin.direction` (1.9.0), `Pin.level` (format 3). Two new keys go into `config/` files, as `segmentation.mode` `per_connector_group` did (D-243); a config file holds its values as a free table, so a 4.1.x tool reads a project with the new keys, keeps them on save and says nothing (tried, section 2.6).
2. **The tool invents no value** (D-11). Which levels must not meet is the project's table, empty by default. While it is empty the level rule is silent and says *not checked* where the project holds levels.
3. **Silence must not look like a pass.** Every rule says, under `unchecked-config`, what it could not judge for lack of data, but only where the project holds the data that makes the question real (a pin with a level, a wire drawn by hand to two device pins), so that a project without such data keeps its written files.
4. **One fault, one finding.** Where a rule of today or the independent verifier already judges a case, the new rule leaves it alone: a generated wire's directions stay with `direction-conflict`, a pair of a connection with `link-direction`, the shields of a generated harness with the verifier's `shield_missing`.

## 1. Scope

### 1.1 In scope

| Rule | Severity | Finds | Reads | Points |
|---|---|---|---|---|
| `pair-untwisted` (*Twisted pairs*) | warning | two wires of a signal pair that are in no twisted group together | `SignalDef.pair` of the interface type; else the names at the device pins (`TX+`/`TX-`, `TXP`/`TXN`, `CANH`/`CANL`, the table `naming.pair_suffixes`); `ShieldGroup` | 2 |
| `signal-unshielded` (*Shielded signals*) | warning | a wire of a harness Generate did not make whose signal every interface type that has it shields, in no shield | the interface types of the signal at the wire's ends (`shielding`, `construction`, `pair`); `ShieldGroup` | 2 |
| `level-conflict` (*Signal levels*) | error, may be accepted as a deviation | a net of a harness, or a pair of a connection without a harness, that joins two device pins whose levels the project keeps apart | `Pin.level` of the device pins; `config/segregation.json` `level_pairs_to_separate` (new, empty by default) | 8 |
| `wire-direction` (*Directions of drawn wires*) | error | a net of wires drawn by hand that joins two outputs, or only inputs | `Pin.direction` of the device pins, else the interface types (`links._direction`, the review of connections) | 8 |

And with them: two settings (`segregation.level_pairs_to_separate`, `naming.pair_suffixes`), their checks in `configcheck`, four assumptions, the explanations (`derive_rules.INFO`), the rule reference (`docs/RULES.md`), four requirements (REQ-DRC-06 to 09), and one fix of the generator found on the way (section 16.1, REQ-GEN-04).

### 1.2 Not in scope

- **Levels on neighbouring pins, in one connector or in one bundle.** Section 5.1 says why the smallest useful form is *joined by a wire*; C2 asks about the others.
- **A current per pin, a split over parallel wires, splices of a harness made from a connection** (point 3): format 5, E5.
- **A shield demand per signal or per pin.** Format 4 says *shielded* only on the interface type (`shielding`, `construction`). A field for one signal of a type is a format change (E5); section 4.1 says what a team does today.
- **Directions of a generated wire read from `Pin.direction`.** A generated wire stays judged by its interface type (`direction-conflict`); section 9 names the case and C10 asks about it.
- **New commands, options or screens.** The rules appear wherever the 39 rules appear today. The new settings are set with `settings DIR --set` and in *Settings > Engineering values* (only the level table, section 7.2).
- **One-click fixes.** No rule gets a *Fix* button in 4.2.0 (`drc.fix_ops` has only *Regenerate*); *Group wires* is two clicks.
- **Everything of E3 to E5.**

## 2. What exists at 4.1.0

### 2.1 The design rules

`core/drc/rules.py` holds the registry `RULES` (order = report order): 28 rules of its own, the 11 `STANDARD_RULES` of `core/drc/standard_rules.py` spliced in after `part-unapproved`, 39 in all. A rule is `Rule(id, severity, topic, why, how, check, waivable, sources, deviation)` (`core/drc/base.py`); its check yields `Hit(object_id, title, fix_label, key)`, and `Rule.run` makes each a `Finding` whose ID is `finding_id(rule, key or object_id)`. A warning can be waived with a reason of 10 characters or more (`can_waive`); an error cannot, unless `deviation=True`, which today only the electrical rules have (`current-over-contact`, `current-over-wire`, `voltage-drop`, the working voltages, the temperature margin, `bundle-current`): `deviation DIR FINDING --reason TEXT` or *Accept as deviation* (`gui/strings.py` `DEVIATE_OK`). What a rule could not judge is a hit of `unchecked-config` (`_unchecked`, `standard_rules.unchecked`), and `drc/by_rule.py` turns them into the per-rule states of the *Checks* tab: `READS` (the keys a rule reads), `GATES` (the values that keep it *pending*), `NOTES` (which note belongs to which rule, and whether it is about a value, the data or an analysis). A test walks the registry and fails for a rule without a positive case (`tests/test_drc.py` `POSITIVE`), without an explanation (`tests/test_s1_rules.py`, `derive_rules.INFO`) or without a row in `docs/RULES.md` and a page of `docs/models/` (`tests/test_models_docs_complete.py`).

### 2.2 Twisting and shields

- **The interface type** (`core/model/logical.py`): `construction` (`single`, `twisted_pair`, `twisted_shielded_pair`, `quad`, `coax`, `twinax`), `shielding` (`none`, `overall`, `per_pair`), and on each `SignalDef` a `pair` (*signals sharing a pair name are routed as one twisted pair*). The 17 starter types (the same in all five examples) pair every differential signal (`rs422` TX and RX, `lvds` D, `can` BUS, `analog` SIG …); `rs422`, `ethernet`, `lvds` and `spacewire` shield per pair, `analog`, `can`, `mil1553b`, `pyro` and `rs485` overall, `rf_coax` is a coax.
- **Generate** (`generate/shields.py` `plan`): a coax wire is a group of its own; a quad is one group; otherwise the wires whose signals share a pair (or, for a type of category power or ground, the way out and back, `pair_names`) and start on one connector are a `twisted_pair`, or a `shielded_pair` when the type shields per pair, and the whole interface gets an `overall_shield` when it shields overall. A type of construction `single` returns before any of it (`if t.construction in ("single",): continue`), whatever its `shielding` and its pairs say (section 16.1).
- **The independent verifier** (`core/verify.py` `_check_shields`): on a generated harness, an interface whose type shields must have a group that is not a twisted pair over every wire (overall) or over at least one wire (per pair); otherwise the error `shield_missing`, reported as a finding of `verify-mismatch` with the fix *Regenerate harnesses* (`drc._verifier_findings`). A harness Generate did not make is not looked at.
- **By hand** (`core/wires.py` `plan_group_wires`, *Group wires*): `GROUP_KINDS` twisted pair (2 wires), shielded pair (2), quad (4), coax (1), overall shield (2 or more), for wires that run between the same two connectors and are **in no group yet**: a person cannot put a pair into an overall shield as Generate does, so a pair that must be twisted and shielded is one *shielded pair*. *Change group…* (`plan_regroup`) changes the kind.
- **A harness made from a connection** (`links.plan_create_harness`) has one drawn wire (`manual`) per pair, no `interface_id`, no group. A wire drawn by hand has none either (`plan_add_wire` takes no interface).
- **The rules of today** read the groups only for their ends (`shield-unterminated`, `shield-wrong-end`, `shield-bonding`, `shield-parts`). No rule says that a pair is not twisted or that a signal is not shielded.

### 2.3 Directions

- `Pin.direction` (`in`, `out`, `bidir`, empty = not set; 1.9.0) on a device pin, from a person, `import-pinout` (*Direction*) or a KiCad netlist (`use_pin_type_direction`).
- `links._direction(project, connector, pin, index)`: the pin's own direction wins; else the direction of the interface types of its signal (`devices.derive_meaning_types`, narrowed by `Connector.carries`), but empty where `direction-conflict` does not judge (a one-directional type such as `analog`, `lvds`, `pyro`, which list `out` at both ends, and a signal with no partner in its type). `links._conflict` says *both are outputs* or *both are inputs*.
- `direction-conflict` (`rules._direction_conflict`) judges each wire **with an interface**, by the directions of its type (`verify.direction_judged`, `passthrough_signals`). `link-direction` judges each **pair of a connection** (`links.check_links`, code `link_direction_conflict`), and the proposal never pairs output with output (`propose_pairs`). A wire drawn by hand has neither: no interface and no pair. In a harness made from a connection, a wire the connection does not pair is already an error of the verifier (`verify.link_issues`, *… which link L1 does not pair*), whatever its directions; in a harness drawn by hand nothing judges it.

### 2.4 Levels

`Pin.level` is free text (`Name`, at most 200 characters) from the device's ICD, such as `RS422-3V3`, `TTL-5V`, `18V` (format 3, design of 3.0.0). It is read by `import-pinout` (columns *Level*, *Signal level*, *Pin level*; `pinout_import.py`), edited in the Devices tab (column *Level*, `gui/devices_view.py`), written to the plan's `CON_…` sheets (`outputs/harness_plan.py`) and stated again by the verifier of the plan (`outputs/verify_plan.py`). **No rule reads it**, and no level word is known to the tool.

### 2.5 Nets and origins

`core/nets.py` `harness_nets(h)` gives each net of a harness: its pins, wires, ends (pins not on a splice) and splices; `end_pairs(net)` each pair of ends once. In a harness without splices every net is one wire. `core/origin.py` says whether a harness came from the interfaces, a connection or a person (`generated`, `Link.harness_id`); nothing is stored.

### 2.6 Where a finding goes

`drc.run` is called by the editor's background check (`core/drc/worker.py`, a helper process), by `drc DIR` (report; `--json` with `rules_run`), by the release (`vcs/release.release_blockers`: an open error whose object `drc.locate` places in the harness blocks it) and by `export`: `outputs/build.findings_table` writes `system/drc_findings.csv` and the sheet *DRC findings* of `system/system.xlsx`, and `drc/report.render_markdown` writes `system/drc_report.md` with the line `Rules run: 39.` The self-check of the outputs (`outputs/verify.py`, the block after `_table(files, "system/drc_findings.csv")` and `_system_workbook`) calls `checks.find` and `drc.run` again and compares; a rule has no second wording there. **The build workbook shows no finding**: its *Start here* lists only the deviations of its harness under *Overrides and deviations* (`deviations.deviation_lines`), so a finding reaches it only when someone accepts an error as a deviation. `check DIR` does not run the design rules (`cli/main.py`: validate plus the merge checks).

`tools/output_hashes.py` reads `Rules run: N.` back as `Rules run: 39.` while N has two digits (`BASE_RULES`), so a new rule alone moves no file of the baseline; `tools/numbers_snapshot.py` hashes with the same `digest`. The output goldens (`tests/fixtures/outputs/*.json`, `tests/fixtures/outputs/mini3/system/drc_report.md`, `tests/fixtures/drc/sat15.md`) and the proof of 3.0.0 (`tests/format3_support.py`, slow) read the line as it is.

A 4.1.0 tool on a copy of `flatsat` with `level_pairs_to_separate` in `config/segregation.json` and `pair_suffixes` in `config/naming.json`: `check`, `validate` and `generate` report nothing about them, `settings --set` of another key of the same file keeps them, and the outputs are those of 4.1.0.

### 2.7 The five examples and the other projects, with the four rules as specified here

Counted with a script that states the four rules of sections 3 to 6 (not the tool's code), each example made as `tools.output_hashes` makes it (`templates.create_project`, then `generate_project` when it has no harness):

| Project | Harnesses (drawn) | Links | Device pins with a direction / a level | `pair-untwisted` | `signal-unshielded` | `level-conflict` | `wire-direction` | Notes |
|---|---|---|---|---|---|---|---|---|
| `blank` | 0 | 0 | 0 / 0 | 0 | 0 | 0 | 0 | 0 |
| `first-steps` | 2 (0) | 0 | 0 / 0 | 0 (2 pairs, all grouped) | 0 | 0 | 0 | 0 |
| `minimal-satellite` | 11 (0) | 0 | 0 / 0 | 0 (6 pairs) | 0 | 0 | 0 | 0 |
| `small-satellite` | 24 (0) | 0 | 0 / 0 | 0 (15 pairs) | 0 | 0 | 0 | 0 |
| `flatsat` | 8 (0) | 0 | 0 / 0 | 0 (31 pairs) | 0 | 0 | 0 | 0 |
| `mini3`, `sat15`, `sat15_full`, `row_layout`, `custom_device` | — | 0 | 0 / 0 | 0 | 0 | 0 | 0 | 0 |
| `loose_ends` (flatsat and five drawn harnesses, `tests/loose_support.py`) | 13 (5) | 0 | 0 / 0 | **3** | **4** | 0 | 0 | **1** (directions of 2 nets of W010) |
| `splices` (`tests/splice_support.branch_leg_project`) | 4 (3) | 0 | 0 / 0 | 0 | 0 | 0 | 0 | **1** (directions of 1 net of W003) |
| pinout first: the two devices of `tests/test_e2e_harness_plan.py` (RS422 with *Direction* and *Level*), a link, *Create harness* (W001) | 1 (from the link) | 1 | 8 / 9 | **2** | **4** | 0 | 0 | **1** (`levels`: the table is empty) |
| … then a harness drawn by hand between the same two device connectors (W002: TX+ to TX+, RX+ to RX+, the 18V return to TX-, TX- to RX-) and the table `[["18V", "RS422-3V3"]]` | 2 (1 drawn) | 1 | 8 / 9 | 2 | **7** (corrected, see below) | **1** | **2** | **2** (`level-unknown`: the SGND net W001-005; `wire-direction-unknown`: W002-003, whose return pin has no direction) |

*Corrected in pull request 4, counted with the registered rules:* the last row gives **7** `signal-unshielded`, not 8 (the four wires of W001 and W002-001, W002-002, W002-004). W002-003 runs from the fixed pin `PWR_RTN` of DEV1-J01, which reads as the signal RTN of port PWR (`core/ports.py`) of the type `discrete`, which shields nothing, to TX- of DEV2-J01, which `ethernet` and `rs422` shield per pair: the types at its two ends disagree, so by the rule of section 4.1 the wire asks for no shield. Every other count of the table is as the registered rules give it (`tests/test_electrical_registered.py`).

So **no example fires**: every example harness is generated (Generate groups every pair, and the verifier judges its shields), and no example has a link, a drawn wire, a pin direction or a pin level. The findings of `loose_ends`: `W009-003`/`W009-004` (TX+/TX- of a cable from a free port, loose at the far end), `W010-001`/`W010-002` and `W013-001`/`W013-002` (1PPS+/1PPS-, by their names) are not twisted; `W009-003`, `W009-004` (TX±, which `rs422` and `ethernet` shield per pair) and `W011-001`, `W011-002` (SIG±, which `analog` shields overall; they are a twisted pair `W011-S1`) are in no shield.

## 3. Rule `pair-untwisted`

### 3.1 What it reads

For each harness, the **pairs**:

1. **Wires with an interface** (every wire of a generated harness): the wires of one interface whose signals (`Wire.signal` up to `/`, as `shields.plan` reads it) have the same `SignalDef.pair` in the interface's type and that join the same two connectors. Exactly two such wires make a pair; one, or three and more, make none (section 9).
2. **Wires without an interface** (a harness made from a connection, or drawn): two wires that join the same two connectors and, at each common connector where both have a signal, carry two signals that are a pair. The signal of an end is the device pin's when the cable connector plugs into a device connector, else the cable pin's own (as `rules._end_signal` reads it, with a fixed pin's port name read as the type's signal, `rules._type_signal`). Two signals are a pair when every interface type that has both gives them one `pair` (`TX+` and `TX-` of `rs422` and `ethernet`; `A` and `B` of `rs485`), or, when no type has both, when their names differ only by the two endings of a row of `naming.pair_suffixes` (default `+ -`, `P N`, `H L`; `1PPS+` and `1PPS-`, `TX_P` and `TX_N`, `CANH` and `CANL`), compared exactly, as port names are (D-237). The rest of the name must not be empty.

A pair is **twisted** when one group holds both wires and its kind is `twisted_pair`, `shielded_pair` or `quad`. An `overall_shield` or a `coax` is not twisting. A wire part with two conductors (`Part.conductors` 2) does not count: it says how the bill of materials counts metres, not which two wires share a piece (C5).

### 3.2 The texts

```
Rule("pair-untwisted", "warning", "Twisted pairs",
     "Two wires of a signal pair that are not twisted together pick up noise and radiate it.",
     "Select the two wires and use Group wires (twisted pair, or shielded pair if the signal needs a shield); for a harness Generate made, give the interface type a twisted construction and generate again.",
     _pair_untwisted)
```

One finding per pair; object the wire with the lower ID, key `HARNESS.WIRE+WIRE`:

| Pair from | Title |
|---|---|
| the type of the interface | `Wires W002-003 (TX+) and W002-004 (TX-) in W002 are pair TX of the interface type rs422 but are not twisted together` |
| the types of the signals | `Wires W001-001 (TX+) and W001-002 (TX-) in W001 are pair TX of the interface types ethernet and rs422 but are not twisted together` |
| the names | `Wires W010-001 (1PPS+) and W010-002 (1PPS-) in W010 are a pair by their names but are not twisted together` |

The signals in brackets are those of the end where the pair was found (the first common connector in ID order).

### 3.3 When the data is missing

Silent: a wire with no signal at a common end, two wires on different connectors, a base name shared by more than two wires. No note: the names and the groups are always there, so nothing is skipped for want of a value.

### 3.4 How it is shown and waived

`drc DIR` and the report list it under *Warnings*; the editor's *Problems* panel and the *Checks* tab (one row *Twisted pairs*); *Show* goes to the wire (`drc.locate`: the harness); *Waive…* with a reason (a pair that a short run inside a box does not twist, for example). A waiver is tied to the title (`checks.finding_hash`), so it opens again when a wire of the pair is renamed or moved. A warning does not block a release.

### 3.5 Written files

`system/drc_findings.csv`, *DRC findings* of `system.xlsx`, `system/drc_report.md` of a project that has such a pair. No example has one (section 2.7). The verifier needs no new wording (section 2.6).

## 4. Rule `signal-unshielded`

### 4.1 What it reads

Only **harnesses Generate did not make** (`Harness.generated` false): a generated harness is the verifier's (`shield_missing`, section 2.2), and two findings for one missing shield would be one too many (frame, point 4).

For each wire, the interface types of the signal at each end (the end's signal as in 3.1, its types by `devices.derive_meaning_types`, narrowed by the connector's `carries`). A type **asks for a shield** for a signal when its `shielding` is `overall`, or `per_pair` and the signal has a `pair`, or its construction is `coax`, as Generate and the verifier read a type (a type of construction `twisted_shielded_pair` with `shielding` `none` asks for no shield there, and does not here). The wire **asks** when it has at least one such type and **every** type found at its ends asks: when a team's own unshielded type has the signal `TX+` too, the types disagree and the rule says nothing (as `derive_meaning` does when types disagree).

The wire is **shielded** when a group that holds it is a `shielded_pair`, an `overall_shield`, a `coax` or a `quad` (the verifier counts every group that is not a twisted pair). A `twisted_pair` is not.

*An analog signal that needs its own shield* is said today through its interface type: a type such as `analog` (overall: each interface its own shield) or a coax. Where the signal comes from a connection, that type must have the signal's name; the rule then asks for the shield. A demand per signal or per pin is a field of format 5 (section 1.2).

### 4.2 The texts

```
Rule("signal-unshielded", "warning", "Shielded signals",
     "A signal that its interface type shields picks up and radiates noise when its wire runs without a shield.",
     "Put the wire into a shielded pair, an overall shield or a coax (Group wires; Change group... for a wire in a twisted pair).",
     _signal_unshielded)
```

One finding per wire; object the wire, key `HARNESS.WIRE`:

- `Wire W001-001 in W001 carries TX+, which the interface types ethernet and rs422 shield (per pair), but is in no shield`
- `Wire W011-001 in W011 carries SIG+, which the interface type analog shields (overall), but is in no shield (it is in twisted pair W011-S1)`

### 4.3 When the data is missing

Silent: a signal no type has, types that disagree, a wire with no signal. No note: *no type asks* is an answer, not a gap.

### 4.4 Shown, waived, written files

As 3.4 and 3.5. On the projects of the goldens it fires only on `loose_ends` (4 findings, section 2.7).

## 5. Rule `level-conflict`

### 5.1 What *meet* means

The model holds a level per device pin, the pins of each device connector in order and, since 4.0.0, the rows of its face, the nets of each harness, the pairs of each connection, and which harnesses share a route. So *meet* can mean:

| Meaning | Data | What a finding would ask the person to change | Our view |
|---|---|---|---|
| **joined**: one net, or one pair of a connection | `Pin.level` at the device ends of a net (`nets.harness_nets`, `end_pairs`), the pairs of a link | the wire, or the pin's level if the ICD was read wrongly | **the smallest useful form**: it is the engineer's example (a VBUS-level signal on a 3.3 V input), the fix is in the harness, and every fact is in the model |
| neighbouring pins on a device connector | the rows of the face (`row_layout.layout_of`, `standard_rules.face_gap`, as `power-return-adjacent` uses them) or the list of pins | the device's pinout, which is the device's ICD (D-172: the pinout is the source of truth) | not a harness fault; later, as a warning, if a team asks (C2) |
| two pins of one connector | `Connector.pins` | the device's pinout | almost every computer connector carries a supply level and a logic level: it would fire everywhere |
| one bundle or harness | the wires of a harness | the segmentation | already the job of `category-mixed` and `emc-mixed`, by category and EMC class |

The rule judges **joined**.

### 5.2 What it reads

- The table `segregation.level_pairs_to_separate` (new, section 7.1): pairs of level words that must not meet, `[["28V", "3V3"], ["VBUS", "RS422-3V3"]]`. Not set, or `null`: the rule is silent.
- For each net of each harness (generated or not): its **device ends**, the device pins that its ends plug into (a cable connector's `mates_with`; a loose end, a cable connector that plugs into nothing and a splice node are not device ends). Every pair of device ends (`end_pairs`) whose two levels are a pair of the table is a finding.
- For each connection that has no harness (`Link.harness_id` empty): each pair, with the levels of its two pins. A connection with a harness is judged through its harness, so one fault gives one finding.
- Levels are compared as whole words, the spaces around them and the case ignored (`RS422-3V3` is `rs422-3v3`). The tool reads no number out of a word: `3V3` and `3.3V` are two words, and `RS422-3V3` is not `3V3` (C3).

### 5.3 The texts

```
Rule("level-conflict", "error", "Signal levels",
     "A wire that joins two signal levels the project keeps apart can damage the device on the lower level.",
     "Move the wire to a pin of a level that fits, or correct the level of the pin (Devices tab). The pairs kept apart are config/segregation.json level_pairs_to_separate.",
     _level_conflict, deviation=True)
```

One finding per pair of device ends; object the net's first wire (or the link), key `HARNESS.WIRE.PIN+PIN`:

- `Wire W002-003 in W002 joins pin 6 of DEV1-J01 (level 18V) and pin 4 of DEV2-J01 (level RS422-3V3), two levels the project keeps apart`
- through a splice: `The wires W003-001 and W003-002 in W003 (through splice W003-X1) join pin 4 of OBC1-J01 (level 28V) and pin 2 of SENS1-J01 (level 3V3), two levels the project keeps apart`
- a connection: `Link L1 pairs pin 6 of DEV1-J01 (level 18V) with pin 3 of DEV2-J01 (level RS422-3V3), two levels the project keeps apart`

Notes under `unchecked-config` (object IDs are the keys of `by_rule.NOTES`):

| Note | When | Text |
|---|---|---|
| `levels` | the table is not set and at least one device pin has a level | `Signal levels were not checked: 9 pin(s) have a level (18V, RS422-3V3), but no pairs of levels to keep apart are set (config/segregation.json: level_pairs_to_separate)` (at most five words, then *and N more*) |
| `no-level` | the table is set and no device pin has a level | `No pin has a level yet, so the signal level check did not run` |
| `level-unknown` | the table is set and a net or pair has a device end without a level | `Signal levels were not checked for 5 net(s) (first: wire W001-005): a pin at an end has no level` |

`levels` is a note of a value (`NOTES` kind `config`, and the rule's gate, see 7.4); the other two are notes of the data. None fires on a project without levels and without the table, so no example writes one.

### 5.4 Severity, waiver, deviation

An error, as `direction-conflict` and the current rules: a 28 V supply on a 3.3 V input is not a matter of taste. It cannot be waived; it can be accepted as a **deviation** (`deviation=True`), as the electrical rules can, for the case a person knows and the table cannot (a level shifter inside the device, a pin that tolerates the level). The deviation keeps the finding on every list marked DEVIATION, puts a line under *Overrides and deviations* of the build workbook's *Start here* (`deviation_lines`; the one way a new finding reaches that workbook) and lets the release go on. An open error blocks the release of its harness (`release_blockers`, `drc.locate`: the wire's harness); a finding on a connection blocks no harness, as there is none yet. The help of `deviation` (and so `docs/CLI.md`) names the rule among those that take a deviation.

### 5.5 Written files

As 3.5, for a project with levels and a table. No example, fixture or golden has a level, so none moves.

## 6. Rule `wire-direction`

### 6.1 What it reads

Every net of a harness **all of whose wires have no interface** (every net of a harness made from a connection or drawn; none of a generated harness, whose wires stay with `direction-conflict`). For each such net, its device ends (5.2) and the direction of each by `links._direction`, the function the review of connections uses: the pin's own direction, else the interface types', else not known. A net is judged when every end is a device end and it has at least two:

- **two or more outputs**: a finding;
- **only inputs** (every end `in`): a finding;
- one output and inputs, a `bidir` or a `passive` end: no finding (a fan-out through a splice is right);
- an end whose direction is not known and no two outputs: not judged, counted for the note.

A net of two ends that a connection pairs is left to `link-direction` (frame, point 4), even when the connection's harness has been edited: the pair it describes is the link's.

### 6.2 The texts

```
Rule("wire-direction", "error", "Directions of drawn wires",
     "Two outputs on one wire drive against each other, and two inputs have nothing to drive them.",
     "Move the wire to a pin that fits, or correct the direction of the pin (Devices tab).",
     _wire_direction)
```

One finding per net; object the net's first wire, key `HARNESS.WIRE`:

- `Wire W002-001 in W002 joins pin 1 of DEV1-J01 (TX+, an output) and pin 3 of DEV2-J01 (TX+, an output): two outputs drive against each other`
- `Wire W002-002 in W002 joins pin 3 of DEV1-J01 (RX+, an input) and pin 1 of DEV2-J01 (RX+, an input): nothing drives the wire`
- through a splice: `The wires W003-001, W003-002 and W003-003 in W003 (through splice W003-X1) join 2 outputs: pin 1 of OBC1-J01 (TX+) and pin 1 of OBC2-J01 (TX+)`

Note under `unchecked-config`, `wire-direction-unknown`: `Directions were not checked for 2 net(s) of wires drawn by hand (first: wire W010-001): a pin at an end has no direction`. It fires on `loose_ends` (W010, 1PPS±, a signal no type has and no pin direction) and on `splices` (one net of W003).

### 6.3 Severity, waiver, written files

An error that cannot be waived or deviated, as `direction-conflict` and `link-direction`: the fix is the wire or the pin's direction, and a wrong direction in an ICD is corrected at the pin. It blocks the release of its harness. Written files as 3.5; the goldens that move are those of section 8.

## 7. Settings, checks, assumptions, explanations and the rule reference

### 7.1 Two settings (`core/settings.py`)

```
Setting("segregation", "level_pairs_to_separate", "Signal levels kept apart", "", "pairs", None,
        "Pairs of signal level words (the Level of a pin, as its ICD writes it) that a wire, a net or a pair of a connection must not join.",
        "rule level-conflict", _PROJECT, "pairs of two different words, each pair once", assumption="A-LEVEL-WORDS")
Setting("naming", "pair_suffixes", "Endings that make two signals a pair", "", "pairs", (("+", "-"), ("P", "N"), ("H", "L")),
        "Two signals whose names differ only by these two endings (TX+ and TX-, TXP and TXN, CANH and CANL) are the two wires of a pair, where no interface type pairs them.",
        "rule pair-untwisted", "the tool's own words (4.2.0, D-258)", "pairs of two different endings of 1 to 3 characters", assumption="A-PAIR-NAMES")
```

`level_pairs_to_separate` has no default and is in no file of the examples, the templates or `samples.start_project`: the tool ships no level word (D-11). `pair_suffixes` has a default, as `signal_counterparts` has `DEFAULT_COUNTERPARTS`: a naming convention, not an engineering value.

### 7.2 `configcheck`

- `OPTIONAL_NEEDS` gets `Need("segregation", "level_pairs_to_separate", "pairs of signal level words that must not be joined, for example [[\"28V\", \"3V3\"]]", "signal level check")`; it is not on the hand-over list (`NEEDS`), so `config DIR` and the placeholder answers do not change.
- `validate`: `level_pairs_to_separate` with `_pairs_ok` (*must be a list of pairs of two different names, each pair once*), each word at most 200 characters and compared after trimming and folding the case, so `["3V3", "3v3"]` is refused as a pair of one word; `pair_suffixes` as pairs of two different endings of 1 to 3 characters (letters, digits, `+`, `-`), each pair once, no ending in two rows. Code `config_invalid`, as every refused value; a refused table keeps its rule silent and `config-invalid` says why.
- `FIELD_INFO` gets the level table for *Settings > Engineering values*: `FieldInfo("Signal levels kept apart", kind="pairs", hint="Write pairs joined by +, separated by commas, like 28V + 3V3")`. A level word that holds `+` or `,` cannot be typed there; `settings DIR --set segregation.level_pairs_to_separate='[["+5V", "3V3"]]'` takes any word. `pair_suffixes` gets no field (its endings are `+` and `-`); it is set with `settings --set`, as the counterpart words are set with `config --counterparts`.

### 7.3 Assumptions (`core/assumptions.py`)

| ID | Kind | Text (short) |
|---|---|---|
| `A-PAIR-NAMES` | setting (`naming.pair_suffixes`) | Two wires that no interface type pairs are a pair when they join the same two connectors and their signals at a common end differ only by the endings of a row of the table. |
| `A-SHIELD-BY-TYPE` | built in (`core/drc/electrical.py`) | A wire of a harness Generate did not make asks for a shield when every interface type that has its signal shields it; a signal no type has asks for none. |
| `A-LEVEL-WORDS` | setting (`segregation.level_pairs_to_separate`) | Two levels meet when one net, or one pair of a connection without a harness, has device pins of both; levels are compared as whole words, case and outer spaces ignored; no number is read from a word. |
| `A-DIRECTION-AT-DEVICE` | built in | The directions of a net of wires drawn by hand are those of the device pins it ends on, read as the review of connections reads them; a net with an end that plugs into no device is not judged. |

`tests/test_models_docs_complete.py` (c) asks for each on a page of `docs/models/`: the first two on `shields.md`, the last two on `rule-limits.md`.

### 7.4 `by_rule`, explanations, the rule reference

- `drc/by_rule.py`: `READS["level-conflict"] = (("segregation", "level_pairs_to_separate"),)`, `READS["pair-untwisted"] = (("naming", "pair_suffixes"),)`; `GATES["level-conflict"]`: *pending* while the table is not set (the *Checks* tab shows the value it waits for, as for `category-mixed`; screen only); `NOTES`: `levels` (`config`, a gate note), `no-level`, `level-unknown` and `wire-direction-unknown` (`data`).
- `derive_rules.INFO`: one `RuleInfo(YES_NO, …)` each, with an `observe` that says what the rule saw at the wire: the pair and where it came from (type or names) and the groups; the types and whether each asks for a shield; the levels at the device ends and the table's pair; the direction of each end and where it came from (pin or type). `explain DIR FINDING` and the editor's *Explain* show it; `derive_kinds.page_of_rule` sends the reader to `shields.md` (the first two) and `rule-limits.md` (the last two). No new kind of derivation, so `explain --all` writes the same files.
- `docs/RULES.md` is made again (`python -m tools.gen_rule_docs`); its line *never part of the 39* (from `tools/gen_rule_docs.py`) says 43.
- No standard requirement is cited (`sources=()`): `compliance/assessment/design_assessment.csv` names none for twisting, per-signal shielding, levels or directions. Pull request 4 cites one only if the assessment gets a row that names it.

### 7.5 The code

A new module **`core/drc/electrical.py`**, as `standard_rules.py` is for the rules of the standards: the four checks, their helpers (`signal_pairs(project, h)`, `shield_asked(project, conn, pin)`, `device_ends(project, h, net)`), `ELECTRICAL_RULES` (spliced into `RULES` after `direction-conflict`, so the report keeps the signals together) and `unchecked(project)`, which `_unchecked` calls. It imports `links._direction` and `_conflict` (made public as `links.pin_direction` and `links.direction_conflict`, the old names kept) and `nets.harness_nets`; no import of the generator. The cost is one pass per harness; pairs are found per pair of connectors, not over every two wires.

## 8. What changes in the written files, and the guards

| Written file | Change | Which projects | Guard |
|---|---|---|---|
| `system/drc_report.md` | `Rules run: 43.` in place of `39.` | every project | `tools.output_hashes --check`: **identical** (it reads 43 back as 39, `BASE_RULES`); `tools.numbers_snapshot --check`: **identical** (same `digest`; no scenario's findings change) |
| `system/drc_report.md`, `system/drc_findings.csv`, *DRC findings* of `system.xlsx` | new findings and notes | projects with a drawn or connection harness that has a pair, a shielded signal or a net of known directions; projects with levels | none of the examples (section 2.7) |
| build workbook, *Start here* | a line under *Overrides and deviations* | a project that accepts a `level-conflict` as a deviation | none of the examples |
| every other file | nothing | — | — |
| generated harnesses (section 16.1) | an `overall_shield` group for an interface of construction `single` that shields overall, so its wires list, cut list, Production sheet, drawings and BOM name it | projects with such a type | none of the examples, templates or fixtures has one (checked: every `interface_types.json` under `tests/fixtures` and `resources`) |

**The goldens that move** (pull request 4, renewed for that one reason): every `tests/fixtures/outputs/*.json` (`mini3`, `sat15`, `sat15_full`, `loose_ends`, `splices`, `row_layout`: the digest of `system/drc_report.md`; for `loose_ends` also `drc_findings.csv` and `system.xlsx`, 7 warnings and 1 note more; for `splices` 1 note more), the text `tests/fixtures/outputs/mini3/system/drc_report.md` and `tests/fixtures/drc/sat15.md`. The plan goldens (`tests/fixtures/outputs/harness_plan/`) do not move: a plan holds no finding.

**The proof of 3.0.0** (`tests/test_format3.py::test_the_written_files_of_3_0_are_those_of_2x_after_the_word_list`, slow, run on `master` and by `tools.release_check`, not on a pull request) compares `system/drc_report.md` of seven recorded projects as text. Pull request 4 adds **step 9** to `tests/format3_support.py`: *the step of 4.2.0 (design of 4.2.0, section 8): the line `Rules run: 39.` of `system/drc_report.md` reads `Rules run: N.` with N the number of rules of this tool*; nothing else of the record changes, because no recorded project (the four examples, `mini3`, `custom_device`, `mini3-released`) has a finding of the new rules. A fast test beside the tests of steps 7 and 8 shows that step 9 changes that one line and that a finding added by hand is still reported. Pull request 4 runs the slow tests (`pytest -m slow`) before it is merged, as pull requests 3 and 5 of 4.1.0 did; the merge of #311 had left the proof red on `master` for want of its step. Pull request 1 (the generator) runs them too, as a check that no recorded project has the type it changes. `test_the_numbers_snapshot_keeps_every_readable_number` stays green (no scenario's findings change).

**The verifier.** The findings files are checked by calling the rules (section 2.6), so no output text needs a second wording. What stands for the independent check is in the tests (section 10): each rule is compared with a second statement of the same question that shares no code with it: the pairs of `pair-untwisted` on a generated harness with the groups `generate/shields.plan` makes; `wire-direction` on a drawn copy of a harness made from a connection with `link-direction` on the connection; the nets of `level-conflict` with `verify.splice_nets`, the verifier's own copy of the nets.

## 9. Edge cases found in the code

| Case | Where in the code | What the design does |
|---|---|---|
| **A wire's signal `TX+/RX+`** | `links._wire_signal`; Generate's `w.signal` | Rules 1 and 2 of a drawn wire read the signal at each device pin, not `Wire.signal`; a generated wire's pair is read from the text before `/`, as `shields.plan` does |
| **Port names** (`RS422_2_TX+`) | `core/ports.py`, `rules._type_signal` | A fixed pin's port name is read as the type's signal before the types are asked; by the names, `RS422_2_TX+` and `RS422_2_TX-` differ only by `+`/`-` |
| **A type of construction `single` with pairs** | `shields.plan` skips `single` | Generate makes no pair group; `pair-untwisted` fires on the generated harness with the fix *give the type a twisted construction* |
| **A type of construction `single` that shields overall** | `shields.plan`; `verify._check_shields` | Today Generate makes no shield and the verifier reports `shield_missing` that *Regenerate* cannot fix; pull request 1 makes the overall shield (16.1) |
| **A per-pair type with an unpaired signal** (a GND in a per-pair type) | `shields.plan`: only paired signals are grouped | That signal asks for no shield (4.1) |
| **`twisted_shielded_pair` with `shielding` `none`** | `shields.plan`, `_check_shields` read `shielding` | Asks for no shield, as Generate and the verifier read it |
| **A quad** | `ShieldKind` `quad`; `_check_shields` counts it as covering | Twisted for rule 1, shielded for rule 2 |
| **A pair in an overall shield** (Generate) | `wires.plan_group_wires` takes only wires in no group | Both groups are read; by hand the same is one *shielded pair* |
| **Three wires of one base name** (`TX+`, `TX-`, `TX+` again on two pins) | `shields.plan` groups any number | Not a pair: silent (3.3) |
| **A split pair** (TX+ to J1, TX- to J2) | — | Not on the same two connectors: silent |
| **A loose end** (role `loose`), a cable connector that plugs into nothing | `tables.is_open_end`, D-201 | Rules 1 and 2 read the cable pin's signal (W009 of `loose_ends`); rules 3 and 4 skip the net, which has an end that is no device pin |
| **A splice** | `core/nets.py` | Rules 3 and 4 judge the net; rule 1 judges two wires that join the same two connectors (a splice is one of them); rule 2 is per wire |
| **Two wires on one pin** (`pin-shared`) | `rules.shared_pins` | They are one net for rules 3 and 4 |
| **A harness made from a connection, edited** | `verify.link_issues` (`link_wire_mismatch`) | A wire the connection does not pair is the verifier's error and also judged by rules 3 and 4; a pair of the connection stays with `link-direction` |
| **One-directional types** (`analog` SIG+/SIG-, `lvds`, `pyro`, `i2c` SCL) | `verify.direction_judged`; `links._direction` returns empty | Not known: no finding; counted for the note only when a device pin has no direction of its own |
| **`bidir` and `passive`** | `links._conflict` | Never a conflict |
| **A person's direction on a generated wire's pins** | `direction-conflict` reads the type | Unchanged in 4.2.0 (C10) |
| **A level word with `+` or `,`** | `FIELD_INFO` *pairs* form | `settings --set` with JSON (7.2) |
| **Level words that differ in case or outer spaces** | `Pin.level` is free text | The same word (5.2) |
| **A released harness** | `vcs/locks`, `released-modified` | Findings are still reported; a warning can be waived; an error blocks only a new release; the fix needs a new version |
| **A project of an older format** | `core/io/upgrade.py` | The rules read fields of format 3 and 4; an older project is upgraded before it is saved, as today |
| **Extensions** | `core/extensions`; `report.render_markdown` adds `rules_for(project)` | `Rules run` counts 43 plus the project's own; rule IDs of extensions start with `x-`, so they cannot take the new IDs |

## 10. Tests to write

| File | What it holds |
|---|---|
| `tests/test_shields_single_overall.py` (pull request 1) | A type of construction `single` with `shielding` `overall` gets one `overall_shield` per interface; `verify_project` reports no `shield_missing`; `explain` of the group says why; a type with `shielding` `none` gets nothing; the examples' plans of Generate are unchanged |
| `tests/test_rule_pair_untwisted.py` | Pairs from the type, from the types of the signals, from the names (`+ -`, `P N`, `H L`, a table of the project), port names; twisted by `twisted_pair`, `shielded_pair`, `quad`, not by `overall_shield` or a pair part; silent for three wires of a base, a split pair, a wire with no signal; the generated harness of a `single` type with pairs; **on every example, with its groups taken away, the pairs found equal the twisted and shielded pairs of `generate/shields.plan`** |
| `tests/test_rule_signal_unshielded.py` | Types that agree and disagree, `carries` narrowing, per pair with an unpaired signal, coax; a twisted pair is no shield; a generated harness is left to the verifier (one finding, not two); the four findings of `loose_ends` |
| `tests/test_rule_level_conflict.py` | A wire, a net through a splice, a pair of a connection without a harness, a connection with a harness (judged once); case and spaces; `3V3` against `RS422-3V3` (no finding); the three notes and when each is silent; a deviation and the line of *Start here*; the release blocked, and not blocked after the deviation; the nets compared with `verify.splice_nets` on random harnesses |
| `tests/test_rule_wire_direction.py` | Out to out, in to in, a fan-out through a splice (no finding), two outputs through a splice, a loose end (not judged), a pair of a connection (left to `link-direction`), `Pin.direction` over the type, a one-directional type (silent), the note; **Hypothesis: on a harness made from a connection with random pin directions, the findings of `wire-direction` on the harness with the connection removed equal the `link_direction_conflict` findings of the connection** |
| `tests/test_configcheck_levels.py` | `level_pairs_to_separate` and `pair_suffixes`: accepted and refused values, the texts of `config_invalid`, the *pairs* form, `settings --set`; a 4.1 project with the keys loads, saves and keeps them |
| `tests/test_drc.py` | A positive case of each rule in `POSITIVE`; quiet on the clean project |
| `tests/test_format3.py` | Step 9 (section 8) |
| `tests/test_e2e_420.py` | One project end to end through the command line: `new --template blank`, two devices by `import-pinout` with *Direction* and *Level*, a connection and its harness (the tool's own planners, as `tests/test_e2e_harness_plan.py` adds its interface), `drc` (two `pair-untwisted`, four `signal-unshielded`, the note `levels`), `settings --set` of the level table, a harness drawn by hand between the same device connectors, `drc` again (two `wire-direction`, one `level-conflict`, seven `signal-unshielded`, section 2.7), *Group wires* as a shielded pair, a waiver, a deviation, `release` blocked and then not, `export`, `verify --outputs` |

The tests that count the rules or the findings of drawn harnesses change with pull request 4: `len(RULES) == 39` and `rules_run == 39` (`tests/test_s1_rules.py`, `test_drc_by_rule.py`, `test_api.py`, `test_api_stability.py`, `test_cli_json.py`, `test_ux_checks.py`, `test_gui_drc.py`, `test_not_checked_without_data.py`, `test_models_docs_complete.py`, `test_device_equivalence.py`, `test_loose_end.py`, `test_extensions_plugins.py`, `test_links_files.py`), and any test that reads the findings of `loose_ends` or `splices`.

The requirements, in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`): **REQ-DRC-06** (`pair-untwisted`), **REQ-DRC-07** (`signal-unshielded`), **REQ-DRC-08** (`level-conflict`, silent while the table is empty, the notes), **REQ-DRC-09** (`wire-direction`), each with a positive and a negative test; **REQ-GEN-04** (Generate makes the shield every interface type asks for, so its own verifier finds no `shield_missing`).

## 11. Documents to update

- `CHANGELOG.md`, `## Unreleased`: one entry per pull request; for pull request 4 the reason for the renewal of the goldens and the step of the proof.
- `docs/releases/4.2.0.md`: the four rules, the two settings, the fix of Generate; *For scripts*: `rules_run` is 43 and `api.list_rules()` has four more entries; *Upgrade*: a 4.1.x tool ignores the new keys (section 2.6), so it shows none of the findings; *Known limits* (section 17).
- `docs/RULES.md` (`python -m tools.gen_rule_docs`), `docs/CLI.md` (`python -m tools.gen_cli_docs`: the help of `deviation`), `docs/CONFIG.md` (the two keys, test (d)), `docs/models/shields.md` and `rule-limits.md` (the rules, the assumptions, the pairs Generate makes for a `single` type), `docs/REQUIREMENTS.md`.
- Every page that says 39 rules: `docs/user-manual/read-and-fix-problems.md` (also the example line *Rules run*), `generate-harnesses.md`, `use-hds-in-your-organisation.md`, `extend-the-tool.md`, `docs/GETTING_STARTED.md`, `CLAUDE.md` (*39 design rules*), `docs/developer/agent/core.md`, the docstrings of `gui/checks_panel.py`.
- User manual: `connect-two-connectors.md` (what is checked on a harness made from a connection), `build-a-harness-by-hand.md` and `edit-a-wire.md` (*Group wires* answers `pair-untwisted` and `signal-unshielded`; why a pair that needs a shield is a shielded pair), `see-what-the-tool-assumes.md` (the two settings, the four assumptions), `import-a-pinout` pages (the *Level* and *Direction* columns now feed two rules), and the in-app guide (`python -m tools.build_guide`).
- `docs/GLOSSARY.md`: *Signal pair*, *Level*.
- `docs/ait/ELEC_FEEDBACK_PLAN.md`: its status (E2 designed) and the corrections of section 16.
- Not changed: `docs/FILE_FORMAT.md` (no key of a project file; the config keys are in `CONFIG.md`), `docs/OUTPUTS.md` (no new file or column).

## 12. What does not change

The project format and `SCHEMA_VERSION` (4); `system/export.json` (`format_version` 2); every written file of a project without such data, apart from the line `Rules run`; the 39 rules of today, their IDs, texts and order among themselves; the verifier (`core/verify.py`, `core/outputs/verify*.py`); the command line's commands and options; the scripting interface's names (`API_VERSION` 1; `list_rules` and `run_checks` return more rules); `check`; the build workbook, the plan and the Production sheet of 4.1.0.

## 13. Proposed decision D-258

> | D-258 | **Release 4.2.0 is a minor release with four electrical design rules (milestone E2 of `docs/ait/ELEC_FEEDBACK_PLAN.md`); no format change** (D-254, D-256; design `docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`). (1) `pair-untwisted` (warning): two wires of a signal pair, from the `pair` of the interface type or, for a wire without an interface, from the types of the signals at its device pins or from the endings of `config/naming.json` `pair_suffixes` (default `+ -`, `P N`, `H L`), that no twisted pair, shielded pair or quad holds together. (2) `signal-unshielded` (warning): a wire of a harness Generate did not make whose signal every interface type that has it shields, in no shield; a generated harness stays with the verifier's `shield_missing`. (3) `level-conflict` (error, may be accepted as a deviation): a net, or a pair of a connection without a harness, that joins two device pins whose levels are a pair of `config/segregation.json` `level_pairs_to_separate`, compared as whole words; the table is empty by default and the tool ships no level word (D-11), so the rule is silent until a project fills it, and says *not checked* where pins have levels. (4) `wire-direction` (error): a net of wires drawn by hand that joins two outputs, or only inputs, by the directions the review of connections reads; a generated wire stays with `direction-conflict`, a pair of a connection with `link-direction`. Each rule notes under `unchecked-config` what it could not judge, only where the project holds the data. (5) Generate makes the overall shield of an interface type of construction `single` that shields overall (it made none, and its own verifier refused the harness). **Written files:** `Rules run: 43` in every DRC report; findings only for projects with such harnesses or levels, none of the examples; the output goldens and the proof of 3.0.0 (its step 9) are renewed for the count. | The owner's answers to C1 to C10. The engineer's feedback of 2026-11-20 (points 2 and 8). |

The release decision of 4.2.0 is a later row (D-259), as D-257 followed D-256.

## 14. Owner questions

Each with our recommendation first. While a question is open, the pull requests follow the recommendation.

1. **C1. The four rules with these IDs and severities: `pair-untwisted` and `signal-unshielded` warnings, `level-conflict` an error that may be accepted as a deviation, `wire-direction` an error?** Recommended: yes. A pair that is not twisted and a missing shield are risks a person may accept with a reason; a level clash and two drivers on one wire are faults. The deviation for `level-conflict` covers what a table of words cannot know (a level shifter in the device).
2. **C2. Levels *meet* when one net (or one pair of a connection without a harness) joins them, and not when they sit on neighbouring pins, in one connector or in one bundle?** Recommended: yes, in 4.2.0 (section 5.1). Neighbouring pins are the device's pinout from its ICD, which the harness cannot change; one connector would fire on nearly every computer; one bundle is `category-mixed` and `emc-mixed`. If a team asks for neighbours, a later warning `level-adjacent` can use the rows of the face as `power-return-adjacent` does.
3. **C3. The level table as pairs that must not meet (`segregation.level_pairs_to_separate`), words compared whole with case and outer spaces ignored, empty by default?** Recommended: yes. The other form, pairs that *may* meet, would make every two different words an error until listed. Reading a voltage out of a word (`3V3` = 3.3 V) is a guess the tool must not make (D-11). We still need the team's level words (plan question 5).
4. **C4. Pairs by name for wires that no interface type pairs, with the endings `+ -`, `P N`, `H L` as the default of a setting `naming.pair_suffixes`, compared exactly?** Recommended: yes. Teams name pairs in their own way (concern Cb); a setting lets one take `H L` out if it names other things `…H`/`…L`. Exact comparison, as port names (D-237).
5. **C5. A wire part with two conductors does not make two wires a twisted pair; only a group does?** Recommended: yes. `Part.conductors` says how the bill of materials counts metres, not which two wires share one piece of cable; the group is the one record of that, and it is on the cut list and the Production sheet.
6. **C6. The shield demand of a wire without an interface from the interface types of its signal, only when every type that has the signal agrees; a generated harness left to the verifier?** Recommended: yes. It reads the types the project holds, as `link-direction` reads them for directions; a signal no type has asks for nothing (no guess), and one fault gives one finding.
7. **C7. Fix Generate for a type of construction `single` that shields overall (section 16.1) in 4.2.0, not in a patch 4.1.1?** Recommended: in 4.2.0, as its pull request 1. No example, template or fixture has such a type, and the fix changes the generated harnesses of a project that has one; a patch would be fine too if a team reports it first.
8. **C8. The notes *not checked* only where the project holds the data (a pin with a level, a net drawn by hand to device pins), so that a project without such data writes the same files?** Recommended: yes. The *Checks* tab still shows `level-conflict` as *pending* while the table is empty, on every project, on screen only.
9. **C9. Renew the output goldens and add step 9 to the proof of 3.0.0 for the line `Rules run: 43`, in the one pull request that registers the four rules?** Recommended: yes, one renewal for one reason, the slow tests run before the merge.
10. **C10. A generated wire whose two device pins both carry a person's direction (`Pin.direction`) stays judged by its interface type only?** Recommended: yes in 4.2.0; `direction-conflict` reads the type, and a pinout that contradicts its type is the business of the connection review and the import. Ask the engineer whether it happens once they use 4.2.0.

## 15. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry.

| PR | Content | Guards |
|---|---|---|
| 1 | **Generate: the overall shield of a `single` type.** `generate/shields.plan` makes an `overall_shield` over the wires of an interface whose type has construction `single` and `shielding` `overall`; `derive_build` explains it; `docs/models/shields.md`; `tests/test_shields_single_overall.py`; REQ-GEN-04 | `output_hashes --check` and `numbers_snapshot --check` *identical*; goldens unchanged; slow tests run (no recorded project has such a type) |
| 2 | **Pairs and shields, not registered.** `core/drc/electrical.py` with `_pair_untwisted`, `_signal_unshielded` and their helpers; the setting `naming.pair_suffixes` (`settings.py`, `configcheck.validate`), `A-PAIR-NAMES`, `A-SHIELD-BY-TYPE`, `docs/CONFIG.md`, the assumptions on `docs/models/shields.md`; `tests/test_rule_pair_untwisted.py`, `test_rule_signal_unshielded.py` (calling the checks directly) | *identical* everywhere: no rule is registered |
| 3 | **Levels and directions, not registered.** `_level_conflict`, `_wire_direction`, `electrical.unchecked`; `links.pin_direction` and `direction_conflict` (public names of `_direction`, `_conflict`); the setting `segregation.level_pairs_to_separate` (`settings.py`, `OPTIONAL_NEEDS`, `validate`, `FIELD_INFO`), `A-LEVEL-WORDS`, `A-DIRECTION-AT-DEVICE`, `docs/CONFIG.md`, `rule-limits.md`; `tests/test_rule_level_conflict.py`, `test_rule_wire_direction.py`, `test_configcheck_levels.py` | *identical* everywhere |
| 4 | **The four rules registered (39 to 43).** `ELECTRICAL_RULES` in `RULES`, the notes in `_unchecked`; `POSITIVE`; `derive_rules.INFO` and `page_of_rule`; `by_rule` `READS`, `GATES`, `NOTES`; `deviation`'s help; `docs/RULES.md`, `docs/CLI.md`; every *39* of section 10 and 11; REQ-DRC-06 to 09 and `tools.trace`; step 9 of the proof and its fast test; the goldens of section 8 | `output_hashes --check` and `numbers_snapshot --check` *identical*; the goldens renewed for the count (and the 7 + 1 findings of `loose_ends`, the note of `splices`), read file by file; **the slow tests run before the merge** |
| 5 | **End to end and documents.** `tests/test_e2e_420.py`; the user manual pages, the guide, `GLOSSARY.md`, `docs/releases/4.2.0.md` | — |
| 6 | **The preparation of 4.2.0**: version, changelog section, the decision rows D-258 (as decided, with what was built where it differs) and D-259, the status pages | stamp only (`4.2.0` has five characters) |

Order: 1 first; 2 and 3 in either order after it; 4 after both; 5 after 4; 6 last. **4.1.0 is tagged before pull request 1 is merged**, because from 1 on `master` generates other harnesses than 4.1.0 for a project with such a type, and from 4 on writes another DRC report for every project; a 4.1.x patch from `master` would carry them.

Why the rules are written in 2 and 3 and registered in 4: the count of the rules is read in thirteen test files, in the report of every golden and in the proof of 3.0.0. Registering them one at a time would renew all of it four times (39, 40, 41, 42, 43), and each renewal would be a review of every golden; one count change is one review. Pull request 1 of 4.1.0 also landed its core with no caller.

## 16. Corrections to the plan, and what was found on the way

Checked against the code at 4.1.0 and the runs of section 2.7.

1. **Found: Generate makes no shield for a type of construction `single` that shields overall, and its own verifier then refuses the harness.** `generate/shields.plan` returns for `single` before it reads `shielding`. On a copy of `flatsat` with the types `discrete` and `i2c` set to `shielding` `overall` and generated again, `verify_project` reports `shield_missing` for IF-040 (W002-025, W002-026) and IF-041 (W006-011, W006-012), and `drc` lists them as two `verify-mismatch` errors whose fix, *Regenerate harnesses*, changes nothing. None of the starter types is such a type, so no project made from a template has met it. Pull request 1 fixes it.
2. **A missing shield of a generated harness is already found.** The plan says *no rule says … "this analog signal needs its own shield"*. For a generated harness the verifier says it (`shield_missing`, an error, since 1.x); the gap is in the harnesses made from a connection or by hand, whose wires have no interface type. `signal-unshielded` judges those only (section 4.1).
3. **A pair that must be twisted and shielded is one group when a person makes it.** The plan says *a person groups wires in the editor (Group wires)*. `plan_group_wires` takes only wires in no group, so the twisted pair inside an overall shield that Generate makes cannot be made by hand; the person makes a *shielded pair*. The fix texts say so.
4. **A wire drawn into a harness made from a connection is already an error.** The plan says *a wire drawn by hand is judged by neither* (`link-direction`, `direction-conflict`). That holds for a harness drawn by hand; in a harness made from a connection, a wire that the connection does not pair is the verifier's `link_wire_mismatch` error, whatever its directions (`verify.link_issues`). `wire-direction` adds the direction to such a wire and is the only judge in a drawn harness.
5. **Findings do not reach *Start here*.** The build workbook lists no finding; only a deviation of its harness reaches *Start here* (`deviation_lines`). The findings are in `system/drc_findings.csv`, `system.xlsx` and `system/drc_report.md` (section 2.6).
6. **No example pin has a direction or a level, and no example has a link or a drawn wire**, so the new rules cannot be shown on the examples. The project of `tests/test_e2e_harness_plan.py` (two devices imported with *Direction* and *Level*) shows them (section 2.7); the next demo should use such a project.
7. **Found by pull request 5: `explain` takes no finding ID on the command line.** Section 7.4 says *`explain DIR FINDING` and the editor's Explain show it*; `explain DIR OBJECT` takes a wire, a harness, a connector and the other objects of its help, not a finding (`… is not a wire, a harness or a part …`). What each rule saw is in the editor's *Explain*, in `derivations.json` of `explain DIR --all --out FOLDER` (a derivation `rule-check` per finding) and in `api.explain_finding`; `tests/test_e2e_420.py` reads it from `derivations.json`. A finding ID for `explain` would be a new form of its argument, left for later; the changelog of pull request 4 and the release notes say what there is.
8. **Found by pull request 5, fixed there: the explanation of a `pair-untwisted` finding showed `naming.pair_suffixes` as `++-, P+N, H+L`.** `derive_rules.yes_no_derivation` showed each setting a rule reads with `settings.display`, which joins a pair with `+`; it now uses `settings.display_of`, which shows the endings as `settings` does (`+ -, P N, H L`) and every other value as before. No written file of the goldens holds such an explanation.

## 17. Risks and what this design does not check

- **No team's level words are known.** The template's words are `TTL-5V`, `RS422-3V3`, `LVDS`, `18V`, `3V3` (the tooltip of the *Level* column); the rule is as good as the table a team writes and the words its ICDs use (plan question 5).
- **Names by endings can pair two wires that are no pair** (a `HEATER_H` and `HEATER_L` that are high and low side of one heater). The finding is a warning; a waiver or a project table without `H L` answers it.
- **Types that share a signal name can disagree** about shielding (a team's own unshielded type with `TX+`); then `signal-unshielded` is silent for that signal. `explain` names the types it read.
- **One finding per wire** for `signal-unshielded`: a connection with ten RS422 lines gives forty findings until it is grouped. One finding per pair or per harness was weighed; per wire keeps *Show* and the waiver on one object.
- **The counts of section 2.7 come from a script that states the rules as written here**, not from the tool's code. Pull request 4 lists what moves in each golden; a difference from these counts is read before the renewal.
- **Directions read from the interface types are a reading of names.** A direction set on the pin wins; the import of a pinout with a *Direction* column is the way to make the rule rest on the ICD.
- **Nobody at a bench or a review has seen the findings.** The texts are this design's; the engineer should read the findings of the pinout-first project before 4.2.0 is tagged.
- **No code was written**; the module and function names are the plan, and the pull requests record where they differ.
