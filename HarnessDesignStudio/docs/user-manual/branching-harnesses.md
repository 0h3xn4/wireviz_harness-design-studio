# Branching harnesses

This page shows how to make a harness that **branches**: one cable assembly with more than two connectors, where the wires leave the main bundle at a branch point. Generate can make one for you, and you can draw one by hand. The page also says how the lengths are measured, what the written files show, and what an older version of the tool does with such a project.

> **New in 2.3.0 (not released yet).** Branching harnesses are decision D-243 ([the design](../ait/DESIGN_2.3_BRANCHING.md)). The command lines were run, and their output is real; the [worked example](#a-worked-example-on-the-command-line) is the end-to-end test of 2.3.0 (`tests/test_e2e_branching.py`). The steps in the app are described from the program's code and its tests; nobody has watched them on a real screen yet (GUI, not run). The file format does not change.

## Contents

- [When a harness branches](#when-a-harness-branches)
- [Branch points and segments](#branch-points-and-segments)
- [How lengths are measured](#how-lengths-are-measured)
- [1. Let Generate make the harness](#1-let-generate-make-the-harness)
- [A worked example on the command line](#a-worked-example-on-the-command-line)
- [2. Enter the lengths](#2-enter-the-lengths)
- [3. Draw the tree of a harness by hand](#3-draw-the-tree-of-a-harness-by-hand)
- [4. Add a leg](#4-add-a-leg)
- [5. Join two harnesses into one](#5-join-two-harnesses-into-one)
- [Move a branch point on the diagram](#move-a-branch-point-on-the-diagram)
- [Shields across a branch](#shields-across-a-branch)
- [The warnings](#the-warnings)
- [What the written files show](#what-the-written-files-show)
- [Read the tree: routing and explain](#read-the-tree-routing-and-explain)
- [Older versions of the tool](#older-versions-of-the-tool)
- [What is not in 2.3.0](#what-is-not-in-230)
- [Common mistakes](#common-mistakes)

## When a harness branches

- One device connector talks to several far devices. A real connector takes one plug, so the wires to all of them start in one plug and split on the way. Before 2.3.0 Generate made one harness per far connector, each with its own plug on the shared connector, and warned `box_connector_shared`.
- Two devices on one side talk to two devices on the other side, and the wires run together for most of the way: one harness *DEV2 + DEV3 to DEV1 + DEV4*, with two connectors at each end.
- You draw a cable and want a second cable from the same plug to another device.

## Branch points and segments

A harness that branches has a **routing tree**, kept in its harness file since format 1:

- A **branch point** is the place where wires leave the main bundle. It has an ID such as `W001-B1` and a name such as *Branch X*.
- A **segment** is the bundle between two nodes. A node is a connector of the harness or a branch point. A segment has an ID such as `W001-L3` and a length.
- The segments form a **tree**: there is one path between any two connectors. A loop would give a wire two paths and two lengths; the editor refuses to close one, and the design rule `segment-loop` reports one in a file you edited.
- The trunk is the segment between the two branch points of a harness with two ends.

A wire still runs from pin to pin, from one connector to another. No wire ends at a branch point. A wire runs along the path of segments between its two connectors.

## How lengths are measured

The owner's answer B4 of the design:

- A segment is measured from the **rear of a connector** (where the wires leave the connector body or its backshell) to the **centre of a branch point**, and between the **centres of two branch points**.
- The length of a wire is its own length when it has one. Else it is the sum of the segments on its path.
- Generate adds a service loop at each end of a wire it makes (the setting `service_loop_m`, assumption `A-SERVICE-LOOP`). A wire of a harness you drew gets no loops; set its length yourself if it needs them.
- Nothing reads the depth of a connector.

In the worked example below, the wire from DEV1 to DEV2 runs along three segments: 0.3 m from DEV1-J01 to *Branch X*, 1.5 m of trunk, and 0.25 m from *Branch Y* to DEV2-J01, so it is 2.05 m long.

## 1. Let Generate make the harness

The choice `per_connector_group` of `segmentation.mode` joins the harnesses that plug into one device connector into one harness that branches: one plug on each device connector, a branch point on an end with more than one connector, the trunk, and a segment to each plug ([how links become harnesses](generate-harnesses.md#how-links-become-harnesses)). **Since 2.4.0 a new project starts with it** (decision D-247): `new FOLDER`, **File > New project** with the empty project, and `create_project` of the scripting interface. For example a 21-pin Micro-D on one device that carries RS-422, RS-485 and CAN to three devices, each with its own connector, gets one harness with one plug on the Micro-D, one branch point and four segments.

A project made before 2.4.0 keeps `per_connector_pair`, one harness for each pair of device connectors, and so do the examples `first-steps`, `minimal-satellite` and `small-satellite`; nothing switches a project's mode by itself. In such a project a device connector with links to several far connectors gets one plug for each harness. After **Generate** the editor then says so once: *OBC-J01 has the plugs of several harnesses (W001, W002 and W003), and a connector takes one plug.* The button **Make one harness that branches** chooses `per_connector_group` (one undo step) and offers **Generate again**. Close the notice to keep `per_connector_pair`; the editor remembers the answer for the project on this computer, not in the project's files.

**In the app:** open **Settings > Project**, find **How interfaces are grouped into harnesses** and choose **Per connector group**. The sentence under it says what the choice does. It is one undo step and takes effect at the next **Generate**.

**On the command line:**

```
harness-design-studio settings DIR --set segmentation.mode="per_connector_group"
harness-design-studio generate DIR
```

What Generate then does:

- It finds the two ends by a walk from the first connector in ID order. The first connector is end X; the connectors it is wired to are end Y; and so on. The harness is named after its ends: *DEV1-J01 + DEV4-J01 to DEV2-J01 + DEV3-J01*. An end with more than one connector gets a branch point, *Branch X* or *Branch Y*.
- **Your drafts are taken over.** The harness with the lowest ID keeps its ID and its plug numbers; the other drafts of the group are removed. Locked wires, labels, notes, strip lengths and the cable connectors you edited carry over. What cannot carry over is named in a warning (`locked_data_lost`).
- **A ring is not joined.** Three connectors wired to each other in a ring cannot be the two ends of one trunk. Their harnesses stay separate, and Generate warns `branch_not_built` with the connectors that close the ring. Draw that harness by hand.
- **The nominal and the redundant chain are never joined**, and neither is a **released harness**: a new interface on the connector of a released harness keeps the warning `box_connector_shared`.
- **A project with no shared connector** gets the same harnesses in both modes.

`explain DIR W001` says why the interfaces share the harness, with its ends ([read the tree](#read-the-tree-routing-and-explain)). The setting and the assumption `A-SEGMENT-MODE` describe the mode, and [the model page of the segmentation](../models/segmentation.md#one-harness-that-branches) shows how the groups are joined.

When a device connector still has plugs of several harnesses that Generate made, the **Problems** panel offers **Use per_connector_group** on the warning. It opens Settings at the choice.

## A worked example on the command line

The users' harness *DEV2 + DEV3 to DEV1 + DEV4*: four devices, one connector each, with two RS-422 ports. DEV2 and DEV3 each talk to DEV1 and to DEV4.

1. Make a blank project and import the four pinouts. The file `dev.csv` holds one connector J1 with the ports RS422_1 on pins 1-4 and RS422_2 on pins 5-8 ([a connector with several ports](define-a-device.md#a-connector-with-several-ports-since-210)). A new project starts in `per_connector_group`; to see what a project made before 2.4.0 does, this example first sets `per_connector_pair`:

   ```
   harness-design-studio new branching --template blank
   harness-design-studio settings branching --set segmentation.mode="per_connector_pair"
   harness-design-studio import-pinout branching dev.csv --device DEV1 --new-device "Device 1" --subsystem avionics --default-part EX-MICROD-25-F --gender female
   ```

   Do the same for DEV2, DEV3 and DEV4. Then connect DEV2 to DEV1, DEV2 to DEV4, DEV3 to DEV1 and DEV3 to DEV4 with RS-422 in the editor (Guided mode chooses the connector and the port of each).

2. Generate in `per_connector_pair`. Every connector gets two plugs, and Generate warns four times:

   ```
   $ harness-design-studio generate branching
   warning: [box_connector_shared] DEV1-J01 has more than one cable plug on it: W001-P1 (W001), W002-P1 (W002). A connector takes one plug. For one harness with one plug on it, put the far devices in one zone and set segmentation.mode to per_zone_pair, use different connectors, or set segmentation.mode to per_connector_group for one harness that branches.
   ...
   4 added, 0 changed, 0 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
   4 interfaces and 16 wires checked: 0 error(s)
   ```

3. Choose the mode and generate again. W001 takes over the other three drafts:

   ```
   $ harness-design-studio settings branching --set segmentation.mode="per_connector_group"
   1 value(s) set.
   $ harness-design-studio generate branching
   0 added, 1 changed, 0 unchanged, 3 removed, 0 frozen (released); 0 locked pin(s) kept
   4 interfaces and 16 wires checked: 0 error(s)
   ```

4. Look at the tree. Each segment lists the wires that run through it:

   ```
   $ harness-design-studio routing branching W001
   Harness W001: DEV1-J01 + DEV4-J01 to DEV2-J01 + DEV3-J01
   It branches at 2 branch points and has 5 segments.

   Segments (from, to, length, where the length came from; the wires through it):
     W001-L1: W001-B1 (Branch X) to W001-B2 (Branch Y), no length, not set
       16 wires: W001-001, W001-002, W001-003, W001-004, W001-005, W001-006, W001-007, W001-008, W001-009, W001-010, W001-011, W001-012, W001-013, W001-014, W001-015, W001-016
     W001-L2: W001-P1 (DEV1-J01) to W001-B1 (Branch X), no length, not set
       8 wires: W001-001, W001-002, W001-003, W001-004, W001-009, W001-010, W001-011, W001-012
     W001-L3: W001-P3 (DEV4-J01) to W001-B1 (Branch X), no length, not set
       8 wires: W001-005, W001-006, W001-007, W001-008, W001-013, W001-014, W001-015, W001-016
     W001-L4: W001-P2 (DEV2-J01) to W001-B2 (Branch Y), no length, not set
       8 wires: W001-001, W001-002, W001-003, W001-004, W001-005, W001-006, W001-007, W001-008
     W001-L5: W001-P4 (DEV3-J01) to W001-B2 (Branch Y), no length, not set
       8 wires: W001-009, W001-010, W001-011, W001-012, W001-013, W001-014, W001-015, W001-016

   Branch points (the connectors beyond it, by segment):
     W001-B1 (Branch X)
       W001-L1: W001-P2, W001-P4
       W001-L2: W001-P1
       W001-L3: W001-P3
     W001-B2 (Branch Y)
       W001-L1: W001-P1, W001-P3
       W001-L4: W001-P2
       W001-L5: W001-P4

   Segments without a length: W001-L1, W001-L2, W001-L3, W001-L4, W001-L5.
   ```

5. Import the lengths you measured on the mock-up, in millimetres, and generate again so that the wires take them:

   ```
   $ cat lengths.csv
   harness,segment,length
   W001,W001-L1,1500
   W001,W001-L2,300
   W001,W001-L3,450
   W001,W001-L4,250
   W001,W001-L5,350
   $ harness-design-studio import-lengths branching lengths.csv --unit mm
   ...
   row 2: OK W001 / W001-L1: 1500 mm = 1.5 m
   ...
   5 length(s) ready, 0 row(s) with problems.
   $ harness-design-studio generate branching
   0 added, 1 changed, 0 unchanged, 0 removed, 0 frozen (released); 0 locked pin(s) kept
   ```

6. Export and check the files:

   ```
   $ harness-design-studio export branching
   27 files written to branching/outputs (model <hash>).
   $ harness-design-studio verify branching --outputs
   4 interfaces and 16 wires checked: 0 error(s)
   ```

   `branching/outputs/harnesses/W001/segments.csv` holds the tree (after the two lines of the stamp):

   ```
   Segment,From,To,Length (m),Number of wires,Wires
   W001-L1,W001-B1,W001-B2,1.5,16,W001-001;W001-002;W001-003;W001-004;W001-005;W001-006;W001-007;W001-008;W001-009;W001-010;W001-011;W001-012;W001-013;W001-014;W001-015;W001-016
   W001-L2,W001-P1,W001-B1,0.3,8,W001-001;W001-002;W001-003;W001-004;W001-009;W001-010;W001-011;W001-012
   W001-L3,W001-P3,W001-B1,0.45,8,W001-005;W001-006;W001-007;W001-008;W001-013;W001-014;W001-015;W001-016
   W001-L4,W001-P2,W001-B2,0.25,8,W001-001;W001-002;W001-003;W001-004;W001-005;W001-006;W001-007;W001-008
   W001-L5,W001-P4,W001-B2,0.35,8,W001-009;W001-010;W001-011;W001-012;W001-013;W001-014;W001-015;W001-016
   ```

A second Generate changes no file, and a second export writes the same bytes. The plug numbers come from the draft that was kept (W001 had W001-P1 on DEV1-J01 and W001-P2 on DEV2-J01); in a project that chose the mode before its first Generate, the plugs are numbered in the order of the ends.

## 2. Enter the lengths

A segment length can come in three ways:

- **Import a table** of harness, segment and length: **File > Import > Import segment lengths…**, or `import-lengths` ([import data](import-data.md#segment-lengths)). Generate again afterwards.
- **Type it in the Routing table.** In the **Drawings** area, open the **Harness** tab of the harness. Under the wire table is **Routing**: one row per segment (segment, from, to, length, the wires through it) and one row per branch point (its name, its segments and their lengths). Double-click a length, type it in metres and press Enter. Each length is one undo step. An empty cell clears it. A segment without a length reads *to fill in*.
- **Edit the harness file** by hand (`length_m` of the segment).

On a harness that Generate made, the Routing table says that Generate keeps a length you enter: the next Generate keeps it by the two ends of its segment, as it keeps an imported one. A length whose segment is gone after a change of the design is named in a warning. A released harness locks its segments: its lengths cannot be changed until a new revision.

`routing` and `explain` say where each length came from: *imported from lengths.csv, row 2*, *entered*, or *not set*, and *kept by Generate* on a harness that Generate made. The source is worked out, not stored: a length that the import record lists with the same value counts as imported.

## 3. Draw the tree of a harness by hand

A harness you made yourself ([build a harness by hand](build-a-harness-by-hand.md), or a cable you drew on the diagram) gets its tree in the **Routing** table of its **Harness** tab:

- **Add branch point** adds one with the next free ID (`W001-B1`) and the name *Branch 1*.
- **Add segment…** opens a window: choose the two nodes (**From** and **To**, a connector or a branch point of this harness) and, if you know it, the **Length (m)**. A segment that would close a loop is refused, and the window says why.
- **Rename…** gives the chosen branch point another name. Two branch points of one harness cannot have the same name.
- **Delete** deletes the chosen segment, or the chosen branch point with its segments. A branch point that is on the only path of a wire is refused, and the wires are named.

Each is one undo step. These buttons are hidden on a harness that Generate made: Generate makes its tree again each time, so only its lengths are yours. A click on a branch point in the table shows it in the **Inspector**: its harness, its segments and their lengths.

## 4. Add a leg

A **leg** is a new branch from a plug that your harness already has.

**On the diagram:** press on a port that a harness you drew plugs into, and drag a cable onto empty ground. Before 2.3.0 that port refused a second cable. Now the cable becomes a **new leg of that harness**: a new loose end, with one wire from each pin of the plug that has a signal and no wire yet. When a leg already left the plug, a branch point is added next to it: the old leg moves onto the branch point and keeps its length, and the new leg runs from the branch point to the loose end. Then plug the loose end into a port, or give it a connector part, as for any [loose end](build-a-harness-by-hand.md#a-cable-with-a-loose-end).

It is one undo step. The message says *A new leg of W001: the loose end W001-P3 from DEV2-J01. Choose its part, or plug it in.*

What is refused, with the reason:

- A plug with no free pin with a signal: *W001-P1 has no free pin with a signal for a new leg. Choose the pins.*
- A pin that has a wire already. Two wires on one pin need a splice, which comes with format 3 ([what is not in 2.3.0](#what-is-not-in-230)).
- A harness made from a connection, or one that Generate made: its pairs belong to the connection or to Generate. Such a port keeps the refusal of 1.17. So does a port with plugs of several harnesses.

## 5. Join two harnesses into one

Two harnesses you drew that plug into the same device connector give that connector two plugs, and the warning `box_connector_mated_twice`. Join them:

- In the **Problems** panel, the warning offers **Join into one harness**. The row menu of the bottom Problems list offers the same.
- On the diagram in Expert mode, right-click the device connector, or a plug on it, and choose **Join into one harness…**. The window asks which other harness joins the one you clicked.

From the Problems panel the harness with the lowest ID keeps its ID; from the diagram the harness you clicked keeps it. The two plugs on the shared connector become one: the wires of the other plug move onto it pin by pin. Every other connector, wire, shield group, branch point, segment and accessory of the other harness moves over under its ID. A branch point next to the plug joins the legs. The other harness is deleted, and its notes are added to the kept one's. It is one undo step and one line of the change journal.

The join is refused, with the reason, when: both harnesses wire the same pin of the shared connector; the two plugs have different parts (give them the same part first); the harnesses share no device connector, or more than one (that would close a loop); one of them was made by Generate or from a connection, or is released; or the harness that would be deleted has a release history.

## Move a branch point on the diagram

On the diagram a harness you drew is drawn from its first plug, through each branch point, to its other ends. A branch point is a small diamond with its name, at the middle of the connectors it joins. Drag it to put it elsewhere; the lines of its harness follow. The tooltip says that a move changes no written file.

The place is the mark `branch:<branch point ID>` in `diagram/marks.json` ([file format](../FILE_FORMAT.md#branching-harnesses-230-format-2-unchanged)). Like every mark it is outside the model hash, so a move never makes the outputs out of date. The mark goes when its branch point is deleted, and `merge-fix` renames it with its harness ([use Git and CI](use-git-and-ci.md)).

## Shields across a branch

A shield group (a twisted pair, a shielded pair, an overall shield) has two ends, A and B. It runs between **two connectors**. The owner's answer B5 of the design:

- A group whose wires all run between the same two connectors keeps that meaning through branch points: the shield runs the whole path.
- A group whose wires end on **different far connectors** would have more than two ends. **Group** in the **Edit wire** tab refuses it: *W001-001 and W001-005 end on different connectors (DEV1-J01, DEV4-J01); a shield group runs between two connectors.*
- Such a group in a file you edited by hand is the warning `shield_across_branch`.
- A shield or cable jacket that ends at a branch point needs a list of the segments it covers. That is a field, so it waits for a later format.

Generate makes only groups of one interface, which has two ends.

## The warnings

Three integrity warnings look at the tree. They are warnings, not errors: the project opens and every edit works. The design rule `model-inconsistent` reports them, as it reports the plug warnings, so they show in the **Problems** panel and in `drc`.

| Warning | What it means | What to do |
| --- | --- | --- |
| `segment_tree_split` | A harness with branch points has segments that do not reach every connector. The wires to an unreached connector have no length. | Add the missing segment. |
| `branch_point_unused` | A branch point has fewer than two segments. | Join it to the tree, or delete it. |
| `shield_across_branch` | A shield group's wires end on different connectors. | Split the group, one per far connector. |

`box_connector_mated_twice` and `box_pin_wired_twice` stay as they were: they go quiet when the plugs are joined. No design rule is new; there are still 39.

## What the written files show

Only a harness with at least one branch point gets new files and sheets. A straight harness keeps its files byte for byte. The full list is in [Outputs](../OUTPUTS.md#a-harness-that-branches).

- **`harnesses/<ID>/segments.csv`**: one row per segment: segment, from, to, length in metres (empty when not set), the number of wires and the wires.
- **The sheet *Segments*** of `<ID>.xlsx`, the last sheet: the same rows.
- **The sheet *Routing*** of the build workbook `<ID>_build.xlsx`, after *Cut list*: one row per segment, with the length or *to fill in* on an amber cell, then one row per branch point with the connectors beyond it on each segment. **Start here** lists the sheet. A segment without a length already shows there as *Wires without a length*.
- **The drawing** (with `--drawings`) is unchanged: it draws a routing sketch of the tree up to 14 nodes and lists the segments with their lengths.
- The wire list, pinouts, labels, bill of materials, mass and tests are unchanged. Without a splice every wire runs pin to pin, so one continuity test and one isolation test per wire stay right.

`verify --outputs` works the rows out from the project on its own and reports `out_routing` when a cell differs, a sheet is missing for a harness with a branch point, or a sheet or `segments.csv` is there for a harness without one. The packaged example `flatsat` has six harnesses with branch points, so its export writes six `segments.csv` files more than with 2.2.0.

## Read the tree: routing and explain

- `harness-design-studio routing DIR HARNESS` prints the tree (see [the worked example](#a-worked-example-on-the-command-line)). It changes nothing. `--json` gives the same as a document: each segment with `id`, `from`, `to`, `length_m`, `source`, `kept_by_generate`, `source_text` and `wires`, then the branch points and their sides, the segments without a length and the wires with no single path ([CLI](../CLI.md)). A harness with no branch point prints its segments and says that it does not branch.
- `harness-design-studio explain DIR W001-L1` explains a segment: its two nodes, its length and where it came from, and the wires through it.
- `harness-design-studio explain DIR W001-B2` explains a branch point: for each of its segments, the connectors beyond it.
- `harness-design-studio explain DIR W001-001` shows the path of a wire: *Path through the segments: 0.3 + 1.5 + 0.25 = 2.05 m*.
- `harness-design-studio explain DIR W001` says why the interfaces share the harness: *IF-001, IF-002, IF-003 and IF-004 share a harness because they plug into DEV1-J01, DEV2-J01, DEV3-J01 and DEV4-J01; mode per_connector_group; ends X: DEV1-J01, DEV4-J01, Y: DEV2-J01, DEV3-J01*.

The model page [wire length](../models/wire-length.md#segments-and-branch-points) has the equations.

## Older versions of the tool

A project with branches is still format 2. Versions 2.2.x, 2.1.x and 2.0.x open it and can save it. What they do:

| What the project holds | What an older version does |
| --- | --- |
| Nothing new | Nothing different. |
| `segmentation.mode` = `per_connector_group` | Its Generate says the mode is *not known; using per_connector_pair* and makes the pairs again: the joined draft is removed, the pairs come back under new numbers, and what you set on the draft is reported as lost. A released harness that branches stays as it is. |
| A drawn harness with branch points, segments, a leg or a join | Read and kept, with the same wire lengths. Its outputs have no *Routing* or *Segments* sheet and no `segments.csv`, and its editor cannot change the tree. |
| `branch:` marks | Kept as marks of a kind it does not know. It never drops them, and its `merge-fix` does not rename them. |
| A length you entered on a generated harness | Kept by its Generate. |

**Update the whole team together** before anyone chooses `per_connector_group`, and before anyone makes a new project with 2.4.0 or later, which starts in it. After you upgrade from 2.2, nothing changes on open or on Generate: existing harnesses with two plugs on one connector stay as they are until you choose the mode or join them.

## What is not in 2.3.0

- **Splices.** A splice joins several wires inside a harness (a signal to two far pins). It needs a new role of a connector, which is a format change, so splices came with format 3 (3.0.0): the **Splices** list of the Harness tab places them in a harness you drew (see the user guide, *Branching harnesses*). A splice is a node of the routing tree like a connector. In 2.x a joint can only be drawn as an inline connector with several wires on one pin; the design rule `pin-shared` reports it, and the test tables of 2.x are not right for such a joint.
- **A kind of branch point** (a breakout, a boot, a transition) and **backshells** as their own rule. A boot or a transition at a branch point is an accessory of the harness, with its place in words (*at W001-B1*).
- **A shield or a jacket that ends at a branch point** ([shields across a branch](#shields-across-a-branch)).
- **Joining in `per_unit_pair` and `per_zone_pair`.** Those modes keep their warning when interfaces of one connector fall into two groups.
- **Labels for the legs** (*to STR2-J01* at the branch).
- **Command-line versions of the edits.** The tree, the legs and the join are edited in the app.

## Common mistakes

- **The Routing table has no buttons.** The harness was made by Generate. Only its lengths are yours; choose `per_connector_group` or change the design to change its tree.
- **A wire has no length.** A segment on its path has no length, or the tree does not reach its connector (`segment_tree_split`). `routing` lists the segments without a length.
- **A dragged cable does not become a leg.** The port has plugs of several harnesses, or of a harness that Generate made or that a connection made. Join them first, or draw a new harness.
- **The lengths you imported are gone after a change of the mode.** A change of the mode builds the drafts again; a length whose two ends changed cannot be kept, and Generate names it. Import the lengths again after the first Generate in the new mode.
- **A colleague's Generate split the harness again.** Their version is older than 2.3.0 ([older versions](#older-versions-of-the-tool)).

Next: [generate harnesses](generate-harnesses.md), [build a harness by hand](build-a-harness-by-hand.md), [export the outputs](export-the-outputs.md)
