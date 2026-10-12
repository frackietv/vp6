"""The ``Chart``: VB's MSChart, on Qt Charts.

    self.chtSales.ChartData = [["", "Sales", "Costs"],
                               ["Q1", 10, 8], ["Q2", 14, 9], ["Q3", 12, 11]]
    self.chtSales.ChartType = vpChartBar

* ``ChartData`` is a table: rows are the categories along the X axis (the
  first value of each row its ``RowLabel``), columns the series (the first
  row their ``ColumnLabel``s, starting with an empty cell). Rows of numbers
  alone are fine too (the labels are then 1, 2, 3 and Series 1, 2...). A
  ``Recordset`` works as well: its first field gives the row labels, the
  others the series. In the designer it is lines of text: ``|Sales|Costs``
  for the labels, then ``Q1|10|8``.
* ``ChartType``: vpChartLine, vpChartSpline, vpChartArea, vpChartBar,
  vpChartStackedBar, vpChartPercentBar, vpChartHorizontalBar, vpChartPie (the
  first series), vpChartScatter.
* ``Title``, ``Legend`` (where: vpLegendNone, Top, Bottom, Left, Right),
  ``AxisXTitle``, ``AxisYTitle``, ``AxisYMin``/``AxisYMax`` (unset: from the
  data), ``LogScale`` (a logarithmic Y axis), ``Animations``. It follows the
  form's light or dark scheme.
* ``RowCount``, ``ColumnCount``, ``Data(Row, Column)`` and ``SetData(Row,
  Column, Value)``, ``RowLabel(Row)``, ``ColumnLabel(Column)`` (all from 1).
* ``PointSelected(Series, DataPoint)`` fires when a point, bar or slice is
  clicked (both from 1). ``EditCopy()`` copies the chart to the clipboard as
  a picture; ``Picture`` is it as a Picture (for SavePicture).
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication, QFrame, QLabel

from ._props import P, enum_choices
from .controls import (_FONT, CONTROL_TYPES, EVENT_ARGS, Control, _add_mouse_members,
                       _add_validation, _geometry)

EVENT_ARGS.update({"PointSelected": "Series, DataPoint"})

_SAMPLE = ["|Sales|Costs", "Q1|10|8", "Q2|14|9", "Q3|12|11", "Q4|18|12"]


def parse_chart_data(lines) -> tuple[list[str], list[str], list[list[float]]]:
    """The designer's ChartData lines as (row labels, column labels, values by row)."""
    lines = [str(line) for line in lines or [] if str(line).strip()]
    columns: list[str] = []
    if lines and lines[0].startswith("|"):
        columns = [part.strip() for part in lines.pop(0).split("|")[1:]]
    rows, values = [], []
    for line in lines:
        parts = [part.strip() for part in line.split("|")]
        label, numbers = (parts[0], parts[1:]) if len(parts) > 1 else ("", parts)
        rows.append(label)
        values.append([_number(n) for n in numbers])
    return rows, columns, values


def _number(value) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _charts():
    """Qt Charts (PySide6's QtCharts), or None where it isn't installed."""
    try:
        from PySide6 import QtCharts
    except ImportError:
        return None
    return QtCharts


