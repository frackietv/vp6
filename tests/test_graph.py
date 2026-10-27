"""The Graph: a coordinate plane, number line and data plot for mathematics."""

import math
from fractions import Fraction

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import vp6
from vp6 import Form, Graph, GraphItem
from vp6 import graph as graph_module
from vp6.graph import (five_numbers, function_of, histogram_bins, least_squares, nice_step,
                       number_text, pi_step, pi_text)
from vp6edu import answers


@pytest.fixture
def form(qapp):
    class Graphs(Form):
        def InitializeComponent(self):
            self.Width, self.Height = 420, 320
            self.events = []
            # 400 x 300 pixels for -10..10 by -7.5..7.5: 20 pixels a unit, 0 at (200, 150)
            self.grfPlane = Graph(self, Left=0, Top=0, Width=400, Height=300, BorderStyle=0,
                                  YMin=-7.5, YMax=7.5)

        def grfPlane_Click(self, X, Y):
            self.events.append(("Click", round(X, 6), round(Y, 6)))

        def grfPlane_PointMoved(self, Item):
            self.events.append(("PointMoved", Item))

        def grfPlane_MouseDown(self, Button, Shift, X, Y):
            self.events.append(("MouseDown", round(X, 6), round(Y, 6)))

    f = Graphs()
    f.Show()
    yield f
    f.Unload()


def px(x, y):
    """A point of the test's plane in its pixels."""
    return QPoint(round(200 + 20 * x), round(150 - 20 * y))


def grab(graph):
    return graph._widget.grab().toImage()


def color_at(image, x, y) -> QColor:
    ratio = image.devicePixelRatio()
    return image.pixelColor(round(x * ratio), round(y * ratio))


def near(color: QColor, name: str, tolerance=60) -> bool:
    other = QColor(name)
    return abs(color.red() - other.red()) + abs(color.green() - other.green()) + \
        abs(color.blue() - other.blue()) < tolerance


# --- expressions, ticks, statistics ---------------------------------------------------------------

def test_function_of_reads_typed_maths():
    assert function_of("2x + 1")(3) == 7
    assert function_of("y = x^2 - 3")(2) == 1
    assert function_of("f(x) = 3x")(2) == 6
    assert function_of("x²")(4) == 16
    assert function_of("sin x")(math.pi / 2) == pytest.approx(1)
    assert function_of("√x")(9) == 3
    assert math.isnan(function_of("√x")(-1))  # (not real)
    assert math.isnan(function_of("1/(x - 2)")(2))  # (undefined)
    assert function_of("x^(1/3)")(-8) == pytest.approx(-2)  # (an odd root of a negative)
    assert math.isnan(function_of("x^(1/2)")(-4))
    assert function_of("2πr", ("r",))(1) == pytest.approx(2 * math.pi)
    assert function_of("1 + cos θ", ("theta", "t"))(0, 0) == 2
    assert function_of("e^x")(0) == 1
    with pytest.raises(ValueError, match="has no value"):
        function_of("x + y")
    with pytest.raises(answers.Unreadable):
        function_of("2x +")


def test_tick_steps_and_numbers():
    assert nice_step(20, 400, 40) == 2
    assert nice_step(20, 400, 90) == 5
    assert nice_step(1, 400, 40) == 0.1
    assert pi_step(4 * math.pi, 400, 45) == Fraction(1, 2)
    assert pi_step(40 * math.pi, 400, 45) == 8
    assert [pi_text(Fraction(n, 2)) for n in (-3, -2, -1, 0, 1, 2, 3)] == \
        ["−3π/2", "−π", "−π/2", "0", "π/2", "π", "3π/2"]
    assert number_text(0.30000000000000004, 0.1) == "0.3"
    assert number_text(-2, 1) == "−2" and number_text(1e-17, 0.5) == "0"
    assert number_text(2500000, 500000) == "2.5e+06"


