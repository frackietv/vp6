"""Find and Replace in the code window, and Go to Line."""

import os

import pytest
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtWidgets import QInputDialog

from vp6 import formfile
from vp6.ide.codeeditor import CodeEditor
from vp6.ide.documents import Document, FormDocument
from vp6.ide.findreplace import (FindReplaceDialog, SearchOptions, compile_pattern, find_in,
                                 find_next, replace_all, replace_one)
from vp6.ide.mainwindow import MainWindow, create_project

TEXT = """first = 1
First = 2
firstly = 3
print(first, First)
"""


# --- the search -----------------------------------------------------------------------------

def _spans(text, options):
    return [m.span() for m in compile_pattern(options).finditer(text)]


def test_case_and_whole_word():
    assert len(_spans(TEXT, SearchOptions("first"))) == 5  # any case, also in "firstly"
    assert len(_spans(TEXT, SearchOptions("first", match_case=True))) == 3
    assert len(_spans(TEXT, SearchOptions("first", whole_word=True))) == 4
    assert len(_spans(TEXT, SearchOptions("first", match_case=True, whole_word=True))) == 2
    assert _spans("a.b ab", SearchOptions("a.b")) == [(0, 3)]  # literal without regex


def test_find_in_wraps_both_ways():
    pattern = compile_pattern(SearchOptions("x"))
    text = "x-x-x"
    assert find_in(text, pattern, 1)[0].start() == 2
    match, wrapped = find_in(text, pattern, 5)
    assert match.start() == 0 and wrapped
    assert find_in(text, pattern, 2, backward=True)[0].start() == 0
    match, wrapped = find_in(text, pattern, 0, backward=True)
    assert match.start() == 4 and wrapped
    assert find_in(text, pattern, 0, skip=(0, 1))[0].start() == 2  # not the selection again
    assert find_in("abc", pattern, 0) == (None, False)


def test_regular_expressions():
    # escape sequences: a match across lines
    assert _spans("a = 1\nb = 2\n", SearchOptions(r"1\nb", regex=True)) == [(4, 7)]
    # groups in the find text
    assert _spans("the the cat", SearchOptions(r"\b(\w+) \1\b", regex=True)) == [(0, 7)]
    # ^ and $ on every line
    assert len(_spans("a\nb\nc", SearchOptions(r"^\w$", regex=True))) == 3
    with pytest.raises(Exception):
        compile_pattern(SearchOptions("(", regex=True))


# --- in an editor ------------------------------------------------------------------------------

@pytest.fixture
def editor(qapp, tmp_path):
    path = tmp_path / "Module1.py"
    path.write_text(TEXT)
    return CodeEditor(Document(str(path)))


def _selected(editor):
    return editor.textCursor().selectedText()


def test_find_next_and_previous(editor):
    options = SearchOptions("first", match_case=True, whole_word=True)
    assert find_next(editor, options).found
    assert editor.textCursor().selectionStart() == 0
    assert find_next(editor, options).found
    assert editor.textCursor().selectionStart() == TEXT.index("(first") + 1
    result = find_next(editor, options)  # wraps to the top
    assert result.found and "end of the file" in result.message
    assert editor.textCursor().selectionStart() == 0
    result = find_next(editor, options, backward=True)  # and back to the bottom
    assert "beginning" in result.message
    assert editor.textCursor().selectionStart() == TEXT.index("(first") + 1
    assert not find_next(editor, SearchOptions("nothing")).found
    assert "Invalid regular expression" in find_next(editor, SearchOptions("(", regex=True)).message


def test_replace_one_and_all(editor):
    options = SearchOptions("First", "Second", match_case=True, whole_word=True)
    replace_one(editor, options)  # the first press only finds
    assert editor.toPlainText() == TEXT and _selected(editor) == "First"
    replace_one(editor, options)  # replaces it and finds the next one
    assert editor.toPlainText().startswith("first = 1\nSecond = 2\n")
    assert _selected(editor) == "First"
    result = replace_all(editor, SearchOptions("first", "one", whole_word=True))
    assert result.message == "Replaced 3 occurrences"
    assert editor.toPlainText() == "one = 1\nSecond = 2\nfirstly = 3\nprint(one, one)\n"
    editor.undo()  # Replace All is one undo step
    assert editor.toPlainText() == "first = 1\nSecond = 2\nfirstly = 3\nprint(first, First)\n"


