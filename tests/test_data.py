"""Data-bound controls: Database (CreateDatabase, OpenDatabase, Execute), the
Recordset (moving, Fields, AddNew, Edit, Update, Delete, Find, Bookmark,
Requery, read-only queries), the Data control (bound controls of each kind,
DataChanged, saving on moving, Validate, Reposition, EOFAction, BOFAction,
Error, ReadOnly, UpdateRecord, UpdateControls, a bound FlexGrid) and the IDE
(the Toolbox, the designer, the Properties window's lists)."""

import sqlite3

import pytest

import vp6
from vp6 import (CheckBox, ComboBox, CreateDatabase, Data, Database, Field, FlexGrid, Form,
                 Image, Label, ListBox, OpenDatabase, Picture, PictureBox, Recordset, TextBox,
                 formfile, vpBlue, vpDataActionCancel, vpDataActionMoveNext,
                 vpDataActionUnload, vpEditAdd, vpEditInProgress, vpEditNone,
                 vpEOFActionAddNew, vpEOFActionEOF, vpBOFActionBOF)
from vp6.controls import CONTROL_TYPES
from vp6.data import field_names

PETS = [("Bella", "Cat", 3, 1), ("Max", "Dog", 5, 1), ("Coco", "Parrot", None, 0)]


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "pets.db"
    db = CreateDatabase(str(path))
    db.Execute("CREATE TABLE pets (Id INTEGER PRIMARY KEY, Name TEXT NOT NULL, Kind TEXT, "
               "Age INTEGER, Vaccinated INTEGER, Photo BLOB)")
    for pet in PETS:
        db.Execute("INSERT INTO pets (Name, Kind, Age, Vaccinated) VALUES (?, ?, ?, ?)", *pet)
    db.Close()
    return str(path)


def rows(path, sql="SELECT Name, Kind, Age, Vaccinated FROM pets ORDER BY Id"):
    with sqlite3.connect(path) as conn:
        return conn.execute(sql).fetchall()


class PetForm(Form):
    database = ""
    source = "pets"

    def InitializeComponent(self):
        self.log = []
        self.cancel = False
        self.dta = Data(self, DatabaseName=self.database, RecordSource=self.source)
        self.lblId = Label(self, DataSource="dta", DataField="Id")
        self.txtName = TextBox(self, DataSource="dta", DataField="Name")
        self.cboKind = ComboBox(self, List=["Cat", "Dog", "Parrot"], DataSource="dta",
                                DataField="kind")  # (any case)
        self.txtAge = TextBox(self, DataSource="dta", DataField="Age")
        self.chkVaccinated = CheckBox(self, DataSource="dta", DataField="Vaccinated")
        self.grd = FlexGrid(self, DataSource="dta", FixedCols=0)

    def Form_Load(self):
        self.log.append("Load")

    def dta_Validate(self, Action, Save):
        self.log.append(("Validate", Action, Save))
        return vpDataActionCancel if self.cancel else None

    def dta_Reposition(self):
        self.log.append(("Reposition", self.dta.Recordset.AbsolutePosition))


@pytest.fixture
def pets(qapp, db_path):
    PetForm.database = db_path
    form = PetForm()
    form.Show()
    yield form
    form.Unload()


# --- Database and Recordset ------------------------------------------------------------------

