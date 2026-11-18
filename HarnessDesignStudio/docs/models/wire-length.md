# Wire length: where the length of a wire comes from

This page explains the length the tool gives a wire: the number in the wire list, the cut list, the mass and the voltage drop. It is written from what the program does, and the numbers in the example come from the `flatsat` example, where you can repeat them.

## Contents

- [What the tool decides](#what-the-tool-decides)
- [The equation](#the-equation)
- [The inputs and where they come from](#the-inputs-and-where-they-come-from)
- [The assumptions it rests on](#the-assumptions-it-rests-on)
- [A worked example](#a-worked-example)
- [Three ways a length can be there](#three-ways-a-length-can-be-there)
- [Segments and branch points](#segments-and-branch-points)
- [What happens when a value is missing](#what-happens-when-a-value-is-missing)
- [What the model does not do](#what-the-model-does-not-do)

## What the tool decides

When **Generate** builds a harness, it lays routing segments between the connectors and gives every wire the length of the path through those segments between its two connectors, plus a service loop at each end. Everything that needs a length asks one function (`wire_length`): the wire list, the cut list, the mass, the voltage drop, the design rules and the release gate. Nothing else makes up a length. `explain DIR WIRE` shows it as the derivation of kind `wire-length`.

## The equation

`L = sum of the routing segments between its connectors + 2 × service loop`

This is the default, the length model `path_plus_loops`. The number of loops (2) and the model are settings of `config/model.json` (`service_loops_per_wire`, `length_model`: the model `path_loops_allowance_twist` adds a cut allowance and the take-up of twisting); see [selectable models](selectable-models.md#length-model). With the defaults a project gives the lengths of this page.

The path is the one path through the tree of segments from the connector at one end of the wire to the connector at the other.

## The inputs and where they come from

| Input | Unit | Source |
| --- | --- | --- |
| Length of each segment on the path | m | The segment of the harness: generated from the zones and chain, or entered or imported by you (**Import lengths**, or the segment table). The segment has no field for the source of its length; `routing` and `explain` of a segment work it out (see [Segments and branch points](#segments-and-branch-points)). |
| Service loop | m | `config/generation.json`: `service_loop_m`. When it is not set, nothing is added and generation says so in a note. |
| Length stored on the wire | m | Only when a length was typed on the wire (**Edit wire**), imported, or kept from an earlier generation. |

## The assumptions it rests on

- **A-PATH-UNIQUE.** The length is the one path through the segments. If the segments form a loop there is no single length, the length stays undecided and the design rule `segment-loop` reports it. Bend radii, tolerances and the part of a connector inside its backshell are not added. Stays built in: whether a path is unique is a property of the drawn segments and not a choice; an allowance you want is the cut allowance of the length model.
- **A-SERVICE-LOOP.** A generated wire is longer than its path by two service loops, one at each end, the same for every wire. The length of a loop is the setting `service_loop_m` and the number of loops the setting `service_loops_per_wire` (2 by default).

## A worked example

`harness-design-studio explain DIR W001-001` on the `flatsat` example prints, for the length:

- **Length: 3.45 m.** The path between the two connectors uses three segments: `W001-L3` 1.5 m, `W001-L1` 0.5 m and `W001-L12` 1.25 m, which sum to 3.25 m. The service loop of the configuration is 0.1 m, so the two loops add 0.2 m, and the generated length is 3.25 + 0.2 = 3.45 m. This is the length stored on the wire and the one the tables, the mass and the voltage drop use.

In the program, select the wire and open **Show the calculation** in the **Why** tab for the same text.

## Three ways a length can be there

The derivation says which one applies, so a number in the cut list is never of unknown origin:

1. **Generated.** The length stored on the wire equals the path through the segments plus two service loops. The derivation lists each segment and both loops.
2. **Entered by hand and locked.** A length typed on the wire with **Edit wire** locks the wire, and generation keeps it. The derivation shows it as *Length stored on the wire*. The segments are no longer used for this wire.
3. **Stored on the wire, origin not recorded.** A length that does not equal the path plus two service loops and is not locked: it was imported, or the segments or the service loop changed since generation. Generate again, or lock the length on purpose, to make the origin clear.

A wire with no length of its own is measured from the segments alone, without service loops, until Generate gives it one.

## Segments and branch points

A segment is the bundle between two nodes: a cable connector or a branch point. Its length is measured from the rear of a connector (where the wires leave the connector body or its backshell) to the centre of a branch point, and between the centres of two branch points. `harness-design-studio routing DIR HARNESS` prints the tree of one harness: every segment with its two nodes, its length, where the length came from and the wires through it, then every branch point with the connectors beyond it on each segment that meets it. These are the rows of `segments.csv` and of the sheet *Routing* that `export` writes for a harness with a branch point. `explain DIR SEGMENT` gives the derivation of kind `segment`, and `explain DIR BRANCH-POINT` the derivation of kind `branch-point`; both are computed when asked and are not in `explain --all`.

Where a segment length came from is worked out, because a segment has no field for it (format 2 does not change):

- **Not set.** The segment has no length. The wires through it have no length from the segments.
- **Imported.** An import record of kind `lengths` (`imports/records.json`, written by `import-lengths`) lists the segment with the same value; the file and the row are named.
- **Entered.** Any other length: typed in the editor, or written in the file. When the same length was typed after an import, it is shown as imported.

On a harness Generate made, Generate keeps an entered or imported length by the two nodes of its segment, so the length is also *kept by Generate*. The wires through a segment are those whose one path between their connectors takes it (A-PATH-UNIQUE); a wire without a single path runs through none and is listed apart.

On the `flatsat` example, `harness-design-studio explain DIR W005-L3` prints *Segment W005-L3 of harness W005. Length: 1 m*, from `W005-P2 (PCDU1-J01)` to `W005-B1 (Branch X)`, *entered, kept by Generate*, and the two wires `W005-001` and `W005-002`. `explain DIR W005-B1` prints the four segments that meet *Branch X* and the connectors beyond each: `W005-P4`, `W005-P5` and `W005-P6` beyond `W005-L1`, and one connector beyond each of `W005-L2`, `W005-L3` and `W005-L4`.

### Splices (format 3)

A splice is a node of the routing tree like a connector: a segment may end at it, and a wire from a plug to a splice is measured along the segments between them like any other wire. Each pin of a splice is a node that joins every wire on it into one net (a net is the set of pins its wires join). `routing DIR HARNESS` lists the splices of a harness with the wires on each node, and `explain DIR SPLICE` gives the derivation of kind `splice`: its part and, for each node, the ends of its net (the pins not on a splice). Like a segment, it is computed when asked and is not in `explain --all`.

## What happens when a value is missing

A length is never made up. The derivation names what is missing: that the harness has no routing segments, that the segments do not give one path between the connectors (a loop, see `segment-loop`), or which segments have no length. Mass, the cut list and the voltage drop then say the same, because they use the same function.

## What the model does not do

- It does not add a bend radius, a tolerance, the length inside a connector or backshell, or a strip length; a cut allowance and the take-up of twisting only with the length model `path_loops_allowance_twist` (both 0 by default). Strip lengths are typed, per end, on the wire.
- It does not measure the harness: the segment lengths are yours, or from your CAD export.
- It does not record who entered a segment length or when: the change journal does, when the project has one, and `explain` prints its history of the segment.
- It does not give a service loop per wire or per end: one value for every wire, counted `service_loops_per_wire` times (twice by default).

Next: [mass](mass.md), [wire sizing](wire-sizing.md), [the models](README.md), [changes to results](../changes.md)
