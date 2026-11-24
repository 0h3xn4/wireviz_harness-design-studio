# History moved out of CLAUDE.md

`CLAUDE.md` is loaded into every Claude Code session, so it holds what an agent needs to work on the code, not the history of the releases. Paragraphs that read like a changelog are moved here word for word, and `CLAUDE.md` keeps a pointer line. The changelog is [`../../CHANGELOG.md`](../../CHANGELOG.md); the status of the tool and its release history are in [`../STATUS.md`](../STATUS.md).

## The Status section of CLAUDE.md up to release 1.9 (round two)

M0 to M9 done (`docs/demos/`), then the October audit (`docs/AUDIT.md`) and the pre-release audit (`../AUDIT.md`); version 1.8.1 is prepared and not published (the version number, the changelog section dated 2026-10-27, the release page text `docs/releases/1.8.1.md` and the regenerated files are on the branch `release/1.8.1`; no tag, no release page, no publication record, not signed off by the owner; it carries the fixes of the audit of 1.8.0, `docs/AUDIT_1.8.0.md`, D-177: no new feature, no file-format change); version 1.8.0 is still the latest published release (published 2026-10-26 as tag v1.8.0 on 1f7431e with the Linux and Windows packages, release workflow run 40390285619; not signed off by the owner; the record and the checksums are in `compliance/SIGNOFF.md`): it carries the milestones M1, M2, M3, M4 and M5 of the workshop feedback (D-172, D-173, D-174, D-175, D-176, plan `docs/ait/WORKSHOP_FEEDBACK_PLAN.md`, which ends with *What is left*). M1 (pull request 111): a new device asks for its name and ID, the word *unit* is *device* on screen and in the documents, problem notices can be turned off (off for the Systems engineer), export asks where to save a project with no folder, RTN is explained. M2 to M5 (pull request 113): M2: connections between connectors, pinout first (D-173). M3: editing a connector and its pins (also on a generated harness, locked against Generate), changing a group, editing all wires, connectors at the ends of the connections (D-174). M4: the library, a folder that a team shares with device and subsystem files, a library window, a number of the same device (D-175). M5: two roles, Systems engineer and Electrical / AIT engineer, replace the Simple/Full workspaces, with a question at the first start (D-176). The design rules number 39. Not built: stage S4, command-line versions of the new edits, a lock per pin; no screen was watched on a real display by a person; macOS support was removed on 2026-10-21 after 1.5.0 (D-168: no macOS build, test or package; the releases 1.2.0 to 1.5.0 keep their disk images, unmaintained); version 1.7.0 (the build workbook per harness and optional PDF drawings, D-169; the build data, D-170; the simple workspace stages S1 and S2, D-171; stage S3 was discarded by the owner and S4 is not built; published 2026-10-22 as tag v1.7.0 on e5d8b1e with the Linux and Windows packages, release workflow run 39861016560; not signed off by the owner); version 1.6.0 (no macOS, D-168; the start screen of a blank project; published 2026-10-21 as tag v1.6.0 on 21f4716 with the Linux and Windows packages; not signed off by the owner); version 1.5.0 (a harness made by hand, D-166; the Linux start check and the packages tested without a Python, D-167; published 2026-10-21 as tag v1.5.0 on 4365368 with the Linux, Windows and macOS packages; not signed off by the owner); version 1.4.0 (the AIT feedback: wire editing, hand-drawn wires, shared pins, groups, pin function, labels, last commit, device library, D-160 to D-165; published 2026-10-20 as tag v1.4.0 on 1427aad with the Linux, Windows and macOS packages; not signed off by the owner); version 1.3.0 (the UI overhaul, D-150 to D-159; published 2026-10-20 as tag v1.3.0 on e7cf531 with the Linux, Windows and macOS packages; not signed off by the owner); version 1.2.0 (published 2026-10-19 as tag v1.2.0 on 1cdd6a7 with the Windows and macOS packages, D-149; not signed off by the owner); version 1.1.0 (published 2026-10-18 as tag v1.1.0 on f998cd9; not signed off by the owner, docs/RELEASE.md step 14); version 1.0.0 (released on the owner's instruction on 2026-10-12, compliance/SIGNOFF.md; version 0.1.0 was released on 2026-10-09 with the engineering decisions open, DEVIATIONS.md T-31). Platform: Ubuntu 24.04 and newer and Windows 10/11 from 1.2.0 (D-149, narrowed by D-168; supersedes D-110, D-127). The owner waived the people-dependent compliance actions on 2026-10-09 (`compliance/DEVIATIONS.md` T-20 to T-30; a waiver accepts a deviation and does not meet the requirement). On 2026-10-12 the owner said "Make default decisions so that I'm not needed" and the assistant recorded defaults (D-142 to D-145, DEVIATIONS.md T-32): the harness boundary rule (D-10) and title block (D-15) are the documented defaults the tool implements; the tool ships no derating/EMC values (D-11) and no approved parts list (D-12), each project supplies them, and nobody has. The licence stays the placeholder `LicenseRef-Proprietary` (D-02, D-143). D-20 is not needed. Generation runs on placeholders until a project supplies values; results must say so. The release is made by pushing a tag `vX.Y.Z`, or by publishing a release on GitHub that creates the tag when tag pushes are refused (`.github/workflows/release.yml`, `docs/RELEASE.md` step 15). Version 1.0.0 is published: tag `v1.0.0` on `0c6a96a`, made through the release page.

## From the Status section of CLAUDE.md, moved with the preparation of 2.1.1 (2026-11-17)

The notes on the publication of 2.0.0rc1, 2.0.0 and 2.0.1, moved word for word to keep `CLAUDE.md` under its size limit; the first item of the Status section still names each of these releases.

**Version `2.0.0rc1` is published** (D-229; 2026-11-12, a pre-release): the first release candidate of 2.0.0 and the first release that writes format 2; its tag was made by `.github/workflows/harness-tag.yml` (D-227), the first use of that workflow, and no ruleset refused it. **Version `2.0.0` is published** (D-230; 2026-11-15, the latest full release until 2.0.1): the full release of what 2.0.0rc1 tested, with the fixes of pull request 226, and no 2.0.0rc2; format 2 is frozen at its tag, which makes M4 and M7a done (M7b followed on `master`, D-231; the later milestones stay open); the end-to-end test was repeated on the head of its pull request before the tag, and the tag was made by `.github/workflows/harness-tag.yml` (D-227), the second use of that workflow. **Version `2.0.1` is published** (D-236; 2026-11-16, the latest full release until 2.1.0): a patch release with M7b (D-231) and the release page of D-232 (the four packages, `SHA256SUMS`, its signature and one release bundle, `tools/release_bundle.py`), and the documents of the demo feedback (D-233 to D-235); no format change, format 2 stays frozen; the tag was made after its pull request was merged and CI was green, by `.github/workflows/harness-tag.yml` (D-227), the third use of that workflow.

## From the Status section of CLAUDE.md, moved with the preparation of 2.2.0 (2026-11-17)

The notes on the publication of the release candidates 1.17.1rc2 and 2.0.0rc1, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 2.1.1 was merged; that item still names the full releases 1.17.1 and 2.0.0 that followed them.

The release candidate `1.17.1rc2` (D-224) was published on 2026-11-11 as a **pre-release** (annotated tag `v1.17.1rc2` on `7fae805`, release workflow run 43067874134, second attempt): the first signed release (keyless Sigstore signatures and a build provenance attestation), with SBOMs, inventories, notices, the LGPL and GPL sources and the offline-audit report attached; Not done for it: nobody verified the signature or the attestation from outside the workflow, the Windows packages were not tried on a real computer and the owner has not signed it off (`compliance/SIGNOFF.md`, *Publication of 1.17.1rc2*).

The release candidate `2.0.0rc1` (D-229), the first release that writes format 2, was published on 2026-11-12 as a **pre-release** (annotated tag `v2.0.0rc1` on `8d1c268`, made by the tag workflow `harness-tag.yml`, run 43175667119, its first use, D-227; release workflow run 43175697733, first attempt; signed and attested by the workflow); `1.17.1` stayed the latest full release until 2.0.0. Not done for it: the signature and the attestation verified from outside the workflow (the owner decided to skip such checks), the Windows packages on a real computer, a look at a real display, the owner's sign-off (`compliance/SIGNOFF.md`, *Publication of 2.0.0rc1*).

## From the Status section of CLAUDE.md, moved with the publication record of 2.2.0 (2026-11-17)

The note on the publication of the full release 1.17.1, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 2.2.0 was written; that item still names 1.17.1 in the list of releases and says where this note is.

The full release `1.17.1` (D-225; the program of `1.17.1rc2` with the retries of the source step) was published on 2026-11-11 (lightweight tag `v1.17.1` on `cb72a3c`, most likely made by the owner publishing the release on GitHub; release workflow run 43117202544, first attempt): the first full release with signed packages, the latest full release until 2.0.0, and its notes say that it supersedes 1.0.0 to 1.17.0. Not done for it: the signature and the attestation verified from outside the workflow (the owner decided to skip it), the Windows packages on a real computer, a look at a real display, the owner's sign-off; a text fault of the Windows install step of its page was fixed by pull request 219 and the `notes_only` run 43125894334 (`compliance/SIGNOFF.md`, *Publication of 1.17.1*).

## From the Status section of CLAUDE.md, moved with the publication record of 2.3.0 (2026-11-18)

The note on the publication of the full release 2.0.0, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 2.3.0 was written; that item still names 2.0.0 in the list of releases and says where this note is.

The full release `2.0.0` (D-230; the program of `2.0.0rc1` with the fixes of pull request 226) was published on 2026-11-15 (annotated tag `v2.0.0` on `e6a6763`, made by the tag workflow `harness-tag.yml`, run 43743416529, its second use, D-227; release workflow run 43743439114, first attempt; signed and attested by the workflow): the latest full release until 2.0.1 and the first full release that writes format 2; format 2 is frozen at its tag. Not done for it: the signature and the attestation verified from outside the workflow (the owner decided to skip such checks), the Windows packages on a real computer, a look at a real display, the owner's sign-off (`compliance/SIGNOFF.md`, *Publication of 2.0.0*).

## From the Status section of CLAUDE.md, moved with the preparation of 2.3.1 (2026-11-18)

The note on the publication of the patch release 2.0.1, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when 2.3.1 was prepared; that item still names 2.0.1 in the list of releases and says where this note is.

The patch release `2.0.1` (D-236; M7b and the release page of D-232; no format change) was published on 2026-11-16 (annotated tag `v2.0.1` on `69c5aac`, made by the tag workflow `harness-tag.yml`, run 43903141934, its third use, D-227; release workflow run 43903192546, first attempt; signed and attested by the workflow): the latest full release until 2.1.0, and the first release page with seven files, the four packages, `SHA256SUMS`, its signature and the release bundle (D-232).

## From the Status section of CLAUDE.md, moved with the publication record of 2.3.1 (2026-11-18)

The note on the publication of the minor release 2.1.0, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 2.3.1 was written; that item still names 2.1.0 in the list of releases and says where this note is.

The minor release `2.1.0` (D-238; several interfaces on one connector, D-237; no format change) was published on 2026-11-17 (annotated tag `v2.1.0` on `97e7d24`, made by the tag workflow, run 43993872749, its fourth use; release workflow run 43993920392, first attempt; signed and attested): the latest full release until 2.1.1.

## From the Status section of CLAUDE.md, moved with the preparation of 2.4.0 (2026-11-18)

The note on the publication of the patch release 2.1.1, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when 2.4.0 was prepared; that item still names 2.1.1 in the list of releases and says where this note is.

The patch release `2.1.1` (D-239; the three fixes of the end-to-end test of 2.1.0; no format change) was published on 2026-11-17 (annotated tag `v2.1.1` on `5e99d3d`, the merge of #249, a test fix after #245; made by the tag workflow, run 44042970611, its fifth use; release workflow run 44042996462, first attempt; signed and attested): the latest full release until 2.2.0.

## From the Status section of CLAUDE.md, moved with the publication record of 2.4.0 (2026-11-18)

The notes on the publication of the minor releases 2.2.0 and 2.3.0, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 2.4.0 was written; that item still names 2.2.0 and 2.3.0 in the list of releases and says where these notes are.

The minor release `2.2.0` (D-244; the device library; no format change) was published on 2026-11-17 (annotated tag `v2.2.0` on `a90ef82`, the merge of #256; made by the tag workflow, run 44137315323, its sixth use; release workflow run 44137517372, first attempt; signed and attested): the latest full release until 2.3.0.

The minor release `2.3.0` (D-245; branching harnesses; no format change) was published on 2026-11-18 (annotated tag `v2.3.0` on `5104988`, the merge of #267; made by the tag workflow, run 44238883189, its seventh use; release workflow run 44238914945, first attempt; signed and attested): the latest full release until 2.3.1.

## From the Status section of CLAUDE.md, moved with the preparation of 3.0.0 (2026-11-18)

The note on the publication of the patch release 2.3.1, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when 3.0.0 was prepared; that item still names 2.3.1 in the list of releases and says where this note is.

The patch release `2.3.1` (D-246; the new logo; no format change) was published on 2026-11-18 (annotated tag `v2.3.1` on `764061f`, the merge of #270; made by the tag workflow, run 44274980246, its eighth use; release workflow run 44275039150, first attempt; signed and attested): the latest full release until 2.4.0.

## From the Status section of CLAUDE.md, moved with the publication record of 3.0.0 (2026-11-19)

The note on the publication of the minor release 2.4.0, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 3.0.0 was written; that item still names 2.4.0 in the list of releases and says where this note is.

The minor release `2.4.0` (D-248; new projects branch, D-247; no format change) was published on 2026-11-18 (annotated tag `v2.4.0` on `85df2a9`, the merge of #275; made by the tag workflow, run 44314858198, its ninth use; release workflow run 44314903316, first attempt; signed and attested): the latest full release until 3.0.0.

The note on version 2.1.1, moved word for word from the fourth item of the same section (the one that starts with *Not built*) for the same reason; the sentence there that names the notes moved out of it now names 2.1.1 too.

**Version `2.1.1` is published** (D-239; 2026-11-17, the latest full release until 2.2.0; no release candidate; tag `v2.1.1` on `5e99d3d`, made by the tag workflow, run 44042970611, its fifth use): a patch release with the three fixes of the end-to-end test of 2.1.0 (`explain` of a shared connector, the advice on a second plug, the *Port* column); no format change.

## From the Status section of CLAUDE.md, moved with the preparation of 3.0.1 (2026-11-19)

The note on version 2.1.0, moved word for word from the fourth item of the Status section (the one that starts with *Not built*) to keep `CLAUDE.md` under its size limit when 3.0.1 was prepared; the sentence there that names the notes moved out of it now names 2.1.0 too, and the first item still names 2.1.0 in the list of releases.

**Version `2.1.0` is published** (D-238; 2026-11-17, the latest full release until 2.1.1; no release candidate first; tag made by the tag workflow, its fourth use): a minor release with several interfaces on one connector and one interface per port (D-233, D-237; `docs/ait/DESIGN_2.1_PORTS.md`, pull requests 236 to 241): a port is a naming convention on `Pin.signal` (`RS422_2_TX+`, `core/ports.py`), the room on a connector is a dry run of Generate's pin assignment (`edit.connector_room`), Guided mode has two tiers, *Choose port…* is `devices.ops_assign_port`; no format change, the scripting interface is unchanged, and every project that generates at 2.0.1 generates the same; 2.0.x does not read port names, so its Generate drops the draft harnesses of such interfaces (owner question Q1), and until the branching harness of 2.3.0 interfaces to different far connectors give one plug each on the shared connector (Q2).

## From the Status section of CLAUDE.md, moved with the publication record of 3.0.1 (2026-11-19)

The note on the publication of the major release 3.0.0, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 3.0.1 was written; that item still names 3.0.0 in the list of releases and says where this note is.

The major release `3.0.0` (D-249; format 3, versions, the harness plan, splices; format 3 frozen from its tag) was published on 2026-11-19 (annotated tag `v3.0.0` on `711f204`, the merge of #287; made by the tag workflow, run 44444461651, its tenth use; release workflow run 44444492708, first attempt; signed and attested): the latest full release until 3.0.1 is tagged.

## From the Status section of CLAUDE.md, moved with the publication record of 3.1.0 (2026-11-19)

The note on the publication of the patch release 3.0.1, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 3.1.0 was written; that item still names 3.0.1 in the list of releases and says where this note is.

The patch release `3.0.1` (D-252; the editor opens nothing with the system's opener; no format change) was published on 2026-11-19 (annotated tag `v3.0.1` on `1c79beb`, the merge of #293; made by the tag workflow, run 44545687219, its eleventh use; release workflow run 44545771026): the latest full release until 3.1.0 is tagged.

## From the Status section of CLAUDE.md, moved with the preparation of 4.0.0 (2026-11-20)

The note on the publication of the minor release 2.2.0, moved word for word from the Status section to keep `CLAUDE.md` under its size limit when 4.0.0 was prepared; the Status section still names 2.2.0 in the list of releases and says where this note is.

**Version `2.2.0` is published** (D-244; 2026-11-17, the latest full release until 2.3.0; no release candidate; tag `v2.2.0` on `a90ef82`, made by the tag workflow, run 44137315323, its sixth use): a minor release with the device library (D-234, D-240; `docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md`, pull requests 246 to 251): a folder of `NAME.device.json` files, `device-libraries.json` at the project root (outside the format), the import record of kind `devices` as the link (`core/library_link.py`), `libraries`/`add-device`/`update-device`/`save-device` (`cli/library.py`), the editor's review (`gui/library_review.py`); no format change, the scripting interface is unchanged, and every project that generates at 2.1.1 generates the same.

## From the Status section of CLAUDE.md, moved with the publication record of 4.0.0 (2026-11-20)

The note on the publication of the minor release 3.1.0, moved word for word from the first item of the Status section to keep `CLAUDE.md` under its size limit when the publication record of 4.0.0 was written; that item still names 3.1.0 in the list of releases and says where this note is.

The minor release `3.1.0` (D-253; `SEARCH`/`ISNUMBER` in the plan's search boxes; no format change) was published on 2026-11-19 (annotated tag `v3.1.0` on `3b183e1`, the merge of #302; made by the tag workflow, run 44605378969, its twelfth use; release workflow run 44605455166): the latest full release until 4.0.0 is tagged.

## From the Status section of CLAUDE.md, moved with the preparation of 4.0.1 (2026-11-20)

The note on the publication of the minor release 2.3.0, moved word for word from the Status section to keep `CLAUDE.md` under its size limit when 4.0.1 was prepared; the Status section still names 2.3.0 in the list of releases and says where this note is.

**Version `2.3.0` is published** (D-245; 2026-11-18, the latest full release until 2.3.1; no release candidate; tag `v2.3.0` on `5104988`, made by the tag workflow, run 44238883189, its seventh use): a minor release with branching harnesses (D-243; `docs/ait/DESIGN_2.3_BRANCHING.md`; #255, #262 to #265 and pull request 7: `per_connector_group`, `core/branching.py`, `segments.csv` and the *Routing* sheet, `routing`, the editor's *Routing* table, legs and the join) and the owner's feedback of 2026-11-17 (the App Center page, #257; the first start on Home with the role question there, no tour, dialogs that fit and move freely, #260); no format change, the scripting interface is unchanged; splices come with format 3 in 3.0.0.

## From the Status section of CLAUDE.md, moved with the publication record of 4.0.1 (2026-11-20)

The note on the publication of the major release 4.0.0, moved word for word from the first item of the Status section when the publication record of 4.0.1 was written, as the note on 3.1.0 was moved with the publication record of 4.0.0, so that `CLAUDE.md` stays under its size limit; that item still names 4.0.0 in the list of releases and says where this note is.

The major release `4.0.0` (D-254; format 4 with a connector's row layout; format 4 frozen from its tag) was published on 2026-11-20 (annotated tag `v4.0.0` on `c0e0250`, the merge of #304; made by the tag workflow, run 44699479126, its thirteenth use; release workflow run 44699532086): the latest full release until 4.0.1 is tagged.

## From the Status section of CLAUDE.md, moved with the preparation of 4.1.0 (2026-11-20)

The note on the publication of the patch release 2.3.1, moved word for word from the Status section to keep `CLAUDE.md` under its size limit when 4.1.0 was prepared; the Status section still names 2.3.1 in the list of releases and says where this note is.

**Version `2.3.1` is published** (D-246; 2026-11-18, the latest full release until 2.4.0; no release candidate; tag `v2.3.1` on `764061f`, made by the tag workflow, run 44274980246, its eighth use): a patch release with the new logo (#269, which carries the draft #258; the owner's feedback of 2026-11-17 on Ubuntu's dark mode, the owner's consent of 2026-11-18): `gui/appicon.py`, `BRAND` in `gui/theme/tokens.py`, the SVGs, `tests/test_icon_contrast.py`; no format change, no change of behaviour.

## From the Status section of CLAUDE.md, moved with the publication record of 4.1.0 (2026-11-21)

The note on the publication of the patch release 4.0.1, moved word for word from the first item of the Status section when the publication record of 4.1.0 was written, as the note on 4.0.0 was moved with the publication record of 4.0.1, so that `CLAUDE.md` stays under its size limit; that item still names 4.0.1 in the list of releases and says where this note is.

The patch release `4.0.1` (D-255; every label format passes the export's self-check; no format change) was published on 2026-11-20 (annotated tag `v4.0.1` on `d45da91`, the merge of #308; made by the tag workflow, run 44741420907, its fourteenth use; release workflow run 44741460590): the latest full release until 4.1.0 is tagged.

## From the Status section of CLAUDE.md, moved with the preparation of 4.2.0 (2026-11-21)

The note on the publication of the minor release 2.4.0, moved word for word from the Status section to keep `CLAUDE.md` under its size limit when 4.2.0 was prepared, as the note on 2.3.1 was moved with the preparation of 4.1.0; the Status section still names 2.4.0 in the list of releases and says where this note is.

**Version `2.4.0` is published** (D-248; 2026-11-18, the latest full release until 3.0.0; no release candidate; tag `v2.4.0` on `85df2a9`, made by the tag workflow, run 44314858198, its ninth use): a minor release: a new project starts in `per_connector_group` (#271, D-247; the registry default stays `per_connector_pair`; the editor's notice once) and one order of revisions (#272, `core/vcs/versions.py`, R1 of 3.0.0, D-242); no format change.

## From the Status section of CLAUDE.md, moved with the publication record of 4.2.0 (2026-11-21)

The note on the publication of the minor release 4.1.0, moved word for word from the first item of the Status section when the publication record of 4.2.0 was written, as the note on 4.0.1 was moved with the publication record of 4.1.0, so that `CLAUDE.md` stays under its size limit; that item still names 4.1.0 in the list of releases and says where this note is.

The minor release `4.1.0` (D-257; the production sheet; no format change) was published on 2026-11-21 (annotated tag `v4.1.0` on `cb43f31`, the merge of #320; made by the tag workflow, run 44845357892, its fifteenth use; release workflow run 44845387838): the latest full release until 4.2.0 is tagged.

The note on version 3.0.0, moved word for word from the fourth item of the same section (the one that starts with *Not built*) for the same reason; the sentence there that names the notes moved out of it now names 3.0.0 too, and the first item still names 3.0.0 in the list of releases.

**Version `3.0.0` is published** (D-249; 2026-11-19, the latest full release until 3.0.1; major; no release candidate; tag `v3.0.0` on `711f204`, made by the tag workflow, run 44444461651, its tenth use): format 3 with versions MAJOR.MINOR.PATCH and the word *Version* (#274, #280; D-242), the harness plan (#277, #278, #279, #281, #284, #283), splices (#282, D-243 section 6), the end-to-end test and documents (#285); format 3 is frozen since the tag `v3.0.0`; a 2.x tool opens it read-only; the editor opens no browser.

## From the Status section of CLAUDE.md, moved with the preparation of 4.3.0 (2026-11-21)

The note on the publication of the patch release 3.0.1, moved word for word from the fourth item of the Status section (the one that starts with *Not built*) to keep `CLAUDE.md` under its size limit when 4.3.0 was prepared, as the note on 3.0.0 was moved with the publication record of 4.2.0; the sentence there that names the notes moved out of it now names 3.0.1 too, and the first item still names 3.0.1 in the list of releases.

**Version `3.0.1` is published** (D-252; 2026-11-19, the latest full release until 3.1.0; no release candidate; tag `v3.0.1` on `1c79beb`, made by the tag workflow, run 44545687219): a patch release with the fix of D-250 (#291): F1 shows the guide in a window of the program (`gui/guide_window.py`), *Open* of an exported file is *Copy path*, *Reveal in folder* hands only a folder to the file manager (`gui/folders.py`, the only user of `QDesktopServices`); no format change.

## From the Status section of CLAUDE.md, moved with the publication record of 4.3.0 (2026-11-22)

The note on the publication of the minor release 4.2.0, moved word for word from the first item of the Status section when the publication record of 4.3.0 was written, as the note on 4.1.0 was moved with the publication record of 4.2.0, so that `CLAUDE.md` stays under its size limit; that item still names 4.2.0 in the list of releases and says where this note is.

The minor release `4.2.0` (D-259; four electrical rules; no format change) was published on 2026-11-21 (annotated tag `v4.2.0` on `6848510`, the merge of #328; made by the tag workflow, run 44895952490, its sixteenth use; release workflow run 44895975583): the latest full release.

The note on version 3.1.0, moved word for word from the fourth item of the same section (the one that starts with *Not built*) for the same reason; the sentence there that names the notes moved out of it now names 3.1.0 too, and the first item still names 3.1.0 in the list of releases.

**Version `3.1.0` is published** (D-253; 2026-11-19, the latest full release until 4.0.0; no release candidate; tag `v3.1.0` on `3b183e1`, made by the tag workflow, run 44605378969): a minor release with `SEARCH`/`ISNUMBER` in the plan's search boxes (D-250, #290: `I2:I3` and `M2:M3`, in a conditional format only; every `.ods` turns regular expressions and wildcards off); no format change.

## From the Status section of CLAUDE.md, moved with the preparation of 4.4.0 (2026-11-23)

The note on version 4.0.0, moved word for word from the fourth item of the Status section (the one that starts with *Not built*) to keep `CLAUDE.md` under its size limit when 4.4.0 was prepared, as the note on 3.0.1 was moved with the preparation of 4.3.0; the sentence there that names the notes moved out of it now names 4.0.0 too, and the first item still names 4.0.0 in the list of releases.

**Version `4.0.0` is published** (D-254; 2026-11-20, the latest full release until 4.0.1; major; no release candidate; tag `v4.0.0` on `c0e0250`, made by the tag workflow, run 44699479126): format 4 with a connector's row layout (D-250, D-251, `docs/ait/DESIGN_4.0_ROW_LAYOUT.md`; #294 to #300): `RowLayout` on `Part.row_layout` and `Connector.row_layout`, `core/row_layout.py`, the three checks, `power-return-adjacent` on the face, the *Pin row* column, `pin-rows`, **Edit rows…**; the older names of 3.0.x are gone (`export.json` `format_version` 2, `harness.revision` removed); format 4 is frozen since the tag `v4.0.0`; a 3.x tool opens it read-only.

## From the Status section of CLAUDE.md, moved with the publication record of 4.4.0 (2026-11-23)

The note on the publication of the minor release 4.3.0, moved word for word from the first item of the Status section when the publication record of 4.4.0 was written, as the note on 4.2.0 was moved with the publication record of 4.3.0, so that `CLAUDE.md` stays under its size limit; that item still names 4.3.0 in the list of releases and says where this note is.

The minor release `4.3.0` (D-261; the review view; no format change) was published on 2026-11-22 (annotated tag `v4.3.0` on `20bf8f1`, the merge of #337; made by the tag workflow, run 45045461615, its seventeenth use; release workflow run 45045481035): the latest full release.

The note on version 4.0.1, moved word for word from the fourth item of the same section (the one that starts with *Not built*) for the same reason; the sentence there that names the notes moved out of it now names 4.0.1 too, and the first item still names 4.0.1 in the list of releases.

**Version `4.0.1` is published** (D-255; 2026-11-20, the latest full release until 4.1.0; no release candidate; tag `v4.0.1` on `d45da91`, made by the tag workflow, run 44741420907): a patch release with the fix of #306: the self-check of `export` (`core/outputs/verify.py`) words the labels in every label format (`compact`, `descriptive`, `custom` failed it since 1.15.0, D-198); no format change.

## From the Status section of CLAUDE.md, moved with the publication record of 4.4.1 (2026-11-23)

The note on the publication of the minor release 4.4.0, moved word for word from the first item of the Status section when the publication record of 4.4.1 was written, as the note on 4.3.0 was moved with the publication record of 4.4.0, so that `CLAUDE.md` stays under its size limit; that item still names 4.4.0 in the list of releases and says where this note is.

The minor release `4.4.0` (D-263; names and ports; no format change) was published on 2026-11-23 (annotated tag `v4.4.0` on `e6eddc0`, the merge of #348; made by the tag workflow, run 45121731874, its eighteenth use; release workflow run 45121757018): the latest full release until 4.4.1 is tagged.

The notes on versions 4.1.0 and 4.2.0, moved word for word from the fourth item of the same section (the one that starts with *Not built*) for the same reason; the sentence there that names the notes moved out of it now names 4.1.0 and 4.2.0 too, and the first item still names both in the list of releases.

**Version `4.1.0` is published** (D-257, the design D-256; 2026-11-21, the latest full release until 4.2.0; no release candidate; tag `v4.1.0` on `cb43f31`, made by the tag workflow, run 44845357892): a minor release with the production sheet (milestone E1, `docs/ait/DESIGN_4.1_PRODUCTION_SHEET.md`; #311 to #319): the sheet *Production* in the build workbook and the harness plan (`core/outputs/production.py`, `verify_production.py`), lengths that say *rear to rear*, the plan's harness sheet over several pages at a fixed scale, the label format `harness_device_connector` in which a new project starts (a 4.0.x tool refuses it), every shield group of a wire in the wire list and the cut list; no format change.

**Version `4.2.0` is published** (D-259, the design D-258; 2026-11-21, the latest full release until 4.3.0; no release candidate; tag `v4.2.0` on `6848510`, made by the tag workflow, run 44895952490): a minor release with four electrical rules (milestone E2, `docs/ait/DESIGN_4.2_ELECTRICAL_CHECKS.md`; #323 to #327): `pair-untwisted`, `signal-unshielded`, `level-conflict` and `wire-direction`, the settings `naming.pair_suffixes` and `segregation.level_pairs_to_separate` (empty by default, D-11), and the overall shield of a `single` type that shields overall; no format change.

## From the Status section of CLAUDE.md, moved with the publication record of 5.0.0 (2026-11-24)

The note on the publication of the patch release 4.4.1, moved word for word from the first item of the Status section when the publication record of 5.0.0 was written, as the note on 4.4.0 was moved with the publication record of 4.4.1, so that `CLAUDE.md` stays under its size limit; that item still names 4.4.1 in the list of releases and says where this note is.

The patch release `4.4.1` (D-265; the library review compares the ICD fields and the pin level; no format change) was published on 2026-11-23 (annotated tag `v4.4.1` on `27a3736`, the merge of #356; made by the tag workflow, run 45257507524, its nineteenth use, after run 45195929317 refused `43cefeb`, the merge of the preparation #352; release workflow run 45257560693): the latest full release until 5.0.0 is tagged.

The notes on versions 4.3.0 and 4.4.0, moved word for word from the fourth item of the same section (the one that starts with *Not built*) for the same reason; the sentence there that names the notes moved out of it now names 4.3.0 and 4.4.0 too, and the first item still names both in the list of releases.

**Version `4.3.0` is published** (D-261, the design D-260; 2026-11-22, the latest full release until 4.4.0; no release candidate; tag `v4.3.0` on `20bf8f1`, made by the tag workflow, run 45045461615): a minor release with the review view (milestone E3, `docs/ait/DESIGN_4.3_REVIEW_VIEW.md`; #331 to #336): a review checklist, the *Review* sheet and page, `release --ticked`, `explain DIR FINDING`; no format change.

**Version `4.4.0` is published** (D-263, the design D-262; 2026-11-23, the latest full release until 4.4.1; no release candidate; tag `v4.4.0` on `e6eddc0`, made by the tag workflow, run 45121731874): a minor release with names and ports (milestone E4, `docs/ait/DESIGN_4.4_NAMES_PORTS.md`; #340, #342 to #347): the opt-in settings `naming.far_device_names` (Generate gives an interface the port named after its far device, the verifier's `port_far_device`, the pairing reads the far device off a pin name) and `naming.signal_map` (a team's signal names renamed at import, also inside a port), and *Unassign* keeps the name of a fixed pin; no format change.