def test_regex_replace_with_groups_and_escapes(editor):
    options = SearchOptions(r"^(?P<name>\w+) = (\d)$", r"\2\t\g<name>", regex=True)
    assert replace_all(editor, options).found
    assert editor.toPlainText().splitlines()[:3] == ["1\tfirst", "2\tFirst", "3\tfirstly"]
    replace_all(editor, SearchOptions(r"\n(?=print)", r"\n\n", regex=True))  # new lines
    assert "firstly\n\nprint" in editor.toPlainText()
    result = replace_all(editor, SearchOptions("first", r"\9", regex=True))
    assert not result.found and "Invalid replacement" in result.message


def test_positions_after_emoji(qapp, tmp_path):
    path = tmp_path / "Module1.py"
    path.write_text('greeting = "😀 hi"\nname = "hi"\n')
    editor = CodeEditor(Document(str(path)))
    options = SearchOptions("hi", whole_word=True)
    find_next(editor, options)
    assert _selected(editor) == "hi"
    find_next(editor, options)
    assert _selected(editor) == "hi" and editor.textCursor().blockNumber() == 1
    replace_all(editor, SearchOptions("hi", "yo", whole_word=True))
    assert editor.toPlainText() == 'greeting = "😀 yo"\nname = "yo"\n'


def test_replace_skips_the_designer_region(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1") + "\n# Form1 is the main form\n")
    editor = CodeEditor(FormDocument(str(path)))
    region = editor.doc.region_range()
    result = replace_all(editor, SearchOptions("Form1", "Main", whole_word=True))
    assert "skipped" in result.message and "designer region" in result.message
    assert "# Main is the main form" in editor.toPlainText()
    assert editor.doc.region_range() == region  # unchanged
    # Finding a match inside the folded region unfolds it
    editor.moveCursor(QTextCursor.Start)
    find_next(editor, SearchOptions("InitializeComponent"))
    assert editor.textCursor().block().isVisible() and not editor.region_folded
    assert "can't be changed" in replace_one(
        editor, SearchOptions("InitializeComponent", "Init")).message


def test_dialog(editor):
    dialog = FindReplaceDialog(lambda: editor)
    cursor = editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.KeepAnchor)
    editor.setTextCursor(cursor)
    dialog.show_find()  # Find: the selected text, no replace fields
    assert dialog.find_edit.text() == "first" and dialog.windowTitle() == "Find"
    assert dialog.replace_edit.isHidden() and dialog.replace_all_button.isHidden()
    dialog.show_find(replace=True)
    assert not dialog.replace_edit.isHidden() and dialog.windowTitle() == "Replace"
    dialog.whole_word.setChecked(True)
    dialog.replace_edit.setText("one")
    assert dialog.replace_all().message == "Replaced 4 occurrences"  # any case
    assert dialog.status.text() == "Replaced 4 occurrences"
    dialog.find_edit.setText("zzz")
    assert not dialog.find_next().found and "not found" in dialog.status.text()
    assert "Open a code window" in FindReplaceDialog(lambda: None).find_next().message
    dialog.close()


