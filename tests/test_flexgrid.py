"""The FlexGrid: cells and fixed headings, FormatString, the current cell and the
selection, cell formats, rows (AddItem, RemoveItem, RowData, Sort), scrolling, the
mouse, and editing with per-column and per-cell editors and their events."""

import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QLineEdit

from vp6 import (FlexGrid, Form, vpCenter, vpGridEditButton, vpGridEditCheck,
                 vpGridEditColor, vpGridEditList, vpGridEditNone, vpGridEditText,
                 vpGridSelectionByRow, vpGridSortGenericAscending, vpGridSortGenericDescending,
                 vpGridSortNumericAscending, vpGridSortNumericDescending,
                 vpGridSortStringAscending, vpGridSortStringDescending,
                 vpGridSortStringNoCaseAscending, vpGridSortStringNoCaseDescending,
                 vpLeftJustify, vpRightJustify, vpYellow)
from vp6.controls import CONTROL_TYPES, EVENT_ARGS, parse_format_string
from vp6.ide.icons import icon
from vp6.ide.panels import Toolbox

os.environ.setdefault("VP6_NO_ERROR_DIALOG", "1")


class Sheet(Form):
    def InitializeComponent(self):
        self.events = []
        self.grd = FlexGrid(self, Rows=4, Cols=3, FormatString="|<Name|>Size",
                            Width=360, Height=160)

    def grd_RowColChange(self):
        self.events.append(("RowColChange", self.grd.Row, self.grd.Col))

    def grd_EnterCell(self):
        self.events.append("EnterCell")

    def grd_LeaveCell(self):
        self.events.append("LeaveCell")

    def grd_SelChange(self):
        self.events.append("SelChange")

    def grd_Scroll(self):
        self.events.append("Scroll")

    def grd_BeforeEdit(self, Row, Col):
        self.events.append(("BeforeEdit", Row, Col))
        return self.grd.TextMatrix(Row, 1) == "locked"  # cancel for that row

    def grd_ValidateEdit(self, Row, Col, Text):
        self.events.append(("ValidateEdit", Row, Col, Text))
        return Text == "bad"  # cancel: refused

    def grd_AfterEdit(self, Row, Col):
        self.events.append(("AfterEdit", Row, Col))

    def grd_CellButtonClick(self, Row, Col):
        self.events.append(("CellButtonClick", Row, Col))


@pytest.fixture
def form(qapp):
    form = Sheet()
    form.Show()
    QTest.qWait(10)
    yield form
    form.Unload()


def fill(grid):
    for row, (name, size) in enumerate((("pear", "10"), ("Apple", "9"), ("fig", "100")),
                                       start=1):
        grid.TextMatrix[row, 0] = str(row)
        grid.TextMatrix[row, 1] = name
        grid.TextMatrix[row, 2] = size


def cell_center(grid, row, col):
    table = grid._widget
    return table.visualRect(table.model().index(row - grid._frows, col - grid._fcols)).center()


def test_format_string():
    assert parse_format_string("|<Name|^Qty|>Price") == [("", 0), ("Name", 0), ("Qty", 2),
                                                          ("Price", 1)]
    assert parse_format_string("") == []


def test_cells_and_headings(form):
    grid = form.grd
    assert (grid.Rows, grid.Cols) == (4, 3)
    assert [grid.TextMatrix(0, c) for c in range(3)] == ["", "Name", "Size"]
    assert grid.ColAlignment(1) == vpLeftJustify and grid.ColAlignment(2) == vpRightJustify
    fill(grid)
    assert grid.TextMatrix[2, 1] == "Apple" and grid.TextMatrix(3, 0) == "3"  # (a heading)
    assert grid._widget.verticalHeaderItem(2).text() == "3"
    assert grid._widget.horizontalHeaderItem(1).text() == "Size"
    grid.TextMatrix[0, 0] = "#"  # the corner
    assert grid.TextMatrix(0, 0) == "#"
    with pytest.raises(IndexError, match="Rows is 4, Cols is 3"):
        grid.TextMatrix(4, 0)
    with pytest.raises(IndexError):
        grid.TextMatrix[0, 3] = "x"
    assert grid._widget.item(0, 1).textAlignment() & Qt.AlignRight  # its column's
    grid.ColAlignment[2] = vpCenter
    assert grid._widget.item(0, 1).textAlignment() & Qt.AlignHCenter
    grid.Clear()
    assert all(grid.TextMatrix(r, c) == "" for r in range(4) for c in range(3))
    assert (grid.Rows, grid.Cols) == (4, 3)