def test_statistics():
    # OpenStax Introductory Statistics 2e, 2.3: 1 11.5 6 7.2 4 8 9 10 6.8 8.3 2 2 10 1
    data = [1, 11.5, 6, 7.2, 4, 8, 9, 10, 6.8, 8.3, 2, 2, 10, 1]
    assert five_numbers(data) == (1, 2, 7, 9, 11.5)
    assert five_numbers([1, 2, 3, 4, 5]) == (1, 1.5, 3, 4.5, 5)  # (the middle value left out)
    assert histogram_bins([1, 2, 2, 3, 4], [0, 2, 4]) == ([0, 2, 4], [1, 4])
    edges, counts = histogram_bins(range(16))  # (Sturges: 5 bins)
    assert len(counts) == 5 and sum(counts) == 16
    slope, intercept, r = least_squares([(1, 3), (2, 5), (3, 7)])
    assert (slope, intercept, r) == pytest.approx((2, 1, 1))
    assert all(math.isnan(v) for v in least_squares([(1, 1)]))


# --- the view -----------------------------------------------------------------------------------

def test_view_equal_scales_and_data(form):
    graph = form.grfPlane
    assert graph._view() == pytest.approx((-10, 10, -7.5, 7.5))
    graph.YMin, graph.YMax = -10, 10  # (taller: X grows to keep a unit square)
    assert graph._view() == pytest.approx((-40 / 3, 40 / 3, -10, 10))
    graph.EqualScales = False
    assert graph._view() == pytest.approx((-10, 10, -10, 10))
    assert (graph.ScaleLeft, graph.ScaleTop, graph.ScaleWidth, graph.ScaleHeight) == \
        pytest.approx((-10, 10, 20, -20))
    graph.Scale(0, 5, 4, -5)
    assert (graph.XMin, graph.XMax, graph.YMin, graph.YMax) == (0, 4, -5, 5)
    graph.ScaleLeft = 1
    assert (graph.XMin, graph.XMax) == (1, 5)
    with pytest.raises(ValueError):
        graph.ScaleWidth = -2
    graph.ResetView()  # (as it was made)
    assert (graph.XMin, graph.XMax, graph.YMin, graph.YMax) == (-10, 10, -7.5, 7.5)
    graph.Mode = vp6.vpGraphNumberLine  # (one axis: Y around 0)
    x0, x1, y0, y1 = graph._view()
    assert (x0, x1) == (-10, 10) and y0 == -y1


def test_zoom_to_fit_and_data_mode(form):
    graph = form.grfPlane
    graph.AddPoint(2, 3)
    graph.AddSegment(-1, -2, 4, 1)
    graph.ZoomToFit()
    x0, x1, y0, y1 = graph._view()
    assert x0 < -1 and x1 > 4 and y0 < -2 and y1 > 3 and x1 - x0 < 8
    graph.Clear()
    graph.Mode = vp6.vpGraphData
    histogram = graph.AddHistogram([150, 155, 160, 161, 170], Bins=[150, 160, 170])
    assert histogram.Counts == [2, 3] and histogram.Edges == [150, 160, 170]
    assert graph.YMin == 0 and graph.XMin < 150 < 170 < graph.XMax  # (fitted to the data)
    assert graph._area().left() > 20  # (room for the numbers)


# --- items --------------------------------------------------------------------------------------

