"""Edit and Continue: a module's new source applied to the running program.

``apply(module, source)`` runs the new source in the module's own namespace,
then puts back what the program already had, updated:

* **functions** keep their identity (whatever refers to them, a form's event
  handler, a function imported by another module, a callback, sees the
  change): the old function object gets the new code, defaults and
  docstring. Where that can't be (its closure changed), the new function
  takes its place, its ``__class__`` cell pointing to the class the program
  has.
* **classes** keep their identity too (the forms the program made are
  theirs): their methods (and static and class methods, and properties'
  functions) are updated the same way, new ones are added, removed ones go;
  class variables keep their values, new ones are added. Nested classes too.
* **module variables** keep the program's values (its state); new ones are
  added. Names in capitals (``MAX_ITEMS``) are constants: they take the new
  value.

A procedure that is running (on the paused program's stack) goes on with its
old code: the change applies from its next call (``Report.running``). A
syntax error, or an error running the module's code, changes nothing.
"""

from __future__ import annotations

import linecache
import types
from dataclasses import dataclass, field

_CLASS_SKIP = {"__dict__", "__weakref__", "__module__", "__qualname__"}


@dataclass
class Report:
    changed: list[str] = field(default_factory=list)  # the qualified names updated
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    running: list[str] = field(default_factory=list)  # changed, but running: next call
    error: str | None = None  # nothing applied


def apply(module: types.ModuleType, source: str, filename: str | None = None,
          running_code: set | None = None) -> Report:
    """Apply a module's new source (the module's documentation). ``running_code``:
    the code objects of the paused program's frames."""
    report = Report()
    filename = filename or module.__file__
    try:
        code = compile(source, filename, "exec", dont_inherit=True)  # (not our __future__)
    except SyntaxError as exc:
        report.error = f"SyntaxError: {exc.msg} (line {exc.lineno})"
        return report
    namespace = module.__dict__
    before = dict(namespace)
    old_code = _code_by_name(before, module.__name__)
    try:
        exec(code, namespace)
    except Exception as exc:  # noqa: BLE001 - the module's own error: nothing changes
        namespace.clear()
        namespace.update(before)
        report.error = f"{type(exc).__name__}: {exc}"
        return report
    for name, old in before.items():
        new = namespace.get(name, old)
        if new is old:
            continue
        if _is_function(old, module) and isinstance(new, types.FunctionType):
            namespace[name] = _update_function(old, new, None, report)
        elif _is_class(old, module) and isinstance(new, type):
            _update_class(old, new, report)
            namespace[name] = old
        elif isinstance(old, (types.ModuleType, type, types.FunctionType)) or callable(old):
            pass  # (an import, or something else's: the new binding)
        elif not name.isupper():
            namespace[name] = old  # a variable: the program's value
    for name, new in namespace.items():
        if name not in before and (isinstance(new, (types.FunctionType, type))):
            report.added.append(f"{module.__name__}.{name}")
    if running_code:
        report.running = sorted(name for name, code in old_code.items()
                                if code in running_code and name in report.changed)
    # Tracebacks and the debugger see the new lines
    lines = source.splitlines(keepends=True)
    linecache.cache[filename] = (len(source), None, lines, filename)
    return report


def _is_function(value, module) -> bool:
    return isinstance(value, types.FunctionType) and value.__module__ == module.__name__


def _is_class(value, module) -> bool:
    return isinstance(value, type) and value.__module__ == module.__name__


def _update_function(old, new, owner: type | None, report: Report):
    """Give ``old`` the new function's code (it stays the one the program
    knows); returns the function to keep (``new`` when that can't be)."""
    if old.__code__ == new.__code__ and old.__defaults__ == new.__defaults__:
        return old
    name = old.__qualname__
    if old.__code__.co_freevars == new.__code__.co_freevars:
        old.__code__ = new.__code__
        old.__defaults__ = new.__defaults__
        old.__kwdefaults__ = new.__kwdefaults__
        old.__doc__ = new.__doc__
        old.__annotations__ = new.__annotations__
        report.changed.append(name)
        return old
    report.changed.append(name)
    return _rebound(new, owner) if owner is not None else new


