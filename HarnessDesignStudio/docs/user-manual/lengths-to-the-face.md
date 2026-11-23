# Lengths to the face

This page shows how to tell the tool that your segment lengths run to the **mating face** of a cable connector instead of its rear, how to give each connector part and backshell its **depth**, and what the lengths, the checks and the written files then say. A length taken from a mechanical model of the boxes often runs to the face of the connectors; the cut length of a wire runs from rear to rear.

> **New in 5.0.0** (format 5, decision D-264 proposed, [`DESIGN_5.0_FORMAT_5.md`](../ait/DESIGN_5.0_FORMAT_5.md) part A). A project of 4.x is upgraded once first ([upgrade a project](upgrade-a-project.md#9-from-format-4-to-format-5-500)). The model and its equation are on [wire length](../models/wire-length.md#a-face-end-and-the-depth-of-a-connector); the keys of the files are in [`FILE_FORMAT.md`](../FILE_FORMAT.md#lengths-to-the-face-part-a); what each written file holds is in [`OUTPUTS.md`](../OUTPUTS.md#a-face-end). The examples below are the walk of `tests/test_e2e_500.py` on the sample `mini3`; the depths in them are made up.

## Contents

- [What a face end is](#what-a-face-end-is)
- [Before you start](#before-you-start)
- [1. Say where the segments are measured to](#1-say-where-the-segments-are-measured-to)
- [2. Give the parts their depths](#2-give-the-parts-their-depths)
- [3. Generate and read the lengths](#3-generate-and-read-the-lengths)
- [What the checks say](#what-the-checks-say)
- [What the written files show](#what-the-written-files-show)
- [Older versions of the tool](#older-versions-of-the-tool)
- [Common mistakes](#common-mistakes)

## What a face end is

- A routing segment that ends at a cable connector runs to its **rear**, where the wires leave the connector body or its backshell. That is what every length meant before 5.0.0, and it stays the default.
- A **face end** is a cable connector whose segments run to its **mating face**. The project says it for every cable connector (the setting `model.length_reference`, `rear` or `face`), and one connector may say otherwise (`length_to` in its harness file: `face` or `rear`; unset follows the project). Only a cable connector has a face: a splice, a branch point or a loose end has none.
- The **depth** of a face end is the depth of the connector's part (from the mating face back to where the wires leave) plus the depth of the part of each backshell on that connector (what it adds behind the rear). At a face end the tool takes the depth off the path of each wire, so the length of a wire stays a length from **rear to rear**, the cut length. Service loops are added as before.
- **A depth is never assumed** (assumption `A-LENGTH-TO`). A face end without a depth leaves its wires without a length, and `check` says why.

## Before you start

- The project is in format 5 (5.0.0).
- The segments have lengths ([branching harnesses](branching-harnesses.md#how-lengths-are-measured), `import-lengths`).
- The tool ships no depth: the starter parts have none. Take the depths of your connector and backshell parts from their datasheets.

## 1. Say where the segments are measured to

**For the whole project.** In the editor: **Settings > Project**, *Segments are measured to*, **rear** or **mating face** (one undo step; off in a read-only project and while a release froze the value). On the command line:

```
harness-design-studio settings DIR --set model.length_reference='"face"'
```

**For one cable connector.** Select it and set **Lengths measured to** in the Inspector: *the project's (face)*, *rear* or *face* (one undo step, also on a harness Generate made, which keeps the choice; off for a released harness). From a file, with a table of cable ends of `import-build-data` ([enter the build data](enter-the-build-data.md#3a-cable-ends-and-shield-ends-since-500)):

```
Connector,Lengths to
W002-P2,rear
```

`project` in the column gives a connector back to the project's setting.

## 2. Give the parts their depths

**In the editor.** In the Inspector of a connector or backshell part, type **Depth (mm)**: `22`, or `25,5` (one undo step; an empty field clears it; refused while a released harness uses the part). A part of another category has no depth.

**From a file.** `import-parts` reads a column *Depth (mm)* (also *Depth* or *Connector depth*), in millimetres, for a connector or backshell part; on a part of another category it refuses the row:

```
part number,manufacturer,description,category,approval status,Depth (mm)
EX-MICROD-25-M,Example Ltd,Micro-D 25 plug (example),connector,Approved,22
EX-BACKSHELL-25,Example Ltd,Backshell for a 25-way Micro-D (example),backshell,Approved,30
```

A backshell counts when it is an accessory of kind backshell on the connector, with a part that has a depth ([enter the build data](enter-the-build-data.md#3-accessories)); a backshell without a part leaves the depth of that end unknown.

## 3. Generate and read the lengths

Generate again. With W002-P1 measured to its face (the project's setting), a plug part of 22 mm, a backshell of 30 mm on it, W002-P2 measured to its rear and one segment of 0.8 m, every wire of W002 is 0.8 − 0.052 = 0.748 m long (no service loop is set in the example). `explain DIR W002-001` shows how:

```
Wire W002-001. Length: 0.748 m
  Equation: L = sum of the routing segments between its connectors − depth of each face end + 2 × service loop
  Inputs:
    Segment W002-L1 = 0.8 m   [routing segment W002-L1 of harness W002]
    Depth of part EX-MICROD-25-M (W002-P1, measured to its face) = 22 mm   [part EX-MICROD-25-M: depth_mm]
    Depth of backshell part EX-BACKSHELL-25 (W002-P1, backshell W002-A1) = 30 mm   [part EX-BACKSHELL-25: depth_mm]
    Service loop = not set   [config/generation.json: service_loop_m is not set (0 used)]
  Steps:
    Path through the segments: 0.8 = 0.8 m
    Path from rear to rear: 0.8 − 0.052 = 0.748 m
    ...
```

A length you typed on a wire, or one locked against Generate, is kept as it is: the face end changes only the lengths the tool works out from the segments. A pin current, a check of a device or a place of a shield end does not change a length.

## What the checks say

- **A face end without a depth.** `check` warns, one line per connector, and the wires there have no length:

  ```
  WARNING length_depth_missing: W002-P1 is measured to its face, but part EX-MICROD-25-M has no depth (library: depth_mm), so the wires there have no length
  ```

  A click on the finding in the Problems list opens the Inspector of that cable connector, where *Lengths measured to* and its part are.
- **Segments shorter than the depths.** When the segments of a wire are not longer than the depths taken off, its length is not known either (`length_below_depth`).
- Both are warnings of `check`, so the design rule check lists them as `model-inconsistent`. No design rule is new: *Rules run* stays 43.

## What the written files show

- The length note of the build workbook (*Start here*, *Cut list*, *Production*, *Routing*) and of the harness plan gets a fifth sentence: *The segments run to the mating face of each connector (model.length_reference), but at W002-P2; the depth of the connector and its backshell is taken off each wire.* The headings *rear to rear* do not change: they stay true.
- A face end is marked in `segments.csv`, the *Segments* and *Routing* sheets (`W001-P1 (face)`), and the caption of the drawing says *lengths to the face*.
- `system/export.json` holds `length_to` on the cable connectors that have one and `depth_mm` on the parts, with the unit in `field_units`.
- A project without a face end keeps every file it had.

## Older versions of the tool

A 4.x tool opens a project of format 5 read-only. It sets aside every harness with a `length_to` and every part with a `depth_mm` as a damaged file (*Extra inputs are not permitted*), so its commands refuse the project. The step to format 5 writes no `length_to`: a team whose lengths were already to the face before 5.0.0 looks at its length note after the upgrade and sets the setting itself.

## Common mistakes

- **Expecting a default depth.** There is none: give each connector part, and each backshell on a face end, its depth.
- **A backshell without a part on a face end.** Its depth is not known, so the wires of that end have no length. Choose its part in the **Accessories** tab.
- **Measuring to the face twice.** A length that already left out the connectors is a length to the rear: leave the setting at *rear*.
- **Setting the face on a released harness.** Refused: start a new version first ([change a released harness](change-a-released-harness.md)).

Next: [wire length](../models/wire-length.md), [enter the build data](enter-the-build-data.md), [branching harnesses](branching-harnesses.md)
