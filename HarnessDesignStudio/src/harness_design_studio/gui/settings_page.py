# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The Settings area: appearance, editing, the project's values, keyboard shortcuts, About, Licences.

    page = SettingsPage(theme, set_role=..., set_theme=..., set_scale=..., set_reduce_motion=..., set_mode=...,
                        set_snap=..., set_labels=..., open_values=..., shortcut_rows=...,
                        settings_file="...")
    page.sync(theme_mode="dark", scale=125, mode="expert", role="electrical", reduce_motion=False, snap=True, labels=False)

The page only shows and calls back; the window changes the setting, stores it and applies it at once
(`MainWindow.set_theme_mode`, `set_scale`, `set_reduce_motion` ...). Every control here has a twin in
a menu or on Ctrl+K, so `sync` follows whatever changed it. A section list on the left, the section
on the right.
"""

import platform
from collections.abc import Callable

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QModelIndex, Qt, qVersion
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio import __version__
from harness_design_studio.gui import licences, strings
from harness_design_studio.gui.empty_state import attach_empty_state
from harness_design_studio.gui.tables import Column, DictTableModel, TableView
from harness_design_studio.gui.theme import ThemeManager, mark_mono

SCALES = (100, 125, 150, 200)
THEMES = (
    ("system", strings.SETTINGS_THEME_SYSTEM),
    ("light", strings.SETTINGS_THEME_LIGHT),
    ("dark", strings.SETTINGS_THEME_DARK),
)
MODES = (("guided", strings.GUIDED), ("expert", strings.EXPERT))
ROLES = (
    ("systems", strings.ROLE_SYSTEMS),
    ("electrical", strings.ROLE_ELECTRICAL),
    ("ait", strings.ROLE_AIT),
)
SECTIONS = (
    ("appearance", strings.SETTINGS_SECTION_APPEARANCE),
    ("editing", strings.SETTINGS_SECTION_EDITING),
    ("project", strings.SETTINGS_SECTION_PROJECT),
    ("shortcuts", strings.SETTINGS_SECTION_SHORTCUTS),
    ("about", strings.SETTINGS_SECTION_ABOUT),
    ("licences", strings.SETTINGS_SECTION_LICENCES),
)


def _section(
    theme: ThemeManager, key: str, title: str, *, wide: bool = False
) -> tuple[QScrollArea, QVBoxLayout]:
    """One scrolling section: a title and a column that is never wider than a readable line (a
    section that holds a table takes all the width there is, up to 900 px)."""
    scroll = QScrollArea()
    scroll.setObjectName(f"settings-section-{key}")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setAccessibleName(title)
    body = QWidget()
    outer = QHBoxLayout(body)
    outer.setContentsMargins(theme.space(24), theme.space(24), theme.space(24), theme.space(24))
    column = QVBoxLayout()
    column.setSpacing(theme.space(12))
    outer.addLayout(column, 1)
    if not wide:
        outer.addStretch(1)
    heading = QLabel(title)
    heading.setProperty("title", True)
    column.addWidget(heading)
    scroll.setWidget(body)
    body.setMaximumWidth(theme.px(900))
    return scroll, column


def _muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("muted", True)
    return label


def _check(text: str, tip: str, object_name: str) -> QCheckBox:
    box = QCheckBox(text)
    box.setObjectName(object_name)
    box.setAccessibleName(text)
    box.setToolTip(tip)
    return box


class SettingsPage(QWidget):
    def __init__(
        self,
        theme: ThemeManager,
        *,
        set_role: Callable[[str], None],
        set_theme: Callable[[str], None],
        set_scale: Callable[[int], None],
        set_reduce_motion: Callable[[bool], None],
        set_mode: Callable[[str], None],
        set_snap: Callable[[bool], None],
        set_labels: Callable[[bool], None],
        set_problem_notices: Callable[[bool], None],
        set_quick: Callable[[bool], None] = lambda _on: None,
        set_connection_ends: Callable[[bool], None] = lambda _on: None,
        open_values: Callable[[], None],
        choose_library_folder: Callable[[], None] = lambda: None,
        clear_library_folder: Callable[[], None] = lambda: None,
        open_library: Callable[[], None] = lambda: None,
        add_project_library: Callable[[], None] = lambda: None,
        remove_project_library: Callable[[str], None] = lambda _path: None,
        set_segmentation: Callable[[str], None] = lambda _mode: None,
        shortcut_rows: Callable[[], list[tuple[str, str]]],
        settings_file: str = "",
    ) -> None:
        super().__init__()
        self.theme = theme
        self._shortcut_rows = shortcut_rows
        self.setObjectName("settings-page")
        self.setAccessibleName(strings.SETTINGS_TITLE)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sections = QListWidget()
        self.sections.setObjectName("settings-sections")
        self.sections.setAccessibleName(strings.SETTINGS_SECTIONS_NAME)
        self.sections.setFixedWidth(theme.px(200))
        self.sections.setProperty("nav", True)
        self.stack = QStackedWidget()
        self.stack.setObjectName("settings-stack")
        lay.addWidget(self.sections)
        lay.addWidget(self.stack, 1)
        self._keys: list[str] = []
        self.pages: dict[str, QScrollArea] = {}

        # ---- appearance
        page, col = self._add("appearance")
        form = QFormLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("settings-theme")
        self.theme_combo.setAccessibleName(strings.SETTINGS_THEME)
        for key, text in THEMES:
            self.theme_combo.addItem(text, key)
        self.theme_combo.activated.connect(lambda i: set_theme(str(self.theme_combo.itemData(i))))
        self.scale_combo = QComboBox()
        self.scale_combo.setObjectName("settings-scale")
        self.scale_combo.setAccessibleName(strings.SETTINGS_SCALE)
        self.scale_combo.setToolTip(strings.SETTINGS_SCALE_HINT)
        for pct in SCALES:
            self.scale_combo.addItem(f"{pct} %", pct)
        self.scale_combo.activated.connect(lambda i: set_scale(int(self.scale_combo.itemData(i))))
        form.addRow(strings.SETTINGS_THEME, self.theme_combo)
        form.addRow(strings.SETTINGS_SCALE, self.scale_combo)
        col.addLayout(form)
        col.addWidget(_muted(strings.SETTINGS_SCALE_HINT))
        self.motion_box = _check(
            strings.SETTINGS_REDUCE_MOTION,
            strings.SETTINGS_REDUCE_MOTION_TIP,
            "settings-reduce-motion",
        )
        self.motion_box.clicked.connect(lambda on: set_reduce_motion(bool(on)))
        col.addWidget(self.motion_box)
        col.addWidget(_muted(strings.SETTINGS_REDUCE_MOTION_TIP))
        col.addStretch(1)

        # ---- editing
        page, col = self._add("editing")
        self.role_combo = QComboBox()
        self.role_combo.setObjectName("settings-role")
        self.role_combo.setAccessibleName(strings.SETTINGS_ROLE)
        self.role_combo.setToolTip(strings.SETTINGS_ROLE_HINT)
        for key, text in ROLES:
            self.role_combo.addItem(text, key)
        self.role_combo.activated.connect(lambda i: set_role(str(self.role_combo.itemData(i))))
        role_form = QFormLayout()
        role_form.addRow(strings.SETTINGS_ROLE, self.role_combo)
        col.addLayout(role_form)
        col.addWidget(_muted(strings.SETTINGS_ROLE_HINT))
        self.mode_combo = QComboBox()
        self.mode_combo.setObjectName("settings-mode")
        self.mode_combo.setAccessibleName(strings.SETTINGS_MODE)
        for key, text in MODES:
            self.mode_combo.addItem(text, key)
        self.mode_combo.activated.connect(lambda i: set_mode(str(self.mode_combo.itemData(i))))
        edit_form = QFormLayout()
        edit_form.addRow(strings.SETTINGS_MODE, self.mode_combo)
        col.addLayout(edit_form)
        self.snap_box = _check(strings.SETTINGS_SNAP, strings.SETTINGS_SNAP_TIP, "settings-snap")
        self.snap_box.clicked.connect(lambda on: set_snap(bool(on)))
        self.labels_box = _check(
            strings.SETTINGS_LABELS, strings.SETTINGS_LABELS_TIP, "settings-labels"
        )
        self.labels_box.clicked.connect(lambda on: set_labels(bool(on)))
        self.notices_box = _check(
            strings.SETTINGS_PROBLEM_NOTICES,
            strings.SETTINGS_PROBLEM_NOTICES_TIP,
            "settings-problem-notices",
        )
        self.notices_box.clicked.connect(lambda on: set_problem_notices(bool(on)))
        self.quick_box = _check(
            strings.SETTINGS_QUICK, strings.SETTINGS_QUICK_TIP, "settings-quick"
        )
        self.quick_box.clicked.connect(lambda on: set_quick(bool(on)))
        self.ends_box = _check(
            strings.SETTINGS_CONNECTION_ENDS,
            strings.SETTINGS_CONNECTION_ENDS_TIP,
            "settings-connection-ends",
        )
        self.ends_box.clicked.connect(lambda on: set_connection_ends(bool(on)))
        col.addWidget(self.snap_box)
        col.addWidget(_muted(strings.SETTINGS_SNAP_TIP))
        col.addWidget(self.labels_box)
        col.addWidget(_muted(strings.SETTINGS_LABELS_TIP))
        col.addWidget(self.ends_box)
        col.addWidget(_muted(strings.SETTINGS_CONNECTION_ENDS_TIP))
        col.addWidget(self.quick_box)
        col.addWidget(_muted(strings.SETTINGS_QUICK_TIP))
        col.addWidget(self.notices_box)
        self.notices_note = _muted(strings.SETTINGS_PROBLEM_NOTICES_TIP)
        col.addWidget(self.notices_note)
        col.addStretch(1)

        # ---- project
        page, col = self._add("project")
        col.addWidget(_muted(strings.SETTINGS_PROJECT_TEXT))
        self.values_btn = QPushButton(strings.SETTINGS_PROJECT_BUTTON)
        self.values_btn.setObjectName("settings-values")
        self.values_btn.setAccessibleName(strings.SETTINGS_PROJECT_BUTTON.rstrip("…"))
        self.values_btn.clicked.connect(lambda _c=False: open_values())
        col.addWidget(self.values_btn, 0, Qt.AlignmentFlag.AlignLeft)
        # how Generate groups interfaces into harnesses (a value of the project, one undo step)
        segmentation_title = QLabel(strings.SETTINGS_SEGMENTATION)
        segmentation_title.setProperty("heading", True)
        col.addWidget(segmentation_title)
        col.addWidget(_muted(strings.SETTINGS_SEGMENTATION_TEXT))
        self.segmentation_combo = QComboBox()
        self.segmentation_combo.setObjectName("settings-segmentation")
        self.segmentation_combo.setAccessibleName(strings.SETTINGS_SEGMENTATION)
        self.segmentation_combo.setToolTip(strings.SETTINGS_SEGMENTATION_TIP)
        for value, text in strings.SETTINGS_SEGMENTATION_CHOICES.items():
            self.segmentation_combo.addItem(text, value)
        self.segmentation_combo.currentIndexChanged.connect(
            lambda _i: self._segmentation_picked(set_segmentation)
        )
        col.addWidget(self.segmentation_combo, 0, Qt.AlignmentFlag.AlignLeft)
        self.segmentation_about = _muted("")
        self.segmentation_about.setObjectName("settings-segmentation-about")
        col.addWidget(self.segmentation_about)
        self._segmentation_why_not = ""
        # the library folder (per person; the library window reads it)
        library_title = QLabel(strings.SETTINGS_LIBRARY_FOLDER)
        library_title.setProperty("heading", True)
        col.addWidget(library_title)
        col.addWidget(_muted(strings.SETTINGS_LIBRARY_TEXT))
        self.library_path = QLineEdit()
        self.library_path.setObjectName("settings-library-folder")
        self.library_path.setAccessibleName(strings.SETTINGS_LIBRARY_FOLDER)
        self.library_path.setToolTip(strings.LIB_FOLDER_TIP)
        self.library_path.setReadOnly(True)
        self.library_path.setPlaceholderText(strings.SETTINGS_LIBRARY_NONE)
        mark_mono(self.library_path)
        col.addWidget(self.library_path)
        library_row = QHBoxLayout()
        self.library_choose = QPushButton(strings.SETTINGS_LIBRARY_CHOOSE)
        self.library_choose.setObjectName("settings-library-choose")
        self.library_choose.setAccessibleName(strings.A_LIBRARY_FOLDER.rstrip("…"))
        self.library_choose.setToolTip(strings.A_LIBRARY_FOLDER_TIP)
        self.library_choose.clicked.connect(lambda _c=False: choose_library_folder())
        self.library_clear = QPushButton(strings.SETTINGS_LIBRARY_CLEAR)
        self.library_clear.setObjectName("settings-library-clear")
        self.library_clear.setAccessibleName(strings.SETTINGS_LIBRARY_CLEAR)
        self.library_clear.setToolTip(strings.SETTINGS_LIBRARY_CLEAR_TIP)
        self.library_clear.clicked.connect(lambda _c=False: clear_library_folder())
        self.library_open = QPushButton(strings.SETTINGS_LIBRARY_OPEN)
        self.library_open.setObjectName("settings-library-open")
        self.library_open.setAccessibleName(strings.SETTINGS_LIBRARY_OPEN.rstrip("…"))
        self.library_open.setToolTip(strings.A_LIBRARY_TIP)
        self.library_open.clicked.connect(lambda _c=False: open_library())
        for b in (self.library_choose, self.library_clear, self.library_open):
            library_row.addWidget(b)
        library_row.addStretch(1)
        col.addLayout(library_row)
        # the device libraries of the open project: device-libraries.json, outside undo (D-240)
        project_title = QLabel(strings.SETTINGS_PROJECT_LIBRARIES)
        project_title.setObjectName("settings-project-libraries-title")
        project_title.setProperty("heading", True)
        col.addWidget(project_title)
        self.project_libraries_text = _muted(strings.SETTINGS_PROJECT_LIBRARIES_TEXT)
        self.project_libraries_text.setObjectName("settings-project-libraries-text")
        col.addWidget(self.project_libraries_text)
        self.project_libraries = QListWidget()
        self.project_libraries.setObjectName("settings-project-libraries")
        self.project_libraries.setAccessibleName(strings.SETTINGS_PROJECT_LIBRARIES_LIST)
        self.project_libraries.setToolTip(strings.SETTINGS_PROJECT_LIBRARIES_LIST_TIP)
        self.project_libraries.setMaximumHeight(theme.px(140))
        mark_mono(self.project_libraries)
        col.addWidget(self.project_libraries)
        self.project_libraries_note = _muted("")
        self.project_libraries_note.setObjectName("settings-project-libraries-note")
        col.addWidget(self.project_libraries_note)
        project_row = QHBoxLayout()
        self.project_library_add = QPushButton(strings.SETTINGS_PROJECT_LIBRARIES_ADD)
        self.project_library_add.setObjectName("settings-project-library-add")
        self.project_library_add.setAccessibleName(
            strings.SETTINGS_PROJECT_LIBRARIES_ADD.rstrip("…")
        )
        self.project_library_add.setToolTip(strings.SETTINGS_PROJECT_LIBRARIES_ADD_TIP)
        self.project_library_add.clicked.connect(lambda _c=False: add_project_library())
        self.project_library_remove = QPushButton(strings.SETTINGS_PROJECT_LIBRARIES_REMOVE)
        self.project_library_remove.setObjectName("settings-project-library-remove")
        self.project_library_remove.setAccessibleName(strings.SETTINGS_PROJECT_LIBRARIES_REMOVE)
        self.project_library_remove.setToolTip(strings.SETTINGS_PROJECT_LIBRARIES_REMOVE_TIP)
        self.project_library_remove.clicked.connect(
            lambda _c=False: self._remove_project_library(remove_project_library)
        )
        self.project_libraries.currentRowChanged.connect(lambda _r: self._project_buttons())
        project_row.addWidget(self.project_library_add)
        project_row.addWidget(self.project_library_remove)
        project_row.addStretch(1)
        col.addLayout(project_row)
        self._project_why_not = ""
        self.show_project_libraries([], "", strings.SETTINGS_PROJECT_LIBRARIES_NO_FOLDER)
        col.addStretch(1)

        # ---- shortcuts
        page, col = self._add("shortcuts", wide=True)
        col.addWidget(_muted(strings.SETTINGS_SHORTCUTS_TEXT))
        self.shortcut_filter = QLineEdit()
        self.shortcut_filter.setObjectName("settings-shortcut-filter")
        self.shortcut_filter.setAccessibleName(strings.SETTINGS_SHORTCUTS_FILTER_NAME)
        self.shortcut_filter.setPlaceholderText(strings.SETTINGS_SHORTCUTS_FILTER)
        self.shortcut_filter.setClearButtonEnabled(True)
        col.addWidget(self.shortcut_filter)
        self.shortcut_model = DictTableModel(
            [
                Column("action", strings.SHORTCUT_COLUMNS[0]),
                Column("keys", strings.SHORTCUT_COLUMNS[1], mono=True),
            ],
            [],
            theme,
        )
        self.shortcut_table = TableView(
            self.shortcut_model, theme, name=strings.SHORTCUTS_TABLE_NAME
        )
        self.shortcut_table.setObjectName("settings-shortcuts")
        self.shortcut_filter.textChanged.connect(self.shortcut_table.proxy.set_text)
        attach_empty_state(
            self.shortcut_table, strings.SHORTCUTS_EMPTY, strings.SHORTCUTS_EMPTY_HINT
        )
        self.shortcut_table.setMinimumHeight(theme.px(320))
        col.addWidget(self.shortcut_table, 1)

        # ---- about
        page, col = self._add("about")
        name = QLabel(strings.ABOUT_TITLE)
        name.setProperty("title", True)
        col.addWidget(name)
        self.version_label = QLabel(strings.ABOUT_VERSION.format(__version__))
        self.version_label.setObjectName("settings-version")
        mark_mono(self.version_label)
        col.addWidget(self.version_label)
        col.addWidget(_muted(strings.ABOUT_OFFLINE))
        self.runtime_label = QLabel(
            strings.ABOUT_RUNTIME.format(platform.python_version(), qVersion(), pyside_version)
        )
        self.runtime_label.setObjectName("settings-runtime")
        col.addWidget(self.runtime_label)
        self.file_label = QLabel(strings.ABOUT_SETTINGS_FILE.format(settings_file))
        self.file_label.setObjectName("settings-file")
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.file_label.setVisible(bool(settings_file))
        col.addWidget(self.file_label)
        col.addWidget(_muted(strings.ABOUT_LICENCE_PROJECT))
        self.legal_labels: list[QLabel] = []
        for text in strings.ABOUT_LEGAL:  # the legal texts, word for word (decision D-210)
            label = _muted(text)
            label.setObjectName("settings-legal")
            self.legal_labels.append(label)
            col.addWidget(label)
        col.addStretch(1)

        # ---- licences
        page, col = self._add("licences", wide=True)
        col.addWidget(_muted(strings.LICENCES_TEXT))
        self.licence_model = DictTableModel(
            [
                Column("name", strings.LICENCE_COLUMNS[0]),
                Column("licence", strings.LICENCE_COLUMNS[1]),
                Column("use", strings.LICENCE_COLUMNS[2]),
            ],
            [{"name": c.name, "licence": c.licence, "use": c.use} for c in licences.entries()],
            theme,
        )
        self.licence_table = TableView(self.licence_model, theme, name=strings.LICENCES_TABLE_NAME)
        self.licence_table.setObjectName("settings-licences")
        self.licence_table.setSelectionBehavior(TableView.SelectionBehavior.SelectRows)
        self.licence_table.setSelectionMode(TableView.SelectionMode.SingleSelection)
        self.licence_table.setMaximumHeight(theme.px(160))
        self.licence_table.horizontalHeader().setStretchLastSection(True)
        col.addWidget(self.licence_table)
        self.licence_text = QPlainTextEdit()
        self.licence_text.setObjectName("settings-licence-text")
        self.licence_text.setAccessibleName(strings.LICENCES_TEXT_NAME)
        self.licence_text.setReadOnly(True)
        mark_mono(self.licence_text)
        self.licence_text.setMinimumHeight(theme.px(240))
        col.addWidget(self.licence_text, 1)
        self.licence_table.selectionModel().currentRowChanged.connect(self._licence_picked)

        for _key, text in SECTIONS:
            self.sections.addItem(text)
        self.sections.currentRowChanged.connect(self._section_changed)
        self.sections.setCurrentRow(0)
        self.show_licence("inter")

    # ---- sections -------------------------------------------------------------------------------
    def _add(self, key: str, *, wide: bool = False) -> tuple[QScrollArea, QVBoxLayout]:
        title = dict(SECTIONS)[key]
        scroll, column = _section(self.theme, key, title, wide=wide)
        self.stack.addWidget(scroll)
        self.pages[key] = scroll
        self._keys.append(key)
        return scroll, column

    def show_section(self, key: str) -> None:
        self.sections.setCurrentRow(self._keys.index(key))

    def current_section(self) -> str:
        return self._keys[self.stack.currentIndex()]

    def _section_changed(self, row: int) -> None:
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        if self._keys[row] == "shortcuts":
            self.refresh_shortcuts()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if self.current_section() == "shortcuts":
            self.refresh_shortcuts()

    def refresh_shortcuts(self) -> None:
        """Read the window's actions again (they change with the project and the mode)."""
        rows = [{"action": a, "keys": k} for a, k in self._shortcut_rows()]
        rows += [{"action": a, "keys": k} for a, k in strings.SHORTCUTS_EXTRA]
        self.shortcut_model.set_rows(rows)

    # ---- licences -------------------------------------------------------------------------------
    def _licence_picked(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid():
            return
        source = self.licence_table.proxy.mapToSource(current)
        self.show_licence(licences.entries()[source.row()].key)

    def show_licence(self, key: str) -> None:
        self.licence_text.setPlainText(licences.text_of(key))

    # ---- follow the window ----------------------------------------------------------------------
    def show_project_libraries(self, paths: list[str], note: str, why_not: str = "") -> None:
        """Show the library paths of the open project's `device-libraries.json`; `note` is a
        sentence under the list (what was written, or why the file cannot be used); `why_not`
        says why the list cannot change now ("" when it can)."""
        current = self.project_libraries.currentItem()
        keep = current.text() if current is not None else ""
        self.project_libraries.clear()
        self.project_libraries.addItems(paths)
        if keep in paths:
            self.project_libraries.setCurrentRow(paths.index(keep))
        elif paths:
            self.project_libraries.setCurrentRow(0)
        lines = [] if paths else [strings.SETTINGS_PROJECT_LIBRARIES_NONE]
        if note:
            lines.append(note)
        if why_not:
            lines.append(why_not)
        self.project_libraries_note.setText(" ".join(lines))
        self._project_why_not = why_not
        self._project_buttons()

    def _project_buttons(self) -> None:
        why = self._project_why_not
        self.project_library_add.setEnabled(not why)
        self.project_library_add.setToolTip(why or strings.SETTINGS_PROJECT_LIBRARIES_ADD_TIP)
        chosen = self.project_libraries.currentItem() is not None
        self.project_library_remove.setEnabled(not why and chosen)
        self.project_library_remove.setToolTip(why or strings.SETTINGS_PROJECT_LIBRARIES_REMOVE_TIP)

    def _remove_project_library(self, remove: Callable[[str], None]) -> None:
        item = self.project_libraries.currentItem()
        if item is not None:
            remove(item.text())

    def _segmentation_picked(self, set_segmentation: Callable[[str], None]) -> None:
        mode = self.segmentation_combo.currentData()
        if isinstance(mode, str):
            set_segmentation(mode)  # the window shows the outcome (`show_segmentation`)

    def show_segmentation(self, mode: str, why_not: str = "") -> None:
        """Show the segmentation mode of the open project; `why_not` says why it cannot change
        now ("" when it can: a read-only project, a release that froze it)."""
        combo = self.segmentation_combo
        self._segmentation_why_not = why_not
        combo.blockSignals(True)
        while combo.count() > len(strings.SETTINGS_SEGMENTATION_CHOICES):
            combo.removeItem(combo.count() - 1)
        i = combo.findData(mode)
        if i < 0:  # a mode of a newer version: shown, never written back by this page
            combo.addItem(mode, mode)
            i = combo.count() - 1
        combo.setCurrentIndex(i)
        combo.blockSignals(False)
        about = strings.SETTINGS_SEGMENTATION_ABOUT.get(
            mode, strings.SETTINGS_SEGMENTATION_UNKNOWN.format(mode)
        )
        self.segmentation_about.setText(" ".join(t for t in (about, why_not) if t))
        combo.setEnabled(not why_not)
        combo.setToolTip(why_not or strings.SETTINGS_SEGMENTATION_TIP)

    def show_library_folder(self, folder: str) -> None:
        """Show the library folder the window uses ('' for none)."""
        if self.library_path.text() != folder:
            self.library_path.setText(folder)
        self.library_clear.setEnabled(bool(folder))

    def sync(
        self,
        *,
        theme_mode: str,
        scale: int,
        mode: str,
        role: str,
        reduce_motion: bool,
        snap: bool,
        labels: bool,
        problem_notices: bool = True,
        connection_ends: bool = False,
        quick: bool = False,
    ) -> None:
        """Show what the window has now (it changes through the menus, the palette and here)."""
        for combo, value in ((self.theme_combo, theme_mode), (self.scale_combo, scale), (self.mode_combo, mode), (self.role_combo, role)):  # fmt: skip
            i = combo.findData(value)
            if i >= 0 and combo.currentIndex() != i:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)
        for box, value in ((self.motion_box, reduce_motion), (self.snap_box, snap), (self.labels_box, labels), (self.notices_box, problem_notices), (self.quick_box, quick), (self.ends_box, connection_ends)):  # fmt: skip
            if box.isChecked() != value:
                box.blockSignals(True)
                box.setChecked(value)
                box.blockSignals(False)
        self.notices_box.setEnabled(not quick)  # (Quick mode forces the notices off)
        self.notices_box.setToolTip(
            strings.SETTINGS_QUICK_NOTICES_OFF if quick else strings.SETTINGS_PROBLEM_NOTICES_TIP
        )
