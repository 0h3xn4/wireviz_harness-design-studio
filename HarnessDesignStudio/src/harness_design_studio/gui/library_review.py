# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The device library in the editor (D-240, pull request 4 of the design of 2.2.0,
`docs/ait/DESIGN_2.2_DEVICE_LIBRARY.md` section 3 item 5).

    links = LibraryLinks(ctl, person_folder=lambda: "/mnt/shared/library")
    links.refresh(notice=True)                   # the project's libraries and states, off the UI thread
    links.newer.connect(show_notice)             # the devices with a newer version in a library
    chip = LibraryChip(theme); chip.show_state(links.state("PCDU00"), links.info)
    message = review_flow(host, links.info.libraries, "PCDU00", links.info)
    added = plan_library_add(host, libraries, ["PCDU00"], count=1)   # asks when the ID is taken

What the window shows of the link between a project device and its library device: the words of
the states, the source line (library name, Git commit, file, *not committed*), the chip on a
device, the review dialog (*Take the library's version*, *Keep this project's*, *Save this
project's to the library…*) and the question when the ID of a library device is taken (add copies,
adopt, or add under another ID). Every change goes through `core.library_link` and the controller
as one undo step; nothing here writes the project. The libraries are read and the states worked
out in a helper thread (`background.JobRunner`), never on the UI thread.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core import copies
from harness_design_studio.core import library_link as ll
from harness_design_studio.core.commands import Op, Put
from harness_design_studio.core.edit import clone_with, zone_of_x
from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.ids import ID_RE
from harness_design_studio.core.library_git import NOT_COMMITTED, file_state, library_git
from harness_design_studio.core.model import Placement, Project, Unit, evolve
from harness_design_studio.core.ports import natural_key
from harness_design_studio.gui import strings
from harness_design_studio.gui.background import Job, JobRunner
from harness_design_studio.gui.controller import Delta, EditorController
from harness_design_studio.gui.devices_dialogs import _PlannerDialog
from harness_design_studio.gui.dialog_base import Dialog
from harness_design_studio.gui.notice import InlineNotice
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager, mark_mono
from harness_design_studio.gui.wrap_label import WrapLabel

# the states a person can review: the device differs from the library's, or has its ID only
REVIEWABLE = frozenset({ll.LIBRARY_CHANGED, ll.CHANGED_HERE, ll.NOT_FROM_LIBRARY})


# ---- what the libraries say about the project (no Qt) ------------------------------------------


@dataclass(frozen=True)
class LinkInfo:
    """The project's libraries and how its devices stand to them, worked out once in a helper
    thread: the states by device ID, the Git line of every library folder (`Git commit 1a2b3c4 on
    main`, "" outside Git) and the device files that differ from the library's last commit."""

    libraries: ll.ProjectLibraries
    states: dict[str, ll.LinkState] = field(default_factory=dict)
    git: dict[Path, str] = field(default_factory=dict)
    uncommitted: frozenset[Path] = frozenset()
    root: Path | None = None

    def state(self, unit_id: str) -> ll.LinkState | None:
        return self.states.get(unit_id)

    def newer(self) -> list[str]:
        """The library devices of which the project has a version that the library changed since
        (one name per library device, its copies counted with it)."""
        return sorted(
            {s.library_id for s in self.states.values() if s.state == ll.LIBRARY_CHANGED},
            key=natural_key,
        )

    def devices(self) -> list[ll.LibraryDevice]:
        """The library devices that can be added (one per ID; an ID in two libraries is left out:
        it is never chosen)."""
        out: dict[str, ll.LibraryDevice] = {}
        for dev in self.libraries.devices():
            if len(self.libraries.holders(dev.unit_id)) == 1:
                out.setdefault(dev.unit_id, dev)
        return list(out.values())

    def source(self, device: ll.LibraryDevice) -> str:
        return source_line(
            device, self.git.get(device.library.folder, ""), device.path in self.uncommitted
        )


# how a view asks the window for the state of a device: (its state, the facts it was worked out from)
LinkLookup = Callable[[str], tuple[ll.LinkState | None, LinkInfo | None]]


