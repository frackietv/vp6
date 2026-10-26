"""Where the IDE's logic keeps its settings: the IDE says (``use``).

The IDE gives its QSettings (``ide_settings``, by default, from the moment
its modules are imported); ``use`` can choose another store. A settings object has ``value(key, default)``,
``setValue(key, value)`` and ``remove(key)``; keys are paths such as
``claude/titles/<session id>``. Without an IDE they are kept in memory.
"""

from __future__ import annotations

from typing import Callable


class MemorySettings:
    """Settings kept in a dictionary (no IDE has given its own)."""

    def __init__(self):
        self.values: dict[str, object] = {}

    def value(self, key: str, default=None):
        return self.values.get(key, default)

    def setValue(self, key: str, value) -> None:  # noqa: N802 - QSettings' name
        self.values[key] = value

    def remove(self, key: str) -> None:
        for name in [k for k in self.values if k == key or k.startswith(key + "/")]:
            del self.values[name]


_memory = MemorySettings()
_default: Callable[[], object] = lambda: _memory  # noqa: E731
_chosen: Callable[[], object] | None = None


def use(provider: Callable[[], object] | None) -> None:
    """Keep the settings in what ``provider()`` gives (called each time they
    are read or written, so it can follow the IDE's settings file); None:
    the default again."""
    global _chosen
    _chosen = provider


def use_by_default(provider: Callable[[], object]) -> None:
    """The settings when none were chosen (``use``): the IDE's, from the
    moment its modules are imported."""
    global _default
    _default = provider


def settings():
    """The settings object of the IDE in use."""
    return (_chosen or _default)()
