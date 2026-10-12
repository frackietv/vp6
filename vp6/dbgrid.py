"""The ``DBGrid``: a grid bound to a Data control, showing and editing all
the records of its Recordset.

    self.dtaPets = Data(self, DatabaseName='pets.db', RecordSource='pets', ...)
    self.grdPets = DBGrid(self, DataSource='dtaPets', AllowAddNew=True, ...)

* Its columns are the Recordset's fields, or those listed in ``Columns``
  (set in the designer: one per line, ``Caption|DataField|Width|NumberFormat``
  with ``hidden`` at the end for a hidden one). At run time ``Columns(i)``
  (from 0) has ``Caption``, ``DataField``, ``Width``, ``Visible`` and
  ``NumberFormat`` (Python's format: ``",.2f"``, ``"03d"``, ``"%"``).
* Choosing a row goes to that record (the Data control's bound controls show
  it), and moving the Data control's record chooses its row. ``Row`` and
  ``Col`` are the current cell (from 0), ``Bookmark`` the current record
  (as the Recordset's), ``Text`` the current cell's text.
* With ``AllowUpdate`` a cell is edited by typing or double-clicking: the
  record is saved when the cell is done. ``BeforeUpdate`` comes first
  (returning True cancels the change), ``AfterUpdate`` after.
  ``AllowAddNew`` adds an empty last row: typing in it adds a record.
  ``AllowDelete``: Delete removes the selected rows' records.
* The rows are read from the Recordset as they are shown (a model, not a
  cell for each value), so large tables stay fast.
"""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from ._props import P
from .app import report_runtime_error
from .controls import (_COLORS, _COMMON, _FONT, CONTROL_TYPES, EVENT_ARGS, Control,
                       _add_mouse_members, _add_validation, _geometry)
from .data import ACTION_BOOKMARK, _add_binding, _as_text

EVENT_ARGS.update({"BeforeUpdate": "", "AfterUpdate": "", "BeforeDelete": ""})


def parse_db_column(line: str) -> dict:
    """A DBGrid column as the designer writes it: Caption|DataField|Width|
    NumberFormat|hidden."""
    parts = [part.strip() for part in str(line).split("|")]
    hidden = any(part.casefold() == "hidden" for part in parts[2:])
    parts = parts[:2] + [part for part in parts[2:] if part.casefold() != "hidden"]
    parts += [""] * (4 - len(parts))
    caption, field, width, number_format = parts[:4]
    return {"Caption": caption, "DataField": field or caption,
            "Width": int(width) if width.isdigit() else 0, "NumberFormat": number_format,
            "Visible": not hidden}


class DBColumn:
    """One column of a DBGrid (``DBGrid1.Columns(0)``)."""

    def __init__(self, grid: "DBGrid", caption: str, field: str, width: int = 0,
                 number_format: str = "", visible: bool = True):
        self._grid = grid
        self._caption, self._field = caption, field
        self._width, self._format, self._visible = width, number_format, visible

    def __repr__(self):
        return f"<DBColumn {self._caption!r}>"

    @property
    def Index(self) -> int:
        return self._grid._columns.index(self)

    @property
    def Caption(self) -> str:
        return self._caption

    @Caption.setter
    def Caption(self, value):
        self._caption = str(value)
        self._grid._model.headerDataChanged.emit(Qt.Horizontal, self.Index, self.Index)

    @property
    def DataField(self) -> str:
        return self._field

    @DataField.setter
    def DataField(self, value):
        self._field = str(value)
        self._grid._model.reset()

    @property
    def Width(self) -> int:
        return self._grid._widget.columnWidth(self.Index)

    @Width.setter
    def Width(self, value):
        self._width = int(value)
        self._grid._widget.setColumnWidth(self.Index, self._width)

    @property
    def Visible(self) -> bool:
        return self._visible

    @Visible.setter
    def Visible(self, value):
        self._visible = bool(value)
        self._grid._widget.setColumnHidden(self.Index, not self._visible)

    @property
    def NumberFormat(self) -> str:
        """How numbers are shown: Python's format spec (",.2f", "05d", ".1%")."""
        return self._format

    @NumberFormat.setter
    def NumberFormat(self, value):
        self._format = str(value)
        self._grid._model.refresh()

    def _text(self, value) -> str:
        if self._format and isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return format(value, self._format)
            except (ValueError, TypeError):
                pass
        return _as_text(value)


