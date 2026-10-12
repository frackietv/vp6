"""Chart (Qt Charts)."""

import pytest
from PySide6 import QtCharts
from PySide6.QtWidgets import QApplication

import vp6
from vp6 import Chart, Form
from vp6.chart import parse_chart_data


@pytest.fixture
def form(qapp):
    class Charts(Form):
        def InitializeComponent(self):
            self.events = []
            self.chtSales = Chart(self, Title="Sales", Animations=False)

        def chtSales_PointSelected(self, Series, DataPoint):
            self.events.append((Series, DataPoint))

    f = Charts()
    f.Show()
    yield f
    f.Unload()


def test_parse_chart_data():
    assert parse_chart_data(["|A|B", "Q1|1|2", "Q2|3|x"]) == (
        ["Q1", "Q2"], ["A", "B"], [[1.0, 2.0], [3.0, 0.0]])
    assert parse_chart_data(["5", "7"]) == (["", ""], [], [[5.0], [7.0]])


def test_data(form):
    chart = form.chtSales
    assert (chart.RowCount, chart.ColumnCount) == (4, 2)  # (the sample)
    assert chart.RowLabel(1) == "Q1" and chart.ColumnLabel(2) == "Costs"
    chart.ChartData = [["", "Apples", "Pears", "Plums"], ["2025", 3, 4, 5], ["2026", 6, 5, 4]]
    assert (chart.RowCount, chart.ColumnCount, chart.Data(2, 3)) == (2, 3, 4)
    assert chart.ChartData[1] == ["2025", 3, 4, 5]
    chart.ChartData = [[1, 2], [3, 4], [5, 6]]  # numbers alone
    assert chart.RowLabel(3) == "3" and chart.ColumnLabel(2) == "Series 2"
    chart.SetData(1, 1, 10)
    assert chart.Data(1, 1) == 10
    with pytest.raises(IndexError):
        chart.Data(9, 1)


def test_chart_from_a_recordset(form, tmp_path):
    db = vp6.CreateDatabase(str(tmp_path / "s.db"))
    db.Execute("CREATE TABLE sales (Quarter TEXT, North REAL, South REAL)")
    db.Execute("INSERT INTO sales VALUES ('Q1', 1.5, 2), ('Q2', 3, 4)")
    form.chtSales.ChartData = db.OpenRecordset("sales")
    db.Close()
    assert form.chtSales.ColumnLabel(1) == "North" and form.chtSales.Data(2, 2) == 4


@pytest.mark.parametrize("kind, series", [
    (vp6.vpChartLine, QtCharts.QLineSeries), (vp6.vpChartSpline, QtCharts.QSplineSeries),
    (vp6.vpChartArea, QtCharts.QAreaSeries), (vp6.vpChartBar, QtCharts.QBarSeries),
    (vp6.vpChartStackedBar, QtCharts.QStackedBarSeries),
    (vp6.vpChartPercentBar, QtCharts.QPercentBarSeries),
    (vp6.vpChartHorizontalBar, QtCharts.QHorizontalBarSeries),
    (vp6.vpChartPie, QtCharts.QPieSeries), (vp6.vpChartScatter, QtCharts.QScatterSeries)])
def test_chart_types(form, kind, series):
    form.chtSales.ChartType = kind
    made = form.chtSales._chart.series()
    assert made and all(isinstance(s, series) for s in made)


def test_point_selected_and_looks(form):
    chart = form.chtSales
    chart._chart.series()[0].barSets()[1].clicked.emit(2)
    assert form.events == [(2, 3)]
    chart.ChartType = vp6.vpChartPie
    chart._chart.series()[0].slices()[0].clicked.emit()
    assert form.events[-1] == (1, 1)
    chart.Legend = vp6.vpLegendNone
    assert not chart._chart.legend().isVisible()
    chart.ChartType, chart.AxisYMin, chart.AxisYMax = vp6.vpChartLine, 5, 50
    axis = [a for a in chart._chart.axes() if isinstance(a, QtCharts.QValueAxis)][0]
    assert (axis.min(), axis.max()) == (5, 50)
    chart.LogScale = True
    assert any(isinstance(a, QtCharts.QLogValueAxis) for a in chart._chart.axes())
    assert len(chart.SeriesColors) == 2


def test_follows_dark_and_copies(form):
    chart = form.chtSales
    form.ColorScheme = vp6.vpSchemeDark
    assert chart._chart.theme() == QtCharts.QChart.ChartThemeDark
    form.ColorScheme = vp6.vpSchemeLight
    assert chart._chart.theme() == QtCharts.QChart.ChartThemeLight
    chart.EditCopy()
    assert not QApplication.clipboard().image().isNull()
    assert chart.Picture.Width > 0