def test_database_execute_and_recordset(qapp, db_path, tmp_path):
    with pytest.raises(FileExistsError):
        CreateDatabase(db_path)
    with pytest.raises(FileNotFoundError):
        OpenDatabase(str(tmp_path / "none.db"))
    assert not (tmp_path / "none.db").exists()
    db = OpenDatabase(db_path)
    assert isinstance(db, Database) and db.Name == db_path
    assert db.Execute("UPDATE pets SET Age = Age + 1 WHERE Age IS NOT NULL") == 2
    assert db.Execute("CREATE TABLE a (x); CREATE TABLE b (y); INSERT INTO a VALUES (1)") == 1
    rs = db.OpenRecordset("pets")
    assert isinstance(rs, Recordset) and rs.Updatable and rs.RecordCount == 3
    assert [f.Name for f in rs.Fields] == ["Id", "Name", "Kind", "Age", "Vaccinated", "Photo"]
    assert isinstance(rs.Fields("Name"), Field) and rs.Fields.Count == 6
    assert rs("Name") == "Bella" and rs["AGE"] == 4 and rs.Fields(1).Value == "Bella"
    assert not rs.BOF and not rs.EOF and rs.AbsolutePosition == 0
    rs.MoveNext()
    rs.MoveNext()
    assert rs("Name") == "Coco" and rs("Age") is None
    rs.MoveNext()
    assert rs.EOF and rs.AbsolutePosition == -1
    with pytest.raises(RuntimeError, match="No current record"):
        rs.MoveNext()
    with pytest.raises(RuntimeError, match="No current record"):
        rs("Name")
    rs.MoveFirst()
    rs.MovePrevious()
    assert rs.BOF
    with pytest.raises(RuntimeError):
        rs.MovePrevious()
    with pytest.raises(KeyError, match="Weight"):
        rs.Fields("Weight")
    db.Close()
    with pytest.raises(RuntimeError, match="closed"):
        rs.MoveFirst()


def test_recordset_changes(qapp, db_path):
    db = OpenDatabase(db_path)
    rs = db.OpenRecordset("SELECT Name, Age FROM pets WHERE Age > 2 ORDER BY Name DESC")
    assert rs.Updatable and [rs("Name")] == ["Max"]
    rs["Age"] = 6  # (starts editing)
    assert rs.EditMode == vpEditInProgress and rs("Age") == 6
    assert rs.Fields("Age").OriginalValue == 5
    rs.Update()
    assert rs.EditMode == vpEditNone and rs("Age") == 6
    rs.Edit()
    rs["Name"] = "Maxi"
    rs.CancelUpdate()
    assert rs("Name") == "Max"
    with pytest.raises(RuntimeError, match="without AddNew or Edit"):
        rs.Update()
    rs.AddNew()
    assert rs.EditMode == vpEditAdd and rs("Name") is None
    rs["Name"], rs["Age"] = "Zed", "7"  # (INTEGER affinity: 7)
    rs.Update()
    assert rs.RecordCount == 3 and rs.AbsolutePosition == 2 and rs("Age") == 7
    rs.AddNew()
    rs["Name"] = None
    with pytest.raises(sqlite3.IntegrityError):
        rs.Update()
    rs.CancelUpdate()
    rs.MoveFirst()
    mark = rs.Bookmark
    rs.Delete()
    with pytest.raises(RuntimeError):
        rs("Name")
    rs.MoveNext()  # the record after the deleted one
    assert rs("Name") == "Bella" and rs.RecordCount == 2
    with pytest.raises(ValueError):
        rs.Bookmark = mark
    assert rows(db_path) == [("Bella", "Cat", 3, 1), ("Coco", "Parrot", None, 0),
                             ("Zed", None, 7, None)]
    db.Close()


def test_find_bookmark_move_and_requery(qapp, db_path):
    db = OpenDatabase(db_path)
    rs = db.OpenRecordset("pets")
    rs.FindFirst("Kind LIKE 'd%' OR Age IS NULL")
    assert not rs.NoMatch and rs("Name") == "Max"
    rs.FindNext("Kind LIKE 'd%' OR Age IS NULL")
    assert rs("Name") == "Coco"
    mark = rs.Bookmark
    rs.FindPrevious("Vaccinated = 1")
    assert rs("Name") == "Max"
    rs.FindLast("Age < 4")
    assert rs("Name") == "Bella"
    rs.FindFirst("Name = 'Nobody'")
    assert rs.NoMatch and rs("Name") == "Bella"  # (it stays)
    rs.Bookmark = mark
    assert rs("Name") == "Coco"
    rs.Move(-2)
    assert rs("Name") == "Bella"
    rs.Move(1, mark)
    assert rs.EOF
    rs.AbsolutePosition = 1
    assert rs("Name") == "Max"
    with pytest.raises(IndexError):
        rs.AbsolutePosition = 3
    db.Execute("INSERT INTO pets (Name) VALUES ('New')")
    rs.Requery()
    assert rs.RecordCount == 4 and rs.AbsolutePosition == 0
    db.Close()


