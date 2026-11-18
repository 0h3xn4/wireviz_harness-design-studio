# Segmentation: why a wire is in this harness

This page explains why the interfaces of a project end up in the harnesses they are in. It is written from what the program does (`core/generate/segmentation.py`), and the examples come from the `flatsat` example, where you can repeat them with `harness-design-studio explain DIR W005` (a harness) or `explain DIR IF-001` (an interface).

## Contents

- [What the tool decides](#what-the-tool-decides)
- [The rule](#the-rule)
- [The inputs and where they come from](#the-inputs-and-where-they-come-from)
- [The assumptions it rests on](#the-assumptions-it-rests-on)
- [A worked example](#a-worked-example)
- [What happens when a value is missing](#what-happens-when-a-value-is-missing)
- [One harness that branches](#one-harness-that-branches)
- [What the model does not do](#what-the-model-does-not-do)

## What the tool decides

Generation puts every interface that has two devices, two connectors and a type into exactly one harness; interfaces that share a **group key** share the harness. `explain DIR HARNESS` gives a derivation of kind `segmentation`: the mode, the settings that keep things apart, the key, each interface of the harness with its devices, zones, chain and class, and the line the generator recorded. `explain DIR INTERFACE` says which harness carries the interface and why, or, when none does, the reason the interface was skipped (no connector on one end, a device that does not exist, more than two devices...).

## The rule

The key depends on `segmentation.mode` (the method is chosen with this key and the `segregation` keys; the table of every key that selects it is on [selectable models](selectable-models.md#segmentation)):

| Mode | Interfaces share a harness when they have the same |
| --- | --- |
| `per_connector_pair` (default of a file that names no mode) | pair of device connectors, and chain |
| `per_unit_pair` | pair of devices, chain and class |
| `per_zone_pair` | pair of zones, chain and class |
| `per_connector_group` (since 2.3.0; a new project starts with it since 2.4.0) | chain, and device connectors joined by interfaces ([below](#one-harness-that-branches)) |

- The **chain** is the redundancy (nominal or redundant) of the interface. With `segregation.forbid_nominal_with_redundant` on (the default) the two chains never share a harness.
- The **class** is `pyro` for a pyro interface (while `forbid_pyro_with_other` is on), otherwise the class of its category in `segregation.category_pairs_to_separate` (categories that must stay apart get different classes), otherwise `main`. In `per_connector_pair` mode the connector decides and the class is not part of the key; the tool notes it when one harness mixes classes.
- The **zone** of a device is the field *Zone* of the device. A device with no zone is in the zone *no zone*.

## The inputs and where they come from

| Input | Source |
| --- | --- |
| Mode | `config/segmentation.json: mode` |
| Keep chains apart, keep pyro apart | `config/segregation.json: forbid_nominal_with_redundant`, `forbid_pyro_with_other` (default yes) |
| Category pairs kept apart | `config/segregation.json: category_pairs_to_separate` |
| Devices, zones, connectors, chain | The design. |

## The assumptions it rests on

- **A-SEGMENT-MODE.** The mode decides which interfaces share a harness; the segregation settings keep chains, pyro lines and listed categories apart. In `per_connector_group`, the mode a new project starts in since 2.4.0, the groups of `per_connector_pair` that plug into one device connector are joined into one harness that branches; a ring, different chains and the interfaces of a released harness are not joined.
- **A-ZONE.** The zone of a device is a field of the device. Dragging a device box into another zone in the block diagram rewrites that field (the editor says so in a message), and the grouping per zone pair changes with it. Stays built in: it states where the zone is kept (a field of the device); how the zones group the harnesses is the setting `segmentation.mode`.

## A worked example

`harness-design-studio explain DIR IF-001` on the `flatsat` example (mode `per_zone_pair`) prints that `IF-001` is in harness `W005`: *3 interfaces share it: bus to egse*. The key is `zp|nominal|main|bus|egse`: the chain is nominal, the class is main, and the zones are `bus` (`PCDU1`) and `egse` (`GPSU1`). The other two interfaces of `W005` are `IF-022` and `IF-025`, which also connect a device in `bus` with a device in `egse`.

## What happens when a value is missing

A mode that is not one of the four is not used: the default is, and the derivation says so. A tool older than 2.3.0 does the same with `per_connector_group`: its Generate warns *segmentation.mode 'per_connector_group' is not known; using per_connector_pair* and makes the pairs again, so it removes a joined draft (a released one stays); update the whole team together. A harness that no group of the current design matches (the design changed since it was generated) is reported as *generate the harnesses again*. A harness drawn by hand has no segmentation rule.

## One harness that branches

Since 2.3.0 (decision D-243) `segmentation.mode` can be `per_connector_group`. It is chosen by the project. Since 2.4.0 (decision D-247) a new project starts with it (`new FOLDER`, the editor's *New project*, `create_project`); a project keeps the mode it names, so a project made before stays `per_connector_pair`, and a file that names no mode is still read as `per_connector_pair`, the default of the setting. Generate first makes the groups of `per_connector_pair`, then joins them:

1. A graph has a node for each device connector and an edge for each group. Each chain has its own graph while `segregation.forbid_nominal_with_redundant` is on, so the two chains are never joined.
2. Each connected part of the graph is a candidate. Its connectors are put on two ends by a walk from its first connector in natural ID order (`STR2-J01` before `STR10-J01`), which is end X; the connectors joined to it are end Y, and so on.
3. When every group joins an X connector to a Y connector, the candidate is one group: key `cg|<chain>|<first connector>`, one harness with one plug on each device connector, a branch point on an end with more than one connector (*Branch X*, *Branch Y*), the trunk between the ends and a segment from each plug to its branch point. Its name is the connectors of each end joined by ` + ` (at most three, then *and N more*): `OBC1-J01 to STR1-J01 + STR2-J01 + STR3-J01`.
4. When connectors are wired in a ring (three connectors each joined to the other two), one trunk with two ends cannot run them. The groups stay separate harnesses, and Generate warns `branch_not_built`, naming the connectors of the ring.
5. A candidate of one group stays that group, with its `cp|...` key: a project with no shared connector gets the same harnesses in both modes.

A group whose interface is carried by a released harness is not joined (a released harness is never taken over). Generated drafts are taken over when the mode is chosen: the draft with the lowest ID among those whose interfaces all belong to the joined group keeps its ID; its locked wires, labels, notes and strip lengths, and those of the other drafts, carry over, as do the cable connectors a person edited. The other drafts are removed; what cannot carry over (an accessory of a removed draft, an entered segment length whose ends are gone) is reported as `locked_data_lost`. `explain DIR HARNESS` names the join (*IF-001, IF-002 and IF-003 share a harness because they plug into OBC1-J01; mode per_connector_group; ends X: OBC1-J01, Y: STR1-J01, STR2-J01, STR3-J01*) or the ring that kept a harness apart.

## What the model does not do

- It does not decide where a harness is routed or how long it is.
- It does not merge two groups by itself, except in `per_connector_group`: a project that wants fewer harnesses chooses a coarser mode.
- It does not segment by geometry: zones are names typed by people.

Next: [pin allocation](pin-allocation.md), [wire length](wire-length.md), [the models](README.md)
