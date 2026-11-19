# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""Help > User guide (F1): the bundled guide (`resources/guide/index.html`) in a window of the
program, beside the editor and not modal (it only shows something, `blocks = False`).

The editor opens no browser (the owner's decisions of 2026-11-18 and 2026-11-19, D-250). A link
inside the guide (its table of contents, an anchor, another page of the guide's folder) is
followed in this window, with Back to return. A link that leaves the guide is never opened: a web
link (`https://`, `http://`, the rule of `weblinks.web_link`) is copied to the clipboard through
`copier` and the window says so; any other link (`mailto:`, a file outside the guide, any other
scheme) is not followed and the window says that too.

    win = GuideWindow(theme, parent, path=guide_path())
    win.copier = window._copy_link       # (the default puts it on the system clipboard)
    run_dialog(win)                      # shown beside the window, no wait

The guide's HTML is written for a browser; `QTextBrowser` reads a subset of HTML and CSS. The
headings, paragraphs, lists, tables, code and the anchors of the table of contents work; the
colours of the guide's own style sheet (CSS custom properties, `prefers-color-scheme`), the
sticky table of contents and the width limit of the text do not. The window gives the document
the theme's colours for links, table lines and code instead (`guide_css`).
"""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget

from harness_design_studio.gui import icons, strings, weblinks
from harness_design_studio.gui.dialog_base import Dialog
from harness_design_studio.gui.theme import ThemeManager


def guide_css(theme: ThemeManager) -> str:
    """The document's default style sheet: the theme's colours where the guide's own style sheet
    uses CSS that `QTextBrowser` cannot read."""
    accent = theme.color("accent").name()
    line = theme.color("border.strong").name()
    code = theme.color("bg.hover").name()
    return (
        f"a {{ color: {accent}; }}"
        f" table {{ border-collapse: collapse; margin-top: 6px; margin-bottom: 6px; }}"
        f" th, td {{ border: 1px solid {line}; padding: 4px; }}"
        f" code, pre {{ background-color: {code}; }}"
    )


class GuideWindow(Dialog):
    """The user guide in a window of its own (see the module text)."""

    blocks = False  # it only shows something: `run_dialog` shows it beside the window

    def __init__(
        self, theme: ThemeManager, parent: QWidget | None = None, *, path: Path | None = None
    ) -> None:
        super().__init__(parent)
        self.theme = theme
        self.path = path.resolve() if path is not None else None
        self.copier: Callable[[str], None] = weblinks.system_clipboard  # a hook for the tests
        self.setObjectName("guide-window")
        self.setWindowTitle(strings.GUIDE_TITLE)
        self.setAccessibleName(strings.GUIDE_TITLE)
        self.resize(theme.px(820), theme.px(680))
        lay = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setObjectName("guide-browser")
        self.browser.setAccessibleName(strings.GUIDE_NAME)
        self.browser.setToolTip(strings.GUIDE_TIP)
        self.browser.setOpenLinks(False)  # every link goes through `follow`
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self.follow)
        lay.addWidget(self.browser, 1)
        self.status = QLabel(strings.GUIDE_HINT)
        self.status.setObjectName("guide-status")
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("guide-back")
        icons.icon_button(self.back_btn, "chevron-left", theme, strings.GUIDE_BACK_TIP, text=strings.GUIDE_BACK)  # fmt: skip
        self.back_btn.setToolTip(strings.GUIDE_BACK_TIP)
        self.back_btn.setShortcut(QKeySequence("Alt+Left"))
        self.back_btn.setEnabled(False)
        self.contents_btn = QPushButton()
        self.contents_btn.setObjectName("guide-contents")
        icons.icon_button(self.contents_btn, "list", theme, strings.GUIDE_CONTENTS_TIP, text=strings.GUIDE_CONTENTS)  # fmt: skip
        self.contents_btn.setToolTip(strings.GUIDE_CONTENTS_TIP)
        self.contents_btn.setShortcut(QKeySequence("Alt+Home"))
        self.close_btn = QPushButton()
        self.close_btn.setObjectName("guide-close")
        icons.icon_button(self.close_btn, "close", theme, strings.GUIDE_CLOSE_TIP, text=strings.CLOSE)  # fmt: skip
        self.close_btn.setToolTip(strings.GUIDE_CLOSE_TIP)
        row.addWidget(self.back_btn)
        row.addWidget(self.contents_btn)
        row.addStretch(1)
        row.addWidget(self.close_btn)
        lay.addLayout(row)
        self.back_btn.clicked.connect(self.browser.backward)
        self.browser.backwardAvailable.connect(self.back_btn.setEnabled)
        self.contents_btn.clicked.connect(self.show_contents)
        self.close_btn.clicked.connect(self.accept)
        theme.changed.connect(self._restyle)
        self.browser.document().setDefaultStyleSheet(guide_css(theme))
        if self.path is not None:
            self.browser.setSource(QUrl.fromLocalFile(str(self.path)))

    def _restyle(self) -> None:
        self.browser.document().setDefaultStyleSheet(guide_css(self.theme))
        self.browser.reload()

    def show_contents(self) -> None:
        """Back to the top of the guide, where its table of contents is."""
        if self.path is not None:
            self.browser.setSource(QUrl.fromLocalFile(str(self.path)))
        self.browser.verticalScrollBar().setValue(0)

    def in_guide(self, url: QUrl) -> QUrl | None:
        """`url` (as the guide has it, perhaps only `#anchor`) as a page of the guide's own folder,
        or None when it leads anywhere else."""
        if self.path is None:
            return None
        target = self.browser.source().resolved(url) if url.isRelative() else url
        if not target.isLocalFile() or target.hasQuery():
            return None
        try:
            page = Path(target.toLocalFile()).resolve()
        except OSError, ValueError:
            return None
        folder = self.path.parent
        if page.suffix.lower() != ".html" or not page.is_file() or not page.is_relative_to(folder):
            return None
        return target

    def follow(self, url: QUrl) -> str:
        """A link of the guide was clicked (or chosen with the keyboard). Returns what was done:
        "followed" (in this window), "copied" (a web link, to the clipboard) or "refused"."""
        inside = self.in_guide(url)
        if inside is not None:
            self.browser.setSource(inside)
            self.status.setText(strings.GUIDE_HINT)
            return "followed"
        text = url.toString()
        if weblinks.copy_web_link(text, self.copier):
            self.status.setText(strings.LINK_COPIED.format(text))
            return "copied"
        self.status.setText(strings.GUIDE_LINK_REFUSED.format(text))
        return "refused"
