"""SpinBox, DTPicker, MonthView, Dial, LCDNumber, FontComboBox and HotKey."""

import datetime

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QKeySequence, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLCDNumber

import vp6
from vp6 import (Data, Dial, DTPicker, FontComboBox, Form, HotKey, LCDNumber, MonthView,
                 SpinBox, TextBox, formfile)
from vp6.controls import CONTROL_TYPES
from vp6.inputs import as_date, as_datetime

NEW_TYPES = ("SpinBox", "DTPicker", "MonthView", "Dial", "LCDNumber", "FontComboBox", "HotKey")


@pytest.fixture
def form(qapp):
    class Inputs(Form):
        def InitializeComponent(self):
            self.events = []
            self.spnQty = SpinBox(self, Max=50, Value=10, Increment=5, Suffix=" pcs")
            self.spnPrice = SpinBox(self, DecimalPlaces=2, Max=9.99, Value=4.5, Prefix="$")
            self.dtpWhen = DTPicker(self, Format=3, CustomFormat="yyyy-MM-dd HH:mm")
            self.mvwDays = MonthView(self)
            self.dialSpeed = Dial(self, Max=255)
            self.lcdTotal = LCDNumber(self, Digits=4)
            self.fcbFont = FontComboBox(self)
            self.hkyKeys = HotKey(self, Keys="Ctrl+Shift+S")

        def spnQty_Change(self):
            self.events.append(("Change", self.spnQty.Value))

        def dtpWhen_Change(self):
            self.events.append(("DTChange", self.dtpWhen.Value))

        def dtpWhen_DropDown(self):
            self.events.append("DropDown")

        def dtpWhen_CloseUp(self):
            self.events.append("CloseUp")

        def mvwDays_DateClick(self, DateClicked):
            self.events.append(("DateClick", DateClicked))

        def mvwDays_DateDblClick(self, DateDblClicked):
            self.events.append(("DateDblClick", DateDblClicked))

        def mvwDays_SelChange(self, StartDate, EndDate):
            self.events.append(("SelChange", StartDate, EndDate))

        def dialSpeed_Scroll(self):
            self.events.append(("Scroll", self.dialSpeed.Value))

        def dialSpeed_Change(self):
            self.events.append(("DialChange", self.dialSpeed.Value))

        def lcdTotal_Overflow(self):
            self.events.append("Overflow")

        def fcbFont_Click(self):
            self.events.append(("Font", self.fcbFont.FontName))

        def hkyKeys_Change(self):
            self.events.append(("Keys", self.hkyKeys.Keys))

    f = Inputs()
    yield f
    f.Unload()


def test_registered_with_validation_and_mouse_members(qapp):
    names = list(CONTROL_TYPES)
    assert names[-1] == "Menu"
    for name in NEW_TYPES:
        cls = CONTROL_TYPES[name]
        assert name in names and name in vp6.__all__
        assert "DragDrop" in cls.Events and "MousePointer" in cls._specs
    assert "Validate" in SpinBox.Events and "CausesValidation" in HotKey._specs
    assert "DataSource" in SpinBox._specs and "DataField" in DTPicker._specs


def test_dates_from_anything(qapp):
    assert as_datetime("2026-10-11 14:30") == datetime.datetime(2026, 10, 11, 14, 30)
    assert as_datetime(datetime.date(2026, 1, 2)) == datetime.datetime(2026, 1, 2)
    assert as_date(QDate(2020, 2, 29)) == datetime.date(2020, 2, 29)
    assert as_datetime("") is None and as_datetime(None) is None
    assert as_datetime("09:15").time() == datetime.time(9, 15)
    with pytest.raises(ValueError):
        as_datetime("next tuesday")


def test_spinbox(form):
    spin = form.spnQty
    assert spin.Value == 10 and isinstance(spin.Value, int) and spin.Text == "10 pcs"
    form.events.clear()
    spin.StepUp()
    assert spin.Value == 15 and form.events == [("Change", 15)]
    spin.Value = 80  # kept between Min and Max
    assert spin.Value == 50
    spin.Wrap = True
    spin.StepUp()
    assert spin.Value == 0  # (past Max: Min)
    price = form.spnPrice
    assert price.Value == 4.5 and isinstance(price.Value, float) and price.Text == "$4.50"
    price.Value = 3.14159
    assert price.Value == 3.14
    price.Locked = True
    assert price._widget.isReadOnly()
    price.Alignment = vp6.vpRightJustify
    assert price._widget.alignment() & Qt.AlignRight


