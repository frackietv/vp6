"""VP6's help: made from its documents and code (vp6.helpdocs), shown by
ShowHelp, App.HelpFile and a CommonDialog's ShowHelp, and in the IDE (the
Help menu, and F1 on the code, a property, a control, a tool or the Object
Browser)."""

import os
import textwrap

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import vp6
from vp6 import helpdocs
from vp6.controls import CONTROL_TYPES
from vp6help import HelpFile, viewer
from vp6help.maker import HelpMaker


@pytest.fixture(scope="module")
def vp6_help():
    path = helpdocs.help_file()
    with HelpFile(path) as help_:
        yield help_


# --- VP6's help file ------------------------------------------------------------------------

def test_made_once_from_the_source():
    path = helpdocs.help_file()
    assert path.startswith(os.environ["VP6_HELP_DIR"])  # (the tests' own folder)
    made = os.path.getmtime(path)
    assert helpdocs.help_file() == path and os.path.getmtime(path) == made  # (kept)
    assert os.path.basename(path) == f"vp6-{helpdocs.sources_hash()[:16]}.vp6help"


def test_installed_help_comes_first(tmp_path, monkeypatch):
    (tmp_path / "help").mkdir()
    (tmp_path / "help" / "vp6.vp6help").write_bytes(b"")
    monkeypatch.setattr(helpdocs, "PACKAGE", str(tmp_path))
    assert helpdocs.help_file() == str(tmp_path / "help" / "vp6.vp6help")
    monkeypatch.setattr(helpdocs, "PACKAGE", str(tmp_path / "nowhere"))
    monkeypatch.setattr(helpdocs, "SOURCE_ROOT", str(tmp_path / "nowhere"))
    assert helpdocs.help_file() is None  # (neither installed nor the source)


def test_the_documents_and_the_reference(vp6_help):
    assert vp6_help.title == helpdocs.TITLE and vp6_help.home == "README.html"
    pages = [p["path"] for p in vp6_help.pages]
    documents = [d[:-3] + ".html" for d in helpdocs.DOCUMENTS]
    assert "packages/vp6help/README.html" in documents  # (help files: how to make them)
    assert pages[:len(documents)] == documents
    assert "python/index.html" in pages and "python/vp6.controls.html" in pages
    toc = [node["url"] for node in vp6_help.toc]
    assert toc == documents + ["python/index.html"]
    features = next(node for node in vp6_help.toc if node["url"] == "FEATURES.html")
    assert features["children"] == []  # (the release notes: one entry)


def test_every_control_and_public_name_has_help(vp6_help):
    # F1 finds them: a control's own section of the API reference first
    for name in CONTROL_TYPES:
        if name == "Menu":
            continue
        entries = vp6_help.lookup(name, case=True)
        assert entries and entries[0].url.startswith("docs/api.html#"), name
    missing = [name for name in vp6.__all__ if not vp6_help.lookup(name, case=True)]
    assert not missing, f"Not in the help's index: {missing}"
    assert vp6_help.lookup("MsgBox")[0].url == "docs/api.html#dialogs"
    assert vp6_help.search("AcceptsTab")