def test_read_only_recordsets(qapp, db_path):
    db = OpenDatabase(db_path)
    db.Execute("CREATE VIEW cats AS SELECT * FROM pets WHERE Kind = 'Cat'")
    for source in ("SELECT Kind, COUNT(*) AS n FROM pets GROUP BY Kind",
                   "SELECT a.Name FROM pets a JOIN pets b ON a.Id = b.Id", "cats"):
        rs = db.OpenRecordset(source)
        assert not rs.Updatable and rs.RecordCount > 0, source
        with pytest.raises(PermissionError):
            rs.Edit()
    rs = db.OpenRecordset("pets", ReadOnly=True)
    assert not rs.Updatable
    with pytest.raises(PermissionError):
        rs["Name"] = "x"
    db.Close()
    db = OpenDatabase(db_path, ReadOnly=True)
    assert db.ReadOnly and not db.OpenRecordset("pets").Updatable
    with pytest.raises(sqlite3.OperationalError):
        db.Execute("DELETE FROM pets")
    db.Close()


def test_pictures_are_kept_as_png(qapp, db_path):
    db = OpenDatabase(db_path)
    db.Execute("UPDATE pets SET Photo = ? WHERE Name = 'Bella'", Picture(10, 8, vpBlue))
    rs = db.OpenRecordset("pets")
    assert rs("Photo")[:8] == b"\x89PNG\r\n\x1a\n"
    rs.MoveNext()
    rs["Photo"] = Picture(4, 4, vpBlue)
    rs.Update()
    assert rs("Photo")[:4] == b"\x89PNG"
    db.Close()


# --- the Data control ----------------------------------------------------------------------------

def test_bound_controls_show_the_record(pets):
    form = pets
    assert form.log[:2] == ["Load", ("Reposition", 0)]  # (opened after Form_Load)
    assert (form.lblId.Caption, form.txtName.Text, form.cboKind.Text, form.txtAge.Text,
            form.chkVaccinated.Value) == ("1", "Bella", "Cat", "3", 1)
    form.dta.Recordset.MoveLast()
    assert (form.txtName.Text, form.txtAge.Text, form.chkVaccinated.Value) == \
        ("Coco", "", 0)
    assert not form.txtName.DataChanged
    assert form.grd.Rows == 4 and form.grd.Cols == 6
    assert form.grd.TextMatrix(0, 1) == "Name" and form.grd.TextMatrix(3, 1) == "Coco"
    assert form.grd.Row == 3  # the current record


def test_changes_are_saved_when_moving(pets, db_path):
    form = pets
    rs = form.dta.Recordset
    form.txtName.Text = "Bellissima"
    form.chkVaccinated.Value = 0
    assert form.txtName.DataChanged and not form.txtAge.DataChanged
    form.log.clear()
    rs.MoveNext()
    assert form.log == [("Validate", vpDataActionMoveNext, True), ("Reposition", 1)]
    assert rows(db_path)[0] == ("Bellissima", "Cat", 3, 0)
    assert form.grd.TextMatrix(1, 1) == "Bellissima"
    form.txtAge.Text = ""  # an emptied number: NULL
    form.txtName.Text = "Maxi"
    form.txtName.DataChanged = False  # not saved
    rs.MoveFirst()
    assert rows(db_path)[1] == ("Max", "Dog", None, 1)