def test_number_kind(qapp):
    from vp6._props import normalize

    assert normalize("number", "2.50") == 2.5 and normalize("number", 3.0) == 3
    assert isinstance(normalize("number", "7"), int)
    assert formfile.format_value("number", 0.25) == "0.25"


def test_dtpicker(form):
    picker = form.dtpWhen
    form.events.clear()
    picker.Value = "2026-03-04 05:06"
    assert picker.Value == datetime.datetime(2026, 3, 4, 5, 6)
    assert picker.Text == "2026-03-04 05:06" and (picker.Year, picker.Hour) == (2026, 5)
    assert form.events == [("DTChange", datetime.datetime(2026, 3, 4, 5, 6))]
    picker.Value = datetime.date(2025, 12, 24)
    assert picker.Day == 24 and picker.Minute == 0
    picker.MinDate = "2026-01-01"
    picker.Value = "2020-05-05"  # before MinDate: MinDate
    assert picker.Value.date() == datetime.date(2026, 1, 1)
    picker.MaxDate = "2026-06-30"  # (that whole day)
    picker.Value = "2026-06-30 23:00"
    assert picker.Value.hour == 23
    picker.Format = vp6.vpDtpLongDate
    assert "2026" in picker.Text and ":" not in picker.Text
    picker.UpDown = True
    assert not picker._widget.calendarPopup()
    picker.UpDown, picker.CalendarDropDown = False, False
    assert not picker._widget.calendarPopup() and \
        picker._widget.buttonSymbols() == picker._widget.ButtonSymbols.NoButtons
    picker.CalendarDropDown = True
    popup = picker._widget.calendarWidget().window()
    form.events.clear()
    popup.show()
    popup.hide()
    assert form.events == ["DropDown", "CloseUp"]
    with pytest.raises(ValueError):
        picker.Value = ""


def test_monthview(form):
    view = form.mvwDays
    form.events.clear()
    view.Value = "2026-05-06"
    assert view.Value == datetime.date(2026, 5, 6)
    assert form.events == [("SelChange", datetime.date(2026, 5, 6), datetime.date(2026, 5, 6))]
    calendar = view._widget.calendar
    calendar.clicked.emit(QDate(2026, 5, 7))
    calendar.activated.emit(QDate(2026, 5, 8))
    assert form.events[-2:] == [("DateClick", datetime.date(2026, 5, 7)),
                                ("DateDblClick", datetime.date(2026, 5, 8))]
    view.DayBold["2026-05-09"] = True
    assert view.DayBold(datetime.date(2026, 5, 9)) and not view.DayBold[datetime.date(2026, 5, 1)]
    assert calendar.dateTextFormat(QDate(2026, 5, 9)).fontWeight() > 500
    view.DayBold["2026-05-09"] = False
    assert list(view.DayBold) == []
    view.StartOfWeek = vp6.vpSunday
    assert calendar.firstDayOfWeek() == Qt.Sunday
    view.ShowWeekNumbers = True
    assert calendar.verticalHeaderFormat() == calendar.VerticalHeaderFormat.ISOWeekNumbers
    view.MinDate = "2026-05-01"
    view.Value = "2026-01-01"
    assert view.Value == datetime.date(2026, 5, 1)
    view.MinDate = ""
    view._widget.today.linkActivated.emit("today")  # the Today link
    assert view.Value == datetime.date.today()
    view.ShowToday = False
    assert view._widget.today.isHidden()


def test_dial(form):
    dial = form.dialSpeed
    form.events.clear()
    dial.Value = 40
    assert form.events == [("DialChange", 40)]
    dial._widget.setSliderDown(True)  # dragged: Scroll, then Change when let go
    dial._widget.setValue(60)
    dial._widget.setSliderDown(False)
    dial._widget.sliderReleased.emit()
    assert form.events[-2:] == [("Scroll", 60), ("DialChange", 60)]
    dial.Value = 999
    assert dial.Value == 255
    dial.Wrapping, dial.NotchesVisible = True, False  # (wrapping: past Max goes round)
    assert dial._widget.wrapping() and not dial._widget.notchesVisible()


