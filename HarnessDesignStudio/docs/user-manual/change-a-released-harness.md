# Change a released harness

This page shows how to change a harness after it was released, by starting a new version, and how to see what changed and who changed it. What the three numbers of a version mean, and what became of the revision letters of 2.x, is on the page [Versions](versions.md).

**Example** (since 5.1.0): `harness-design-studio new practice --template released-harness` makes a finished example: W002 released as version 1.0.0, then its minor version 1.1.0 started with one change (the length of W002-L1), so `log` and `diff` show the history and the change.

## Contents

- [Before you start](#before-you-start)
- [1. Start a new version](#1-start-a-new-version)
- [2. Make the change](#2-make-the-change)
- [3. See what changed](#3-see-what-changed)
- [4. Release version 1.1.0](#4-release-version-110)
- [5. Read the history](#5-read-the-history)
- [Compare two copies of a project](#compare-two-copies-of-a-project)
- [Common mistakes](#common-mistakes)

## Before you start

- A harness is released and locked ([release a harness](release-a-harness.md)). This page continues with the practice project of that page: the harness `W002`, version 1.0.0, released.
- You never edit a released harness. You start a **new version** and choose its kind: **major** (not compatible with the versions before it), **minor** (adds something and stays compatible) or **patch** (a fix that stays compatible). From `1.0.0` they give `2.0.0`, `1.1.0` and `1.0.1`. The old version stays available, so it can always be reproduced.
- Editing a locked harness, a link it carries or a pin it uses is refused, with the reason. So is editing a **part** or **interface type** the harness uses (its connectors' and wires' parts, its contact and accessory parts, and the parts of the box connectors it plugs into) or the **configuration** its checks read (derating, EMC, segregation, title block, and the electrical and test values in the generation file), for example by importing parts or changing a derating value. Notes and names stay editable, and so does everything no released harness uses: new parts, other parts, the naming and segmentation settings. The exact list is in [`FILE_FORMAT.md`](../FILE_FORMAT.md#what-a-release-freezes). If the files were changed by hand anyway, `harness-design-studio check` reports it ([release a harness](release-a-harness.md#4-after-the-release)).

## 1. Start a new version

**On the command line**

```
harness-design-studio new-version wheel-link W002 --kind minor --by "A. Engineer" --comment "Add wire colours, nothing else changes"
```

```
New version 1.1.0 of W002: done.
```

`--kind` is required. `revise` is the older name of `new-version` and takes the same options. With `--kind major` the command adds a note: a major version says that the harness is not compatible with its earlier versions, and the harness plan template gives such a harness a new ID instead (TH01 becomes TH02). You can go on; the tool does not enforce it.

**In the app** (GUI, not run): select `W002` in the **Versions** tab (or the **Harness** tab), press **New version…**, choose **Minor** (none of the three is chosen at the start; each shows the version it gives, *1.0.0 → 1.1.0*), type your name and a comment (at least 10 characters), and press **Start new version**. The window first says what happens (the next version becomes a draft, the released one stays as a baseline) and lists what becomes editable, and what stays locked because another released harness uses it. A refused edit on the diagram or in the Inspector also offers **Start a new version…**. The app says "New version of W002 started; it can be edited again."

Version 1.1.0 is a `draft` that you can edit. Version 1.0.0 and its baseline are kept. If you find out later that the change is only a fix, choose the kind again before the review: `new-version wheel-link W002 --kind patch ...` makes it `1.0.1` and records *version changed* ([choose the kind again](versions.md#choose-the-kind-again)).

## 2. Make the change

Edit the design as usual. As an example, give the two power signals colours in `config/generation.json` (or use **Edit > Wire colours…**; see [set wire colours](set-wire-colours.md)), then generate. (Wire colours are **not in the 0.1.0 packages**. With a 0.1.0 package, make a different change; the output below then differs.)

```
harness-design-studio generate wheel-link
```

```
0 added, 1 changed, 1 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
2 interfaces and 6 wires checked: 0 error(s)
```

## 3. See what changed

**On the command line**

```
harness-design-studio diff wheel-link W002
```

```
# W002: working design against version 1.0.0

Comparing before with after: 0 added, 0 removed, 3 changed.

## Changed (3)

- Harness `W002`
  - approver: A. Engineer -> (none)
  - checker: B. Checker -> (none)
  - released_on: 2026-10-22 -> (none)
  - status: released -> draft
  - version: 1.0.0 -> 1.1.0
- Wire `W002-001`
  - colour: (none) -> red
- Wire `W002-002`
  - colour: (none) -> black
```

Without `--from` and `--to` the command compares the working design with the latest baseline. The harness lines (approver, status, version) are the release bookkeeping that a new version resets. `--from` and `--to` take a version; an old letter of 2.x is read as its version (`--from A` is `1.0.0`), and the command says so in its first line. The wire lines are your change.

**In the app**: open the **Versions** tab, pick the harness and use **Compare version … with …** (a baseline, another version or the working design). The differences are grouped by kind with counts, and each row is tinted by the kind of change; added and removed objects say "(did not exist)" and "(removed)". A line says what the released harness locks. **Mark on diagram** marks the changed devices and interfaces on the diagram; **Clear marks** removes the marks. **Changes…** in the **More** menu of the **Harness** tab (also **Design > Show changes of harness…**) opens the window "Changes in W002" with the same marks.

## 4. Release version 1.1.0

Export, then release as before. Submitting for review first is optional, as on [release a harness](release-a-harness.md):

```
harness-design-studio export wheel-link
harness-design-studio release wheel-link W002 --by "A. Engineer" --comment "Version 1.1.0 with wire colours" --accept-placeholders "Practice project: demo values only" --accept-unapproved-parts "Practice project: example parts only"
```

```
35 files written to wheel-link/outputs (model <hash>).
Release W002 version 1.1.0: done.
Outputs re-exported with the released status (35 files).
```

When the version is minor or patch and the change reaches an end that plugs into a device (a cable connector's part, gender or keying, the device connector it mates with, or a wire added, removed or moved at such a connector), `review` and `release` add a line `Note: This version changes the pinout at a device (...). The harness plan template calls that an incompatible change.` The colours of this example change no pinout, so there is no note. The note blocks nothing ([the notes](versions.md#the-notes-on-the-kind)).

Now both versions have a baseline, and you can compare them:

```
harness-design-studio diff wheel-link W002 --from 1.0.0 --to 1.1.0
```

```
# W002: version 1.0.0 to 1.1.0

Comparing before with after: 0 added, 0 removed, 3 changed.

## Changed (3)

- Harness `W002`
  - checker: B. Checker -> (none)
  - version: 1.0.0 -> 1.1.0
- Wire `W002-001`
  - colour: (none) -> red
- Wire `W002-002`
  - colour: (none) -> black
```

Before version 1.1.0 is released, `--to 1.1.0` fails: `error: W002 has no baseline for version 1.1.0.` (exit code 2). Compare with the working design instead, as in step 3.

## 5. Read the history

```
harness-design-studio log wheel-link
```

```
Entry | Harness | Version | Event | By | Date | Comment
C0001 | W002 | 1.0.0 | submitted for review | A. Engineer | 2026-10-22 | 
C0002 | W002 | 1.0.0 | released | A. Engineer | 2026-10-22 | First release of the wheel power harness [Released on placeholder configuration (...); accepted by A. Engineer: Practice project: demo values only] [...]
C0003 | W002 | 1.1.0 | new version started | A. Engineer | 2026-10-22 | Add wire colours, nothing else changes
C0004 | W002 | 1.1.0 | released | A. Engineer | 2026-10-22 | Version 1.1.0 with wire colours [Released on placeholder configuration (...); ...] [...]
```

(Long parts of the comment column are shortened here with `...`.) A kind chosen again shows as *version changed*. Add a harness ID (`harness-design-studio log wheel-link W002`) to see one harness. In the app: the timeline of the **Versions** tab, or **Change log…** in the **More** menu of the **Harness** tab (also **Design > Show change log of harness…**). The entries cannot be deleted. The outputs also have them: `system/changelog.csv` and `system/version_report.md`.

## Compare two copies of a project

To see what differs between two project folders (for example two Git checkouts, or a copy you made before the change with `cp -r wheel-link wheel-link-1.0.0`):

```
harness-design-studio compare wheel-link-1.0.0 wheel-link
```

```
# Project comparison

Comparing wheel-link-1.0.0 with wheel-link: 3 added, 0 removed, 4 changed.

## Added (3)

- Baseline `W002.1.1.0`
- Change log entry `C0003`
- Change log entry `C0004`

## Changed (4)

- Configuration `generation`
  - values: {'conductor_resistivity_ohm_m': 1.72e-08, 'default_gauge_awg': None, 'mass_ma... -> {'conductor_resistivity_ohm_m': 1.72e-08, 'default_gauge_awg': None, 'mass_ma...
- Harness `W002`
  - checker: B. Checker -> (none)
  - version: 1.0.0 -> 1.1.0
- Wire `W002-001`
  - colour: (none) -> red
- Wire `W002-002`
  - colour: (none) -> black
Not compared: the generation record, the contents of baselines (only their version, date, name, comment and hash), and the files of the outputs folders.
```

It does not change either folder. It compares the devices, interfaces, connectors, harnesses, wires, parts, interface types, configuration, waivers, the project name and description, the zones, the library information, the diagram positions, the baselines and the change log, and it ends with a line that names what it does not compare. Equal folders print `No differences.` followed by that line. See [use Git and CI](use-git-and-ci.md).

## Common mistakes

- **Editing the JSON of a released harness, or of a part, interface type or configuration value it uses.** Start a new version instead. `harness-design-studio check` finds the edit (`released_modified`).
- **"This change was blocked because it touches released items" when you import parts, apply a profile or change a derating value.** A released harness uses those parts or values. Start a new version of that harness (of each released harness, for configuration), make the change, and release again. The command ends with exit code 1 and changes nothing; `--dry-run` says it would be blocked.
- **Forgetting to export after the release.** `harness-design-studio release` exports for you; after a new version you still export yourself before the next release.
- **"W002 has no baseline for version 1.1.0."** Version 1.1.0 is not released yet.
- **"--kind" missing.** `new-version` needs the kind; the tool does not choose it for you.
- **Deleting a released harness.** The app does not allow it. Start a new version and change it.

More: [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md), [`CLI.md`](../CLI.md#harness-design-studio-new-version).

Next: [versions](versions.md), [use Git and CI](use-git-and-ci.md), [release a harness](release-a-harness.md)
