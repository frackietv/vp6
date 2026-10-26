"""Capture the IDE process's own stdout and stderr for the Output window,
without Qt (the IDE's ``outputcapture`` posts the text to its window).

Replacing ``sys.stdout`` would miss libraries that write to the file
descriptors directly (Qt's warnings, C extensions), so capture happens at
the descriptor level: each descriptor (1 and 2) is pointed at a pipe with
``os.dup2``, and a reader thread per pipe

* copies everything to the original descriptor, so a terminal that started
  the IDE still shows it, and
* hands the decoded text to the Output window (``attach``).

Text that arrives before the window exists is kept and replayed when
``attach`` is called, so startup messages aren't lost.
"""

from __future__ import annotations

import codecs
import os
import sys
import threading
from collections import deque

HISTORY_CHUNKS = 5000  # text kept for replaying when a window attaches


class OutputCapture:
    def __init__(self, streams: tuple[tuple[int, str], ...] = ((1, "out"), (2, "err"))):
        self._lock = threading.Lock()
        self._history: deque[tuple[str, str]] = deque(maxlen=HISTORY_CHUNKS)
        self._post = None  # post(function, *args): runs it on the main thread (attach)
        self._append = None
        self._saved: list[tuple[int, int]] = []  # (captured fd, duplicate of the original)
        self._threads: list[threading.Thread] = []
        self._flush_python_streams()
        for fd, kind in streams:
            original = os.dup(fd)
            read_end, write_end = os.pipe()
            os.dup2(write_end, fd)
            os.close(write_end)  # fd itself is now the only write end
            self._saved.append((fd, original))
            thread = threading.Thread(target=self._pump, args=(read_end, original, kind),
                                      name=f"vp6-output-{fd}", daemon=True)
            thread.start()
            self._threads.append(thread)
        # Python's own streams: flush each line so output shows up promptly
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(line_buffering=True)
            except (AttributeError, ValueError):
                pass

    @staticmethod
    def _flush_python_streams() -> None:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (AttributeError, ValueError, OSError):
                pass

    def _pump(self, read_end: int, original: int, kind: str) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            try:
                data = os.read(read_end, 65536)
            except OSError:
                break
            if not data:  # the descriptor was restored: no writers left
                break
            try:
                os.write(original, data)  # tee to the terminal (if there is one)
            except OSError:
                pass
            text = decoder.decode(data)
            if text:
                self._deliver(text, kind)
        os.close(read_end)

    def _deliver(self, text: str, kind: str) -> None:
        with self._lock:
            self._history.append((text, kind))
            post, append = self._post, self._append
        if post is not None:
            try:
                post(append, text, kind)
            except RuntimeError:  # the window is gone (shutting down)
                pass

    def attach(self, append, post) -> None:
        """Send all captured text (so far and from now on) to
        ``append(text, kind)``, which ``post(function, *args)`` runs on the
        main thread (the readers are threads of their own). Call it from the
        main thread."""
        with self._lock:
            history = list(self._history)
            self._post, self._append = post, append
        for text, kind in history:
            append(text, kind)

    def stop(self) -> None:
        """Restore the original descriptors. The reader threads then see the
        end of their pipes and finish."""
        self._flush_python_streams()
        with self._lock:
            self._post = self._append = None
        for fd, original in self._saved:
            os.dup2(original, fd)
        # Close the duplicates only after the readers finished: they write to
        # them, and a closed descriptor number can be reused by another file.
        for thread in self._threads:
            thread.join(timeout=1)
        for (_fd, original), thread in zip(self._saved, self._threads):
            if not thread.is_alive():  # still draining: leave it open rather than race
                os.close(original)
        self._saved.clear()
        self._threads.clear()
