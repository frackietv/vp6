"""ColumnView, UndoStack and UndoView."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

import vp6
from vp6 import ColumnView, Form, Label, ListBox, TextBox, UndoStack, UndoView


@pytest.fixture
def form(qapp, tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.txt").write_text("a")

    class Views(Form):
        def InitializeComponent(self):
            self.events = []
            self.cvwNature = ColumnView(self, Items=["Animals|animals", "    Cats|cats",
                                                     "        Lion|lion", "Plants|plants"],
                                        PreviewWidget="lblPreview")
            self.lblPreview = Label(self, Caption="preview")
            self.lstItems = ListBox(self)
            self.undList = UndoView(self, EmptyLabel="(empty)")
            self.txtNotes = TextBox(self, MultiLine=True, Text="")
            self.undNotes = UndoView(self, Editor="txtNotes")

        def _base_dir(self):
            return str(tmp_path)

        def cvwNature_NodeClick(self, Node):
            self.events.append(("NodeClick", Node.Key))

        def cvwNature_Expand(self, Node):
            self.events.append(("Expand", Node.Key))

        def undList_Change(self):
            self.events.append(("Change", self.undList.Stack.Index))

    f = Views()
    f.Show()
    yield f
    f.Unload()


def test_columnview_nodes(form):
    view = form.cvwNature
    nodes = view.Nodes
    assert nodes.Count == 4 and nodes("lion").FullPath == "Animals\\Cats\\Lion"
    assert nodes("animals").Children == 1 and nodes("animals").Child is nodes("cats")
    assert nodes("lion").Parent is nodes("cats") and nodes(1) is nodes("animals")
    assert nodes("animals").Next is nodes("plants") and nodes("plants").Previous is \
        nodes("animals")
    added = nodes.Add("cats", vp6.vpTvwChild, "tiger", "Tiger")
    assert added.Parent is nodes("cats") and nodes("cats").Children == 2
    with pytest.raises(ValueError):
        nodes.Add(None, None, "tiger", "Again")
    view.SelectedItem = "lion"  # (code: no NodeClick)
    assert view.SelectedItem is nodes("lion") and nodes("lion").Selected and form.events == []
    view._widget.setCurrentIndex(nodes("cats")._item.index())  # the user
    assert form.events == [("NodeClick", "cats"), ("Expand", "cats")]
    nodes.Remove("cats")
    assert "lion" not in nodes and nodes.Count == 2  # (its children went with it)
    nodes("plants").Text = "Flora"
    assert nodes("plants").Text == "Flora"
    assert view._widget.previewWidget() is form.lblPreview._widget  # (made in Form_Load)
    view.PathSeparator = "/"
    assert nodes("plants").FullPath == "Flora"


def test_columnview_file_system(form, tmp_path):
    view = form.cvwNature
    view.Path = "docs"
    view.FileSystem = True
    view.SelectedPath = str(tmp_path / "docs" / "a.txt")
    QTest.qWait(50)
    node = view.SelectedItem
    assert view.SelectedPath == str(tmp_path / "docs" / "a.txt")
    assert node.Text == "a.txt" and not node.IsFolder and node.Parent.IsFolder
    with pytest.raises(AttributeError):
        node.Text = "b.txt"
    view.FileSystem = False
    assert view.SelectedPath == "" and view.Nodes.Count == 4


def test_undo_stack(form):
    stack = form.undList.Stack
    assert isinstance(stack, UndoStack) and not stack.CanUndo
    form.count = 0
    stack.Push("Add one", "self.count += 1", "self.count -= 1")  # code, run as the form's
    stack.Push("Add ten", lambda: setattr(form, "count", form.count + 10),
               lambda: setattr(form, "count", form.count - 10))
    assert form.count == 11 and stack.Count == 2 and stack.UndoText == "Add ten"
    stack.Undo()
    assert form.count == 1 and stack.CanRedo and stack.RedoText == "Add ten"
    stack.Index = 0
    assert form.count == 0 and stack.Text(0) == "Add one"
    stack.Redo()
    stack.SetClean()
    assert stack.IsClean and stack.CleanIndex == 1
    assert [e for e in form.events if e[0] == "Change"][-1] == ("Change", 1)
    stack.Clear()
    assert stack.Count == 0


def test_undo_stack_of_its_own(qapp):
    stack = UndoStack()
    items = []
    stack.Push("x", lambda: items.append("x"), lambda: items.pop())
    stack.Undo()
    assert items == [] and repr(stack) == "<UndoStack 0/1>"


def test_undo_view_of_an_editor(form):
    editor = form.txtNotes._widget
    history = form.undNotes.Stack
    QTest.keyClicks(editor, "hello")
    QTest.keyClick(editor, Qt.Key_Return)
    QTest.keyClicks(editor, "world")
    assert history.Count >= 2 and form.txtNotes.Text == "hello\nworld"
    history.Index = 0
    assert form.txtNotes.Text == ""
    history.Index = history.Count
    assert form.txtNotes.Text == "hello\nworld"
    editor.undo()  # the editor's own Undo: the history follows
    assert history.Index == history.Count - 1
    with pytest.raises(TypeError):
        history.Push("x", None, None)
