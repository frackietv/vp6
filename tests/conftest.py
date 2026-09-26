import os

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


def wait_for(predicate, timeout_ms=5000):
    """Process events until predicate() is true (PySide has no QTest.qWaitFor)."""
    from PySide6.QtCore import QDeadlineTimer
    from PySide6.QtTest import QTest

    deadline = QDeadlineTimer(timeout_ms)
    while not predicate():
        if deadline.hasExpired():
            raise AssertionError("timed out waiting for condition")
        QTest.qWait(10)
