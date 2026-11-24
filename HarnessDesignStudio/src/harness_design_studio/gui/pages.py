# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The Home area, a page of its own (Settings is in `settings_page.py`).

    home = HomePage(theme, new=..., open_=..., example=..., sample=...)
    home.show_project(name, path, summary)

It only shows and calls back; the window does the work. Home is the first screen of the program
(the landing page, `set_landing`: nothing is open yet, so the card of the open project is left out)
and of a project: what is open and how to start another. The recent projects are listed newest
first; *Clear list* empties the list (the window asks first) and touches no project folder.

At the first start Home also asks *Who are you working as?* (`show_role_question`): a short heading
and the three roles as big buttons on the page itself, with the line that the role can be changed
later in View > Role. A button calls back `choose_role(role)`; the window stores the answer and
puts the section away. (Until the owner's feedback of 2026-11-17 this was a window of its own,
`RoleDialog`, which a window manager could open taller than the main window.)
"""

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from harness_design_studio.gui import strings
from harness_design_studio.gui.recent import RecentEntry
from harness_design_studio.gui.roles import AIT, ELECTRICAL, SYSTEMS
from harness_design_studio.gui.shell import ElidedLabel
from harness_design_studio.gui.states import StateChip
from harness_design_studio.gui.theme import ThemeManager, mark_mono


def _example_infos() -> tuple:  # type: ignore[type-arg]
    """The packaged examples of the group Start (`core.templates.TEMPLATES`) except the empty
    project: one row each on Home; the feature examples get one line (design of 5.1.0, T9)."""
    from harness_design_studio.core import templates

    return tuple(t for t in templates.in_group(templates.START) if t.name != "blank")


def _feature_count() -> int:
    from harness_design_studio.core import templates

    return len(templates.in_group(templates.FEATURE))


def _page(theme: ThemeManager, name: str, title: str) -> tuple[QScrollArea, QVBoxLayout]:
    """A scrolling page with a title and a column that is never wider than a readable line."""
    scroll = QScrollArea()
    scroll.setObjectName(name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setAccessibleName(title)
    body = QWidget()
    outer = QHBoxLayout(body)
    column = QVBoxLayout()
    column.setSpacing(theme.space(16))
    outer.setContentsMargins(theme.space(24), theme.space(24), theme.space(24), theme.space(24))
    outer.addLayout(column, 1)
    outer.addStretch(1)
    heading = QLabel(title)
    heading.setProperty("title", True)
    heading.setAccessibleName(title)
    column.addWidget(heading)
    scroll.setWidget(body)
    body.setMaximumWidth(theme.px(900))
    return scroll, column


def _card(
    theme: ThemeManager, heading: str, action: QWidget | None = None
) -> tuple[QFrame, QVBoxLayout]:
    """A card with its heading; `action` (a button) sits at the right end of the heading's line."""
    card = QFrame()
    card.setProperty("card", True)
    lay = QVBoxLayout(card)
    lay.setContentsMargins(theme.space(16), theme.space(12), theme.space(16), theme.space(16))
    lay.setSpacing(theme.space(8))
    label = QLabel(heading)
    label.setProperty("heading", True)
    if action is None:
        lay.addWidget(label)
        return card, lay
    line = QHBoxLayout()
    line.addWidget(label, 1)
    line.addWidget(action, 0, Qt.AlignmentFlag.AlignVCenter)
    lay.addLayout(line)
    return card, lay


