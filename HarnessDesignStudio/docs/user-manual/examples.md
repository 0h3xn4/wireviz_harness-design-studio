# Examples: one project per feature

This page lists every feature of the tool with the example project that shows it, and the manual page that explains it. It says how to make a project from an example, in the app and on the command line, and what the numbers and parts in an example are (and are not).

**In one minute.** The tool ships 19 example projects in two groups. The group *Start* holds the five projects to begin with (`first-steps` is the one for the tutorial). The group *Feature examples* (since 5.1.0) holds 14 small projects of two to four devices, one feature each. `harness-design-studio new practice --template splice-by-hand` makes your own copy of one, in a new folder; the example itself never changes. The numbers and parts in the examples are EXAMPLE data for learning, not engineering data.

## Contents

- [Make a project from an example](#make-a-project-from-an-example)
- [The two groups](#the-two-groups)
- [Every feature and its example](#every-feature-and-its-example)
- [What no example shows](#what-no-example-shows)
- [EXAMPLE values and parts are not engineering data](#example-values-and-parts-are-not-engineering-data)
- [What a copy holds](#what-a-copy-holds)
- [Common mistakes](#common-mistakes)

## Make a project from an example

**On the command line.** List the examples, then make a copy of one in a folder that does not exist yet (or is empty):

```
harness-design-studio new --list
harness-design-studio new practice --template splice-by-hand
```

`new --list` prints a heading line per group, *Start:* and *Feature examples (small projects, one feature each; the manual page Examples lists them):*, and under each heading one line per example: its name and what it holds. `new` says what it made:

```
Project 'Splice by hand (EXAMPLE)' created in practice (3 devices, 0 interfaces).
Next: harness-design-studio validate practice   or open it in the app (File > Open project).
```

`--name TEXT` gives the copy another name. `new --list --json` gives each example with its `group` (`start` or `feature`), for a script ([script the tool](script-the-tool.md)). The full list of options is in [`CLI.md`](../CLI.md#harness-design-studio-new).

**In the app.** Choose **File > New project from an example…**. The list of the window *New project* has a heading row per group, **Start** and **Feature examples**, and the examples under each; a heading cannot be chosen, and the arrow keys pass over it. Pick an example (its summary shows under the list), choose an empty folder, type a name and press **Create project**. The window opens with `first-steps` chosen.

**From Home.** The **Home** page lists the group *Start* and ends with one line, *14 feature examples, one per feature: File > New project from an example…*, and the button **Show the feature examples…**. The button opens the same window with the first feature example, `full-connectors`, chosen. As a Systems engineer, Home is not in the rail: open it with **Go > Go to Home** (Ctrl+7).

**Then look at it.** A feature example opens ready to look at: every example that has an interface is shipped generated, so the Harness tab and the outputs have content, and `generate` has nothing to do. On every feature example `check` gives 0 errors and 0 warnings, `drc` gives no open error, and `export` writes the outputs that `verify --outputs` checks with 0 errors:

```
harness-design-studio check practice
harness-design-studio drc practice
harness-design-studio export practice
harness-design-studio verify practice --outputs
```

The last line of `check practice` is `3 devices, 0 interfaces, 8 connectors, 1 harnesses: 0 error(s), 0 warning(s).` What `drc` still names on every example is said [below](#example-values-and-parts-are-not-engineering-data). Steps in the app are described from the program's own texts and code; they have not been run on a screen.

## The two groups

**Start**: the five projects of 1.0.0, unchanged.

| Example | What it is |
| --- | --- |
| `blank` | An empty project with the starter parts and interface types and no devices: your own design. |
| `first-steps` | Three devices, a power link and an RS-422 link, nothing generated yet: the tutorial ([`GETTING_STARTED.md`](../GETTING_STARTED.md)) and most pages of this manual. |
| `minimal-satellite` | Seven devices, nominal only: a small spacecraft to adapt. |
| `small-satellite` | 14 devices with nominal and redundant chains. |
| `flatsat` | A complete bench of 23 flight and ground devices, generated, with EXAMPLE numbers ([`FLATSAT_EXAMPLE.md`](../FLATSAT_EXAMPLE.md)). |

What each of the five prints is on the [examples page](../examples/README.md).

**Feature examples** (since 5.1.0): small projects in the order of this manual. The page of each says what to look at in it, in the line *Example* under its title.

| Example | What it shows | Page |
| --- | --- | --- |
| `full-connectors` | PCDU1, OBC1 and TTC1 with six nine-way device connectors whose 54 pins all carry a fixed, named signal; named ports, each interface put on its port; the pin rows 1 to 5 over 6 to 9; keyed connectors; generated, no spare pin | [Define a device](define-a-device.md), [Pin rows of a connector](pin-rows-of-a-connector.md) |
| `names-and-ports` | OBC1 talks to TTC1 and TTC2 on one connector, whose ports are named after them; the pinouts read in the team's words through the project's signal map | [Define a device](define-a-device.md), [Import data](import-data.md) |
| `splice-by-hand` | A power line drawn by hand from PCDU1 to OBC1 and TTC1 through two splices of the EXAMPLE part `EX-SPLICE-1` | [Splices](splices.md), [Build a harness by hand](build-a-harness-by-hand.md) |
| `splice-from-connection` | A connection that joins one pin to two (a junction), with pin currents; the harness made from it carries the splices | [Connect two connectors](connect-two-connectors.md), [Splices](splices.md) |
| `branching-harness` | Four devices; Generate makes two harnesses that branch where one connector serves two devices | [Branching harnesses](branching-harnesses.md) |
| `loose-cable-end` | A cable from a port with its far end loose, and a leg added to it; a release asks for a reason | [Build a harness by hand](build-a-harness-by-hand.md), [Branching harnesses](branching-harnesses.md) |
| `shields-and-ends` | A grounding concept, shield groups, pigtails landed on pins and on the lug of a backshell, 360 degree ends in backshells, one end without a place | [Enter the build data](enter-the-build-data.md) |
| `lengths-to-the-face` | Segments measured to the mating face; the depth of each connector and backshell taken off each wire; the length model with a cut allowance | [Lengths to the face](lengths-to-the-face.md) |
| `released-harness` | A harness reviewed and released with a checklist and three different people, then its next version started | [Release a harness](release-a-harness.md), [Versions](versions.md) |
| `overrides-and-deviations` | A gauge set by hand with its reason, a warning waived and two errors accepted as deviations | [Override a value and keep a history](override-and-keep-a-history.md) |
| `device-library` | Devices taken from a library folder inside the project: one checked, one with a copy, one changed in the library since; a subsystem | [Use the library](use-the-library.md) |
| `build-data-and-as-built` | Strip lengths, a contact and its crimp tool, accessories, a colour code by pin and a Cover for the harness plans; then a record of what was built, with one value out of its limit | [Enter the build data](enter-the-build-data.md), [Record what was built](record-what-was-built.md) |
| `imports-from-files` | The devices of `first-steps` and what the import templates hold, each import with its record | [Import data](import-data.md) |
| `extensions` | A rule and a table in data files, and a Python plug-in that stays off until you trust it | [Extend the tool](extend-the-tool.md) |

## Every feature and its example

*Every example* means that any example shows the feature once you open it (and generate it, where Generate has something to make). Where no example shows a feature, the page's steps are the way to see it ([what no example shows](#what-no-example-shows)).

| Feature | Example | Page |
| --- | --- | --- |
| The roles, the Next step page | `first-steps` (the roles show the same data of any project) | [Choose your role](choose-your-role.md) |
| Quick mode, *Export diagram* (SVG, PDF, PNG) | `first-steps`, `minimal-satellite` | [Make a block diagram in five minutes](quick-diagram.md) |
| Devices, interfaces, lanes, Guided and Expert mode | `first-steps`, `minimal-satellite` | [Draw the design](draw-the-design.md) |
| The looks of the devices and their *Kind* | `flatsat`, `minimal-satellite` | [Telling devices apart](telling-devices-apart.md) |
| Redundant copies, `cross-strap`, zones and lanes | `small-satellite`, `flatsat` | [Redundancy and zones](redundancy-and-zones.md) |
| Generate: preview, apply, undo, the self-check; one harness per pair of connectors (`per_connector_pair`) or per pair of zones (`per_zone_pair`) | `first-steps`, `flatsat` | [Generate harnesses](generate-harnesses.md) |
| One harness per device connector that branches (`per_connector_group`, the start of a new project) | `branching-harness` | [Generate harnesses](generate-harnesses.md), [Branching harnesses](branching-harnesses.md) |
| Errors, warnings and notes, their fixes, `drc` | every example | [Read and fix problems](read-and-fix-problems.md) |
| A waiver of a warning | `overrides-and-deviations` | [Read and fix problems](read-and-fix-problems.md) |
| The rules of mating halves and look-alike connectors, spare pins, the gap between power and return pins | `full-connectors` (keyed connectors; with a spare fraction or a pin gap set, `spare-pins-low` and `power-return-adjacent` speak), `overrides-and-deviations` (a waived `connector-lookalike`) | [Read and fix problems](read-and-fix-problems.md), [`RULES.md`](../RULES.md) |
| Engineering values, `config`, the demo values | `flatsat` and every feature example with *(EXAMPLE)* in its name | [Fill in the engineering values](fill-in-engineering-values.md) |
| The current rules with values (`current-over-wire`, `voltage-drop`, `bundle-current`, `current-over-contact`) | `flatsat`, `overrides-and-deviations` (a `current-over-wire` and a `voltage-drop` error accepted) | [Fill in the engineering values](fill-in-engineering-values.md) |
| Settings, assumptions, `explain`, the selectable models | `lengths-to-the-face` (the length model `path_loops_allowance_twist`) | [See what the tool assumes](see-what-the-tool-assumes.md) |
| `override`, `deviation`, the journal | `overrides-and-deviations` | [Override a value and keep a history](override-and-keep-a-history.md) |
| Imports: interfaces, parts, lengths, build data; the import record, `imports` | `imports-from-files` | [Import data](import-data.md) |
| A KiCad netlist, fixed pins, a signal map | `imports-from-files`, `names-and-ports` (the signal map) | [Import KiCad pinouts](import-kicad-pinouts.md) |
| A device: pins, signals, roles, directions, fixed pins, `import-pinout`, `export-pinout` | `full-connectors`, `imports-from-files` (the pinout of GYRO1) | [Define a device](define-a-device.md) |
| Device connectors with a signal on every pin | `full-connectors` | [Define a device](define-a-device.md) |
| Ports (a named port, *Assign… Port*) | `full-connectors`, `names-and-ports` | [Define a device](define-a-device.md) |
| Ports named after the far device (`naming.far_device_names`), the project's signal map (`naming.signal_map`) | `names-and-ports` | [Define a device](define-a-device.md) |
| A current per pin, the current of a wire from its pins | `splice-from-connection` | [Define a device](define-a-device.md) |
| The rows of pins on the face of a connector, the column *Pin row*, `pin-rows` | `full-connectors` | [Pin rows of a connector](pin-rows-of-a-connector.md) |
| A connection: pairing, *Check my connections*, *Create harness*, the connection list | `splice-from-connection` | [Connect two connectors](connect-two-connectors.md) |
| Wires drawn by hand, the gauge and colour of a wire; a generated wire changed by hand | `splice-by-hand`, `overrides-and-deviations` | [Edit a wire](edit-a-wire.md) |
| Wire colours | `flatsat`, `splice-by-hand` (red and black on the wires drawn by hand) | [Set wire colours](set-wire-colours.md) |
| A harness built by hand | `splice-by-hand` | [Build a harness by hand](build-a-harness-by-hand.md) |
| The electrical rules of drawn wires (`wire-direction`, `level-conflict`) | `splice-by-hand` (pin directions that fit, so the rules are quiet) | [Build a harness by hand](build-a-harness-by-hand.md) |
| A cable with a loose end, a new leg, `release --accept-loose-ends` | `loose-cable-end` | [Build a harness by hand](build-a-harness-by-hand.md), [Branching harnesses](branching-harnesses.md) |
| Branch points, segments, the *Routing* table, `routing` | `branching-harness`, `flatsat` | [Branching harnesses](branching-harnesses.md) |
| A splice drawn by hand (a splice part, *Add splice*, *Splice this wire*, the column *Via*, the tests through a splice) | `splice-by-hand` | [Splices](splices.md) |
| A splice from a connection (a junction) | `splice-from-connection` | [Splices](splices.md), [Connect two connectors](connect-two-connectors.md) |
| Lengths to the mating face, the depths of connector and backshell parts | `lengths-to-the-face` | [Lengths to the face](lengths-to-the-face.md) |
| Strip lengths, contacts and crimp tools, accessories | `build-data-and-as-built` | [Enter the build data](enter-the-build-data.md) |
| Shield groups, the grounding concept, where a shield end lands | `shields-and-ends` | [Enter the build data](enter-the-build-data.md) |
| The build workbook, the PDF drawings, the system files | every example (`export`); `build-data-and-as-built` (the build data in the workbook) | [Export the outputs](export-the-outputs.md) |
| The harness plans, `document` (the Cover), the colour code by pin, the *Production* sheet | `build-data-and-as-built` | [Export the harness plans](export-the-harness-plans.md) |
| Name patterns, label formats, the title block | `build-data-and-as-built` (the label format, the title block), `released-harness` (the author, checker and approver) | [Naming and title block](naming-and-title-block.md) |
| Review, release, the gates, the review checklist and its ticks, different people | `released-harness` | [Release a harness](release-a-harness.md) |
| A new version, `diff`, `log`, the version report | `released-harness` | [Change a released harness](change-a-released-harness.md), [Versions](versions.md) |
| `.gitattributes`, `check`, a build script for CI | every example | [Use Git and CI](use-git-and-ci.md) |
| The device library: a library folder, `add-device`, `update-device`, `save-device`, a number of the same device, subsystems | `device-library` | [Use the library](use-the-library.md) |
| The checked state of a device (`device-checked`) | `device-library` | [Use the library](use-the-library.md) |
| `--json`, the Python interface | every example; the scripts of [`examples/scripting/`](../examples/scripting/README.md) | [Script the tool](script-the-tool.md) |
| `export-data`, the run record | every example; [`examples/open-data/`](../examples/open-data/) | [Export the data](export-the-data.md) |
| Extensions: a data rule, a table, a Python plug-in, `extensions`, `trust` | `extensions` (the plug-in stays untrusted) | [Extend the tool](extend-the-tool.md) |
| `workflow`, the nine steps | every example | [Follow the workflow](follow-the-workflow.md) |
| The as-built record (`export-asbuilt`, `import-asbuilt`, `asbuilt`) | `build-data-and-as-built` | [Record what was built](record-what-was-built.md) |
| `schema`, `templates`, `new --annotate-config` | every example | [`CLI.md`](../CLI.md) |

## What no example shows

Some features need another project, another person or a step that a shipped project cannot hold. The page's own steps show them on a copy:

- **Standard profiles** (`config --apply-profile`): a profile writes a standard's values, and no example carries them ([fill in the engineering values](fill-in-engineering-values.md)).
- **Join into one harness**: a join needs two harnesses drawn by hand that plug into one device connector; draw a second cable on a copy of `loose-cable-end` and join the two ([branching harnesses](branching-harnesses.md)).
- **`compare`** compares two folders: compare a copy of `released-harness` with another copy you changed ([change a released harness](change-a-released-harness.md)).
- **`merge-fix`** needs two Git branches that both pressed Generate ([use Git and CI](use-git-and-ci.md)).
- **`migrate`**: `new` writes the current format, so no example is in an older one ([upgrade a project](upgrade-a-project.md)).
- **A trusted plug-in**: a trust is kept in your own settings folder, never in a project, so `extensions` ships its plug-in untrusted; `trust` is the exercise ([extend the tool](extend-the-tool.md)).
- **An open error**: no example ships one (`drc` would end with exit code 1). `overrides-and-deviations` holds two errors accepted as deviations; the page [build a harness by hand](build-a-harness-by-hand.md) makes `wire-direction` speak on a copy.
- **What the tool is, for safety, quality and IT**: not a feature of a project ([using HDS in your organisation](use-hds-in-your-organisation.md)).

## EXAMPLE values and parts are not engineering data

- **Every engineering number in an example is an EXAMPLE**: the values come from the demo files of the templates (`config-demo-values/`, see [`PLACEHOLDERS.md`](../PLACEHOLDERS.md)), and a feature example adds its own EXAMPLE numbers only where its feature needs one (a depth, a pin current, a contact rating, a segment length, a tolerance); its page says which. They are not from any standard and not from any supplier.
- **Every configuration file stays marked `"placeholder": true`**, so `check` names the placeholders and a release asks for a written reason.
- **Every part is an example part**: its number starts with `EX-` (or is the `TBD-CONNECTOR` of a loose end), and the parts a feature example adds (`EX-SPLICE-1`, `EX-BACKSHELL-MICROD`, `EX-CONTACT-22`) say *EXAMPLE ONLY: not a real part* in their description and are marked unverified. No example approves a part; `imports-from-files` reads every status of its parts list as *Review*.
- **An example with an engineering number says so in its name**: its title ends with *(EXAMPLE)*, so the title block of every drawing and plan made from it says so too. `flatsat` says *EXAMPLE numbers, not engineering data*.
- **The people, companies, devices and documents are made up**: *Designer 1*, *Checker 1*, *Releaser 1*, *Reviewer 1*, *Example Ltd*, *ICD-OBC EXAMPLE Issue 2*.
- **What `drc` names on every example.** One `part-unapproved` warning for each `EX-` part in use, and a note `unchecked-config` for each placeholder value a rule needs. A feature example names nothing else that is open, apart from what its page names (`extensions`: the plug-in that is not trusted). These findings are the point: the tool does not treat EXAMPLE data as checked.

Do not copy a number of an example into a real design. Your programme's own values and approved parts replace them ([fill in the engineering values](fill-in-engineering-values.md), [import data](import-data.md)).

## What a copy holds

- **The project, in the current format.** `new` writes the model of the example into your folder, with a `.gitattributes` ([use Git and CI](use-git-and-ci.md)).
- **A journal from the first step.** The examples hold no journal; `new` starts one (`journal.jsonl`) unless you give `--no-journal`, so every change you make is recorded. A deviation of `overrides-and-deviations` therefore shows *who and when* as not recorded.
- **The files beside the model, for two examples.** `new` also copies the folder `extensions/` (`extensions`), the file `device-libraries.json` and the library folders it names inside the example (`device-library`), and nothing else. A plug-in is never trusted by the copy.
- **No outputs.** No example ships `outputs/`: run `export`.
- **Releases, waivers, deviations, import and as-built records** stay as the example has them, with fixed EXAMPLE dates.

## Common mistakes

- **`error: Unknown template 'splice-by-hand'`.** The tool is older than 5.1.0, or the name is mistyped: `harness-design-studio new --list` shows the names your version has ([`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md#creating-a-project)).
- **`error: practice already exists and is not an empty folder; choose a new one.`** `new` writes only into a new or empty folder (exit code 2). Pick another name.
- **`extensions practice` ends with exit code 1.** The plug-in of `extensions` is not trusted until you trust it; that is the exercise ([extend the tool](extend-the-tool.md)).
- **`asbuilt practice` ends with exit code 1 on `build-data-and-as-built`.** One measured length is out of its EXAMPLE tolerance on purpose ([record what was built](record-what-was-built.md)).

Next: [choose your role](choose-your-role.md), [draw the design](draw-the-design.md), [`GETTING_STARTED.md`](../GETTING_STARTED.md)