def test_lcdnumber(form):
    lcd = form.lcdTotal
    lcd.Value = 12.5
    assert lcd.Value == 12.5 and lcd.Text == "12.5" and lcd._widget.value() == 12.5
    form.events.clear()
    lcd.Value = 123456  # too long for 4 digits
    assert "Overflow" in form.events and lcd.Overflowing
    lcd.Digits = 8
    assert not lcd.Overflowing
    lcd.Mode, lcd.Value = vp6.vpLcdHex, 255
    assert lcd.Text == "ff" and lcd._widget.mode() == QLCDNumber.Mode.Hex
    lcd.Text = "12:30"
    assert lcd.Text == "12:30"
    lcd.SegmentStyle = vp6.vpLcdFlat
    assert lcd._widget.segmentStyle() == QLCDNumber.SegmentStyle.Flat
    lcd.ForeColor = vp6.vpRed
    assert lcd._widget.palette().color(QPalette.WindowText).name() == "#ff0000"


def test_fontcombobox(form):
    combo = form.fcbFont
    family = form.fcbFont.List[1]
    form.events.clear()
    combo.FontName = family
    assert combo.FontName == family and form.events == [("Font", family)]
    assert combo.ListCount == len(combo.List) > 1
    combo.FontFilters = vp6.vpFontsMonospaced
    assert combo.ListCount >= 1 and combo._widget.fontFilters() & \
        combo._widget.FontFilter.MonospacedFonts


def test_hotkey(form):
    keys = form.hkyKeys
    assert keys.Keys == "Ctrl+Shift+S"
    assert keys.KeyCode == vp6.vpKeyS and keys.Shift == vp6.vpShiftMask + vp6.vpCtrlMask
    form.events.clear()
    keys.Keys = "F5"
    assert keys.KeyCode == vp6.vpKeyF5 and keys.Shift == 0
    assert form.events == [("Keys", "F5")]
    keys.Clear()
    assert keys.Keys == "" and keys.KeyCode == 0
    keys._widget.setKeySequence(QKeySequence("Alt+X"))  # recorded by the user
    assert keys.Keys == "Alt+X"
    keys.ClearButton = True
    keys.MaxKeys = 2
    if hasattr(keys._widget, "maximumSequenceLength"):
        assert keys._widget.maximumSequenceLength() == 2


def test_spinbox_and_dtpicker_are_data_bound(qapp, tmp_path):
    db = vp6.CreateDatabase(str(tmp_path / "shop.db"))
    db.Execute("CREATE TABLE items (Name TEXT, Qty INTEGER, Due TEXT)")
    db.Execute("INSERT INTO items VALUES ('Nails', 12, '2026-04-01')")
    db.Execute("INSERT INTO items VALUES ('Screws', 30, '2026-05-15')")
    db.Close()

    class Shop(Form):
        def InitializeComponent(self):
            self.dtaItems = Data(self, DatabaseName=str(tmp_path / "shop.db"),
                                 RecordSource="items")
            self.txtName = TextBox(self, DataSource="dtaItems", DataField="Name")
            self.spnQty = SpinBox(self, Max=100, DataSource="dtaItems", DataField="Qty")
            self.dtpDue = DTPicker(self, DataSource="dtaItems", DataField="Due")

    shop = Shop()
    shop.Show()
    try:
        assert shop.spnQty.Value == 12 and shop.dtpDue.Value.date() == datetime.date(2026, 4, 1)
        shop.spnQty.Value = 15
        shop.dtpDue.Value = "2026-04-02"
        assert shop.spnQty.DataChanged and shop.dtpDue.DataChanged
        shop.dtaItems.Recordset.MoveNext()
        assert shop.spnQty.Value == 30
        shop.dtaItems.Recordset.MoveFirst()
        assert shop.spnQty.Value == 15 and shop.dtaItems.Recordset("Due") == "2026-04-02"
    finally:
        shop.Unload()


@pytest.mark.parametrize("type_name", NEW_TYPES)
def test_designer_creates_them(qapp, tmp_path, type_name):
    from vp6.ide.designer import NAME_PREFIX, FormDesigner
    from vp6.ide.documents import FormDocument
    from vp6.ide.panels import TOOLBOX_CATEGORIES

    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    designer = FormDesigner(FormDocument(str(path)), str(tmp_path))
    name = designer.create_control(type_name, None, None)
    assert name == f"{NAME_PREFIX[type_name]}1"
    assert f"self.{name} = {type_name}(self" in designer.document.text
    assert formfile.parse(designer.document.text).control(name).type == type_name
    assert any(type_name in names for _title, names in TOOLBOX_CATEGORIES)
