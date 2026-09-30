"""Drawing on forms and PictureBoxes: Line, Circle, PSet, Print, Cls, Point,
TextWidth / TextHeight, the drawing properties, AutoRedraw and Paint."""

import math
import os
import subprocess
import sys
import textwrap

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest

from vp6 import (CommandButton, Form, Menu, PictureBox, UserControl, formfile, vpBlue, vpGreen,
                 vpRed, vpWhite, vpYellow)
from vp6.controls import CONTROL_TYPES
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.properties import PropertiesWindow

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


def shot_color(widget, x, y) -> str:
    """The color on screen at x, y of a widget (its image is in device pixels)."""
    image = widget.grab().toImage()
    ratio = image.devicePixelRatio()
    return image.pixelColor(round(x * ratio), round(y * ratio)).name()


class Canvas(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 300, 200
        self.BackColor = vpWhite
        self.AutoRedraw = True
        self.paints = 0

    def Form_Paint(self):
        self.paints += 1


@pytest.fixture
def form(qapp):
    form = Canvas()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def test_lines(form):
    form.Line(10, 10, 100, 10)
    assert form.Point(50, 10) == 0  # black: ForeColor unset, a light form
    assert form.Point(100, 10) == vpWhite  # (a line doesn't cover its end point, as in VB)
    assert (form.CurrentX, form.CurrentY) == (100, 10)
    form.Line(100, 50, Color=vpRed)  # from the current point
    assert form.Point(100, 30) == vpRed and (form.CurrentX, form.CurrentY) == (100, 50)
    form.Line(20, 20, 30, 0, vpBlue, Step=True)  # the second point relative to the first
    assert form.Point(35, 20) == vpBlue and form.CurrentX == 50
    form.ForeColor = vpGreen
    form.Line(10, 60, 50, 60)
    assert form.Point(30, 60) == vpGreen
    form.DrawWidth = 5  # wide
    form.Line(10, 80, 100, 80, vpRed)
    assert form.Point(50, 82) == vpRed and form.Point(50, 86) == vpWhite
    form.DrawWidth, form.DrawStyle = 1, 2  # dotted: some pixels drawn, some not
    form.Line(10, 100, 100, 100, vpBlue)
    row = [form.Point(x, 100) for x in range(10, 40)]
    assert vpBlue in row and vpWhite in row
    form.DrawStyle = 5  # transparent: nothing
    form.Line(10, 110, 100, 110, vpBlue)
    assert form.Point(50, 110) == vpWhite
    with pytest.raises(ValueError):
        form.Line(0, 0, 1, 1, Box="X")


def test_dashes_at_any_width_and_across_joined_lines(form):
    def row(y, start=10, end=200):
        return [form.Point(x, y) for x in range(start, end)]

    form.DrawWidth, form.DrawStyle = 3, 1  # wide and dashed: gaps
    form.Line(10, 20, 200, 20, vpRed)
    assert vpRed in row(20) and vpWhite in row(20)
    # A line drawn bit by bit (as following the mouse), each piece shorter than a dash
    form.DrawWidth = 1
    form.PSet(10, 50, vpWhite)
    for x in range(12, 200, 2):
        form.Line(x, 50, Color=vpBlue)  # from the current point
    pieces = row(50, 11, 199)
    assert vpBlue in pieces and vpWhite in pieces  # dashed, not solid
    form.DrawStyle = 0
    form.Line(10, 80, 200, 80, vpBlue)  # (solid is solid)
    assert vpWhite not in row(80, 10, 199)

    def freehand(y, color):  # a line drawn bit by bit, as following the mouse
        form.PSet(10, y, vpWhite)
        for x in range(12, 200, 2):
            form.Line(x, y, Color=color)

    for style, width in ((0, 1), (0, 4), (6, 1), (6, 4)):  # Solid, Inside Solid: all of it
        form.DrawStyle, form.DrawWidth = style, width
        freehand(100 + 10 * style + 3 * width, vpRed)
        y = 100 + 10 * style + 3 * width
        assert set(row(y, 11, 198)) == {vpRed}, (style, width)  # (198: the end point)
    form.DrawStyle, form.DrawWidth = 5, 4  # Transparent: nothing at all, no point either
    form.PSet(10, 190, vpRed)
    freehand(190, vpRed)
    assert vpRed not in row(190, 8, 199) and vpRed not in row(188, 8, 199)
    assert (form.CurrentX, form.CurrentY) == (198, 190)


def test_boxes(form):
    form.Line(10, 10, 50, 40, vpRed, "BF")  # filled with its color, both corners
    assert form.Point(10, 10) == form.Point(50, 40) == form.Point(30, 25) == vpRed
    assert form.Point(51, 41) == vpWhite
    form.Line(60, 10, 100, 40, vpBlue, "B")  # FillStyle Transparent: an outline
    assert form.Point(60, 25) == form.Point(100, 25) == form.Point(80, 40) == vpBlue
    assert form.Point(80, 25) == vpWhite
    form.FillStyle, form.FillColor = 0, vpYellow  # Solid fill
    form.Line(110, 10, 150, 40, vpBlue, "B")
    assert form.Point(130, 25) == vpYellow and form.Point(110, 25) == vpBlue
    form.FillStyle = 2  # Horizontal Line: some lines
    form.Line(160, 10, 200, 60, vpBlue, "B")
    column = [form.Point(180, y) for y in range(12, 58)]
    assert vpYellow in column and vpWhite in column
    form.DrawStyle, form.DrawWidth = 6, 6  # Inside Solid: inside the box's bounds
    form.Line(10, 100, 60, 150, vpRed, "B")
    assert form.Point(10, 125) == vpRed and form.Point(8, 125) == vpWhite


def test_circles(form):
    form.FillStyle, form.FillColor = 0, vpYellow
    form.DrawWidth = 3  # (the edge is antialiased: its middle is solid)
    form.Circle(50, 50, 30, vpBlue)
    form.DrawWidth = 1
    assert form.Point(50, 50) == vpYellow  # the fill
    assert form.Point(50, 20) == form.Point(80, 50) == vpBlue  # the edge
    assert form.Point(10, 10) == vpWhite and (form.CurrentX, form.CurrentY) == (50, 50)
    form.Circle(150, 50, 30, vpBlue, Aspect=0.5)  # an ellipse: wide and low
    assert form.Point(150, 25) == vpWhite and form.Point(150, 40) == vpYellow
    form.Circle(250, 50, 30, vpRed, math.pi / 4, math.pi)  # an arc: not filled
    assert form.Point(250, 40) == vpWhite
    # A pie slice (both ends negative; -0.0 is 3 o'clock): filled, the top right quarter
    form.Circle(50, 150, 30, vpRed, -0.0, -math.pi / 2)
    assert form.Point(60, 140) == vpYellow and form.Point(40, 160) == vpWhite
    form.Circle(10, 0, 5, Step=True)  # relative to the current point (the last center)
    assert (form.CurrentX, form.CurrentY) == (60, 150)


def test_points(form):
    form.PSet(5, 6, vpRed)
    assert form.Point(5, 6) == vpRed and form.Point(6, 6) == vpWhite
    assert (form.CurrentX, form.CurrentY) == (5, 6)
    form.PSet(2, 2, vpBlue, Step=True)
    assert form.Point(7, 8) == vpBlue
    form.DrawWidth = 6  # a round dot
    form.PSet(50, 50, vpGreen)
    assert form.Point(50, 50) == form.Point(51, 50) == vpGreen and form.Point(56, 50) == vpWhite
    assert form.Point(-1, 5) == form.Point(5, 500) == -1  # outside


def test_print_and_text_size(form):
    form.CurrentX, form.CurrentY = 10, 20
    form.Print("Hello", "there", end="")  # print's sep and end
    assert form.CurrentX == pytest.approx(10 + form.TextWidth("Hello there"))
    assert form.CurrentY == 20
    form.Print("!")  # then a new line: back at the left
    height = form.TextHeight("x")
    assert (form.CurrentX, form.CurrentY) == (0, pytest.approx(20 + height))
    form.Print("one\ntwo")
    assert form.CurrentY == pytest.approx(20 + 3 * height)
    assert form.TextHeight("a\nb") == pytest.approx(2 * height)
    assert form.TextWidth("ab\nabcd") == form.TextWidth("abcd") > form.TextWidth("ab") > 0
    pixels = [form.Point(x, y) for x in range(10, 60) for y in range(20, 20 + int(height))]
    assert 0 in pixels or any(p != vpWhite for p in pixels)  # some text was drawn
    form.FontSize = 30  # the Font
    assert form.TextHeight("x") > height


def test_cls(form, tmp_path):
    form.Line(0, 0, 100, 100, vpRed, "BF")
    form.CurrentX = 7
    form.Cls()
    assert form.Point(50, 50) == vpWhite and (form.CurrentX, form.CurrentY) == (0, 0)


def test_auto_redraw_and_paint(qapp):
    class Painted(Form):
        def InitializeComponent(self):
            self.BackColor = vpWhite
            self.paints = 0

        def Form_Paint(self):
            self.paints += 1
            self.Line(0, 0, 40, 40, vpBlue, "BF")  # (drawn again at every Paint)

    form = Painted()
    form.Show()
    QTest.qWait(20)
    assert form.paints >= 1 and form.Point(20, 20) == vpBlue
    before = form.paints
    form.Refresh()
    QTest.qWait(20)
    assert form.paints > before
    form.AutoRedraw = True  # no more Paint
    before = form.paints
    form.Refresh()
    QTest.qWait(20)
    assert form.paints == before
    form.Unload()


def test_auto_redraw_keeps_the_drawing_when_the_form_grows(form):
    form.Line(200, 150, 299, 199, vpRed, "BF")
    form.Width, form.Height = 500, 400
    QTest.qWait(10)
    form.Line(400, 300, 450, 350, vpBlue, "BF")  # (on the larger part too)
    assert form.Point(250, 180) == vpRed and form.Point(420, 320) == vpBlue
    form.Width, form.Height = 100, 100  # smaller...
    form.Width, form.Height = 500, 400  # ...and back: still there
    QTest.qWait(10)
    assert form.Point(250, 180) == vpRed
    assert form.paints == 0  # (AutoRedraw)


def test_under_the_controls(form):
    button = CommandButton(form, Left=10, Top=10, Width=80, Height=40)
    form.Line(0, 0, 150, 100, vpRed, "BF")
    assert form.Point(30, 30) == vpRed  # under the button
    assert shot_color(form._widget, 120, 80) == "#ff0000"  # beside it
    assert shot_color(form._widget, 30, 30) != "#ff0000"  # the button is on top
    button.Visible = False


def test_on_a_picture_box(qapp, tmp_path):
    picture = str(tmp_path / "p.png")
    image = QImage(40, 40, QImage.Format_RGB32)
    image.fill(0x00FF00)  # green
    image.save(picture)

    class Pictures(Form):
        def InitializeComponent(self):
            self.picDraw = PictureBox(self, Left=10, Top=10, Width=100, Height=80,
                                      BackColor=vpWhite, Picture=picture, AutoRedraw=True)
            self.picPaint = PictureBox(self, Left=150, Top=10, Width=100, Height=80,
                                       BorderStyle=0, BackColor=vpWhite)

        def picPaint_Paint(self):
            self.picPaint.Line(0, 0, self.picPaint.ScaleWidth, self.picPaint.ScaleHeight,
                               vpBlue, "BF")

    form = Pictures()
    form.Show()
    QTest.qWait(20)
    box = form.picDraw
    assert box.ScaleWidth == 100 - 2 * box._widget.frameWidth()  # inside its border
    assert box.Point(5, 5) == vpGreen and box.Point(60, 60) == vpWhite  # its picture
    box.Line(50, 0, 80, 30, vpRed, "BF")
    box.Print("x")
    assert box.Point(60, 10) == vpRed and box.CurrentY > 0
    origin = box._widget.mapTo(form._widget, QPoint(0, 0)) + box._widget.contentsRect().topLeft()
    point = origin + QPoint(60, 10)  # (0, 0) is inside the border
    assert shot_color(form._widget, point.x(), point.y()) == "#ff0000"
    box.Cls()  # the drawing goes, the Picture stays
    assert box.Point(60, 10) == vpWhite and box.Point(5, 5) == vpGreen
    assert form.picPaint.Point(50, 40) == vpBlue  # its Paint
    assert "Paint" in PictureBox.Events and "FontName" in PictureBox._specs
    form.Unload()


def test_with_a_menu_bar_in_the_window(qapp):
    class WithMenu(Form):
        def InitializeComponent(self):
            self.BackColor = vpWhite
            self.AutoRedraw = True
            self.mnuFile = Menu(self, Caption="&File")

    form = WithMenu()
    form.Show()
    QTest.qWait(10)
    form.Line(0, 0, 20, 20, vpRed, "BF")  # at the client area's top left
    assert form.Point(10, 10) == vpRed
    assert shot_color(form._drawing_surface(), 10, 10) == "#ff0000"
    form.Unload()


class ctlDial(UserControl):
    def InitializeComponent(self):
        self.Surface.Width, self.Surface.Height = 60, 60
        self.Surface.BackColor = vpWhite
        self.painted = 0

    def UserControl_Paint(self):
        self.painted += 1
        self.Surface.FillStyle, self.Surface.FillColor = 0, vpRed
        self.Surface.Circle(30, 30, 20, vpRed)


def test_a_user_controls_paint(qapp):
    class Holder(Form):
        def InitializeComponent(self):
            self.dial = ctlDial(self, Left=10, Top=10)

    form = Holder()
    form.Show()
    QTest.qWait(20)
    assert form.dial.painted >= 1 and form.dial.Surface.Point(30, 30) == vpRed
    form.Unload()


def test_properties_and_form_file():
    names = ("AutoRedraw", "DrawWidth", "DrawStyle", "FillStyle", "FillColor")
    for cls in (Form, PictureBox):
        assert set(names) <= set(cls._specs)
        assert "Paint" in cls.Events
    assert (Form._specs["DrawWidth"].default, Form._specs["FillStyle"].default) == (1, 1)
    body = ("def InitializeComponent(self):\n"
            "    self.AutoRedraw = True\n"
            "    self.DrawWidth = 3\n"
            "    self.picA = PictureBox(self, Left=8, Top=8, Width=64, Height=48, "
            "FillStyle=0, FillColor=0xff)\n")
    region = " ".join(formfile.generate_region(formfile.parse_region_body(body, "Form1")).split())
    assert "self.AutoRedraw = True" in region and "self.DrawWidth = 3" in region
    assert "FillStyle=0, FillColor=0x0000FF" in region or "FillStyle=0, FillColor=255" in region


def test_the_designer_doesnt_paint(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    source = formfile.new_form_source("Form1").replace(
        "    # endregion", "    # endregion\n\n    def Form_Paint(self):\n"
        "        raise RuntimeError('not in the designer')\n", 1)
    path.write_text(source)
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    designer.show()
    QTest.qWait(20)  # (painted, without Form_Paint)
    designer.select([])
    window = PropertiesWindow()
    window.set_designer(designer)
    rows = [window.table.item(r, 0).text() for r in range(window.table.rowCount())]
    assert {"AutoRedraw", "DrawWidth", "DrawStyle", "FillStyle", "FillColor"} <= set(rows)
    designer.close()
    assert "Paint" in CONTROL_TYPES["PictureBox"].Events


@pytest.mark.skipif(sys.platform != "darwin", reason="the macOS style (not offscreen)")
def test_point_on_the_macos_style():
    # Point renders a PictureBox's frame: the macOS style must be able to draw it
    code = textwrap.dedent("""
        from vp6 import Form, PictureBox, vpRed
        from vp6.app import ensure_app
        ensure_app()
        class F(Form):
            def InitializeComponent(self):
                self.pic = PictureBox(self, Width=100, Height=80, AutoRedraw=True)
        form = F()
        form.pic.Line(0, 0, 50, 50, vpRed, "BF")
        print(form.pic.Point(10, 10))
    """)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}  # (the real one)
    env["PYTHONPATH"] = root
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                         timeout=60)
    assert out.stdout.strip() == str(vpRed), out.stderr
    assert "graphics context" not in out.stderr, out.stderr