def test_rows_cols_and_fixed(form):
    grid = form.grd
    fill(grid)
    grid.Rows = 6
    grid.Cols = 4
    assert grid._widget.rowCount() == 5 and grid._widget.columnCount() == 3
    assert grid._widget.verticalHeaderItem(4).text() == ""  # (not Qt's numbers)
    grid.Rows = 4
    grid.FixedRows = 0  # the headings become row 0
    assert grid.Rows == 4 and grid.TextMatrix(0, 1) == "Name"
    assert not grid._widget.horizontalHeader().isVisible()
    assert grid._widget.item(0, 0).text() == "Name"
    grid.FixedRows = 1
    assert grid.TextMatrix(0, 1) == "Name" and grid.TextMatrix(1, 1) == "pear"
    grid.FixedCols = 0  # the row headings become column 0
    assert grid.Cols == 4 and grid.TextMatrix(1, 0) == "1" and grid.TextMatrix(0, 1) == "Name"
    grid.FixedCols = 1
    assert grid.TextMatrix(1, 0) == "1" and grid.TextMatrix(1, 1) == "pear"


def test_current_cell_and_selection(form):
    grid = form.grd
    fill(grid)
    assert (grid.Row, grid.Col) == (1, 1)  # the first cell under the headings
    form.events.clear()
    grid.Row = 2
    moves = [e for e in form.events if e != "SelChange"]
    assert moves[:3] == ["LeaveCell", ("RowColChange", 2, 1), "EnterCell"]
    assert grid.Text == "Apple"
    grid.Text = "Quince"
    assert grid.TextMatrix(2, 1) == "Quince"
    grid.Col = 2
    assert grid.Text == "9"
    with pytest.raises(IndexError, match="fixed"):
        grid.Row = 0
    grid.Row, grid.Col = 1, 1
    grid.RowSel, grid.ColSel = 3, 2
    assert (grid.Row, grid.Col, grid.RowSel, grid.ColSel) == (1, 1, 3, 2)
    assert "SelChange" in form.events
    assert len(grid._widget.selectedItems()) == 6
    grid.SelectionMode = vpGridSelectionByRow
    grid.Row = 3
    assert len(grid._widget.selectedItems()) == 2  # the whole row


def test_cell_formats(form):
    grid = form.grd
    fill(grid)
    grid.Row, grid.Col = 2, 1
    assert grid.CellBackColor is None and grid.CellForeColor is None and not grid.CellFontBold
    grid.CellBackColor = vpYellow
    grid.CellForeColor = 0x0000FF
    grid.CellFontBold = grid.CellFontItalic = True
    grid.CellAlignment = vpRightJustify
    assert (grid.CellBackColor, grid.CellForeColor, grid.CellFontBold, grid.CellFontItalic,
            grid.CellAlignment) == (vpYellow, 0x0000FF, True, True, vpRightJustify)
    grid.Row = 1
    assert grid.CellBackColor is None  # (that cell only)
    grid.Row = 2
    grid.CellBackColor = None
    assert grid.CellBackColor is None


def test_rows_and_sorting(form):
    grid = form.grd
    fill(grid)
    for row in (1, 2, 3):
        grid.RowData[row] = row * 10
    grid.AddItem("4\tbanana\t25")
    grid.AddItem("0\tcherry\t7", 1)
    assert grid.Rows == 6 and [grid.TextMatrix(r, 1) for r in range(1, 6)] == [
        "cherry", "pear", "Apple", "fig", "banana"]
    grid.RemoveItem(1)
    assert grid.Rows == 5 and grid.TextMatrix(1, 1) == "pear"
    with pytest.raises(IndexError):
        grid.RemoveItem(0)
    with pytest.raises(IndexError):
        grid.RowData(0)

    def column(col):
        return [grid.TextMatrix(r, col) for r in range(1, grid.Rows)]

    grid.Col = 2
    grid.Sort = vpGridSortNumericAscending
    assert column(2) == ["9", "10", "25", "100"]
    assert column(0) == ["2", "1", "4", "3"]  # the rows' headings move with them
    assert [grid.RowData(r) for r in (1, 2, 4)] == [20, 10, 30]  # and their RowData
    grid.Sort = vpGridSortNumericDescending
    assert column(2) == ["100", "25", "10", "9"]
    grid.Sort = vpGridSortStringAscending  # as text: "10" < "100" < "25" < "9"
    assert column(2) == ["10", "100", "25", "9"]
    grid.Sort = vpGridSortStringDescending
    assert column(2) == ["9", "25", "100", "10"]
    grid.Col = 1
    grid.Sort = vpGridSortGenericAscending
    assert column(1) == ["Apple", "banana", "fig", "pear"]
    grid.Sort = vpGridSortGenericDescending
    assert column(1) == ["pear", "fig", "banana", "Apple"]
    grid.Sort = vpGridSortStringNoCaseAscending
    assert column(1) == ["Apple", "banana", "fig", "pear"]
    grid.Sort = vpGridSortStringNoCaseDescending
    assert column(1)[0] == "pear"
    grid.Sort = vpGridSortStringAscending  # with case: capitals first
    assert column(1) == ["Apple", "banana", "fig", "pear"]
    with pytest.raises(ValueError):
        grid.Sort = 99
    with pytest.raises(AttributeError, match="set, not read"):
        grid.Sort


