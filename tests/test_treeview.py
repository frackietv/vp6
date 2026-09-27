"""The TreeView control, its Nodes collection and Node objects."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest

from vp6 import (Form, TreeView, formfile, vpRed, vpTvwChild, vpTvwFirst, vpTvwLast, vpTvwNext,
                 vpTvwPrevious, vpTvwTreeLines)
from vp6.controls import CONTROL_TYPES, parse_outline
from vp6.ide import icons
from vp6.ide.codeeditor import CodeWindow
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.kitchensink import draw_picture
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

OUTLINE = ["Animals|animals", "    Cats|cats", "        Lion|lion", "    Dogs|dogs",
           "Plants|plants"]


def test_parse_outline():
    assert parse_outline(OUTLINE + ["", "\tTree | tree", "No key"])[:-1] == [
        (0, "Animals", "animals", ""), (1, "Cats", "cats", ""), (2, "Lion", "lion", ""),
        (1, "Dogs", "dogs", ""), (0, "Plants", "plants", ""),
        (1, "Tree", "tree", "")]  # a tab is an indent too
    # Any deeper indentation is a child; going back to an earlier one is a sibling there
    assert [level for level, *_ in parse_outline(["a", "  b", "      c", "   d", "e"])] == \
        [0, 1, 2, 2, 0]
    assert parse_outline(["No key"]) == [(0, "No key", "", "")]
    # An Image: a key or Index in the ImageList (digits), or a picture file
    assert parse_outline(["Cats|cats|cat", "Dogs||2", "Birds|birds|img/bird.png"]) == [
        (0, "Cats", "cats", "cat"), (0, "Dogs", "", 2), (0, "Birds", "birds", "img/bird.png")]


class Zoo(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 320, 400
        self.tvwZoo = TreeView(self, Left=8, Top=8, Width=300, Height=380, Items=OUTLINE)

    def Form_Load(self):
        self.events = []

    def tvwZoo_NodeClick(self, Node):
        self.events.append(("click", Node.Key))

    def tvwZoo_Expand(self, Node):
        self.events.append(("expand", Node.Key))

    def tvwZoo_Collapse(self, Node):
        self.events.append(("collapse", Node.Key))

    def tvwZoo_NodeCheck(self, Node):
        self.events.append(("check", Node.Key, Node.Checked))


@pytest.fixture
def zoo(qapp):
    form = Zoo()
    form.Show()
    yield form
    form.Unload()


def test_nodes_collection(zoo):
    nodes = zoo.tvwZoo.Nodes
    assert nodes.Count == len(nodes) == 5
    assert [n.Text for n in nodes] == ["Animals", "Cats", "Lion", "Dogs", "Plants"]
    assert nodes("cats") is nodes["cats"] is nodes.Item("cats") is nodes(2)  # key or Index from 1
    assert nodes(2).Index == 2 and "cats" in nodes and "tigers" not in nodes
    with pytest.raises(KeyError):
        nodes("tigers")
    with pytest.raises(IndexError):
        nodes(0)  # Index starts at 1, like VB
    with pytest.raises(ValueError, match="not unique"):
        nodes.Add(None, None, "cats", "Cats again")
    with pytest.raises(TypeError):
        nodes.Add(None, None, 7, "A number is an Index, not a key")


def test_relationships(zoo):
    tree, nodes = zoo.tvwZoo, zoo.tvwZoo.Nodes

    def texts(parent=None):
        item = parent._item if parent else tree._widget.invisibleRootItem()
        return [item.child(i).text(0) for i in range(item.childCount())]

    nodes.Add(None, None, "fungi", "Fungi")  # the end of the top level
    nodes.Add(None, vpTvwFirst, "bacteria", "Bacteria")
    nodes.Add("plants", vpTvwPrevious, "algae", "Algae")
    nodes.Add("plants", None, "moss", "Moss")  # vpTvwNext is the default
    nodes.Add("fungi", vpTvwLast, "virus", "Virus")
    assert texts() == ["Bacteria", "Animals", "Algae", "Plants", "Moss", "Fungi", "Virus"]
    tiger = nodes.Add("cats", vpTvwChild, "tiger", "Tiger")
    cats = nodes("cats")
    assert texts(cats) == ["Lion", "Tiger"]
    assert tiger.Parent is cats and tiger.Previous is nodes("lion") and tiger.Next is None
    assert cats.Child is nodes("lion") and cats.Children == 2
    assert tiger.FirstSibling is nodes("lion") and tiger.LastSibling is tiger
    assert tiger.Root is nodes("animals") and nodes("animals").Parent is None
    assert tiger.FullPath == "Animals\\Cats\\Tiger"
    tree.PathSeparator = "/"
    assert tiger.FullPath == "Animals/Cats/Tiger"
    nodes.Remove("cats")  # with its children
    assert "lion" not in nodes and "tiger" not in nodes and texts(nodes("animals")) == ["Dogs"]
    assert nodes("dogs").Index == 2  # Indexes close up after a removal
    nodes.Clear()
    assert nodes.Count == 0 and tree._widget.topLevelItemCount() == 0


def test_node_properties(zoo, tmp_path):
    tree, nodes = zoo.tvwZoo, zoo.tvwZoo.Nodes
    lion = nodes("lion")
    lion.Text, lion.Key, lion.Tag = "Lion King", "king", "roar"
    assert nodes("king") is lion and "lion" not in nodes and lion.Tag == "roar"
    with pytest.raises(ValueError):
        lion.Key = "cats"
    lion.Bold, lion.ForeColor = True, vpRed
    assert lion.Bold and lion.ForeColor == vpRed
    picture = str(tmp_path / "icon.png")
    draw_picture(picture)
    lion.Image = picture
    assert not lion._item.icon(0).isNull()
    lion.EnsureVisible()
    assert nodes("cats").Expanded and nodes("animals").Expanded
    assert zoo.events == []  # changes made by code fire no events
    tree.Sorted = True
    nodes.Add(None, vpTvwFirst, "zebra", "Zebra")
    assert [tree._widget.topLevelItem(i).text(0) for i in range(3)] == ["Animals", "Plants",
                                                                        "Zebra"]
    nodes("animals").Sorted = True  # a node's own children
    assert [c.text(0) for c in (nodes("animals")._item.child(i) for i in range(2))] == \
        ["Cats", "Dogs"]


def test_selection_and_user_events(zoo):
    tree = zoo.tvwZoo
    tree.SelectedItem = "animals"  # by code: no NodeClick
    assert tree.SelectedItem is tree.Nodes("animals") and tree.Nodes("animals").Selected
    assert zoo.events == []
    viewport = tree._widget.viewport()

    def click(node):
        rect = tree._widget.visualItemRect(node._item)
        QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, rect.center())

    click(tree.Nodes("plants"))
    click(tree.Nodes("plants"))  # clicking the selected node again fires again
    assert zoo.events == [("click", "plants"), ("click", "plants")]
    QTest.keyClick(tree._widget, Qt.Key_Up)  # keyboard navigation too
    assert zoo.events[-1] == ("click", "animals")
    QTest.keyClick(tree._widget, Qt.Key_Right)  # expands Animals
    QTest.keyClick(tree._widget, Qt.Key_Left)
    assert zoo.events[-2:] == [("expand", "animals"), ("collapse", "animals")]
    tree.Nodes("animals").Expanded = True  # code: no event
    assert zoo.events[-1] == ("collapse", "animals")
    rect = tree._widget.visualItemRect(tree.Nodes("dogs")._item)
    assert tree.HitTest(rect.center().x(), rect.center().y()) is tree.Nodes("dogs")
    assert tree.HitTest(5, 370) is None


def test_checkboxes(zoo):
    tree = zoo.tvwZoo
    tree.Checkboxes = True
    plants = tree.Nodes("plants")
    assert not plants.Checked
    plants.Checked = True  # code: no event
    assert plants.Checked and zoo.events == []
    plants._item.setCheckState(0, Qt.Unchecked)  # like the user clicking the box
    assert zoo.events == [("check", "plants", False)]
    tree.Nodes.Add(None, None, "new", "New")
    assert not tree.Nodes("new").Checked  # new nodes get a box too
    tree.Checkboxes = False
    assert tree.Nodes("new")._item.data(0, Qt.CheckStateRole) is None


def test_properties(zoo):
    tree = zoo.tvwZoo
    tree.LineStyle = vpTvwTreeLines
    tree.Indentation = 30
    assert not tree._widget.rootIsDecorated() and tree._widget.indentation() == 30
    tree.Items = ["One", "    Two"]  # replaces the nodes
    assert [n.FullPath for n in tree.Nodes] == ["One", "One\\Two"]
    assert TreeView.DefaultEvent == "NodeClick" and "TabIndex" in TreeView._specs


# --- the file and the IDE ---------------------------------------------------------------------

def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.tvwA = TreeView(self, Left=8, Top=8, Width=161, Height=193, "
            "Items=['A|a', '    B'])\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("tvwA").props["Items"] == ["A|a", "    B"]
    assert "Items=['A|a', '    B']" in formfile.generate_region(form)


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("TreeView", QRect(origin + QPoint(16, 16), origin + QPoint(200, 200)),
                            None)
    assert name == "TreeView1"
    d.select([name])
    assert d.set_property("Items", OUTLINE) is None
    tree = d.controls[name]
    assert tree.Nodes.Count == 5 and tree.Nodes("cats").Expanded  # all shown while designing
    window = PropertiesWindow()
    window.set_designer(d)
    row = next(r for r in range(window.table.rowCount())
               if window.table.item(r, 0).text() == "Items")
    assert window.table.cellWidget(row, 1).text() == "(Tree: 5 nodes)"
    code = CodeWindow(d.document)
    code.goto_event(name, "NodeClick")
    assert "def TreeView1_NodeClick(self, Node):" in d.document.text
    d.close()


def test_toolbox_and_icon(qapp):
    assert "TreeView" in Toolbox().buttons and "TreeView" in CONTROL_TYPES
    assert not icons.icon("TreeView").isNull()
    assert (vpTvwFirst, vpTvwLast, vpTvwNext, vpTvwPrevious, vpTvwChild) == (0, 1, 2, 3, 4)
