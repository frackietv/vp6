"""Controls for entering values: ``SpinBox``, ``DTPicker``, ``MonthView``,
``Dial``, ``LCDNumber`` (a display), ``FontComboBox`` and ``HotKey``.

* **SpinBox** is a number box with arrows in one control (UpDown stays the
  separate buddy control): ``Value`` between ``Min`` and ``Max`` in steps of
  ``Increment``, with ``DecimalPlaces``, a ``Prefix`` and a ``Suffix``;
  ``Wrap`` goes round. ``Change`` fires when the Value changes.
* **DTPicker** is VB's date and time picker: ``Value`` is a ``datetime``;
  ``Format`` vpDtpShortDate, vpDtpLongDate, vpDtpTime or vpDtpCustom
  (``CustomFormat``, Qt's: ``"yyyy-MM-dd HH:mm"``); ``MinDate``/``MaxDate``
  (ISO text, ``"2000-01-01"``); a ``CalendarDropDown`` or ``UpDown`` arrows.
  Events: ``Change``, ``DropDown``, ``CloseUp``.
* **MonthView** is VB's month calendar: ``Value`` (a ``date``),
  ``MinDate``/``MaxDate``, ``StartOfWeek``, ``ShowWeekNumbers``,
  ``ShowToday`` (a "Today" link under it), ``DayBold[date] = True``; events
  ``DateClick(DateClicked)``, ``DateDblClick(DateDblClicked)``,
  ``SelChange(StartDate, EndDate)``.
* **Dial** is a knob, like the Slider: ``Value``, ``Min``, ``Max``,
  ``SmallChange``/``LargeChange``, ``Wrapping``, ``NotchesVisible``;
  ``Scroll`` while it is turned by the mouse, ``Change`` once it has changed.
* **LCDNumber** is a seven-segment display: ``Value`` (a number) or ``Text``
  (digits, ``:``, ``-``, a few letters), ``Digits``, ``Mode`` (decimal, hex,
  octal, binary), ``SegmentStyle``, ``SmallDecimalPoint``; ``Overflow`` fires
  when a value doesn't fit.
* **FontComboBox** lists the fonts, each drawn in its own font: ``FontName``
  is the one chosen (``Click`` when it changes), ``FontFilters`` which fonts.
* **HotKey** records a shortcut the user presses: ``Keys`` is its text
  (``"Ctrl+Shift+S"``), ``KeyCode`` and ``Shift`` its key and modifiers as
  KeyDown gives them, ``MaxKeys`` how many presses it records,
  ``ClearButton``; ``Change`` fires when it changes.

SpinBox and DTPicker are data-bound like a TextBox (``DataSource``,
``DataField``).
"""

from __future__ import annotations

import datetime as _dt

from PySide6.QtCore import QDate, QDateTime, QEvent, QLocale, QObject, Qt, QTime
from PySide6.QtGui import QFont, QKeySequence, QPalette, QTextCharFormat
from PySide6.QtWidgets import (QAbstractSpinBox, QCalendarWidget, QDateTimeEdit, QDial,
                               QDoubleSpinBox, QFontComboBox, QFrame, QKeySequenceEdit, QLabel,
                               QLCDNumber, QLineEdit, QTableView, QVBoxLayout, QWidget)

from . import colors
from ._props import P, enum_choices
from .controls import (_ALIGNMENT, _COLORS, _COMMON, _FONT, _QT_ALIGN, CONTROL_TYPES, EVENT_ARGS,
                       Control, _add_mouse_members, _add_validation, _geometry, vp_key_code,
                       vp_shift)
from .data import BINDINGS, _add_binding, _as_text

EVENT_ARGS.update({"DropDown": "", "CloseUp": "", "Overflow": "", "DateClick": "DateClicked",
                   "DateDblClick": "DateDblClicked"})

_BASIC = (P("Enabled", "bool", True, description="Whether the control responds to the user"),
          P("Visible", "bool", True, description="Whether the control is shown at run time"),
          P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
          P("Tag", "str", "", description="Free for your own use"),
          P("ZIndex", "int", 0, description=_COMMON[-1].description))


# --- dates ------------------------------------------------------------------------------------

