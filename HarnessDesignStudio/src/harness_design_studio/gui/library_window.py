# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The library window: a window of its own, beside the editor, with the devices and subsystems of the
library folder (workshop feedback M4, D-175).

    win = LibraryWindow(ctl, theme, settings, parent=main_window)
    win.set_folder("/mnt/shared/harness-library")      # the setting is kept by the main window
    win.show()

Left, a search field, a filter (devices / subsystems) and the list of what the folder holds. Right,
a preview: the connectors and pins of a device, or the devices and connections of a subsystem. Below,
*Add to project* (one undo step, never replaces anything) with the number of these devices, and
*Save selection to library…* (the devices selected in the project). Since 2.2.0 (D-240) each device
has a *Status* (how the device of the project with its ID stands to the library, worked out in a
helper thread), the preview names its source (library, Git commit, file, *not committed*), *Review
changes…* opens the review of a device that differs, and a taken ID asks what to do (add copies,
adopt, or add under another ID; `gui/library_review.py`). The window lists the libraries the
project names in its `device-libraries.json` (`library_link.project_libraries`, with a line that
names each and its path, and a *Library* column) and the person's library folder; a device of a
project library is added and compared with the project's libraries, a device of the person's
folder with that folder (`read_libraries`). Save writes into the person's folder. The window
shares the editor's
controller, so an addition is an ordinary edit with undo; it is not modal, follows the theme, and
keeps its own size and place (`library/geometry`), apart from the editor's layout. The folder is
read in a helper thread (it may be on a slow drive); nothing is written unless the person saves.
The headless logic is in `core.library_folder`, `core.subsystem_library` and `core.copies`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QModelIndex, QSettings, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.core import copies, library_folder, library_link, library_pointer
from harness_design_studio.core import subsystem_library as sl
from harness_design_studio.core.commands import Op
from harness_design_studio.core.edit import EditError, clone_with
from harness_design_studio.core.errors import HarnessError
from harness_design_studio.core.library_folder import LibraryConflict, LibraryEntry, LibraryScan
from harness_design_studio.core.model import Project
from harness_design_studio.gui import strings
from harness_design_studio.gui.background import Job, JobRunner
from harness_design_studio.gui.controller import EditorController
from harness_design_studio.gui.devices_dialogs import _PlannerDialog
from harness_design_studio.gui.dialog_base import Dialog, refit_on, run_dialog
from harness_design_studio.gui.icons import icon_button
from harness_design_studio.gui.library_review import (
    REVIEWABLE,
    Host,
    LinkInfo,
    plan_library_add,
    resolve_links,
    review_flow,
    state_words,
)
from harness_design_studio.gui.notice import InlineNotice
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager, mark_mono
from harness_design_studio.gui.wrap_label import WrapLabel

SETTINGS_FOLDER = "library/folder"
SETTINGS_GEOMETRY = "library/geometry"
SETTINGS_SPLIT = "library/split"

_COUNT = {
    "connectors": strings.LIB_N_CONNECTORS,
    "pins": strings.LIB_N_PINS,
    "devices": strings.LIB_N_DEVICES,
    "connections": strings.LIB_N_CONNECTIONS,
}


def _n(kind: str, n: int) -> str:
    one, many = _COUNT[kind]
    return (one if n == 1 else many).format(n)


PROJECT, PERSON = "project", "person"  # where a library of the window comes from


@dataclass(frozen=True)
class WindowLibrary:
    """A library folder the window lists: its name, where it comes from (`project`: named in the
    project's `device-libraries.json`; `person`: the person's library folder), the path as that
    source writes it, and what the folder holds."""

    folder: Path
    name: str
    origin: str
    path: str
    scan: LibraryScan


@dataclass
class WindowLibraries:
    """What the window reads in its helper thread: the libraries to list (the project's first, in
    their order, then the person's folder unless the project names it already), the project's
    libraries as the link sees them (`library_link.project_libraries`), and the sentences of what
    the project's list could not use (the file itself, a folder that cannot be read)."""

    libraries: list[WindowLibrary] = field(default_factory=list)
    project: library_link.ProjectLibraries = field(default_factory=library_link.ProjectLibraries)
    problems: list[str] = field(default_factory=list)

    def person(self) -> WindowLibrary | None:
        return next((lib for lib in self.libraries if lib.origin == PERSON), None)


