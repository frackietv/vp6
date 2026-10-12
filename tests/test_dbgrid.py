"""DBGrid: a grid bound to a Data control."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

import vp6
from vp6 import Data, DBGrid, Form, TextBox
from vp6.dbgrid import parse_db_column


@pytest.fixture
def form(qapp, tmp_path):
    db = vp6.CreateDatabase(str(tmp_path / "pets.db"))
    db.Execute("CREATE TABLE pets (Name TEXT, Age INTEGER, Weight REAL)")
    for i in range(300):
        db.Execute("INSERT INTO pets VALUES (?, ?, ?)", f"Pet {i:03d}", i % 15, i * 0.5)
    db.Close()

    class Grid(Form):
        def InitializeComponent(self):
            self.events = []
            self.refuse = False
            self.dtaPets = Data(self, DatabaseName=str(tmp_path / "pets.db"),
                                RecordSource="pets")
            self.grdPets = DBGrid(self, DataSource="dtaPets", Width=400, Height=300,
                                  AllowAddNew=True, AllowDelete=True,
                                  Columns=["Name|Name|120", "Age|Age|50|03d",
                                           "Weight (kg)|Weight|80|.1f", "Secret|Name||hidden"])
            self.txtName = TextBox(self, DataSource="dtaPets", DataField="Name")

        def grdPets_RowColChange(self):
            self.events.append(("RowCol", self.grdPets.Row, self.grdPets.Col))

        def grdPets_BeforeUpdate(self):
            self.events.append("Before")
            return self.refuse

        def grdPets_AfterUpdate(self):
            self.events.append("After")

        def grdPets_BeforeDelete(self):
            self.events.append("BeforeDelete")

    f = Grid()
    f.Show()
    QTest.qWait(10)
    yield f
    f.Unload()


def test_parse_db_column():
    assert parse_db_column("Weight (kg)|Weight|80|.1f") == {
        "Caption": "Weight (kg)", "DataField": "Weight", "Width": 80, "NumberFormat": ".1f",
        "Visible": True}
    assert parse_db_column("Name")["DataField"] == "Name"
    assert not parse_db_column("x|y|||hidden")["Visible"]


def test_records_and_columns(form):
    grid, model = form.grdPets, form.grdPets._model
    assert model.rowCount() == 301 and model.columnCount() == 4  # (and the new row)
    assert model.headerData(300, Qt.Vertical) == "*"
    assert [c.Caption for c in grid.Columns] == ["Name", "Age", "Weight (kg)", "Secret"]
    assert grid.Columns("Weight").Caption == "Weight (kg)" and grid.Columns.Count == 4
    assert model.data(model.index(3, 1)) == "003" and model.data(model.index(3, 2)) == "1.5"
    assert grid._widget.isColumnHidden(3) and grid.Columns(0).Width == 120
    grid.Columns(1).NumberFormat = ""
    assert model.data(model.index(3, 1)) == "3"
    grid.Columns(3).Visible = True
    assert not grid._widget.isColumnHidden(3)


def test_rows_follow_the_data_control(form):
    grid = form.grdPets
    grid.Row = 7
    assert form.dtaPets.Recordset.AbsolutePosition == 7 and form.txtName.Text == "Pet 007"
    assert ("RowCol", 7, 0) in form.events and grid.Text == "Pet 007"
    form.dtaPets.Recordset.MoveLast()
    assert grid.Row == 299 and grid.Bookmark is form.dtaPets.Recordset.Bookmark
    grid.Bookmark = form.dtaPets.Recordset._records[10]
    assert grid.Row == 10


def test_editing(form):
    grid, model = form.grdPets, form.grdPets._model
    form.events.clear()
    assert model.setData(model.index(5, 1), "42")
    rs = form.dtaPets.Recordset
    assert rs.AbsolutePosition == 5 and rs("Age") == 42 and form.events[-2:] == ["Before",
                                                                                 "After"]
    form.refuse = True
    assert not model.setData(model.index(5, 1), "43")
    assert rs("Age") == 42
    form.refuse = False
    assert model.setData(model.index(300, 0), "Newbie")  # the last row: a new record
    assert rs.RecordCount == 301 and rs("Name") == "Newbie" and model.rowCount() == 302
    grid.AllowUpdate = False
    assert not model.flags(model.index(1, 1)) & Qt.ItemIsEditable


def test_deleting(form):
    grid = form.grdPets
    grid.Row = 0
    grid._widget.selectRow(1)
    QTest.keyClick(grid._widget, Qt.Key_Delete)
    rs = form.dtaPets.Recordset
    assert "BeforeDelete" in form.events and rs.RecordCount == 299
    assert all(r.values[0] != "Pet 001" for r in rs._records)


def test_properties_window_shows_its_lines(form):
    from vp6.ide.properties import PropertiesWindow

    window = PropertiesWindow()
    assert window._value([form.grdPets], DBGrid._specs["Columns"])[0] == "Name|Name|120"
