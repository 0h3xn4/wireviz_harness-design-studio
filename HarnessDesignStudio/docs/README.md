# Documentation map of Harness Design Studio

This page lists the documents of the tool, grouped by what you want to do. The index of the whole repository (including the WireViz documents) is [`../../docs/INDEX.md`](../../docs/INDEX.md).

## Contents

- [Getting started](#getting-started)
- [Do a task](#do-a-task)
- [Look something up](#look-something-up)
- [Examples and templates](#examples-and-templates)
- [Stuck](#stuck)
- [For developers](#for-developers)
- [Project records](#project-records)

## Getting started

| Document | For | What it gives you |
| --- | --- | --- |
| [`INSTALL.md`](INSTALL.md) | everyone | Install on Ubuntu (`.deb`, `.tar.gz`) or Windows (setup program, portable `.zip`), check the checksum and that it works, uninstall, build from source |
| [`VERIFY_OFFLINE.md`](VERIFY_OFFLINE.md) | everyone, IT departments | Verify it yourself in 30 minutes: run a downloaded package without network and under `strace` or Windows' audit, list its network code, look for your design data outside the project, switch Python plug-ins off; what is and is not claimed |
| [`GETTING_STARTED.md`](GETTING_STARTED.md) | newcomers | A guided tour with real output: example project, generate, read problems, export, fill in values, release |
| [`LEARNING_PATH.md`](LEARNING_PATH.md) | newcomers | The whole route in nine steps, with the example or template for each and how you know you are done |
| [`CONCEPTS.md`](CONCEPTS.md) | newcomers | The words and the mental model, in ten minutes |
| [`GLOSSARY.md`](GLOSSARY.md) | everyone | Every term and abbreviation, in plain words |

## Do a task

| Document | What it gives you |
| --- | --- |
| [`user-manual/`](user-manual/README.md) | One page per task: draw the design, add redundancy and zones, generate harnesses, read and fix problems, fill in engineering values, connect two connectors pin by pin (the pinout first, since 1.8.0), edit a wire, build a harness by hand (no interface needed), enter the build data (strip lengths, contacts, crimp tools, accessories), choose your role (Systems engineer, Electrical engineer or AIT engineer, and the Next step page), make a block diagram in five minutes (Quick mode and Export diagram), tell devices apart (the picture of each kind), follow the workflow, import data, define a device (and reuse it in another project), use the library (a folder your team shares with devices and subsystems, and a number of the same device, since 1.8.0), import KiCad pinouts, export the outputs, set wire colours, change IDs and the title block, release a harness, change a released harness, use Git and CI, script the tool (JSON output and the Python interface), see what the tool assumes and override a value with a reason, extend the tool, record what was built (as-built records) and export the open data, how auto-linking and the checks work, connector IDs and tags, and using the tool in an organisation (for safety, quality and IT) |
| [`HOWTO.md`](HOWTO.md) | The index of the old recipes, pointing at the user manual |
| [`TIPS.md`](TIPS.md) | Shortcuts, power-user workflows, and exchanging data with other tools |
| [`CHEATSHEET.md`](CHEATSHEET.md) | One page: the loop, the data imports, release, shortcuts, the folder layout, the words |

## Look something up

| Document | What it says |
| --- | --- |
| [`guide/USER_GUIDE.md`](guide/USER_GUIDE.md) | The user guide that opens with **F1** in the app: the window (rail, top bar, tabs, Home and Settings), modes, checks, export and import, menus, shortcuts |
| [`CLI.md`](CLI.md) | Every `harness-design-studio` command and option, and the keys of the JSON each prints with `--json` (generated from the program) |
| [`RULES.md`](RULES.md) | Every design rule: what, why, how to fix, severity (generated) |
| [`CONFIG.md`](CONFIG.md) | Every key of `config/*.json` |
| [`PLACEHOLDERS.md`](PLACEHOLDERS.md) | Which engineering values are still placeholders, who owns them |
| [`IMPORTS.md`](IMPORTS.md) | Importing interfaces, parts, lengths, engineering values, device pinouts and the build data |
| [`KICAD.md`](KICAD.md) | Taking device connector pinouts from a KiCad netlist |
| [`OUTPUTS.md`](OUTPUTS.md) | Every output file and its limits, and the build workbook |
| [`models/`](models/README.md) | The models of the tool for engineers: the equation, the inputs and their sources, the assumptions built in, a worked example, the definitions the tool fixes, the methods you can choose ([`selectable-models.md`](models/selectable-models.md)) and the as-built records. Wire sizing first |
| [`FILE_FORMAT.md`](FILE_FORMAT.md) | The project folder format |
| [`../CHANGELOG.md`](../CHANGELOG.md) | What changed, release by release |
| [`STATUS.md`](STATUS.md) | The status of the tool and its release history (latest published release, tags, commits), moved from the README |
| [`releases/`](releases/5.0.0.md) | The highlights of each release from 1.1.0 to 5.0.0, as the GitHub release page shows them (one file per version) |

## Examples and templates

| Document | What it gives you |
| --- | --- |
| [`examples/README.md`](examples/README.md) | The five example projects and the template files: what each is, how to run it, what you should see |
| [`examples/scripting/README.md`](examples/scripting/README.md) | Three Python scripts that drive the tool: a batch, a trade study, and every derivation as files |
| [`FLATSAT_EXAMPLE.md`](FLATSAT_EXAMPLE.md) | A tour of the biggest example, a flatsat with ground equipment |
| [`templates/README.md`](../src/harness_design_studio/resources/examples/templates/README.md) | What each file written by `harness-design-studio templates FOLDER` is for |

`harness-design-studio new --list` shows the example projects and `harness-design-studio templates FOLDER` copies the import templates, demo values, CI scripts and the review checklist. Screenshots of the app (the window of version 1.3.0 and later, light theme) are in [`ux/qt/`](ux/qt/) (see [`ux/README.md`](ux/README.md) for the other picture folders).

## Stuck

| Document | What it gives you |
| --- | --- |
| [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) | Real error messages and their fixes, by the step where they happen |
| [`FAQ.md`](FAQ.md) | Questions that are not errors |

## For developers

[`../../CONTRIBUTING.md`](../../CONTRIBUTING.md), [`developer/`](developer/README.md) (setup and tests, architecture, the scripts in `tools/`, keeping the documents correct, releasing, refreshing the upstream README), [`../CLAUDE.md`](../CLAUDE.md) (commands, layout and conventions, written for the AI assistant), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DECISIONS.md`](DECISIONS.md), [`SECURITY.md`](SECURITY.md) (and [`VERIFY_OFFLINE.md`](VERIFY_OFFLINE.md)), [`RELEASE.md`](RELEASE.md) (the checklist for releasing the tool, not a harness).

Some files are **generated** and a test fails when they are stale: `RULES.md` (`python -m tools.gen_rule_docs`), `CLI.md` (`python -m tools.gen_cli_docs`), the HTML of the user guide (`python -m tools.build_guide`), the example projects (`python -m tools.build_examples`), and the snapshot of the scripting interface (`python -m tools.gen_api_snapshot`). More in [`developer/docs-maintenance.md`](developer/docs-maintenance.md).

## Project records

These explain how the tool was specified and checked; you do not need them to use it.

| Document | What it says |
| --- | --- |
| [`SPEC.md`](SPEC.md), [`REQUIREMENTS.md`](REQUIREMENTS.md), [`UX.md`](UX.md) | What the tool must do and how it should feel |
| [`UX_GUIDELINES_REVIEW.md`](UX_GUIDELINES_REVIEW.md) | The owner's UX/UI guidelines, point by point: done, new, not applicable, open |
| [`DESIGN.md`](DESIGN.md) | The design system of the editor: tokens, type and spacing, themes, icons, state chips, tables, the diagram, the window, the views, shortcuts, decisions |
| [`ui/BEFORE_AFTER.md`](ui/BEFORE_AFTER.md), [`ui/UI_OVERHAUL.md`](ui/UI_OVERHAUL.md), [`ui/UI_OVERHAUL_PLAN.md`](ui/UI_OVERHAUL_PLAN.md), [`ui/PERF_BASELINE.md`](ui/PERF_BASELINE.md) | The new user interface of version 1.3.0: the window before and after, the brief, the plan and the timing numbers (decisions D-150 to D-159) |
| [`ait/AIT_FEEDBACK_PLAN.md`](ait/AIT_FEEDBACK_PLAN.md) | The feedback of the AIT engineers (ten requirements), what the tool did about each before 1.4.0, what version 1.4.0 built and in which milestone (decisions D-160 to D-165), and the later request to start a project from scratch, answered in 1.5.0 (D-166) |
| [`ait/TEST_USER_FEEDBACK_PLAN.md`](ait/TEST_USER_FEEDBACK_PLAN.md) | The feedback of the test users on 1.6.0 (a build spreadsheet instead of the PDF plans; the tool felt overwhelming), what the tool does about each, the decisions taken with the owner and the plan for 1.7.0, with what it built and what it did not |
| [`ait/PLAN_2.0.md`](ait/PLAN_2.0.md) | The plan for the programme towards 2.0.0 (a cable-first, free-form harness workflow, team and process features, a rebuilt user experience): what exists, the milestones M0 to M10, the migration safety net, the risks and the owner's decisions (D-200). Nothing in it is built yet |
| [`ait/SPIKE_M4_LOOSE_END.md`](ait/SPIKE_M4_LOOSE_END.md) | The report of the throw-away spike of milestone M4 of the 2.0 programme (the loose cable end as an ordinary connector): what was built, everything run over a project with loose ends, the wording and the open decisions, and at its end the eight decisions taken (D-201). Historical except section 8; M4a is built from it |
| [`ait/DESIGN_2.1_PORTS.md`](ait/DESIGN_2.1_PORTS.md) | The design of 2.1.0 (D-237): several interfaces on one connector, one interface per port, ports read from the signal names of fixed pins (`RS422_2_TX+`), no format change; what the program does at 2.0.1, the pin assignment, the editor and the six pull requests. All six are built; 2.1.0 is published (D-238, 2026-11-17) |
| [`ait/DESIGN_2.2_DEVICE_LIBRARY.md`](ait/DESIGN_2.2_DEVICE_LIBRARY.md) | The design of 2.2.0 (D-240): the device library as a folder of `NAME.device.json` files, `library.json`, the project's `device-libraries.json`, the import record as the link to the library, the update that shows a diff first, no format change; what exists, the workflows and the six pull requests. Its five pull requests of the program are built (246, 247, 248, 250 and 251); 2.2.0 is published (D-244; 2026-11-17, tag `v2.2.0`) |
| [`ait/DESIGN_2.3_BRANCHING.md`](ait/DESIGN_2.3_BRANCHING.md) | The design of 2.3.0 (D-243): branching harnesses in format 2 (the choice `per_connector_group` of `segmentation.mode`, the routing tree drawn by a person, the *Routing* sheet), and splices, which need a format change and are recommended for format 3 and 3.0.0; what the program does at 2.2, the format question piece by piece, the pull requests and the owner questions B1 to B9. Its six pull requests of the program are built (255, 262, 263, 264, 265 and pull request 7); 2.3.0 is published (D-245; 2026-11-18, tag `v2.3.0`). Since pull request 271 a new project starts in `per_connector_group` (D-247); 2.4.0 holds it and is published (D-248; 2026-11-18, tag `v2.4.0`). The splices of its section 6 are built in format 3 (pull request 282), and 3.0.0 holds them (D-249; published 2026-11-19, tag `v3.0.0`) |
| [`ait/DESIGN_3.0_HARNESS_PLAN.md`](ait/DESIGN_3.0_HARNESS_PLAN.md) | The design of 3.0.0 (D-242): the harness plan, one `.ods` file with formulas per harness in the users' layout (cover, change register, the harness sheet with device and harness side, `CON_…` sheets, notes), the fields of format 3 (pin level, the role *signal ground*, document data, part and source links, an optional colour code by pin number, with the users' code as an example), revisions as versions MAJOR.MINOR.PATCH and their migration, the word *Version* in place of *Revision* on screen and in every written file with the proof that allows exactly that change, the formula rules and the package bytes, branching, the pull requests, the owner's answers of 2026-11-17 to Q1 to Q27 and the questions Q28 to Q33 that the word change raises. Of it pull request R1 is built (pull request 272: one order of the revisions, `core/vcs/versions.py`, no format change), and 2.4.0 holds it (D-248; published 2026-11-18, tag `v2.4.0`); pull request 1 (format 3, versions, the word *Version* in the files) is merged after the tag as pull request 274, so `master` held unreleased work of 3.0.0 until its tag; every pull request of its section 12 is built, and 3.0.0 holds them (D-249: a major release with format 3; published 2026-11-19, tag `v3.0.0`); the search boxes of its section 25 (pull request 290) are in 3.1.0 (D-253; published 2026-11-19, tag `v3.1.0`) |
| [`ait/DESIGN_4.0_ROW_LAYOUT.md`](ait/DESIGN_4.0_ROW_LAYOUT.md) | The design of 4.0.0 (D-251), after the owner's yes of 2026-11-19 (D-250): the row layout of a connector (a Micro-D with the rows 1–11 and 12–21) in format 4, on the connector part and, where it differs, on a box connector; the keys and their rules, the step from 3 to 4 that writes only the number and its proof, what older tools do, the *Pin row* column of the pinouts and the harness plan, the rule `power-return-adjacent` on the face, the editor, `pin-rows`, the pull requests and the owner questions L1 to L4, which the owner answered as recommended on 2026-11-19. Its pull requests 1 to 6 and R are merged (#294 to #300), and pull request 7 is the preparation of 4.0.0 (D-254: a major release with format 4, which is frozen at its tag; published 2026-11-20, tag `v4.0.0`) |
| [`ait/ELEC_FEEDBACK_PLAN.md`](ait/ELEC_FEEDBACK_PLAN.md) | The feedback of an electrical engineer after a demo (November 2026; top request: production-ready output): what 4.0.0 does about each point, a fault of the label formats found on the way, the milestones E0 to E5 with their format impact and the owner questions. No decision of the owner yet; E0 is built (#306, in 4.0.1, D-255); E2 is designed (`ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`); E3 is designed (`ait/DESIGN_4.3_REVIEW_VIEW.md`); E4 is designed (`ait/DESIGN_4.4_NAMES_PORTS.md`); E5 is designed (`ait/DESIGN_5.0_FORMAT_5.md`), built by its pull requests 1 to 8 (merged) and published as 5.0.0 (D-266, 2026-11-24) |
| [`ait/DESIGN_4.1_PRODUCTION_SHEET.md`](ait/DESIGN_4.1_PRODUCTION_SHEET.md) | The design of 4.1.0, milestone E1 of the electrical engineer's plan (decision D-256; built and published as 4.1.0, D-257): a *Production* sheet in the build workbook and the harness plan with one row per pin and wire (far pin, wire part, colour, gauge, length, label at this end, shield ends), the label format `harness_device_connector` (`W001:MTQ1:J01`) for new projects, the plan's harness sheet over several pages, and the length reference on every length heading; no format change. Owner questions P1 to P10 and eight pull requests |
| [`ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`](ait/DESIGN_4.2_ELECTRICAL_CHECKS.md) | The design of 4.2.0, milestone E2 of the electrical engineer's plan (decision D-258; built and published as 4.2.0, D-259): four design rules, `pair-untwisted` (a signal pair not twisted together), `signal-unshielded` (a drawn wire whose signal its interface types shield, in no shield), `level-conflict` (two device pins whose levels the project keeps apart, joined by a net; the table `segregation.level_pairs_to_separate` is empty by default) and `wire-direction` (a net drawn by hand that joins two outputs or only inputs); the fix of Generate for a `single` type that shields overall; no format change. What each rule finds on the examples (nothing) and on the fixtures, owner questions C1 to C10 and six pull requests |
| [`ait/DESIGN_4.3_REVIEW_VIEW.md`](ait/DESIGN_4.3_REVIEW_VIEW.md) | The design of 4.3.0, milestone E3 of the electrical engineer's plan (decision D-260; built and published as 4.3.0, D-261): the review view. The project's review checklist as the key `review_checklist` of `config/naming.json` (empty by default; the template `design-review-checklist.md` is taken on purpose with `config --review-checklist`), a *Review* sheet in the build workbook and a *Review* page in the editor for each harness (the checklist with a tick column, every finding of the harness, the values still open, the ICD of each device connector, the page of each part, how a number is explained), the ticks in the release comment from the person releasing (`release --ticked`, the release dialog; not from a ticked sheet read back), `explain DIR FINDING` and the label format on *Settings > Project*; no format change. What the page and the sheet list on the five examples, owner questions R1 to R12 and seven pull requests |
| [`ait/DESIGN_4.4_NAMES_PORTS.md`](ait/DESIGN_4.4_NAMES_PORTS.md) | The design of 4.4.0, milestone E4 of the electrical engineer's plan (decision D-262; built and published as 4.4.0, D-263): names and ports. The setting `naming.far_device_names` (off by default): Generate gives an interface the port named after the device at its other end (`TTC2_TX+` … for the interface to TTC2) and never a port named after another device, checked by the verifier; the pairing of a connection reads the other device's name off a pin name and leaves out the pins of a third device. The project's signal map, the key `signal_map` of `config/naming.json` (empty by default): `import-pinout` and `import-netlist` write the type's name for a team's name, also inside a port. No ICD importer until an example is given; the fix of *Unassign* on a fixed pin; no format change, and no written file changes for a project that sets neither key. What 4.3.0 does today (run), owner questions N1 to N12 and eight pull requests |
| [`ait/DESIGN_5.0_FORMAT_5.md`](ait/DESIGN_5.0_FORMAT_5.md) | The design of 5.0.0, milestone E5 of the electrical engineer's plan (decision D-264, decided with the preparation of 5.0.0; its pull requests 1 to 8 are merged (#353, #357, #359 to #364), and pull request 9 is the preparation of 5.0.0 (D-266: a major release with format 5, which is frozen at its tag; published 2026-11-24)): format 5, a major release. The step from format 4 to 5 writes only the number, and every new key is sparse, so a missing value stays missing and the outputs of a format 4 project change only in the version stamp. Where a length is measured to at each end of a cable connector (`length_to`, face or rear; the setting `model.length_reference`) and the depth of a connector or backshell part (`depth_mm`); a current per device pin (`current_a`), from which the current of a wire, a split over parallel wires and a splice are checked; a splice in a harness made from a connection (a junction or a repeated pair in a link; Generate still makes none); where a shield end lands (`ShieldGroup.at_a`/`at_b`: connector, pigtail pin, backshell); the checked state of a library device (`Unit.checked`, `device-checked --by`). The fix of `update-device`, which did not compare the ICD fields and the level of a pin, as patch 4.4.1 first (published 2026-11-23). Owner questions F1 to F16 and ten pull requests |
| [`ait/DESIGN_5.1_FEATURE_TEMPLATES.md`](ait/DESIGN_5.1_FEATURE_TEMPLATES.md) | The design of 5.1.0 (decision D-268, proposed): a template for each feature, after the owner's request of 2026-11-24. A catalogue of every feature of the user manual, the rules and format 5 with the template that shows it today and in 5.1.0; fourteen small feature templates (`full-connectors`, whose device connectors carry a signal on every pin; `splice-by-hand` and `splice-from-connection`, the two ways to a spliced harness; `names-and-ports`, `branching-harness`, `loose-cable-end`, `shields-and-ends`, `lengths-to-the-face`, `released-harness`, `overrides-and-deviations`, `device-library`, `build-data-and-as-built`, `imports-from-files`, `extensions`), listed in a second group after the five examples; every number an EXAMPLE, every part unapproved; `create_project` copies `extensions/` and a library folder; the fix of the note `isolated`; no format change, a minor release. What 5.0.0 does today (run), owner questions T1 to T14 and eight pull requests |
| [`ux-audit.md`](ux-audit.md) | The October 2026 audit of the editor against the UX/UI Standard (83 numbered issues) and, at the end, what was built for each one |
| [`ux-custom-devices-audit.md`](ux-custom-devices-audit.md) | Audit and design proposal for custom devices (approved on 14 October 2026 and built as the Devices tab; the owner's decisions are at its end): what the tool does today for a device of your own (unit, connectors, pins, interfaces on pins, pinout import), the gaps, and a Devices tab with a pin table; pictures in [`ux/custom-devices/`](ux/custom-devices/) |
| [`DECISIONS.md`](DECISIONS.md), [`OPEN_DECISIONS.md`](OPEN_DECISIONS.md) | What was decided, and what still needs an owner |
| [`PLAN.md`](PLAN.md), [`demos/`](demos/README.md) | The plan and the note from each milestone |
| [`AUDIT.md`](AUDIT.md) | The October audit |
| [`AUDIT_1.8.0.md`](AUDIT_1.8.0.md) | The audit of version 1.8.0: ratings, findings, the plan for 1.8.1 to 2.0 |
| [`transparency_audit.md`](transparency_audit.md) | The transparency audit of version 1.11.1 (Phase 0, no code changed): what the tool hides, hard-codes and forces, how far real numbers can be traced, the state of 14 requirements, a proposed plan and the decisions needed. Nine appendices in [`transparency_audit/`](transparency_audit/configuration-and-defaults.md) hold the row-level catalogue |
| [`transparency_plan.md`](transparency_plan.md) | The plan to the complete release of the transparency work: stages S1 to S10, what each delivers and when it is finished |
| [`transparency_final_audit.md`](transparency_final_audit.md) | The final audit of the transparency work (S10): for each of the 14 requirements the original verdict, what was built, the evidence and the honest remaining gaps; the owner's open decisions; the limits of the verification. With [`transparency_trace_results.md`](transparency_trace_results.md), the 16 numbers of the audit traced again with the tool's own surfaces |
| [`changes.md`](changes.md) | Every change of the transparency work that moves something an engineer can see in a result: before and after, why, who agreed; and how the numbers are kept |
| [`../compliance/README.md`](../compliance/README.md) | The ECSS/ESCC self-assessment: matrix, gaps, deviations, sign-off, open actions, risks. No claim of compliance. |
| [`usability/`](usability/README.md) | The usability test kit |
| [`../../docs/DOCS_AUDIT.md`](../../docs/DOCS_AUDIT.md) | The audit of these documents |

Next: [`INSTALL.md`](INSTALL.md).