class RoleChoice(QPushButton):
    """A big button: the name of the role, and under it one sentence that wraps. Its height follows
    the width it gets, so the sentence is never cut, whatever the width of the page."""

    def __init__(self, theme: ThemeManager, role: str, title: str, sentence: str, tip: str) -> None:
        super().__init__()
        self.role = role
        self.setObjectName(f"home-role-{role}")
        self.setAccessibleName(title)
        self.setAccessibleDescription(sentence)
        self.setToolTip(tip)
        self.setProperty("choice", True)  # the style sheet frees the height of a control
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.space(16), theme.space(12), theme.space(16), theme.space(12))
        lay.setSpacing(theme.space(4))
        self.head = QLabel(title)
        self.head.setProperty("heading", True)
        self.body = QLabel(sentence)
        self.body.setWordWrap(True)
        for label in (self.head, self.body):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(label)

    # (a QPushButton measures its own text; this one is measured by the labels in its layout)
    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        lay = self.layout()
        return lay.totalHeightForWidth(width) if lay is not None else super().heightForWidth(width)

    def sizeHint(self) -> QSize:
        lay = self.layout()
        if lay is None:
            return super().sizeHint()
        hint = lay.totalSizeHint()
        return QSize(hint.width(), max(hint.height(), self.heightForWidth(hint.width())))

    def minimumSizeHint(self) -> QSize:
        lay = self.layout()
        if lay is None:
            return super().minimumSizeHint()
        least = lay.totalMinimumSize()
        return QSize(least.width(), max(least.height(), self.heightForWidth(self.width())))


