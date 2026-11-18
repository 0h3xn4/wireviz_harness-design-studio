# Design of 2.3.0: branching harnesses and splices

Written on 2026-11-17 from a reading of the code at `ba1d2b2` (master, with pull request 3 of 2.2.0) and of the users' harness plan template as the owner's session described it. The decision that records it is D-243. D-235 is the owner decision that placed branching harnesses and splices at 2.3.0; in [`PLAN_2.0.md`](PLAN_2.0.md) section 3.2 they are milestone M6 (M6a splices, M6b branches and breakouts, M6c backshells). It is a design only: nothing of it is built. *Added 2026-11-18:* pull requests 2 to 7 of section 10 are built (255, 262, 263, 264, 265 and pull request 7), and version 2.3.0 is prepared (decision D-245: a minor release, no format change, no release candidate first); it is not tagged yet. *Added 2026-11-18, after the publication of 2.3.0:* 2.3.0 is published as the latest full release (annotated tag `v2.3.0` on `5104988`, the merge of the preparation, #267; `compliance/SIGNOFF.md`, *Publication of 2.3.0*); the branching of pull requests 2 to 7 is in it, and the splices of section 6 are not (3.0.0, format 3). Paths are relative to `src/harness_design_studio/` unless they start with `docs/` or `tests/`.

## 0. The answer in short

- **Branching fits format 2.** A harness with several connectors, branch points and segments with lengths are all in the model already (`Harness.connectors`, `BranchPoint`, `Segment`). Generate already makes such harnesses. What 2.3.0 adds is a new segmentation choice, edits of the routing tree, and new outputs. None of it needs a new field or a new value of a list in a project file.
- **A splice does not fit format 2 cleanly.** The clean form is a connector of the harness with a new role `splice`. A new value of `Role` is a format change: a 2.x tool sets the whole harness aside (tried, section 4). A format 2 form exists (an `inline` connector named by the existing `Splice` entry), but every 2.x tool then reads the project as editable and writes a test table that cannot be done on the built harness (tried, section 4).
- **Recommendation (owner question B1):** 2.3.0 is a minor release in format 2 with **branching only** (M6b without the breakout kind). **Splices** (M6a) go into **format 3**, so by the owner's answer to Q10 of the 3.0 design they ship with **3.0.0**, together with the versions and the fields of the harness plan. Backshells (M6c) come later. The alternatives are in B1.
- **The owner's answers (2026-11-17):** B1 to B9 as recommended (section 12). 2.3.0 is branching in format 2 (M6b); splices come with format 3 in 3.0.0 (M6a); Generate joins harnesses that share a device connector only in the new opt-in mode `per_connector_group`; existing two-plug harnesses stay as they are; harnesses with a branch point get the *Routing* and *Segments* sheets and `segments.csv`. The decision is recorded as D-243.

## 1. What the program does at 2.2 (master)

**Branch points and segments that Generate makes.** `core/generate/engine.py` `_build_harness` puts every interface of a segmentation group into one harness. It orients each interface to two ends, X and Y (`segmentation.orient`). It makes one cable connector for each device connector on each end (one plug per device connector inside one harness). An end with more than one connector gets a branch point, named `Branch X` or `Branch Y` (ID `<harness>-B1` or `-B2`, `naming.DEFAULTS["branch"]`). Segments join each cable connector to its branch point, and the two ends to each other (the trunk, `<harness>-L1`). An entered segment length is kept by the pair of its nodes (`old_len`); a length that cannot be kept is reported (`_warn_lost_data`). The wires run from cable connector to cable connector; no wire ends at a branch point.

**When that happens.** With `segmentation.mode` = `per_zone_pair` or `per_unit_pair`, a group can hold several connectors on one end. The packaged example `flatsat` (mode `per_zone_pair`) has six such harnesses: `W001` has 18 cable connectors, two branch points and 19 segments; `W007` has `GPSU1-J03 + RFSU1-J02` on one end and `SCOE1-J02 + SCOE1-J14` on the other, the shape of the users' harness. With the default `per_connector_pair`, a group is one pair of device connectors, so every harness is straight.

**One plug per far connector (2.1, D-237 Q2).** Run on a blank project with `OBC1-J01` carrying RS-422 ×3 to three star trackers (the case of `tests/test_e2e_rs422x3.py`): the default mode gives three harnesses `W001` to `W003`, each with a plug on `OBC1-J01`. Generate warns `box_connector_shared`; the integrity check reports `box_connector_mated_twice` through the design rule `model-inconsistent`. With `per_zone_pair`, only the star trackers that share a zone join one harness: in the blank template's placement one went to another zone, so two harnesses still plugged into `OBC1-J01`. The advice text (`integrity.one_plug_advice`) and the editor's note (`edit.py`, the notes of a connector in use) say *until a harness can branch (planned for 2.3.0)*.

**What a person can draw.** A harness drawn by hand (`generated: false`) can hold any number of connectors: `manual_harness.plan_add_connector` adds a cable connector that mates with a device connector, or an `inline`, `feedthrough` or `test` connector with a library part; `wires.plan_add_wire` adds wires between any two pins. The diagram draws such a harness from its anchor: each further plugged connector is a line from the anchor port to its own port (`core/cable_ends.py`). `gui/cable.py` refuses a second plug on a port. A person cannot create, move or delete a branch point or a segment: a search of `gui/` for *segment* finds only the import and the lock tree. Segment lengths come in only through `import-lengths` (harness, segment, length) and the import wizard; `export-data` writes them back (`open_data.segment_lengths`). The release text `RELEASE_TEXT_LENGTHS` says to enter them *in the Harness tab*, which has no place for them.

**Lengths.** `lengths.wire_length` is the one answer: the wire's own `length_m`, else the sum of the segments on the one path between its two connectors (`path_trail`; none when the segments form a loop, which the rule `segment-loop` reports). A generated wire stores the path plus the service loops (`generated_length`, A-SERVICE-LOOP). A wire of a drawn harness without a length of its own takes the path sum, without loops. The bundle model `busiest_segment` reads segments (`generate/bundle.py`). The output verifier has its own path walk (`outputs/verify.py` `_length_of`).

**What the outputs do with branches.** The drawing puts connectors in two columns by a two-colouring of the wire groups (`drawing._sides`), draws a routing sketch of the tree when it has at most 14 nodes (`SKETCH_MAX_NODES`; `flatsat` `W001` has 20, so it has none), and lists the segments with their lengths under the diagram. The wire list has one row per wire with its length. The build workbook has no segment, no branch point and no routing sheet. The tests are one continuity and one isolation test per wire (`tables.tests`). The labels, the BOM and the mass do not read segments.

**Splices.** `class Splice(id, name, wire_ids)` and `Harness.splices` exist. Integrity checks only that `wire_ids` name wires of the harness. Diff (`vcs/diff.py`), the lock view (`vcs/lockview.py`), the snapshot of a release, the journal (`journal._HARNESS_LISTS`), `merge-fix` (`merge_ids._CHILD_LISTS`) and the JSON export carry the list. Nothing creates a splice, shows one, counts one in the BOM or the mass (`A-MASS-SCOPE`), or follows a net through one. Every project's `splices` list is empty. The screen's glossary says *a joint where several wires are connected together inside a harness* (`gui/strings.py`).

**The rules that a joint meets today.** The design rule `pin-shared` reports every pin with more than one wire (A-PIN-ONE-WIRE). The independent verifier (`core/verify.py`) reports a pin with several wires as the error `pin_reused`, or as the warning `pin_shared` when one of the wires was drawn by a person. Its `_wire_connection` reads an interface wire only between two cable connectors that mate with device connectors. A generated harness's cable connector without a mate is the error `mate_missing`.

**Backshells and breakouts.** A backshell is `Accessory(kind="backshell", part_id, target=<connector>)` since 1.7.0, in the BOM and, under `full_bom`, in the mass. A breakout is not an object; a boot can be an accessory of the harness whose `position` says where, in words.

**The format.** Every model class refuses unknown fields and checks its values strictly (`core/model/base.py`: `extra="forbid"`, `strict=True`). `Role` is `box, cable, inline, feedthrough, test, loose`; `PartCategory` is `connector, contact, backshell, wire, sleeving, label`. Format 2 is frozen for 2.x (D-230).

## 2. What the users need, and where it lands

The users' harness plan template (described, not read here) has a harness *DEV2 + DEV3 <–> DEV1 + DEV4*: one cable assembly with two connectors at each end, wires from each near connector to the far connectors, shield groups S1 and S2 per wire group, a length per wire, cable types with a number of wires per cable, and pins that are not connected marked.

| Need | At 2.2 | In 2.3.0 |
|---|---|---|
| One harness, two connectors at each end | Generate makes it with `per_zone_pair` when the devices sit in two zones; a person can draw it, without a routing tree | Also with the default kind of grouping, by the new choice `per_connector_group` (section 5.1); a person draws the tree (section 5.2) |
| Wires from each near connector to the far ones | Yes: point to point, through the segments | Unchanged |
| A signal to two far pins | Only as two wires on one pin, with `pin-shared` | A splice, in 3.0.0 (section 6) |
| Shield groups per wire group | `ShieldGroup.wire_ids`, one group per interface or as a person groups | Unchanged; a group that splits at a branch is not allowed (B5) |
| Length per wire | `wire_length`: own length, else the path | Unchanged; segment lengths can be entered in the editor |
| Cable type with N wires | `Part.conductors` (1.11) | Unchanged |
| Pins not connected | *Spare pins* lines of the drawing | Unchanged |
| One plug on a shared connector (D-237 Q2) | One plug per far connector, and a warning | One plug that branches (section 5.1) |

## 3. Scope

**In 2.3.0 (recommended):**

1. Generate: a new choice of `segmentation.mode`, `per_connector_group`, that joins the harnesses of `per_connector_pair` that plug into one device connector into one harness that branches. Opt-in: the default stays (B2).
2. A person: the routing tree of a harness drawn by hand (add, rename and delete branch points; add and delete segments), a segment length entered in the editor (also on a harness Generate made: Generate keeps it), a new leg drawn from a plugged port, and *Join into one harness* for two drawn harnesses on one device connector (B6).
3. Outputs: a *Routing* sheet in the build workbook and a file `segments.csv`, for a harness with at least one branch point (B7); the independent output check of both.
4. Command line: `routing DIR HARNESS [--json]` (read only) and `explain` of a segment and of a branch point.
5. Integrity warnings for a tree that does not reach every connector, for a branch point that joins nothing, and for a shield group across a branch.

**Not in 2.3.0, and why:**

- **Splices (M6a):** a format change (section 4). Recommended for 3.0.0 (B1); designed in section 6.
- **The breakout kind** (`BranchPoint.kind`): a new field. A branch point is where wires leave the trunk, which is what a breakout is; a boot or a transition is an accessory of the harness with its place in words, as today. Not needed for the users' case.
- **Backshells (M6c):** no format change, but the new rule `backshell-missing` would change the rule count (39) and the findings of every project with a `backshell_360` shield end and no placed backshell. Later, in a release of its own (2.4.0 or 3.x).
- **Splices made by Generate** (multi-drop interfaces, more than two devices): skipped today (`segmentation.segment`), and still skipped (B8).
- **Joining in `per_unit_pair` and `per_zone_pair`:** these modes can also leave two plugs on one connector when interfaces of one connector fall into two groups. The join of section 5.1 is defined for `per_connector_pair` groups only; the other modes keep their warning.
- **A shield or a cable jacket that ends at a branch point:** needs a field that says which segments it covers (B5).
- **Labels of branch legs** (*to STR2-J01* at the branch): left out, so the label files of existing harnesses keep their bytes.

**The slices over releases.**

| Release | Content | Format |
|---|---|---|
| 2.3.0 | M6b: branching (this design, sections 5 and 8 to 10) | 2 |
| 3.0.0 | Format 3 of the 3.0 design (versions, the plan's fields) with M6a: the splice role and everything that reads a splice (section 6) | 3 |
| 3.x | The editor gestures of splices if they do not fit 3.0.0; the plan's branching sheets (3.0 design pull request 6) | 3 |
| 2.4.0 or 3.x | M6c: backshells and `backshell-missing` | unchanged |

## 4. Does 2.3.0 need a format change?

### 4.1 Each piece of data

| Piece | Where it can live | New field or value? | Evidence |
|---|---|---|---|
| A harness with N connectors, one plug per device connector | `Harness.connectors`, `Connector.mates_with` | No | Generate makes them (`flatsat`); `plan_add_connector` for a drawn harness |
| A branch point | `BranchPoint(id, name)` | No | `engine._build_harness` makes them; integrity accepts any number |
| Its place on the block diagram | a mark `branch:<branch point ID>` in `diagram/marks.json` (offset `dx`, `dy`) | No: outside the model hash, like `pos:` (D-200 (f)) | `DiagramMark.id` is free text; `mark_is_orphan` never drops a mark of a kind it does not know (also at the tags `v2.0.0` and `v2.1.1`) |
| A segment and its length | `Segment(id, from_node, to_node, length_m)` | No | Nodes may be a connector or a branch point of the harness (`integrity._check_harness`, `dangling_segment`) |
| Which segments a wire runs through | worked out: the one path in the tree (`path_trail`) | No: not stored | `wire_length`, `bundle`, the output verifier all work it out |
| A length per wire | `Wire.length_m`, else the path | No | `lengths.wire_length` |
| The new grouping | the value `per_connector_group` of `segmentation.mode` in `config/segmentation.json` | No field: `ConfigFile.values` is a map of settings | Tried: Generate of 2.2 says *segmentation.mode 'per_connector_group' is not known; using per_connector_pair*, the same code as at `v2.0.0` and `v2.1.1`; `validate` says nothing |
| A breakout kind | `BranchPoint.kind` | **Yes**, a field | `extra="forbid"`; left out (section 3) |
| A boot or transition at a branch | `Accessory(target=None, position="at W001-B1")` | No | `Accessory.position` is words; `target` must be a wire or connector, so it cannot name the branch point without a change of meaning |
| A shield that ends at a branch | a list of segments on `ShieldGroup` | **Yes**, a field | left out (B5) |
| A splice body | a connector with role `splice` | **Yes**, a value of `Role` | tried: see 4.2 |
| "Bonded" pins (`PLAN_2.0.md` 2.4) | `Connector.bonded` | **Yes**, a field; **not needed**: a splice node is one pin, and several wires end on it | tried: see 4.2 |
| A splice part in the library | `PartCategory` `splice` | **Yes**, a value; or category `connector` (B3) | `integrity` requires a connector's part to be of category `connector` (`wrong_part_category`) |
| The kind of splice (crimp, solder sleeve) | the part, and `Pin.termination` (`crimp`, `solder`) of the splice pin | No | `Termination` exists on every pin |
| Continuity through a splice | worked out from the wires and the splice nodes | No | — |

So everything that branching needs is in format 2. Only the splice and two pieces left out of scope need something new.

### 4.2 The splice, tried both ways

A copy of the experiment project of section 1, changed by hand and opened with the code at `ba1d2b2`:

- **A connector with role `splice`:** `validate` reports *A harness could not be loaded and was set aside: connectors.1.role: Input should be 'box', 'cable', 'inline', 'feedthrough', 'test' or 'loose'* (`quarantined`). **A field `bonded`:** the same, *Extra inputs are not permitted*. Every 2.x tool would do the same, harness by harness. That is a format change.
- **The format 2 form:** an `inline` connector `W001-X1` with one pin, three wires ending on its pin, and `Splice(id="W001-J1", wire_ids=[…the three wires])`. It loads with no error. `verify` gives *Pin 1 of W001-X1 is used by 3 wires* (`pin_shared`, a warning because the wires were drawn). `export` writes `tests.csv` with `T001,continuity,W001-P1.1,W001-X1.1,…` and `T011,isolation,W001-X1.1,all other wires and shields,isolated,…`: a continuity test to a pin that is inside the sleeve of a built harness, and an isolation test that a spliced harness fails. Its default mass counts the splice body as a connector, against D-200 (*splices go into the opt-in `full_bom` model only*).

### 4.3 The three ways

| | A (recommended) | B | C |
|---|---|---|---|
| 2.3.0 | Branching, format 2 | Branching and splices, format 2 (the form of 4.2) | No 2.3.0: one release 3.0.0 with branching, splices, format 3 and the 3.0 design |
| Splices | 3.0.0, role `splice` in format 3 | 2.3.0, `inline` body plus a `Splice` entry | 3.0.0 |
| A 2.x tool on a project with a splice | opens it read-only (D-226): it is format 3 | opens it read-write and writes wrong tests, a pin warning and the body's mass | read-only |
| Cost | Splices wait for format 3, which also carries the versions change of the 3.0 design | Two objects per splice that must agree; a convention kept in format 3 or migrated by its step; older tools mislead silently | Branching waits for the versions change, the largest piece of 3.0.0 |
| Release numbers | 2.3.0, then 3.0.0 | 2.3.0, then 3.0.0 without splices | 3.0.0 |

**Why A.** The users' Y harness and the one plug of D-237 Q2 need no splice: every wire runs from one pin to one pin. Branching can ship now, in format 2, with nothing that an older tool misreads in a way that changes what is built (section 8). A splice changes what a test table must say, so an older tool must not write one; only a new format stops it. Format 3 is coming for other reasons (the 3.0 design), and the owner decided that one format 3 holds both (Q10).

**The rule for the splice in format 3.** Everything that reads a splice ships in the release that first writes format 3: the role, the nets, the rules, the verifiers, the test table, the mass and the outputs (section 6). Otherwise a 3.0.0 tool would read a later 3.x project with splices read-write and repeat the faults of 4.2. Only the editor's gestures may follow in a 3.x minor release.

## 5. Branching in 2.3.0

### 5.1 Generate: `per_connector_group`

A new choice of `segmentation.mode`: *Interfaces whose device connectors are joined by interfaces share a harness: one plug on each device connector, branching where needed.* `core/settings.py` gets the choice; `A-SEGMENT-MODE` gets a sentence. The default stays `per_connector_pair`.

**The groups.** `segmentation.segment` first makes the groups of `per_connector_pair`, with every check of today (skipped interfaces, chains). Then it joins them:

1. Build a graph: a node per device connector, an edge per group.
2. A connected part of the graph is one candidate. Groups of different chains (nominal, redundant, when `forbid_nominal_with_redundant` holds) are never joined: each chain makes its own graph. The class note of `per_connector_pair` (*mixes interface classes*) stays: one plug forces the classes together at that connector anyway.
3. **Two-sided test.** The candidate is coloured in two by a walk in breadth from its first connector in natural ID order (`links.natural_key`), neighbours in the same order. The first connector is end X. When every edge joins X to Y, the candidate becomes one group of mode `per_connector_group`, with the side of each connector. When it is not two-sided (three connectors wired in a ring), its groups stay as `per_connector_pair` and Generate warns `branch_not_built`: *OBC1-J01, RW1-J01 and RW2-J01 are wired in a ring, so one harness cannot run them as two ends of one trunk. They stay separate harnesses; draw the harness to join them.*
4. A candidate of one group is that group, unchanged (key `cp|…`), so a project with no shared connector gets the same groups and keys in both modes.

**The harness.** `_build_harness` takes the side of each connector from the group (a new field of the `Group` dataclass, `sides`; not a file field) instead of `orient`. Everything after that is the code of today: one cable connector per device connector, a branch point on an end with more than one connector, the segments, the wires, the shields, the lengths. The D-237 case gives one harness: one plug on `OBC1-J01`, three plugs on the star trackers, `Branch Y` and four segments. The users' case gives `Branch X`, the trunk and `Branch Y`. The name is the connectors of each end joined by ` + `, then ` to `, at most three names per end and then *and N more*: `OBC1-J01 to STR1-J01 + STR2-J01 + STR3-J01`.

**The key and the ID.** The key is `cg|<chain>|<first connector>`. A joined group takes over the unreleased draft with the lowest ID among the drafts whose interfaces all belong to the group (an extension of `_match_renamed`). The other such drafts are removed. Their locked wires, labels, notes and strip lengths carry over by interface and signal (`_wire_keys` of every taken draft); a cable connector a person edited keeps its part, gender, keying and pin details (`_keep_edited_connector`) under the kept harness's numbering. What cannot carry over (an accessory on a removed draft's connector, an entered segment length whose nodes are gone) is reported by `_warn_lost_data`, as today. A released harness is never taken over: its interfaces stay out of the group (`frozen_owned`), and a new interface on its connector keeps the warning `box_connector_shared`.

**The words.** `one_plug_advice` names the new choice: *… or set segmentation.mode to per_connector_group for one harness that branches.* The editor's note on a connector in use says, in that mode, *Generate joins it into the harness on J1 as a branch*. The text of a finding is part of its ID (2.1.1, D-239), so a waiver of `model-inconsistent` on such a connector shows as stale once and must be made again. No stored golden holds the old text (searched: only documents do).

**Explain.** `derive_layout.segmentation_derivation` adds the step of the join: *IF-001, IF-002 and IF-003 share a harness because they plug into OBC1-J01; mode per_connector_group; ends X: OBC1-J01, Y: STR1-J01, STR2-J01, STR3-J01.* A ring names the connectors that close it.

### 5.2 A person draws the tree

A new pure module `core/routing.py` (no Qt), one undo step per plan, a released harness refuses with the reason (`wires.released_text`):

- `plan_add_branch_point(project, harness_id, name)`: the next free `branch` ID of the namer. Drawn harnesses only.
- `plan_rename_branch_point`, `plan_delete_branch_point` (its segments go with it; refused while a wire's only path runs through it, with the wires named).
- `plan_add_segment(project, harness_id, a, b, length=None)`: `a` and `b` are connectors or branch points of the harness. Refused when it would close a loop (`loop_segments`), so the rule `segment-loop` stays for hand-edited files. Drawn harnesses only.
- `plan_delete_segment`.
- `plan_set_segment_length(project, harness_id, segment_id, metres)`: also on a harness Generate made. Generate keeps the entered length by its two nodes (`old_len`), as it keeps an imported one. A released harness refuses.
- `plan_add_leg(project, harness_id, connector_id, pin_ids=None)`: a new loose end on a drawn harness, with a wire from each chosen pin of its plug on `connector_id` that no wire of the harness uses yet (default: those with a signal). A pin with a wire already is refused with the pin named: two wires on one pin need a splice. It adds a branch point and its segments when the plug had one leg before, and moves the existing leg's segment onto the branch point. The diagram calls it when a cable is dragged from a port that a drawn harness plugs into: today `gui/cable.py` refuses that port; in 2.3.0 the port accepts it as a new leg of that harness. A harness made from a connection keeps the refusal (its link owns its pairs).
- `plan_join_harnesses(project, keep_id, other_id)`: two drawn harnesses with plugs on one device connector become one. The plugs on that connector become one (the kept one); the wires of the other are moved to it pin by pin; refused when both wire one pin, or when the two plugs have different parts, with the reason. Every other connector, wire, shield and accessory of the other harness moves over under its ID; a branch point and segments join them; the other harness is deleted. A harness made from a connection or a released one refuses. One undo step and one journal row.

**The diagram.** A drawn harness with branch points is drawn from its anchor through each branch point to its far ports (`cable_ends` gains the branch points of a harness and their places). A branch point sits at the middle of its connectors unless the mark `branch:<ID>` moves it; dragging it writes the mark (outside the hash, so no output goes out of date). `layout.mark_is_orphan` drops a `branch:` mark whose branch point is gone, and `merge_ids` renames it with its harness, as it does `pos:`.

### 5.3 Lengths (owner question B4)

A segment is the bundle between two nodes. Its length is measured from the rear of a connector (where the wires leave the connector body or its backshell) to the centre of a branch point, and between the centres of two branch points. A wire's length stays `wire_length`: its own, else the sum of the segments on its path; Generate adds the service loops to a generated wire (A-SERVICE-LOOP); a wire of a drawn harness gets no loops unless a person sets its length. `import-lengths` keeps its columns (harness, segment, length) and its unit option; it already accepts a drawn harness's segments. `export-data` `segment_lengths` writes them back. Nothing in 2.3.0 reads a connector's depth. A new derivation step in `explain` of a wire lists the segments of its path with their lengths and where each length came from (entered, imported, kept by Generate).

### 5.4 Shields across a branch (owner question B5)

A shield group is a set of wires with one end A and one end B (`ShieldGroup.end_a`, `end_b`). A group whose wires all run between the same two connectors keeps that meaning through branch points: the shield runs the whole path. Generate makes only such groups (an interface has two ends). A group whose wires end on different far connectors has more than two ends, which the model cannot say. In 2.3.0 `wires.plan_group_wires` refuses it with *W001-001 and W001-005 end on different connectors (STR1-J01, STR2-J01); a shield group runs between two connectors*, and integrity warns `shield_across_branch` for one in a file. An overall shield (or the jacket of a multi-core cable) that ends at a branch point needs the list of segments it covers: a field, left for a later format.

### 5.5 Rules and integrity

No new design rule; the count stays 39. New integrity warnings, reported through `model-inconsistent` like the plug warnings, each declared in `_Reads` of the tracker (`core/integrity.py`, `docs/developer/agent/core.md` *Incremental work*):

- `segment_tree_split`: a harness with branch points whose segments do not reach every connector; the wires between unreached nodes have no length.
- `branch_point_unused`: a branch point with fewer than two segments.
- `shield_across_branch`: section 5.4.

`box_connector_mated_twice` and `box_pin_wired_twice` stay as they are; they go quiet when the plugs are joined. `pin-shared` is unchanged in 2.3.0. `segment-loop` is unchanged.

### 5.6 Outputs

**The sparse rule, and where it cannot hold.** New lines and files appear only for a harness with at least one branch point. A straight harness keeps its bytes. The example `flatsat` already has branch points, so its files change once (owner question B7, with D-191 (4)).

| Output | Change |
|---|---|
| Drawing | Unchanged code paths. The sketch shows the tree up to 14 nodes, as today; the segment lines list the lengths. The users' harness (four connectors, two branch points) gets a sketch. |
| Wire list, pinouts, labels, BOM, mass and length | Unchanged |
| Tests | Unchanged: without a splice every wire runs pin to pin, so one continuity and one isolation test per wire stays right |
| Build workbook | A sheet *Routing*, after *Cut list*, for a harness with a branch point: one row per segment (segment, from, to, length or *to fill in*, number of wires, the wires), then one row per branch point (its name and the connectors beyond it on each side). *Start here* lists the sheet. No new readiness check: a segment without a length already shows as *Wires without a length* |
| `harnesses/<ID>/segments.csv` and a sheet *Segments* in `<ID>.xlsx` | The same rows as the first block of *Routing* |
| `system/export.json`, `wireviz.yaml` | Unchanged: they already carry the branch points and segments, and WireViz connectors as they are |
| `export-data` | Unchanged: `segment_lengths` exists |

**The independent output check** (`core/outputs/verify.py`) works out the *Routing* and *Segments* rows from the project alone, with its own path walk (`_length_of`) and its own count of the wires per segment, and reports `out_routing` when a cell differs, a sheet is missing for a harness with a branch point, or one is present for a harness without one.

### 5.7 Explain, diff, lock view, journal, `merge-fix`

- `explain DIR W001-L3` (a segment): its nodes, its length and its source, and the wires through it. `explain DIR W001-B2` (a branch point): its segments and the connectors beyond it. `explain DIR W001` names the join (5.1).
- `diff` and `lockview` already know the kinds `branch_point` and `segment`: an entered length is a change of a segment; a join is a removed harness and a changed one. A released harness locks its segments (`content_hash`), so an entered length is refused on it, as `import-lengths` refuses today.
- Journal: every plan of 5.2 goes through `History`, so each change is a row of kind `branch_point` or `segment` (`journal._HARNESS_LISTS`).
- `merge-fix`: renames branch points and segments with their harness already (`merge_ids`); 2.3.0 adds the `branch:` marks.

### 5.8 Editor

- **Settings > Project:** the segmentation choice offers *per connector group* with its text.
- **Harness tab:** a *Routing* table under the wires (segment, from, to, length, wires), with the length editable (one undo step; on a generated harness it says *kept by Generate*). For a drawn harness: *Add branch point*, *Add segment…*, *Rename*, *Delete*. The drawing preview shows the sketch.
- **Diagram:** a cable dragged from a plugged port of a drawn harness becomes a new leg (5.2); branch points drawn and dragged; the context menu of a plug on a shared connector offers *Join into one harness…*.
- **Problems panel:** the fix of `box_connector_mated_twice` is *Join into one harness* when the plugs are drawn, and *Use per_connector_group* (opens Settings at the choice) when they are Generate's.
- **Inspector:** a branch point shows its segments and lengths.
- Strings in `gui/strings.py`; the prototype follows (`prototype/app.js` holds its own copy of the diagram rules).

### 5.9 Command line

- `routing DIR HARNESS [--json]`: the tree (segments with lengths and sources, branch points, the wires per segment), read only, with a `SHAPES` entry for `--json` and a line in `docs/CLI.md`.
- `settings DIR --set segmentation.mode="per_connector_group"`: exists.
- `import-lengths`: unchanged.
- `explain`: the objects of 5.7.
- No command-line versions of the edits of 5.2: the tool has none for its other edits either (*Not built: command-line versions of the new edits*, `CLAUDE.md`). `api.__all__` is unchanged.

## 6. Splices (for the release that first writes format 3)

*Status (added 2026-11-18):* sections 6.1 to 6.6 are built on the branch `feat/splices` (milestone M6a, the splice parts S1 to S4 of section 10 in one pull request, with the end-to-end test of S5 through the command line), on `master` after pull request 1 of 3.0.0 (format 3, #274): the role `splice` and the category `splice` in format 3, `core/splices.py`, `core/nets.py` with the verifier's and the output check's own copies, the rules and integrity checks of 6.4, the outputs of 6.5 with their check and a golden set, `explain` and `routing` of 6.6, and the editor's *Splices* list in the Harness tab. Where it differs from this section, and what is left, is in section 21 of [`DESIGN_3.0_HARNESS_PLAN.md`](DESIGN_3.0_HARNESS_PLAN.md#21-splices-as-built-m6a). Not released.

### 6.1 Model

- `Role` gets `splice`. A splice is a connector of a harness with role `splice`, no `mates_with`, no `unit_id`, and a library part (B3). Each pin is one node: an ordinary splice has one pin, `1`; a splice block with several nodes has one pin per node. Several wires end on one pin. There is no `bonded` field.
- `Pin.termination` of the node says how the wires are joined: `crimp` (a crimp splice) or `solder` (a solder sleeve).
- A splice is a node of the routing tree like any connector: `Segment.from_node` can name it, so `wire_length` of a wire from a plug to a splice works unchanged.
- The `Splice` stub of format 2 stays readable and is never written. The step from 2 to 3 writes nothing for splices: every `splices` list is empty (nothing creates one). A non-empty list in a hand-edited file is kept as it is and reported.
- `PartCategory` gets `splice` if B3 is answered so; the step writes nothing for it.

### 6.2 Core plans

`core/splices.py` (no Qt), drawn harnesses only, one undo step each:

- `plan_add_splice(project, harness_id, part_id, nodes=1)`.
- `plan_splice_wire(project, wire_id, splice_id, node="1")`: cuts a wire in two at the node. The wire keeps its ID, signal, interface, gauge, part and colour up to the node; a new wire with the next free ID runs on. A wire with a length of its own refuses (the person says how to split it).
- `plan_add_wire` accepts a splice node as an end that already carries wires.
- `plan_delete_splice`: refused while wires end on it, except a node with exactly two wires, which are joined back into one.

### 6.3 Nets

A **net** of a harness is a set of pins joined by wires, where a splice node joins every wire on it. Pins of cable connectors that mate with a device connector, and loose ends, are the **ends** of a net. The core has one function, `nets.harness_nets(h)`. The independent verifier and the output check each have their own (they must not import the core's), and a test compares the three on random harnesses (Hypothesis).

### 6.4 Rules, integrity, verifier

- `pin-shared` and A-PIN-ONE-WIRE leave out the pins of a splice.
- Integrity warnings: `splice_unused` (a node with no wire), `splice_one_wire` (a node with one wire), `splice_signals_mixed` (wires of different signals on one node).
- `core/verify.py`: an interface wire may end on a splice node; an interface's connections are counted per net: each pair of ends of a net is one connection between two device pins. `pin_reused` and `pin_shared` leave out splice nodes; `mate_missing` leaves out splices.

### 6.5 Outputs

| Output | Change, only for a harness with a splice |
|---|---|
| Tests | Continuity per pair of ends of a net, through the splice (`W001-P1.1 to W001-P2.3 via W001-X1`), in place of one test per wire for the wires of that net; isolation per net, against all other nets and shields |
| Wire list | From and To name the splice as they name any connector; a column *Via* (the splices of the wire's net) |
| Build workbook | The *Connectors* sheet lists splices in a block of their own (part, termination, the wires on each node); the cut list cuts each piece |
| BOM | One line per splice part, counted per splice, as connectors are |
| Mass | Splices only under `full_bom` (D-200); the default model leaves them out, as it leaves out a loose end |
| Drawing | A splice as a small node on its wires with its ID, not as a connector table |
| `wireviz.yaml` | A splice as a WireViz connector of style `simple` |
| Labels | No label for a splice |

The output check mirrors each with its own nets.

### 6.6 Editor and command line

The Harness tab's *Add splice* and *Splice this wire*; the diagram shows nothing new (a splice is inside the harness). No new command; `explain DIR W001-X1` shows the nets of a splice; `routing` lists splices as nodes.

### 6.7 What the 3.0 design takes from this

Format 3 of the 3.0 design (`docs/ait/DESIGN_3.0_HARNESS_PLAN.md` on the branch `docs/design-harness-plan`, not on `master` yet) gains the value `splice` of `Role` and, by B3, of `PartCategory`. Its section 9 says *splices, whose pins are one net*; with this design each pin of a splice is one node, so the rule reads *a node per splice pin*. Its risk *2.3.0 may need a format change itself* is answered: 2.3.0 does not; the splice does, and joins format 3.

## 7. Breakouts and backshells

A **breakout** is a branch point: the place where wires leave the trunk. A boot, a transition or tape at it is an accessory of the harness, with its place in `position` (*at W001-B1*), as 1.7.0 allows; the BOM counts it. The tool does not read the words. A kind on the branch point and an accessory that names it need a field and a change of `Accessory.target` (section 4.1). Not in 2.3.0.

A **backshell** stays the accessory of 1.7.0. The rule `backshell-missing` and a mating part suggested from `Part.mates_with` (M6c) change no format, but they add a rule and new findings to existing projects. Later, in a release of their own.

## 8. Compatibility

**Projects that generate today generate the same.** The default mode does not change, and nothing joins unless a person chooses `per_connector_group`. In `per_connector_pair`, `per_unit_pair` and `per_zone_pair` the groups are made by the code of today; `_build_harness` takes the sides from the group only in the new mode. Proof by tests (section 9): a copy of the segmentation of 2.2 (`tests/reference/segmentation_220.py`) gives the same groups on random projects in the three old modes, the fixture `sat15` and the four examples regenerate to the same harness files, and a second Generate is empty.

**The written outputs.** Straight harnesses keep their bytes. Harnesses with a branch point gain the *Routing* sheet, the *Segments* sheet and `segments.csv`: in the output-hash baseline that is the `flatsat` files `W001`, `W002` and `W004` to `W007` (`<ID>.xlsx`, `<ID>_build.xlsx`, a new `segments.csv`) and the stamp. Owner question B7.

**A project saved by 2.3.0, opened by 2.2.x or 2.1.x (or 2.0.x).** It is format 2, so they open it read-write.

| What the project holds | What the older tool does |
|---|---|
| Nothing new | Nothing different |
| `segmentation.mode` = `per_connector_group` | Its Generate warns *not known; using per_connector_pair* and makes the pairs again: the joined draft is removed and the pairs come back under new numbers; what a person set on the draft is reported as lost (`_warn_lost_data`). A released branching harness stays, frozen. The release notes say: update the whole team (as for ports, D-237 Q1) |
| A drawn harness with branch points, segments, a leg or a join | Read and kept; lengths the same (`wire_length`); its outputs have no *Routing* sheet; its editor cannot change the tree |
| `branch:` marks | Kept: a mark of a kind it does not know is never an orphan |
| An entered segment length on a generated draft | Kept by its Generate, which keeps entered lengths by node pair |

**After the upgrade from 2.2.** Nothing changes on open or on Generate. Existing two-plug harnesses stay as they are (B6): the warning names the way to join them.

**Format 3 (3.0.0) with splices.** A 2.x tool opens such a project read-only (D-226), as the 3.0 design says for format 3.

## 9. Tests first

- `tests/test_branch_segmentation.py`: the D-237 case gives one harness with one plug on `OBC1-J01` and `Branch Y`; the users' case gives `Branch X`, trunk, `Branch Y`; a ring gives pairs and `branch_not_built`; chains are not joined; a released harness is not taken over and the new interface keeps `box_connector_shared`; the lowest draft ID is kept with the locked wires of every taken draft; lost data is reported; two runs give identical files; a switch back to `per_connector_pair` gives the pairs again.
- `tests/test_segmentation_compat_220.py` with `tests/reference/segmentation_220.py` (a word-for-word copy, not edited): the same groups and keys on random projects in the three old modes (Hypothesis).
- `tests/test_routing_edit.py`: every plan of 5.2, its refusals, undo, a released harness refusing, an entered length kept by Generate, a leg from a plugged port, a pin with a wire refused for a leg.
- `tests/test_join_harnesses.py`: a join, a shared pin refused, different parts refused, a harness of a connection refused, undo.
- `tests/test_integrity_tracker.py`: a scenario per new warning.
- `tests/test_outputs_routing.py`: the *Routing* and *Segments* rows; none for a straight harness.
- `tests/test_verify_routing.py` (mutations): a changed length cell, a wire moved to another segment, a row missing, a sheet missing or present where it must not be, a wrong count: each gives `out_routing`.
- `tests/test_e2e_branching.py`, through the command line: a blank project; `import-pinout` of DEV1 to DEV4, one connector each; four interfaces DEV2→DEV1, DEV2→DEV4, DEV3→DEV1, DEV3→DEV4; `settings --set segmentation.mode="per_connector_group"`; `generate`: one harness, four plugs, two branch points, a trunk, no `box_connector_shared`; `import-lengths` of the five segments; `export`, `verify --outputs` with 0 errors; `routing --json`; `explain` of a wire, a segment and the harness; a second Generate changes no file; two exports are byte-identical; the same in two folders gives identical project files. Then the RS-422 ×3 case of 2.1.0 in the new mode: one plug on J1, port k to IF-k as in `tests/test_e2e_rs422x3.py`.
- GUI (`tests/test_ui_branching.py`, offscreen): the Routing table, an entered length, a new leg by a drag, a branch point dragged (no output goes out of date), *Join into one harness*.
- Guards: `tools.output_hashes --check` identical except the files of B7; `tools.numbers_snapshot --check`; the goldens; `tests/test_api_stability.py`; the offline and security tests; `docs/CLI.md` and the JSON keys in sync; `perf`: the two-sided test and the join on 200 devices under a stated time (set when measured).
- For the splices (3.0.0): `tests/test_splices.py`, `tests/test_nets.py` (the three copies agree), the verifier mutation tests for continuity through a splice, a golden of a harness with a splice, and an end-to-end test with a power line from DEV2 to DEV1 and DEV4 through one splice.

## 10. Pull requests

| PR | Content |
|---|---|
| 1 | This page (the design commit); D-243 recorded by the lead |
| 2 | Generate: `per_connector_group` in `segmentation.py` and `engine.py` (sides, key, taking over drafts, `branch_not_built`), the setting and `A-SEGMENT-MODE`, the advice texts, the explain step; the compatibility copy and its test. Output hashes identical (no example uses the mode) |
| 3 | `core/routing.py` (the plans of 5.2 with the leg and the join), the three integrity warnings, the `branch:` marks in `layout` and `merge_ids`, the refusal in `plan_group_wires` |
| 4 | Outputs: *Routing*, *Segments*, `segments.csv`; the output check and its mutation tests; the goldens and the output-hash baseline for the files of B7, in a commit of their own |
| 5 | Command line: `routing`, `explain` of a segment and a branch point, `SHAPES`, `docs/CLI.md` |
| 6 | Editor: Settings, the Harness tab's *Routing*, the diagram (legs, branch points, join), the Problems fix, the Inspector, strings, the prototype, UI tests, screenshots |
| 7 | The end-to-end test; the user manual page *Branching harnesses*, `docs/FILE_FORMAT.md` (the `branch:` mark), `docs/OUTPUTS.md`, the in-app guide, CHANGELOG; then the preparation of 2.3.0 as a pull request of its own |

Order: 2, then 3 and 4 in either order, then 5, then 6, then 7. The splice work follows the 3.0 design's pull request 1 (format 3), in this order: S1 the role and category in the model and the step; S2 nets, rules and the verifier; S3 the outputs and the output check; S4 the editor; S5 the end-to-end test. S1 to S3 go into the release that first writes format 3 (section 4.3).

Pull requests 2 to 7 are built (D-243). *Added 2026-11-18:* the preparation of 2.3.0 is done, with decision D-245; it is not tagged yet. *Added 2026-11-18, after the publication of 2.3.0:* 2.3.0 is published (tag `v2.3.0` on `5104988`); pull requests 2 to 7 and the preparation (#267) are in it. *Added 2026-11-18, with the preparation of 2.4.0:* since pull request 271 a new project starts in `per_connector_group` (decision D-247; the default of the setting stays `per_connector_pair`, section 5.1), and version 2.4.0 holds it (decision D-248: a minor release, no format change); it is prepared, not tagged. *Added 2026-11-18, after the publication of 2.4.0:* 2.4.0 is published as the latest full release (annotated tag `v2.4.0` on `85df2a9`, the merge of the preparation, #275; `compliance/SIGNOFF.md`, *Publication of 2.4.0*).

## 11. Risks

- **`_build_harness` serves every mode.** A change for the new mode could move the others. Held by the sides hook only in the new mode, the copy of 2.2's segmentation, the regenerated fixtures and the output hashes.
- **Older tools on the new mode** remake pairs, with a warning, and drop the joined draft. Held by the release notes (update the whole team); a released branching harness is kept.
- **A switch of mode** renumbers and rebuilds drafts: lengths entered on segments whose nodes change are lost and reported.
- **Stale waivers** of `model-inconsistent` after the advice text changes (as in 2.1.1).
- **The `flatsat` outputs change** (B7); a team that compares exported files sees two sheets and a file appear on its branching harnesses.
- **The drawing of a large branching harness** has no sketch above 14 nodes, and connectors of one end may sit in both columns of `_sides`. Not looked at on a real display.
- **Splices wait** for format 3. Until then a person who needs a joint draws an inline connector with several wires on one pin, and the outputs of 2.x then hold the wrong tests of section 4.2. The user manual page says so.
- **3.0.0 grows** by the splice core (section 4.3).
- **A ring of three connectors** is not joined; a person draws it.

## 12. Owner questions and the owner's answers

- **B1. The format change and the release number.** Recommended: **A**: 2.3.0 is branching in format 2, a minor release; splices go into format 3 and ship with 3.0.0, with everything that reads a splice in that release (section 4.3). Alternatives: **B**, splices in 2.3.0 in the format 2 form (an `inline` body and a `Splice` entry), with older 2.x tools writing wrong test tables for them; **C**, no 2.3.0: branching, splices and the 3.0 design together in 3.0.0, so branching waits for the versions change.
  - **Owner's answer (2026-11-17):** as recommended.
- **B2. Does Generate make branching harnesses by itself?** Recommended: yes, by the new choice `per_connector_group`, opt-in; the default stays `per_connector_pair`, and a person can also draw one. Alternatives: make it the default of new projects only (the templates' `config/segmentation.json`), which changes nothing for existing projects but gives new users the join without asking; or no Generate change at all (only drawn harnesses branch).
  - **Owner's answer (2026-11-17):** as recommended.
- **B3. Splice kinds and the library.** Recommended: a splice is a library part of a new category `splice` (in format 3), with `pin_count` the number of nodes; its kind is the part (its description) and the `termination` of its pins (`crimp` for a crimp splice, `solder` for a solder sleeve); the tool ships no splice part (D-12), only an example part in the templates, marked as an example. Alternative: category `connector`, no new value, with splices and connectors mixed in the parts pickers and the BOM.
  - **Owner's answer (2026-11-17):** as recommended.
- **B4. How a branch's length is measured and imported.** Recommended: a segment from the rear of a connector to the centre of a branch point, and between branch point centres; a wire is the sum of its path, plus the service loops of Generate for a generated wire; `import-lengths` unchanged (harness, segment, length); a drawn harness's wires get no loops unless a person sets the length. Alternative: measured to the mating face of a connector, which needs a connector depth on the part (a field).
  - **Owner's answer (2026-11-17):** as recommended.
- **B5. Shields across a branch.** Recommended: a shield group runs between two connectors; a group whose wires end on different far connectors is refused in the editor and warned in a file (`shield_across_branch`); a shield or cable jacket that ends at a branch point waits for a field (the segments it covers) in a later format, not 3.0.0 unless the owner wants it there. Alternative: allow such a group and treat its end B as every far end, which the drawing and the shield rules would have to guess.
  - **Owner's answer (2026-11-17):** as recommended.
- **B6. Existing two-plug harnesses after the upgrade.** Recommended: left as they are. Nothing joins on open or on Generate. Generated drafts join when a person chooses `per_connector_group` (the Generate preview shows what is removed and added); drawn ones by *Join into one harness*, an explicit step that is one undo step and journalled; released ones never, until a new revision. Alternative: the editor offers the join when it opens a project with such plugs.
  - **Owner's answer (2026-11-17):** as recommended.
- **B7. The outputs of harnesses that already branch.** Recommended: approve that the *Routing* sheet, the *Segments* sheet and `segments.csv` appear for every harness with a branch point, which changes the `flatsat` example's files once (D-191 (4)). Alternative: write them only when an export option asks, as `--drawings` does, so no existing export changes.
  - **Owner's answer (2026-11-17):** as recommended.
- **B8. Does Generate make splices?** Recommended: not with the first splices; a person places them in a drawn harness, and multi-drop interfaces stay skipped. Later, when people have used splices, a design of multi-drop generation (bus or star, terminations).
  - **Owner's answer (2026-11-17):** as recommended.
- **B9. The milestone names.** Recommended: keep the plan's names: 2.3.0 is M6b, the splices M6a, the backshells M6c; *M5* stays the drawn-first harness of the plan (section 3.6 of the plan left this to the owner).
  - **Owner's answer (2026-11-17):** as recommended.

## 13. What this design does not check

- The users' template was not read for this design; section 2 follows the description the owner's session gave. Whether S1 and S2 are shields per far connector or of the trunk was not seen (B5).
- No branching harness was built from the tool's outputs, and no user has seen the *Routing* sheet.
- The two-sided test, the taking over of drafts and the leg were not prototyped. What was run: the D-237 case in `per_connector_pair` and `per_zone_pair`, an unknown `segmentation.mode` and an unknown segmentation key, a connector with role `splice`, a connector with a field `bonded`, and the format 2 splice form through `validate`, `verify` and `export`, all with the code at `ba1d2b2` on hand-edited copies of one project.
- The behaviour of 2.0.x and 2.1.x was read from the source at the tags `v2.0.0` and `v2.1.1` (the note of an unknown mode, the rule for marks of an unknown kind), not run.
- The drawing of a branching harness was not looked at, on a real display or offscreen; nor were the diagram's legs and branch points, which do not exist yet.
- Speed of the join on large projects was not measured.
- The splice design (section 6) was not tried beyond section 4.2; the effect of one node per pin on the 3.0 design's sides rule was read, not run.
- Whether a team mixes 2.2 and 2.3 tools, and how often a shared device connector occurs in real projects, was not asked.
