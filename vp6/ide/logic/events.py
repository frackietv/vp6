"""``Event``: what the shared logic's objects tell their IDE, as Qt's signals do
(``connect``, ``disconnect``, ``emit``) but without Qt. The IDE passes them
on to its own signals."""

from __future__ import annotations


class Event:
    """A list of functions called, in order, with what is emitted."""

    def __init__(self):
        self._handlers: list = []

    def connect(self, handler) -> None:
        self._handlers.append(handler)

    def disconnect(self, handler=None) -> None:
        """Forget a handler (all of them without one)."""
        if handler is None:
            self._handlers.clear()
        elif handler in self._handlers:
            self._handlers.remove(handler)

    def emit(self, *args) -> None:
        for handler in list(self._handlers):
            handler(*args)

    def __len__(self) -> int:
        return len(self._handlers)