def as_datetime(value) -> _dt.datetime | None:
    """A date or time given as a datetime, a date, a QDateTime / QDate or ISO
    text ("2026-10-11", "2026-10-11 14:30"); None for None or ""."""
    if value is None or value == "":
        return None
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day)
    if isinstance(value, QDateTime):
        return as_datetime(value.toString(Qt.ISODate))
    if isinstance(value, QDate):
        return _dt.datetime(value.year(), value.month(), value.day())
    if isinstance(value, _dt.time):
        today = _dt.date.today()
        return _dt.datetime.combine(today, value)
    text = str(value).strip().replace("T", " ")
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        pass
    try:  # (a time alone: today at that time)
        return _dt.datetime.combine(_dt.date.today(), _dt.time.fromisoformat(text))
    except ValueError:
        raise ValueError(f"Not a date or time: {value!r} (e.g. '2026-10-11 14:30')") from None


def as_date(value) -> _dt.date | None:
    moment = as_datetime(value)
    return moment.date() if moment is not None else None


def _qdate(day: _dt.date) -> QDate:
    return QDate(day.year, day.month, day.day)


def _qdatetime(moment: _dt.datetime) -> QDateTime:
    return QDateTime(_qdate(moment), QTime(moment.hour, moment.minute, moment.second,
                                           moment.microsecond // 1000))


def _from_qdate(day: QDate) -> _dt.date:
    return _dt.date(day.year(), day.month(), day.day())


def _from_qdatetime(moment: QDateTime) -> _dt.datetime:
    day, time = moment.date(), moment.time()
    return _dt.datetime(day.year(), day.month(), day.day(), time.hour(), time.minute(),
                        time.second(), time.msec() * 1000)


def _date_spec(name: str, what: str) -> P:
    return P(name, "str", "", description=f"The {what} date that can be chosen, as ISO text "
                                          f"(e.g. 2000-01-01); empty = no limit")


class _InnerEdits:
    """A control whose widget has an editor inside it (a spin box's line
    edit): the mouse over that editor is the control's, the keys and the
    focus only once (they come to the outer widget)."""

    def _inner(self) -> QWidget | None:
        return None

    def _event_targets(self):
        inner = self._inner()
        return [self._widget] + ([inner] if inner is not None else [])

    def _on_qt_event(self, watched, event):
        if watched is not self._widget and event.type() in (
                QEvent.KeyPress, QEvent.KeyRelease, QEvent.FocusIn, QEvent.FocusOut,
                QEvent.ShortcutOverride):
            return False
        return super()._on_qt_event(watched, event)


# --- SpinBox ---------------------------------------------------------------------------------

class SpinBox(_InnerEdits, Control):
    """A number box with arrows (the module's documentation). The Value is an
    int while DecimalPlaces is 0, else a float."""

    TypeName = "SpinBox"
    DefaultEvent = "Change"
    DefaultSize = (97, 25)
    Events = ("Change", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp", "MouseDown",
              "MouseMove", "MouseUp")
    _qss_type = "QDoubleSpinBox"
    Properties = (
        *_geometry(*DefaultSize),
        P("DecimalPlaces", "int", 0,
          description="Digits after the decimal point; 0 = whole numbers (the Value is an int)"),
        P("Min", "number", 0, description="Smallest Value"),
        P("Max", "number", 100, description="Largest Value"),
        P("Value", "number", 0,
          description="The number, kept between Min and Max; changing it fires Change"),
        P("Increment", "number", 1,
          description="How much an arrow (or the Up and Down keys) changes the Value"),
        P("Prefix", "str", "", description="Text shown before the number, e.g. $"),
        P("Suffix", "str", "", description="Text shown after the number, e.g. ' kg'"),
        P("Wrap", "bool", False,
          description="Past Max go on from Min (and below Min from Max) instead of stopping"),
        P("Alignment", "enum", 0, _ALIGNMENT, description="Where the number is in the box"),
        P("Locked", "bool", False, description="Read-only: the number can't be changed"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        widget = QDoubleSpinBox(parent)
        widget.setDecimals(0)
        widget.setRange(0, 100)
        widget.setKeyboardTracking(False)  # (Change for a number typed in: when it's done)
        return widget

    def _inner(self):
        return self._widget.lineEdit()

    def _connect_signals(self):
        self._widget.valueChanged.connect(lambda *_: self._fire("Change"))

    def _number(self, value):
        return int(round(value)) if self._widget.decimals() == 0 else float(value)

    def _apply_DecimalPlaces(self, v):
        self._widget.setDecimals(max(0, min(int(v), 10)))

    def _apply_Min(self, v):
        self._widget.setMinimum(float(v))

    def _apply_Max(self, v):
        self._widget.setMaximum(float(v))

    def _read_Value(self):
        return self._number(self._widget.value())

    def _apply_Value(self, v):
        self._widget.setValue(float(v))

    def _apply_Increment(self, v):
        self._widget.setSingleStep(float(v))

    def _apply_Prefix(self, v):
        self._widget.setPrefix(v)

    def _apply_Suffix(self, v):
        self._widget.setSuffix(v)

    def _apply_Wrap(self, v):
        self._widget.setWrapping(bool(v))

    def _apply_Alignment(self, v):
        self._widget.setAlignment(_QT_ALIGN.get(v, Qt.AlignLeft) | Qt.AlignVCenter)

    def _apply_Locked(self, v):
        self._widget.setReadOnly(bool(v))

    @property
    def Text(self) -> str:
        """What the box shows: the number with its Prefix and Suffix (read-only)."""
        return self._widget.text()

    def StepUp(self) -> None:
        """Up by one Increment, as the up arrow."""
        self._widget.stepUp()

    def StepDown(self) -> None:
        """Down by one Increment, as the down arrow."""
        self._widget.stepDown()


# --- DTPicker -----------------------------------------------------------------------------------

class _PopupWatcher(QObject):
    """DTPicker's DropDown and CloseUp: its calendar's window shown and hidden."""

    def __init__(self, picker: "DTPicker", parent: QObject):
        super().__init__(parent)
        self._picker = picker

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Show:
            self._picker._fire("DropDown")
        elif event.type() == QEvent.Hide:
            self._picker._fire("CloseUp")
        return False


class DTPicker(_InnerEdits, Control):
    """VB's date and time picker (the module's documentation)."""

    TypeName = "DTPicker"
    DefaultEvent = "Change"
    DefaultSize = (161, 25)
    Events = ("Change", "DropDown", "CloseUp", "GotFocus", "LostFocus", "KeyDown", "KeyPress",
              "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QDateTimeEdit"
    Properties = (
        *_geometry(*DefaultSize),
        P("Format", "enum", 0, enum_choices("Short Date", "Long Date", "Time", "Custom"),
          description="How the Value is shown: the system's short or long date, its time, or "
                      "CustomFormat"),
        P("CustomFormat", "str", "yyyy-MM-dd HH:mm",
          description="With Format Custom: Qt's date format, e.g. dd.MM.yyyy or "
                      "ddd d MMM yyyy, h:mm ap"),
        _date_spec("MinDate", "earliest"),
        _date_spec("MaxDate", "latest"),
        P("CalendarDropDown", "bool", True,
          description="An arrow that drops a month calendar down to choose the date from"),
        P("UpDown", "bool", False,
          description="Up and down arrows that step the part of the date or time the cursor "
                      "is in (instead of the calendar)"),
        P("Alignment", "enum", 0, _ALIGNMENT, description="Where the text is in the box"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        widget = QDateTimeEdit(parent)
        widget.setDateTime(_qdatetime(_dt.datetime.now().replace(second=0, microsecond=0)))
        widget.setCalendarPopup(True)
        if not self._design_mode:  # (DropDown, CloseUp)
            popup = widget.calendarWidget()
            watcher = _PopupWatcher(self, widget)
            popup.window().installEventFilter(watcher)
            self.__dict__["_popup_watcher"] = watcher
        return widget

    def _inner(self):
        return self._widget.lineEdit()

    def _connect_signals(self):
        self._widget.dateTimeChanged.connect(lambda *_: self._fire("Change"))

    # -- the value ---------------------------------------------------------------------------
    @property
    def Value(self) -> _dt.datetime:
        """The date and time (a datetime); set it to a datetime, a date or ISO
        text ("2026-10-11 14:30"). Changing it fires Change."""
        return _from_qdatetime(self._widget.dateTime())

    @Value.setter
    def Value(self, value):
        moment = as_datetime(value)
        if moment is None:
            raise ValueError(f"DTPicker '{self.Name}': the Value must be a date or a time")
        self._widget.setDateTime(_qdatetime(moment))

    @property
    def Text(self) -> str:
        """The Value as the box shows it (read-only)."""
        return self._widget.text()

    def _part(name):  # noqa: N805 - (a helper building the properties below)
        def fget(self):
            return getattr(self.Value, name.lower())
        return property(fget, doc=f"The Value's {name.lower()} (read-only)")

    Year, Month, Day = _part("Year"), _part("Month"), _part("Day")
    Hour, Minute, Second = _part("Hour"), _part("Minute"), _part("Second")
    del _part

    # -- how it looks -------------------------------------------------------------------------
    def _apply_Format(self, v):
        locale = QLocale()
        formats = {0: locale.dateFormat(QLocale.ShortFormat),
                   1: locale.dateFormat(QLocale.LongFormat),
                   2: locale.timeFormat(QLocale.ShortFormat)}
        self._widget.setDisplayFormat(formats.get(v) or self._values.get("CustomFormat") or
                                      "yyyy-MM-dd HH:mm")

    def _apply_CustomFormat(self, v):
        if self._values.get("Format") == 3:
            self._apply_Format(3)

    def _apply_MinDate(self, v):
        moment = as_datetime(v)
        self._widget.setMinimumDateTime(_qdatetime(moment) if moment else
                                        QDateTime(QDate(100, 1, 1), QTime(0, 0)))

    def _apply_MaxDate(self, v):
        moment = as_datetime(v)
        if moment is not None and moment.time() == _dt.time(0, 0) and len(str(v)) <= 10:
            moment = moment.replace(hour=23, minute=59, second=59)  # (that whole day)
        self._widget.setMaximumDateTime(_qdatetime(moment) if moment else
                                        QDateTime(QDate(9999, 12, 31), QTime(23, 59, 59)))

    def _apply_buttons(self, _=None):
        updown = self._values.get("UpDown", False)
        calendar = self._values.get("CalendarDropDown", True) and not updown
        self._widget.setCalendarPopup(calendar)
        self._widget.setButtonSymbols(QAbstractSpinBox.UpDownArrows if updown or calendar
                                      else QAbstractSpinBox.NoButtons)

    _apply_CalendarDropDown = _apply_UpDown = _apply_buttons

    def _apply_Alignment(self, v):
        self._widget.setAlignment(_QT_ALIGN.get(v, Qt.AlignLeft) | Qt.AlignVCenter)


# --- MonthView ------------------------------------------------------------------------------------

class _MonthWidget(QWidget):
    """A month calendar with a "Today:" link under it."""

    def __init__(self, parent):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        layout.addWidget(self.calendar, 1)
        self.today = QLabel(self)
        self.today.setTextFormat(Qt.RichText)
        self.today.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.today)
        self.update_today()

    def update_today(self) -> None:
        day = QDate.currentDate()
        text = QLocale().toString(day, QLocale.ShortFormat)
        self.today.setText(f'<a href="today">Today: {text}</a>')


class _DayBold:
    """MonthView.DayBold: ``mvw.DayBold(date)`` (or ``[date]``) tells whether
    a day is in bold, ``mvw.DayBold[date] = True`` makes it so."""

    def __init__(self, view: "MonthView"):
        self._view = view

    def __call__(self, date) -> bool:
        return as_date(date) in self._view._bold

    __getitem__ = __call__

    def __setitem__(self, date, bold) -> None:
        day = as_date(date)
        days = self._view._bold
        if bold:
            days.add(day)
        else:
            days.discard(day)
        fmt = QTextCharFormat()
        if bold:
            fmt.setFontWeight(QFont.Bold)
        self._view._widget.calendar.setDateTextFormat(_qdate(day), fmt)

    def __iter__(self):
        return iter(sorted(self._view._bold))


class MonthView(Control):
    """VB's month calendar (the module's documentation)."""

    TypeName = "MonthView"
    DefaultEvent = "DateClick"
    DefaultSize = (281, 233)
    Events = ("DateClick", "DateDblClick", "SelChange", "GotFocus", "LostFocus", "KeyDown",
              "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    EventArgs = {"DateClick": "DateClicked", "DateDblClick": "DateDblClicked",
                 "SelChange": "StartDate, EndDate"}
    _qss_type = "QCalendarWidget"
    Properties = (
        *_geometry(*DefaultSize),
        _date_spec("MinDate", "earliest"),
        _date_spec("MaxDate", "latest"),
        P("StartOfWeek", "enum", 0, enum_choices("System", "Monday", "Tuesday", "Wednesday",
                                                 "Thursday", "Friday", "Saturday", "Sunday"),
          description="The first day of each week's row (System: as the system's locale)"),
        P("ShowWeekNumbers", "bool", False, description="Week numbers at the left"),
        P("ShowToday", "bool", True,
          description="A 'Today:' link under the calendar that goes to today"),
        *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_bold"] = set()
        widget = _MonthWidget(parent)
        widget.today.linkActivated.connect(lambda _link: self._go_today())
        return widget

    def _event_targets(self):
        view = self._widget.calendar.findChild(QTableView)
        return [self._widget] + ([view, view.viewport()] if view is not None else [])

    def _connect_signals(self):
        calendar = self._widget.calendar
        calendar.clicked.connect(lambda day: self._fire("DateClick", _from_qdate(day)))
        calendar.activated.connect(lambda day: self._fire("DateDblClick", _from_qdate(day)))
        calendar.selectionChanged.connect(
            lambda: self._fire("SelChange", self.Value, self.Value))

    def _go_today(self) -> None:
        if not self._design_mode:
            self.Value = _dt.date.today()

    @property
    def Value(self) -> _dt.date:
        """The chosen day (a date); set it to a date, a datetime or ISO text."""
        return _from_qdate(self._widget.calendar.selectedDate())

    @Value.setter
    def Value(self, value):
        day = as_date(value)
        if day is None:
            raise ValueError(f"MonthView '{self.Name}': the Value must be a date")
        self._widget.calendar.setSelectedDate(_qdate(day))

    @property
    def DayBold(self) -> _DayBold:
        """The days shown in bold: ``DayBold(date)``, ``DayBold[date] = True``."""
        return _DayBold(self)

    def _apply_MinDate(self, v):
        day = as_date(v)
        self._widget.calendar.setMinimumDate(_qdate(day) if day else QDate(100, 1, 1))

    def _apply_MaxDate(self, v):
        day = as_date(v)
        self._widget.calendar.setMaximumDate(_qdate(day) if day else QDate(9999, 12, 31))

    def _apply_StartOfWeek(self, v):
        day = Qt.DayOfWeek(int(v)) if 1 <= int(v) <= 7 else QLocale().firstDayOfWeek()
        self._widget.calendar.setFirstDayOfWeek(day)

    def _apply_ShowWeekNumbers(self, v):
        self._widget.calendar.setVerticalHeaderFormat(
            QCalendarWidget.ISOWeekNumbers if v else QCalendarWidget.NoVerticalHeader)

    def _apply_ShowToday(self, v):
        self._widget.today.setVisible(bool(v))


# --- Dial -------------------------------------------------------------------------------------

class Dial(Control):
    """A knob turned with the mouse or the arrow keys (the module's
    documentation): Scroll while it is dragged, Change once it changed."""

    TypeName = "Dial"
    DefaultEvent = "Change"
    DefaultSize = (73, 73)
    Events = ("Change", "Scroll", "Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress",
              "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    _qss_type = "QDial"
    Properties = (
        *_geometry(*DefaultSize),
        P("Min", "int", 0, description="Smallest Value"),
        P("Max", "int", 100, description="Largest Value"),
        P("Value", "int", 0, description="The knob's position; changing it fires Change"),
        P("SmallChange", "int", 1, description="Step for the arrow keys"),
        P("LargeChange", "int", 10, description="Step for Page Up / Page Down"),
        P("Wrapping", "bool", False,
          description="Turns all the way round (Max next to Min) instead of stopping at a gap "
                      "at the bottom"),
        P("NotchesVisible", "bool", True, description="Notches around the knob"),
        *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_changed_while_dragging"] = False
        widget = QDial(parent)
        widget.setNotchesVisible(True)
        return widget

    def _connect_signals(self):
        self._widget.valueChanged.connect(self._on_value_changed)
        self._widget.sliderReleased.connect(self._on_released)

    def _on_value_changed(self, _value):
        if self._widget.isSliderDown():
            self.__dict__["_changed_while_dragging"] = True
            self._fire("Scroll")
        else:
            self._fire("Change")

    def _on_released(self):
        if self._changed_while_dragging:
            self.__dict__["_changed_while_dragging"] = False
            self._fire("Change")

    def _apply_Min(self, v):
        self._widget.setMinimum(int(v))

    def _apply_Max(self, v):
        self._widget.setMaximum(int(v))

    def _read_Value(self):
        return self._widget.value()

    def _apply_Value(self, v):
        self._widget.setValue(int(v))

    def _apply_SmallChange(self, v):
        self._widget.setSingleStep(int(v))

    def _apply_LargeChange(self, v):
        self._widget.setPageStep(int(v))

    def _apply_Wrapping(self, v):
        self._widget.setWrapping(bool(v))

    def _apply_NotchesVisible(self, v):
        self._widget.setNotchesVisible(bool(v))


# --- LCDNumber ---------------------------------------------------------------------------------

class LCDNumber(Control):
    """A seven-segment display (the module's documentation)."""

    TypeName = "LCDNumber"
    DefaultEvent = "Overflow"
    DefaultSize = (121, 41)
    Events = ("Overflow", "Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("Digits", "int", 5, description="How many digits (and points, colons) it has room for"),
        P("Mode", "enum", 0, enum_choices("Decimal", "Hex", "Octal", "Binary"),
          description="The base whole numbers are shown in"),
        P("SegmentStyle", "enum", 1, enum_choices("Outline", "Filled", "Flat"),
          description="How the segments are drawn: outlined, raised in the ForeColor, or flat"),
        P("SmallDecimalPoint", "bool", False,
          description="The decimal point between two digits instead of taking a digit's room"),
        P("Value", "number", 0,
          description="The number shown; one that doesn't fit fires Overflow"),
        P("BorderStyle", "enum", 1, enum_choices("None", "Fixed Single"),
          description="A frame around the display"),
        *_COLORS, *_BASIC,
    )

    def _create_widget(self, parent):
        self.__dict__["_text"] = None  # what Text showed (None: the Value)
        widget = QLCDNumber(parent)
        widget.setFocusPolicy(Qt.NoFocus)
        return widget

    def _connect_signals(self):
        self._widget.overflow.connect(lambda: self._fire("Overflow"))

    def _apply_Digits(self, v):
        self._widget.setDigitCount(max(1, int(v)))
        self._redisplay()

    def _apply_Mode(self, v):
        self._widget.setMode((QLCDNumber.Dec, QLCDNumber.Hex, QLCDNumber.Oct,
                              QLCDNumber.Bin)[int(v) if 0 <= int(v) <= 3 else 0])
        self._redisplay()

    def _apply_SegmentStyle(self, v):
        self._widget.setSegmentStyle((QLCDNumber.Outline, QLCDNumber.Filled,
                                      QLCDNumber.Flat)[int(v) if 0 <= int(v) <= 2 else 1])

    def _apply_SmallDecimalPoint(self, v):
        self._widget.setSmallDecimalPoint(bool(v))
        self._redisplay()

    def _redisplay(self) -> None:
        if self._text is not None:
            self._widget.display(self._text)
        elif "Value" in self._values:
            self._apply_Value(self._values["Value"])

    def _apply_Value(self, v):
        self.__dict__["_text"] = None
        value = v if isinstance(v, (int, float)) else 0
        if self._values.get("Mode", 0) and isinstance(value, float):
            value = int(value)  # (hex, octal and binary show whole numbers)
        self._widget.display(value)

    def _read_Value(self):
        value = self._values.get("Value", 0)
        return value if self._text is None else self._widget.value()

    @property
    def Text(self) -> str:
        """What it shows, as text; set it to show text (digits, '-', ':', '.',
        a few letters such as E, H, L, o, P, r, u)."""
        if self._text is not None:
            return self._text
        value = self._values.get("Value", 0)
        if isinstance(value, float) or not self._values.get("Mode", 0):
            return str(value)
        return {1: f"{value:x}", 2: f"{value:o}", 3: f"{value:b}"}[self._values["Mode"]]

    @Text.setter
    def Text(self, value):
        self.__dict__["_text"] = str(value)
        self._widget.display(str(value))

    @property
    def Overflowing(self) -> bool:
        """Whether the number shown is too long for Digits."""
        return self._widget.checkOverflow(float(self._values.get("Value", 0))) \
            if self._text is None else len(self._text.replace(".", "")) > \
            self._widget.digitCount()

    def _apply_BorderStyle(self, v):
        self._widget.setFrameStyle(QFrame.Box | QFrame.Raised if v else QFrame.NoFrame)

    def _apply_colors(self, _=None):
        widget = self._widget
        back, fore = self._values.get("BackColor"), self._values.get("ForeColor")
        palette = QPalette()  # (only the roles set: scheme changes still reach the rest)
        if fore is not None:
            color = colors.to_qcolor(fore)
            for role in (QPalette.WindowText, QPalette.Light, QPalette.Dark):
                palette.setColor(role, color)
        if back is not None:
            palette.setColor(QPalette.Window, colors.to_qcolor(back))
        widget.setPalette(palette if back is not None or fore is not None else QPalette())
        widget.setAutoFillBackground(back is not None)

    _apply_BackColor = _apply_ForeColor = _apply_colors


# --- FontComboBox ---------------------------------------------------------------------------------

_FONT_FILTERS = (QFontComboBox.AllFonts, QFontComboBox.ScalableFonts,
                 QFontComboBox.NonScalableFonts, QFontComboBox.MonospacedFonts,
                 QFontComboBox.ProportionalFonts)


class FontComboBox(Control):
    """A drop-down list of the fonts, each drawn in its own font (the module's
    documentation)."""

    TypeName = "FontComboBox"
    DefaultSize = (185, 25)
    Events = ("Click", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp")
    _qss_type = "QFontComboBox"
    Properties = (
        *_geometry(*DefaultSize),
        P("FontFilters", "enum", 0,
          enum_choices("All", "Scalable", "Non-scalable", "Monospaced", "Proportional"),
          description="Which fonts are listed"),
        P("FontName", "font", None,
          description="The chosen font; unset = the system's font; choosing one fires Click"),
        *_COLORS, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_quiet"] = True  # (its first font is no Click)
        widget = QFontComboBox(parent)
        self.__dict__["_quiet"] = False
        return widget

    def _connect_signals(self):
        self._widget.currentFontChanged.connect(self._on_font_changed)

    def _on_font_changed(self, _font):
        if not self._quiet:
            self._fire("Click")

    def _apply_font(self, _=None):
        pass  # (FontName is the font chosen, not the control's own)

    def _apply_FontFilters(self, v):
        self.__dict__["_quiet"] = True
        try:
            self._widget.setFontFilters(_FONT_FILTERS[int(v) if 0 <= int(v) <= 4 else 0])
        finally:
            self.__dict__["_quiet"] = False

    def _read_FontName(self):
        return self._widget.currentFont().family()

    def _apply_FontName(self, v):
        if v:  # (unset: the list starts at the system's font, as Qt chooses it)
            self._widget.setCurrentFont(QFont(v))

    @property
    def ListCount(self) -> int:
        """How many fonts are listed."""
        return self._widget.count()

    @property
    def List(self) -> list[str]:
        """The fonts listed (their names)."""
        return [self._widget.itemText(i) for i in range(self._widget.count())]


# --- HotKey -----------------------------------------------------------------------------------

class HotKey(_InnerEdits, Control):
    """A box that records the shortcut pressed in it (the module's documentation)."""

    TypeName = "HotKey"
    DefaultEvent = "Change"
    DefaultSize = (161, 25)
    Events = ("Change", "GotFocus", "LostFocus", "MouseDown", "MouseMove", "MouseUp")
    _qss_type = "QLineEdit"
    Properties = (
        *_geometry(*DefaultSize),
        P("MaxKeys", "int", 1,
          description="How many key presses one shortcut has (1 to 4: Ctrl+K, Ctrl+C is two)"),
        P("Keys", "str", "",
          description="The shortcut, as text (e.g. Ctrl+Shift+S); pressing keys in it records "
                      "a new one and fires Change"),
        P("ClearButton", "bool", False, description="A button in the box that clears it"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        return QKeySequenceEdit(parent)

    def _inner(self):
        return self._widget.findChild(QLineEdit)

    def _on_qt_event(self, watched, event):
        if event.type() in (QEvent.FocusIn, QEvent.FocusOut) and watched is not self._widget:
            return Control._on_qt_event(self, self._widget, event)  # (the focus is its editor's)
        return super()._on_qt_event(watched, event)

    def _connect_signals(self):
        self._widget.keySequenceChanged.connect(lambda *_: self._fire("Change"))

    def _apply_MaxKeys(self, v):
        if hasattr(self._widget, "setMaximumSequenceLength"):  # (Qt 6.5)
            self._widget.setMaximumSequenceLength(max(1, min(int(v), 4)))

    def _read_Keys(self):
        return self._widget.keySequence().toString(QKeySequence.PortableText)

    def _apply_Keys(self, v):
        self._widget.setKeySequence(QKeySequence.fromString(v or "", QKeySequence.PortableText))

    def _apply_ClearButton(self, v):
        if hasattr(self._widget, "setClearButtonEnabled"):  # (Qt 6.4)
            self._widget.setClearButtonEnabled(bool(v))

    def _first(self):
        sequence = self._widget.keySequence()
        return sequence[0] if not sequence.isEmpty() else None

    @property
    def KeyCode(self) -> int:
        """The key of the (first) shortcut, as KeyDown's KeyCode (vpKeyS...); 0 if none."""
        first = self._first()
        return vp_key_code(first.key()) if first is not None else 0

    @property
    def Shift(self) -> int:
        """Its modifiers, as KeyDown's Shift (vpShiftMask + vpCtrlMask + vpAltMask)."""
        first = self._first()
        return vp_shift(first.keyboardModifiers()) if first is not None else 0

    def Clear(self) -> None:
        """No shortcut (fires Change)."""
        self._widget.clear()


# --- data binding, registration ------------------------------------------------------------------

def _spin_value(control, value):
    if value is None or value == "":
        return control.Min
    try:
        return float(value)
    except (TypeError, ValueError):
        return control.Min


def _dt_saved(control, shown, original):
    if control._values.get("Format") in (0, 1):  # a date: saved as one
        return shown.date().isoformat()
    if control._values.get("Format") == 2 and isinstance(original, str) and len(original) <= 8:
        return shown.time().isoformat(timespec="seconds")
    return shown.isoformat(sep=" ", timespec="seconds")


def _dt_show(control, value):
    try:
        moment = as_datetime(_as_text(value) if isinstance(value, (bytes, int, float)) else value)
    except ValueError:
        moment = None
    if moment is not None:
        control.Value = moment


BINDINGS.update({
    "SpinBox": (lambda c: c.Value, lambda c, v: setattr(c, "Value", _spin_value(c, v)),
                lambda c, shown, original: shown),
    "DTPicker": (lambda c: c.Value, _dt_show, _dt_saved),
})

_TYPES = (SpinBox, DTPicker, MonthView, Dial, LCDNumber, FontComboBox, HotKey)
for _cls in _TYPES:
    _add_validation(_cls)
    _add_mouse_members(_cls)
for _cls in (SpinBox, DTPicker):
    _add_binding(_cls, grid=False)
# The Toolbox: after the other controls (Menu stays last)
for _cls in _TYPES:
    CONTROL_TYPES[_cls.TypeName] = _cls
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
