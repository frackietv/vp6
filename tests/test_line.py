"""The Line control: run time, the form file and the designer."""

import os

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest

from vp6 import Form, Frame, Label, Line, formfile, vpRed, vpSchemeDark, vpSchemeLight
from vp6.ide import icons
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.panels import Toolbox
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


# --- run time --------------------------------------------------------------------------------

class Drawing(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 300, 200
        self.lblUnder = Label(self, Caption="under", Left=0, Top=0, Width=300, Height=200)
        self.linDiagonal = Line(self, X1=20, Y1=20, X2=120, Y2=70, BorderWidth=3,
                                BorderColor=vpRed)
        self.fraBox = Frame(self, Left=150, Top=100, Width=140, Height=90)
        self.linInside = Line(self.fraBox, X1=10, Y1=40, X2=130, Y2=40)

    def Form_Load(self):
        self.clicks = 0

    def lblUnder_Click(self):
        self.clicks += 1


@pytest.fixture
def drawing(qapp):
    form = Drawing()
    form.Show()
    QTest.qWaitForWindowExposed(form._widget)
    yield form
    form.Unload()


def _pixel(form, x, y) -> QColor:
    return form._widget.grab().toImage().pixelColor(x, y)


def test_geometry_follows_the_points(drawing):
    line = drawing.linDiagonal
    assert line._widget.geometry() == QRect(17, 17, 107, 57)  # the box plus room for the width
    line.X2, line.Y2 = 40, 150  # changes apply at once
    assert line._widget.geometry() == QRect(17, 17, 27, 137)
    assert drawing.linInside._widget.parentWidget() is drawing.fraBox._widget
    assert (line.X1, line.Y1, line.X2, line.Y2) == (20, 20, 40, 150)


def test_drawing_styles_and_colors(drawing):
    red = _pixel(drawing, 70, 45)  # the middle of the diagonal
    assert red.red() > 150 and red.green() < 100
    drawing.linDiagonal.BorderStyle = 0  # Transparent
    assert _pixel(drawing, 70, 45).red() < 250 or _pixel(drawing, 70, 45).green() > 200
    drawing.linDiagonal.BorderStyle = 1
    drawing.linDiagonal.Visible = False
    assert not drawing.linDiagonal._widget.isVisible()
    # Without a BorderColor, the color scheme's text color: dark on light, light on dark
    drawing.ColorScheme = vpSchemeLight
    assert _pixel(drawing, 200, 140).lightness() < 100
    drawing.ColorScheme = vpSchemeDark
    assert _pixel(drawing, 200, 140).lightness() > 150


def test_clicks_go_through_and_no_events(drawing):
    QTest.mouseClick(drawing.lblUnder._widget, Qt.LeftButton, Qt.NoModifier, QPoint(70, 45))
    assert drawing.clicks == 1  # on the line, but the label underneath gets it
    assert Line.Events == () and drawing.linDiagonal._widget.focusPolicy() == Qt.NoFocus
    drawing.linDiagonal.ZIndex = 5
    assert drawing.linDiagonal.ZIndex == 5


# --- the form file and the designer ------------------------------------------------------------

def test_form_file_round_trip():
    body = ("def InitializeComponent(self):\n"
            "    self.linA = Line(self, X1=8, Y1=16, X2=200, Y2=16, BorderStyle=2)\n")
    form = formfile.parse_region_body(body, "Form1")
    assert form.control("linA").props == {"X1": 8, "Y1": 16, "X2": 200, "Y2": 16,
                                          "BorderStyle": 2}
    assert "self.linA = Line(self, X1=8, Y1=16, X2=200, Y2=16, BorderStyle=2)" in \
        formfile.generate_region(form)


@pytest.fixture
def designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    d.ask_create_array = lambda name: False  # "No" instead of a blocking message box
    d.resize(800, 600)
    d.show()
    yield d
    d.close()


def _at(d, x, y) -> QPoint:
    return d.form_canvas_rect().topLeft() + QPoint(x, y)


def _points(d, key):
    return tuple(d.form_def.control(key).props[k] for k in ("X1", "Y1", "X2", "Y2"))


def test_drawing_a_line_with_the_tool(designer):
    d = designer
    d.set_tool("Line")
    QTest.mousePress(d.overlay, Qt.LeftButton, Qt.NoModifier, _at(d, 17, 81))
    QTest.mouseMove(d.overlay, _at(d, 100, 60))
    QTest.mouseMove(d.overlay, _at(d, 199, 39))
    QTest.mouseRelease(d.overlay, Qt.LeftButton, Qt.NoModifier, _at(d, 199, 39))
    assert _points(d, "Line1") == (16, 80, 200, 40)  # from press to release (snapped)
    assert "self.Line1 = Line(self, X1=16, Y1=80, X2=200, Y2=40)" in d.document.text
    d.create_control("Line", None, None, _at(d, 40, 200))  # a click: a horizontal line
    assert _points(d, "Line2") == (40, 200, 140, 200)


def test_selecting_moving_and_dragging_the_ends(designer):
    d = designer
    d.create_control("Label", QRect(_at(d, 8, 8), _at(d, 300, 300)), None)
    d.create_control("Line", None, None, _at(d, 40, 40), _at(d, 200, 200))
    assert d.line_at(_at(d, 120, 120)) == "Line1"  # on the line
    assert d.control_at(_at(d, 180, 60)) == "Label1"  # inside its box, far from the line
    QTest.mouseClick(d.overlay, Qt.LeftButton, Qt.NoModifier, _at(d, 121, 119))
    assert d.selection == ["Line1"]
    handles = d.overlay._line_handles("Line1")
    assert set(handles) == {"p1", "p2"}  # handles at the ends only
    # Drag the end
    end = handles["p2"].center()
    QTest.mousePress(d.overlay, Qt.LeftButton, Qt.NoModifier, end)
    QTest.mouseMove(d.overlay, end + QPoint(20, 5))
    QTest.mouseMove(d.overlay, end + QPoint(40, -40))
    QTest.mouseRelease(d.overlay, Qt.LeftButton, Qt.NoModifier, end + QPoint(40, -40))
    assert _points(d, "Line1") == (40, 40, 240, 160)
    # Move the whole line
    QTest.mousePress(d.overlay, Qt.LeftButton, Qt.NoModifier, _at(d, 140, 100))
    QTest.mouseMove(d.overlay, _at(d, 150, 110))
    QTest.mouseMove(d.overlay, _at(d, 156, 116))
    QTest.mouseRelease(d.overlay, Qt.LeftButton, Qt.NoModifier, _at(d, 156, 116))
    assert _points(d, "Line1") == (56, 56, 256, 176)
    d.nudge(8, 0)  # arrow keys
    assert _points(d, "Line1") == (64, 56, 264, 176)
    d.nudge(8, 8, resize=True)  # Shift+arrows don't resize a line
    assert _points(d, "Line1") == (64, 56, 264, 176)
    d.undo()
    assert _points(d, "Line1") == (56, 56, 256, 176)
    d.select(["Line1"])
    d.copy_selection()
    d.paste()
    assert _points(d, "Line2") == (64, 64, 264, 184)  # pasted copies are offset


def test_hovering_over_an_end_shows_a_move_cursor(designer):
    # Regression: hovering over a selected Line's end raised KeyError('p2')
    d = designer
    d.create_control("Line", None, None, _at(d, 40, 40), _at(d, 200, 120))
    d.select(["Line1"])
    for end in ("p1", "p2"):
        QTest.mouseMove(d.overlay, d.overlay._line_handles("Line1")[end].center())
        assert d.overlay.cursor().shape() == Qt.SizeAllCursor
    QTest.mouseMove(d.overlay, _at(d, 300, 300))
    assert d.overlay.cursor().shape() == Qt.ArrowCursor


def test_properties_and_no_code_stub(designer):
    d = designer
    d.create_control("Line", None, None, _at(d, 40, 40))
    d.select(["Line1"])
    window = PropertiesWindow()
    window.set_designer(d)
    rows = [window.table.item(r, 0).text() for r in range(window.table.rowCount())]
    assert rows == ["(Name)", "Index", "BorderColor", "BorderStyle", "BorderWidth", "Tag",
                    "Visible", "X1", "X2", "Y1", "Y2", "ZIndex"]
    assert d.set_property("X2", 300) is None and _points(d, "Line1") == (40, 40, 300, 40)
    requests = []
    d.viewCodeRequested.connect(lambda obj, event: requests.append((obj, event)))
    QTest.mouseDClick(d.overlay, Qt.LeftButton, Qt.NoModifier, _at(d, 100, 40))
    assert requests == [("Line1", "")]  # no events: the IDE just shows the code
    from vp6.ide.codeeditor import CodeWindow

    window = CodeWindow(d.document)
    window.goto_event("Line1", "")
    assert "def Line1_" not in d.document.text


def test_toolbox_and_icon(qapp):
    assert "Line" in Toolbox().buttons
    assert not icons.icon("Line").isNull()
