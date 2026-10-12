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