def test_make_help_from_a_source_folder(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(HelpMaker, "build", lambda self, output: calls.append(
        (self.title, [f.name for f in self._files], self._packages, output)) or {})
    helpdocs.make_help(str(tmp_path / "x.vp6help"))
    title, files, packages, output = calls[0]
    assert title == "VP6 Help" and files == [os.path.basename(d) for d in helpdocs.DOCUMENTS]
    assert packages[0][0] == ["vp6"] and output == str(tmp_path / "x.vp6help")


def test_the_wheel_gets_the_help():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    setup = open(os.path.join(root, "setup.py"), encoding="utf-8").read()
    assert "helpdocs.make_help(output, ROOT)" in setup and "editable_mode" in setup
    manifest = open(os.path.join(root, "MANIFEST.in"), encoding="utf-8").read()
    assert "recursive-include packages/vp6help/vp6help *.py" in manifest


# --- ShowHelp ---------------------------------------------------------------------------------

@pytest.fixture
def own_help(tmp_path):
    (tmp_path / "guide.md").write_text(textwrap.dedent("""\
        # My guide

        ## Saving

        **`SaveAll()`**

        Saves everything.
        """))
    maker = HelpMaker("Mine")
    maker.add(tmp_path / "guide.md")
    maker.build(tmp_path / "Mine.vp6help")
    return tmp_path / "Mine.vp6help"


def test_show_help(qapp, own_help, monkeypatch):
    window = vp6.ShowHelp(Keyword="TextBox")  # VP6's own help
    assert window.current_page() == "docs/api.html#textbox"
    window = vp6.ShowHelp(str(own_help), Keyword="SaveAll")
    assert window.help.title == "Mine" and window.current_page() == "guide.html#saving"
    assert vp6.ShowHelp(str(own_help), Search="every") is window
    assert window.tabs.currentIndex() == 2 and window.search_matches() == ["every"]
    vp6.ShowHelp(str(own_help), Search="SAVE", MatchCase=True)
    assert window.search_results.topLevelItemCount() == 0
    vp6.ShowHelp(str(own_help), Search=r"sav\w+", Regex=True)
    assert window.search_matches() == ["Saving", "SaveAll", "Saves"]
    vp6.ShowHelp(str(own_help), Page="guide.html")
    assert window.current_page() == "guide.html"
    # App.HelpFile: the program's help (relative: from its folder)
    monkeypatch.setattr(type(vp6.App), "Path", property(lambda self: str(own_help.parent)))
    monkeypatch.setattr(vp6.App, "HelpFile", "Mine.vp6help")
    assert vp6.ShowHelp() is window
    monkeypatch.setattr(vp6.App, "HelpFile", "Other.vp6help")
    with pytest.raises(FileNotFoundError):
        vp6.ShowHelp()


def test_common_dialog_shows_a_help_file(qapp, own_help, monkeypatch):
    form = vp6.Form()
    cdl = vp6.CommonDialog(form, "cdlHelp")
    cdl.HelpFile = str(own_help)
    opened = []
    monkeypatch.setattr("vp6.controls.QDesktopServices.openUrl", lambda url: opened.append(url))
    assert cdl.ShowHelp() and not opened  # (the contents, in VP6's help window)
    window = viewer._viewers[os.path.normcase(str(own_help))]
    assert window.tabs.currentIndex() == 0
    cdl.HelpCommand, cdl.HelpKey = vp6.vpHelpKey, "SaveAll"
    cdl.ShowHelp()
    assert window.current_page() == "guide.html#saving"
    cdl.HelpCommand, cdl.HelpKey = vp6.vpHelpPartialKey, "Sav"
    cdl.ShowHelp()
    assert window.tabs.currentIndex() == 1 and window.index_filter.text() == "Sav"
    cdl.HelpCommand, cdl.HelpKey = vp6.vpHelpSearch, "everything"
    cdl.ShowHelp()
    assert window.tabs.currentIndex() == 2 and window.search_results.topLevelItemCount() == 1
    form.Unload()


# --- the IDE ----------------------------------------------------------------------------------

@pytest.fixture
def ide(qapp, tmp_path):
    from vp6.ide.mainwindow import MainWindow, create_project

    window = MainWindow()
    window.show()
    window.open_project(create_project(str(tmp_path), "Demo", "exe"))
    form1 = os.path.join(tmp_path, "Demo", "Form1.py")
    designer = window._designer_for(form1)
    designer.create_control("TextBox", None, None)
    yield window, form1
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
    window.close()


def test_the_help_menu(ide):
    window, _ = ide
    menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Help")
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts[:4] == ["&Contents", "&Index", "&Search…", "Context &Help"]
    assert window.act_context_help.shortcut().toString() == "F1"
    window.act_help_contents.trigger()
    help_window = window.help_viewer
    assert help_window.isVisible() and help_window.tabs.currentIndex() == 0
    assert help_window.current_page() == "README.html"
    window.act_help_index.trigger()
    assert help_window.tabs.currentIndex() == 1
    window.act_help_search.trigger()
    assert help_window.tabs.currentIndex() == 2
    for doc in window.documents.values():
        doc.text_document.setModified(False)
    window.close_project()
    window.close()  # (the IDE closes its help)
    assert not help_window.isVisible()


def test_f1_in_the_code(ide):
    window, form1 = ide
    code = window.view_code(form1)
    editor = code.editor
    editor.setPlainText("def f(self):\n    self.Text1.SelStart = 0\n    MsgBox('x')\n")
    cursor = editor.textCursor()
    for word, expected in (("MsgBox", ("MsgBox", "")), ("SelStart", ("SelStart", "")),
                           ("Text1", ("TextBox", "")),  # a control of the form: its type
                           ("def", ("def", ""))):
        cursor.setPosition(editor.toPlainText().index(word) + 1)
        editor.setTextCursor(cursor)
        editor.setFocus()
        QApplication.processEvents()
        assert window.help_context() == expected, word
    cursor.setPosition(editor.toPlainText().index("MsgBox") + 2)
    editor.setTextCursor(cursor)
    help_window = window.context_help()
    assert help_window.current_page() == "docs/api.html#dialogs"


def test_f1_on_a_property_a_control_and_a_tool(ide):
    window, form1 = ide
    designer = window.view_object(form1)
    designer.select(["Text1"])
    designer.setFocus()
    QApplication.processEvents()
    assert window.help_context() == ("TextBox", "")
    window.properties.select_property("MaxLength")
    window.properties.table.setFocus()
    QApplication.processEvents()
    assert window.help_context() == ("MaxLength", "TextBox")
    help_window = window.context_help()
    assert help_window.current_page() == "docs/api.html#textbox"  # (TextBox's MaxLength)
    help_window.close()  # (F1 asks about the focus: it has it now)
    window.activateWindow()
    window.toolbox.buttons["Timer"].click()  # the tool chosen in the Toolbox
    window.toolbox.buttons["Timer"].setFocus(Qt.MouseFocusReason)
    QApplication.processEvents()
    assert window.current_tool == "Timer" and window.help_context() == ("Timer", "")


def test_f1_in_the_object_browser(ide):
    window, _ = ide
    browser = window.show_object_browser()
    assert browser.show_class("CommandButton", "Caption")
    browser.member_list.setFocus()
    QApplication.processEvents()
    if browser.member_list.hasFocus():
        assert window.help_context() == ("Caption", "CommandButton")
    browser.class_list.setFocus()
    QApplication.processEvents()
    if browser.class_list.hasFocus():
        assert window.help_context() == ("CommandButton", "")
    browser.close()


# --- vp6-make ---------------------------------------------------------------------------------

def test_executables_get_the_help(tmp_path):
    from vp6 import make
    from vp6.project import Project

    project = Project(name="Hello", type="console", path=str(tmp_path / "Hello.vp6p"))
    project.save()
    command = make.pyinstaller_command(project, "/w/launcher.py", "/d", "/w")
    data = [command[i + 1] for i, arg in enumerate(command) if arg == "--add-data"]
    assert f"{helpdocs.help_file()}{os.pathsep}vp6/help" in data
    hidden = [command[i + 1] for i, arg in enumerate(command) if arg == "--hidden-import"]
    assert "vp6help.viewer" in hidden
