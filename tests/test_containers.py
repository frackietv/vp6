"""Containers with pages (ToolBox, PageFrame: Control.Page, the designer's pages) and
the ScrollPanel."""

import pytest
from PySide6.QtCore import QPoint, QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton

from vp6 import (CommandButton, ControlArray, Form, Label, PageFrame, ScrollPanel, TextBox,
                 ToolBox, formfile)


@pytest.fixture
def form(qapp):
    class Paged(Form):
        def InitializeComponent(self):
            self.events = []
            self.tbxTools = ToolBox(self, Pages=["&Shapes|shapes|Draw", "Colors|colors",
                                                 "Notes|notes"], CurrentPage=1)
            self.lblShape = Label(self.tbxTools, Page=0, Caption="Shape", Left=8, Top=8)
            self.lblColor = Label(self.tbxTools, Page=1, Caption="Color", Left=8, Top=8)
            self.pgfSteps = PageFrame(self, Left=220, PageCount=3)
            self.txtName = TextBox(self.pgfSteps, Page=0, Text="")
            self.lblDone = Label(self.pgfSteps, Page=2, Caption="Done")
            self.cmdStep = ControlArray()
            self.cmdStep[0] = CommandButton(self.pgfSteps, Page=1, Caption="Step")
            self.scpBig = ScrollPanel(self, Left=0, Top=300, Width=200, Height=150)
            self.cmdFar = CommandButton(self.scpBig, Caption="Far", Left=700, Top=500)

        def tbxTools_PageChange(self):
            self.events.append(("ToolBox", self.tbxTools.CurrentPage))

        def pgfSteps_PageChange(self):
            self.events.append(("PageFrame", self.pgfSteps.CurrentPage))

        def scpBig_Scroll(self):
            self.events.append("Scroll")

    f = Paged()
    f.Width, f.Height = 640, 480
    f.Show()
    QTest.qWait(10)
    yield f
    f.Unload()


def test_toolbox_pages(form):
    box = form.tbxTools
    assert box.Pages.Count == 3 and box.CurrentPage == 1
    assert box.SelectedItem is box.Pages("colors") and box.Pages(1).Caption == "&Shapes"
    assert box.Pages("shapes").ToolTipText == "Draw"
    assert form.lblShape.Page == 0 and form.lblColor.Page == 1
    assert form.lblColor._widget.parentWidget() is box._page_widget(1)
    assert form.lblColor._widget.isVisible() and not form.lblShape._widget.isVisible()
    box.CurrentPage = 0
    assert form.events == [("ToolBox", 0)] and form.lblShape._widget.isVisible()
    box.SelectedItem = "notes"
    assert box.CurrentPage == 2 and box.Pages("notes").Selected
    form.lblColor.Page = 2  # moved to another page
    assert form.lblColor._widget.parentWidget() is box._page_widget(2)
    assert form.lblColor.Left == 8
    box.Pages.Add(1, "first", "First")  # pages before it: its Page follows
    assert form.lblColor.Page == 3 and form.lblShape.Page == 1
    assert [p.Caption for p in box.Pages] == ["First", "&Shapes", "Colors", "Notes"]
    box.Pages("colors").Enabled = False
    assert not box._widget.isItemEnabled(2)
    box.Pages.Remove("notes")
    assert box.Pages.Count == 3
    assert form.txtName.Page == 0 and form.cmdFar.Page is None
    with pytest.raises(AttributeError):
        form.cmdFar.Page = 1  # (not in a container with pages)


def test_pageframe(form):
    frame = form.pgfSteps
    assert frame.PageCount == 3 and frame.CurrentPage == 0
    assert form.txtName._widget.isVisible() and not form.lblDone._widget.isVisible()
    frame.CurrentPage = 2
    assert form.events == [("PageFrame", 2)] and form.lblDone._widget.isVisible()
    frame.CurrentPage = 9
    assert frame.CurrentPage == 2
    new = frame.AddPage(0)
    assert new == 0 and frame.PageCount == 4 and form.txtName.Page == 1
    frame.RemovePage(0)
    assert frame.PageCount == 3 and form.txtName.Page == 0
    with pytest.raises(IndexError):
        frame.RemovePage(7)
    loaded = form.cmdStep.Load(1)  # a control array element: on its template's page
    assert loaded.Page == 1
    frame.PageCount = 1
    assert frame.PageCount == 1


