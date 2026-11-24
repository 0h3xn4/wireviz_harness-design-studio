# Splices

This page shows how to join several wires inside a harness with a splice: a power line from one device to two others, for example. It says what a splice is, how to place one, what the checks say about it, and what the written files and the harness plan show.

> **New in 3.0.0** (format 3, milestone M6a, decision D-243, [`DESIGN_2.3_BRANCHING.md`](../ait/DESIGN_2.3_BRANCHING.md) section 6). What each written file holds for a splice is in [`OUTPUTS.md`](../OUTPUTS.md#a-splice).

## Contents

- [What a splice is](#what-a-splice-is)
- [Before you start](#before-you-start)
- [1. Bring in a splice part](#1-bring-in-a-splice-part)
- [2. Add a splice and splice a wire](#2-add-a-splice-and-splice-a-wire)
- [3. Delete a splice](#3-delete-a-splice)
- [What the checks say](#what-the-checks-say)
- [What the written files show](#what-the-written-files-show)
- [Read a splice: routing and explain](#read-a-splice-routing-and-explain)
- [Older versions of the tool](#older-versions-of-the-tool)
- [What is not in 3.0.0](#what-is-not-in-300)
- [Common mistakes](#common-mistakes)

## What a splice is

- A **splice** is a joint inside a harness. In the project it is a connector of the harness with the role `splice`, made of a library part of the category `splice`. It plugs into nothing.
- Each pin of a splice is a **node**. A node joins every wire that ends on it.
- A **net** is the set of pins that the wires of a harness join, through every splice on the way. The pins of a net that are not on a splice are its **ends**: the points a technician can probe.
- A splice is a node of the routing tree, like a connector: a segment can end at it, and its wires take their lengths from the segments ([branching harnesses](branching-harnesses.md#branch-points-and-segments)).
- Generate makes no splice. You place a splice in a harness you drew ([build a harness by hand](build-a-harness-by-hand.md)), never in one Generate made or one made from a connection: those own their pairs of pins. Since 5.0.0 a harness made from a connection gets its splices from the connection itself, one for each junction (one pin paired with several), of the splice part you choose at **Create harness** ([connect two connectors](connect-two-connectors.md#a-junction-one-pin-to-several-since-500)); the outputs below apply to it too.

## Before you start

- The project is in format 3 (3.0.0). A project of 2.x is upgraded once with `migrate` or the editor's question ([upgrade a project](upgrade-a-project.md), [versions](versions.md#the-letters-of-2x)).
- You have a harness you drew, with its plugs. The examples below use the practice project `wheel-link` (`harness-design-studio new wheel-link --template first-steps`) with a harness **Heater Y**, `W003`, drawn by hand from `PCDU1-J02` to `OBC1-J02` and `OBC1-J03`, each pin 1 with the signal `HTR`.
- The harness is not released. A released harness is locked: start a new version first ([change a released harness](change-a-released-harness.md)).

## 1. Bring in a splice part

The tool ships no splice part. The templates hold one example row, `splice-parts-EXAMPLE.csv` (`harness-design-studio templates FOLDER` copies it). It is not a real part: replace it with the part your project uses. The pin count of a splice part is its number of nodes.

```
harness-design-studio templates tpl
harness-design-studio import-parts wheel-link tpl/splice-parts-EXAMPLE.csv --pending Review
```

```
row 2: OK added EX-SPLICE-1
1 part(s) ready, 0 row(s) with problems.
```

The library saves splice parts in `library/splice.json`, a file that is there only while the library holds one.

## 2. Add a splice and splice a wire

In the app (GUI, not run here):

1. Open the **Harness** tab (Drawings on the rail, Ctrl+2) and choose `W003`. Under the **Routing** table, the **Splices** list shows one row per node of each splice: the splice, the node, the part, how its wires are joined (**Joined by**: crimp, solder, or empty while not said) and the wires on it.
2. Choose the part under **Splice part** and press **Add splice**. The splice gets the next free ID, `W003-X1`, with one node, node 1.
3. Draw the wire from `W003-P1` pin 1 to `W003-P2` pin 1 in the **Edit wire** tab, as for any wire. Choose it in the wire table, choose node 1 of `W003-X1` in the **Splices** list and press **Splice this wire**. The wire is cut in two at the node: `W003-001` now ends on the node, and the new wire `W003-002` runs on from it to where the wire ended, with the same signal, gauge, part and colour. A wire with a length of its own is refused: clear the length first, so that each piece takes the length of its path.
4. Draw a wire from the node to `W003-P3` pin 1 (**New wire** in **Edit wire**, with `W003-X1` and node 1 as one end). A node can have as many wires as you need.

Each step is one undo step and goes into the change journal. How a node is joined (crimp or solder) is set like the termination of a pin, in the **Connectors** tab.

## 3. Delete a splice

Choose a node of the splice in the **Splices** list and press **Delete splice**. A node with two wires joins them back into one wire. A splice that a segment or an accessory names is refused until you delete or move them; the message names them.

## What the checks say

`validate`, `check` and the editor give these, by the integrity check of the project (the warnings show in the **Problems** panel under the design rule *Model consistency*, `model-inconsistent`):

| Code | Kind | When |
| --- | --- | --- |
| `splice_unused` | warning | a node has no wire |
| `splice_one_wire` | warning | a node has one wire, so it joins nothing |
| `splice_signals_mixed` | warning | a node joins wires of different signals |
| `splice_stub` | warning | the harness file holds an entry of the old list `splices`, which no tool reads; it is kept as it is |
| `splice_mated` | error | a splice says it mates with a connector; a splice plugs into nothing |
| `splice_in_generated_harness` | error | a splice is in a harness Generate makes, which Generate would replace |

The design rule *Several wires on one pin* (`pin-shared`) leaves the nodes out: a splice joins its wires there by design. The independent check of the harnesses counts a connection of an interface per pair of ends of a net.

## What the written files show

A splice changes the files of its own harness only. Every harness without a splice keeps its files byte for byte.

- **Tests** (`tests.csv` and the *Tests* sheets): one continuity test per pair of ends of a net through a splice, and one isolation test per net, in place of the tests of its wires:

  ```
  T001,continuity,W003-P1.1,W003-P2.1 via W003-X1,continuous,TBD (placeholder),,W003-001;W003-002
  T002,continuity,W003-P1.1,W003-P3.1 via W003-X1,continuous,TBD (placeholder),,W003-001;W003-003
  T003,continuity,W003-P2.1,W003-P3.1 via W003-X1,continuous,TBD (placeholder),,W003-002;W003-003
  T004,isolation,W003-P1.1 + W003-P2.1 + W003-P3.1,all other nets and shields,isolated,TBD (placeholder),TBD (placeholder),W003-001;W003-002;W003-003
  ```

- **Wire list:** a last column *Via*, the splices of the wire's net.
- **Pinouts, labels, BOM, mass:** a splice is listed like a connector of role `splice` in the pinouts; it has no label; its part is a line of the BOM; its mass counts only under the mass model `full_bom`.
- **Build workbook:** the *Connectors* sheet has a block per splice under the heading *Splices: each node joins the wires listed on it*, a row per node with its wires, where each goes and how it is joined.
- **Drawing** (with `--drawings`): a splice is a small bar with a dot per node, not a connector table.
- **Harness plan** (with `--harness-plan`, [export the harness plans](export-the-harness-plans.md#a-harness-with-splices)): the two ends of the plan are found through the splices, a row lists every far pin its wire reaches through a splice, and the wires beyond a splice are under *Further wires*.

`verify --outputs` works the nets out with its own code and checks each of these.

## Read a splice: routing and explain

`harness-design-studio routing wheel-link W003` lists the splices of a harness with the wires on each node (`--json`: the key `splices`):

```
Splices (nodes of the routing tree; the wires each node joins):
  W003-X1 (EX-SPLICE-1)
    node 1, crimp: W003-001, W003-002, W003-003
```

`harness-design-studio explain wheel-link W003-X1` shows the nets of a splice:

```
Splice W003-X1 of harness W003. The nets of the splice: node 1: W003-P1.1, W003-P2.1, W003-P3.1
```

## Older versions of the tool

A splice is saved in format 3. Versions 2.x open a format 3 project read-only and change nothing, so the whole team upgrades together ([versions](versions.md)).

## What is not in 3.0.0

- **Generate makes no splice.** Draw the harness by hand.
- **No command-line versions of the edits.** A splice is placed, used and deleted in the app; the command line reads it (`routing`, `explain`, the checks, the outputs).
- **The Inspector** shows a splice as a connector.
- **A kind of branch point and backshells** as their own objects ([branching harnesses](branching-harnesses.md#what-is-not-in-230)).

## Common mistakes

- **Add splice is off, and the list says the library has no splice part.** Import one with the category `splice` (step 1).
- **"W001 is made by Generate, which makes no splice."** Draw a harness of your own for the joint ([build a harness by hand](build-a-harness-by-hand.md)).
- **"W003-001 has a length of its own".** Clear the length of the wire, then splice it: each piece takes the length of its path.
- **`splice_signals_mixed`.** Two signals meet at one node. Check the wires; a node joins one signal.

Next: [branching harnesses](branching-harnesses.md), [export the harness plans](export-the-harness-plans.md), [export the outputs](export-the-outputs.md)
