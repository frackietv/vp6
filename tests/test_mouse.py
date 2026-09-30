"""The mouse: MousePointer and MouseIcon (controls, forms, Screen), VB drag and drop
(DragMode, Drag, DragIcon, DragOver, DragDrop) and drops from other programs
(OLEDropMode, OLEDragOver, OLEDragDrop)."""

import os

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from vp6 import (CommandButton, Form, Label, PictureBox, Screen, TextBox, UserControl,
                 vpAutomatic, vpBeginDrag, vpCancelDrag, vpCFFiles, vpCFText, vpCrosshair,
                 vpCustom, vpDefault, vpDropEffectNone, vpEndDrag, vpEnter, vpHourglass,
                 vpLeave, vpOver, vpSizeWE)
from vp6 import controls
from vp6.controls import CONTROL_TYPES, EVENT_ARGS, DataObject

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class ctlTarget(UserControl):
    def InitializeComponent(self):
        self.Surface.Width = 100
        self.Surface.Height = 50


class Board(Form):
    def InitializeComponent(self):
        self.events = []
        self.refuse = False
        self.lblCard = Label(self, Caption="Card", Left=10, Top=10, Width=60, Height=25)
        self.cmdAuto = CommandButton(self, Caption="Auto", Left=10, Top=40, DragMode=1)
        self.pic = PictureBox(self, Left=150, Top=10, Width=200, Height=150)
        self.txt = TextBox(self, Left=10, Top=200, Width=200)
        self.txtOle = TextBox(self, Left=10, Top=240, Width=200, OLEDropMode=1)
        self.ctl = ctlTarget(self, Left=400, Top=10)

    def pic_DragOver(self, Source, X, Y, State):
        self.events.append(("DragOver", Source.Name, X, Y, State))
        return False if self.refuse else None

    def pic_DragDrop(self, Source, X, Y):
        self.events.append(("DragDrop", Source.Name, X, Y))

    def cmdAuto_MouseDown(self, Button, Shift, X, Y):
        self.events.append("MouseDown")

    def cmdAuto_Click(self):
        self.events.append("Click")

    def txtOle_OLEDragOver(self, Data, Effect, Button, Shift, X, Y, State):
        self.events.append(("OLEDragOver", State))
        return vpDropEffectNone if self.refuse else Effect

    def txtOle_OLEDragDrop(self, Data, Effect, Button, Shift, X, Y):
        self.events.append(("OLEDragDrop", Data.GetData(vpCFText), Effect, X, Y))

    def ctl_DragDrop(self, Source, X, Y):
        self.events.append(("ctl DragDrop", Source.Name))

    def Form_OLEDragDrop(self, Data, Effect, Button, Shift, X, Y):
        self.events.append(("Form OLEDragDrop", Data.GetData(vpCFFiles)))


@pytest.fixture
def form(qapp):
    form = Board()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def vp6_mime():
    mime = QMimeData()
    mime.setData(controls._VP6_DRAG_MIME, b"1")
    return mime


def send(widget, mime, point, kinds=("enter", "move", "drop")):
    point = QPoint(*point)
    events = {"enter": lambda: QDragEnterEvent(point, Qt.MoveAction, mime, Qt.LeftButton,
                                               Qt.NoModifier),
              "move": lambda: QDragMoveEvent(point, Qt.MoveAction, mime, Qt.LeftButton,
                                             Qt.NoModifier),
              "leave": lambda: QDragLeaveEvent(),
              "drop": lambda: QDropEvent(QPointF(point), Qt.MoveAction, mime, Qt.LeftButton,
                                         Qt.NoModifier)}
    results = []
    for kind in kinds:
        event = events[kind]()
        QApplication.sendEvent(widget, event)
        results.append(event.isAccepted())
    return results


@pytest.fixture
def dragging(form):
    """A VP6 drag of lblCard in progress (as Drag starts it)."""
    controls._DRAGGING.update(source=form.lblCard, drag=object(), target=None)
    yield form.lblCard
    controls._DRAGGING.update(source=None, drag=None, target=None)