def test_dialog_highlights_the_first_match_as_you_type(editor):
    dialog = FindReplaceDialog(lambda: editor)
    dialog.show_find()
    editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(1)))  # line 2
    for text in ("f", "fi", "first"):  # the match grows as you type
        dialog.find_edit.setText(text)
        assert editor.textCursor().selectionStart() == TEXT.index("First")
        assert editor.textCursor().selectedText().lower() == text
        assert dialog.status.text() == ""
    dialog.find_edit.setText("firstly")  # no longer matches at "First": the next one
    assert editor.textCursor().selectedText() == "firstly"
    dialog.match_case.setChecked(True)  # options search again
    assert editor.textCursor().selectedText() == "firstly"
    dialog.find_edit.setText("FIRST")  # wraps around; not found: nothing selected
    assert not editor.textCursor().hasSelection() and "not found" in dialog.status.text()
    dialog.match_case.setChecked(False)
    assert editor.textCursor().selectedText() == "first"  # first = 1 comes after wrapping
    dialog.regex.setChecked(True)
    dialog.find_edit.setText("fir(")  # a regex still being typed: no jump, a message
    assert editor.textCursor().selectedText() == "first"
    assert "Invalid regular expression" in dialog.status.text()
    dialog.find_edit.clear()  # empty: the selection goes, the cursor stays
    assert not editor.textCursor().hasSelection()
    dialog.close()


# --- in the IDE ---------------------------------------------------------------------------------

@pytest.fixture
def ide(qapp, tmp_path):
    w = MainWindow()
    w.show()
    w.open_project(create_project(str(tmp_path), "Demo", "exe"))
    yield w
    for doc in w.documents.values():
        doc.text_document.setModified(False)
    w.close_project()
    w.close()


def test_edit_menu(ide):
    edit = next(a.menu() for a in ide.menuBar().actions() if a.text() == "&Edit")
    texts = [a.text() for a in edit.actions()]
    for text in ("&Find…", "Find &Next", "Find Pre&vious", "R&eplace…", "&Go to Line…"):
        assert text in texts
    assert not ide.act_find.shortcut().isEmpty() and not ide.act_replace.shortcut().isEmpty()
    # No clash with the Immediate window's Ctrl+G (Cmd+G on macOS)
    shortcuts = [k for act in ide.findChildren(QAction) for k in act.shortcuts()]
    assert len(shortcuts) == len(set(shortcuts))


def test_find_from_the_designer_opens_the_code(ide, tmp_path):
    form1 = os.path.join(tmp_path, "Demo", "Form1.py")
    assert ide.mdi.currentSubWindow().widget() is ide.designer_windows[form1].widget()
    ide.show_find()
    assert ide.mdi.currentSubWindow().widget() is ide.code_windows[form1].widget()
    ide.find_dialog.find_edit.setText("Form_Load")
    ide.find_next()  # F3
    editor = ide.code_windows[form1].widget().editor
    assert editor.textCursor().selectedText() == "Form_Load"
    ide.find_dialog.close()


def test_goto_line(ide, tmp_path, monkeypatch):
    module1 = os.path.join(tmp_path, "Demo", "Module1.py")
    editor = ide.view_code(module1).editor
    asked = []

    def get_int(parent, title, label, value, minimum, maximum, step):
        asked.append((title, label, value, minimum, maximum))
        return 3, True

    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(get_int))
    ide.act_goto_line.trigger()
    count = editor.document().blockCount()
    assert asked == [("Go to Line", f"Line number (1 - {count}):", 1, 1, count)]
    assert editor.current_line() == 3
    monkeypatch.setattr(QInputDialog, "getInt", staticmethod(lambda *args: (1, False)))
    ide.act_goto_line.trigger()  # cancelled: stays
    assert editor.current_line() == 3


# --- in the whole project ---------------------------------------------------------------------

@pytest.fixture
def project_ide(ide, tmp_path):
    """The Demo project with "needle" in Form1 (its code and its designer region),
    Module1 and a second module."""
    folder = os.path.join(tmp_path, "Demo")
    form1, module1 = os.path.join(folder, "Form1.py"), os.path.join(folder, "Module1.py")
    form = ide.documents[form1]
    text = form.text.replace("    # endregion", "        self.Caption = 'needle'\n"
                             "    # endregion", 1)
    form.replace_text(text + "\n# needle in the form's code\n")
    ide.documents[module1].replace_text(ide.documents[module1].text +
                                        "\n# a needle\n# another NEEDLE\n")
    ide.add_module()  # Module2 (after Module1 in the project)
    module2 = next(p for p in ide.documents if p.endswith("Module2.py"))
    ide.documents[module2].replace_text("# the last needle\n")
    ide.view_code(form1).editor.moveCursor(QTextCursor.Start)
    dialog = ide._find_dialog()
    dialog.show_find()
    dialog.find_edit.setText("needle")
    dialog.scope_project.setChecked(True)
    yield ide, dialog, form1, module1, module2
    dialog.close()