def test_items(form):
    graph = form.grfPlane
    f = graph.AddFunction("x^2", XMin=-2, XMax=2, Key="square")
    assert isinstance(f, GraphItem) and f.Kind == "Function" and f.Value(3) == 9
    assert graph.Items("square") is f and graph.Items(1) is f and f.Index == 1
    assert graph.Items.Count == 1 and len(graph.Items) == 1
    p = graph.AddPoint(1, 2, Label="A", Open=True)
    assert (p.X, p.Y, p.Open, p.Label) == (1, 2, True, "A")
    p.X = 3
    assert p.X == 3.0
    with pytest.raises(AttributeError, match="no Radius"):
        p.Radius = 2
    with pytest.raises(AttributeError, match="no X1"):
        print(p.X1)
    slider = graph.AddPoint(1, On=f, Draggable=True)  # (on the curve)
    assert slider.Y == 1
    slider.X = 1.5
    assert slider.Y == 2.25
    a, b = graph.AddPoint(0, 1), graph.AddPoint(2, 5)
    line = graph.AddLine(a, b)
    assert line.Points == [(0, 1), (2, 5)] and (line.X2, line.Y2) == (2, 5)
    b.Y = 7
    assert line.Y2 == 7  # (it follows its points)
    with pytest.raises(AttributeError, match="follows its points"):
        line.X1 = 4
    triangle = graph.AddPolygon([a, b, (4, 0)])
    assert triangle.Points == [(0, 1), (2, 7), (4, 0)]
    box = graph.AddBoxPlot([1, 11.5, 6, 7.2, 4, 8, 9, 10, 6.8, 8.3, 2, 2, 10, 1])
    assert (box.Min, box.Q1, box.Median, box.Q3, box.Max) == (1, 2, 7, 9, 11.5)
    with pytest.raises(AttributeError, match="can't be set"):
        box.Median = 3
    scatter = graph.AddScatter([1, 2, 3], [2, 4, 6.5], FitLine=True)
    assert scatter.Slope == pytest.approx(2.25) and scatter.Correlation > 0.99
    graph.Items.Remove(b)  # (what follows it goes too)
    assert line not in list(graph.Items) and triangle not in list(graph.Items)
    with pytest.raises(KeyError):
        graph.Items("nothing")
    with pytest.raises(ValueError, match="not unique"):
        graph.AddPoint(0, 0, Key="square")
    with pytest.raises(TypeError):
        graph.AddLine(a, (1, 2))
    with pytest.raises(ValueError):
        graph.AddInequality("y = 2x")
    p.Remove()
    graph.Clear()
    assert graph.Items.Count == 0
    assert graph.AddPoint(0, 0)._auto == 0  # (the colors start again)


def test_every_kind_draws(form):
    graph = form.grfPlane
    graph.AddFunction(lambda x: x / 2)
    graph.AddParametric("cos t", "sin t")
    graph.AddPolar("2")
    graph.AddPoint(1, 1)
    graph.AddSegment(0, 0, 1, 2)
    graph.AddRay(0, 0, 1, -1)
    graph.AddLine(0, 1, 1, 1)
    graph.AddVector(0, 0, -2, 2)
    graph.AddPolygon([(1, 1), (3, 1), (2, 3)], FillColor=vp6.vpYellow)
    graph.AddRegion("x^2", "x", 0, 1)
    graph.AddInequality("y > 3")
    graph.AddLabel("$\\frac{1}{2}$ here", -5, 5, Alignment=vp6.vpCenter)
    graph.AddInterval(None, -6, HighClosed=False)
    graph.AddHistogram([1, 2, 2, 3])
    graph.AddDotPlot([1, 1, 2])
    graph.AddScatter([(1, 1), (2, 3)], FitLine=True)
    graph.AddBoxPlot([1, 2, 3, 4, 5], Y=-5)
    grab(graph)
    assert all(item._error is None for item in graph.Items)


def test_plots_in_pixels(form):
    graph = form.grfPlane
    graph.ShowGrid = False
    graph.AddFunction("1/(x - 2)", Color=vp6.vpRed)  # (an asymptote at x = 2)
    graph.AddFunction("x + 1", XMin=-8, XMax=-4, Color=vp6.vpBlue)  # (a domain)
    graph.AddInequality("y < -6", FillColor=vp6.RGB(0, 200, 0))
    image = grab(graph)
    assert near(color_at(image, *px(3, 1).toTuple()), "#ff0000")  # (on 1/(x-2) at 3)
    column = [color_at(image, px(2, 0).x(), y) for y in range(px(0, 4).y(), px(0, -2).y())]
    assert not any(near(c, "#ff0000") for c in column)  # (the branches aren't joined)
    assert near(color_at(image, *px(-6, -5).toTuple()), "#0000ff", 100)
    assert not near(color_at(image, *px(-2, -1).toTuple()), "#0000ff")  # (outside its domain)
    assert near(color_at(image, *px(5, -6.5).toTuple()), "#00c800", 90)  # (shaded below)
    assert not near(color_at(image, *px(5, -5).toTuple()), "#00c800", 90)