def test_validate_can_cancel(pets, db_path):
    form = pets
    form.txtName.Text = "Nope"
    form.cancel = True
    form.dta.Recordset.MoveNext()
    assert form.dta.Recordset.AbsolutePosition == 0 and form.txtName.Text == "Nope"
    form.dta.UpdateControls()  # dropped
    assert form.txtName.Text == "Bella" and not form.txtName.DataChanged
    form.cancel = False
    form.txtName.Text = "Now"
    form.dta.UpdateRecord()  # saved, no Validate
    assert rows(db_path)[0][0] == "Now"


def test_arrows_and_eof_bof_actions(pets, db_path):
    form = pets
    data, rs = form.dta, form.dta.Recordset
    data._button(1)  # BOFAction MoveFirst: stays
    assert rs.AbsolutePosition == 0
    data._button(3)
    data._button(2)  # EOFAction MoveLast: stays
    assert rs.AbsolutePosition == 2
    data.EOFAction = vpEOFActionEOF
    data._button(2)
    assert rs.EOF and form.txtName.Text == "" and form.chkVaccinated.Value == 2
    data._button(1)
    assert rs("Name") == "Coco"
    data._button(0)
    data.BOFAction = vpBOFActionBOF
    data._button(1)
    assert rs.BOF
    data.EOFAction = vpEOFActionAddNew
    data._button(3)
    data._button(2)
    assert rs.EditMode == vpEditAdd and form.txtName.Text == ""
    data._button(0)  # nothing typed: no new record
    assert rs.RecordCount == 3
    data._button(3)
    data._button(2)
    form.txtName.Text = "Zed"
    form.cboKind.Text = "Dog"
    form.chkVaccinated.Value = 1
    data._button(1)
    assert rs.RecordCount == 4 and rs("Name") == "Coco"
    assert rows(db_path)[-1] == ("Zed", "Dog", None, 1)
    assert form.grd.Rows == 5


def test_errors_and_read_only(qapp, db_path, tmp_path):
    class Errors(PetForm):
        def dta_Error(self, Description):
            self.log.append(("Error", Description))

    Errors.database = str(tmp_path / "missing.db")
    form = Errors()
    form.Show()
    assert form.dta.Recordset is None and "Couldn't find" in form.log[1][1]
    assert form.txtName.Text == "" and form.grd.Rows == 1
    form.dta.DatabaseName = db_path
    form.dta.Refresh()
    form.dta.EOFAction = vpEOFActionAddNew
    form.dta._button(3)
    form.dta._button(2)
    form.txtAge.Text = "4"  # no Name: NOT NULL
    form.dta._button(0)
    assert form.log[-1][0] == "Error" and "NOT NULL" in form.log[-1][1]
    assert form.dta.Recordset.EditMode == vpEditAdd  # still there to fix
    form.dta.Recordset.CancelUpdate()
    form.dta.ReadOnly = True
    form.dta.Refresh()
    form.txtName.Text = "Changed"
    form.dta.Recordset.MoveNext()
    assert rows(db_path)[0][0] == "Bella"
    form.Unload()


def test_saved_on_unload_and_grid_moves_the_record(pets, db_path):
    form = pets
    form.grd._widget.setCurrentCell(2, 0)  # a row chosen in the grid
    assert form.dta.Recordset.AbsolutePosition == 2 and form.txtName.Text == "Coco"
    form.txtName.Text = "Cocoa"
    form.log.clear()
    form.Unload()
    assert form.log[0] == ("Validate", vpDataActionUnload, True)
    assert rows(db_path)[2][0] == "Cocoa"


