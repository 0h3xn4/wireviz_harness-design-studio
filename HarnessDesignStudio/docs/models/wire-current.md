# Wire current: the current of a wire from the pin currents of its net

This page explains the current the design rules judge a wire with: the current a device pin states (format 5, 5.0.0; design `docs/ait/DESIGN_5.0_FORMAT_5.md` part B, REQ-WIRE-10), worked out over the net the wire is in, or else the current of the wire's interface. It is written from what the program does (`core/currents.py`); the example is made up and can be repeated with `explain`.

## Contents

- [What the tool decides](#what-the-tool-decides)
- [The equation](#the-equation)
- [The inputs and where they come from](#the-inputs-and-where-they-come-from)
- [The assumptions it rests on](#the-assumptions-it-rests-on)
- [A worked example](#a-worked-example)
- [What happens when a value is missing](#what-happens-when-a-value-is-missing)
- [Where the current is used](#where-the-current-is-used)
- [What the model does not do](#what-the-model-does-not-do)

## What the tool decides

A pin of a device connector may state the current through its contact in operation, in amperes, as the device's ICD gives it (*Current (A)* in the Devices tab, the *Current* column of `import-pinout`). For each net of a harness (the pins its wires join, through splices; [splices](../user-manual/splices.md)) the tool looks at the device pin behind each end: the pin of the device connector the end is on, or the one a cable connector's pin mates with (the pin of the same ID). An end on a splice is no end; an end on a loose end or a test connector has no device pin.

- **Every end has a current and they add up** (the largest is the sum of the others): the current of each wire is worked out from them.
- **An end has no current:** each wire takes the current of its interface (*Max current*), as before 5.0.0, or has none.
- **They do not add up**, or the wires form a loop other than equal parallel wires: no wire of the net is worked out, and `check` says so (`current_unbalanced`, a warning, and `current_not_worked_out`, an info).

A project in which no pin states a current is judged as in 4.4.0, wire by wire from its interface; a test compares the rules with a word-for-word copy of 4.4.0 on random projects.

## The equation

The wires between the same two pins are one **branch**. When the branches form a tree, removing a branch splits the net in two sides:

`I(branch) = min(sum of the end currents on one side, sum on the other side)`

`I(wire) = I(branch) / k`, for a branch of k parallel wires of one gauge and one length.

For a net with one source the smaller sum is the current through the branch: the source's side holds the source and the loads beyond it, so it is the larger. The comparison "adds up" uses the tolerance of every other current comparison of the tool (a relative 1e-9).

## The inputs and where they come from

| Input | Unit | Source |
| --- | --- | --- |
| Current of a pin | A | The pin of the device connector: *Current (A)* (`current_a` in its file under `physical/connectors/`), from the ICD of the device. |
| The nets and the branches | none | The wires of the harness and the pins they end on; a splice joins every wire on a node. |
| Gauge and length of parallel wires | AWG, m | The wires: the gauge, and the length the tables use ([wire length](wire-length.md)). |
| Current of the interface | A | The interface of the wire: *Max current*, used when an end of the net has no pin current. |

## The assumptions it rests on

- **A-ONE-SOURCE.** The pin currents of a net describe one source and its loads: the largest is the sum of the others. A net whose currents do not add up is not worked out, and `check` says so (`current_unbalanced`). A net in which an end has no current takes the current of the interface of each wire, as before. Stays built in: it is the reading of a net the method rests on, not a number or a choice among listed alternatives; a net with two sources in parallel is not described by it and is said, not guessed.
- **A-PARALLEL-SHARE.** Wires between the same two pins, of one gauge and one length, share the current equally; contact resistance is not counted. Parallel wires that differ, or whose gauge or length is not known, are not worked out, and neither is a net whose wires form another loop (`current_not_worked_out`). Stays built in for the same reason.

The current of a pin is never assumed (D-11): a pin without one states none, and the interface's current applies.

## A worked example

PCDU1-J01 pin 1 gives 6 A; OBC1-J01 pins 1, 2 and 3 take 2 A each (the contacts of OBC1 are rated 3 A and derated by 0.5, so the line is split over three pins). Harness W003, drawn by hand, joins them in the splice W003-X1: W003-001 from W003-P1.1 to W003-X1.1, and W003-002, W003-003 and W003-004 from W003-X1.1 to W003-P2.1, .2 and .3.

- The net adds up: 6 = 2 + 2 + 2.
- W003-001 carries min(6, 2 + 2 + 2) = **6 A**.
- W003-002 carries min(2, 6 + 2 + 2) = **2 A**, and so do W003-003 and W003-004.
- Two wires in parallel from W003-P1.1 to W003-P2.1, of one gauge and length, with 6 A at both pins, carry 3 A each.

`harness-design-studio explain DIR W003-002` names the pin currents of the net (*6 A at PCDU1-J01.1; 2 A, 2 A and 2 A at OBC1-J01.1, .2 and .3*), the current of each end, the current of the branch (*the smaller of the end currents on its two sides: min(2, 10)*) and, for parallel wires, the share; the current limit, the bundle limit and the voltage drop of the wire then use 2 A, and the derivations list A-ONE-SOURCE and A-PARALLEL-SHARE. When the interface of the wire states a current too, the pins win for the wire and the explanation names the interface's current as *not used*. `current-over-contact` judges each of the four pins on its own: *Pin 1 of OBC1-J01 carries 2 A but its contacts allow 1.5 A after derating* ([contact current](contact-current.md)).

## What happens when a value is missing

- An end without a pin current: the interface's current, as before; a wire with neither has no current, and the checks that need one skip it (the note *Current, voltage-drop and bundle checks did not run for N wire(s) of harness W003: they have no interface and no current on their pins to take a current from* while some pin of the project states a current).
- Currents that do not add up: *The pin currents of the net of W003-001 do not add up: 6 A at PCDU1-J01.1; 2 A, 2 A and 1.5 A at OBC1-J01.1, .2 and .3. Its wires were not checked for current. Correct the currents of the pins.* (`check`, a warning, so a finding of `model-inconsistent` in the design rule check).
- A wire whose current comes from its pins and that has no interface type: the voltage drop is not checked, because the category of the type says how many conductors to count (A-ROUND-TRIP); `unchecked-config` names it (*… wire(s) without an interface type to count the conductors of*).

## Where the current is used

The same function gives the current to the rules `current-over-wire`, `bundle-current` and `voltage-drop`, to their explanations, to the extension field `wire.current_a` and to the column `current_a` of the table `wire_sizing` of `export-data`. **Generate does not read it** (owner question F5): it sizes a wire from its interface's current, and a pin current does not make the harnesses out of date. The rules judge the gauge Generate chose, or the one a person set.

## What the model does not do

- It does not take two sources in parallel, a current that flows back, or a load case: a pin current is one number, the operating current of the contact.
- It does not split a current over parallel wires that differ in gauge or length, and does not count the resistance of the contacts.
- It does not put currents in the build workbook, the Production sheet, the labels or the harness pinouts (cable pins carry none).

Next: [contact current](contact-current.md), [wire sizing](wire-sizing.md), [the models](README.md)
