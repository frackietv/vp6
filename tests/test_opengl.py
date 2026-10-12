"""OpenGLView and QuickView (QML)."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from conftest import wait_for
from vp6 import Form, Label, OpenGLView, QuickView, TextBox

QML = """import QtQuick
Rectangle {
    id: root
    width: 100; height: 80
    property int count: 0
    signal tapped(int x, string what)
    Text { text: "Hi " + context.name + " " + root.count }
    MouseArea {
        anchors.fill: parent
        onClicked: (m) => {
            root.tapped(7, "seven")
            vp6.raiseEvent("Clicked", [Math.round(m.x), {"a": 1}])
            vp6.set("lblOut", "Caption", "from QML: " + vp6.get("txtIn", "Text"))
        }
    }
}
"""


@pytest.fixture
def form(qapp):
    class Views(Form):
        def InitializeComponent(self):
            self.events = []
            self.glvScene = OpenGLView(self, FrameRate=20)
            self.qmlHello = QuickView(self, Width=200, Height=150)
            self.lblOut = Label(self, Caption="")
            self.txtIn = TextBox(self, Text="typed")

        def glvScene_Paint(self):
            self.events.append("Paint")

        def qmlHello_QmlEvent(self, Name, Args):
            self.events.append((Name, Args))

    f = Views()
    f.Show()
    yield f
    f.Unload()


def test_opengl_view_without_opengl(form):
    view = form.glvScene  # (the offscreen platform has no OpenGL: a note instead)
    assert view.GL is None and "no OpenGL" in view._widget.text()
    view.Animate = True
    assert view._loop.isActive() and view._loop.interval() == 50
    view.FrameRate = 10
    assert view._loop.interval() == 100
    view.Animate = False
    assert not view._loop.isActive()
    view.Update()
    assert view.FrameCount == 0 and view.ElapsedTime >= 0 and view.PixelRatio >= 1


def test_opengl_view_graphics_methods(qapp):
    """The graphics methods over what OpenGL drew: in Paint on its picture,
    outside Paint kept over every frame until Cls."""
    from PySide6.QtGui import QColor, QImage

    from vp6 import RGB, vpFSSolid

    class Over(Form):
        def InitializeComponent(self):
            self.glvOver = OpenGLView(self, Width=100, Height=80, Samples=4,
                                      ForeColor=RGB(0, 0, 255))

        def glvOver_Paint(self):
            view = self.glvOver
            view.FillStyle, view.FillColor = vpFSSolid, RGB(255, 0, 0)
            view.Line(10, 10, 40, 40, RGB(255, 0, 0), "BF")  # (OpenGL would have drawn first)
            view.CurrentX, view.CurrentY = 50, 50
            view.Print("Hi")

    f = Over()
    f.Show()
    try:
        view = f.glvOver
        assert not view.Available  # (offscreen: no OpenGL, a program draws another way)
        assert view.Samples == 4 and view.ScaleWidth == 100 and view.ScaleHeight == 80
        assert view.TextWidth("Hi") > 0 and view.TextHeight("Hi") > 0
        assert view._widget.styleSheet() == ""  # (ForeColor: just the graphics methods')
        frame = QImage(100, 80, QImage.Format_ARGB32_Premultiplied)
        frame.fill(QColor(0, 0, 0))
        view._paint_gl(frame)  # (as paintGL would, on its framebuffer)
        assert frame.pixelColor(25, 25) == QColor(255, 0, 0)
        assert frame.pixelColor(80, 20) == QColor(0, 0, 0)
        assert view._draw_state()["painter"] is None and view._draw_state()["image"] is None
        view.Line(0, 70, 99, 70, RGB(0, 255, 0))  # outside Paint: over every frame
        frame.fill(QColor(0, 0, 0))
        view._paint_gl(frame)
        assert frame.pixelColor(25, 25) == QColor(255, 0, 0)
        assert frame.pixelColor(60, 70) == QColor(0, 255, 0)
        view.Cls()
        frame.fill(QColor(0, 0, 0))
        view._paint_gl(frame)
        assert frame.pixelColor(60, 70) == QColor(0, 0, 0)
    finally:
        f.Unload()


def test_quick_view(form):
    view = form.qmlHello
    view.Context["name"] = "Ada"
    assert view.Context["name"] == "Ada" and "name" in view.Context
    view.QmlText = QML
    wait_for(lambda: view.Root is not None, 3000)
    assert view.Errors == [] and view.Root is not None
    view.SetProperty("count", 5)  # (a property change isn't an event)
    assert view.GetProperty("count") == 5 and form.events == []
    temp = view._temp
    assert os.path.exists(temp)
    QTest.mouseClick(view._widget, Qt.LeftButton, Qt.NoModifier, QPoint(20, 20))
    QTest.qWait(20)
    assert form.events == [("tapped", [7, "seven"]), ("Clicked", [20, {"a": 1}])]
    assert form.lblOut.Caption == "from QML: typed"
    view.QmlText = "import QtQuick\nRectangle { width: }"  # (not QML)
    assert view.Errors
    form.Unload()
    assert not os.path.exists(temp)


def test_designer_placeholders(qapp, tmp_path):
    from vp6 import formfile
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument

    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    for type_name in ("OpenGLView", "QuickView", "MediaPlayer"):
        name = designer.create_control(type_name, None, None)
        assert designer.controls[name]._widget.text()  # (a label saying what it is)