def _where(ide):
    """The current code window's file and selection."""
    sub = ide.mdi.currentSubWindow()
    path = ide._path_of(sub.widget())
    return os.path.basename(path), sub.widget().editor.textCursor().selectedText()


def test_find_next_and_previous_through_the_project(project_ide):
    ide, dialog, form1, module1, module2 = project_ide
    ide.view_code(form1).editor.moveCursor(QTextCursor.Start)
    seen = []
    for _ in range(6):
        result = dialog.find_next()
        seen.append(_where(ide))
    # Form1 (the region's caption, its code), Module1 (twice), Module2, then round again
    assert [name for name, _ in seen] == ["Form1.py", "Form1.py", "Module1.py", "Module1.py",
                                          "Module2.py", "Form1.py"]
    assert seen[3][1] == "NEEDLE" and "Passed the end of the project" in result.message
    result = dialog.find_previous()  # back round to the last one
    assert _where(ide) == ("Module2.py", "needle") and "beginning" in result.message
    dialog.find_previous()
    assert _where(ide) == ("Module1.py", "NEEDLE")
    dialog.match_case.setChecked(True)
    dialog.find_edit.setText("NEEDLE")
    assert dialog.find_next().message == "This is the only match"
    dialog.find_edit.setText("nowhere")
    assert "not found in the project" in dialog.find_next().message


def test_find_all(project_ide):
    ide, dialog, form1, module1, module2 = project_ide
    result = dialog.find_all()
    assert result.message == "5 matches in 3 files" and dialog.results.isVisible()
    rows = [dialog.results.item(i).text() for i in range(dialog.results.count())]
    assert rows[0] == "Form1.py:" + str(dialog.found[0].line) + ":  self.Caption = 'needle'"
    assert rows[-1].startswith("Module2.py:1:") and "the last needle" in rows[-1]
    dialog.results.itemActivated.emit(dialog.results.item(3))  # goes there
    assert _where(ide) == ("Module1.py", "NEEDLE")
    dialog.scope_module.setChecked(True)  # just the current module
    assert dialog.find_all().message == "2 matches in 1 file"
    dialog.find_edit.setText("nowhere")
    dialog.find_all()
    assert not dialog.results.isVisible()


def test_replace_in_the_project(project_ide):
    ide, dialog, form1, module1, module2 = project_ide
    dialog.replace_edit.setText("pin")
    result = dialog.replace_all()  # not in the designer region
    assert result.message == "Replaced 4 occurrences in 3 files; skipped 1 in designer regions"
    assert "# a pin\n# another pin" in ide.documents[module1].text
    assert "self.Caption = 'needle'" in ide.documents[form1].text
    assert "# pin in the form's code" in ide.documents[form1].text
    assert ide.documents[module2].modified and ide.documents[module2].text == "# the last pin\n"
    ide.documents[module1].text_document.undo()  # one undo step a file
    assert "# a needle\n# another NEEDLE" in ide.documents[module1].text
    # Replace: the selected match, then on to the next one in the project
    ide.view_code(module1).editor.moveCursor(QTextCursor.Start)
    dialog.find_next()
    assert _where(ide) == ("Module1.py", "needle")
    dialog.replace()
    assert "# a pin\n# another NEEDLE" in ide.documents[module1].text
    assert _where(ide) == ("Module1.py", "NEEDLE")


def test_scope_needs_a_project():
    dialog = FindReplaceDialog(lambda: None)
    assert not dialog.scope_project.isEnabled() and not dialog.in_project()
    assert dialog.find_all().message == "Find All needs a project"