def resolve_links(
    project: Project,
    root: Path | None,
    person_folder: str,
    libraries: ll.ProjectLibraries | None = None,
) -> LinkInfo:
    """Read the project's libraries (unless `libraries` are given), the state of every device, the
    Git line of each library and which linked device files are not committed. Runs in a helper
    thread on a private copy of the project; reads only."""
    libs = (
        libraries
        if libraries is not None
        else ll.project_libraries(root, person_folder=person_folder or None)
    )
    if not libs.libraries:
        return LinkInfo(libs, root=root)
    states = {s.unit_id: s for s in ll.link_states(project, libs)}
    git = {lib.folder: library_git(lib.folder).note() for lib in libs.libraries}
    uncommitted = frozenset(
        s.device.path
        for s in states.values()
        if s.device is not None
        and s.state != ll.NOT_IN_PROJECT
        and git.get(s.device.library.folder)
        and file_state(s.device.library.folder, s.device.file) == NOT_COMMITTED
    )
    return LinkInfo(libs, states, git, uncommitted, root)


def state_words(state: str) -> str:
    """The state in plain words (`Library changed`)."""
    return strings.LINK_STATE_WORDS.get(state, state)


def source_line(device: ll.LibraryDevice, git: str, uncommitted: bool) -> str:
    """Where a library device comes from, in one line: `ACME devices, Git commit 1a2b3c4 on main,
    PCDU00.device.json, not committed` (no Git words outside Git)."""
    parts = [device.library.name, git, device.file, NOT_COMMITTED if uncommitted else ""]
    return ", ".join(p for p in parts if p)


def chip_text(state: ll.LinkState) -> str:
    """The words of the chip on a project device: `From ACME devices, PCDU00.device.json, up to
    date`."""
    dev = state.device
    if state.state in ll.LINKED_STATES and dev is not None:
        return strings.LIBCHIP_FROM.format(
            library=dev.library.name, file=dev.file_name, state=state.state
        )
    if state.state == ll.SOURCE_NOT_FOUND:
        file = state.record_id.partition(":")[2] or (dev.file_name if dev else state.library_id)
        return strings.LIBCHIP_NOT_FOUND.format(file=file)
    if state.state == ll.NOT_FROM_LIBRARY and dev is not None:
        return strings.LIBCHIP_NOT_FROM.format(device=state.library_id, library=dev.library.name)
    if state.state == ll.AMBIGUOUS:
        return strings.LIBCHIP_AMBIGUOUS.format(device=state.library_id)
    return state_words(state.state)


# ---- the project's libraries, kept up to date in a helper thread --------------------------------


class LibraryLinks(QObject):
    """The libraries of the open project and the state of its devices. `refresh()` reads the
    libraries again (a project opened, the list of libraries or the person's folder changed, a
    device saved to a library); an edit only works the states out again. `ready` follows every
    answer; `newer(ids)` follows the answer of `refresh(notice=True)` when a library has a newer
    version of a device of the project (the notice of a project that opens). Nothing is applied."""

    ready = Signal()
    newer = Signal(list)  # the library devices with a newer version (when a project opens)

    def __init__(self, ctl: EditorController, person_folder: Callable[[], str]) -> None:
        super().__init__()
        self.ctl, self.person_folder = ctl, person_folder
        self.jobs = JobRunner(ctl)
        self.jobs.done.connect(self._done)
        self.info: LinkInfo | None = None
        self.problem = ""
        self._generation = 0
        self._notice = False
        self._installs = ctl.state_token[0]
        ctl.changed.connect(self._changed)

    def state(self, unit_id: str) -> ll.LinkState | None:
        return self.info.state(unit_id) if self.info is not None else None

    def libraries(self) -> ll.ProjectLibraries:
        """The project's libraries as last read; read now when they were not yet (on demand,
        for a review or an add that the person asked for)."""
        if self.info is not None:
            return self.info.libraries
        return ll.project_libraries(self.ctl.root, person_folder=self.person_folder() or None)

    def refresh(self, *, notice: bool = False) -> None:
        """Read the project's libraries again and work out the states (in a helper thread)."""
        self._generation += 1
        self._notice = notice
        if self.ctl.state_token[0] != self._installs:  # another project: nothing is known yet
            self.info = None
        self._installs = self.ctl.state_token[0]
        root, folder = self.ctl.root, self.person_folder()
        if root is None and not folder:
            self.info = None
            self.ready.emit()
            return
        project = clone_with(self.ctl.project, [])
        self.jobs.start(
            "library-links", self._generation, lambda: resolve_links(project, root, folder)
        )

    def _changed(self, _delta: Delta) -> None:
        if self.ctl.state_token[0] != self._installs:  # another project: its own libraries
            self.refresh()
            return
        info = self.info
        if info is None or not info.libraries.libraries:
            return
        project, root, libs = clone_with(self.ctl.project, []), self.ctl.root, info.libraries
        self.jobs.start(
            "library-states",
            self._generation,
            lambda: resolve_links(project, root, "", libs),
        )

    def _done(self, job: Job) -> None:
        if job.key != self._generation:
            return  # an answer for libraries that were read again since
        if job.error is not None:
            self.problem = job.error
            return
        self.problem = ""
        self.info = job.value
        self.ready.emit()
        if job.kind == "library-links" and self._notice:
            self._notice = False
            found = self.info.newer() if self.info is not None else []
            if found:
                self.newer.emit(found)

    def wait(self, timeout_ms: int = 10000) -> bool:
        """Wait until the answers are in (tests and screenshots; the window never needs it)."""
        return self.jobs.wait_idle(timeout_ms)