def test_sizes_scrolling_and_the_mouse(form):
    grid = form.grd
    grid.ColWidth[1] = 120
    grid.ColWidth[0] = 40
    grid.RowHeight[1] = 40
    assert grid.ColWidth(1) == 120 and grid.ColWidth(0) == 40 and grid.RowHeight(1) == 40
    with pytest.raises(IndexError):
        grid.ColWidth[3] = 10
    grid.Rows = 40
    form.events.clear()
    grid.TopRow = 10
    assert grid.TopRow == 10 and "Scroll" in form.events
    grid.TopRow = 1
    grid.Cols = 12
    grid.LeftCol = 3
    assert grid.LeftCol == 3
    grid.LeftCol = 1
    fill(grid)
    QTest.mouseMove(grid._widget.viewport(), cell_center(grid, 2, 1))
    assert (grid.MouseRow, grid.MouseCol) == (2, 1)
    header = grid._widget.horizontalHeader()
    QTest.mouseMove(header, QPoint(header.sectionViewportPosition(1) + 5, 5))
    assert (grid.MouseRow, grid.MouseCol) == (0, 2)


def test_not_editable_by_default(form):
    grid = form.grd
    fill(grid)
    grid.Row, grid.Col = 1, 1
    grid.EditCell()
    assert grid._widget.state() != grid._widget.State.EditingState and not form.events[-1:] == [
        ("BeforeEdit", 1, 1)]


def test_text_editing(form):
    grid = form.grd
    fill(grid)
    grid.Editable = True
    grid.Row, grid.Col = 1, 1
    grid.EditCell()
    editor = grid._widget.findChild(QLineEdit)
    assert editor is not None and editor.text() == "pear"
    assert ("BeforeEdit", 1, 1) in form.events
    editor.setText("plum")
    QTest.keyClick(editor, Qt.Key_Return)
    QTest.qWait(10)  # (Qt commits it a moment later)
    assert grid.TextMatrix(1, 1) == "plum"
    assert form.events[-2:] == [("ValidateEdit", 1, 1, "plum"), ("AfterEdit", 1, 1)]
    grid.EditCell()  # ValidateEdit refusing it
    editor = grid._widget.findChild(QLineEdit)
    editor.setText("bad")
    QTest.keyClick(editor, Qt.Key_Return)
    QTest.qWait(10)
    assert grid.TextMatrix(1, 1) == "plum" and form.events[-1] == ("ValidateEdit", 1, 1, "bad")
    grid.TextMatrix[2, 1] = "locked"  # BeforeEdit cancelling
    grid.Row = 2
    form.events.clear()
    grid.EditCell()
    assert form.events == [("BeforeEdit", 2, 1)] and grid._widget.findChild(QLineEdit) is None \
        or not grid._widget.findChild(QLineEdit).isVisible()
    grid.Row = 3  # typing starts editing
    grid._widget.setFocus()
    QTest.keyClicks(grid._widget, "k")
    editor = grid._widget.findChild(QLineEdit)
    assert editor is not None and editor.isVisible() and editor.text() == "k"