def test_binding_at_run_time_lists_and_pictures(qapp, db_path):
    db = OpenDatabase(db_path)
    db.Execute("UPDATE pets SET Photo = ?", Picture(12, 9, vpBlue))
    db.Close()

    class Bound(Form):
        def InitializeComponent(self):
            self.dta = Data(self, DatabaseName=db_path, RecordSource="pets")
            self.lst = ListBox(self, List=["Cat", "Dog"], DataSource="dta", DataField="Kind")
            self.img = Image(self, DataSource="dta", DataField="Photo")
            self.pic = PictureBox(self)
            self.txt = TextBox(self)

    form = Bound()
    form.Show()
    assert form.lst.Text == "Cat" and form.img.Picture.Width == 12
    form.txt.DataField = "Name"
    form.txt.DataSource = form.dta  # (VB's Set ... = Data1)
    assert form.txt.DataSource == "dta" and form.txt.Text == "Bella"
    form.pic.DataSource, form.pic.DataField = "dta", "Photo"
    assert form.pic.Picture.Height == 9
    form.img.Picture = Picture(3, 3, vpBlue)
    assert form.img.DataChanged
    form.dta.Recordset.MoveLast()
    assert form.lst.ListIndex == -1  # Parrot isn't in its list
    form.dta.Recordset.MoveFirst()
    assert form.img.Picture.Width == 3
    form.Unload()


def test_recordset_can_be_assigned(qapp, db_path):
    class Bound(Form):
        def InitializeComponent(self):
            self.dta = Data(self)
            self.txt = TextBox(self, DataSource="dta", DataField="Name")

    form = Bound()
    form.Show()
    assert form.dta.Recordset is None
    db = OpenDatabase(db_path)
    form.dta.Recordset = db.OpenRecordset("SELECT * FROM pets ORDER BY Name DESC")
    assert form.txt.Text == "Max"
    with pytest.raises(TypeError):
        form.dta.Recordset = "pets"
    form.Unload()
    db.Close()


# --- in the IDE ----------------------------------------------------------------------------------

def test_toolbox_designer_and_properties_window(qapp, tmp_path, db_path):
    from vp6.ide import icons
    from vp6.ide.designer import FormDesigner
    from vp6.ide.documents import FormDocument
    from vp6.ide.panels import Toolbox
    from vp6.ide.properties import PropertiesWindow

    assert "Data" in Toolbox().buttons and CONTROL_TYPES["Data"] is Data
    assert list(CONTROL_TYPES)[-2:] == ["Data", "Menu"] and not icons.icon("Data").isNull()
    assert Data.EventArgs["Validate"] == "Action, Save" and Data.DefaultEvent == "Validate"
    for name in ("TextBox", "Label", "CheckBox", "ComboBox", "ListBox", "Image"):
        assert {"DataSource", "DataField"} <= set(CONTROL_TYPES[name]._specs)
    assert "DataField" not in FlexGrid._specs and "DataSource" in FlexGrid._specs
    assert field_names(db_path, "SELECT Name, Age FROM pets") == ["Name", "Age"]
    assert field_names(db_path, "nothing") == [] and field_names("", "pets") == []

    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    data = designer.create_control("Data", None, None)
    assert data == "Data1" and designer.controls[data].Recordset is None
    designer.select([data])
    assert designer.set_property("DatabaseName", "pets.db") is None
    assert designer.set_property("RecordSource", "pets") is None
    text = designer.create_control("TextBox", None, None)
    designer.select([text])
    assert designer.set_property("DataSource", "Data1") is None
    window = PropertiesWindow()
    window.set_designer(designer)

    def editor(prop):
        row = next(r for r in range(window.table.rowCount())
                   if window.table.item(r, 0) is not None and
                   window.table.item(r, 0).text() == prop)
        return window.table.cellWidget(row, 1)

    sources = editor("DataSource")
    assert [sources.itemText(i) for i in range(sources.count())] == ["Data1"]
    fields = editor("DataField")
    assert [fields.itemText(i) for i in range(fields.count())] == \
        ["Id", "Name", "Kind", "Age", "Vaccinated", "Photo"]
    fields.setCurrentText("Name")
    fields.lineEdit().editingFinished.emit()
    assert "DataSource='Data1', DataField='Name'" in designer.document.text
    designer.close()
    assert "Data" in vp6.__all__ and "OpenDatabase" in vp6.__all__