def test_light_and_dark(form):
    graph = form.grfPlane
    item = graph.AddFunction("2")
    light = grab(graph)
    assert color_at(light, 20, 20).lightness() > 200
    assert near(color_at(light, *px(5, 2).toTuple()), graph_module.PLOT_COLORS[0][0])
    form.ColorScheme = vp6.vpSchemeDark
    dark = grab(graph)
    assert color_at(dark, 20, 20).lightness() < 80
    assert near(color_at(dark, *px(5, 2).toTuple()), graph_module.PLOT_COLORS[0][1])
    item.Color = vp6.vpYellow
    assert near(color_at(grab(graph), *px(5, 2).toTuple()), "#ffff00")
    form.ColorScheme = vp6.vpSchemeLight


def test_failing_function_is_reported(form, monkeypatch):
    reported = []
    monkeypatch.setattr("vp6.app.report_runtime_error", reported.append)
    item = form.grfPlane.AddFunction(lambda x: undefined_name)  # noqa: F821
    grab(form.grfPlane)
    QApplication.processEvents()
    assert isinstance(item._error, NameError) and len(reported) == 1
    grab(form.grfPlane)  # (not drawn again: reported once)
    QApplication.processEvents()
    assert len(reported) == 1


# --- the mouse --------------------------------------------------------------------------------

def test_click_and_mouse_events_in_graph_units(form):
    widget = form.grfPlane._widget
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, px(3, -2))
    assert ("MouseDown", 3, -2) in form.events and ("Click", 3, -2) in form.events


def test_dragging_a_point(form):
    graph = form.grfPlane
    point = graph.AddPoint(1, 1, Draggable=True)
    widget = graph._widget
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, px(1, 1))
    QTest.mouseMove(widget, px(2.2, 2.9))
    QTest.mouseMove(widget, px(3.1, 4.2))
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, px(3.1, 4.2))
    assert (point.X, point.Y) == (3, 4)  # (in steps of Snap)
    assert [e for e in form.events if e[0] == "PointMoved"] == [("PointMoved", point)] * 2
    assert not any(e[0] == "Click" for e in form.events)  # (dragged, not clicked)
    assert graph._view() == pytest.approx((-10, 10, -7.5, 7.5))  # (not panned)


def test_panning_and_zooming(form):
    graph = form.grfPlane
    widget = graph._widget
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, px(0, 0))
    QTest.mouseMove(widget, px(1, 0))
    QTest.mouseMove(widget, px(2, 1))
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, px(2, 1))
    assert graph._view() == pytest.approx((-12, 8, -8.5, 6.5))
    graph.ResetView()
    wheel = QWheelEvent(QPointF(px(0, 0)), QPointF(widget.mapToGlobal(px(0, 0))), QPoint(),
                        QPoint(0, 120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(widget, wheel)
    x0, x1, y0, y1 = graph._view()
    assert x1 - x0 < 20 and (x0 + x1) / 2 == pytest.approx(0)  # (in, around the mouse)
    graph.PanZoom = False
    QApplication.sendEvent(widget, wheel)
    assert graph._view()[1] == pytest.approx(x1)


def test_placing_a_point_and_a_line(form):
    graph = form.grfPlane
    widget = graph._widget
    graph.PlaceMode = vp6.vpPlacePoint
    assert graph.Answer is None
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, px(2.1, -2.9))
    assert (graph.Answer.X, graph.Answer.Y) == (2, -3)
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, px(4, 1))  # (moved there)
    assert answers.Point(4, 1).check(graph.Answer).status == answers.RIGHT
    graph.PlaceMode = vp6.vpPlaceLine  # (what was placed goes)
    assert graph.Answer is None and graph.Items.Count == 0
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, px(0, 1))
    assert graph.Answer is None
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, px(1, 3))
    assert graph.Answer.Kind == "Line"
    assert answers.Line("y = 2x + 1").check(graph.Answer).status == answers.RIGHT
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, px(5, 5))  # (two are enough)
    assert graph.Items.Count == 3
    graph.ClearAnswer()
    assert graph.Items.Count == 0