def test_editors_per_column_and_cell(form):
    grid = form.grd
    fill(grid)
    grid.Editable = True
    assert grid.ColEditor(1) == vpGridEditText
    grid.ColEditor[2] = vpGridEditNone  # read-only column
    grid.Row, grid.Col = 1, 2
    form.events.clear()
    grid.EditCell()
    assert not form.events  # (not even BeforeEdit)
    grid.ColEditor[2] = vpGridEditList
    grid.ColList[2] = [9, 10, 100]
    assert grid.ColList(2) == ["9", "10", "100"] and grid.CellList == ["9", "10", "100"]
    grid.Row = 2
    grid.CellList = ["1", "2", "9"]  # this cell's own choices
    grid.EditCell()
    combo = grid._widget.findChild(QComboBox)
    assert [combo.itemText(i) for i in range(combo.count())] == ["1", "2", "9"]
    assert combo.currentText() == "9"
    combo.setCurrentIndex(0)  # choosing one commits it
    combo.activated.emit(0)
    QTest.qWait(10)
    assert grid.TextMatrix(2, 2) == "1" and ("AfterEdit", 2, 2) in form.events
    grid.Row, grid.Col = 3, 1
    grid.CellEditor = vpGridEditNone  # a cell of its own, read-only
    assert grid.CellEditor == vpGridEditNone and grid.ColEditor(1) == vpGridEditText
    grid.Row = 1
    assert grid.CellEditor == vpGridEditText


def test_check_boxes(form):
    grid = form.grd
    fill(grid)
    grid.TextMatrix[1, 2] = "True"
    grid.ColEditor[2] = vpGridEditCheck
    assert [grid.TextMatrix(r, 2) for r in (1, 2, 3)] == ["True", "False", "False"]
    assert grid._widget.item(0, 1).checkState() == Qt.Checked
    assert grid._widget.item(0, 1).text() == ""
    grid.TextMatrix[2, 2] = "yes"
    assert grid.TextMatrix(2, 2) == "True"
    grid.AddItem("4\tnew\tTrue")  # a new row in a check column
    assert grid.TextMatrix(4, 2) == "True"
    grid.Rows = 6
    assert grid._widget.item(4, 1).data(Qt.CheckStateRole) is not None  # its box too
    viewport = grid._widget.viewport()
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, cell_center(grid, 3, 2))
    assert grid.TextMatrix(3, 2) == "False"  # not Editable: no change
    grid.Editable = True
    form.events.clear()
    QTest.mouseClick(viewport, Qt.LeftButton, Qt.NoModifier, cell_center(grid, 3, 2))
    assert grid.TextMatrix(3, 2) == "True"
    assert form.events[-3:] == [("BeforeEdit", 3, 2), ("ValidateEdit", 3, 2, "True"),
                                ("AfterEdit", 3, 2)]
    grid.Row, grid.Col = 3, 2
    grid.EditCell()  # (as Space)
    assert grid.TextMatrix(3, 2) == "False"
    grid.ColEditor[2] = vpGridEditText  # back to text, keeping the values
    assert grid.TextMatrix(1, 2) == "True" and grid._widget.item(0, 1).text() == "True"


def test_color_and_button_cells(form, monkeypatch):
    grid = form.grd
    fill(grid)
    grid.Editable = True
    grid.Row, grid.Col = 1, 2
    grid.CellEditor = vpGridEditColor
    grid.Text = "#ff0000"
    monkeypatch.setattr("vp6.controls.QColorDialog.getColor",
                        lambda initial, parent, title: QColor("#00ff00")
                        if initial == QColor("#ff0000") else QColor())
    grid.EditCell()
    QTest.qWait(20)
    assert grid.Text == "#00ff00" and ("AfterEdit", 1, 2) in form.events
    grid.Row = 2
    grid.CellEditor = vpGridEditButton
    form.events.clear()
    grid.EditCell()  # F2 / Enter on it: as its button
    assert form.events == [("BeforeEdit", 2, 2), ("CellButtonClick", 2, 2)]
    rect = grid._widget.visualRect(grid._widget.model().index(1, 1))
    QTest.mouseClick(grid._widget.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(rect.right() - 6, rect.center().y()))
    assert form.events[-1] == ("CellButtonClick", 2, 2)
    grid._widget.grab()  # (paints the swatch and the button)


def test_toolbox_icon_and_events(qapp):
    assert "FlexGrid" in Toolbox().buttons and "FlexGrid" in CONTROL_TYPES
    assert not icon("FlexGrid").isNull()
    assert EVENT_ARGS["ValidateEdit"] == "Row, Col, Text"
    assert EVENT_ARGS["BeforeEdit"] == EVENT_ARGS["AfterEdit"] == "Row, Col"
