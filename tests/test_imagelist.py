"""The ImageList control and the controls showing its pictures (TreeView, TabStrip)."""

import os
import sys

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QColor, QImage

from vp6 import Image, ImageList, TabStrip, TreeView, formfile
from vp6.controls import CONTROL_TYPES, parse_list_image
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow, TextListDialog

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")

PICTURES = ["images/red.png|red", "images/green.png|green", "images/big.png|big"]


@pytest.fixture
def pictures(qapp, tmp_path, monkeypatch):
    """A folder with three pictures (16, 16 and 64 pixels) and a form module in it."""
    (tmp_path / "images").mkdir()
    for name, color, size in (("red", "red", 16), ("green", "green", 16), ("big", "blue", 64)):
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(QColor(color))
        image.save(str(tmp_path / "images" / f"{name}.png"))
    (tmp_path / "Pictures.py").write_text(
        "from vp6 import *\n\n\n"
        "class Pictures(Form):\n"
        "    def InitializeComponent(self):\n"
        "        # The users come first: their Images are shown once the form is built\n"
        "        self.tvw = TreeView(self, ImageList='iml', "
        "Items=['Red|r|red', '    Green|g|2', 'Plain|p'])\n"
        "        self.tbs = TabStrip(self, ImageList='iml', Tabs=['A|a||red', 'B|b||green'])\n"
        f"        self.iml = ImageList(self, ListImages={PICTURES!r})\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    sys.modules.pop("Pictures", None)


def _shown(node):
    return not node._item.icon(0).isNull()


def test_parse_list_image():
    assert parse_list_image("images/open.png|open") == {"Picture": "images/open.png",
                                                        "Key": "open"}
    assert parse_list_image(" logo.png ") == {"Picture": "logo.png", "Key": ""}


def test_list_images(pictures):
    from Pictures import Pictures
    form = Pictures()
    images = form.iml.ListImages
    assert images.Count == 3 and [i.Index for i in images] == [1, 2, 3]
    assert images("green") is images(2) and images(2).Picture == "images/green.png"
    assert (images(1).Width, images(1).Height) == (16, 16)  # the first picture's size...
    big = images("big")._pixmap()
    assert (big.width(), big.height()) == (16, 16)  # ...for every picture
    form.iml.ImageWidth, form.iml.ImageHeight = 32, 24  # or a size of its own
    assert images("red")._pixmap().size().toTuple() == (32, 24)
    added = images.Add(1, "first", "images/big.png")
    assert added.Index == 1 and images("red").Index == 2
    with pytest.raises(KeyError):
        images.Add(Key="red")
    with pytest.raises(IndexError):
        images(9)
    images.Remove("first")
    assert form.iml._widget is None  # invisible at run time
    # A ListImage's Picture is a file: an Image control can show it
    form.img = Image(form, Picture=images("big").Picture)
    assert not form.img._widget.pixmap().isNull()


def test_tree_and_tabs_show_its_pictures(pictures):
    from Pictures import Pictures
    form = Pictures()
    tvw, tbs, iml = form.tvw, form.tbs, form.iml
    assert [_shown(n) for n in tvw.Nodes] == [True, True, False]  # by key, by Index, none
    assert tvw.Nodes("g").Image == 2 and tvw.Nodes("p").Image == ""
    assert [not tbs._widget.tabIcon(i).isNull() for i in range(2)] == [True, True]
    # Code sets an Image by key or Index; an unknown one is an error
    tvw.Nodes("p").Image = "big"
    assert _shown(tvw.Nodes("p"))
    with pytest.raises(KeyError):
        tvw.Nodes("p").Image = "nothing"
    with pytest.raises(IndexError):
        tbs.Tabs("a").Image = 9
    node = tvw.Nodes.Add(None, None, "new", "New", Image="green")
    assert _shown(node)
    # The users follow the ImageList's changes
    iml.ListImages.Clear()
    assert not any(_shown(n) for n in tvw.Nodes) and tbs._widget.tabIcon(0).isNull()
    iml.ListImages.Add(Key="red", Picture="images/red.png")
    assert _shown(tvw.Nodes("r")) and not tbs._widget.tabIcon(0).isNull()
    tvw.ImageList = ""  # no ImageList: no pictures by key...
    assert not _shown(tvw.Nodes("r"))
    tvw.Nodes("r").Image = "images/green.png"  # ...but a picture file still works
    assert _shown(tvw.Nodes("r"))
    with pytest.raises(ValueError, match="needs an ImageList"):
        tvw.Nodes("r").Image = 1


def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.iml = ImageList(self, Left=8, Top=8, ImageWidth=16, ImageHeight=16, "
            "ListImages=['images/open.png|open'])\n"
            "    self.tvw = TreeView(self, Left=50, Top=8, Width=161, Height=193, "
            "ImageList='iml', Items=['Open|o|open'])\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("iml").props["ListImages"] == ["images/open.png|open"]
    region = formfile.generate_region(form)
    assert "ListImages=['images/open.png|open']" in region and "ImageList='iml'" in region


def test_in_the_designer(pictures):
    path = pictures / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(pictures))
    d.resize(800, 600)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    tree = d.create_control("TreeView", QRect(origin + QPoint(16, 16), origin + QPoint(200, 200)),
                            None)
    iml = d.create_control("ImageList", QRect(origin + QPoint(250, 16), origin + QPoint(282, 48)),
                           None)
    assert iml == "ImageList1" and d.controls[iml]._widget is not None  # an icon while designing
    d.select([iml])
    assert d.set_property("ListImages", PICTURES) is None
    d.select([tree])
    assert d.set_property("ImageList", "ImageList1") is None
    assert d.set_property("Items", ["Red|r|red", "Big|b|big"]) is None
    assert all(_shown(n) for n in d.controls[tree].Nodes)  # the pictures, while designing
    window = PropertiesWindow()
    window.set_designer(d)
    d.select([iml])
    row = next(r for r in range(window.table.rowCount())
               if window.table.item(r, 0).text() == "ListImages")
    assert window.table.cellWidget(row, 1).text() == "(Images: 3)"
    d.close()


def test_add_pictures_in_the_list_dialog(qapp, tmp_path):
    dialog = TextListDialog("ListImages (Pictures)", "images/a.png|a", None, "hint",
                            pictures_dir=str(tmp_path))
    dialog.add_pictures([str(tmp_path / "images" / "open.png"), "/elsewhere/save.png"])
    assert dialog.edit.toPlainText().split("\n") == [
        "images/a.png|a", "images/open.png|open", "/elsewhere/save.png|save"]


def test_toolbox_and_icon(qapp):
    assert "ImageList" in Toolbox().buttons and "ImageList" in CONTROL_TYPES
    assert ImageList.Events == () and not icons.icon("ImageList").isNull()
    assert "ImageList" in TreeView._specs and "ImageList" in TabStrip._specs
