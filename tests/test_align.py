"""PictureBox Align: panes docked to the edges of the form."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect

from vp6 import (Form, Frame, Label, Menu, PictureBox, formfile, vpAlignBottom, vpAlignLeft,
                 vpAlignNone, vpAlignRight, vpAlignTop)
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


def _place(control):
    return control.Left, control.Top, control.Width, control.Height


class Docked(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 400, 300
        self.picTop = PictureBox(self, Align=vpAlignTop, Height=40)
        self.picLeft = PictureBox(self, Align=vpAlignLeft, Width=100)
        self.picBottom = PictureBox(self, Align=vpAlignBottom, Height=30)
        self.picRight = PictureBox(self, Align=vpAlignRight, Width=50)
        self.lblMiddle = Label(self, Caption="middle", Left=120, Top=60)

    def Form_Load(self):
        self.seen = []

    def Form_Resize(self):
        self.seen.append(self.picLeft.Height)  # the panes are placed before Form_Resize


@pytest.fixture
def docked(qapp):
    form = Docked()
    form.Show()
    yield form
    form.Unload()


def test_panes_dock_in_creation_order(docked):
    # Each pane takes its edge of the space the earlier ones left
    assert _place(docked.picTop) == (0, 0, 400, 40)
    assert _place(docked.picLeft) == (0, 40, 100, 260)
    assert _place(docked.picBottom) == (100, 270, 300, 30)
    assert _place(docked.picRight) == (350, 40, 50, 230)
    assert _place(docked.lblMiddle)[:2] == (120, 60)  # other controls stay put


def test_panes_follow_the_form(docked):
    docked.Width, docked.Height = 600, 500
    assert _place(docked.picTop) == (0, 0, 600, 40)
    assert _place(docked.picLeft) == (0, 40, 100, 460)
    assert _place(docked.picRight) == (550, 40, 50, 430)
    assert docked.seen[-1] == 460


def test_changing_panes(docked):
    docked.picLeft.Width = 150  # its thickness is yours to set; the rest follows
    assert _place(docked.picLeft) == (0, 40, 150, 260)
    assert _place(docked.picBottom) == (150, 270, 250, 30)
    docked.picLeft.Top = 99  # its place isn't: the form docks it
    assert docked.picLeft.Top == 40
    docked.picTop.Visible = False  # a hidden pane gives its space to the others
    assert _place(docked.picLeft) == (0, 0, 150, 300)
    docked.picLeft.Align = vpAlignNone  # undocked: an ordinary PictureBox again
    docked.picLeft.Left = 200
    assert docked.picLeft.Left == 200 and _place(docked.picBottom)[0] == 0
    docked.picBottom.Align = vpAlignTop  # moved to another edge; created before picRight,
    assert _place(docked.picBottom) == (0, 0, 400, 30)  # it docks first: the full width
    assert _place(docked.picRight) == (350, 30, 50, 270)


def test_panes_created_in_code_and_nested_pictureboxes(qapp):
    class Plain(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 300, 200
            self.fraBox = Frame(self, Left=10, Top=10, Width=100, Height=80)
            self.picInFrame = PictureBox(self.fraBox, Align=vpAlignTop, Left=5, Top=20,
                                         Width=40, Height=30)

    form = Plain()
    form.Show()
    assert _place(form.picInFrame) == (5, 20, 40, 30)  # only on the form itself
    form.picStatus = PictureBox(form, Align=vpAlignBottom, Height=24)  # at run time
    assert _place(form.picStatus) == (0, 176, 300, 24)
    form.Unload()


def test_below_an_in_window_menu_bar(qapp):
    class WithMenu(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 300, 200
            self.picTop = PictureBox(self, Align=vpAlignTop, Height=30)
            self.mnuFile = Menu(self, Caption="&File")

    form = WithMenu()
    form.Show()
    if form._menubar.isNativeMenuBar():
        pytest.skip("the menu bar is the system's (macOS)")
    assert _place(form.picTop) == (0, 0, 300, 30)  # in the client area, under the bar
    assert form.picTop._widget.mapTo(form._widget, QPoint(0, 0)).y() == form._menu_height
    form.Unload()


def test_in_a_form_shown_in_a_container(qapp):
    class Host(Form):
        def InitializeComponent(self):
            self.picPane = PictureBox(self, Left=0, Top=0, Width=200, Height=150,
                                      BorderStyle=0)

    class Page(Form):
        def InitializeComponent(self):
            self.picBar = PictureBox(self, Align=vpAlignRight, Width=20)

    host, page = Host(), Page()
    host.Show()
    page.ShowIn(host.picPane)
    assert _place(page.picBar) == (180, 0, 20, 150)
    host.picPane.Height = 100
    assert _place(page.picBar) == (180, 0, 20, 100)
    host.Unload()


def test_in_the_designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))  # 480 x 360
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.resize(900, 700)
    d.show()
    origin = d.form_canvas_rect().topLeft()
    name = d.create_control("PictureBox", QRect(origin + QPoint(40, 40), origin + QPoint(160, 120)),
                            None)
    d.select([name])
    assert d.set_property("Align", vpAlignLeft) is None
    props = d.form_def.control(name).props
    assert (props["Left"], props["Top"], props["Width"], props["Height"]) == (0, 0, 120, 360)
    assert "Align=3" in d.document.text
    # Resizing the form: the pane follows, and the file says where it is
    d.form_widget().resize(480, 400)
    d.commit_form_size()
    assert props["Height"] == 400
    # Dragging it away: it goes back to its edge
    d.controls[name]._widget.move(200, 100)
    d.commit_geometry([name])
    assert (props["Left"], props["Top"]) == (0, 0)
    d.undo()
    assert d.form_def.control(name).props["Height"] == 360
    d.close()


def test_constants():
    assert (vpAlignNone, vpAlignTop, vpAlignBottom, vpAlignLeft, vpAlignRight) == (0, 1, 2, 3, 4)
