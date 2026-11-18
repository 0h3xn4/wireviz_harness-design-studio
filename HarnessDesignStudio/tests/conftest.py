# SPDX-FileCopyrightText: 2026 0h3xn4
# SPDX-License-Identifier: GPL-3.0-only
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The real-platform lane on Linux (`harness-real-platform.yml`) runs its tests in
# parallel workers under `xvfb-run`. One X display has one pointer: `QTest.mouseMove` on `xcb` moves
# it (`QCursor::setPos`), so a move of one worker reached the window of another worker's test and
# took its hover away (`test_the_pointer_over_a_port_lights_it_and_shows_the_open_hand`, seen once
# in CI and made to fail at will by a second process that moves the pointer). Each worker therefore
# starts a virtual display of its own, with the screen of the lane, before Qt starts.
LANE_SCREEN = "3840x2160x24"
_OWN_DISPLAY: subprocess.Popen[bytes] | None = None


def _own_display() -> subprocess.Popen[bytes] | None:
    """A new Xvfb for this pytest-xdist worker of the `xcb` lane (None anywhere else)."""
    if os.environ.get("HARNESS_REAL_PLATFORM") != "xcb" or not os.environ.get(
        "PYTEST_XDIST_WORKER"
    ):
        return None
    xvfb = shutil.which("Xvfb")
    if xvfb is None:
        return None  # the shared display of `xvfb-run` is used, as before
    read, write = os.pipe()
    server = subprocess.Popen(
        [xvfb, "-displayfd", str(write), "-screen", "0", LANE_SCREEN, "-nolisten", "tcp"],
        pass_fds=(write,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os.close(write)
    with os.fdopen(read, "rb") as answer:
        number = answer.readline().strip().decode("ascii")  # written once the display is ready
    if not number.isdigit():
        server.kill()
        raise RuntimeError("Xvfb did not start a display for this worker")
    os.environ["HARNESS_SHARED_DISPLAY"] = os.environ.get("DISPLAY", "")
    os.environ["DISPLAY"] = f":{number}"
    return server


def _stop_own_display() -> None:
    if _OWN_DISPLAY is not None and _OWN_DISPLAY.poll() is None:
        _OWN_DISPLAY.terminate()
        try:
            _OWN_DISPLAY.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _OWN_DISPLAY.kill()


_OWN_DISPLAY = _own_display()
atexit.register(_stop_own_display)

# Safety net: a test that builds the editor with the default settings must not read or write the
# developer's own ~/.config (the role, window geometry). Qt resolves the per-user ini
# folder from XDG_CONFIG_HOME on Linux.
_CONFIG_HOME = tempfile.mkdtemp(prefix="harness-tests-config-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_HOME
atexit.register(shutil.rmtree, _CONFIG_HOME, ignore_errors=True)

# Every process (the one that runs pytest and each pytest-xdist worker) imports this file and so has
# its own folder, which keeps parallel workers from sharing one settings file. A worker ends without
# running the atexit hook, so the folder is removed when pytest unconfigures as well.


def pytest_unconfigure(config: object) -> None:
    shutil.rmtree(_CONFIG_HOME, ignore_errors=True)
    _stop_own_display()


@pytest.fixture(autouse=True)
def _trust_store_in_a_temp_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The list of trusted Python plug-ins is kept in the user's settings folder (S8). A test never
    reads or writes the real one: each test gets an empty store of its own."""
    monkeypatch.setenv("HARNESS_DESIGN_STUDIO_CONFIG_DIR", str(tmp_path_factory.mktemp("trust")))


@pytest.fixture(autouse=True)
def _no_plugin_switch_of_this_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python plug-ins can be switched off on a computer: by an environment variable
    or a machine-wide policy file. A test does not see the switch of the computer it runs on; the
    tests of the switch set it themselves."""
    from harness_design_studio.core.extensions import policy

    monkeypatch.delenv(policy.ENV_NO_PLUGINS, raising=False)
    nowhere = Path(_CONFIG_HOME) / "no-policy-here" / "policy.json"  # never created
    monkeypatch.setattr(policy, "policy_path", lambda: nowhere)


@pytest.fixture(autouse=True)
def _electrical_role_for_a_new_settings_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A settings file with no values asks who the person is working as (D-176), and a window that
    is shown waits for the answer. The tests build their windows on a new file, so they get the
    Electrical / AIT engineer role (every area, the diagram first) through the hook the program
    has for this, and no question, unless a test asks for the real default (`roles.FIRST_RUN_ROLE`
    None)."""
    from harness_design_studio.gui import roles

    monkeypatch.setattr(roles, "FIRST_RUN_ROLE", "electrical")


@pytest.fixture(autouse=True)
def _collect_cycles_between_tests() -> Iterator[None]:
    """Once the editor has started (a test built a controller) the automatic garbage collector is
    off and a timer on the GUI thread runs it (`gui/gc_policy.py`). A test does not wait for that
    timer, so the collection that is due runs here, on the test's own thread, after each test."""
    yield
    policy = sys.modules.get("harness_design_studio.gui.gc_policy")
    if policy is not None and policy.installed():
        policy.collect_if_due()


@pytest.fixture(autouse=True)
def _close_the_windows_a_test_left_open() -> Iterator[None]:
    """Delete the top-level widgets a test created and did not close (most GUI tests build a
    window and walk away). Each one kept its timers and its child widgets alive for the rest of
    the process, so later tests got slower and slower (a layout test took 77 s after 160 left-over
    windows and 8 s on its own) and a worker grew to several GB. Windows that exist before the
    test starts (those of module-scoped fixtures) are left alone; the editor's own clean-up
    (`ctl.release`: timers, helper process, project lock) runs first."""
    if "PySide6.QtWidgets" not in sys.modules:
        yield  # a test that never imports Qt has nothing to close
        return
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    # the list keeps their Python objects alive; before the first test there is no application
    before = QApplication.topLevelWidgets() if QApplication.instance() else []
    yield
    app = QApplication.instance()
    if app is None:
        return
    _release_stray_modifiers(app)
    for widget in QApplication.topLevelWidgets():
        if widget in before:
            continue
        release = getattr(getattr(widget, "ctl", None), "release", None)
        if callable(release):
            release()
        widget.hide()
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _release_stray_modifiers(app: object) -> None:
    """`QTest.keyClick(w, key, Ctrl|Shift)` can leave Shift (or another modifier) pressed as far as
    `QGuiApplication.keyboardModifiers()` goes. A table with extended selection reads that state in
    `selectRow`, so the next test's selection came out toggled or empty. Release what is left."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget

    held = QGuiApplication.keyboardModifiers()
    if held == Qt.KeyboardModifier.NoModifier:
        return
    target = QWidget()
    for modifier, key in (
        (Qt.KeyboardModifier.ShiftModifier, Qt.Key.Key_Shift),
        (Qt.KeyboardModifier.ControlModifier, Qt.Key.Key_Control),
        (Qt.KeyboardModifier.AltModifier, Qt.Key.Key_Alt),
        (Qt.KeyboardModifier.MetaModifier, Qt.Key.Key_Meta),
    ):
        if held & modifier:
            QTest.keyRelease(target, key)
    target.deleteLater()
