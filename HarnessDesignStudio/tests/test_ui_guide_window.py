# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
# mypy: disable-error-code="no-untyped-def"
"""The user guide in a window of the program (`gui/guide_window.py`, 3.0.1, the owner's decision of
2026-11-19): the bundled guide is shown, its table of contents and anchors move within the window,
Back returns, and a link that leaves the guide is never opened: a web link is copied to the
clipboard and said, any other link is refused and said."""

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytestmark = pytest.mark.gui

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from harness_design_studio.gui import strings  # noqa: E402
from harness_design_studio.gui.guide_window import GuideWindow, guide_css  # noqa: E402
from harness_design_studio.gui.theme import ThemeManager  # noqa: E402
from harness_design_studio.resources import guide_path  # noqa: E402
from tests.test_accessibility import unnamed  # noqa: E402


@pytest.fixture
def guide(qtbot):
    path = guide_path()
    assert path is not None
    win = GuideWindow(ThemeManager(), None, path=path)
    qtbot.addWidget(win)
    win.copied = []  # type: ignore[attr-defined]
    win.copier = win.copied.append  # type: ignore[attr-defined]
    win.show()
    QApplication.processEvents()
    return win


def _top(win: GuideWindow) -> int:
    return win.browser.verticalScrollBar().value()


def test_the_window_shows_the_bundled_guide_beside_the_editor(guide) -> None:
    assert guide.blocks is False and not guide.isModal()
    text = guide.browser.toPlainText()
    assert "Harness Design Studio: user guide" in text
    assert "Keyboard and menus" in text  # the table of contents and the last sections are there
    assert guide.browser.document().find("Glossary").position() > 0
    assert guide.status.text() == strings.GUIDE_HINT
    assert unnamed(guide) == []
    for b in (guide.back_btn, guide.contents_btn, guide.close_btn):
        assert b.toolTip(), b.objectName()


def test_the_table_of_contents_moves_within_the_window_and_back_returns(guide) -> None:
    index = guide.browser.source()
    assert _top(guide) == 0 and not guide.back_btn.isEnabled()
    assert guide.follow(QUrl("#outputs")) == "followed"
    QApplication.processEvents()
    assert guide.browser.source().fragment() == "outputs"
    assert guide.browser.source().toLocalFile() == index.toLocalFile()  # the same page
    assert _top(guide) > 0  # scrolled down to the section
    assert guide.back_btn.isEnabled()
    guide.back_btn.click()
    QApplication.processEvents()
    assert guide.browser.source().fragment() == ""
    guide.follow(QUrl("#glossary"))
    guide.contents_btn.click()
    QApplication.processEvents()
    assert _top(guide) == 0
    assert guide.copied == []


def test_a_web_link_is_copied_to_the_clipboard_and_never_opened(guide) -> None:
    before = guide.browser.source()
    assert guide.follow(QUrl("https://example.org/datasheet")) == "copied"
    assert guide.copied == ["https://example.org/datasheet"]
    assert guide.status.text() == strings.LINK_COPIED.format("https://example.org/datasheet")
    assert guide.browser.source() == before  # the window stays on the guide


@pytest.mark.parametrize(
    "link",
    [
        "mailto:plans@example.org",
        "ftp://example.org/x",
        "javascript:alert(1)",
        "file:///etc/passwd",
    ],
)
def test_any_other_link_out_of_the_guide_is_refused(guide, link: str) -> None:
    before = guide.browser.source()
    assert guide.follow(QUrl(link)) == "refused"
    assert guide.copied == []
    assert guide.status.text() == strings.GUIDE_LINK_REFUSED.format(QUrl(link).toString())
    assert guide.browser.source() == before


def test_a_file_beside_the_guide_folder_is_not_a_page_of_the_guide(guide, tmp_path: Path) -> None:
    other = tmp_path / "other.html"
    other.write_text("<p>not the guide</p>", encoding="utf-8")
    assert guide.in_guide(QUrl.fromLocalFile(str(other))) is None
    assert guide.follow(QUrl.fromLocalFile(str(other))) == "refused"
    assert "not the guide" not in guide.browser.toPlainText()


def test_the_document_gets_the_theme_colours(qtbot) -> None:
    theme = ThemeManager()
    css = guide_css(theme)
    assert theme.color("accent").name() in css and "border" in css
    win = GuideWindow(theme, None, path=guide_path())
    qtbot.addWidget(win)
    assert win.browser.document().defaultStyleSheet() == css


def test_without_a_guide_the_window_is_empty_and_follows_nothing(qtbot) -> None:
    win = GuideWindow(ThemeManager(), None, path=None)
    qtbot.addWidget(win)
    assert win.follow(QUrl("#outputs")) == "refused"
