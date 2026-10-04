"""Edit and Continue's patching (vp6.hotpatch): a module's new source applied
to the objects the program already has."""

import linecache
import sys
import types

import pytest

from vp6 import hotpatch

SOURCE = '''
MAX_ITEMS = 3
count = 0
items = []


def helper(x):
    return x + 1


def closure_maker():
    def inner():
        return 1
    return inner


class Base:
    def hello(self):
        return "base"


class Form1(Base):
    clicks = 0

    def hello(self):
        return "one " + super().hello()

    @property
    def doubled(self):
        return self.clicks * 2

    @staticmethod
    def kind():
        return "static one"

    @classmethod
    def made(cls):
        return cls.__name__ + " one"

    def gone(self):
        return "gone"

    class Inner:
        def where(self):
            return "inner one"
'''


@pytest.fixture
def module(tmp_path):
    path = tmp_path / "Mod1.py"
    path.write_text(SOURCE)
    module = types.ModuleType("Mod1")
    module.__file__ = str(path)
    sys.modules["Mod1"] = module
    exec(compile(SOURCE, str(path), "exec"), module.__dict__)
    yield module
    sys.modules.pop("Mod1", None)


def _edit(source, *pairs):
    for old, new in pairs:
        assert old in source
        source = source.replace(old, new)
    return source


def test_functions_and_classes_keep_their_identity(module):
    helper, form_class, inner_class = module.helper, module.Form1, module.Form1.Inner
    form = module.Form1()
    form.clicks = 5
    new = _edit(SOURCE, ("x + 1", "x + 100"), ('"one "', '"two "'), ("* 2", "* 3"),
                ('"static one"', '"static two"'), ('" one"', '" two"'),
                ('"inner one"', '"inner two"'))
    report = hotpatch.apply(module, new)
    assert report.error is None
    assert module.helper is helper and helper(1) == 101  # (whoever holds it sees it)
    assert module.Form1 is form_class and module.Form1.Inner is inner_class
    assert form.hello() == "two base"  # (the program's form: super() still works)
    assert form.doubled == 15 and form_class.kind() == "static two"
    assert form_class.made() == "Form1 two" and inner_class().where() == "inner two"
    assert set(report.changed) == {"helper", "Form1.hello", "Form1.doubled", "Form1.kind",
                                   "Form1.made", "Form1.Inner.where"}  # (only what changed)


def test_added_and_removed(module):
    form = module.Form1()
    new = _edit(SOURCE, ('''    def gone(self):
        return "gone"
''', '''    def fresh(self):
        return "fresh " + super().hello()
'''), ("def closure_maker", "def added():\n    return 'added'\n\n\ndef closure_maker"))
    report = hotpatch.apply(module, new)
    assert not hasattr(form, "gone") and form.fresh() == "fresh base"  # (super(): the class)
    assert module.added() == "added"
    assert "Form1.fresh" in report.added and "Mod1.added" in report.added
    assert report.removed == ["Form1.gone"]


def test_variables_keep_the_programs_values_constants_change(module):
    module.count = 9
    module.items.append("kept")
    module.Form1.clicks = 4
    new = _edit(SOURCE, ("MAX_ITEMS = 3", "MAX_ITEMS = 10"), ("count = 0", "count = 1"),
                ("clicks = 0", "clicks = 2\n    label = 'new'"))
    hotpatch.apply(module, new + "\nfresh_value = 7\n")
    assert module.MAX_ITEMS == 10  # (a constant: the new value)
    assert module.count == 9 and module.items == ["kept"]  # (the program's state)
    assert module.Form1.clicks == 4 and module.Form1.label == "new"
    assert module.fresh_value == 7


def test_a_closure_that_changes(module):
    maker = module.closure_maker
    new = _edit(SOURCE, ('''    def inner():
        return 1''', '''    value = 2

    def inner():
        return value'''))
    hotpatch.apply(module, new)
    assert module.closure_maker is maker and maker()() == 2


def test_a_method_whose_closure_changes_still_knows_its_class(module):
    form = module.Form1()
    new = _edit(SOURCE, ('''    def gone(self):
        return "gone"''', '''    def gone(self):
        return "now " + super().hello()'''))  # (__class__ cell: none before, one now)
    report = hotpatch.apply(module, new)
    assert form.gone() == "now base" and "Form1.gone" in report.changed


def test_errors_change_nothing(module):
    helper = module.helper
    module.count = 9
    report = hotpatch.apply(module, "def broken(:\n")
    assert report.error.startswith("SyntaxError") and "line 1" in report.error
    report = hotpatch.apply(module, _edit(SOURCE, ("x + 1", "x + 100")) +
                            "\nraise ValueError('no')\n")
    assert report.error == "ValueError: no"
    assert helper(1) == 2 and module.count == 9 and module.helper is helper


def test_running_procedures_and_the_new_lines(module):
    running = {module.helper.__code__}
    new = _edit(SOURCE, ("x + 1", "x + 100"), ('"one "', '"two "'))
    report = hotpatch.apply(module, new, running_code=running)
    assert report.running == ["helper"]  # (it goes on with its old code)
    assert linecache.getline(module.__file__, 8) == "    return x + 100\n"


def test_not_our_future_imports(module):
    """compile() would give the module this file's __future__ flags."""
    new = _edit(SOURCE, ("x + 1", "x + 2"), ("def helper(x):", "def helper(x: 'int'):"))
    hotpatch.apply(module, new)
    assert module.helper.__annotations__ == {"x": "int"}
    hotpatch.apply(module, _edit(SOURCE, ("def helper(x):", "def helper(x: int):")))
    assert module.helper.__annotations__ == {"x": int}  # (evaluated: no PEP 563)
