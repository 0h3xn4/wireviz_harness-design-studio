# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
"""The one place where the editor hands a web address to the system browser (3.0.0, design of the
harness plan section 10: the link of a part and the source link of a connector, opened on a
person's click).

A link is opened only when the model's own rule accepts it (`devices.check_web_link`: `https://`
or `http://`, no spaces, at most 2000 characters) and Qt parses it strictly as a valid address with
that scheme. Anything else (a `file:` or `javascript:` address, a path, a text with spaces) is not
opened, and the caller gets False. The tool itself never connects anywhere: the browser opens the
page, on the person's click. `tests/test_security.py` allows `QDesktopServices` in this module
only, beside the local files of the guide and the export.
"""

from collections.abc import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from harness_design_studio.core.devices import check_web_link
from harness_design_studio.core.edit import EditError

WEB_SCHEMES = ("https", "http")


def web_url(link: object) -> QUrl | None:
    """The address to open for `link`, or None when it is not a web link the model accepts."""
    try:
        checked = check_web_link(link, "The link")
    except EditError:
        return None
    if checked is None:
        return None
    url = QUrl(checked, QUrl.ParsingMode.StrictMode)
    if not url.isValid() or url.scheme().lower() not in WEB_SCHEMES or not url.host():
        return None
    return url


def system_opener(url: QUrl) -> bool:
    """Hand `url` to the system's browser (the default opener; tests pass their own)."""
    return bool(QDesktopServices.openUrl(url))


def open_web_link(link: object, opener: Callable[[QUrl], bool] = system_opener) -> bool:
    """Open `link` in the browser when it is a web link the model accepts; False otherwise."""
    url = web_url(link)
    if url is None:
        return False
    return bool(opener(url))