def notice_text(found: Sequence[str]) -> str:
    """`1 device has a newer version in the library: PCDU00.`"""
    if len(found) == 1:
        return strings.NOTICE_NEWER_ONE.format(devices=found[0])
    return strings.NOTICE_NEWER_MANY.format(n=len(found), devices=", ".join(found))


# ---- the chip on a device ---------------------------------------------------------------------


class LibraryChip(QFrame):
    """One line on a device that comes from a library (the Inspector, the Devices tab): where it
    comes from and how it stands, with *Review…* when it differs. Hidden for a device that has
    nothing to do with the libraries."""

    reviewRequested = Signal(str)  # the project device

    def __init__(self, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("library-chip")
        self.setAccessibleName(strings.LIBCHIP_NAME)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.space(8))
        self.label = QLabel()
        self.label.setObjectName("library-chip-text")
        self.label.setWordWrap(True)
        self.label.setProperty("muted", True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.review = QPushButton(strings.LIBCHIP_REVIEW)
        self.review.setObjectName("library-chip-review")
        self.review.setToolTip(strings.LIBCHIP_REVIEW_TIP)
        self.review.clicked.connect(self._review)
        lay.addWidget(self.label, 1)
        lay.addWidget(self.review, 0, Qt.AlignmentFlag.AlignTop)
        self.unit_id = ""
        self.hide()

    def show_state(self, unit_id: str, state: ll.LinkState | None, info: LinkInfo | None) -> None:
        """Show how the device `unit_id` stands to the library (hidden when it has nothing to do
        with one)."""
        self.unit_id = unit_id
        if state is None or state.state == ll.NOT_IN_PROJECT:
            self.label.clear()
            self.hide()
            return
        text = chip_text(state)
        self.label.setText(text)
        tip = strings.LINK_STATE_TIPS.get(state.state, "")
        if state.device is not None and info is not None:
            tip = f"{strings.LIB_SOURCE_LINE.format(info.source(state.device))}\n{tip}"
        if state.message:
            tip = f"{tip}\n{state.message}"
        self.label.setToolTip(tip.strip())
        self.setAccessibleName(f"{strings.LIBCHIP_NAME}: {text}")
        self.review.setVisible(state.state in REVIEWABLE)
        self.review.setAccessibleName(strings.LIBCHIP_REVIEW_NAME.format(unit_id))
        self.show()

    def text(self) -> str:
        return self.label.text() if self.isVisibleTo(self.parentWidget() or self) else ""

    def _review(self) -> None:
        if self.unit_id:
            self.reviewRequested.emit(self.unit_id)


# ---- the review dialog -------------------------------------------------------------------------


class LibraryReviewDialog(Dialog):
    """The differences of a project device (and its copies) from its library device: one row per
    field (connector, pin, field, in this project, in the library, locked by), what taking the
    library's version touches, and what is kept. `choice` is "take" (with `plan`, made and checked
    here: a refusal shows its reason and keeps the dialog open), "save" or "keep" (also Esc)."""

    def __init__(
        self,
        parent: QWidget | None,
        theme: ThemeManager,
        diff: ll.LibraryDiff,
        source: str,
        take: Callable[[], ll.UpdatePlan],
        *,
        read_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.theme, self.diff, self._take = theme, diff, take
        self.choice = "keep"
        self.plan: ll.UpdatePlan | None = None
        self.setObjectName("library-review-dialog")
        self.setWindowTitle(strings.REVIEW_TITLE)
        self.setAccessibleName(strings.REVIEW_TITLE)
        lay = QVBoxLayout(self)
        lay.setSpacing(theme.space(8))
        base = diff.devices[0] if diff.devices else diff.library_id
        title = QLabel(strings.REVIEW_HEADING.format(device=base))
        title.setObjectName("library-review-heading")
        title.setProperty("heading", True)
        title.setWordWrap(True)
        lay.addWidget(title)
        self.source = QLabel(strings.REVIEW_SOURCE.format(source))
        self.source.setObjectName("library-review-source")
        self.source.setWordWrap(True)
        self.source.setProperty("muted", True)
        self.source.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        mark_mono(self.source)
        lay.addWidget(self.source)
        state = diff.state.state if diff.state is not None else ""
        lines = [strings.REVIEW_STATE.format(state_words(state))] if state else []
        if len(diff.devices) > 1:
            lines.append(strings.REVIEW_COPIES.format(", ".join(diff.devices[1:])))
        self.state = QLabel(" ".join(lines))
        self.state.setObjectName("library-review-state")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        many = len({r.device for r in diff.rows}) > 1
        columns = [
            Column("device", strings.REVIEW_COLUMNS[0], mono=True, width=80),
            Column("connector", strings.REVIEW_COLUMNS[1], mono=True, width=90),
            Column("pin", strings.REVIEW_COLUMNS[2], mono=True, width=50),
            Column("field", strings.REVIEW_COLUMNS[3], width=100),
            Column("here", strings.REVIEW_COLUMNS[4], mono=True, width=130),
            Column("library", strings.REVIEW_COLUMNS[5], mono=True, width=130),
            Column("locked", strings.REVIEW_COLUMNS[6], mono=True),
        ]
        if not many:
            columns = columns[1:]
        rows = [
            {
                "device": r.device,
                "connector": r.connector,
                "pin": r.pin,
                "field": r.field,
                "here": r.here,
                "library": r.library,
                "locked": r.locked_by,
            }
            for r in diff.rows
        ]
        self.model = DictTableModel(columns, rows, theme)
        self.table = TableView(self.model, theme, name=strings.REVIEW_TABLE)
        self.table.setObjectName("library-review-table")
        self.table.setToolTip(strings.REVIEW_TABLE)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(theme.px(160))
        self.table.setVisible(bool(rows))
        lay.addWidget(self.table, 1)
        self.no_rows = WrapLabel(strings.REVIEW_NO_ROWS)
        self.no_rows.setObjectName("library-review-same")
        self.no_rows.setProperty("muted", True)
        self.no_rows.setVisible(not rows)
        lay.addWidget(self.no_rows)
        words: list[str] = []
        if diff.impacts:
            words.append(strings.REVIEW_IMPACTS)
            words += [f"• {t}" for t in diff.impacts]
        if diff.notes:
            words.append(strings.REVIEW_NOTES)
            words += [f"• {t}" for t in diff.notes]
        self.impacts = WrapLabel("\n".join(words))
        self.impacts.setObjectName("library-review-impacts")
        self.impacts.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.impacts.setVisible(bool(words))
        lay.addWidget(self.impacts)
        self.notice = InlineNotice(theme)
        self.notice.setObjectName("library-review-notice")
        lay.addWidget(self.notice)
        row = QHBoxLayout()
        self.save_btn = QPushButton(strings.REVIEW_SAVE)
        self.save_btn.setObjectName("library-review-save")
        self.save_btn.setAccessibleName(strings.REVIEW_SAVE.rstrip("…"))
        self.save_btn.setToolTip(strings.REVIEW_SAVE_TIP)
        self.keep_btn = QPushButton(strings.REVIEW_KEEP)
        self.keep_btn.setObjectName("library-review-keep")
        self.keep_btn.setAccessibleName(strings.REVIEW_KEEP)
        self.keep_btn.setToolTip(strings.REVIEW_KEEP_TIP)
        self.keep_btn.setDefault(True)  # (Enter gives the answer that changes nothing)
        self.take_btn = QPushButton(strings.REVIEW_TAKE)
        self.take_btn.setObjectName("library-review-take")
        self.take_btn.setProperty("primary", True)
        self.take_btn.setAccessibleName(strings.REVIEW_TAKE)
        adopt = state == ll.NOT_FROM_LIBRARY
        self.take_btn.setToolTip(strings.REVIEW_ADOPT_TIP if adopt else strings.REVIEW_TAKE_TIP)
        if read_only:
            for b in (self.take_btn, self.save_btn):
                b.setEnabled(False)
                b.setToolTip(strings.WHY_READ_ONLY)
        row.addWidget(self.save_btn)
        row.addStretch(1)
        row.addWidget(self.keep_btn)
        row.addWidget(self.take_btn)
        lay.addLayout(row)
        self.take_btn.clicked.connect(self.take)
        self.keep_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self._save)
        self.resize(theme.px(760), theme.px(480))

    def take(self) -> bool:
        """*Take the library's version*: plan it; a refusal shows its reason and changes nothing."""
        try:
            plan = self._take()
        except (HarnessError, OSError) as exc:
            text = str(exc) if isinstance(exc, HarnessError) else str(exc.strerror or exc)
            self.notice.show_notice("error", strings.REVIEW_REFUSED.format(text))
            return False
        self.plan, self.choice = plan, "take"
        self.accept()
        return True

    def _save(self) -> None:
        self.choice = "save"
        self.accept()

    def reject(self) -> None:
        self.choice = "keep"  # (Esc and the window's close button change nothing)
        super().reject()


# ---- a library device whose ID the project has --------------------------------------------------


class TakenIdDialog(_PlannerDialog):
    """The ID of the library device is taken in the project: add copies of the project's device,
    adopt it (link it to the library and take the library's version), or add the library's device
    under another ID (an unlinked copy). `choice()` is "copy", "adopt" or "other"."""

    quiet_at_open = True

    def __init__(
        self,
        parent: QWidget | None,
        theme: ThemeManager,
        project: Project,
        error: ll.TakenIdError,
        count: int = 1,
    ) -> None:
        super().__init__(parent, theme, strings.TAKEN_TITLE, "library-taken-dialog")
        self.project, self.error = project, error
        uid = error.unit_id
        text = WrapLabel(f"{error}\n{strings.TAKEN_ASK}")
        text.setObjectName("library-taken-text")
        self.lay.addWidget(text)
        have = copies.device_count(project, uid) if uid in project.units else 1
        room = copies.MAX_DEVICES - have
        can_copy = uid in project.units and not copies.is_copy(project, uid) and room > 0
        self.copy = QRadioButton(strings.TAKEN_COPY.format(device=uid))
        self.copy.setObjectName("library-taken-copy")
        self.copy.setAccessibleName(strings.TAKEN_COPY.format(device=uid))
        self.copy.setToolTip(
            strings.TAKEN_COPY_TIP.format(device=uid) if can_copy else strings.TAKEN_COPY_FULL
        )
        self.copy.setEnabled(can_copy)
        self.number = QSpinBox()
        self.number.setObjectName("library-taken-number")
        self.number.setAccessibleName(strings.TAKEN_COPY_NUMBER)
        self.number.setToolTip(strings.TAKEN_COPY_NUMBER_TIP)
        self.number.setRange(1, max(room, 1))
        self.number.setValue(min(max(count, 1), max(room, 1)))
        self.adopt = QRadioButton(strings.TAKEN_ADOPT.format(device=uid))
        self.adopt.setObjectName("library-taken-adopt")
        self.adopt.setAccessibleName(strings.TAKEN_ADOPT.format(device=uid))
        self.adopt.setToolTip(
            strings.TAKEN_ADOPT_LINKED if error.linked else strings.TAKEN_ADOPT_TIP
        )
        self.adopt.setEnabled(not error.linked)
        self.other = QRadioButton(strings.TAKEN_OTHER)
        self.other.setObjectName("library-taken-other")
        self.other.setAccessibleName(strings.TAKEN_OTHER)
        self.other.setToolTip(strings.TAKEN_OTHER_TIP)
        self.new_id = QLineEdit(error.free_id)
        self.new_id.setObjectName("library-taken-id")
        self.new_id.setAccessibleName(strings.TAKEN_OTHER_ID)
        self.new_id.setToolTip(strings.TAKEN_OTHER_TIP)
        copy_row = QHBoxLayout()
        copy_row.addWidget(self.copy, 1)
        copy_row.addWidget(QLabel(strings.TAKEN_COPY_NUMBER))
        copy_row.addWidget(self.number)
        other_row = QHBoxLayout()
        other_row.addWidget(self.other, 1)
        other_row.addWidget(QLabel(strings.TAKEN_OTHER_ID))
        other_row.addWidget(self.new_id)
        self.lay.addLayout(copy_row)
        self.lay.addWidget(self.adopt)
        self.lay.addLayout(other_row)
        (self.copy if error.linked and can_copy else self.adopt if not error.linked else self.other).setChecked(True)  # fmt: skip
        for w in (self.copy, self.adopt, self.other):
            w.toggled.connect(self.revalidate)
        self.number.valueChanged.connect(self.revalidate)
        self.new_id.textChanged.connect(self._id_edited)
        self._finish(strings.TAKEN_OK)
        if self.ok is not None:
            self.ok.setAccessibleName(strings.TAKEN_OK)

    def _id_edited(self, _text: str) -> None:
        if not self.other.isChecked():
            self.other.setChecked(True)
        self.revalidate()

    def choice(self) -> str:
        if self.copy.isChecked():
            return "copy"
        if self.adopt.isChecked():
            return "adopt"
        return "other"

    def copies(self) -> int:
        return int(self.number.value())

    def chosen_id(self) -> str:
        return self.new_id.text().strip()

    def check(self) -> str | None:
        self.number.setEnabled(self.copy.isChecked())
        self.new_id.setEnabled(True)
        if self.choice() != "other":
            return None
        new = self.chosen_id()
        if not ID_RE.fullmatch(new):
            return strings.TAKEN_ID_BAD.format(new)
        if new.casefold() in {u.casefold() for u in self.project.units}:
            return strings.TAKEN_ID_USED.format(new)
        return None


# ---- the flows the windows share -------------------------------------------------------------


@dataclass
class Host:
    """What a flow needs from the window that runs it: where its dialogs belong, the theme, the
    controller, and the hooks that tests replace (`run_dialog`, `ask_choice`)."""

    parent: QWidget | None
    theme: ThemeManager
    ctl: EditorController
    run_dialog: Callable[[QDialog], int]
    ask_choice: Callable[[str, str, list[str]], int]


@dataclass
class LibraryAdd:
    """What adding library devices does, as one undo step: the ops, the devices added, the name
    of the step, the devices adopted, and notes."""

    ops: list[Op]
    ids: list[str]
    label: str
    adopted: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def message(self) -> str:
        words = []
        if self.ids:
            words.append(strings.LIB_ADDED.format(", ".join(self.ids)))
        words += [strings.TAKEN_ADOPTED.format(u) for u in self.adopted]
        return " ".join(words)


def plan_library_add(
    host: Host, libraries: ll.ProjectLibraries, names: Sequence[str], count: int = 1
) -> LibraryAdd | None:
    """Plan adding the library devices `names` (`count` of each) as one undo step, through
    `library_link.plan_add_device` with the record of the file. A taken ID asks what to do (add
    copies, adopt, or add under another ID). None when the person cancelled; a `HarnessError`
    says why it cannot be done. Nothing is changed here."""
    ctl = host.ctl
    root = ctl.root
    scratch = ctl.project
    out = LibraryAdd([], [], "")
    labels: list[str] = []
    for name in dict.fromkeys(names):
        try:
            add = ll.plan_add_device(scratch, libraries, name, count, root=root)
            ops, ids, notes, skipped = add.ops, list(add.unit_ids), list(add.notes), add.skipped
        except ll.TakenIdError as err:
            dlg = TakenIdDialog(host.parent, host.theme, scratch, err, count)
            if host.run_dialog(dlg) != QDialog.DialogCode.Accepted:
                dlg.deleteLater()
                return None
            choice, n, new_id = dlg.choice(), dlg.copies(), dlg.chosen_id()
            dlg.deleteLater()
            if choice == "copy":
                have = copies.device_count(scratch, err.unit_id)
                plan = copies.plan_copies(scratch, err.unit_id, have + n)
                ops, ids, notes, skipped = plan.ops, list(plan.new_ids), [], plan.skipped
                labels.append(strings.STEP_LIB_COPIES.format(", ".join(ids), err.unit_id))
            elif choice == "adopt":
                up = ll.plan_update_device(scratch, libraries, err.unit_id, adopt=True, root=root)
                ops, ids, notes, skipped = up.ops, [], list(up.notes), ()
                out.adopted.append(err.unit_id)
                labels.append(up.label)
            else:
                add = ll.plan_add_device(scratch, libraries, name, count, new_id, root=root)
                ops, ids, notes, skipped = add.ops, list(add.unit_ids), list(add.notes), add.skipped
        if skipped:
            notes.append(strings.REDUNDANT_SKIPPED.format(len(skipped), ", ".join(skipped)).strip())
        out.ops += ops
        out.ids += ids
        out.notes += [t for t in notes if t not in out.notes]
        scratch = clone_with(scratch, ops)
    if out.ids:
        labels.insert(0, strings.STEP_LIB_ADD_DEVICE.format(", ".join(out.ids)))
    out.label = labels[0] if labels else ""
    return out


def review_flow(
    host: Host,
    libraries: ll.ProjectLibraries,
    unit_id: str,
    info: LinkInfo | None = None,
) -> tuple[str, bool]:
    """Review the library's version of the project device `unit_id`: the dialog, then what the
    person chose (one undo step for *Take*, the file and the record for *Save*, nothing for
    *Keep*). Returns (the sentence to show, whether the library folder was written). A
    `HarnessError` says why the device cannot be compared."""
    ctl = host.ctl
    project, root = ctl.project, ctl.root
    diff = ll.library_diff(project, libraries, unit_id)
    dev = diff.device
    source = (
        info.source(dev)
        if info is not None
        else source_line(dev, library_git(dev.library.folder).note(), False)
    )
    adopt = diff.state is not None and diff.state.state == ll.NOT_FROM_LIBRARY
    base = diff.devices[0] if diff.devices else diff.library_id

    def take() -> ll.UpdatePlan:
        return ll.plan_update_device(ctl.project, libraries, base, adopt=adopt, root=root)

    dlg = LibraryReviewDialog(host.parent, host.theme, diff, source, take, read_only=ctl.read_only)
    host.run_dialog(dlg)
    choice, plan = dlg.choice, dlg.plan
    dlg.deleteLater()
    if choice == "take" and plan is not None:
        if not plan.ops:
            return strings.REVIEW_TAKEN_NONE.format(device=base), False
        if not ctl.run(plan.label, plan.ops):
            return "", False
        return strings.REVIEW_TAKEN.format(device=base), False
    if choice == "save":
        answer = host.ask_choice(
            strings.REVIEW_SAVE_TITLE,
            strings.REVIEW_SAVE_BODY.format(device=base, file=dev.file, library=dev.library.name),
            [strings.REVIEW_SAVE_OK, strings.CANCEL],
        )
        if answer != 0:
            return "", False
        saved = ll.plan_save_device(ctl.project, dev.library, base, replace=True, root=root)
        if saved.ops:
            ctl.run(strings.STEP_RECORD_LIBRARY.format(saved.file), saved.ops)
        words = strings.REVIEW_SAVED.format(device=base, file=saved.file, library=dev.library.name)
        return " ".join([words, *saved.notes]), True
    return strings.REVIEW_KEPT.format(device=base), False


def placed_at(project: Project, ops: list[Op], unit_id: str, x: float, y: float) -> list[Op]:
    """`ops` with the device `unit_id` put at (x, y) of the diagram (*Add here* of the diagram);
    its zone follows the place, as for a device added by hand."""
    out: list[Op] = []
    for op in ops:
        if isinstance(op, Put) and isinstance(op.obj, Placement) and op.obj.id == unit_id:
            op = Put("placements", Placement(id=unit_id, x=x, y=y))
        elif (
            isinstance(op, Put)
            and op.collection == "units"
            and isinstance(op.obj, Unit)
            and op.obj.id == unit_id
        ):
            op = Put("units", evolve(op.obj, zone=zone_of_x(project, x) or None))
        out.append(op)
    return out