def _same_folder(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a == b


def read_libraries(root: Path | None, person_folder: str) -> WindowLibraries:
    """The libraries of the window (no Qt; runs in a helper thread and reads only)."""
    project = library_link.project_libraries(root)
    paths: list[str] = []
    if root is not None:
        try:
            paths = library_pointer.read_pointer(root)
        except library_pointer.PointerError:
            paths = []  # project_libraries says why in its problems
    named = (
        dict(zip(library_pointer.library_folders(root, paths), paths, strict=True)) if root else {}
    )
    out = WindowLibraries(project=project)
    file_problems: set[str] = set()
    for lib in project.libraries:
        scan = library_folder.scan_folder(lib.folder)
        file_problems |= {f"{lib.folder.name}: {p}" for p in scan.problems}
        out.libraries.append(
            WindowLibrary(
                lib.folder, lib.name, PROJECT, named.get(lib.folder, str(lib.folder)), scan
            )
        )
    out.problems = [p for p in project.problems if p not in file_problems]
    if person_folder:
        folder = Path(person_folder)
        if not any(_same_folder(folder, lib.folder) for lib in out.libraries):
            scan = library_folder.scan_folder(folder)
            name = scan.name or folder.name or person_folder
            out.libraries.append(WindowLibrary(folder, name, PERSON, person_folder, scan))
    return out


def contents_of(entry: LibraryEntry) -> str:
    """The Contents cell: what the entry holds, in words."""
    if entry.kind == "device":
        return f"{_n('connectors', entry.connectors)}, {_n('pins', entry.pins)}"
    return (
        f"{_n('devices', entry.devices)}, {_n('connectors', entry.connectors)}, "
        f"{_n('connections', entry.connections)}"
    )


# ---- a device of the same ID is in the file already -------------------------------------------


class LibraryConflictDialog(Dialog):
    """ "RW1 is in the library already (in RW1.json) and differs in 2 pins": Replace, Save as RW1-2,
    or Cancel. `choice` is "replace", "new" or "cancel" (also when the window is closed)."""

    def __init__(self, parent: QWidget | None, conflict: LibraryConflict) -> None:
        super().__init__(parent)
        self.conflict = conflict
        self.choice = "cancel"
        self.setObjectName("library-conflict-dialog")
        self.setWindowTitle(strings.LIB_CONFLICT_TITLE)
        self.setAccessibleName(strings.LIB_CONFLICT_DIALOG)
        found = conflict.conflicts
        if len(found) == 1:
            c = found[0]
            text = strings.LIB_CONFLICT_ONE.format(
                id=c.unit_id, file=conflict.file, how=c.differs_in()
            )
            new_text = strings.LIB_CONFLICT_NEW_ONE.format(c.suggested_id)
        else:
            what = ", ".join(f"{c.unit_id} ({c.differs_in()})" for c in found)
            text = strings.LIB_CONFLICT_MANY.format(file=conflict.file, what=what)
            new_text = strings.LIB_CONFLICT_NEW_MANY
        lay = QVBoxLayout(self)
        self.text = QLabel(f"{text}\n{strings.LIB_CONFLICT_ASK}")
        self.text.setObjectName("library-conflict-text")
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        row = QHBoxLayout()
        row.addStretch(1)
        self.replace_btn = QPushButton(strings.LIB_CONFLICT_REPLACE)
        self.replace_btn.setObjectName("library-conflict-replace")
        self.replace_btn.setAccessibleName(strings.LIB_CONFLICT_REPLACE)
        self.replace_btn.setToolTip(strings.LIB_CONFLICT_REPLACE_TIP)
        self.new_btn = QPushButton(new_text)
        self.new_btn.setObjectName("library-conflict-new")
        self.new_btn.setAccessibleName(new_text)
        self.new_btn.setToolTip(strings.LIB_CONFLICT_NEW_TIP)
        self.cancel_btn = QPushButton(strings.CANCEL)
        self.cancel_btn.setObjectName("library-conflict-cancel")
        self.cancel_btn.setAccessibleName(strings.CANCEL)
        self.cancel_btn.setDefault(True)  # (the safe answer is the one Enter gives)
        for btn in (self.replace_btn, self.new_btn, self.cancel_btn):
            row.addWidget(btn)
        lay.addLayout(row)
        self.replace_btn.clicked.connect(lambda: self._answer("replace"))
        self.new_btn.clicked.connect(lambda: self._answer("new"))
        self.cancel_btn.clicked.connect(self.reject)

    def _answer(self, choice: str) -> None:
        self.choice = choice
        self.accept()


@dataclass
class DeviceSave:
    """What `save_devices_asking` did: the files, what was kept on the way, the new IDs when the
    devices were saved under others (`{"RW1": "RW1-2"}`)."""

    paths: list[Path]
    notes: list[str] = field(default_factory=list)
    new_ids: dict[str, str] = field(default_factory=dict)

    @property
    def names(self) -> str:
        """The names of the files written, for a message: `OBC.device.json, RW1.device.json`."""
        return ", ".join(p.name for p in self.paths)


def _paths(written: Path | list[Path]) -> list[Path]:
    return written if isinstance(written, list) else [written]


def save_devices_asking(
    parent: QWidget | None,
    run_dialog: Callable[[QDialog], int],
    save: Callable[..., Path | list[Path]],
) -> DeviceSave | None:
    """Save devices with `save(replace=..., new_ids=..., notes=...)`. When the file has a different
    device of the same ID, ask first (Replace / Save as new ID / Cancel). None when the person
    cancelled: nothing was written. Other errors are raised for the caller to show."""
    notes: list[str] = []
    try:
        return DeviceSave(_paths(save(notes=notes)), notes)
    except LibraryConflict as conflict:
        dlg = LibraryConflictDialog(parent, conflict)
        run_dialog(dlg)
        choice = dlg.choice
        dlg.deleteLater()
        if choice == "replace":
            return DeviceSave(_paths(save(replace=True, notes=notes)), notes)
        if choice == "new":
            ids = {c.unit_id: c.suggested_id for c in conflict.conflicts}
            return DeviceSave(_paths(save(new_ids=ids, notes=notes)), notes, ids)
        return None


# ---- save to the library --------------------------------------------------------------------


class SaveToLibraryDialog(_PlannerDialog):
    """Save the selected devices to the library folder: as devices, or as one subsystem with a
    name. The reason a save cannot be done shows under the fields; Save stays off until it can."""

    quiet_at_open = True

    def __init__(
        self,
        parent: QWidget | None,
        theme: ThemeManager,
        project: Project,
        unit_ids: list[str],
        folder: str,
        scan: LibraryScan | None = None,
    ) -> None:
        super().__init__(parent, theme, strings.LIB_SAVE_TITLE, "library-save-dialog")
        self.project, self.unit_ids, self.folder = project, list(unit_ids), folder
        # the file each device goes into (the one that holds it, else <ID>.device.json, D-240)
        self.targets = list(dict.fromkeys(library_folder.save_targets(scan, self.unit_ids)))
        self.lay.addWidget(QLabel(strings.LIB_SAVE_SELECTED.format(", ".join(self.unit_ids))))
        self.as_devices = QRadioButton(strings.LIB_SAVE_AS_DEVICES)
        self.as_devices.setObjectName("library-save-devices")
        self.as_devices.setAccessibleName(strings.LIB_SAVE_AS_DEVICES)
        self.as_devices.setToolTip(strings.LIB_SAVE_AS_DEVICES_TIP)
        self.as_subsystem = QRadioButton(strings.LIB_SAVE_AS_SUBSYSTEM)
        self.as_subsystem.setObjectName("library-save-subsystem")
        self.as_subsystem.setAccessibleName(strings.LIB_SAVE_AS_SUBSYSTEM)
        self.as_subsystem.setToolTip(strings.LIB_SAVE_AS_SUBSYSTEM_TIP)
        many = len(self.unit_ids) > 1
        (self.as_subsystem if many else self.as_devices).setChecked(True)
        self.lay.addWidget(QLabel(strings.LIB_SAVE_AS))
        self.lay.addWidget(self.as_devices)
        self.lay.addWidget(self.as_subsystem)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setObjectName("library-save-name")
        self.name.setAccessibleName(strings.LIB_SAVE_NAME)
        self.name.setToolTip(strings.LIB_SAVE_NAME_TIP)
        self.description = QLineEdit()
        self.description.setObjectName("library-save-description")
        self.description.setAccessibleName(strings.LIB_SAVE_DESCRIPTION)
        self.description.setToolTip(strings.LIB_SAVE_DESCRIPTION_TIP)
        form.addRow(strings.LIB_SAVE_NAME, self.name)
        form.addRow(strings.LIB_SAVE_DESCRIPTION, self.description)
        self.lay.addLayout(form)
        self.info = QLabel()
        self.info.setObjectName("library-save-info")
        self.info.setProperty("muted", True)
        self.info.setWordWrap(True)
        self.lay.addWidget(self.info)
        for w in (self.as_devices, self.as_subsystem):
            w.toggled.connect(self.revalidate)
        self.name.textChanged.connect(self.revalidate)
        self._finish(strings.LIB_SAVE_OK)
        if self.ok is not None:
            self.ok.setToolTip(strings.LIB_SAVE_OK_TIP)
            self.ok.setAccessibleName(strings.LIB_SAVE_OK)

    def is_subsystem(self) -> bool:
        return self.as_subsystem.isChecked()

    def check(self) -> str | None:
        subsystem = self.is_subsystem()
        self.name.setEnabled(subsystem)
        self.description.setEnabled(subsystem)
        kept = sl.connections_between(self.project, self.unit_ids)
        left = sl.left_out_connections(self.project, self.unit_ids)
        lines = []
        if subsystem:
            lines.append(strings.LIB_SAVE_KEPT.format(_n("connections", kept)))
        if left:
            lines.append(strings.LIB_SAVE_LEFT_OUT.format(_n("connections", left)))
        if not subsystem:
            many = len(self.targets) > 1
            text = strings.LIB_SAVE_TARGETS if many else strings.LIB_SAVE_TARGET
            lines.append(text.format(", ".join(self.targets)))
        if subsystem and self.name.text().strip():
            lines.append(
                strings.LIB_SAVE_FILE.format(
                    sl.default_file_name(self.name.text().strip()), self.folder
                )
            )
        self.info.setText(" ".join(lines))
        if not subsystem:
            return None
        name = self.name.text().strip()
        if not name:
            return strings.LIB_SAVE_NEEDS_NAME
        if (Path(self.folder) / sl.default_file_name(name)).exists():
            return strings.LIB_SAVE_EXISTS.format(sl.default_file_name(name))
        return None


# ---- the window -----------------------------------------------------------------------------


class LibraryWindow(QWidget):
    """The non-modal library window (see the module text)."""

    folderChangeRequested = Signal()
    added = Signal(list)  # the IDs of the devices that were added to the project
    libraryWritten = Signal()  # a device file of the folder was written (the editor reads it again)

    def __init__(
        self,
        ctl: EditorController,
        theme: ThemeManager,
        settings: QSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.ctl, self.theme, self.settings = ctl, theme, settings
        self.setObjectName("library-window")
        self.setWindowTitle(strings.LIB_TITLE)
        self.setAccessibleName(strings.LIB_TITLE)
        self.run_dialog: Callable[[QDialog], int] = run_dialog
        self.opener: Callable[[QUrl], bool] = QDesktopServices.openUrl  # a part's link (3.0.0)
        self.ask_choice: Callable[[str, str, list[str]], int] = self._ask_choice
        # the states of the devices by where their library comes from (D-240): the project's
        # libraries, and the person's folder on its own
        self.links: dict[str, LinkInfo] = {}
        self._generation = 0  # the reading of the libraries that is shown
        self._installs = ctl.state_token[0]  # the project the libraries were read for
        self.jobs = JobRunner(ctl)
        self.jobs.done.connect(self._job_done)
        self.folder = str(settings.value(SETTINGS_FOLDER, "") or "")
        self.read: WindowLibraries | None = None  # None until the first reading is in
        self._origin: dict[str, WindowLibrary] = {}  # the library of each entry, by its key
        self._entries: list[LibraryEntry] = []
        self.entry: LibraryEntry | None = None
        self.entry_data: dict[str, Any] | None = None
        self._shown_once = False
        self._shown: list[LibraryEntry] = []
        self._build()
        ctl.selectionChanged.connect(self._update_buttons)
        ctl.stateChanged.connect(self._update_buttons)
        ctl.changed.connect(lambda _d: self._update_buttons())
        ctl.changed.connect(lambda _d: self._project_changed())
        self.refresh()

    # ---- building -----------------------------------------------------------------------------
    def _build(self) -> None:
        theme = self.theme
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.space(12), theme.space(12), theme.space(12), theme.space(12))
        outer.setSpacing(theme.space(8))
        head = QHBoxLayout()
        head.addWidget(QLabel(strings.LIB_FOLDER_LABEL))
        self.folder_label = QLabel()
        self.folder_label.setObjectName("library-folder")
        self.folder_label.setAccessibleName(strings.LIB_FOLDER_LABEL)
        self.folder_label.setToolTip(strings.LIB_FOLDER_TIP)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        mark_mono(self.folder_label)
        head.addWidget(self.folder_label, 1)
        self.change_btn = QPushButton()
        self.change_btn.setObjectName("library-change")
        icon_button(
            self.change_btn, "folder-open", theme, strings.LIB_CHANGE_TIP, text=strings.LIB_CHANGE
        )
        self.change_btn.clicked.connect(self.folderChangeRequested.emit)
        self.refresh_btn = QPushButton()
        self.refresh_btn.setObjectName("library-refresh")
        icon_button(
            self.refresh_btn,
            "refresh",
            theme,
            strings.LIB_REFRESH_TIP,
            "F5",
            text=strings.LIB_REFRESH,
        )
        self.refresh_btn.clicked.connect(self.refresh)
        head.addWidget(self.change_btn)
        head.addWidget(self.refresh_btn)
        outer.addLayout(head)
        # the libraries the project names in device-libraries.json, each with its source (D-240)
        named = QHBoxLayout()
        named.addWidget(QLabel(strings.LIB_PROJECT_LABEL))
        self.project_label = QLabel()
        self.project_label.setObjectName("library-project-libraries")
        self.project_label.setAccessibleName(strings.LIB_PROJECT_LABEL)
        self.project_label.setToolTip(strings.LIB_PROJECT_TIP)
        self.project_label.setWordWrap(True)
        self.project_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        named.addWidget(self.project_label, 1)
        outer.addLayout(named)
        self.folder_notice = InlineNotice(theme)
        self.folder_notice.setObjectName("library-folder-notice")
        outer.addWidget(self.folder_notice)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setObjectName("library-split")
        split.setChildrenCollapsible(False)
        self.split = split
        # the list
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName("library-search")
        self.search.setAccessibleName(strings.LIB_SEARCH_NAME)
        self.search.setToolTip(strings.LIB_SEARCH_TIP)
        self.search.setPlaceholderText(strings.LIB_SEARCH_PLACEHOLDER)
        self.search.setClearButtonEnabled(True)
        self.kind = QComboBox()
        self.kind.setObjectName("library-kind")
        self.kind.setAccessibleName(strings.LIB_KIND_NAME)
        self.kind.setToolTip(strings.LIB_KIND_TIP)
        for key, text in (
            ("all", strings.LIB_KIND_ALL),
            ("device", strings.LIB_KIND_DEVICES),
            ("subsystem", strings.LIB_KIND_SUBSYSTEMS),
        ):
            self.kind.addItem(text, key)
        row.addWidget(self.search, 1)
        row.addWidget(self.kind)
        lv.addLayout(row)
        self.list_model = DictTableModel(
            [
                Column("kind", strings.LIB_COLUMNS[0], width=80),
                Column("id", strings.LIB_COLUMNS[1], mono=True, width=70),
                Column("name", strings.LIB_COLUMNS[2], width=160),
                Column("status", strings.LIB_COLUMN_STATUS, width=120, tooltip="status_tip"),
                Column("library", strings.LIB_COLUMN_LIBRARY, width=120, tooltip="library_tip"),
                Column("contents", strings.LIB_COLUMNS[3], width=190),
                Column("file", strings.LIB_COLUMN_FILE, mono=True),
            ],
            [],
            theme,
        )
        self.list = TableView(self.list_model, theme, name=strings.LIB_LIST_NAME)
        self.list.setObjectName("library-list")
        self.list.setToolTip(strings.LIB_LIST_TIP)
        self.list.setSelectionBehavior(TableView.SelectionBehavior.SelectRows)
        self.list.setSelectionMode(TableView.SelectionMode.SingleSelection)
        self.list.horizontalHeader().setStretchLastSection(True)
        self.empty_title = (
            WrapLabel()
        )  # (it lies in a splitter pane, which asks for no height for width)
        self.empty_title.setObjectName("library-empty-title")
        self.empty_title.setProperty("heading", True)
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint = WrapLabel()
        self.empty_hint.setObjectName("library-empty-hint")
        self.empty_hint.setProperty("muted", True)
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_choose = QPushButton(strings.LIB_EMPTY_CHOOSE)
        self.empty_choose.setObjectName("library-empty-choose")
        self.empty_choose.setAccessibleName(strings.LIB_EMPTY_CHOOSE.rstrip("…"))
        self.empty_choose.setToolTip(strings.A_LIBRARY_FOLDER_TIP)
        self.empty_choose.clicked.connect(self.folderChangeRequested.emit)
        empty = QWidget()
        empty.setObjectName("library-empty")
        ev = QVBoxLayout(empty)
        ev.addStretch(1)
        ev.addWidget(self.empty_title)
        ev.addWidget(self.empty_hint)
        ev.addWidget(self.empty_choose, 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addStretch(2)
        self.list_stack = QStackedWidget()
        self.list_stack.addWidget(self.list)
        self.list_stack.addWidget(empty)
        lv.addWidget(self.list_stack, 1)
        split.addWidget(left)
        # the preview
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.preview_title = QLabel(strings.LIB_PREVIEW_NONE)
        self.preview_title.setObjectName("library-preview-title")
        self.preview_title.setProperty("title", True)
        self.preview_title.setWordWrap(True)
        self.preview_title.setAccessibleName(strings.LIB_PREVIEW_NAME)
        self.preview_text = QLabel()
        self.preview_text.setObjectName("library-preview-text")
        self.preview_text.setWordWrap(True)
        self.preview_text.setProperty("muted", True)
        self.preview_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.source_label = QLabel()  # library, Git commit, file, "not committed" (D-240)
        self.source_label.setObjectName("library-source")
        self.source_label.setWordWrap(True)
        self.source_label.setProperty("muted", True)
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        mark_mono(self.source_label)
        self.pin_model = DictTableModel(
            [
                Column("connector", strings.LIB_PREVIEW_PIN_COLUMNS[0], mono=True),
                Column("pin", strings.LIB_PREVIEW_PIN_COLUMNS[1], mono=True),
                Column("signal", strings.LIB_PREVIEW_PIN_COLUMNS[2], mono=True),
                Column("function", strings.LIB_PREVIEW_PIN_COLUMNS[3]),
            ],
            [],
            theme,
        )
        self.pin_table = TableView(self.pin_model, theme, name=strings.LIB_PREVIEW_TABLE_PINS)
        self.pin_table.setObjectName("library-preview-pins")
        self.pin_table.horizontalHeader().setStretchLastSection(True)
        self.sub_model = DictTableModel(
            [
                Column("kind", strings.LIB_PREVIEW_SUB_COLUMNS[0]),
                Column("item", strings.LIB_PREVIEW_SUB_COLUMNS[1], mono=True),
                Column("detail", strings.LIB_PREVIEW_SUB_COLUMNS[2]),
            ],
            [],
            theme,
        )
        self.sub_table = TableView(self.sub_model, theme, name=strings.LIB_PREVIEW_TABLE_SUB)
        self.sub_table.setObjectName("library-preview-subsystem")
        self.sub_table.horizontalHeader().setStretchLastSection(True)
        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.pin_table)
        self.preview_stack.addWidget(self.sub_table)
        # the parts of a device with their web links (format 3, design of 3.0.0 section 10)
        self.part_model = DictTableModel(
            [
                Column("part", strings.LIB_PREVIEW_PART_COLUMNS[0], mono=True, width=130),
                Column("description", strings.LIB_PREVIEW_PART_COLUMNS[1], width=180),
                Column("link", strings.LIB_PREVIEW_PART_COLUMNS[2], mono=True),
            ],
            [],
            theme,
        )
        self.part_table = TableView(self.part_model, theme, name=strings.LIB_PREVIEW_TABLE_PARTS)
        self.part_table.setObjectName("library-preview-parts")
        self.part_table.setToolTip(strings.LIB_PREVIEW_PARTS_TIP)
        self.part_table.horizontalHeader().setStretchLastSection(True)
        self.part_table.setMaximumHeight(theme.px(130))
        self.part_table.activated.connect(self._part_activated)
        self.part_table.hide()
        rv.addWidget(self.preview_title)
        rv.addWidget(self.preview_text)
        rv.addWidget(self.source_label)
        rv.addWidget(self.preview_stack, 1)
        rv.addWidget(self.part_table)
        split.addWidget(right)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 5)
        outer.addWidget(split, 1)

        self.result_notice = InlineNotice(theme)
        self.result_notice.setObjectName("library-result-notice")
        outer.addWidget(self.result_notice)
        buttons = QHBoxLayout()
        self.number = QSpinBox()
        self.number.setObjectName("library-number")
        self.number.setAccessibleName(strings.LIB_NUMBER)
        self.number.setToolTip(strings.LIB_NUMBER_TIP)
        self.number.setRange(1, copies.MAX_DEVICES)
        self.number.setValue(1)
        buttons.addWidget(QLabel(strings.LIB_NUMBER))
        buttons.addWidget(self.number)
        buttons.addStretch(1)
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("library-save")
        icon_button(self.save_btn, "export", theme, strings.LIB_SAVE_TIP, text=strings.LIB_SAVE)
        self.add_btn = QPushButton()
        self.add_btn.setObjectName("library-add")
        self.add_btn.setProperty("primary", True)
        icon_button(self.add_btn, "plus", theme, strings.LIB_ADD_TIP, "Enter", text=strings.LIB_ADD)
        self.review_btn = QPushButton(strings.LIB_REVIEW)
        self.review_btn.setObjectName("library-review")
        self.review_btn.setAccessibleName(strings.LIB_REVIEW.rstrip("…"))
        self.review_btn.setToolTip(strings.LIB_REVIEW_NONE)
        self.close_btn = QPushButton(strings.LIB_CLOSE)
        self.close_btn.setObjectName("library-close")
        self.close_btn.setAccessibleName(strings.LIB_CLOSE)
        self.close_btn.setToolTip(strings.LIB_CLOSE_TIP)
        buttons.addWidget(self.review_btn)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.close_btn)
        outer.addLayout(buttons)

        self.save_btn.clicked.connect(self.save_flow)
        self.review_btn.clicked.connect(self.review_flow)
        self.add_btn.clicked.connect(self.add_flow)
        self.close_btn.clicked.connect(self.close)
        self.search.textChanged.connect(lambda _t: self._fill_list())
        self.kind.currentIndexChanged.connect(lambda _i: self._fill_list())
        self.list.selectionModel().currentRowChanged.connect(self._row_changed)
        self.list.activated.connect(lambda _i: self.add_flow())
        find = QAction(self)
        find.setShortcut(QKeySequence("Ctrl+F"))
        find.triggered.connect(self._focus_search)
        self.addAction(find)
        leave = QAction(self)
        leave.setShortcut(QKeySequence("Esc"))
        leave.triggered.connect(self.close)
        self.addAction(leave)
        again = QAction(self)
        again.setShortcut(QKeySequence("F5"))
        again.triggered.connect(self.refresh)
        self.addAction(again)
        self.setTabOrder(self.search, self.kind)
        self.setTabOrder(self.kind, self.list)
        self.resize(theme.px(1120), theme.px(620))
        self._show_empty(strings.LIB_EMPTY_NO_FOLDER, strings.LIB_EMPTY_NO_FOLDER_HINT, True)

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    # ---- the libraries ----------------------------------------------------------------------------
    def set_folder(self, folder: str) -> None:
        """Use another library folder of the person ('' for none) and read the libraries again."""
        self.folder = folder
        self.refresh()

    @property
    def scan(self) -> LibraryScan | None:
        """What the person's library folder holds (None while it is not read, or none is set)."""
        lib = self.read.person() if self.read is not None else None
        return lib.scan if lib is not None else None

    def refresh(self) -> None:
        """Read the project's libraries and the person's folder again (in a helper thread)."""
        self.folder_label.setText(self.folder or strings.LIB_FOLDER_NONE)
        self.folder_label.setProperty("muted", not self.folder)
        self.result_notice.clear()
        self.entry_data = None  # read again with the libraries
        self._generation += 1
        self._installs = self.ctl.state_token[0]
        root = self.ctl.root
        self.refresh_btn.setEnabled(bool(self.folder) or root is not None)
        self.links = {}
        if not self.folder and root is None:
            self.read = None
            self._origin, self._entries = {}, []
            self._show_project_libraries()
            self._fill_list()
            return
        folder = self.folder
        self.jobs.start("library-scan", self._generation, lambda: read_libraries(root, folder))

    def _project_changed(self) -> None:
        """An edit works the states out again; another project reads its own libraries."""
        if self.ctl.state_token[0] != self._installs:
            self.refresh()
        else:
            self._start_states()

    def _job_done(self, job: Job) -> None:
        if job.kind == "library-scan":
            if job.key != self._generation:
                return  # an answer for libraries that were read again since
            if job.error is not None:
                scan = LibraryScan(Path(self.folder), error=job.error)
                person = WindowLibrary(Path(self.folder), "", PERSON, self.folder, scan)
                self.read = WindowLibraries([person] if self.folder else [])
                if not self.folder:
                    self.read.problems.append(job.error)
            else:
                self.read = job.value
            self._scan_ready()
        elif job.kind == "library-entry":
            if self.entry is None or job.key != self.entry.key:
                return
            self._entry_ready(job)
        elif job.kind == "library-states":
            if job.key != self._generation or job.error is not None:
                return
            self.links = job.value
            self._fill_list(states_only=True)
            self._show_source()

    # ---- the states of the devices (D-240) ------------------------------------------------------
    def library_of(self, entry: LibraryEntry | None) -> WindowLibrary | None:
        """The library an entry of the list comes from."""
        return self._origin.get(entry.key) if entry is not None else None

    def _group(self, origin: str) -> library_link.ProjectLibraries | None:
        """The libraries a device is added from, compared with and reviewed against: the project's
        libraries for a device of one of them; the person's folder on its own for a device of it
        (when the project names no library, that is the editor's library too)."""
        read = self.read
        if read is None:
            return None
        if origin == PROJECT:
            return read.project if read.project.libraries else None
        person = read.person()
        if person is None or person.scan.error:
            return None
        return library_link.libraries_from_scan(person.scan, self.ctl.root)

    def libraries(self, entry: LibraryEntry | None = None) -> library_link.ProjectLibraries | None:
        """The libraries of an add or a review of `entry` (the chosen one by default); None while
        they are not read."""
        lib = self.library_of(entry if entry is not None else self.entry)
        return self._group(lib.origin) if lib is not None else None

    def _start_states(self) -> None:
        """Work out how the project's devices stand to each group of libraries (in the helper
        thread)."""
        groups = {o: g for o in (PROJECT, PERSON) if (g := self._group(o)) is not None}
        if not groups:
            return
        project, root = clone_with(self.ctl.project, []), self.ctl.root

        def work() -> dict[str, LinkInfo]:
            return {o: resolve_links(project, root, "", libs) for o, libs in groups.items()}

        self.jobs.start("library-states", self._generation, work)

    def state_of(self, entry: LibraryEntry | None) -> library_link.LinkState | None:
        lib = self.library_of(entry)
        if entry is None or lib is None or entry.kind != "device":
            return None
        info = self.links.get(lib.origin)
        return info.state(entry.id) if info is not None else None

    def _show_source(self) -> None:
        entry = self.entry
        lib = self.library_of(entry)
        info = self.links.get(lib.origin) if lib is not None else None
        dev = None
        if entry is not None and lib is not None and entry.kind == "device" and info is not None:
            dev = next(
                (
                    d
                    for d in info.libraries.holders(entry.id)
                    if d.file == entry.file and _same_folder(d.library.folder, lib.folder)
                ),
                None,
            )
        self.source_label.setText(
            strings.LIB_SOURCE_LINE.format(info.source(dev)) if dev is not None and info else ""
        )
        self.source_label.setVisible(dev is not None)
        self._update_buttons()

    def _show_project_libraries(self) -> None:
        """The line of the project's libraries: each with its name and its path."""
        read = self.read
        named = [lib for lib in read.libraries if lib.origin == PROJECT] if read else []
        if named:
            text = "; ".join(
                strings.LIB_PROJECT_ITEM.format(name=x.name, path=x.path) for x in named
            )
        elif self.ctl.root is None:
            text = strings.LIB_PROJECT_NO_PROJECT
        else:
            text = strings.LIB_PROJECT_NONE
        self.project_label.setText(text)
        self.project_label.setProperty("muted", not named)

    def _scan_ready(self) -> None:
        read = self.read
        if read is None:
            return
        self._show_project_libraries()
        many = len(read.libraries) > 1
        errors = [lib.scan.error for lib in read.libraries if lib.scan.error] + read.problems
        damaged = [
            f"{lib.name}: {p}" if many else str(p)
            for lib in read.libraries
            if not lib.scan.error
            for p in lib.scan.problems
        ]
        if errors:
            details = errors[1:] + damaged
            self.folder_notice.show_notice("error", errors[0], details=details[:8] or None)
        elif damaged:
            n = len(damaged)
            self.folder_notice.show_notice(
                "warning",
                strings.LIB_DAMAGED_ONE if n == 1 else strings.LIB_DAMAGED.format(n),
                details=damaged[:8] + ([f"… +{n - 8}"] if n > 8 else []),
            )
        else:
            self.folder_notice.clear()
        self._origin, self._entries = {}, []
        for k, lib in enumerate(read.libraries):
            if lib.scan.error:
                continue
            for e in lib.scan.entries:
                # the person's folder keeps the keys of its scan; a project library's are its own
                entry = e if lib.origin == PERSON else replace(e, key=f"library-{k}:{e.key}")
                self._origin[entry.key] = lib
                self._entries.append(entry)
        self.links = {}
        self._fill_list()
        self._start_states()

    # ---- the list ---------------------------------------------------------------------------------
    def _wanted(self) -> list[LibraryEntry]:
        kind = str(self.kind.currentData())
        words = self.search.text().lower().split()
        out = []
        for e in self._entries:
            if kind != "all" and e.kind != kind:
                continue
            lib = self._origin[e.key]
            hay = f"{e.id} {e.name} {e.description} {e.subsystem} {e.file} {lib.name}".lower()
            if all(w in hay for w in words):
                out.append(e)
        return out

    def _library_cells(self, entry: LibraryEntry) -> tuple[str, str]:
        lib = self._origin[entry.key]
        tip = strings.LIB_FROM_PROJECT if lib.origin == PROJECT else strings.LIB_FROM_PERSON
        return lib.name, tip.format(name=lib.name, path=lib.path)

    def _fill_list(self, states_only: bool = False) -> None:
        wanted = self._wanted()
        self._shown = wanted
        keep = self.entry.key if self.entry is not None else None
        rows = [
            {
                "kind": strings.LIB_KIND_DEVICE
                if e.kind == "device"
                else strings.LIB_KIND_SUBSYSTEM,
                "id": e.id,
                "name": e.name,
                "status": self._status(e)[0],
                "status_tip": self._status(e)[1],
                "library": self._library_cells(e)[0],
                "library_tip": self._library_cells(e)[1],
                "contents": contents_of(e),
                "file": e.file,
                "key": e.key,
            }
            for e in wanted
        ]
        shown = [r.get("key") if isinstance(r, dict) else None for r in self.list_model.rows()]
        same = shown == [r["key"] for r in rows]
        if states_only and rows and same:
            self.list_model.update_rows(rows)  # (the states arrived: the selection stays)
            self._update_buttons()
            return
        self.list_model.set_rows(rows)
        read = self.read
        if wanted:
            self.list_stack.setCurrentIndex(0)
            row = next((i for i, e in enumerate(wanted) if e.key == keep), 0)
            self.list.selectRow(row)
            self._select(wanted[row])
        else:
            self._select(None)
            if read is None or not read.libraries:
                if read is not None and read.problems:
                    self._show_empty(
                        strings.LIB_EMPTY_UNREADABLE, strings.LIB_EMPTY_UNREADABLE_HINT, True
                    )
                else:
                    self._show_empty(
                        strings.LIB_EMPTY_NO_FOLDER, strings.LIB_EMPTY_NO_FOLDER_HINT, True
                    )
            elif all(lib.scan.error for lib in read.libraries):
                self._show_empty(
                    strings.LIB_EMPTY_UNREADABLE, strings.LIB_EMPTY_UNREADABLE_HINT, True
                )
            elif self._entries:
                self._show_empty(strings.LIB_EMPTY_NOMATCH, strings.LIB_EMPTY_NOMATCH_HINT, False)
            elif len(read.libraries) > 1:
                self._show_empty(strings.LIB_EMPTY_LIBRARIES, strings.LIB_EMPTY_FOLDER_HINT, False)
            else:
                self._show_empty(strings.LIB_EMPTY_FOLDER, strings.LIB_EMPTY_FOLDER_HINT, False)
        self._update_buttons()

    def _status(self, entry: LibraryEntry) -> tuple[str, str]:
        """The Status cell of an entry and its tooltip ("" for a subsystem, or before the states
        are worked out)."""
        state = self.state_of(entry)
        if state is None:
            lib = self.library_of(entry)
            if entry.kind == "device" and lib is not None and lib.origin in self.links:
                return state_words(library_link.NOT_IN_PROJECT), strings.LINK_STATE_TIPS[
                    library_link.NOT_IN_PROJECT
                ]
            return "", ""
        tip = strings.LINK_STATE_TIPS.get(state.state, "")
        if state.unit_id != entry.id or state.message:
            tip = " ".join(t for t in (tip, state.message) if t)
        return state_words(state.state), tip

    def _show_empty(self, title: str, hint: str, choose: bool) -> None:
        self.empty_title.setText(title)
        self.empty_hint.setText(hint)
        self.empty_choose.setVisible(choose)
        self.list_stack.setCurrentIndex(1)

    def _row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        source = self.list.proxy.mapToSource(current)
        shown = self._shown
        if 0 <= source.row() < len(shown):
            self._select(shown[source.row()])

    def current_entry(self) -> LibraryEntry | None:
        return self.entry

    def select_entry(self, key: str) -> bool:
        """Choose the entry with this key in the list (for tests and after a save)."""
        for i, e in enumerate(self._shown):
            if e.key == key:
                self.list.selectRow(
                    self.list.proxy.mapFromSource(self.list_model.index(i, 0)).row()
                )
                self._select(e)
                return True
        return False

    # ---- the preview ------------------------------------------------------------------------------
    def _select(self, entry: LibraryEntry | None) -> None:
        same = entry is not None and self.entry is not None and entry.key == self.entry.key
        if same and self.entry_data is not None:
            return
        self.entry, self.entry_data = entry, None
        self.result_notice.clear()
        if entry is None:
            self.preview_title.setText(strings.LIB_PREVIEW_NONE)
            self.preview_text.setText("")
            self._show_source()
            self.pin_model.set_rows([])
            self.sub_model.set_rows([])
            self._update_buttons()
            return
        self.preview_title.setText(
            f"{entry.id}  {entry.name}".strip() if entry.kind == "device" else entry.name
        )
        self.preview_text.setText(strings.LIB_PREVIEW_LOADING)
        self.pin_model.set_rows([])
        self.sub_model.set_rows([])
        self.part_model.set_rows([])
        self.part_table.hide()
        lib = self.library_of(entry)
        folder = lib.folder if lib is not None else Path(self.folder)

        def load() -> dict[str, Any]:
            return library_folder.load_entry(folder, entry)

        self.jobs.start("library-entry", entry.key, load)
        self._update_buttons()

    def _entry_ready(self, job: Job) -> None:
        entry = self.entry
        if entry is None:
            return
        if job.error is not None:
            self.preview_text.setText(strings.LIB_PREVIEW_ERROR.format(job.error))
            self.entry_data = None
            self._update_buttons()
            return
        data = job.value
        self.entry_data = data
        rows = library_folder.describe_entry(data, entry)
        if entry.kind == "device":
            self.pin_model.set_rows(rows)
            self.preview_stack.setCurrentWidget(self.pin_table)
            parts = library_folder.describe_parts(data, entry.id)
            self.part_model.set_rows(parts)
            self.part_table.setVisible(bool(parts))
            text = [contents_of(entry)]
        else:
            self.sub_model.set_rows(rows)
            self.preview_stack.setCurrentWidget(self.sub_table)
            text = [entry.description] if entry.description else []
            text.append(contents_of(entry))
            if data.get("notes"):
                text.append(str(data["notes"]))
        if entry.kind == "device" and entry.description:
            text.insert(0, entry.description)
        text.append(strings.LIB_FILE.format(entry.file))
        self.preview_text.setText("\n".join(text))
        self._show_source()
        self._update_buttons()

    def _part_activated(self, index: QModelIndex) -> None:
        row = self.part_table.row_at(index)
        if isinstance(row, dict):
            self.open_part_link(str(row.get("part", "")))

    def open_part_link(self, part_id: str) -> bool:
        """Open the link of a part of the device shown in the web browser (`https://` or
        `http://` only; `describe_parts` leaves any other out)."""
        for row in self.part_model.rows():
            if isinstance(row, dict) and row.get("part") == part_id and row.get("link"):
                return bool(self.opener(QUrl(str(row["link"]))))
        return False

    # ---- buttons ----------------------------------------------------------------------------------
    def _update_buttons(self) -> None:
        entry = self.entry
        ready = entry is not None and self.entry_data is not None
        ro = self.ctl.read_only
        self.add_btn.setEnabled(ready and not ro)
        self.add_btn.setToolTip(
            strings.LIB_ADD_READ_ONLY
            if ro
            else strings.LIB_ADD_TIP
            if ready
            else strings.LIB_ADD_NONE
        )
        is_device = entry is not None and entry.kind == "device"
        self.number.setEnabled(is_device and not ro)
        self.number.setToolTip(
            strings.LIB_NUMBER_TIP if is_device or entry is None else strings.LIB_NUMBER_SUBSYSTEM
        )
        if not is_device:
            self.number.setValue(1)
        state = self.state_of(entry)
        review = (
            state is not None and state.state in REVIEWABLE and state.unit_id == state.library_id
        )
        self.review_btn.setEnabled(review and not ro)
        self.review_btn.setToolTip(
            strings.LIB_REVIEW_READ_ONLY
            if ro and review
            else strings.LIB_REVIEW_TIP
            if review
            else strings.LIB_REVIEW_NONE
        )
        selected = self.ctl.selected_ids("unit")
        usable = bool(self.folder) and self.scan is not None and not self.scan.error
        self.save_btn.setEnabled(bool(selected) and usable)
        self.save_btn.setToolTip(
            strings.LIB_SAVE_NO_FOLDER
            if not usable
            else strings.LIB_SAVE_TIP
            if selected
            else strings.LIB_SAVE_NONE
        )

    # ---- add to the project -----------------------------------------------------------------------
    def host(self) -> Host:
        return Host(self, self.theme, self.ctl, self.run_dialog, self.ask_choice)

    def _ask_choice(self, title: str, text: str, buttons: list[str]) -> int:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        created = [box.addButton(b, QMessageBox.ButtonRole.ActionRole) for b in buttons]
        run_dialog(box)  # (waits for the answer, but moves on its own)
        clicked = box.clickedButton()
        return created.index(clicked) if clicked in created else len(buttons) - 1

    def plan_add(self) -> tuple[list[Op], list[str], str, list[str], str] | None:
        """(ops, IDs of the new devices, the name of the undo step, notes, the message) for the
        chosen entry and number; None when the person cancelled the question about a taken ID.
        Raises a `HarnessError` (the sentence says what is wrong)."""
        entry, data = self.entry, self.entry_data
        if entry is None or data is None:
            raise EditError(strings.LIB_ADD_NONE)
        project = self.ctl.project
        if entry.kind == "subsystem":
            plan = sl.plan_subsystem_import(project, data)
            if not plan.ok:
                raise EditError(plan.problem)
            ids = [r.new_id for r in plan.rows if r.ok]
            n_conn = sum(1 for o in plan.ops if getattr(o, "collection", "") == "links")
            message = strings.LIB_ADDED_SUBSYSTEM.format(
                entry.name, _n("devices", len(ids)), _n("connections", n_conn)
            )
            return (
                plan.ops,
                ids,
                strings.STEP_LIB_ADD_SUBSYSTEM.format(plan.name),
                plan.notes,
                message,
            )
        # one core function adds the device with its import record; a taken ID asks (D-240)
        libs = self.libraries()
        if libs is None:
            raise EditError(strings.LIB_ADD_NONE)
        add = plan_library_add(self.host(), libs, [entry.id], int(self.number.value()))
        if add is None:
            return None
        return add.ops, add.ids, add.label, add.notes, add.message()

    def add_flow(self) -> None:
        """Add to project: one undo step; the notice under the list says what was added."""
        if not self.add_btn.isEnabled():
            if self.ctl.read_only:
                self.ctl.refuse_read_only()
            return
        try:
            planned = self.plan_add()
        except HarnessError as exc:
            self.result_notice.show_notice("error", str(exc))
            return
        if planned is None:  # the question about a taken ID was cancelled: nothing changed
            return
        ops, ids, label, notes, message = planned
        if not ops or not self.ctl.run(label, ops, message=message):
            return
        self.result_notice.show_notice("info", message, details=notes or None)
        if ids:
            self.ctl.select("unit", ids[0])
        self.added.emit(ids)

    # ---- review a device that differs (D-240) -----------------------------------------------------
    def review_flow(self) -> None:
        """Review changes…: the project's device with the chosen entry's ID beside the library's."""
        entry, libs = self.entry, self.libraries()
        if entry is None or libs is None or not self.review_btn.isEnabled():
            return
        try:
            lib = self.library_of(entry)
            info = self.links.get(lib.origin) if lib is not None else None
            message, wrote = review_flow(self.host(), libs, entry.id, info)
        except HarnessError as exc:
            self.result_notice.show_notice("error", str(exc))
            return
        if wrote:
            self.refresh()
            self.libraryWritten.emit()
        if message:
            self.result_notice.show_notice("info", message)

    # ---- save the selection -----------------------------------------------------------------------
    def save_flow(self) -> None:
        """Save selection to library…: asks devices or a subsystem, then writes into the folder."""
        selected = self.ctl.selected_ids("unit")
        if not selected or not self.folder:
            return
        dlg = SaveToLibraryDialog(
            self, self.theme, self.ctl.project, selected, self.folder, self.scan
        )
        if self.run_dialog(dlg) != QDialog.DialogCode.Accepted:
            return
        notes: list[str] = []
        try:
            if dlg.is_subsystem():
                name = dlg.name.text().strip()
                path = library_folder.save_subsystem(
                    self.folder, self.ctl.project, selected, name, dlg.description.text()
                )
                message = strings.LIB_SAVED_SUBSYSTEM.format(name, path.name)
            else:
                folder, project = self.folder, self.ctl.project
                done = save_devices_asking(
                    self,
                    self.run_dialog,
                    lambda **kw: library_folder.save_devices(folder, project, selected, **kw),
                )
                if done is None:  # cancelled: nothing was written
                    return
                notes = done.notes
                if done.new_ids:
                    message = strings.LIB_SAVED_AS_NEW.format(
                        ", ".join(done.new_ids), done.names, ", ".join(done.new_ids.values())
                    )
                else:
                    message = strings.LIB_SAVED_DEVICES.format(", ".join(selected), done.names)
        except (HarnessError, OSError) as exc:
            text = str(exc) if isinstance(exc, HarnessError) else str(exc.strerror or exc)
            self.result_notice.show_notice("error", text)
            return
        self.refresh()
        self.libraryWritten.emit()
        self.result_notice.show_notice("info", message, details=notes or None)

    # ---- the window's own place ---------------------------------------------------------------------
    def event(self, e: QEvent) -> bool:
        handled = super().event(e)
        refit_on(self, e)  # as high as its wrapped text needs, like the dialogs (dialog_base)
        return handled

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            geometry = self.settings.value(SETTINGS_GEOMETRY)
            if geometry is not None:
                self.restoreGeometry(geometry)
            sizes = self.settings.value(SETTINGS_SPLIT)
            if isinstance(sizes, list) and len(sizes) == 2:
                self.split.setSizes([int(s) for s in sizes])
            else:
                total = max(self.split.width(), 1)
                self.split.setSizes([total // 2, total // 2])
        self.search.setFocus()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.settings.setValue(SETTINGS_GEOMETRY, self.saveGeometry())
        self.settings.setValue(SETTINGS_SPLIT, self.split.sizes())
        self.jobs.wait_idle(500)  # (a thread must not outlive the window that started it)
        super().closeEvent(event)