def test_scrollpanel(form):
    panel = form.scpBig
    QTest.qWait(10)
    content = panel._container_widget()
    assert content.width() >= 797 and content.height() >= 533
    form.events.clear()
    panel.ScrollTop = 100
    assert panel.ScrollTop == 100 and "Scroll" in form.events
    panel.EnsureVisible(form.cmdFar)
    viewport = panel._widget.viewport()
    far = form.cmdFar._widget
    assert viewport.rect().contains(QRect(far.mapTo(viewport, QPoint(0, 0)), far.size()))
    panel.ScrollLeft = panel.ScrollTop = 0
    panel.ScrollWidth, panel.ScrollHeight = 2000, 1500
    assert content.width() == 2000 and content.height() == 1500
    with pytest.raises(ValueError):
        panel.EnsureVisible(form.lblShape)
    panel.ScrollBars = 0
    assert not panel._widget.verticalScrollBar().isVisible()


def test_page_in_the_form_file(qapp):
    source = formfile.new_form_source("Form1").replace(
        "        self.Height = 360\n",
        "        self.Height = 360\n"
        "        self.tbxA = ToolBox(self, Left=8, Top=8, Width=201, Height=257)\n"
        "        self.lblA = Label(self.tbxA, Caption='a', Left=8, Top=8, Width=97, Height=25,"
        " Page=1)\n")
    form_def = formfile.parse(source)
    assert form_def.control("lblA").props["Page"] == 1
    text = formfile.replace_region(source, form_def)
    assert "Label(self.tbxA, Page=1, Caption='a'" in text  # (right after its container)
    assert formfile.replace_region(text, formfile.parse(text)) == text


@pytest.fixture
def designer(qapp, tmp_path):
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument

    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.ask_create_array = lambda name: False  # (a pasted copy: a new name, no question)
    d.resize(900, 700)
    d.show()
    yield d
    d.close()


def test_designing_pages(designer):
    d = designer
    box = d.create_control("ToolBox", QRect(40, 80, 220, 280), None)
    rect = d.canvas_rect(box)
    first = d.create_control("CommandButton", None, box, rect.topLeft() + QPoint(30, 70))
    assert f"CommandButton(self.{box}, Page=0, Caption='{first}'" in d.document.text
    # A click on the second page's header: that page is edited now
    second_header = sorted((b for b in d.controls[box]._widget.findChildren(QAbstractButton)
                            if b.objectName() == "qt_toolbox_toolboxbutton"),
                           key=lambda b: b.y())[1]
    point = second_header.mapTo(d.canvas, second_header.rect().center())
    assert d.page_header_click(box, point)
    assert d.controls[box].CurrentPage == 1 and "CurrentPage=1" in d.document.text
    assert d.canvas_rect(first) is None  # (on a page not shown)
    second = d.create_control("Label", None, box, d.canvas_rect(box).topLeft() + QPoint(30, 90))
    assert f"Label(self.{box}, Page=1, Caption='{second}'" in d.document.text
    d.select([first])  # selecting it shows its page
    assert d.controls[box]._current() == 0
    d.step_page(1)  # Next Page
    assert d.controls[box].CurrentPage == 1 and d.selection == [box]
    d.step_page(-1)
    assert d.controls[box].CurrentPage == 0
    # Pasted into it: on the page shown (selecting the label showed its page)
    d.select([second])
    d.copy_selection()
    d.select([box])
    assert d.controls[box]._current() == 1
    d.paste()
    pasted = d.selection[0]
    assert d.form_def.control(pasted).props["Page"] == 1
    # A page removed in the designer: its controls go to the last page kept
    d.select([box])
    d.set_property("Pages", ["Only|only"])
    assert d.form_def.control(second).props["Page"] == 0
    d.undo()
    assert d.form_def.control(second).props["Page"] == 1
    assert d.paged_object() is d.controls[box]


def test_designing_a_pageframe_and_scrollpanel(designer):
    d = designer
    frame = d.create_control("PageFrame", QRect(40, 80, 260, 180), None)
    d.select([frame])
    d.step_page(1)
    inside = d.create_control("TextBox", None, frame, d.canvas_rect(frame).topLeft() +
                              QPoint(20, 20))
    assert f"TextBox(self.{frame}, Page=1, " in d.document.text
    assert d.controls[frame]._widget.badge.text() == "Page 2 of 2"
    panel = d.create_control("ScrollPanel", QRect(340, 80, 200, 150), None)
    far = d.create_control("CommandButton", None, panel, d.canvas_rect(panel).topLeft() +
                           QPoint(20, 20))
    d.controls[far].Move(600, 500)
    d.commit_geometry([far])
    QTest.qWait(10)
    scroll = d.controls[panel]
    assert scroll._design_wheel(QPoint(0, -240)) and scroll.ScrollTop > 0
    assert inside and d.form_def.control(far).parent == panel
