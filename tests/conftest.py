import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["VP6_NO_ERROR_DIALOG"] = "1"

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    # Keep IDE tests from touching the user's real QSettings
    from PySide6.QtCore import QSettings

    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(tmp_path / "settings"))
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / "settings"))
    from vp6.ide.theme import ide_settings, reset_theme_manager

    assert ide_settings().fileName().startswith(str(tmp_path)), "IDE settings are not isolated"
    reset_theme_manager()
    yield
    reset_theme_manager()  # undo any application-wide scheme a test forced


@pytest.fixture(autouse=True)
def _no_user_controls_left():
    """User controls registered by a test (an IDE project, a Kitchen Sink) are
    gone after it: the control types are the built-in ones again."""
    yield
    from vp6.usercontrol import unregister_user_controls

    unregister_user_controls()


@pytest.fixture(autouse=True)
def _fail_on_errors_in_qt_callbacks(monkeypatch):
    """An exception raised in Python code that Qt calls (an event handler
    override like mouseMoveEvent, a slot) doesn't reach the test: PySide
    prints it through sys.excepthook and carries on. Record those and fail
    the test, so such bugs can't hide behind a passing run."""
    errors = []

    def record(kind, value, tb):
        errors.append("".join(traceback.format_exception(kind, value, tb)))
        sys.__excepthook__(kind, value, tb)

    monkeypatch.setattr(sys, "excepthook", record)
    yield
    assert not errors, "Exception(s) in code called by Qt:\n" + "\n".join(errors)


def wait_for(predicate, timeout_ms=5000):
    """Process events until predicate() is true (PySide has no QTest.qWaitFor)."""
    from PySide6.QtCore import QDeadlineTimer
    from PySide6.QtTest import QTest

    deadline = QDeadlineTimer(timeout_ms)
    while not predicate():
        if deadline.hasExpired():
            raise AssertionError("timed out waiting for condition")
        QTest.qWait(10)
