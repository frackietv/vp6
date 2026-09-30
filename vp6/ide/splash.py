"""The splash screen shown while the IDE starts: the VP6 logo and version.

It shows for DURATION milliseconds and then closes itself; the user can't
move, resize or close it (it has no frame, and clicks, keys and close
requests are ignored). ``vp6 --no-splash`` starts without it.
"""

from __future__ import annotations

from PySide6.QtCore import QEventLoop, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

import vp6

from .dialogs import logo_pixmap

DURATION = 2000  # milliseconds
BACKGROUND = "#c0c0c0"
VERSION_COLOR = "#34495e"  # dark blue-grey, whatever the light/dark appearance


class SplashScreen(QWidget):
    """The logo with the version centered under it, in a frameless window."""

    finished = Signal()

    def __init__(self, duration: int | None = None):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.duration = DURATION if duration is None else duration
        self.done = False
        # Its own colors: the palette's text color would be white in Dark (the OS's, or
        # the IDE's, applied while the splash screen shows), on the light grey background
        self.setStyleSheet(f"* {{ background-color: {BACKGROUND}; color: {VERSION_COLOR}; }}")
        frame = QFrame(self)  # a thin border around it
        frame.setObjectName("splash")
        frame.setStyleSheet("QFrame#splash { border: 1px solid palette(mid); }")
        self.logo = QLabel()
        self.logo.setPixmap(logo_pixmap())
        self.logo.setAlignment(Qt.AlignCenter)
        self.version = QLabel(f"VP6 {vp6.__version__}")
        self.version.setAlignment(Qt.AlignCenter)
        font = self.version.font()
        font.setPointSize(font.pointSize() + 4)
        font.setBold(True)
        self.version.setFont(font)
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(32, 28, 32, 24)
        inner.setSpacing(12)
        inner.addWidget(self.logo)
        inner.addWidget(self.version)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self.setFixedSize(self.sizeHint())  # not resizable
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.finish)

    def start(self) -> None:
        """Show it in the middle of the screen, for ``duration``."""
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.center() - self.rect().center())
        self.show()
        self.raise_()
        self._timer.start(self.duration)

    def finish(self) -> None:
        """Its time is up: close it."""
        self.done = True
        self._timer.stop()
        self.close()
        self.finished.emit()

    def wait(self) -> None:
        """Keep the application running (e.g. the IDE window being built
        meanwhile) until the splash screen has finished."""
        if self.done:
            return
        loop = QEventLoop()
        self.finished.connect(loop.quit)
        loop.exec()

    # -- the user can't close it --------------------------------------------------------------
    def closeEvent(self, event):
        if self.done:
            event.accept()
        else:
            event.ignore()  # Cmd+W, Alt+F4...: only the timer closes it

    def mousePressEvent(self, event):
        event.accept()  # (a click doesn't close it, nor start a drag)

    def keyPressEvent(self, event):
        event.accept()  # (nor does Esc)