# --- pointers --------------------------------------------------------------------------------

def test_mouse_pointer(form, tmp_path):
    widget = form.txt._widget
    assert widget.cursor().shape() == Qt.IBeamCursor  # a TextBox's own
    form.txt.MousePointer = vpSizeWE
    assert widget.cursor().shape() == Qt.SizeHorCursor
    form.txt.MousePointer = vpDefault  # its own again
    assert widget.cursor().shape() == Qt.IBeamCursor
    form.lblCard.MousePointer = vpCrosshair
    assert form.lblCard._widget.cursor().shape() == Qt.CrossCursor
    picture = tmp_path / "hand.png"
    image = QImage(16, 16, QImage.Format_ARGB32)
    image.fill(0xFF00FF00)
    image.save(str(picture))
    form.pic.MouseIcon = str(picture)
    form.pic.MousePointer = vpCustom  # its MouseIcon
    assert form.pic._widget.cursor().shape() == Qt.BitmapCursor
    form.MousePointer = vpCrosshair  # a form's
    assert form._widget.cursor().shape() == Qt.CrossCursor
    form.MousePointer = vpDefault
    assert form._widget.cursor().shape() == Qt.ArrowCursor


def test_screen_mouse_pointer(qapp):
    Screen.MousePointer = vpHourglass
    assert QApplication.overrideCursor().shape() == Qt.WaitCursor
    Screen.MousePointer = vpCrosshair  # (one at a time)
    assert QApplication.overrideCursor().shape() == Qt.CrossCursor
    Screen.MousePointer = vpDefault
    assert QApplication.overrideCursor() is None and Screen.MousePointer == vpDefault


def test_which_controls_have_them():
    for name in ("Label", "TextBox", "CommandButton", "PictureBox", "ComboBox", "FlexGrid"):
        cls = CONTROL_TYPES[name]
        assert {"MousePointer", "MouseIcon", "DragMode", "DragIcon", "OLEDropMode"} <= \
            set(cls._specs)
        assert {"DragDrop", "DragOver", "OLEDragDrop", "OLEDragOver"} <= set(cls.Events)
    for name in ("Timer", "Line", "Shape", "ImageList", "Menu", "Splitter"):
        assert "DragDrop" not in CONTROL_TYPES[name].Events
    assert EVENT_ARGS["DragOver"] == "Source, X, Y, State"
    assert EVENT_ARGS["OLEDragDrop"] == "Data, Effect, Button, Shift, X, Y"


# --- VB drag and drop ------------------------------------------------------------------------