class HomePage(QScrollArea):
    def __init__(
        self,
        theme: ThemeManager,
        *,
        new: Callable[[], None],
        open_: Callable[[], None],
        example: Callable[[], None],
        sample: Callable[[], None],
        library: Callable[[], None] = lambda: None,
        open_recent: Callable[[str], None] | None = None,
        forget_recent: Callable[[str], None] | None = None,
        open_example: Callable[[str], None] | None = None,
        clear_recent: Callable[[], object] | None = None,
        choose_role: Callable[[str], None] | None = None,
        features: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.theme = theme
        self._open_recent = open_recent or (lambda _p: None)
        self._forget_recent = forget_recent or (lambda _p: None)
        self._clear_recent = clear_recent or (lambda: None)
        page, column = _page(theme, "home-page", strings.HOME_TITLE)
        self.setObjectName("home-page")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(page.takeWidget())
        self.setAccessibleName(strings.HOME_TITLE)
        # the landing page (the start of the program): one line instead of the open project's card
        self.landing_note = QLabel(strings.HOME_LANDING)
        self.landing_note.setObjectName("home-landing")
        self.landing_note.setWordWrap(True)
        self.landing_note.setProperty("muted", True)
        self.landing_note.setAccessibleName(strings.HOME_LANDING)
        self.landing_note.hide()
        column.addWidget(self.landing_note)
        # the question of the first start: shown by `show_role_question` until it is answered
        self._choose_role = choose_role or (lambda _r: None)
        self.role_card, role_lay = _card(theme, strings.HOME_ROLE_TITLE)
        self.role_card.setObjectName("home-role")
        self.role_card.setAccessibleName(strings.HOME_ROLE_NAME)
        role_text = QLabel(strings.HOME_ROLE_TEXT)
        role_text.setWordWrap(True)
        role_lay.addWidget(role_text)
        self.role_buttons: dict[str, RoleChoice] = {}
        for role, role_title, sentence, tip in (
            (
                SYSTEMS,
                strings.ROLE_SYSTEMS,
                strings.HOME_ROLE_SYSTEMS_TEXT,
                strings.ROLE_SYSTEMS_TIP,
            ),
            (
                ELECTRICAL,
                strings.ROLE_ELECTRICAL,
                strings.HOME_ROLE_ELECTRICAL_TEXT,
                strings.ROLE_ELECTRICAL_TIP,
            ),  # fmt: skip
            (AIT, strings.ROLE_AIT, strings.HOME_ROLE_AIT_TEXT, strings.ROLE_AIT_TIP),
        ):
            choice = RoleChoice(theme, role, role_title, sentence, tip)
            choice.clicked.connect(lambda _c=False, r=role: self._choose_role(r))
            role_lay.addWidget(choice)
            self.role_buttons[role] = choice
        later = QLabel(strings.HOME_ROLE_LATER)
        later.setObjectName("home-role-later")
        later.setProperty("muted", True)
        later.setWordWrap(True)
        role_lay.addWidget(later)
        self.role_card.hide()
        column.addWidget(self.role_card)
        card, lay = _card(theme, strings.HOME_PROJECT)
        self.project_card = card
        self.name = ElidedLabel()
        self.name.setProperty("title", True)
        self.name.setObjectName("home-name")
        self.name.setAccessibleName(strings.HOME_PROJECT)
        self.path = ElidedLabel()
        self.path.setObjectName("home-path")
        mark_mono(self.path)
        self.path.setProperty("muted", True)
        self.summary = QLabel()
        self.summary.setObjectName("home-summary")
        self.summary.setProperty("muted", True)
        for w in (self.name, self.path, self.summary):
            lay.addWidget(w)
        column.addWidget(card)
        start, start_lay = _card(theme, strings.HOME_ACTIONS)
        row = QHBoxLayout()
        self.buttons: dict[str, QPushButton] = {}
        for key, text, callback in (
            ("new", strings.HOME_NEW, new),
            ("open", strings.HOME_OPEN, open_),
            ("example", strings.HOME_EXAMPLE, example),
            ("sample", strings.HOME_SAMPLE, sample),
            ("library", strings.HOME_LIBRARY, library),
        ):
            b = QPushButton(text)
            b.setObjectName(f"home-{key}")
            b.setAccessibleName(text.rstrip("…"))
            if key == "library":
                b.setToolTip(strings.HOME_LIBRARY_TIP)
            b.clicked.connect(lambda _c=False, cb=callback: cb())
            row.addWidget(b)
            self.buttons[key] = b
        row.addStretch(1)
        start_lay.addLayout(row)
        column.addWidget(start)
        # recent projects: a card each, filled by `set_recent`, newest first; Clear list empties it
        self.clear_btn = QPushButton(strings.HOME_CLEAR)
        self.clear_btn.setObjectName("home-recent-clear")
        self.clear_btn.setProperty("ghost", True)
        self.clear_btn.setAccessibleName(strings.HOME_CLEAR_NAME)
        self.clear_btn.setToolTip(strings.HOME_CLEAR_TIP)
        self.clear_btn.clicked.connect(lambda _c=False: self._clear_recent())
        self.clear_btn.hide()  # shown while the list has an entry
        self.recent_card, self.recent_lay = _card(theme, strings.HOME_RECENT, self.clear_btn)
        self.recent_empty = QLabel(strings.HOME_RECENT_NONE)
        self.recent_empty.setProperty("muted", True)
        self.recent_empty.setWordWrap(True)
        self.recent_lay.addWidget(self.recent_empty)
        self.recent_rows: list[QWidget] = []
        column.addWidget(self.recent_card)
        # the packaged examples, with a one-click way into the flatsat
        ex, ex_lay = _card(theme, strings.HOME_EXAMPLES)
        self.example_buttons: dict[str, QPushButton] = {}
        for info in _example_infos():
            line = QHBoxLayout()
            col = QVBoxLayout()
            title = QLabel(info.title)
            title.setProperty("title", False)
            blurb = QLabel(info.summary)
            blurb.setWordWrap(True)
            blurb.setProperty("muted", True)
            col.addWidget(title)
            col.addWidget(blurb)
            line.addLayout(col, 1)
            b = QPushButton(
                strings.HOME_EXAMPLE_FLATSAT
                if info.name == "flatsat"
                else strings.HOME_EXAMPLE_OPEN
            )
            b.setObjectName(f"home-example-{info.name}")
            b.setAccessibleName(f"{strings.HOME_EXAMPLE_OPEN}: {info.title}")
            if info.name == "flatsat":
                b.setProperty("primary", True)
                b.setToolTip(strings.HOME_EXAMPLE_FLATSAT_TIP)
            if open_example is not None:
                b.clicked.connect(lambda _c=False, n=info.name: open_example(n))
            line.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
            ex_lay.addLayout(line)
            self.example_buttons[info.name] = b
        # the feature examples: one line and a button that opens New project from an example with
        # the first of them chosen, so nineteen rows do not push the page down
        count = _feature_count()
        self.features_line = QLabel(
            strings.HOME_FEATURES_ONE if count == 1 else strings.HOME_FEATURES.format(count)
        )
        self.features_line.setObjectName("home-features")
        self.features_line.setWordWrap(True)
        self.features_line.setProperty("muted", True)
        self.features_button = QPushButton(strings.HOME_FEATURES_BUTTON)
        self.features_button.setObjectName("home-features-show")
        self.features_button.setAccessibleName(strings.HOME_FEATURES_NAME)
        self.features_button.setToolTip(strings.HOME_FEATURES_TIP)
        if features is not None:
            self.features_button.clicked.connect(lambda _c=False: features())
        line = QHBoxLayout()
        line.addWidget(self.features_line, 1)
        line.addWidget(self.features_button, 0, Qt.AlignmentFlag.AlignTop)
        ex_lay.addLayout(line)
        self.features_line.setVisible(bool(count))
        self.features_button.setVisible(bool(count))
        column.addWidget(ex)
        column.addStretch(1)

    def set_recent(self, entries: Sequence[RecentEntry], *, exists: Callable[[str], bool]) -> None:
        """One card per recent project (the folder must still exist to be opened)."""
        for w in self.recent_rows:
            self.recent_lay.removeWidget(w)
            w.hide()  # deleteLater is deferred; hide now so the old card is not drawn beside the new
            w.deleteLater()
        self.recent_rows = []
        self.recent_empty.setVisible(not entries)
        self.clear_btn.setVisible(bool(entries))
        for e in entries:
            card = QWidget()
            card.setObjectName("home-recent")
            lay = QHBoxLayout(card)
            lay.setContentsMargins(0, self.theme.space(4), 0, self.theme.space(4))
            col = QVBoxLayout()
            title = QLabel(e.name or e.path)
            title.setProperty("title", True)
            path = ElidedLabel(e.path)
            mark_mono(path)
            path.setProperty("muted", True)
            counts = QLabel(strings.HOME_COUNTS.format(e.units, e.interfaces, e.harnesses))
            counts.setProperty("muted", True)
            col.addWidget(title)
            col.addWidget(path)
            chips = QHBoxLayout()
            chips.addWidget(counts)
            for state, n, text in (
                ("draft", e.draft, strings.HOME_DRAFT),
                ("in-review", e.in_review, strings.HOME_IN_REVIEW),
                ("released", e.released, strings.HOME_RELEASED),
            ):
                if n:
                    chip = StateChip(self.theme)
                    chip.set_state(state, str(n))
                    chip.setToolTip(text.format(n))
                    chips.addWidget(chip)
            chips.addStretch(1)
            col.addLayout(chips)
            lay.addLayout(col, 1)
            present = exists(e.path)
            open_btn = QPushButton(strings.HOME_OPEN_BTN)
            open_btn.setObjectName("home-recent-open")
            open_btn.setAccessibleName(f"{strings.HOME_OPEN_BTN} {e.name or e.path}")
            open_btn.setEnabled(present)
            if not present:
                open_btn.setToolTip(strings.HOME_MISSING.format(e.path))
            open_btn.clicked.connect(lambda _c=False, p=e.path: self._open_recent(p))
            drop = QPushButton(strings.HOME_REMOVE)
            drop.setObjectName("home-recent-remove")
            drop.setProperty("ghost", True)
            drop.setAccessibleName(f"{strings.HOME_REMOVE}: {e.name or e.path}")
            drop.clicked.connect(lambda _c=False, p=e.path: self._forget_recent(p))
            lay.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(drop, 0, Qt.AlignmentFlag.AlignTop)
            self.recent_lay.addWidget(card)
            self.recent_rows.append(card)

    def show_role_question(self, on: bool) -> None:
        """Show or put away the question of the first start, *Who are you working as?*."""
        self.role_card.setVisible(on)

    def set_landing(self, on: bool) -> None:
        """The landing page of the program's start (`on`): no project of the person's is open, so
        the card of the open project gives way to one line that says how to start."""
        self.landing_note.setVisible(on)
        self.project_card.setVisible(not on)

    def landing(self) -> bool:
        return not self.landing_note.isHidden()

    def show_project(self, name: str, path: str, summary: str) -> None:
        self.name.set_full_text(name)
        self.path.set_full_text(path or strings.HOME_NO_PROJECT)
        self.summary.setText(summary)