def _rebound(function, owner: type):
    """A new method whose ``__class__`` cell (super()) is the class the program
    has, not the one the new source made."""
    if not function.__closure__:
        return function
    cells = tuple(types.CellType(owner) if name == "__class__" else cell
                  for name, cell in zip(function.__code__.co_freevars, function.__closure__))
    rebuilt = types.FunctionType(function.__code__, function.__globals__, function.__name__,
                                 function.__defaults__, cells)
    rebuilt.__kwdefaults__ = function.__kwdefaults__
    rebuilt.__qualname__ = function.__qualname__
    rebuilt.__doc__ = function.__doc__
    return rebuilt


def _update_member(old, new, owner: type, report: Report):
    """A class's attribute: the one to keep."""
    if isinstance(old, types.FunctionType) and isinstance(new, types.FunctionType):
        return _update_function(old, new, owner, report)
    for kind in (staticmethod, classmethod):
        if isinstance(old, kind) and isinstance(new, kind):
            kept = _update_member(old.__func__, new.__func__, owner, report)
            return old if kept is old.__func__ else kind(kept)
    if isinstance(old, property) and isinstance(new, property):
        parts = [_update_member(o, n, owner, report) if o is not None and n is not None else n
                 for o, n in ((old.fget, new.fget), (old.fset, new.fset), (old.fdel, new.fdel))]
        if all(kept is was for kept, was in zip(parts, (old.fget, old.fset, old.fdel))):
            return old
        return property(*parts, doc=new.__doc__)
    if isinstance(old, type) and isinstance(new, type) and old.__qualname__ == new.__qualname__:
        _update_class(old, new, report)
        return old
    if callable(new) or isinstance(new, (staticmethod, classmethod, property)):
        return new  # (a function where there was something else: the new one)
    return old  # a class variable: the program's value


def _update_class(old: type, new: type, report: Report) -> None:
    for name, value in vars(new).items():
        if name in _CLASS_SKIP:
            continue
        if name not in vars(old):
            setattr(old, name, _rebound(value, old) if isinstance(value, types.FunctionType)
                    else value)
            if callable(value) or isinstance(value, (staticmethod, classmethod, property)):
                report.added.append(f"{old.__qualname__}.{name}")
            continue
        current = vars(old)[name]
        kept = _update_member(current, value, old, report)
        if kept is not current:
            setattr(old, name, kept)
    for name, value in list(vars(old).items()):  # procedures taken out of the source
        if name not in vars(new) and name not in _CLASS_SKIP and \
                isinstance(value, (types.FunctionType, staticmethod, classmethod, property)):
            delattr(old, name)
            report.removed.append(f"{old.__qualname__}.{name}")
    if new.__doc__ != old.__doc__:
        try:
            old.__doc__ = new.__doc__
        except (AttributeError, TypeError):
            pass


def _code_by_name(namespace: dict, module_name: str) -> dict:
    """The code objects of a module's functions and methods, by qualified name."""
    found = {}

    def visit_class(cls):
        for value in vars(cls).values():
            function = value.__func__ if isinstance(value, (staticmethod, classmethod)) \
                else value
            if isinstance(function, types.FunctionType):
                found[function.__qualname__] = function.__code__
            elif isinstance(value, property):
                for part in (value.fget, value.fset, value.fdel):
                    if isinstance(part, types.FunctionType):
                        found[part.__qualname__] = part.__code__
            elif isinstance(value, type) and value.__module__ == module_name:
                visit_class(value)

    for value in namespace.values():
        if isinstance(value, types.FunctionType) and value.__module__ == module_name:
            found[value.__qualname__] = value.__code__
        elif isinstance(value, type) and value.__module__ == module_name:
            visit_class(value)
    return found