def test_drag_over_and_drop(form, dragging):
    assert send(form.pic._widget, vp6_mime(), (20, 30)) == [True, True, True]
    assert form.events == [("DragOver", "lblCard", 20, 30, vpEnter),
                           ("DragOver", "lblCard", 20, 30, vpOver),
                           ("DragDrop", "lblCard", 20, 30)]
    form.events.clear()
    send(form.pic._widget, vp6_mime(), (5, 5), ("enter", "leave"))
    assert form.events[-1] == ("DragOver", "lblCard", 5, 5, vpLeave)
    form.refuse = True  # DragOver returning False: not here (the no-drop pointer)
    mime = vp6_mime()  # (kept: the event doesn't own it)
    enter = QDragEnterEvent(QPoint(5, 5), Qt.MoveAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(form.pic._widget, enter)
    assert enter.dropAction() == Qt.IgnoreAction  # (and not the form's to take)


def test_dropping_on_a_user_control(form, dragging):
    send(form.ctl._widget, vp6_mime(), (5, 5), ("enter", "drop"))
    assert form.events == [("ctl DragDrop", "lblCard")]


def test_drag_starts_ends_and_cancels(form, monkeypatch, tmp_path):
    seen = {}

    def fake_exec(self, actions):  # (the real one follows the mouse until a drop)
        seen.update(mime=self.mimeData().hasFormat(controls._VP6_DRAG_MIME),
                    pixmap=not self.pixmap().isNull(), source=controls._DRAGGING["source"])
        controls._DRAGGING.update(target=form.pic, pos=(7, 8))
        form.lblCard.Drag(vpEndDrag)  # drop where it is
        return Qt.MoveAction

    cancelled = []
    monkeypatch.setattr("vp6.controls.QDrag.exec", fake_exec)
    monkeypatch.setattr("vp6.controls.QDrag.cancel", lambda: cancelled.append(True))
    form.lblCard.Drag()  # vpBeginDrag
    assert seen == {"mime": True, "pixmap": True, "source": form.lblCard}
    assert form.events == [("DragDrop", "lblCard", 7, 8)] and cancelled == [True]
    assert controls._DRAGGING["source"] is None  # (over)
    form.lblCard.Drag(vpCancelDrag)  # (no drag: nothing)
    picture = tmp_path / "icon.png"
    image = QImage(20, 10, QImage.Format_ARGB32)
    image.fill(0xFFFF0000)
    image.save(str(picture))
    form.lblCard.DragIcon = str(picture)
    monkeypatch.setattr("vp6.controls.QDrag.exec",
                        lambda self, actions: seen.update(size=self.pixmap().size(),
                                                          spot=self.hotSpot()))
    form.lblCard.Drag(vpBeginDrag)
    assert seen["size"].width() == 20 and seen["spot"] == QPoint(10, 5)  # its DragIcon


def test_automatic_drag_mode(form, monkeypatch):
    started = []
    monkeypatch.setattr(type(form.cmdAuto), "Drag", lambda self, Action=1: started.append(self))
    QTest.mouseClick(form.cmdAuto._widget, Qt.LeftButton)
    assert started == [form.cmdAuto] and form.events == []  # no MouseDown, no Click
    form.cmdAuto.DragMode = 0
    QTest.mouseClick(form.cmdAuto._widget, Qt.LeftButton)
    assert form.events == ["MouseDown", "Click"] and form.cmdAuto.DragMode == vpAutomatic - 1


# --- drops from other programs --------------------------------------------------------------

def text_mime(text="hello"):
    mime = QMimeData()
    mime.setText(text)
    return mime


def test_ole_drops(form):
    send(form.txtOle._widget, text_mime(), (3, 4), ("enter", "move", "drop"))
    assert form.events == [("OLEDragOver", vpEnter), ("OLEDragOver", vpOver),
                           ("OLEDragDrop", "hello", 1, 3, 4)]
    assert form.txtOle.Text == ""  # (Manual: its events, not its own text drop)
    form.refuse = True
    mime = text_mime()
    enter = QDragEnterEvent(QPoint(3, 4), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(form.txtOle._widget, enter)
    assert enter.dropAction() == Qt.IgnoreAction
    send(form.txt._widget, text_mime("typed"), (3, 4), ("enter", "drop"))  # None: its own
    assert "typed" in form.txt.Text


def test_ole_drop_on_a_form(form):
    form.OLEDropMode = 1
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile("/tmp/a.txt"), QUrl.fromLocalFile("/tmp/b.txt")])
    send(form._container_widget(), mime, (300, 300), ("enter", "drop"))
    assert form.events[-1] == ("Form OLEDragDrop", ["/tmp/a.txt", "/tmp/b.txt"])


def test_data_object():
    mime = QMimeData()
    mime.setText("words")
    mime.setUrls([QUrl.fromLocalFile("/tmp/x.png"), QUrl("https://example.com")])
    data = DataObject(mime)
    assert data.GetFormat(vpCFText) and data.GetFormat(vpCFFiles) and not data.GetFormat(2)
    assert data.GetData(vpCFFiles) == ["/tmp/x.png"] and data.Files == ["/tmp/x.png"]
    assert data.GetData() == mime.text() and data.GetData(2) is None
    assert DataObject(QMimeData()).GetData(vpCFFiles) is None
