# Contact current: what the contacts of a connector may carry

This page explains the check of the design rule `current-over-contact`: the current an interface carries against what the contacts of the connector at its end allow after derating. It is written from what the program does, and the numbers come from the `flatsat` example, where you can repeat them.

## Contents

- [What the tool decides](#what-the-tool-decides)
- [The equation](#the-equation)
- [The inputs and where they come from](#the-inputs-and-where-they-come-from)
- [The assumptions it rests on](#the-assumptions-it-rests-on)
- [A worked example](#a-worked-example)
- [What happens when a value is missing](#what-happens-when-a-value-is-missing)
- [What the model does not do](#what-the-model-does-not-do)

## What the tool decides

For every interface with a known current and every connector at one of its ends, the rule compares the current with the limit of the contacts of that connector. Since 5.0.0 (format 5) a pin of a device connector may state its own current (*Current (A)*, from the ICD): such a pin is judged on its own, with its current, and the finding names the object `CONNECTOR.PIN` (*Pin 1 of OBC1-J01 carries 2 A but its contacts allow 1.5 A after derating*; `explain DIR OBC1-J01.1`). The interface is then judged at a connector only for its pins there that state no current, so a line split over three contacts is no longer judged as if each carried all of it; a project without a pin current is judged as before. A connector of the interface whose rating is not in the library is not checked, and a project whose configuration has no `contact_current_factor` is not checked at all (the rule `unchecked-config` says so). The finding names the object `INTERFACE.CONNECTOR`, for example `IF-001.GPSU1-J01`. `explain DIR INTERFACE.CONNECTOR` shows it as the derivation of kind `contact-current`.

## The equation

`limit = contact rating of the connector part × contact current factor`

The interface is within the limit when its current does not exceed the limit (with the same comparison that the other current rules use, so that a value exactly at the limit passes).

## The inputs and where they come from

| Input | Unit | Source |
| --- | --- | --- |
| Current of the interface | A | The interface: *Max current*. |
| Current of a pin (format 5) | A | The pin of the device connector: *Current (A)*, from its ICD; it replaces the interface's current for that pin ([wire current](wire-current.md)). |
| Contact rating | A | The connector part of the library: the entry of `ratings` named by `config/derating.json: contact_rating_key` (default `contact_current_a`). |
| Contact current factor | none | `config/derating.json: contact_current_factor`. |

The project records no source for the rating or the factor.

## The assumptions it rests on

- **A-CONTACT-SHARED.** The whole current of an interface is compared with the derated rating of the contacts of the connector at each endpoint, unless every pin of the interface at that connector states its own current, which is then judged pin by pin. It is not split over the pins the interface uses, the rating is that of the connector part (not of the contact or the wire crimped into it), and the factor is one number for every connector. Stays built in: the model does not say how many contacts carry the current of an interface (the supply and the return pins belong to one interface), so a split would need an input the project does not have; the one number that is a choice, the factor, is a setting.

## A worked example

`harness-design-studio explain DIR IF-001.GPSU1-J01` on the `flatsat` example prints:

- **Contact current limit: 6 A.** The connector part `EX-MICROD-9-F` has a contact rating of 12 A, the factor is 0.5, so the limit is 12 × 0.5 = 6 A. The interface `IF-001` carries 5 A: within the limit, 1 A to spare.

## What happens when a value is missing

The explanation names what is not set: the current of the interface, the rating of the connector part (with the key it looked for), or `derating.contact_current_factor`. A limit is never made up.

## What the model does not do

- It does not split the current of an interface over several pins or contacts (a pin's own current, from the ICD, says how it is split), and it does not look at the wire in the contact.
- It does not know the temperature, the altitude or the number of mating cycles of the contact.
- It checks the interface's maximum current, not the current of a load case.

Next: [wire sizing](wire-sizing.md), [the models](README.md), [changes to results](../changes.md)
