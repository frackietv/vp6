"""Capture the IDE process's own stdout and stderr for the Output window.

Replacing ``sys.stdout`` would miss libraries that write to the file
descriptors directly (Qt's warnings, C extensions), so capture happens at
the descriptor level: each descriptor (1 and 2) is pointed at a pipe with
``os.dup2``, and a reader thread per pipe

* copies everything to the original descriptor, so a terminal that started
  the IDE still shows it, and
* hands the decoded text to the Output window.

Text that arrives before the window exists is kept and replayed when
``attach`` is called, so startup messages aren't lost.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from .logic import capture
from .logic.capture import HISTORY_CHUNKS  # noqa: F401


class _Relay(QObject):
    """Carries text from the reader threads to the GUI thread (queued
    signal)."""

    received = Signal(object, str, str)  # append, text, kind ("out" or "err")


class OutputCapture(capture.OutputCapture):
    """The shared capture (``logic.capture``), its text posted to the GUI
    thread through a queued signal."""

    def attach(self, append, post=None) -> None:
        """Send all captured text (so far and from now on) to
        ``append(text, kind)``; it runs in the GUI thread. Call from the GUI
        thread, after the QApplication exists."""
        if post is None:
            self._relay = relay = _Relay()
            relay.received.connect(lambda function, text, kind: function(text, kind))
            post = relay.received.emit
        super().attach(append, post)