class _Columns:
    """DBGrid.Columns: ``Columns(0)`` or by DataField, ``Count``, iteration."""

    def __init__(self, grid: "DBGrid"):
        self._grid = grid

    def __call__(self, index) -> DBColumn:
        columns = self._grid._columns
        if isinstance(index, str):
            for column in columns:
                if column._field.casefold() == index.casefold() or column._caption == index:
                    return column
            raise KeyError(f"DBGrid '{self._grid.Name}' has no column {index!r}")
        index = int(index)
        if not 0 <= index < len(columns):
            raise IndexError(f"DBGrid '{self._grid.Name}' has no column {index} "
                             f"(0 to {len(columns) - 1})")
        return columns[index]

    Item = __getitem__ = __call__

    def __iter__(self):
        return iter(list(self._grid._columns))

    def __len__(self):
        return len(self._grid._columns)

    @property
    def Count(self) -> int:
        return len(self._grid._columns)


class _RecordModel(QAbstractTableModel):
    """The Recordset's records, read as they are shown."""

    def __init__(self, grid: "DBGrid"):
        super().__init__()
        self._grid = grid

    def _rs(self):
        data = self._grid._data
        return data._recordset if data is not None else None

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        rs = self._rs()
        count = len(rs._records) if rs is not None else 0
        return count + (1 if self._grid._adding_row() else 0)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._grid._columns)

    def _value(self, row: int, column: DBColumn):
        rs = self._rs()
        if rs is None or row >= len(rs._records):
            return None
        try:
            return rs._records[row].values[rs._index_of(column._field)]
        except KeyError:
            return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        column = self._grid._columns[index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            value = self._value(index.row(), column)
            if role == Qt.EditRole:
                return "" if value is None else str(value)
            return column._text(value)
        if role == Qt.TextAlignmentRole:
            value = self._value(index.row(), column)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            columns = self._grid._columns
            return columns[section]._caption if section < len(columns) else None
        rs = self._rs()
        return "*" if rs is not None and section >= len(rs._records) else ""

    def flags(self, index):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self._grid._values.get("AllowUpdate", True) or (
                self._grid._adding_row() and index.row() == self.rowCount() - 1):
            flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        return self._grid._save_cell(index.row(), self._grid._columns[index.column()], value)

    def reset(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def refresh(self) -> None:
        if self.rowCount() and self.columnCount():
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(self.rowCount() - 1, self.columnCount() - 1))


def _typed(text: str, original):
    """A cell's new text as a value of the original's type where it can be."""
    if text == "" and not isinstance(original, str):
        return None
    if isinstance(original, bool):
        return text.strip().lower() in ("1", "-1", "true", "yes")
    for kind in (int, float):
        if isinstance(original, kind) or original is None:
            try:
                return kind(text)
            except ValueError:
                continue
    return text


class DBGrid(Control):
    """A grid bound to a Data control's records (the module's documentation)."""

    TypeName = "DBGrid"
    DefaultEvent = "RowColChange"
    DefaultSize = (329, 161)
    Events = ("RowColChange", "BeforeUpdate", "AfterUpdate", "BeforeDelete", "Click",
              "DblClick", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp", "MouseDown",
              "MouseMove", "MouseUp")
    _qss_type = "QTableView"
    _design_values = ("Columns",)  # (the designer's lines; at run time a collection)
    Properties = (
        *_geometry(*DefaultSize),
        P("Columns", "list", [],
          description="Its columns, one per line: Caption|DataField|Width|NumberFormat, and "
                      "|hidden for a hidden one; empty = every field of the Recordset"),
        P("AllowUpdate", "bool", True, description="Cells can be edited (saved to the records)"),
        P("AllowAddNew", "bool", False,
          description="An empty row at the end: typing in it adds a record"),
        P("AllowDelete", "bool", False,
          description="Delete removes the selected rows' records"),
        P("RecordSelectors", "bool", True, description="A column of row headers at the left"),
        P("ColumnHeaders", "bool", True, description="The columns' captions along the top"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_data=None, _columns=[], _syncing=False)
        view = QTableView(parent)
        model = _RecordModel(self)
        self.__dict__["_model"] = model
        view.setModel(model)
        view.setSelectionBehavior(QAbstractItemView.SelectItems)
        view.verticalHeader().setDefaultSectionSize(22)
        view.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        view.horizontalHeader().setStretchLastSection(True)
        return view

    def _event_targets(self):
        return [self._widget, self._widget.viewport()]

    def _connect_signals(self):
        selection = self._widget.selectionModel()
        selection.currentChanged.connect(self._on_current_changed)

    # -- the Data control's records ------------------------------------------------------------
    def _data_fill(self, data) -> None:
        """The records changed (opened, added, saved, deleted): show them."""
        self.__dict__["_data"] = data
        rs = data._recordset
        fields = list(rs._columns) if rs is not None else []
        old = [(c._caption, c._field) for c in self._columns]
        self._make_columns(fields)
        if old == [(c._caption, c._field) for c in self._columns] and \
                self.__dict__.get("_shown_rows") == self._model.rowCount():
            self._model.refresh()  # (the same shape: no reset, an editor stays)
        else:
            self._model.reset()
            self._apply_widths()
        self.__dict__["_shown_rows"] = self._model.rowCount()
        self._data_sync(data)

    def _make_columns(self, fields: list[str]) -> None:
        lines = self._values.get("Columns") or []
        if lines:
            specs = [parse_db_column(line) for line in lines]
        else:
            specs = [{"Caption": f, "DataField": f, "Width": 0, "NumberFormat": "",
                      "Visible": True} for f in fields]
        old = {c._field: c for c in self._columns}
        columns = []
        for spec in specs:
            column = old.get(spec["DataField"])
            if column is None or lines:
                column = DBColumn(self, spec["Caption"], spec["DataField"], spec["Width"],
                                  spec["NumberFormat"], spec["Visible"])
            columns.append(column)
        self.__dict__["_columns"] = columns

    def _apply_widths(self) -> None:
        view = self._widget
        for index, column in enumerate(self._columns):
            if column._width:
                view.setColumnWidth(index, column._width)
            view.setColumnHidden(index, not column._visible)

    def _data_sync(self, data) -> None:
        """The Data control's record moved: choose its row."""
        rs = data._recordset
        if rs is None:
            return
        view = self._widget
        row = rs._pos if rs._has_current() else -1
        if row < 0 or view.currentIndex().row() == row:
            return
        self.__dict__["_syncing"] = True
        try:
            view.setCurrentIndex(self._model.index(row, max(view.currentIndex().column(), 0)))
        finally:
            self.__dict__["_syncing"] = False

    def _adding_row(self) -> bool:
        data = self._data
        return bool(self._values.get("AllowAddNew")) and data is not None and \
            data._recordset is not None and data._recordset.Updatable

    def _on_current_changed(self, current, previous):
        if self._syncing or not current.isValid():
            return
        data = self._data
        if current.row() != previous.row() and data is not None:
            rs = data._recordset
            if rs is not None and current.row() < len(rs._records):
                data._grid_moved(current.row())
        self._fire("RowColChange")

    # -- editing -------------------------------------------------------------------------------
    def _save_cell(self, row: int, column: DBColumn, text) -> bool:
        data = self._data
        rs = data._recordset if data is not None else None
        if rs is None or not rs.Updatable:
            return False
        adding = row >= len(rs._records)
        try:
            index = rs._index_of(column._field)
            if self._fire("BeforeUpdate") is True:
                return False
            if adding:
                rs.AddNew()
                rs[index] = _typed(str(text), None)
            else:
                if rs._pos != row or not rs._has_current():
                    if not rs._go(lambda: row, ACTION_BOOKMARK):  # (False: Validate kept it)
                        return False
                original = rs._records[row].values[index]
                value = _typed(str(text), original)
                if value == original:
                    return False
                rs[index] = value
            rs.Update()
        except (sqlite3.Error, PermissionError, RuntimeError, KeyError) as exc:
            if rs._edit_mode:
                rs.CancelUpdate()
            data._report(exc) if data is not None else report_runtime_error(exc)
            return False
        self._fire("AfterUpdate")
        return True

    def _on_qt_event(self, watched, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete and \
                self._values.get("AllowDelete") and not self._design_mode and \
                self._widget.state() != QAbstractItemView.EditingState:
            self._delete_selected()
            return True
        return super()._on_qt_event(watched, event)

    def _delete_selected(self) -> None:
        data = self._data
        rs = data._recordset if data is not None else None
        if rs is None:
            return
        rows = sorted({index.row() for index in self._widget.selectionModel().selectedIndexes()
                       if index.row() < len(rs._records)}, reverse=True)
        if not rows or self._fire("BeforeDelete") is True:
            return
        records = [rs._records[row] for row in rows]
        try:
            for record in records:
                if record in rs._records:
                    rs.Bookmark = record
                    rs.Delete()
            if rs._records:
                rs.Move(0, rs._records[min(rows[-1], len(rs._records) - 1)])
        except (sqlite3.Error, PermissionError, RuntimeError) as exc:
            data._report(exc)

    # -- properties ---------------------------------------------------------------------------
    def _apply_Columns(self, v):
        data = self._data
        rs = data._recordset if data is not None else None
        self._make_columns(list(rs._columns) if rs is not None else [])
        self._model.reset()
        self._apply_widths()

    def _apply_AllowUpdate(self, v):
        self._widget.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed if v or self._values.get("AllowAddNew")
            else QAbstractItemView.NoEditTriggers)

    def _apply_AllowAddNew(self, v):
        self._apply_AllowUpdate(self._values.get("AllowUpdate", True))
        self._model.reset()

    def _apply_RecordSelectors(self, v):
        self._widget.verticalHeader().setVisible(bool(v))

    def _apply_ColumnHeaders(self, v):
        self._widget.horizontalHeader().setVisible(bool(v))

    # -- run time -------------------------------------------------------------------------------
    @property
    def Columns(self) -> _Columns:
        return _Columns(self)

    @Columns.setter
    def Columns(self, lines):
        """In the designer (and InitializeComponent): the columns as lines."""
        self._set_prop("Columns", lines)

    @property
    def Row(self) -> int:
        """The current row (from 0; -1 if none); setting it chooses that record."""
        return self._widget.currentIndex().row()

    @Row.setter
    def Row(self, value):
        self._widget.setCurrentIndex(self._model.index(int(value), max(self.Col, 0)))

    @property
    def Col(self) -> int:
        """The current column (from 0; -1 if none)."""
        return self._widget.currentIndex().column()

    @Col.setter
    def Col(self, value):
        self._widget.setCurrentIndex(self._model.index(max(self.Row, 0), int(value)))

    @property
    def Text(self) -> str:
        """The current cell's text."""
        index = self._widget.currentIndex()
        return self._model.data(index) or "" if index.isValid() else ""

    @property
    def Bookmark(self):
        """The current row's record (as Recordset.Bookmark); setting it goes there."""
        data = self._data
        rs = data._recordset if data is not None else None
        row = self.Row
        return rs._records[row] if rs is not None and 0 <= row < len(rs._records) else None

    @Bookmark.setter
    def Bookmark(self, value):
        data = self._data
        if data is not None and data._recordset is not None:
            data._recordset.Bookmark = value

    @property
    def VisibleRows(self) -> int:
        """How many rows fit in it."""
        view = self._widget
        return max(1, view.viewport().height() // max(view.verticalHeader().defaultSectionSize(),
                                                      1))

    def Refresh(self) -> None:
        self._model.refresh()


_add_validation(DBGrid)
_add_mouse_members(DBGrid)
_add_binding(DBGrid, grid=True)
CONTROL_TYPES["DBGrid"] = DBGrid  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
