# Design of 2.1.0: several interfaces on one connector, one interface per port

Written on 2026-11-16 from a reading of the code at 2.0.1 (`69c5aac`). Decision D-237 records it; D-233 is the owner decision it implements, D-235 the order of the 2.x releases. Pull request 1 of section 7 builds the parser of section 3 (`core/ports.py`, `tests/test_ports.py`). Pull request 2 builds the pin assignment of section 4, the two design rules and the verifier of section 1 (`tests/test_ports_allocation.py`, `tests/test_ports_compat_201.py`, `tests/test_ports_checks.py`). Pull request 4 builds the editor core of section 5: the room, the two tiers of the choice, `ops_assign_pins`, `ops_assign_port`, the notes, `connector_choice`, `explain` and `A-PORTS` (`tests/test_multi_interface_connector.py`, `tests/test_multi_interface_release.py`, `tests/test_device_equivalence.py`). Pull request 5 builds the editor screens of section 5: the diagram, the Inspector with the port of each end and *Choose port…*, one *Confirm* per interface, the Devices tab's *Port* column and the port in *Assign…*, the strings and the prototype (`tests/test_ui_multi_interface.py`); nothing else in this page is built yet. Paths are relative to `src/harness_design_studio/` unless they start with `docs/` or `tests/`.

## 1. What the program does at 2.0.1

The files and the generator already allow several interfaces on one device connector (`InterfaceInstance.endpoints[].connector_id`; audit run 1 in `docs/ux-custom-devices-audit.md`). These places refuse it or assume one:

- **Editor core.** `core/edit.py` `_used_connectors` keeps one interface per connector, `free_connectors` leaves out every connector in use (it feeds the Guided auto-choice `choose_connector` and `unit_compat`), and `connector_compat` refuses with *"… already carries IF-… One interface per connector."* Callers: `ops_add_interface`, `ops_complete_chain`, `ops_set_endpoint_connector`, and `core/checks.py` `_assign_connectors` (the fix of the `no-connector` finding). `core/devices.py` `ops_assign_pins` refuses with the same words; it also re-points a pin of another interface without a word and rewrites a fixed pin's signal to the bare name. `core/connector_choice.py` never offers a connector in use and matches fixed pins by the bare name. `core/derive_layout.py` (explain) names only the first interface on a connector.
- **Editor screens.** `gui/controller.py` and `gui/canvas.py` go through `connector_compat`; `gui/canvas.py` keeps the last interface per connector for the port side; `gui/panels.py` has one *Confirm* per connector; `gui/devices_dialogs.py` `AssignDialog` calls `ops_assign_pins`; `prototype/app.js` has its own copy of the refusal. `gui/cable.py` refuses a second plug on a port: that is the physical rule for links and hand-drawn cables, and it stays.
- **Generator.** `core/generate/pins.py` `_allocate_fixed` gives each signal the first free fixed pin with exactly that name. Nothing knows which pins form one port: names like `RS422_1_TX+` fail with "no free pin named TX+", and repeated bare names can mix the pins of two ports. `core/generate/engine.py` keys the pins it held before by `(interface, pin.signal)`. With the default segmentation `per_connector_pair`, interfaces from one connector to different far connectors become separate harnesses, each with a plug on the same connector: warning `box_connector_shared` (generation) and `box_connector_mated_twice` / `box_pin_wired_twice` (`core/integrity.py`, reported by the rule `model-inconsistent`).
- **Design rules.** `signal-unassigned` and `direction-conflict` compare `pin.signal` with the type's signal names, so a port name breaks them. `chains-mixed`, `pyro-mixed` and `model-inconsistent` already handle several interfaces per connector. `category-mixed`, `emc-mixed` and `emc-class-split` look at a harness, not at a connector that carries a noisy and a sensitive interface: a known gap, not changed here. No rule refuses several interfaces; the count stays 39.
- **Independent verifier.** `core/verify.py` takes `pin.signal` of the box pin as the signal at that end and requires the wire label to equal it, so a port name gives `wire_signal_mismatch`.
- **Outputs.** The box pinouts, the mating matrix, traceability, labels and the block diagram work per pin, per plug, per interface or per wire. None needs a change.
- **Releases.** A released harness locks the part, gender and keying of the box connector and the pins its interfaces and wires use; the other pins stay editable (`docs/FILE_FORMAT.md`, `core/vcs/snapshot.py` `locked_pins`).
- **Documents** that say "one interface per connector": `docs/user-manual/define-a-device.md`, `docs/user-manual/generate-harnesses.md`, `docs/models/selectable-models.md`, `docs/transparency_audit/editing-and-change-control.md` (EDIT-C4-008).

## 2. No format change

Format 2 is frozen (D-230). What 2.1.0 needs fits in fields that exist and keep their meaning:

