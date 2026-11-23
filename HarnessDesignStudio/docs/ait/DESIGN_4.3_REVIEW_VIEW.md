# Design of 4.3.0: the review view

Written on 2026-11-21 from a reading of the code at 4.2.0 (annotated tag `v4.2.0` on `6848510`, the merge of the preparation, #328; the checkout reports `harness 4.2.0`) and from runs of the command line and of a throw-away script on the five examples and on copies of `flatsat`. It designs milestone E3 of [`ELEC_FEEDBACK_PLAN.md`](ELEC_FEEDBACK_PLAN.md) (point 9 of the feedback: *a review view: a checklist of what the reviewer checks, and quick links to all sources*). Paths are relative to `src/harness_design_studio/` unless they start with `docs/`, `tests/` or `tools/`. Its form follows the designs of 4.1.0 and 4.2.0 ([`DESIGN_4.1_PRODUCTION_SHEET.md`](DESIGN_4.1_PRODUCTION_SHEET.md), [`DESIGN_4.2_ELECTRICAL_CHECKS.md`](DESIGN_4.2_ELECTRICAL_CHECKS.md)): scope, what exists, one part per feature, what changes in the written files, edge cases, tests, documents, the decision, the owner questions, the pull requests, the corrections to the plan and what was not checked. Choices that are the owner's are R1 to R12 (section 15), each with a recommendation first.

**Status (2026-11-22):** built and published as 4.3.0 (annotated tag `v4.3.0` on `20bf8f1`, the merge of the preparation, #337, made by the tag workflow of D-227, run 45045461615; release workflow run 45045481035; `compliance/SIGNOFF.md`, *Publication of 4.3.0*). Pull requests 1 to 6 of section 16 are written: 1 (*Core*) as #332; 2 (*The ticks in the release comment*) as #333, 3 (`explain DIR FINDING`) as #331 and 4 (*The Review sheet*) as #334; 5 (*The editor*) as #335; and 6, the end-to-end test `tests/test_e2e_430.py`, the documents of section 12 and the release notes [`docs/releases/4.3.0.md`](../releases/4.3.0.md), as #336. The pull requests follow the recommendations of R1 to R12; no owner answer is recorded. Pull request 7 is this preparation of 4.3.0, on the branch `feat/e3-prepare-m` (decision D-261): the version 4.3.0, the changelog section, the decision rows, the status pages and the records made again with the repository's tools (a stamp-only renewal: `4.3.0` has five characters, as `4.2.0` and `2.4.0` have). The decision that records the design is D-260 (section 14); this preparation writes it into `docs/DECISIONS.md` as decided, on the recommendations of R1 to R12, with a note of what was built where it differs from section 14. 4.3.0 was prepared on 2026-11-21 and published on 2026-11-22. *Added 2026-11-23, with the preparation of 4.4.0:* the minor release 4.4.0 (decision D-263; prepared, not tagged) writes the *Review* sheet and shows the *Review* page as 4.3.0 does; its two settings (decision D-262) change neither.

*Written before any code (kept as it was):* draft. No code is written. No owner answer yet; the owner has said that the work goes on by the recommendations, so each question of section 15 has the answer the pull requests follow while it is open. The decision that records the design is D-260 (section 14), proposed.

## 0. The frame

The engineer asked for one place where a reviewer finds what to check and where each fact comes from. The parts exist one by one (the plan, point 9: `review` and `release`, the Problems panel, the template `design-review-checklist.md`, `explain`, the plan's *Link to ICD* and *Part link*); nothing gathers them for one harness, and a reviewer's tick is kept nowhere. E3 answers it in a minor release:

1. **Format 4 stays frozen** (D-254). The ticks are not stored in the project (plan question 8). The one new value is a key of a config file that exists, `config/naming.json`, which a 4.2.x tool reads and keeps without a word (tried, section 2.6); a new config file would not be (also tried).
2. **The tool invents no review content** (D-11). No checklist goes into a project by itself: the default is empty, and the template the tool already ships is a start that a person takes on purpose.
3. **Gather, do not duplicate.** Every row of the new page and sheet comes from a function that already answers its question: the findings from the rules, the verifier and the logical checks; the open values from the readiness checks of *Start here* and the hand-over list of `config`; the sources from the fields of format 3. The one new rule, which findings belong to a harness, is taken out of the release gate, where it is written inline today, so that the gate and the review use one function.
4. **A tick is a person's statement, never a pass.** The tool ticks no point and says of no point that it passed. What it records is what the person releasing says was ticked.
5. **Every new text of a written file is worded a second time by the independent verifier**, from its own copy of the rules (`docs/developer/agent/outputs.md`), as for the *Production* sheet of 4.1.0.

## 1. Scope

### 1.1 In scope

| Part | What is built | Points |
|---|---|---|
| A | **The review checklist of the project**: the key `review_checklist` of `config/naming.json` (a list of points, empty by default), `config DIR --review-checklist FILE` that reads the list items of a text or Markdown file (the template is one), and a section *Review checklist* under *Settings > Project* | 9 |
| B | **A sheet *Review* in the build workbook** (`<ID>_build.xlsx`): the head with the release entry, the checklist with a tick column, every finding of the harness with its state, the findings of the whole project, the values still open, the sources to look at (the ICD of each device connector, the page of each part) and how every number is explained; checked by the verifier (`core/outputs/verify_review.py`) | 9 |
| C | **A page *Review* in the editor**, one harness at a time: the same blocks from the same function, with *Show*, *Explain* and *Copy link* on the rows, tick boxes, *Release…*, and the library state of each device | 9 |
| D | **The ticks in the release comment**: `release DIR HARNESS --ticked POINTS` and the release dialog started from the page add one note to the comment (`vcs/release.review_note`), as the notes of placeholders, parts and loose ends are added today | 9 |
| E | **`explain DIR FINDING`**: the command line explains a finding ID, the limit of 4.2.0 (its section 16.7) | 9 (the links to `explain`) |
| F | **The label format in *Settings > Project***: the choice of `model.label_format` with *(a new project's choice)*, section 6.5 of the design of 4.1.0, not built | — (an open item of 4.1.0) |

And with them: one setting (`naming.review_checklist`), its check in `configcheck`, three requirements (REQ-OUT-16, REQ-CC-11, REQ-GUI-31), the guards of the written files renewed once for the new sheet, and step 10 of the proof of 3.0.0.

### 1.2 Not in scope

- **Ticks stored in the project.** A field for them is a format change (E5; plan question 8 recommends the sheet and the comment first).
- **A ticked sheet read back.** Section 6.1 says why; R4 asks.
- **A release gate on the checklist.** A release with points not ticked goes ahead and says so in its comment (R5). A setting like `release_requires_asbuilt` can follow if teams ask.
- **A *Review* sheet in the harness plan (`.ods`).** The plan is opt-in and the users' layout; the build workbook is written for every harness.
- **A command that prints the review view.** `export` writes the sheet; `--json` of `release` and the scripting interface keep their keys and names (R12).
- **A checked state of a library device** (by whom, against which ICD version): a field of format 5 (E5, point Ca). The page shows the library state of each device that exists today (`library_link.link_state`); the sheet cannot, because that state depends on folders outside the project (section 5.2).
- **A type of construction `single` that shields per pair.** Found on the way (section 17.2); it is a fault of Generate, not of the review, and needs a choice of meaning (R11).
- **No new rule, no change of a rule's text, no change of `check`.**
- **Everything of E4 and E5.**

## 2. What exists at 4.2.0

### 2.1 Review and release

- **`review DIR HARNESS`** (`cli/changes.py`, `vcs/release.plan_submit_review`) puts a draft *in review*: the status, the author (the name typed with `--by`) and a change-log entry of kind `review` with an empty comment. Nothing is checked or listed. The editor's *Submit for review* (Releases tab) does the same.
- **`release DIR HARNESS --by NAME --comment TEXT`** (`plan_release`) needs a comment of 10 to 2000 characters (`MIN_COMMENT`, `MAX_COMMENT`), and passes the gate `release_blockers`: the names and the date (`_common`, `role_blockers` with `release_distinct_roles`), placeholder files (`placeholder_blockers`, `--accept-placeholders REASON`), parts not approved or example data (`part_blockers`, `unapproved_parts`, `--accept-unapproved-parts`), loose ends (`--accept-loose-ends`), the as-built records when `release_requires_asbuilt` is on (`--accept-asbuilt`), the status, wires, the generation, every **verifier error** of the harness's objects (`related_ids`), every **open error of the design rules** that `drc.locate` places in the harness, on an interface it carries, or `config-invalid` (written inline in `release_blockers`), gauges, lengths, and the outputs (`outputs_blockers`: exported, current by `content_hash`, unchanged since the export, `damaged_files`). The comment gets a note for each reason given and for overrides and deviations (`placeholder_note`, `part_note`, `loose_end_note`, `asbuilt_note`, `deviations.release_note`), each in the form ` [Released with …; accepted by NAME: REASON]`; the whole is the comment of the change-log entry and of the baseline. After the release the outputs are written again (`_restamp`), so the title blocks say *released*.
- **The editor** runs the same plans through `ChangeDialog.for_release` (`gui/dialogs.py`): the blockers in words (`release_text.plain_blocker`), the reasons, the lock tree, the checker.
- **The record afterwards**: `log DIR`, the Releases tab's timeline, `system/changelog.csv`, `system/version_report.md`.

### 2.2 Where findings show

- The **Problems panel** (`gui/problems_panel.py`): every open finding of the project (`ctl.findings()`: `checks.find` and `drc.run`), filtered by severity, not by harness.
- The **Checks tab** (`gui/checks_panel.py`): one row per rule (`drc/by_rule.py`: pass, fail, not checked, pending) and *Explain* (`derive.explain_finding`, `ExplainDialog`).
- The inspector's **Problems** tab with its *To do* lines, for the object selected.
- The **Next step page** (`gui/next_page.py`, `gui/next_step.py`): one step; the last is *Review and release* (`NEXT_RELEASE_TITLE`), whose button *Go to Releases* opens the Releases tab.
- The written files: `system/drc_findings.csv`, *DRC findings* of `system/system.xlsx` and `system/drc_report.md`, for the whole project. **The build workbook shows no finding** (design of 4.2.0, section 16.5).
- **No view lists the findings of one harness.** The only place that selects them is the inline loop of `release_blockers`, for errors only.

### 2.3 Open values

- *Start here* of the build workbook (`buildsheet._start_sheet`): *Ready to build*, the readiness checks (`READINESS_CHECKS`, eight, and *Ends not decided* for a loose end) with their **counts**, status (OK, TO FIX, NOTE) and what to do; `open_items` knows the items but the sheet prints only the counts; *From the design* (author, checker, approver, released on, the four length sentences); *Placeholder files*; *Overrides and deviations*; *How to use this workbook*; *Build sign-off*.
- `config DIR` (`configcheck.engineering_values`): the hand-over list of 17 engineering values, with what stays unchecked while each is not set.
- `project.placeholder_configs()`: the config files still marked `placeholder`.
- `Part.unverified` and `InterfaceType.unverified`: example data nobody has confirmed. The rule `part-unapproved` names a used part that is missing, not approved or example data; no rule or list names an interface type that is example data.

### 2.4 Sources and explanations

- The ICD of a device connector: `Connector.source_doc`, `source_version`, `source_link` (format 3), edited in the Devices tab, written in the plan's `CON_…` sheets as *Link to ICD* and *ICD version* (`harness_plan.py`).
- The page of a part: `Part.link` (format 3), in the plan (*Part link*) and in the Inspector's `PartLinkBox`. Since 3.0.1 (D-250) the editor copies a link (`weblinks.py`) and opens no browser.
- `explain DIR OBJECT` (`cli/explain.py`) takes a wire, harness, test, interface, connector, pin, shield group, segment, branch point, part or `INTERFACE.CONNECTOR`, **not a finding ID** (design of 4.2.0, section 16.7); `explain DIR --all --out FOLDER` writes `derivations.json` with a derivation `rule-check` or `rule-limit` per finding (`derive_export.explain_all`); the editor's *Explain* and *Why*; `api.explain_finding`.

### 2.5 The checklist template

`templates FOLDER` copies `design-review-checklist.md` (`resources/examples/templates/`), *a list of things to look at before a harness is released*: 26 points of the form `- [ ] …` in five sections (*Before the review* 4, *Look at* 7, *If you use the ECSS profiles* 9, *Drawings and lists* 4, *Release* 2), each 38 to 247 characters long after its mark. The program never reads it.

### 2.6 Where a checklist can live: tried with 4.2.0

On copies of `flatsat` made by `new --template flatsat` with this tool:

- **A new file `config/review.json`** (`{"name": "review", "placeholder": false, "values": {"checklist": ["a"]}}`): `validate` reports `ERROR quarantined: A configuration could not be loaded and was set aside: 'review' is not a known configuration name [config/review.json]`, and `generate` stops: *the project has damaged files … nothing was generated*. The loader knows a fixed list of config names (`model/config.py` `CONFIG_NAMES`, checked in `io/loader.py` `_build`). So a new file would stop every 4.2.x tool on a project of 4.3.0.
- **A new key in `config/naming.json`** (`"review_checklist": ["Item one"]`): `validate` reports nothing, and `settings DIR --set naming.harness=…` keeps the key. The same holds for the other free tables, as the design of 4.2.0 found for `segregation.json` (its section 2.6).
- **A new key in `config/model.json`** is refused: `configcheck.validate_model` reports every key that is not a model setting as `config_invalid`.
- `config/naming.json` already holds the two release settings, `release_distinct_roles` (`vcs/roles.py`, `CONFIG_FILE`) and `release_requires_asbuilt`; both are in `generation_status.NOT_READ_BY_GENERATION`, so changing them does not make the harness plans out of date; and `naming.json` is not frozen by a release (`vcs/snapshot.FROZEN_CONFIG_FILES` is derating, emc, segregation and titleblock).
- Every config file is in the model hash (`io/layout.model_hash`), so a changed list changes `content_hash` and the outputs are out of date until the next export; that is right for a list the sheet prints.

### 2.7 A ticked copy in the outputs folder

`outputs_blockers` refuses a release while a file that the manifest lists was changed after the export (`outputs_modified`, `build.damaged_files`), and `verify --outputs` reports its hash. A reviewer who ticks `outputs/harnesses/W001/W001_build.xlsx` in a spreadsheet program and saves it stops the release. The sheet must say where to tick (section 4.2).

### 2.8 What the page and the sheet would list on the five examples

Counted with a throw-away script that states the selection of sections 4.2 and 4.3 (not the tool's code), each example made as `tools.output_hashes` makes it (`templates.create_project`, then `generate_project` when it has no harness):

| Project | Harnesses | Checklist | Findings of the harness (all harnesses) | For the whole project | Values still open (rows; most in one harness) | Sources (rows; most in one harness) |
|---|---|---|---|---|---|---|
| `blank` | 0 | — | — | — | — | — |
| `first-steps` | 2 | 0 points | 7: 2 notes (`unconfirmed`), 5 warnings (`part-unapproved`) | 6 notes | 18 (9) | 9 (5) |
| `minimal-satellite` | 11 | 0 points | 41: 11 notes, 30 warnings (27 `part-unapproved`, 3 `connector-lookalike`) | 6 notes | 99 (9) | 49 (5) |
| `small-satellite` | 24 | 0 points | 90: 24 notes, 66 warnings (59 `part-unapproved`, 6 `connector-lookalike`, 1 `cross-strap`) | 4 notes | 216 (9) | 107 (5) |
| `flatsat` | 8 | 0 points | 90: 44 notes, 46 warnings (32 `part-unapproved`, 14 `connector-lookalike`) | 3 notes | 61 (8) | 120 (28: W002, 22 device connectors and 6 parts) |

No example has an error, a waiver, a deviation, an override, a loose end, an ICD named on a device connector or a link on a part, and none sets a checklist; with the template's list a sheet has 26 points more. Every example has the six placeholder files; the hand-over list has 17 values not set on `first-steps`, `minimal-satellite` and `small-satellite` and 4 on `flatsat`; all 17 interface types of every example are example data. On `flatsat` the open build data of one harness reach 173 items (W002: 24 wires without a gauge, 13 without a colour, 26 without strip lengths, 52 pins without a termination and 52 without a contact part, 6 parts), which is why section 4.2 prints the first five of each check and its count, not every item (R6).

The 44 notes of `flatsat` are the logical check `unconfirmed` (*IF-009 uses connectors the tool chose for you*), the template's point *No interface shows auto-filled*. A `connector-lookalike` finding is on a device connector; it belongs to the harness that plugs into that connector, as `release_blockers` counts it (`related_ids`): the 14 of `flatsat` are the 14 findings of the rule in the project, each on a device connector of one harness.

## 3. Part A: the review checklist

### 3.1 Where it lives and its shape

```
config/naming.json
  "review_checklist": [
    "`harness-design-studio check DIR` prints no error.",
    "Wire list, pinouts and BOM agree with the drawing.",
    ...
  ]
```

A list of **points**, in the order a reviewer goes through them; a point is one line of text of 1 to 300 characters, each point once (compared after trimming and folding the case), at most 100 points. Its number is its place in the list (1 to N). Not set, `null` or `[]`: the project has no checklist.

- **`core/settings.py`:** `Setting("naming", "review_checklist", "Review checklist", "", "names", None, "The points a reviewer checks before a harness is released, in order; the Review page and the Review sheet of the build workbook list them, and a release records which were ticked.", "Review page, Review sheet, release comment", _PROJECT, "a list of points, each one line of 1 to 300 characters, each once, at most 100")`. No default: the tool ships no point (D-11).
- **`core/configcheck.py`:** the check of the key (code `config_invalid`, as every refused value: *config/naming.json: review_checklist must be a list of points, each one line of 1 to 300 characters, each once, at most 100*). It is not on the hand-over list (`NEEDS`, `OPTIONAL_NEEDS`), so `config DIR` and its exit code do not change. A refused list is no list for the page and the sheet, and `config-invalid` says why (and, as today for any refused value, blocks every release).
- **`core/generation_status.py`:** `review_checklist` joins the keys of `naming` in `NOT_READ_BY_GENERATION`, so a changed list does not make the harness plans out of date.
- **`core/review.py`** (new): `points(project) -> tuple[str, ...]` (the accepted list, else empty) and `list_hash(points) -> str`, the first 8 hexadecimal characters of the SHA-256 of the list as canonical JSON. The hash names the list in the sheet and in the release comment, because `naming.json` is not frozen by a release (section 2.6): a later reader can tell whether a comment and a sheet speak of the same list.

### 3.2 How a project sets it

- **`config DIR --review-checklist FILE`** (`cli/data.py`, beside `--counterparts` and `--distinct-roles`): reads a UTF-8 text file of at most 64 KiB with `review.points_from_text`: when the file has list items (lines that start with `- [ ] `, `- [x] `, `- `, `* `, `+ ` or a number and `. `), each list item is a point and every other line is skipped (headings, the line *Project: ____*); else each line that is not empty and does not start with `#` is a point. The list mark, `**` and backticks are taken away; nothing else of the text changes. `--review-checklist none` takes the key out. The command prints the number of points and the list hash, and refuses a file that gives a list the check of 3.1 refuses, with the same text.
- **`settings DIR --set naming.review_checklist='[...]'`** takes the list as JSON, as every setting.
- **The editor:** *Settings > Project* gets a section *Review checklist*: a plain text box with one point per line, *Use the template's points* (fills the box from the shipped `design-review-checklist.md`, read with the same function), *Take the points of a file…* (`ask_file`) and *Save*, one undo step (`configcheck.plan_set_checklist(project, points)`, a plan of ops like `plan_set_choice`); a refused list shows its reason inline under the box. Nothing is saved until *Save*.

### 3.3 The start: the template, taken on purpose

The registry default is empty, and `samples.start_project`, the examples and the templates' projects get no list. The start is the template the tool already ships: from `design-review-checklist.md` the function of 3.2 takes its 26 points, the 9 points of the section *If you use the ECSS profiles* among them, which cite clauses of the standards and say that the tool cannot check them. The person takes the file on purpose (a command, or a button and *Save*) and sees every point before it is saved, as a profile is applied only on `config --apply-profile` (R2). The template's own text is not changed in 4.3.0.

### 3.4 What changes in written files

Nothing until a project sets a list: the key is in `config/naming.json` only, and the sheet of a project without one says so (4.2). A project with a list gets other bytes in `config/naming.json`, another model hash on every written file (the config is part of it) and its points on the sheet.

## 4. Part B: the Review sheet

### 4.1 What is built

**`core/review.py`** `review_view(project, h, findings) -> ReviewView`, pure, no file and no style, gives the blocks and rows of sections 4.2 and 4.3 as plain values; `findings` is the list of `checks.find` and `drc.run` that the caller already has (the export runs them once for `system/drc_findings.csv`, `build.findings_table`; the editor has `ctl.findings()`), so the rules are not run once per harness. **`buildsheet._review_sheet`** writes the view into the build workbook as the sheet `REVIEW_SHEET = "Review"`, before *About* (after *Tests* and, when there is one, *As-built*); `SHEETS` and `sheet_names` change. *Start here* gets the line `("Review", "for the reviewer: the project's checklist with a column to tick, every finding and open value of this harness, and the sources to look at")` in *How to use this workbook*, before *About*. `build_workbook(project, h, stamp, findings)` takes the findings from `build_outputs`.

**Why the build workbook and before *About*.** It is the file that exists for every harness and is read on paper; the plan is opt-in. The reviewer's sheet comes after the builder's sheets, so the position of every sheet that a script or a person knows stays as it is (4.1.0 moved the sheets once already).

### 4.2 The blocks, their order and their texts

The order is the reviewer's: what the project asks to check, what the tool found, what is still open, where to look it up. Each block has a heading row and a column row; an empty block has one sentence in place of its rows.

**Head** (no column row):

| Row | Text |
|---|---|
| 1 | `Review of W002  aocs to bus` (bold, 16 pt; the harness's label, else its name) |
| 2 | `Version 1.0.0   ·   status draft   ·   <stamp line>   ·   <notice>` (as *Start here*) |
| 3 | `Release: not released yet.` or `Release: version 1.0.0 released on 2026-11-22 by NAME, checked by NAME. Comment: <the comment of the change-log entry of kind release of this version>` |
| 4 | `What stops the release is marked in the column Release; a release also needs current outputs, a name and a comment.` |
| 5 | `Tick a printout, or a copy saved outside the outputs folder: a file in outputs/ that was changed after the export stops the release (outputs_modified).` (italic) |

**1. Checklist.** Heading `Checklist: 26 points (config/naming.json review_checklist, list 1a2b3c4d)`; columns `No.`, `Point`, `Done (x)`, `Note`; one row per point, its number and text; **Done (x)** with `_tick_rules`, as the other sheets. Without a list: `No checklist: this project sets no review_checklist in config/naming.json. Set one with harness-design-studio config DIR --review-checklist FILE, or under Settings > Project in the editor; the file design-review-checklist.md of harness-design-studio templates is a start.`

**2. Findings of the harness.** Heading `Findings of W002: 0 errors, 7 warnings, 11 notes open; 0 waived, 0 accepted as deviations`; columns `Severity`, `Rule`, `Finding`, `Object`, `Finding text`, `State`, `Release`. The findings of section 4.3; open errors, open warnings, open notes, then deviations, then waived, each by finding ID. *Severity* is `error`, `warning` or `note` (the words of `drc_report.md`); *Finding text* is the finding's title as the rule words it (as in `drc_findings.csv`); *State* is `open`, `open: its waiver no longer applies (the finding changed)` (`waiver_changed`), `waived: <justification>` or `accepted as a deviation: <justification>`; *Release* is `stops the release` for an open error, `needs a written reason` for a finding of `part-unapproved` (the gate's `part_blockers`, whether waived or not), else empty. None: `No finding of the design rules, the verifier or the logical checks is about W002 or what it carries.`

**3. For the whole project.** Heading `For the whole project`; columns `Severity`, `Rule`, `Finding`, `Finding text`, `Release`: the notes of `unchecked-config` (*Spare pins were not checked: the required fraction is still a placeholder*) and the errors of `config-invalid` (`stops the release`, as the gate has it). None: `No finding is about the whole project.` The same rows are on the sheet of every harness.

**4. Values still open.** Heading `Values still open`; columns `What`, `Open`, `First items`, `Where to see them all`, `Release`; a row only for what is open, in this order:

| What | First items | Where to see them all | Release |
|---|---|---|---|
| `Configuration files still placeholders` | every file, `config/derating.json, config/emc.json, …` | `harness-design-studio config DIR` | `needs a written reason` |
| `Engineering values not set` | `derating.spare_pin_fraction, generation.power_signal_gap_pins, …` | `harness-design-studio config DIR; Settings > Engineering values` | |
| each open check of *Start here* but *Parts that are not approved*, with its label (`Wires without a gauge`) | the first five of `buildsheet.open_items`, then `and N more` | `Cut list, Production` for a wire, `Connectors` for a pin, `Production` for an end | `stops the release` for the length and the gauge (`length_unknown`, `gauge_pending`), `needs a written reason` for *Ends not decided*, else empty |
| `Interface types marked as example data` (those the harness carries) | `analog, can, discrete, power_primary, rs422` | `logical/interface_types.json` | |
| `Values set by hand (overrides)` | the first five lines of `deviations.override_lines` | `Edit wire; the release comment lists them` | |
| `As-built records` (only while `release_requires_asbuilt` is on) | `release.asbuilt_open`: the first open value | `As-built` | `needs a written reason` |

The parts are left out of this block because the findings of `part-unapproved` name every used part that is missing, not approved or example data, and the sources list each part with its approval: a third row for the same part would be one too many. Nothing open: `Nothing is open.`

**5. Sources to look at.** Heading `Sources to look at`; columns `Kind`, `ID`, `What`, `Document`, `Version`, `Link`: one row per device connector the harness plugs into, in natural ID order (`Device connector`, `PDU2-J01`, `PDU2:J01`, `source_doc` else `not named`, `source_version`, `source_link`), then one row per part it uses (`Part`, `EX-WIRE-SINGLE`, its approval as the *Parts* sheet words it, `pending (example data)`, empty, empty, `Part.link`). A link is written as text, as the plan writes it.

**6. How the numbers were made.** Heading `How the numbers were made`; two rows: `Every ID on this sheet can be explained: harness-design-studio explain DIR ID shows the equation, the inputs and their sources for a wire, a connector, a part or a finding (Finding column); in the editor, select it and open Why.` and `harness-design-studio explain DIR --all --out FOLDER writes every derivation of the project (derivations.json, derivations.csv).`

### 4.3 Which findings belong to a harness

One function, **`vcs/release.harness_findings(project, h, findings) -> list[Finding]`**, which `release_blockers` then uses for its errors (the same blockers as today; `tests/test_change_control.py` and the other release tests hold them) and `review_view` uses for every severity: a finding belongs to harness `h` when its object is one of `related_ids(project, h)` (the harness, its connectors, wires and shields, the device connectors it plugs into), or `drc.locate` places it in the harness or on an interface the harness carries (`snapshot.carried_interfaces`), or `drc.locate` places it nowhere and its object is a part the harness uses (`part-unapproved`, whose object is a part ID). `config-invalid` and `unchecked-config` go to block 3. Every other finding (a device connector the harness does not plug into, a part only a device uses) is not about this harness and stays on the Problems panel.

### 4.4 Rows of `flatsat`, W002

| Block | Rows |
|---|---|
| 1 | the sentence *No checklist …* |
| 2 | 11 notes (`unconfirmed.IF-009` … `unconfirmed.IF-040`, *IF-009 uses connectors the tool chose for you*), 1 warning `connector-lookalike.PDU2-J01`, 6 warnings `part-unapproved.EX-MICROD-15-M` … `part-unapproved.EX-WIRE-TWISTED-SHIELDED` (*needs a written reason*) |
| 3 | `unchecked-config.emc`, `unchecked-config.separation`, `unchecked-config.spare-pins` |
| 4 | placeholders (6 files), 4 engineering values, *Wires without a gauge* 24 (first `W002-003`; *stops the release*), *Wires without a colour* 13, *Pins in use without a termination* 52, *Wires without strip lengths* 26, *Pins in use without a contact part* 52, 5 interface types of example data |
| 5 | 22 device connectors (each `not named`), 6 parts (each `pending (example data)`, no link) |
| 6 | the two sentences |

### 4.5 Print set-up

As every sheet (`_finish`): A4 landscape, one page wide, as many pages as needed, the stamp in the footer and *Page &P of &N*, no repeated header row (the blocks have their own, as *Start here*), the columns capped at 46 characters (`_Layout.see`), the *Point* and *Finding text* columns at 80 so that a point of 300 characters wraps on four lines; a manual page break before a block that would start in the last five rows of a page.

### 4.6 How the verifier checks it

A new module of the verifier, **`core/outputs/verify_review.py`**, `review_rows(project, h, findings)`, states every row a second time and imports none of `core/review.py`, `buildsheet.py`, `tables.py` or `vcs/release.py`. `verify.py` `_build_review` reads the sheet with `_xlsx_values` and compares it row by row (code **`out_review`**, the object the harness). Its own copies: the check of a list (3.1), the list hash, the selection of 4.3 (with `drc.locate`, the one place a finding is placed, and its own rule for the places that belong to the harness), the order and the state words, the release entry from `project.changelog`, the open items of the readiness checks (it already counts them in `_build_expected_checks`; the items move into `verify_review.expected_items`, which `verify.py` then counts), and every heading and sentence of 4.2. What it does not word a second time is what it does not for `drc_findings.csv` either: the findings themselves (it calls `checks.find` and `drc.run`, as `verify_outputs` does today, and passes them in) and the hand-over list (`configcheck.engineering_values`, which `verify.py` imports already).

Its texts:

- `The build workbook of W002 has no Review sheet before About.` (the sheet list, as today for the other sheets, `out_build`)
- `The build workbook of W002 (Review) lists 25 points, but config/naming.json has 26 (list 1a2b3c4d).`
- `The build workbook of W002 (Review) gives point 3 as '…', but the project's checklist says '…'.`
- `The build workbook of W002 (Review) has ticks before anyone reviewed it.` (any cell of **Done (x)**)
- `The build workbook of W002 (Review) does not list the finding part-unapproved.EX-WIRE-SINGLE.` and `… lists the finding X, which is not about W002.`
- `The build workbook of W002 (Review) gives the finding X as 'open', but it is waived.` (and each other column)
- `The build workbook of W002 (Review) shows a wrong count for 'Wires without a gauge'.`
- `The build workbook of W002 (Review) names the release of version 1.0.0 wrongly.`
- `The build workbook of W002 (Review) does not name the source of PDU2-J01 as the design has it.`
- `The build workbook of W002 (Start here) does not list the Review sheet before About.`

The tests compare `review_rows` with `review_view` by Hypothesis on the random harnesses of `tests/test_verify_plan.py` with random findings, waivers and checklists, and a mutation test changes each column of one row of each block.

### 4.7 What changes in existing outputs

Every build workbook of every project changes once: a new sheet, a new line on *Start here*. A changed finding, waiver or checklist changes the sheet of the harnesses it is about. Every other file stays as it is (section 9).

## 5. Part C: the Review page in the editor

### 5.1 How it is reached

A page area of its own, as the As-built page is (`gui/areas.py`): `Area("review", strings.AREA_REVIEW, "nav-review", (), strings.AREA_REVIEW_TIP)`, after *Outputs* and *As-built*, before *Versions*; a Lucide icon `nav-review` (clipboard with a check) in `icons.py`. It is reached by:

- the rail (listed for the Electrical engineer and the AIT engineer; left out of the Systems engineer's rail, as Drawings and Outputs are: R7);
- the Next step page: the step *Review and release* gets the button *Open the Review page* (`NEXT_RELEASE_BUTTON`) in place of *Go to Releases*; the page opens on the first harness in ID order that is not released;
- the Releases tab: a button *Review page* beside *Submit for review*, *Release* and *New version*, for the harness chosen there;
- *Go > Review* (`act-go-review`, in no role's hidden list), the command palette, and *Review…* in the menu of a harness in the project tree.

### 5.2 What it shows

`gui/review_page.py`, `ReviewPage`, a page like `AsBuiltPage`: it shows a `core.review.ReviewView` and calls back; the window does the rest. At the top a harness picker (shared with the Releases tab through `current_harness`), its state chip, a summary line (`W002, version 1.0.0, draft: 3 of 26 points ticked; 1 thing stops the release; 7 warnings and 11 notes open; 8 values still open`) and the buttons **Release…** (primary) and **Edit the checklist…** (*Settings > Project*). Then the blocks of 4.2, each a `tables.TableView` with an empty state (`attach_empty_state`), the same rows from the same function and `ctl.findings()`:

- **Checklist:** a tick box per point (the column *Done*), **Tick all** and **Clear**.
- **Findings** and **For the whole project:** *Show* (double-click, `show_object`), *Explain* (`checks_panel.explain`, the `ExplainDialog` of the Checks tab), *Waive…* or *Accept as deviation…* where the finding takes it (the flows of the Problems panel).
- **Values still open:** *Show* goes to the first item, *Supply value…* for an engineering value (`config_dialog`), *Show all* to the sheet's place (the Harness tab or the Lists tab).
- **Sources:** *Copy link* (`weblinks`, the window's `_copy_link`; nothing opens a browser, D-250), *Show* (the device connector in the Devices tab, the part in the Inspector), and one column the sheet does not have, **Library**: the state of the device in the device library (`library_link.link_state`, the words of `LINK_STATE_WORDS`: *Up to date*, *Library changed*, *Changed here*, *Source not found* …), from the libraries the window already reads. A written file depends on the project alone, so the sheet cannot hold it.
- While the background check is running the page lists the last result and says so (*The checks are running; this list is from the last check*), as the Problems panel does.

### 5.3 The ticks on the page

A tick is kept for this computer only, in `QSettings` under `layout/<hash>/review/<harness>`, as the branching notice keeps its answer (`layout/<hash>/branching_notice_done`): the ticked numbers with the list hash and the first 12 characters of `content_hash` they were made for. Never in the project, the model hash or a written file. When the list or the design changed since (another hash), the ticks are dropped and the page says *The checklist or the design changed after these points were ticked; tick them again* (R8). A released harness shows its release entry and no tick boxes.

### 5.4 Roles, texts, accessibility

Every string in a block *4.3.0 E3* at the end of `gui/strings.py`; every control an accessible name and a tooltip; no colour alone (the states are `StateChip`s); the layout keys under `self._wkey`. `areas.SYSTEMS_HIDDEN` gets `review`; `tests/test_ui_role_pages.py` reads it.

## 6. Part D: the ticks in the release comment

### 6.1 From what input, and why

The ticks reach the comment from **the person releasing**, through the two ways a release is made today:

- **the editor:** *Release…* (from the page, the Releases tab, the top bar or the menu) hands the page's ticks of 5.3 for that harness to the release dialog, which shows the note it will add under the comment field (*Added to the comment: [Review checklist …]*) with *Open the Review page*;
- **the command line:** `release DIR HARNESS --by NAME --comment TEXT --ticked POINTS`.

Not from a ticked sheet read back, for four reasons found in the code: a ticked copy in `outputs/` stops the release (`outputs_modified`, section 2.7), so the file read back would be a copy elsewhere that the tool must first prove to belong to this design and this list (a stamp check, as `import-asbuilt` does for its sheet); a sheet ticked on paper cannot be read at all; reading a workbook saved by another program is a new import path with its own refusals, which the as-built import shows to be a release of its own; and the release would then rest on a file nobody but the tool looks at, where the comment holds what a person says. The tick column of the sheet is for the review on paper or in a copy; the person releasing says what was ticked, as they type the checker's name today (R4).

### 6.2 `--ticked` and its blockers

`--ticked POINTS` (`cli/changes.py`, `OPTIONS["ticked"] = "--ticked"`): `all`, `none`, or numbers and ranges joined by commas, `1-5,7,9-14` (`review.parse_ticked(text, n)`). `plan_release(..., ticked: frozenset[int] | None)` and `release_blockers` get it; new blockers (`about="ticked"`):

- `ticked_invalid`: *--ticked must be all, none, or point numbers from 1 to 26 such as 1-5,7 (got '27').*
- `ticked_no_checklist`: *This project has no review checklist, so there is nothing to tick (config/naming.json: review_checklist).*

Without `--ticked` a release goes ahead as today (R5).

### 6.3 The note

`vcs/release.review_note(project, by, ticked) -> str`, added last to the comment after the notes of today (so their text and order stay):

| Case | Note |
|---|---|
| no checklist, no `--ticked` | `` (nothing: every project of today) |
| a checklist, no ticks given | ` [Review checklist (26 points, list 1a2b3c4d): no ticks recorded]` |
| some ticked | ` [Review checklist (26 points, list 1a2b3c4d), recorded by NAME: ticked 1-5, 7, 9-26; not ticked 6 (Wire list, pinouts and BOM agree with the drawing.), 8 (…)]` |
| all ticked | ` [Review checklist (26 points, list 1a2b3c4d), recorded by NAME: all ticked]` |
| none ticked | ` [Review checklist (26 points, list 1a2b3c4d), recorded by NAME: none ticked]` |

The ticked numbers are written as ranges; at most five points not ticked are named, each cut to 60 characters, then `and N more`; so the note is at most about 500 characters and the check of `comment_long` (2000 with the notes) keeps its meaning. `--json` of `release` keeps its keys; the note is in the comment.

### 6.4 Where it is read afterwards

In every place a release comment shows today: `log DIR`, the Releases tab's timeline, the baseline, `system/changelog.csv`, `system/version_report.md`; and, after the release writes the outputs again (`_restamp`), in row 3 of the Review sheet (4.2), which names the release entry of the version. So the ticks reach the sheet through the comment, and the model holds nothing new.

## 7. Part E: `explain DIR FINDING`

`cli/explain.py`: when `OBJECT` names no object `explain` knows (the order of today is kept, so no argument changes its meaning), it is looked up among the finding IDs of `checks.find` and `drc.run` (`rule.object`, cut and hashed when long, `checks.finding_id`); a finding gives `derive.explain_finding(project, rule, object_id)` rendered as for an object, `--json` as a list of derivations as today. A finding of a rule with no calculation says what the rule compares (the `rule-check` derivation, `derive_rules`), as the editor's *Explain* does. An ID that is neither: `error: … is not a wire, a harness, … or a finding of this project` (the list of today, with *a finding* added). The help (and so `docs/CLI.md`) names the finding. It is what the *Finding* column of the sheet points to, and the limit the release notes of 4.2.0 list.

## 8. Part F: the label format in *Settings > Project*

Section 6.5 of the design of 4.1.0 said that *Settings > Project* shows the choice of `model.label_format` with *(a new project's choice)* after `harness_device_connector`, as D-247 did for the segmentation; the page has only the segmentation (`settings_page.py`, `segmentation_combo`). A combo box `settings-label-format` with the five formats (`label_format.FORMATS`, the words of `FORMAT_TEXT`), set through `configcheck.plan_set_choice(project, "model", "label_format", value)` (one undo step); `custom` names the two templates and says they are set with `settings --set`. It changes no written file and nothing on the command line. It is in 4.3.0 because the pull request of the page of part A touches the same section, and a reviewer of labels sees the format in force there.

## 9. What changes in the written files, and the guards

| Written file | Change | Which projects | Guard |
|---|---|---|---|
| `<ID>_build.xlsx` | the sheet *Review*; the line *Review* on *Start here* | every project, every harness | `docs/ui/OUTPUT_HASHES_BASELINE.json` (the 45 build workbooks of the four examples), `tests/fixtures/numbers/snapshot.json`, the build workbook digests of `tests/fixtures/outputs/*.json` (`mini3`, `sat15`, `sat15_full`, `loose_ends`, `splices`, `row_layout`), renewed for this one reason |
| `config/naming.json` | the key `review_checklist` | a project that sets a list | none: no example, template or fixture sets one |
| the comment of a release (change log, baseline, `changelog.csv`, `version_report.md`) | the note of 6.3 | a release in a project with a list, or with `--ticked` | none: no recorded release has a list |
| every other file, the harness plans | nothing | — | `tools.output_hashes --check` names only the build workbooks as changed; the plan goldens (`tests/fixtures/outputs/harness_plan/`) do not move |

**The proof of 3.0.0** (`tests/test_format3.py::test_the_written_files_of_3_0_are_those_of_2x_after_the_word_list`, slow, run on `master` and by `tools.release_check`, not on a pull request) compares every build workbook of seven recorded projects cell by cell. Pull request 4 adds **step 10** to `tests/format3_support.py`: *the step of 4.3.0 (design of 4.3.0, section 4): `<ID>_build.xlsx` has the new sheet Review, taken as the file of 4.3.0 has it, and the members that list the sheets and the styles follow; Start here has the line Review in How to use this workbook before About* (`review_sheet`, built as `production_sheet` is for step 8). A fast test beside those of steps 7 to 9 shows that step 10 changes that sheet and line and that a cell changed by hand elsewhere is still reported. `mini3-released` has a release entry, so its sheet shows row 3 with the release; the step takes the sheet as written, and its own tests read it. Pull request 4 **runs the slow tests (`pytest -m slow`) before it is merged**, because a pull request's CI does not run them (the merge of #311 left the proof red on `master` for want of its step).

## 10. Edge cases found in the code

| Case | Where in the code | What the design does |
|---|---|---|
| **A ticked workbook in `outputs/`** | `outputs_blockers`, `damaged_files`; `verify --outputs` | Row 5 of the sheet says where to tick; the release refuses as today (`outputs_modified`) |
| **The list changed after the export** | `content_hash` holds the config | The outputs are out of date; the release needs an export first (`outputs_stale`), so the released sheet holds the list of the release |
| **The list changed after the release** | `naming.json` is not frozen (`FROZEN_CONFIG_FILES`) | The release comment and the released sheet keep the list hash; the next export writes the new list on the sheet of the released harness, with its release entry |
| **A refused list** | `configcheck`, `config-invalid` blocks every release | No points on the page and the sheet; block 3 lists `config-invalid` with *stops the release* |
| **`--ticked` without a list, or a number out of range** | — | `ticked_no_checklist`, `ticked_invalid` (6.2) |
| **Three different people** (`release_distinct_roles`) | `role_blockers` | The checker may tick on their computer; the note says who recorded the ticks (the person releasing), and the checker's name is in the dialog and the baseline as today |
| **A finding located on an interface two harnesses carry, or on a device connector two harnesses plug into** | `drc.locate`, `related_ids` | On both sheets, as the release gate counts it for both |
| **`part-unapproved` placed nowhere** | `drc.locate` returns None for a part ID | Taken by the part's use (4.3); the gate's reason for parts is its own (`part_blockers`), whether the finding is waived or not |
| **A waiver whose finding changed** | `waiver_changed` | *open: its waiver no longer applies* |
| **A deviation** | `Finding.deviation` | Listed after the open findings with its reason; *Overrides and deviations* of *Start here* stays as it is |
| **Notes of the whole project** | `unchecked-config` has no place | Block 3, on every harness's sheet |
| **Rules of an extension** (`x-…`) | `run_extension_rules` | Listed like the others; *Explain* asks the extension |
| **The check failed in the editor** | `ctl._drc_failure_finding` | The page shows the finding `drc-failed`; the sheet is written from a fresh run at export |
| **A harness with a loose end** | `LOOSE_CHECK`, `loose_end_blockers` | *Ends not decided* in block 4 (*needs a written reason*) and the finding of `part-unapproved` for the TBD part |
| **A harness drawn by hand or from a connection** | no interface | Block 4 has no interface types; the findings of 4.2.0's rules show as any other |
| **A released harness, a new version** | `h.status`, the change log | Row 3 names the release of the version on the sheet; a draft of a new version says *not released yet* and shows no older release (its comment is in `log`) |
| **A read-only project** (newer format) | `project.read_only` | The page shows, *Release…* is off, as in the Releases tab |
| **A project copied to another folder** | `layout/<hash>` is per folder | The ticks of 5.3 stay behind; by design, they are a convenience of one computer |
| **A point with Markdown or 300 characters** | — | Printed as written after 3.2; the *Point* column wraps |
| **The `as-built` gate on** | `asbuilt_gate_on`, `asbuilt_open` | One row in block 4; nothing without the setting |
| **The 4.2.x tool on a 4.3.0 project** | §2.6 | Keeps the key, shows no page, writes no sheet, adds no note; its `verify --outputs` refuses a 4.3.0 export (*does not have the sheets*), as an older tool refuses any sheet list it does not know |

## 11. Tests to write

| File | What it holds |
|---|---|
| `tests/test_review_checklist.py` (pull request 1) | The check of 3.1 (accepted and refused lists, the texts of `config_invalid`); `points_from_text` on the template (26 points, the marks and backticks taken away), on a plain file and on a file with headings; `config --review-checklist FILE` and `none`; the key is not an input of generation (`input_hash` unchanged) but changes `content_hash`; a 4.2 project with the key loads, saves and keeps it |
| `tests/test_review_view.py` (pull request 1) | `harness_findings` against the blockers of `release_blockers` on every example and on random findings (the gate's errors are the view's open errors); the blocks and rows of `flatsat` W002 (section 4.4) and of `loose_ends`, `splices` and `mini3-released`; the counts of section 2.8 |
| `tests/test_release_ticks.py` (pull request 2) | `parse_ticked`; the two blockers; the five notes of 6.3, the cut and the ranges, `comment_long` with the note; a release without a list writes the comment of today byte for byte; the command line end to end |
| `tests/test_explain_finding.py` (pull request 3) | `explain DIR FINDING` for a finding of a rule with a limit, of a yes/no rule and of a logical check; an object ID keeps its meaning; an unknown ID; `--json` |
| `tests/test_review_sheet.py` (pull request 4) | The sheet order with and without *Routing* and *As-built*; the head, the six blocks, the empty sentences; the tick column empty; *Start here*'s line; the print set-up |
| `tests/test_review_verify.py` (pull request 4) | The imports of `verify_review.py` (no builder, not `core/review.py`, not `vcs/release.py`); Hypothesis: `review_rows` equals `review_view`; a mutation of each column of each block, a tick, a point, a release entry gives `out_review` |
| `tests/test_format3.py` | Step 10 and its fast test (section 9) |
| `tests/test_ui_review_page.py` (pull request 5) | The page from each way of 5.1; the blocks of `flatsat` W002; *Show*, *Explain*, *Copy link* (the copier hook, no opener); the ticks kept and dropped (5.3); *Release…* hands them to the dialog, which shows the note; the Library column; the Systems engineer's rail; *Settings > Project*: the checklist section and the label format |
| `tests/test_e2e_430.py` (pull request 6) | One project end to end through the command line: `new --template flatsat`, `templates`, `config --review-checklist design-review-checklist.md`, `generate`, `export`, the Review sheet read back, `explain DIR FINDING`, `release --ticked 1-20` blocked (placeholders) and then with the reasons, the note in `log`, the sheet after the release with row 3, `verify --outputs` |

The requirements, in `docs/REQUIREMENTS.md` and `compliance/traceability.csv` (`python -m tools.trace`): **REQ-OUT-16** (the Review sheet of the build workbook: the checklist, the findings of the harness, the values still open and the sources, checked by the verifier), **REQ-CC-11** (a release records the ticks the person releasing states, with the list hash; no gate), **REQ-GUI-31** (the Review page, one harness at a time, reachable in every role).

## 12. Documents to update

- `CHANGELOG.md`, `## Unreleased`: one entry per pull request; for pull request 4 the reason for the renewal of the baseline, the snapshot and the goldens, and step 10.
- `docs/releases/4.3.0.md`: the checklist, the sheet, the page, `--ticked`, `explain DIR FINDING`, the label format on *Settings > Project*; *For scripts*: the build workbook has one sheet more before *About*, `release` has `--ticked`, `config` has `--review-checklist`, `explain` takes a finding ID; *Upgrade*: a 4.2.x tool keeps the key and refuses a 4.3.0 export in `verify --outputs`, so a team updates at the same time; *Known limits* (section 18).
- `docs/OUTPUTS.md` (the row *Review* in the table of the build workbook), `docs/CONFIG.md` (`naming.review_checklist`, test (d)), `docs/CLI.md` (`python -m tools.gen_cli_docs`), `docs/REQUIREMENTS.md`.
- `docs/developer/agent/outputs.md` (a bullet for the Review sheet: `core/review.py`, `verify_review.py`, `harness_findings`), `gui.md` (the Review page, the area, the ticks in `QSettings`), `change-control.md` (`review_note`, `--ticked`, `harness_findings`).
- User manual: `release-a-harness.md` (the Review page, the ticks and the note), `export-the-outputs.md` (the sheet, where to tick), `read-and-fix-problems.md` (the findings of one harness), `follow-the-workflow.md` and `choose-your-role.md` (the step's button, the rail), `naming-and-title-block.md` (the label format on *Settings > Project*), `use-git-and-ci.md` (the template and `config --review-checklist`), and the in-app guide (`python -m tools.build_guide`).
- `resources/examples/templates/README.md` and `docs/examples/README.md` (row 14: the checklist template is read by `config --review-checklist`), `docs/LEARNING_PATH.md` (step 7), `docs/GLOSSARY.md` (*Review checklist*, *Review sheet*).
- `docs/ait/ELEC_FEEDBACK_PLAN.md`: E3 built, and the corrections of section 17.
- Not changed: `docs/FILE_FORMAT.md` (no key of a project file outside `config/`), `docs/RULES.md` (no rule), the template `design-review-checklist.md`.

## 13. What does not change

The project format and `SCHEMA_VERSION` (4); `system/export.json` (`format_version` 2); every written file but the build workbooks; the harness plans; the 43 rules, their texts and `check`; the release gate's blockers of today and their texts (`harness_findings` gives the same errors); the comment of every release in a project without a list; `--json` of every command; the scripting interface (`API_VERSION` 1, `tests/fixtures/api_snapshot.json`); the template `design-review-checklist.md`; the sheets of the build workbook before *About* and *Start here* but its one line.

## 14. Proposed decision D-260

> | D-260 | **Release 4.3.0 is a minor release with the review view (milestone E3 of `docs/ait/ELEC_FEEDBACK_PLAN.md`); no format change** (D-254, D-258; design `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`). (1) A project's review checklist is the key `review_checklist` of `config/naming.json`: a list of points, each one line of 1 to 300 characters, each once, at most 100; empty by default, so the tool ships no point (D-11); `config DIR --review-checklist FILE` takes the list items of a file (the shipped template `design-review-checklist.md` gives 26), *Settings > Project* edits it; it is not read by generation and not frozen by a release, and its list hash names it. A new config file was refused: a 4.2.x tool quarantines it and stops. (2) The build workbook gets a sheet *Review* before *About*: the release entry of the version, the checklist with a tick column, every finding of the harness with its state (one function, `vcs/release.harness_findings`, which the release gate now uses too), the findings of the whole project, the values still open (placeholders, engineering values, the open checks of *Start here* with their count and first five items, example interface types, overrides), the sources (the ICD of each device connector it plugs into, each part with its approval and link) and how a number is explained; the verifier words it again (`core/outputs/verify_review.py`, `out_review`). (3) The editor gets a page *Review* per harness, the same blocks with *Show*, *Explain*, *Copy link*, the library state of each device and tick boxes kept on the computer only. (4) The ticks reach the release comment from the person releasing (the release dialog, `release --ticked POINTS`), as one note with the list hash and the points not ticked; no gate; not from a ticked sheet read back. (5) `explain DIR FINDING`. (6) *Settings > Project* shows the label format (design of 4.1.0, section 6.5). **Written files:** every build workbook changes once; the output-hash baseline, the numbers snapshot and the goldens are written again for this reason, and the proof of 3.0.0 gets its step 10; the comment of a release changes only in a project with a checklist. | The owner's answers to R1 to R12. The engineer's feedback of 2026-11-20 (point 9). |

The release decision of 4.3.0 is a later row (D-261), as D-259 followed D-258.

## 15. Owner questions

Each with our recommendation first. While a question is open, the pull requests follow the recommendation.

1. **R1. The checklist as the key `review_checklist` of `config/naming.json`, a list of texts, empty by default?** Recommended: yes. A 4.2.x tool keeps an unknown key of a known file and says nothing, while a new file `config/review.json` makes it stop with `quarantined` (section 2.6, tried); `naming.json` already holds the two release settings and is not frozen by a release. The name of the file is a reason to move the release keys into a file of their own with format 5, not before.
2. **R2. The template as the start, taken on purpose, all 26 points (the ECSS section included), and no point in a new project?** Recommended: yes. The points are those the tool already ships in a template; a person sees them before they are saved and takes out what does not apply. The alternative, a new project with the 17 points outside the ECSS section, would put review content into every project by itself.
3. **R3. The Review sheet in the build workbook, before *About*; none in the harness plan?** Recommended: yes. The build workbook exists for every harness and keeps the place of its other sheets; the plan is opt-in and the users' layout.
4. **R4. The ticks from the person releasing (the editor's page through the release dialog, and `release --ticked`), not from a ticked sheet read back?** Recommended: yes (section 6.1): a ticked copy in `outputs/` stops the release, a paper sheet cannot be read, and a read-back is an import of its own. Revisit if teams tick on screen in the workbook and ask for it.
5. **R5. No gate: a release with points not ticked, or with no ticks given, goes ahead and says so in its comment?** Recommended: yes. A checklist holds what the tool cannot judge; a gate would make the tool judge a person's tick. A setting `release_requires_review` (as `release_requires_asbuilt`) can follow if teams ask.
6. **R6. The open build data as one row per check with its count, the first five items and where to see them all, not every item?** Recommended: yes. One harness of `flatsat` has 173 such items; the *Cut list*, *Production* and *Connectors* sheets show each in amber already. Every finding and every engineering value is listed in full.
7. **R7. The Review page as an area of the rail after *As-built*, left out of the Systems engineer's rail, and the button of the step *Review and release* of the Next step page opening it?** Recommended: yes. It is a page per harness, like the As-built page; the Systems engineer reaches it from the Next step page, the menu and the palette.
8. **R8. The page's ticks kept on this computer (`QSettings`) and dropped when the list or the design changes?** Recommended: yes. A tick says *I looked at this design against this list*; after a change it says nothing. Nothing of it is in the project.
9. **R9. `explain DIR FINDING` in 4.3.0?** Recommended: yes. The sheet's *Finding* column points to it, and it is the limit 4.2.0 names; the order of today's lookup is kept.
10. **R10. The label format on *Settings > Project* (design of 4.1.0, section 6.5) in 4.3.0?** Recommended: yes, in the pull request of the page, which touches the same section. No file changes.
11. **R11. A type of construction `single` that shields per pair (section 17.2): out of 4.3.0, and later a check that names the combination instead of a fix in Generate?** Recommended: out of 4.3.0. Generate makes no group for it and the verifier reports `shield_missing` that *Regenerate* cannot fix. There is no group kind for a shielded pair that is not twisted (`shielded_pair` is twisted, `overall_shield` is the whole interface), so a fix would choose a meaning the type does not say. We recommend that the interface type check reports *construction single with shielding per_pair: choose twisted_shielded_pair, or shielding overall* in a later release, and that Generate stays as it is.
12. **R12. No command that prints the review view, no new key in `--json` of `release`, the scripting interface unchanged?** Recommended: yes. `export` writes the sheet; the note is in the comment that `log --json` prints. A script that needs the rows can be served by `api` later without a format change.

## 16. Pull requests

Small, each green on its own, each with its `CHANGELOG.md` entry.

| PR | Content | Guards |
|---|---|---|
| 1 | **Core, no output change.** `core/review.py` (`points`, `list_hash`, `points_from_text`, `parse_ticked`, `review_view` with no caller); `vcs/release.harness_findings`, used by `release_blockers` (the same blockers); the setting `naming.review_checklist` (`settings.py`, `configcheck`, `NOT_READ_BY_GENERATION`, `plan_set_checklist`); `config --review-checklist`; `docs/CONFIG.md`, `docs/CLI.md`; `tests/test_review_checklist.py`, `test_review_view.py` | `output_hashes --check` and `numbers_snapshot --check` *identical* |
| 2 | **The ticks in the release comment.** `review_note`, `plan_release(ticked=)`, the two blockers, `release --ticked`, `OPTIONS`; `docs/CLI.md`; `tests/test_release_ticks.py`; REQ-CC-11 | *identical*: no recorded project has a list |
| 3 | **`explain DIR FINDING`.** `cli/explain.py`, its help, `docs/CLI.md`; `tests/test_explain_finding.py` | *identical* |
| 4 | **The Review sheet.** `buildsheet._review_sheet`, `SHEETS`, *Start here*'s line, `build_workbook(..., findings)` from `build_outputs`; `core/outputs/verify_review.py`, `verify.py` `_build_review`, `_BUILD_SHEETS`, `expected_items`; `tests/test_review_sheet.py`, `test_review_verify.py`; step 10 of the proof and its fast test; REQ-OUT-16 | **changes written files**: the baseline (45 build workbooks), the numbers snapshot and the build workbook digests of `tests/fixtures/outputs/*.json` renewed for this one reason and read file by file; **the slow tests, the proof of 3.0.0 in `tests/format3_support.py` among them, run before the merge** |
| 5 | **The editor.** `gui/review_page.py`, the area `review` and its icon, `act-go-review`, the Next step button, the Releases tab button, the tree menu, the ticks in `QSettings`, the release dialog's note; *Settings > Project*: the checklist section and the label format (part F); `gui/strings.py`; `tests/test_ui_review_page.py`, the role tests; REQ-GUI-31 | *identical*: no written file |
| 6 | **End to end and documents.** `tests/test_e2e_430.py`; the pages of section 12; the guide; `docs/releases/4.3.0.md` | — |
| 7 | **The preparation of 4.3.0**: the version, the changelog section, the decision rows D-260 (as decided, with what was built where it differs) and D-261, the status pages | stamp only (`4.3.0` has five characters, as `4.2.0`) |

Order: 1 first; 2, 3 and 4 in any order after it; 5 after 2 and 4 (the page reads the view and hands the ticks to the release); 6 after 5; 7 last. Only pull request 4 changes written files, and it alone must run the slow tests before it is merged. 4.2.0 is tagged (`v4.2.0` on `6848510`), so nothing waits for a tag; a 4.2.x patch is made from the tag from pull request 4 on, because `master` then writes other build workbooks than 4.2.0.

Why the core comes first with no caller: the selection of 4.3 is the release gate's, and pull request 1 shows on its own that the gate gives the same blockers with it, before any file depends on it; 4.1.0 and 4.2.0 landed their cores the same way.

## 17. Corrections to the plan, and what was found on the way

Checked against the code at 4.2.0 and the runs of section 2.

1. **A per-harness list of findings exists, inside the release gate.** The plan says *nothing gathers them into one view per harness*. True for the screens and files; the gate selects the errors of a harness inline in `release_blockers`. E3 makes it one function (4.3) rather than a second copy.
2. **Found: a type of construction `single` that shields per pair gets no shield, and Generate then refuses to save.** On a copy of `flatsat` with the type `rs422` set to construction `single` (`shielding` stays `per_pair`, its signals keep their pairs), `generate` says *44 interfaces and 103 wires checked: 5 error(s)* and *Not saved: fix the errors above first*; the verifier reports `shield_missing` for IF-034 and IF-035 (W002), IF-033 (W004), IF-021 (W007) and IF-023 (W008). `generate/shields.plan` gives a `single` type no pair group (`for w in mine if t.construction != "single" else []`) and only the overall shield since 4.2.0. It is the case 4.2.0 fixed for `overall` (its section 16.1), for `per_pair`; none of the starter types is such a type. Out of E3 (R11).
3. **The list cannot be a new file of `config/`.** The plan says *a list in `config/`*. A new config file stops every 4.2.x tool (`quarantined`, section 2.6); the list is a key of `config/naming.json`.
4. **The ticks cannot go into the exported sheet in `outputs/`.** The plan says *the reviewer's ticks go into the sheet*. A changed file in `outputs/` stops the release (`outputs_modified`); the sheet is ticked on paper or in a copy, and the ticks reach the sheet afterwards through the release comment (6.4).
5. **No library device is *unverified* in format 4.** A device has no checked state (E5, point Ca). What is marked as example data are parts (`Part.unverified`, in the findings of `part-unapproved`) and interface types (`InterfaceType.unverified`: all 17 starter types of every example, which nothing lists today); the page also shows the library state of each device.
6. **The template's checklist is a start the program never reads.** The plan lists `templates → design-review-checklist.md` among the parts; it is a Markdown file to tick by hand, 26 points, 9 of them for the ECSS profiles. E3 reads it only when a person asks (3.2).

7. **Found by pull request 6: a release made in the editor writes no output file.** Section 6.4 says the ticks reach row 3 of the Review sheet *after the release writes the outputs again (`_restamp`)*. The command line's `release` does that (`cli/changes._restamp`); the editor's release, from the Review page or the Releases tab, records the release and its note and says *Export the outputs again so they show the released status*, as it did before 4.3.0. So the sheet of a harness released in the editor shows the release and the note after the next export; `tests/test_e2e_430.py` walks both ways. Nothing was changed for it.
8. **Found by pull request 6: `config DIR --review-checklist FILE` exits with 1 while an engineering value is missing.** Section 3.2 says the command prints the number of points and the list hash; it does, then prints the hand-over list of `config`, whose exit code is that of the list (section 3.1: *`config DIR` and its exit code do not change*), as `--counterparts` and `--distinct-roles` do. On `flatsat` (four values not set) the list is saved and the command ends with 1. The release notes and the user manual say so; a script reads the first line.

## 18. Risks and what this design does not check

- **Nobody at a review has seen the page or the sheet.** The order of the blocks, the first five items and the words are this design's; the engineer should read the sheet of `flatsat` W002 before 4.3.0 is tagged.
- **A long sheet.** W002 of `flatsat` has about 80 rows (section 4.4) without a checklist, about 105 with the template's points; a project with many device connectors per harness has a long *Sources* block. Nothing is cut; the page breaks are the reader's after the rule of 4.5.
- **The ticks are a statement.** The note records what the person releasing says; the tool cannot know who looked at what. The comment says *recorded by*, not *checked*.
- **Two copies of the selection of 4.3** (the core's and the verifier's) must agree; the Hypothesis test of 4.6 holds them together, as for the Production sheet.
- **The counts of section 2.8 come from a script that states the selection as written here**, not from the tool's code. Pull request 4 lists what moves in each golden; a difference from these counts is read before the renewal.
- **The page's ticks live on one computer.** A team that reviews on several computers records the ticks at the release, not on the page.
- **No code was written**; the module and function names are the plan, and the pull requests record where they differ.
