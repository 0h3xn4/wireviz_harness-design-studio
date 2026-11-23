# Shield groups and shield ends

This page explains which wires form a shield group and why the group has the ends it has. It is written from what the program does (`core/generate/shields.py`, used by generation and by `explain`), and the examples come from the `flatsat` example, where you can repeat them with `harness-design-studio explain DIR W001-S1` or `explain DIR W005-S4`.

## Contents

- [What the tool decides](#what-the-tool-decides)
- [Which wires form a group](#which-wires-form-a-group)
- [The ends](#the-ends)
- [The inputs and where they come from](#the-inputs-and-where-they-come-from)
- [The assumptions it rests on](#the-assumptions-it-rests-on)
- [A worked example](#a-worked-example)
- [What happens when a value is missing](#what-happens-when-a-value-is-missing)
- [What the model does not do](#what-the-model-does-not-do)

## What the tool decides

Generation makes one shield group for each shield or twisted pair a harness needs, with its wires and its two ends. `explain DIR GROUP` (or `HARNESS.GROUP`, or the wire in the group) gives a derivation of kind `shield-group`: why the group exists, why it has these ends, and how the ends compare with the grounding concept. The cut list shows the group of each wire (*Shield group*).

## Which wires form a group

The group follows the construction and the shielding of the interface type:

| Interface type | Groups made |
| --- | --- |
| `single` construction | no twisted pair, even when its signals name a pair; the overall shield below when the type shields overall (since 4.2.0: before, Generate made none, and its own verifier then refused the harness with `shield_missing`) |
| `coax` | one group of kind `coax` for each wire |
| `quad` | one group of kind `quad` |
| a pair of signals (the signals with the same `pair`; the way out and the way back of a power or ground type) | one `twisted_pair`, or a `shielded_pair` when the type shields per pair |
| shielding `overall` | one more group of kind `overall_shield` over all wires of the interface |

A group a person made is kept.

## The ends

Every generated group except a coax gets the ends `shield_end_a` and `shield_end_b` of `config/generation.json` (`backshell_360`, `pigtail` or `floating`). While one is not set, `floating` is used and generation says so. A **coax** shield is bonded at both ends (`backshell_360`), fixed by the file format. A twisted pair has no shield to ground, and the rules skip it.

**Which connector is end A.** A group names no connector; its ends are placed by its *reference wire*, the wire of the group with the lowest ID in the whole harness: end A is where that wire starts (its `from` connector) and end B where it ends (its `to` connector). It is the rule the drawings have always used, and since 4.1.0 it is one function of the core (`core/shield_ends.py`) that the drawing and the *Production* sheet both take. In `flatsat`, the shielded pair `W002-S12` has the reference wire `W002-013`, which runs from `W002-P10` to `W002-P17`, so its end A (`backshell_360`) is at `W002-P10` and its end B (`floating`) at `W002-P17`. The *Production* sheet of the build workbook and of the harness plan writes each group with its end at the connector of the block and at the far end: in the block of `W002-P10` it reads `W002-S12 shielded pair: here backshell 360, far floating`, in the block of `W002-P17` `here floating, far backshell 360`. A twisted pair has no shield and is written without ends. A group whose wires end on more than two connectors (the warning `shield_across_branch`) has no end at the other connectors, and the sheet says `here not defined (the group ends on more than two connectors)` there.

### Where an end lands

Since 5.0.0 (format 5, part D of `docs/ait/DESIGN_5.0_FORMAT_5.md`) an end may state where it lands (`at_a`, `at_b`; [File format](../FILE_FORMAT.md#where-a-shield-end-lands-part-d)): the connector at that end, the pin of it a pigtail lands on, and the backshell (an accessory of kind `backshell` on that connector) for a 360 degree bond or a pigtail to its lug. A person states it, on a group Generate made too: the grounding concept decides the kind of end, not where it lands. The tool never fills one (owner question F10), not even from the only pin of role `shield` of the device connector, which is a statement about the device and not about this harness; Generate keeps a place while it makes the group again with the same wires, kind and end, and says in the explanation when it drops one. A place names its connector because the ends follow the reference wire and can swap: `check` then says `shield_end_moved`. Its other checks: `shield_pin_missing`, `shield_pin_wired` (a wire ends on that pin as well), `shield_pin_role` (the device pin it mates with has the stored role `power`, `return`, `signal` or `signal_ground`; a role read from the name is not judged) and `shield_backshell_missing`, all warnings; an end `pigtail` with no place is the info `shield_place_not_stated`, and an end `backshell_360` with no place is not reported (F11). [Outputs](../OUTPUTS.md#the-place-of-a-shield-end).

The rules that look at the ends are `shield-unterminated` (both ends floating), `shield-wrong-end` (the ends differ from the grounding concept) and `shield-bonding` (both ends are `backshell_360`, when `config/emc.json: shield_bonding` asks for it); each is explained with the ends it saw.

## The inputs and where they come from

| Input | Source |
| --- | --- |
| Construction, shielding, pairs | The interface type. |
| The wires of the interface | The harness. |
| Ends of the concept | `config/generation.json: shield_end_a`, `shield_end_b` |
| Bonding required | `config/emc.json: shield_bonding` |

## The assumptions it rests on

- **A-SHIELD-GROUPS.** A group follows the construction and the shielding of the interface type. Stays built in: it is the rule that turns a construction into a shield group (a coax is a shield of its own, a pair is twisted), which follows the construction and cannot be a number; the grounding of the ends is a setting (A-SHIELD-ENDS).
- **A-SHIELD-ENDS.** The ends are the grounding concept of the project, except a coax.
- **A-PAIR-NAMES** (a setting, 4.2.0). The design rule `pair-untwisted` finds the signal pairs of a harness: the wires of one interface whose signals have one `pair` in the type, run from the same connector to the same connector and are exactly two (the pairs Generate twists); and two wires without an interface that join the same two connectors and, at each of the two where both have a signal, carry two signals that every interface type that has both gives one pair, or, when no type has both, whose names differ only by the two endings of a row of `naming.pair_suffixes` (`+ -`, `P N`, `H L` by default). A name shared by three wires makes no pair. A pair is twisted when one twisted pair, shielded pair or quad holds both wires; an overall shield, a coax and a wire part with two conductors do not twist.
- **A-SHIELD-BY-TYPE** (built in, 4.2.0). The design rule `signal-unshielded` asks for a shield over a wire of a harness Generate did not make when every interface type that has the signal at its ends shields it (shielding `overall`, `per_pair` for a signal of a pair, or a coax; read as Generate reads a type) and there is at least one; a signal no type has asks for none, and neither does one whose types disagree. A shielded pair, an overall shield, a coax and a quad are shields; a twisted pair is not. A generated harness is left to the verifier (`shield_missing`). Stays built in: it is how a wire without an interface is given the shield its type would have given it, a reading of the types the project holds and not a number.

## A worked example

`harness-design-studio explain DIR W001-S1` on the `flatsat` example prints **twisted_pair, end A backshell_360, end B floating**: the wires `W001-001` and `W001-002` are the pair `power` of `IF-010` (type `power_primary`, shielding none), twisted together. The ends are the concept (`backshell_360` and `floating`), and the comparison says *equal*.

`explain DIR W005-S4` prints **coax, end A backshell_360, end B backshell_360**: the type `rf_coax` is a coax, so each wire is a shield, with the ends fixed by the file format; the concept (`backshell_360`/`floating`) does not apply.

## What happens when a value is missing

If a shield end of the concept is not set, the derivation says that `floating` is used until `shield_end_a` and `shield_end_b` are set. A group no rule of the generator makes today (the design changed since generation) is named, with the advice to generate again. A group made by hand says so.

## What the model does not do

- It does not know where a shield is grounded in the hardware, only the end type typed in the concept and, where a person states it, the pin or backshell the end lands on (format 5).
- It does not check the resistance of a shield bond; the check list names what needs measurements.
- It does not choose between pigtail and backshell: that is the project's concept.

Next: [labels and colours](labels-and-colours.md), [rule limits](rule-limits.md), [the models](README.md)