- Several interfaces on one connector: `Endpoint.connector_id` (unchanged).
- The port: part of the existing free-text `Pin.signal` (`RS422_2_TX+`). A KiCad netlist already names nets this way, because net names must be unique.
- Which interface uses a port: the existing `Pin.interface_id`, written by Generate, or `locked` plus `interface_id` when a person chooses.
- A Port column of an imported pinout is not a field: the import writes it into the signal name.

`Endpoint.role` exists but is not used; giving it the meaning of a port would be a format change, so it is not used. Every file that 2.0.1 can write means the same in 2.1.0, and 2.1.0 writes no new field.

**Known limit (owner question Q1, answered by the recommendation).** 2.0.x does not read port names. If 2.0.x runs Generate on a project that uses them, those interfaces fail with "no free pin named TX+" and their *draft* harnesses are dropped; released harnesses and locked pins stay, and 2.1.0 makes the drafts again. The release notes of 2.1.0 say so: update the whole team. The alternative, a sparse field `Pin.port` in a format 3 whose migration writes only the number (2.0.x would open such a project read-only), stays open if the owner prefers it; the parser below reads names either way.

## 3. Ports

A new pure module `core/ports.py`. The independent verifier gets its own copy (it must not import the core's), and a test compares the two.

**Which pins form a port.** For an interface type T with signal names N(T), a pin with `fixed` set and signal s is

- a **bare** pin when s is in N(T) (today's rule; it belongs to the unnamed port);
- a pin of the **named port** P when s is `P<sep>t` (prefix form) or `t<sep>P` (suffix form), with t in N(T), sep one of `_`, `.`, `-`, and P not empty. The port is shown as P (`RS422_2`).

Matching is exact and case-sensitive, as today. Only fixed pins are read, so free pins and the link features (`links.py` `derive_meaning`) do not change.

**When a port can be used.** A named port is complete when each name in N(T) has exactly one pin.

**Refused with a message, never guessed:**

| Case | What happens |
|---|---|
| A pin that reads as two signals or two ports | A note on the pin; no port contains it |
| Two pins for one signal in a named port | The port is refused |
| An incomplete port (no `RX-`) | The port is not offered; a warning names the missing signals |
| Two templates with the same shown name | Both are refused |
| An interface whose locked pins name a port | Its other signals come from that port, or an error ("port RS422_2 has no free RX-"); pins of two ports are never mixed |

**Repeated bare names** (`TX+` on three pins) keep today's assignment byte for byte. When two or more interfaces of one type need them, Generate adds the warning `pin_port_unknown`: it cannot tell which pins form one port; name the ports or lock the pins of each port. The Guided auto-choice never counts repeated bare names as several ports.

## 4. Pin assignment (`core/generate/pins.py`, `core/generate/engine.py`)

Per connector:

1. The pins held before are keyed by the type's signal (through the parser for fixed pins; bare names give the same keys as today).
2. Locked pins stay.
3. Each interface first gets back the complete named port it held before, if it is still free. This keeps the changes of a second Generate small.
4. Then, per interface in today's order (category rank, then interface ID): (a) when today's exact-name path places all its signals, that path is used unchanged; (b) else it takes the first free complete named port in natural name order (`RS422_2` before `RS422_10`).

All or nothing per interface. The explanation of each pin says why ("TX+ of IF-012 uses pin 5, the TX+ of port RS422_2 of OBC1-J1, the first free RS-422 port; ports in name order, interfaces in ID order"), and `explain` shows it.

Because of (a), every project that generates at 2.0.1 generates the same at 2.1.0. Only projects that fail at 2.0.1 with "no free pin named …" change: they now generate. No example or fixture project has a fixed pinout with repeated names or a shared connector, so the output-hash baseline stays identical. A test compares the new allocator with a word-for-word copy of the 2.0.1 `pins.py` on random bare-name connectors.

## 5. The editor and the command line

- **Expert mode.** A connector that already carries interfaces can take another one of a type it carries, when it has room. Room is decided by a dry run of the same `pins.allocate` that Generate uses, with every interface that ends on the connector and the new one, so the editor and Generate cannot disagree. A full connector is refused: *"J01 cannot take another RS-422: its RS-422 ports RS422_1, RS422_2 are used by IF-010, IF-011"*, or *"… too few free pins for TX+, TX- (2 free, 4 needed)"*. A note, not a refusal, when the connector's other interfaces go to another far connector (Generate will make a second harness with its own plug on it and warn, until the branching harness of 2.3.0), or when a released harness plugs into it (the new interface is wired only after a new revision).
- **Guided mode.** First a free connector, exactly as today. Only when none is free: a connector with a fixed pinout that has a free complete port of the type, in the `model.connector_choice` order. Guided never shares a connector whose pins the device leaves free.
- **Inspector.** Each end shows *Port RS422_2 (pins 5-8), chosen by Generate* with *Choose port…*, which calls a new `devices.ops_assign_port` and locks the port's pins (`locked`, `interface_id`; `fixed` and the signal kept). One *Confirm* per interface. The port side on the canvas is the side of the first interface by ID.
- **Devices tab.** A *Port* column (derived; not stored, not exported). *Assign to interface…* offers a port. `ops_assign_pins` no longer refuses a second interface; it refuses a pin that belongs to another interface ("Pin 5 carries IF-011; unassign it first"). The inline notes become port-aware, with a new note for port problems.
- **Explain.** The ranking of connectors lists the interfaces on each candidate and its free ports; a new assumption `A-PORTS`.
- **`import-pinout`** and the import wizard: a new column *Port* (also *Port name*, *Port ID*, or `--column port=HEADING`). A signal is written as `PORT_SIGNAL` unless it already starts with the port. Refused rows: a port without a signal, a port name that cannot be used, a signal that names another port, more than 200 characters. The preview lists the ports per connector, with incomplete or doubled ports as warnings; `--json` gets `ports`.
- **`import-netlist`:** the report of unmatched signals reads port names. **`export-pinout`:** unchanged (the composed names read back without a Port column).
- No new command and no change of `api.__all__`.

**A released harness on the connector.** An interface on a free port of a connector that a released harness plugs into is allowed (the lock rules leave the other pins editable). To the same far connector it joins the frozen group and Generate gives `frozen_changed` (a new revision is needed); to another far connector it gets a new harness with a second plug and the warnings above (owner question Q2, answered by the recommendation: accepted until the branching harness of 2.3.0). A port whose pins a release locks cannot be assigned (`pin_lock_reason`).

## 6. Tests first

- Changed: `tests/test_edit.py` and `tests/test_edit_device.py` (the tests that hold the refusal), `tests/test_gui_journeys.py`, `tests/test_prototype.py`, `tests/test_pinout_import.py`, `tests/test_pinout_cli.py`, `tests/test_kicad.py`, `tests/test_drc.py`, `tests/test_verify_checks.py` (new error `port_mixed`), `tests/test_device_equivalence.py`, `tests/test_release_freeze.py`, `tests/test_freeze_wire_pins.py`, `tests/test_ux_devices_edit.py`, `tests/test_s1_build_layout.py`. Guards that stay green: the output hashes and the goldens.
- New: `tests/test_ports.py` (the parser, with a Hypothesis round trip), `tests/test_ports_allocation.py`, `tests/test_ports_compat_201.py` with `tests/reference/pins_201.py`, `tests/test_multi_interface_connector.py`, `tests/test_multi_interface_release.py`, `tests/test_ui_multi_interface.py`, and the end-to-end test `tests/test_e2e_rs422x3.py`: a blank project; `import-pinout` of OBC1 with J1 = RS-422 ×3 (with a Port column, and with names `RS422_k_TX+`); three star trackers; three interfaces OBC1 → STRk added in Guided mode; `generate`, `export`, `verify --outputs`, `drc`. Each interface uses one port, port k for IF-k; 0 verifier errors; a second Generate changes nothing; two exports are byte-identical.

## 7. Pull requests

| PR | Content |
|---|---|
| 1 | `core/ports.py` and its tests; this page; D-237. No caller yet |
| 2 | Generation, the two design rules and the verifier read ports; the comparison with 2.0.1; `pin_port_unknown`; explain lines; output hashes unchanged |
| 3 | Import: the Port column, port-aware reports of the pinout and KiCad imports, `--json`, `docs/CLI.md`, `docs/IMPORTS.md` |
| 4 | Editor core: room and the two tiers of the choice in `edit.py`, `devices.py` (`ops_assign_pins`, `ops_assign_port`, notes), `connector_choice`, `derive_layout`, the assumption |
| 5 | Editor screens: Inspector, canvas, Devices tab, the wizard, strings, prototype, UI tests, screenshots |
| 6 | The end-to-end test, the release test, the user manual and the guide, CHANGELOG, STATUS, the 2.1.0 preparation |

Order: 1, 2, then 3 and 4, then 5, then 6.

## 8. Risks

- Ports read wrongly from old pin names: held by the exact-name path first, fixed pins only, complete ports only, the comparison with 2.0.1 and the output hashes.
- The independence of the verifier: its own copy of the parser, compared by a test.
- Speed: the dry run of the allocator runs when the pointer is over a connector; it gets a cache and a `perf` test at 1000 pins and 200 devices.
- Two plugs on one connector before 2.3.0 can surprise a user: the note in the editor and the warning of Generate say it.