def test_placing_intervals_on_a_number_line(form):
    graph = form.grfPlane
    graph.Mode = vp6.vpGraphNumberLine
    graph.PlaceMode = vp6.vpPlaceInterval
    widget = graph._widget
    y = graph._mapping()[0](0, 0)[1]
    at = lambda x: QPoint(round(200 + 20 * x), round(y))  # noqa: E731
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, at(-2))
    QTest.mouseMove(widget, at(1))
    QTest.mouseMove(widget, at(3))
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, at(3))
    QTest.mouseClick(widget, Qt.LeftButton, Qt.NoModifier, at(-2))  # (that end: open)
    assert answers.Inequality("-2 < x <= 3").check(graph.Answer).status == answers.RIGHT
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, at(5))  # (a ray, past the edge)
    QTest.mouseMove(widget, at(7))
    QTest.mouseMove(widget, QPoint(widget.width() - 1, round(y)))
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, QPoint(widget.width() - 1, round(y)))
    result = answers.Inequality("-2 < x <= 3 or x >= 5").check(graph.Answer)
    assert result.status == answers.RIGHT, result.message
    assert graph.Intervals == graph.Answer
    graph.AddInterval(-9, -8)  # (one of the program's: in Intervals, not the Answer)
    assert len(graph.Intervals) == 3 and len(graph.Answer) == 2


# --- the graphics methods -------------------------------------------------------------------------

def test_graphics_methods_in_graph_units(form):
    graph = form.grfPlane
    graph.ShowGrid = graph.ShowAxes = False
    graph.DrawWidth = 3
    graph.Line(1, 1, 5, 1, vp6.vpRed)  # (outside Paint: kept)
    assert (graph.CurrentX, graph.CurrentY) == pytest.approx((5, 1))
    graph.DrawWidth = 1
    assert near(color_at(grab(graph), *px(3, 1).toTuple()), "#ff0000")
    graph.Scale(-9, 8.5, 11, -6.5)  # (the view moved: the line with it)
    image = grab(graph)
    assert near(color_at(image, *px(2, 0).toTuple()), "#ff0000")
    assert not near(color_at(image, *px(3, 1).toTuple()), "#ff0000")
    graph.Cls()
    assert not near(color_at(grab(graph), *px(2, 0).toTuple()), "#ff0000")


def test_paint_event_draws_over_the_plots(qapp):
    class Painted(Form):
        def InitializeComponent(self):
            self.grfDraw = Graph(self, Width=400, Height=300, BorderStyle=0, YMin=-7.5,
                                 YMax=7.5)

        def grfDraw_Paint(self):
            self.grfDraw.Line(-2, -2, 2, 2, vp6.vpBlue, "BF")

    form = Painted()
    form.Show()
    try:
        assert near(color_at(grab(form.grfDraw), *px(1, -1).toTuple()), "#0000ff")
        assert not form.grfDraw._drawn  # (drawn in Paint: not kept)
    finally:
        form.Unload()


def test_pictures(form):
    graph = form.grfPlane
    graph.AddFunction("x")
    assert graph.Picture.Width == 400
    graph.EditCopy()
    assert not QApplication.clipboard().image().isNull()


def test_designer_makes_a_graph(qapp):
    from vp6.ide.designer import NAME_PREFIX
    from vp6.metadata import category_of_type

    assert NAME_PREFIX["Graph"] == "Graph" and category_of_type("Graph") == "Graphics"