class Chart(Control):
    """VB's MSChart (the module's documentation)."""

    TypeName = "Chart"
    DefaultEvent = "PointSelected"
    DefaultSize = (401, 281)
    Events = ("PointSelected", "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _design_values = ("ChartData",)  # (the designer's lines; at run time a table)
    Properties = (
        *_geometry(*DefaultSize),
        P("ChartType", "enum", 3,
          enum_choices("Line", "Spline", "Area", "Bar", "Stacked Bar", "Percent Bar",
                       "Horizontal Bar", "Pie", "Scatter"),
          description="How the data is drawn (a Pie shows the first series)"),
        P("ChartData", "list", _SAMPLE,
          description="The data, one row per line: Label|value|value... (a first line "
                      "|Name|Name... names the series)"),
        P("Title", "str", "", description="The title above the chart"),
        P("Legend", "enum", 2, enum_choices("None", "Top", "Bottom", "Left", "Right"),
          description="Where the legend (the series' names and colors) is"),
        P("AxisXTitle", "str", "", description="The X axis's title"),
        P("AxisYTitle", "str", "", description="The Y axis's title"),
        P("AxisYMin", "number", None, description="The Y axis's lowest value; unset = from the "
                                                  "data"),
        P("AxisYMax", "number", None, description="The Y axis's highest value; unset = from the "
                                                  "data"),
        P("LogScale", "bool", False, description="A logarithmic Y axis (positive values)"),
        P("Animations", "bool", True, description="Series grow into place when shown"),
        *_FONT,
        P("Enabled", "bool", True, description="Whether the control responds to the user"),
        P("Visible", "bool", True, description="Whether the control is shown at run time"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
        P("ZIndex", "int", 0, description="Stacking order among controls in the same "
                                          "container: higher values are drawn on top"),
    )

    def _create_widget(self, parent):
        self.__dict__.update(_rows=[], _columns=[], _table=[], _building=True)
        charts = _charts()
        if charts is None:
            label = QLabel("Chart needs PySide6's QtCharts", parent)
            label.setFrameStyle(QFrame.Box)
            label.setAlignment(Qt.AlignCenter)
            self.__dict__["_chart"] = None
            return label
        chart = charts.QChart()
        view = charts.QChartView(chart, parent)
        view.setRenderHint(QPainter.Antialiasing)
        self.__dict__["_chart"] = chart
        return view

    def _event_targets(self):
        viewport = getattr(self._widget, "viewport", None)
        return [self._widget] + ([viewport()] if viewport is not None else [])

    def _init_values(self, props):
        super()._init_values(props)
        self.__dict__["_building"] = False
        self._rebuild()  # (once, with every property set)

    # -- the data ---------------------------------------------------------------------------------
    def _apply_ChartData(self, lines):
        rows, columns, values = parse_chart_data(lines)
        self._set_table(rows, columns, values)

    @property
    def ChartData(self) -> list[list]:
        """The data as rows: [["", "Sales", ...], ["Q1", 10, ...], ...]; set it
        to such a list, to rows of numbers alone, or to a Recordset."""
        return [["", *self._columns]] + [[label, *row] for label, row in
                                         zip(self._rows, self._table)]

    @ChartData.setter
    def ChartData(self, value):
        if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
            self._set_prop("ChartData", value)  # (the designer's lines)
            return
        rows, columns, table = self._table_of(value)
        self._set_table(rows, columns, table)

    @staticmethod
    def _table_of(value):
        if hasattr(value, "_records") and hasattr(value, "_columns"):  # a Recordset
            fields = list(value._columns)
            rows = [str(r.values[0]) if r.values else "" for r in value._records]
            table = [[_number(v) for v in r.values[1:]] for r in value._records]
            return rows, fields[1:], table
        data = [list(row) if isinstance(row, (list, tuple)) else [row] for row in value or []]
        columns = []
        if data and data[0] and (data[0][0] in ("", None)) and \
                all(isinstance(v, str) for v in data[0][1:]):
            columns = [str(v) for v in data.pop(0)[1:]]
        labelled = data and all(row and isinstance(row[0], str) for row in data)
        rows = [row[0] for row in data] if labelled else []
        table = [[_number(v) for v in (row[1:] if labelled else row)] for row in data]
        return rows, columns, table

    def _set_table(self, rows, columns, table) -> None:
        width = max((len(row) for row in table), default=0)
        table = [row + [0.0] * (width - len(row)) for row in table]
        self.__dict__["_table"] = table
        self.__dict__["_rows"] = [str(r) for r in rows] + \
            [str(i + 1) for i in range(len(rows), len(table))]
        self.__dict__["_columns"] = [str(c) for c in columns][:width] + \
            [f"Series {i + 1}" for i in range(len(columns), width)]
        self._rebuild()

    @property
    def RowCount(self) -> int:
        return len(self._table)

    @property
    def ColumnCount(self) -> int:
        return len(self._columns)

    def _check(self, row, column=1) -> tuple[int, int]:
        row, column = int(row), int(column)
        if not 1 <= row <= self.RowCount or not 1 <= column <= max(self.ColumnCount, 1):
            raise IndexError(f"Chart '{self.Name}': no data at row {row}, column {column} "
                             f"({self.RowCount} rows, {self.ColumnCount} columns)")
        return row - 1, column - 1

    def Data(self, Row: int, Column: int = 1) -> float:
        """The value at Row, Column (from 1)."""
        row, column = self._check(Row, Column)
        return self._table[row][column]

    def SetData(self, Row: int, Column: int, Value) -> None:
        row, column = self._check(Row, Column)
        self._table[row][column] = _number(Value)
        self._rebuild()

    def RowLabel(self, Row: int) -> str:
        return self._rows[self._check(Row)[0]]

    def ColumnLabel(self, Column: int) -> str:
        return self._columns[self._check(1 if self.RowCount else 0, Column)[1]] \
            if self.RowCount else self._columns[int(Column) - 1]

    # -- drawing -----------------------------------------------------------------------------------
    def _apply_any(self, _=None):
        self._rebuild()

    _apply_ChartType = _apply_Title = _apply_Legend = _apply_AxisXTitle = _apply_AxisYTitle = \
        _apply_AxisYMin = _apply_AxisYMax = _apply_LogScale = _apply_any

    def _apply_Animations(self, v):
        if self._chart is not None:
            charts = _charts()
            self._chart.setAnimationOptions(charts.QChart.SeriesAnimations if v and not
                                            self._design_mode else charts.QChart.NoAnimation)

    def _apply_font(self, _=None):
        super()._apply_font()
        if self._chart is not None:
            self._chart.setTitleFont(self._widget.font())
            self._chart.legend().setFont(self._widget.font())

    _apply_FontName = _apply_FontSize = _apply_FontBold = _apply_FontItalic = \
        _apply_FontUnderline = _apply_font

    def _scheme_changed(self, dark: bool) -> None:
        if self._chart is not None:
            charts = _charts()
            self._chart.setTheme(charts.QChart.ChartThemeDark if dark
                                 else charts.QChart.ChartThemeLight)
            self._apply_font()

    def _rebuild(self) -> None:
        chart = self._chart
        if chart is None or self._building:
            return
        charts = _charts()
        values = self._values
        chart.removeAllSeries()
        for axis in chart.axes():
            chart.removeAxis(axis)
        kind = values.get("ChartType", 3)
        chart.setTitle(values.get("Title", ""))
        legend = values.get("Legend", 2)
        chart.legend().setVisible(legend != 0)
        if legend:
            chart.legend().setAlignment({1: Qt.AlignTop, 2: Qt.AlignBottom, 3: Qt.AlignLeft,
                                         4: Qt.AlignRight}[legend])
        if kind == 7:
            self._build_pie(charts)
        elif kind in (3, 4, 5, 6):
            self._build_bars(charts, kind)
        else:
            self._build_lines(charts, kind)
        self._apply_Animations(values.get("Animations", True))
        if "_was_themed" not in self.__dict__:
            self.__dict__["_was_themed"] = True
            self._scheme_changed(self._form._is_dark())

    def _y_axis(self, charts):
        values = self._values
        if values.get("LogScale"):
            axis = charts.QLogValueAxis()
            axis.setBase(10)
        else:
            axis = charts.QValueAxis()
        axis.setTitleText(values.get("AxisYTitle", ""))
        low, high = values.get("AxisYMin"), values.get("AxisYMax")
        numbers = [v for row in self._table for v in row] or [0.0]
        if values.get("ChartType") == 5:  # (a percent bar: 0 to 100)
            numbers = [0.0, 100.0]
        elif values.get("ChartType") == 4:  # (stacked: the sums)
            numbers = [sum(v for v in row if v > 0) for row in self._table] + \
                [sum(v for v in row if v < 0) for row in self._table] or [0.0]
        if low is None:
            low = min(min(numbers), 0.0) if not values.get("LogScale") else \
                max(min(v for v in numbers if v > 0) if any(v > 0 for v in numbers) else 1,
                    1e-9) / 2
        if high is None:
            high = max(numbers) * 1.1 if max(numbers) > 0 else 1.0
        if high <= low:
            high = low + 1
        axis.setRange(float(low), float(high))
        return axis

    def _x_axis(self, charts):
        axis = charts.QBarCategoryAxis()
        axis.append(self._rows or [""])
        axis.setTitleText(self._values.get("AxisXTitle", ""))
        return axis

    def _build_bars(self, charts, kind: int) -> None:
        chart = self._chart
        series = {3: charts.QBarSeries, 4: charts.QStackedBarSeries,
                  5: charts.QPercentBarSeries, 6: charts.QHorizontalBarSeries}[kind]()
        for column, name in enumerate(self._columns):
            bar_set = charts.QBarSet(name)
            bar_set.append([row[column] for row in self._table])
            bar_set.clicked.connect(lambda index, c=column: self._selected(c, index))
            series.append(bar_set)
        chart.addSeries(series)
        x_axis, y_axis = self._x_axis(charts), self._y_axis(charts)
        if kind == 6:  # (horizontal: the categories up the side)
            chart.addAxis(x_axis, Qt.AlignLeft)
            chart.addAxis(y_axis, Qt.AlignBottom)
        else:
            chart.addAxis(x_axis, Qt.AlignBottom)
            chart.addAxis(y_axis, Qt.AlignLeft)
        series.attachAxis(x_axis)
        series.attachAxis(y_axis)

    def _build_lines(self, charts, kind: int) -> None:
        chart = self._chart
        x_axis, y_axis = self._x_axis(charts), self._y_axis(charts)
        chart.addAxis(x_axis, Qt.AlignBottom)
        chart.addAxis(y_axis, Qt.AlignLeft)
        for column, name in enumerate(self._columns):
            points = [QPointF(row, values[column]) for row, values in enumerate(self._table)]
            if kind == 2:  # an area under the line
                upper = charts.QLineSeries()
                upper.append(points)
                series = charts.QAreaSeries(upper)
                series.setOpacity(0.7)
                series.__dict__["_upper"] = upper  # (kept alive with it)
            else:
                series = {0: charts.QLineSeries, 1: charts.QSplineSeries,
                          8: charts.QScatterSeries}.get(kind, charts.QLineSeries)()
                series.append(points)
                if kind != 8:
                    series.setPointsVisible(True)
            series.setName(name)
            series.clicked.connect(lambda point, c=column: self._selected(
                c, max(0, min(round(point.x()), len(self._table) - 1))))
            chart.addSeries(series)
            series.attachAxis(x_axis)
            series.attachAxis(y_axis)

    def _build_pie(self, charts) -> None:
        series = charts.QPieSeries()
        for row, (label, values) in enumerate(zip(self._rows, self._table)):
            value = values[0] if values else 0.0
            pie_slice = series.append(label, max(value, 0.0))
            pie_slice.clicked.connect(lambda r=row, s=pie_slice: self._slice_clicked(r, s))
        series.setLabelsVisible(True)
        self._chart.addSeries(series)

    def _slice_clicked(self, row: int, pie_slice) -> None:
        if not self._design_mode:
            for other in pie_slice.series().slices():
                other.setExploded(other is pie_slice and not other.isExploded())
        self._selected(0, row)

    def _selected(self, column: int, row: int) -> None:
        self._fire("PointSelected", column + 1, row + 1)

    # -- pictures ------------------------------------------------------------------------------
    @property
    def Picture(self):
        """The chart as a Picture (read-only)."""
        from .picture import Picture

        image = self._widget.grab().toImage()
        return Picture(_image=image)

    def EditCopy(self) -> None:
        """Copy the chart to the clipboard, as a picture."""
        QApplication.clipboard().setImage(self._widget.grab().toImage())

    @property
    def SeriesColor(self):
        """Not settable: the theme picks the series' colors (read their QColor
        names with ``SeriesColors``)."""
        return None

    @property
    def SeriesColors(self) -> list[str]:
        """The series' colors, as #rrggbb (the theme's)."""
        chart = self._chart
        if chart is None or not chart.series():
            return []
        series = chart.series()[0]
        sets = getattr(series, "barSets", None)
        if sets is not None:
            return [bar_set.color().name() for bar_set in sets()]
        slices = getattr(series, "slices", None)
        if slices is not None:
            return [pie_slice.color().name() for pie_slice in slices()]
        return [QColor(s.color()).name() for s in chart.series()]


_add_validation(Chart)
_add_mouse_members(Chart)
CONTROL_TYPES["Chart"] = Chart  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
