"""Data-bound controls: VB's ``Data`` control, its ``Recordset``, and the
``DataSource`` and ``DataField`` of the controls that show a record.

A ``Data`` control opens a SQLite database (Python's own ``sqlite3``) and a
set of its records, and shows one record at a time in the controls bound to
it; its arrow buttons go to the first, previous, next and last record::

    self.dtaPets = Data(self, DatabaseName='pets.db', RecordSource='pets', ...)
    self.txtName = TextBox(self, DataSource='dtaPets', DataField='Name', ...)

* ``DatabaseName`` is the database file (relative to the form's folder);
  ``RecordSource`` a table's name or a ``SELECT``. They are opened after
  Form_Load (so Form_Load can make the database), or when ``Recordset`` is
  first used; after changing them, ``Refresh()`` opens them again.
* The bound controls: TextBox, Label, CheckBox, ComboBox, ListBox,
  RichTextBox, CodeBox and MarkdownBox show the field's value; Image and PictureBox a
  picture kept in it (a BLOB, e.g. a PNG); a FlexGrid bound to a Data
  control (DataSource only) shows all its records, and choosing a row there
  goes to that record. ``DataChanged`` tells whether the user changed the
  value shown.
* Moving to another record first saves what was changed: the ``Validate
  (Action, Save)`` event comes before (Action: vpDataActionMoveNext...; Save:
  whether something was changed); returning ``vpDataActionCancel`` (or True)
  from it stays on the record. ``Reposition`` comes after. ``Error
  (Description)`` reports a database that can't be opened or a record that
  can't be saved (unhandled: a run-time error).
* ``EOFAction`` and ``BOFAction``: what the next and previous buttons do at the
  ends: stay on the last (first) record, go past it (EOF, BOF), or, past the
  last, start a new record (``vpEOFActionAddNew``).
* ``ReadOnly``: nothing is saved. ``UpdateRecord()`` saves the bound controls'
  values now; ``UpdateControls()`` shows the record again (dropping changes).

The ``Recordset`` is DAO's: ``MoveFirst``, ``MoveLast``, ``MoveNext``,
``MovePrevious``, ``Move``, ``BOF``, ``EOF``, ``RecordCount``,
``AbsolutePosition``, ``Bookmark``, ``Fields`` (``rs("Name")`` and
``rs["Name"]`` are a field's value; ``rs["Name"] = x`` sets it), ``AddNew``,
``Edit``, ``Update``, ``CancelUpdate``, ``EditMode``, ``Delete`` (then move
to another record, as in VB), ``FindFirst`` / ``FindLast`` / ``FindNext`` /
``FindPrevious`` with a SQL condition (``"Name LIKE 'B%'"``) and ``NoMatch``,
``Requery``. A table, or a ``SELECT`` from one table, can be changed; other
queries are read-only (``Updatable``).

``OpenDatabase(Name)`` and ``CreateDatabase(Name)`` give a ``Database``:
``Execute(SQL, *Params)``, ``OpenRecordset(Source)``, ``Close()``. A Picture
given as a value is kept as a PNG.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPolygonF
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QWidget

from . import markdown  # noqa: F401  (MarkdownBox: a control type before the bindings)
from ._props import P, enum_choices
from .app import report_runtime_error
from .controls import (_COLORS, _FONT, CONTROL_TYPES, EVENT_ARGS, Control, _geometry,
                       resolve_path)
from .picture import Picture, is_picture

EVENT_ARGS.update({"Reposition": ""})

# Validate's Action (constants.vpDataAction...)
ACTION_CANCEL, ACTION_MOVE_FIRST, ACTION_MOVE_PREVIOUS, ACTION_MOVE_NEXT, ACTION_MOVE_LAST, \
    ACTION_ADD_NEW, ACTION_UPDATE, ACTION_DELETE, ACTION_FIND, ACTION_BOOKMARK, ACTION_CLOSE, \
    ACTION_UNLOAD = range(12)
EDIT_NONE, EDIT_IN_PROGRESS, EDIT_ADD = 0, 1, 2  # Recordset.EditMode (vpEdit...)

_KEY = "__vp6_rowid"  # the record's rowid, selected with it
_TABLE_NAME = r'(?:"(?:[^"]|"")+"|\[[^\]]+\]|`[^`]+`|[A-Za-z_]\w*)'
_TABLE = re.compile(rf"^\s*({_TABLE_NAME})\s*;?\s*$")
_SELECT = re.compile(rf"^\s*select\s+(?P<columns>.+?)\s+from\s+(?P<table>{_TABLE_NAME})"
                     r"(?P<rest>\s+(?:where|order\s+by|limit)\b.*?)?\s*;?\s*$", re.I | re.S)
_NOT_ONE_TABLE = re.compile(r"\b(?:join|union|group\s+by|intersect|except|distinct)\b", re.I)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _unquote(name: str) -> str:
    if name[:1] in "\"[`":
        return name[1:-1].replace('""', '"') if name[0] == '"' else name[1:-1]
    return name


def _no_record() -> RuntimeError:
    return RuntimeError("No current record.")


def picture_bytes(picture) -> bytes:
    """A Picture as PNG bytes (how a picture is kept in a field)."""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    picture._image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _stored(value):
    """A value as the database keeps it: a Picture as a PNG."""
    return picture_bytes(value) if is_picture(value) and not isinstance(value, str) else value


# --- Database -------------------------------------------------------------------------------

class Database:
    """An open SQLite database (DAO's Database): ``OpenDatabase(Name)`` or
    ``CreateDatabase(Name)``; a Data control's ``Database``."""

    def __init__(self, Name: str, ReadOnly: bool = False, _create: bool = False):
        path = os.path.abspath(str(Name))
        if _create:
            if os.path.exists(path):
                raise FileExistsError(f"Database '{Name}' already exists")
            mode = "rwc"
        else:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Couldn't find the database '{Name}'")
            mode = "ro" if ReadOnly else "rw"
        self._conn = sqlite3.connect(f"{Path(path).as_uri()}?mode={mode}", uri=True,
                                     isolation_level=None)  # (each change saved at once)
        self._name = path
        self._read_only = bool(ReadOnly)
        self.RecordsAffected = 0

    def __repr__(self):
        return f"<Database {self._name}>"

    @property
    def Name(self) -> str:
        """The database file's full path."""
        return self._name

    @property
    def ReadOnly(self) -> bool:
        """Opened for reading only."""
        return self._read_only

    def _check(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError(f"Database '{self._name}' is closed")
        return self._conn

    def Execute(self, SQL: str, *Params) -> int:
        """Run a SQL statement (CREATE, INSERT, UPDATE, DELETE...), its ``?``
        filled from Params in order (a Picture as a PNG); several statements
        separated by ``;`` when there are no Params. Returns (and sets)
        RecordsAffected."""
        conn = self._check()
        try:
            cursor = conn.execute(SQL, [_stored(p) for p in Params])
        except sqlite3.ProgrammingError as exc:
            if Params or "one statement" not in str(exc):
                raise
            before = conn.total_changes  # (several statements)
            conn.executescript(SQL)
            self.RecordsAffected = conn.total_changes - before
        else:
            self.RecordsAffected = max(cursor.rowcount, 0)
        return self.RecordsAffected

    def OpenRecordset(self, Source: str, ReadOnly: bool = False) -> "Recordset":
        """The records of a table or a SELECT, at the first one."""
        return Recordset(self, Source, ReadOnly)

    def Close(self) -> None:
        """Close the database (its Recordsets can't be used any more)."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def OpenDatabase(Name: str, ReadOnly: bool = False) -> Database:
    """Open a SQLite database file (FileNotFoundError if there is none)."""
    return Database(Name, ReadOnly)


def CreateDatabase(Name: str) -> Database:
    """Make a new, empty SQLite database file (FileExistsError if there is one)."""
    return Database(Name, _create=True)


def field_names(database: str, source: str) -> list[str]:
    """The fields of a RecordSource (for the designer); [] if it can't be read."""
    if not database or not source or not os.path.isfile(database):
        return []
    try:
        db = Database(database, ReadOnly=True)
    except (OSError, sqlite3.Error):
        return []
    try:
        match = _TABLE.match(source)
        sql = f"SELECT * FROM {match.group(1)}" if match else source
        return [d[0] for d in db._conn.execute(f"SELECT * FROM ({sql}) LIMIT 0").description]
    except sqlite3.Error:
        return []
    finally:
        db.Close()


# --- Recordset ------------------------------------------------------------------------------

class _Record:
    """A record: its values, and its rowid when it can be changed. It is
    also its Bookmark."""

    __slots__ = ("key", "values")

    def __init__(self, key, values):
        self.key = key
        self.values = list(values)

    def __repr__(self):
        return f"<Bookmark {self.key}>"


class Field:
    """A field of a Recordset's current record: ``Name``, ``Value`` (set: the
    record is being edited, saved by Update), ``OriginalValue``."""

    def __init__(self, recordset: "Recordset", index: int):
        self._rs = recordset
        self._index = index

    def __repr__(self):
        return f"<Field {self.Name}>"

    @property
    def Name(self) -> str:
        return self._rs._columns[self._index]

    @property
    def Value(self):
        """The value in the current record (being edited: the new one)."""
        rs = self._rs
        if rs._buffer is not None:
            return rs._buffer[self._index]
        return rs._current().values[self._index]

    @Value.setter
    def Value(self, value):
        self._rs._set_value(self._index, value)

    @property
    def OriginalValue(self):
        """The value saved in the database (None for a new record)."""
        rs = self._rs
        if rs._edit_mode == EDIT_ADD:
            return None
        return rs._current().values[self._index]


class _Fields:
    """A Recordset's Fields: ``Fields("Name")`` or ``Fields(0)``, ``Count``,
    iterating gives each Field."""

    def __init__(self, recordset: "Recordset"):
        self._rs = recordset

    def __call__(self, key) -> Field:
        return Field(self._rs, self._rs._index_of(key))

    __getitem__ = Item = __call__

    def __iter__(self):
        return iter([Field(self._rs, i) for i in range(len(self._rs._columns))])

    def __len__(self) -> int:
        return len(self._rs._columns)

    @property
    def Count(self) -> int:
        return len(self._rs._columns)


class Recordset:
    """Records of a table or a SELECT, one of them current (the module's
    documentation). ``Database.OpenRecordset`` makes one; a Data control's
    ``Recordset`` is its own, moving which shows the record in its bound
    controls."""

    def __init__(self, database: Database, Source: str, ReadOnly: bool = False,
                 _owner: "Data | None" = None):
        self._db = database
        self._source = str(Source)
        self._read_only = bool(ReadOnly) or database.ReadOnly
        self._owner = _owner
        self._table = None  # the table changes go to (None: read-only)
        self._refetch = ""  # SQL reading one record again by its rowid
        self._columns: list[str] = []
        self._records: list[_Record] = []
        self._pos = -1
        self._deleted = False  # the current record was deleted (until moving)
        self._edit_mode = EDIT_NONE
        self._buffer = None  # the values being edited
        self._dirty: set[int] = set()
        self.NoMatch = False
        self._query()
        self._pos = 0 if self._records else -1

    def __repr__(self):
        return f"<Recordset {self._source!r}: {len(self._records)} records>"

    # -- reading --------------------------------------------------------------------------------
    def _query(self) -> None:
        conn = self._db._check()
        source = self._source
        table = _TABLE.match(source)
        select = None if table else _SELECT.match(source)
        if table:
            name, columns, rest = table.group(1), "*", ""
        elif select and not _NOT_ONE_TABLE.search(source):
            name, columns, rest = select.group("table"), select.group("columns"), \
                select.group("rest") or ""
        else:
            name = None
        cursor = None
        if name is not None:  # with the rowid, so it can be changed
            try:
                cursor = conn.execute(f"SELECT rowid AS {_KEY}, {columns} FROM {name}{rest}")
                self._table = _unquote(name)
                self._refetch = f"SELECT rowid AS {_KEY}, {columns} FROM {name} WHERE rowid = ?"
            except sqlite3.Error:  # (a view, a table without rowid...)
                cursor = None
        if cursor is None:
            self._table = None
            cursor = conn.execute(f"SELECT * FROM {name}" if table else source)
            self._columns = [d[0] for d in cursor.description or ()]
            self._records = [_Record(None, row) for row in cursor.fetchall()]
            return
        self._columns = [d[0] for d in cursor.description][1:]
        self._records = [_Record(row[0], row[1:]) for row in cursor.fetchall()]

    def _check_open(self) -> None:
        if self._db._conn is None:
            raise RuntimeError("The Recordset's database is closed")

    def _index_of(self, key) -> int:
        if isinstance(key, int) and not isinstance(key, bool):
            if 0 <= key < len(self._columns):
                return key
        else:
            name = str(key)
            if name in self._columns:
                return self._columns.index(name)
            for i, column in enumerate(self._columns):  # (VB's names: any case)
                if column.casefold() == name.casefold():
                    return i
        raise KeyError(f"Item not found in this collection: no field {key!r} in "
                       f"{self._source!r}")

    def _has_current(self) -> bool:
        return not self._deleted and 0 <= self._pos < len(self._records)

    def _current(self) -> _Record:
        if not self._has_current():
            raise _no_record()
        return self._records[self._pos]

    @property
    def Fields(self) -> _Fields:
        """The fields: ``Fields("Name").Value``, ``Fields(0).Name``, ``Fields.Count``."""
        return _Fields(self)

    def __call__(self, key):
        """``rs("Name")``: the field's value in the current record."""
        return self.Fields(key).Value

    def __getitem__(self, key):
        return self.Fields(key).Value

    def __setitem__(self, key, value):
        self.Fields(key).Value = value

    @property
    def Name(self) -> str:
        """Its source: the table or SELECT."""
        return self._source

    @property
    def Updatable(self) -> bool:
        """Whether its records can be changed: a table, or a SELECT from one."""
        return self._table is not None and not self._read_only

    @property
    def RecordCount(self) -> int:
        return len(self._records)

    @property
    def BOF(self) -> bool:
        """Before the first record (also when there is none)."""
        return self._pos < 0 or not self._records

    @property
    def EOF(self) -> bool:
        """After the last record (also when there is none)."""
        return self._pos >= len(self._records) or not self._records

    @property
    def AbsolutePosition(self) -> int:
        """The current record's number, from 0; -1 when there is none."""
        return self._pos if self._has_current() else -1

    @AbsolutePosition.setter
    def AbsolutePosition(self, value):
        value = int(value)
        if not 0 <= value < len(self._records):
            raise IndexError(f"AbsolutePosition {value}: there are {len(self._records)} records")
        self._go(lambda: value, ACTION_BOOKMARK)

    @property
    def Bookmark(self):
        """The current record, to come back to: ``mark = rs.Bookmark`` ...
        ``rs.Bookmark = mark``."""
        return self._current()

    @Bookmark.setter
    def Bookmark(self, value):
        for index, record in enumerate(self._records):
            if record is value:
                self._go(lambda: index, ACTION_BOOKMARK)
                return
        raise ValueError("Not a valid bookmark (its record is gone, or it isn't one)")

    @property
    def EditMode(self) -> int:
        """vpEditNone, vpEditInProgress (Edit) or vpEditAdd (AddNew)."""
        return self._edit_mode

    # -- moving -----------------------------------------------------------------------------------
    def _go(self, target, action: int) -> bool:
        """Go to the record ``target()`` gives (after the Data control saved the
        one it leaves: the positions may have changed). False: Validate cancelled."""
        self._check_open()
        if self._owner is not None and not self._owner._leaving(action):
            return False
        self._edit_mode, self._buffer, self._dirty = EDIT_NONE, None, set()
        self._pos = max(-1, min(target(), len(self._records)))
        self._deleted = False
        if self._owner is not None:
            self._owner._arrived()
        return True

    def MoveFirst(self) -> None:
        self._go(lambda: 0 if self._records else -1, ACTION_MOVE_FIRST)

    def MoveLast(self) -> None:
        self._go(lambda: len(self._records) - 1, ACTION_MOVE_LAST)

    def MoveNext(self) -> None:
        """The next record; past the last one EOF is True (moving on from
        there is an error)."""
        if self._edit_mode != EDIT_ADD and not self._deleted and self.EOF:
            raise _no_record()
        self._go(lambda: self._pos if self._deleted else self._pos + 1, ACTION_MOVE_NEXT)

    def MovePrevious(self) -> None:
        """The previous record; before the first one BOF is True (moving back
        from there is an error)."""
        if self._edit_mode != EDIT_ADD and not self._deleted and self.BOF:
            raise _no_record()
        self._go(lambda: self._pos - 1, ACTION_MOVE_PREVIOUS)

    def Move(self, Rows: int, Start=None) -> None:
        """Move Rows records on (back if negative), from the current record or
        from the Start bookmark."""
        if Start is not None:
            base = next((i for i, r in enumerate(self._records) if r is Start), None)
            if base is None:
                raise ValueError("Not a valid bookmark")
        elif not self._has_current():
            raise _no_record()
        else:
            base = self._pos
        action = ACTION_MOVE_NEXT if Rows >= 0 else ACTION_MOVE_PREVIOUS
        self._go(lambda: base + int(Rows), action)

    def _find(self, criteria: str, start, step: int) -> bool:
        self._check_open()
        if not self._columns:
            self.NoMatch = True
            return False
        columns = ", ".join(f"? AS {_quote(name)}" for name in self._columns)
        sql = f"SELECT ({criteria}) FROM (SELECT {columns})"
        conn = self._db._conn
        index = start
        while 0 <= index < len(self._records):
            if conn.execute(sql, self._records[index].values).fetchone()[0]:
                found = index
                self.NoMatch = False
                record = self._records[found]
                self._go(lambda: self._records.index(record) if record in self._records
                         else found, ACTION_FIND)
                return True
            index += step
        self.NoMatch = True  # (the current record stays)
        return False

    def FindFirst(self, Criteria: str) -> None:
        """Go to the first record where Criteria (a SQL condition, e.g.
        ``"Age > 3 AND Name LIKE 'B%'"``) holds; NoMatch tells if there was none."""
        self._find(Criteria, 0, 1)

    def FindLast(self, Criteria: str) -> None:
        self._find(Criteria, len(self._records) - 1, -1)

    def FindNext(self, Criteria: str) -> None:
        self._find(Criteria, self._pos if self._deleted else self._pos + 1, 1)

    def FindPrevious(self, Criteria: str) -> None:
        self._find(Criteria, min(self._pos - 1, len(self._records) - 1), -1)

    def Requery(self) -> None:
        """Read the records again (changes made elsewhere), at the first one."""
        self._check_open()
        if self._owner is not None and not self._owner._leaving(ACTION_MOVE_FIRST):
            return
        self._query()
        self._edit_mode, self._buffer, self._dirty = EDIT_NONE, None, set()
        self._pos, self._deleted = (0 if self._records else -1), False
        if self._owner is not None:
            self._owner._rows_changed()
            self._owner._arrived()

    # -- changing -----------------------------------------------------------------------------
    def _check_updatable(self) -> None:
        self._check_open()
        if self._read_only:
            raise PermissionError(f"Recordset {self._source!r} is read-only")
        if self._table is None:
            raise PermissionError(f"Recordset {self._source!r} can't be changed (only a table, "
                                  "or a SELECT from one table, can)")

    def _set_value(self, index: int, value) -> None:
        self._check_updatable()
        if self._edit_mode == EDIT_NONE:
            self._start_edit()
        self._buffer[index] = value
        self._dirty.add(index)

    def _start_edit(self) -> None:
        self._buffer = list(self._current().values)
        self._dirty = set()
        self._edit_mode = EDIT_IN_PROGRESS

    def Edit(self) -> None:
        """Start changing the current record (setting a field's Value does too);
        Update saves it."""
        self._check_updatable()
        if self._edit_mode == EDIT_NONE:
            self._start_edit()

    def AddNew(self) -> None:
        """Start a new record (its fields empty); Update saves it, after the
        last record, and it becomes the current one."""
        self._check_updatable()
        if self._owner is not None:
            if not self._owner._leaving(ACTION_ADD_NEW):
                return
        elif self._edit_mode != EDIT_NONE:
            self.CancelUpdate()
        self._edit_mode = EDIT_ADD
        self._buffer = [None] * len(self._columns)
        self._dirty = set()
        if self._owner is not None:
            self._owner._arrived()

    def Update(self) -> None:
        """Save the record being edited or added (with a Data control: the
        bound controls' changes too, after its Validate)."""
        if self._owner is not None:
            if not self._owner._collect(ACTION_UPDATE):
                return
        if self._edit_mode == EDIT_NONE:
            raise RuntimeError("Update without AddNew or Edit.")
        self._write()
        if self._owner is not None:
            self._owner._arrived()

    def CancelUpdate(self) -> None:
        """Drop the changes of Edit or AddNew."""
        self._edit_mode, self._buffer, self._dirty = EDIT_NONE, None, set()
        if self._owner is not None:
            self._owner._arrived(reposition=False)

    def _write(self) -> None:
        """Save the record being edited or added; it is the current one."""
        self._check_updatable()
        conn = self._db._conn
        names = [self._columns[i] for i in sorted(self._dirty)]
        values = [_stored(self._buffer[i]) for i in sorted(self._dirty)]
        table = _quote(self._table)
        if self._edit_mode == EDIT_ADD:
            if names:
                cursor = conn.execute(
                    f"INSERT INTO {table} ({', '.join(_quote(n) for n in names)}) "
                    f"VALUES ({', '.join('?' * len(names))})", values)
            else:
                cursor = conn.execute(f"INSERT INTO {table} DEFAULT VALUES")
            row = conn.execute(self._refetch, (cursor.lastrowid,)).fetchone()
            self._records.append(_Record(row[0], row[1:]) if row else
                                 _Record(cursor.lastrowid, self._buffer))
            self._pos = len(self._records) - 1
        elif names:
            record = self._current()
            conn.execute(f"UPDATE {table} SET {', '.join(f'{_quote(n)} = ?' for n in names)} "
                         f"WHERE rowid = ?", [*values, record.key])
            row = conn.execute(self._refetch, (record.key,)).fetchone()
            if row:
                record.values = list(row[1:])
        self._edit_mode, self._buffer, self._dirty = EDIT_NONE, None, set()
        self._deleted = False
        if self._owner is not None:
            self._owner._rows_changed()

    def Delete(self) -> None:
        """Delete the current record. As in VB, there is then no current record
        until you move (MoveNext goes to the one after it)."""
        self._check_updatable()
        record = self._current()
        if self._owner is not None and not self._owner._leaving(ACTION_DELETE, save=False):
            return
        self._db._conn.execute(f"DELETE FROM {_quote(self._table)} WHERE rowid = ?",
                               (record.key,))
        self._records.remove(record)
        self._edit_mode, self._buffer, self._dirty = EDIT_NONE, None, set()
        self._deleted = True
        if self._owner is not None:
            self._owner._rows_changed()

    def Close(self) -> None:
        """Done with it (its Data control's database stays open)."""
        self._records, self._pos, self._deleted = [], -1, False
        self._edit_mode, self._buffer = EDIT_NONE, None


# --- the bound controls ---------------------------------------------------------------------

_NOT_SHOWN = object()  # DataChanged: never shown a record
_FORCED = object()  # DataChanged = True


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "(binary)"
    return str(value)


def _text_to_value(text: str, original):
    """What a control's text saves: empty is NULL unless the field held text."""
    if text == "" and not isinstance(original, str):
        return None
    return text


def _checked(value) -> int:
    if value is None:
        return 2  # vpGrayed: NULL
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("1", "-1", "true", "yes", "checked") else 0
    return 1 if value else 0


def _picture_of(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        image = QImage.fromData(bytes(value))
        return Picture(_image=image) if not image.isNull() else ""
    return value if is_picture(value) and not isinstance(value, str) else ""


def _picture_value(control, value):
    if is_picture(value) and not isinstance(value, str):
        return picture_bytes(value)
    if isinstance(value, str) and value:  # a file
        with open(resolve_path(control._form, value), "rb") as file:
            return file.read()
    return None


def _set_list(control, value) -> None:
    items = control.List
    text = _as_text(value)
    control.ListIndex = items.index(text) if text in items else -1


def _set_combo(control, value) -> None:
    widget = control._widget
    text = _as_text(value)
    if widget.isEditable():
        control.Text = text
    else:
        widget.setCurrentIndex(widget.findText(text))


# TypeName: (what it shows (control), show (control, value), what it saves (control, shown,
# original))
_TEXT = (lambda c: c.Text, lambda c, v: setattr(c, "Text", _as_text(v)),
         lambda c, shown, original: _text_to_value(shown, original))
BINDINGS = {
    "TextBox": _TEXT, "RichTextBox": _TEXT, "CodeBox": _TEXT, "MarkdownBox": _TEXT,
    "Label": (lambda c: c.Caption, lambda c, v: setattr(c, "Caption", _as_text(v)),
              lambda c, shown, original: _text_to_value(shown, original)),
    "CheckBox": (lambda c: c.Value, lambda c, v: setattr(c, "Value", _checked(v)),
                 lambda c, shown, original: None if shown == 2 else int(shown == 1)),
    "ComboBox": (lambda c: c.Text, _set_combo,
                 lambda c, shown, original: _text_to_value(shown, original)),
    "ListBox": (lambda c: c.Text, _set_list,
                lambda c, shown, original: _text_to_value(shown, original)),
    "Image": (lambda c: c.Picture, lambda c, v: setattr(c, "Picture", _picture_of(v)),
              lambda c, shown, original: _picture_value(c, shown)),
    "PictureBox": (lambda c: c.Picture, lambda c, v: setattr(c, "Picture", _picture_of(v)),
                   lambda c, shown, original: _picture_value(c, shown)),
}
BOUND_GRIDS = ("FlexGrid",)  # a whole Recordset: DataSource only

_DATA_SOURCE = P("DataSource", "str", "",
                 description="The Data control (its Name) whose current record it shows")
_DATA_FIELD = P("DataField", "str", "",
                description="The field of the Data control's record it shows (and saves "
                            "when changed)")
_GRID_SOURCE = P("DataSource", "str", "",
                 description="The Data control (its Name) whose records it shows; choosing a "
                             "row goes to that record")


def _data_source_property() -> property:
    def fget(self):
        return self._values.get("DataSource", "")

    def fset(self, value):
        if isinstance(value, Data):  # (VB's Set Text1.DataSource = Data1)
            value = value.Name
        self._set_prop("DataSource", value)

    return property(fget, fset, doc="VB property DataSource")


def _data_changed_property() -> property:
    def fget(self):
        """Whether the value shown was changed since the record was shown (it is
        saved when moving on); False keeps it from being saved."""
        shown = self.__dict__.get("_data_shown", _NOT_SHOWN)
        if shown is _NOT_SHOWN:
            return False
        if shown is _FORCED:
            return True
        current = BINDINGS[self.TypeName][0](self)
        return current is not shown if is_picture(shown) and not isinstance(shown, str) \
            else current != shown

    def fset(self, value):
        self.__dict__["_data_shown"] = _FORCED if value else BINDINGS[self.TypeName][0](self)

    return property(fget, fset, doc="Whether the bound value was changed")


def _data_control(control) -> "Data | None":
    name = control._values.get("DataSource", "")
    if not name or control._design_mode:
        return None
    for other in control._form._controls:
        if isinstance(other, Data) and other._name == name:
            return other
    return None


def _rebind(control, _=None) -> None:
    """DataSource or DataField changed at run time: show the record (or not)."""
    if control._design_mode:
        return
    if control.TypeName in BOUND_GRIDS:
        control.__dict__.pop("_data_follow", None)
    data = _data_control(control)
    if data is not None and data._recordset is not None:
        if control.TypeName in BOUND_GRIDS:
            data._fill_grid(control)
        else:
            data._show_control(control)


def _add_binding(cls, grid: bool) -> None:
    specs = (_GRID_SOURCE,) if grid else (_DATA_SOURCE, _DATA_FIELD)
    cls.Properties = tuple(cls.Properties) + specs
    cls._specs = {**cls._specs, **{spec.name: spec for spec in specs}}
    cls.DataSource = _data_source_property()
    cls._apply_DataSource = _rebind
    if not grid:
        cls.DataField = property(lambda self: self._values.get("DataField", ""),
                                 lambda self, value: self._set_prop("DataField", value),
                                 doc="VB property DataField")
        cls._apply_DataField = _rebind
        cls.DataChanged = _data_changed_property()


# --- the Data control -----------------------------------------------------------------------

class _NavButton(QToolButton):
    """One of the Data control's arrows: first, previous, next, last."""

    def __init__(self, kind: int, parent: QWidget):
        super().__init__(parent)
        self._kind = kind
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip(("First record", "Previous record", "Next record", "Last record")[kind])
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.palette().buttonText() if self.isEnabled()
                         else self.palette().mid())
        size = min(self.width(), self.height()) * 0.36
        cx, cy = self.width() / 2, self.height() / 2
        left = self._kind in (0, 1)
        bar = self._kind in (0, 3)
        x0 = cx - size / 2 + (size * 0.2 if bar and left else -size * 0.2 if bar else 0)
        if left:
            triangle = [QPointF(x0 + size, cy - size / 2), QPointF(x0 + size, cy + size / 2),
                        QPointF(x0, cy)]
        else:
            triangle = [QPointF(x0, cy - size / 2), QPointF(x0, cy + size / 2),
                        QPointF(x0 + size, cy)]
        painter.drawPolygon(QPolygonF(triangle))
        if bar:
            x = x0 - size * 0.35 if left else x0 + size + size * 0.1
            painter.drawRect(QRectF(x, cy - size / 2, max(1.5, size * 0.22), size))
        painter.end()


class _DataBar(QFrame):
    """The Data control: |< < Caption > >|."""

    def __init__(self, control: "Data", parent: QWidget):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.buttons = [_NavButton(kind, self) for kind in range(4)]
        self.caption = QLabel(self)
        self.caption.setContentsMargins(6, 0, 6, 0)
        self.caption.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout.addWidget(self.buttons[0])
        layout.addWidget(self.buttons[1])
        layout.addWidget(self.caption, 1)
        layout.addWidget(self.buttons[2])
        layout.addWidget(self.buttons[3])
        for kind, button in enumerate(self.buttons):
            button.clicked.connect(lambda _=False, k=kind: control._button(k))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        side = max(12, self.contentsRect().height())
        for button in self.buttons:
            button.setFixedWidth(side)


class Data(Control):
    """VB's Data control: a database's records, one at a time, shown in the
    controls bound to it (the module's documentation)."""

    TypeName = "Data"
    DefaultEvent = "Validate"
    DefaultSize = (241, 33)
    Events = ("Validate", "Reposition", "Error")
    EventArgs = {"Validate": "Action, Save", "Error": "Description"}
    _qss_type = "QLabel"  # (BackColor and ForeColor: the caption's)
    Properties = (
        P("Caption", "str", "", always=True, description="The text between the arrows"),
        *_geometry(*DefaultSize),
        P("DatabaseName", "file", "",
          description="The SQLite database file (relative to the form's folder)"),
        P("RecordSource", "str", "",
          description="Its records: a table's name, or a SELECT"),
        P("ReadOnly", "bool", False, description="Nothing is saved"),
        P("EOFAction", "enum", 0, enum_choices("Move Last", "EOF", "Add New"),
          description="What the next button does on the last record: stay there, go past it "
                      "(EOF), or start a new record"),
        P("BOFAction", "enum", 0, enum_choices("Move First", "BOF"),
          description="What the previous button does on the first record: stay there, or "
                      "go before it (BOF)"),
        *_COLORS, *_FONT,
        P("Enabled", "bool", True, description="Whether its buttons respond to the user"),
        P("Visible", "bool", True, description="Whether it is shown at run time (hidden, it "
                                               "still works: move with its Recordset)"),
        P("ToolTipText", "str", "", description="Text shown when the mouse rests on it"),
        P("Tag", "str", "", description="Free for your own use"),
        P("ZIndex", "int", 0, description="Stacking order among controls in the same "
                                          "container: higher values are drawn on top"),
    )

    def __init__(self, parent, Name: str = "", **props):
        self.__dict__.update(_db=None, _recordset=None, _opened=False, _syncing=False,
                             _arriving=False)
        super().__init__(parent, Name, **props)

    def _create_widget(self, parent):
        return _DataBar(self, parent)

    def _apply_Caption(self, v):
        self._widget.caption.setText(v)

    def _apply_colors(self, _=None):
        super()._apply_colors()
        back = self._values.get("BackColor")
        self._widget.caption.setAutoFillBackground(back is not None)

    _apply_BackColor = _apply_ForeColor = _apply_colors

    # -- opening ----------------------------------------------------------------------------------
    @property
    def Recordset(self) -> Recordset | None:
        """Its records (opened when first used, or after Form_Load); None in
        the designer or without DatabaseName and RecordSource. Setting it to
        another Recordset (``Database.OpenRecordset``) shows that one."""
        if not self._opened and not self._design_mode:
            self.Refresh()
        return self._recordset

    @Recordset.setter
    def Recordset(self, value):
        if not isinstance(value, Recordset):
            raise TypeError(f"Data '{self.Name}': the Recordset must be a Recordset, not "
                            f"{value!r}")
        if self._recordset is not None and not self._leaving(ACTION_CLOSE):
            return
        value._owner = self
        self.__dict__.update(_recordset=value, _opened=True)
        self._rows_changed()
        self._arrived()

    @property
    def Database(self) -> Database | None:
        """The open database (Execute, OpenRecordset...)."""
        if not self._opened and not self._design_mode:
            self.Refresh()
        return self._db

    def Refresh(self) -> None:
        """Open DatabaseName and RecordSource (again: after changing them, or
        to see changes made elsewhere), at the first record."""
        if self._design_mode:
            return
        if self._recordset is not None and not self._leaving(ACTION_CLOSE):
            return
        self._close()
        self.__dict__["_opened"] = True
        name, source = self._values.get("DatabaseName", ""), self._values.get("RecordSource", "")
        if name and source:
            try:
                db = Database(resolve_path(self._form, name), self._values.get("ReadOnly"))
                try:
                    recordset = Recordset(db, source, self._values.get("ReadOnly"), _owner=self)
                except sqlite3.Error:
                    db.Close()
                    raise
            except (OSError, sqlite3.Error) as exc:
                self._report(exc)
            else:
                self.__dict__.update(_db=db, _recordset=recordset)
        self._rows_changed()
        self._arrived()

    def _close(self) -> None:
        if self._db is not None:
            self._db.Close()
        self.__dict__.update(_db=None, _recordset=None)

    def _report(self, exc: BaseException) -> None:
        """Error(Description), or a run-time error when it isn't handled."""
        if self._handler("Error") is not None:
            self._fire("Error", str(exc))
        else:
            report_runtime_error(exc)

    def _form_loaded(self) -> None:
        if not self._opened:
            self.Refresh()

    def _form_unloaded(self) -> None:
        try:
            if self._recordset is not None:
                self._leaving(ACTION_UNLOAD)
        except Exception as exc:  # noqa: BLE001 - reported; the form still unloads
            report_runtime_error(exc)
        self._close()

    # -- the bound controls ---------------------------------------------------------------------
    def _bound(self) -> list[Control]:
        if not self._name:
            return []
        return [c for c in self._form._controls if c.TypeName in BINDINGS and
                c._values.get("DataSource") == self._name and c._values.get("DataField")]

    def _grids(self) -> list[Control]:
        if not self._name:
            return []
        return [c for c in self._form._controls if c.TypeName in BOUND_GRIDS and
                c._values.get("DataSource") == self._name]

    def _show_control(self, control) -> None:
        rs = self._recordset
        field = control._values.get("DataField", "")
        if not field:
            return
        if rs is None or (rs._buffer is None and not rs._has_current()):
            value = None
        else:
            value = rs.Fields(field).Value
        shown, show, _ = BINDINGS[control.TypeName]
        show(control, value)
        control.__dict__["_data_shown"] = shown(control)

    def _changed(self) -> list[Control]:
        return [c for c in self._bound() if c.DataChanged]

    def _validate(self, action: int) -> bool:
        """Validate(Action, Save); False: it cancelled (returned
        vpDataActionCancel or True)."""
        result = self._fire("Validate", action, bool(self._changed()))
        return not (result is True or (isinstance(result, int) and
                                       not isinstance(result, bool) and result == ACTION_CANCEL))

    def _collect(self, action: int | None) -> bool:
        """Validate(Action, Save) (unless ``action`` is None), then the changed
        bound controls' values into the record being edited. False: Validate
        cancelled."""
        if action is not None and not self._validate(action):
            return False
        rs = self._recordset
        changed = self._changed()  # (Validate may have set DataChanged = False)
        if not changed or rs is None or not rs.Updatable or rs._deleted or \
                (rs._buffer is None and not rs._has_current()):
            return True
        for control in changed:
            index = rs._index_of(control._values["DataField"])
            original = rs._buffer[index] if rs._buffer is not None else \
                rs._current().values[index]
            shown, _, value = BINDINGS[control.TypeName]
            rs._set_value(index, value(control, shown(control), original))
        return True

    def _leaving(self, action: int, save: bool = True) -> bool:
        """Before the current record changes: Validate, and save it (unless
        ``save`` is False). False: stay."""
        if self._arriving:
            return True
        rs = self._recordset
        if not save:
            return self._validate(action)
        if not self._collect(action):
            return False
        if rs is not None and rs._edit_mode != EDIT_NONE:
            if rs._edit_mode == EDIT_ADD and not rs._dirty:
                rs._edit_mode, rs._buffer = EDIT_NONE, None  # (an empty new record: dropped)
            else:
                rs._write()
        return True

    def _arrived(self, reposition: bool = True) -> None:
        """Show the current record in the bound controls; Reposition."""
        self.__dict__["_arriving"] = True  # (their Change events can't move it again)
        try:
            for control in self._bound():
                self._show_control(control)
            self._sync_grids()
        finally:
            self.__dict__["_arriving"] = False
        if reposition:
            self._fire("Reposition")

    def UpdateRecord(self) -> None:
        """Save the bound controls' values to the current record now (no Validate)."""
        rs = self.Recordset
        if rs is None:
            return
        self._collect(None)
        if rs._edit_mode != EDIT_NONE and (rs._edit_mode != EDIT_ADD or rs._dirty):
            rs._write()
        self._arrived(reposition=False)

    def UpdateControls(self) -> None:
        """Show the current record again in the bound controls (their changes
        dropped)."""
        if self.Recordset is not None:
            self._arrived(reposition=False)

    # -- bound grids ------------------------------------------------------------------------------
    def _rows_changed(self) -> None:
        for grid in self._grids():
            self._fill_grid(grid)

    def _fill_grid(self, grid) -> None:
        rs = self._recordset
        columns = rs._columns if rs is not None else []
        records = rs._records if rs is not None else []
        fr, fc = grid._frows, grid._fcols
        self.__dict__["_syncing"] = True
        try:
            table = grid._widget
            table.setUpdatesEnabled(False)
            grid.Rows = fr + len(records)
            grid.Cols = fc + max(len(columns), 0)
            if fr:
                for col, name in enumerate(columns):
                    grid._set_text(0, fc + col, name)
            for row, record in enumerate(records):
                for col, value in enumerate(record.values):
                    grid._set_text(fr + row, fc + col, _as_text(value))
            table.setUpdatesEnabled(True)
        finally:
            self.__dict__["_syncing"] = False
        grid.__dict__["_data_follow"] = lambda row, data=self: data._grid_moved(row)
        self._sync_grid(grid)

    def _sync_grids(self) -> None:
        for grid in self._grids():
            self._sync_grid(grid)

    def _sync_grid(self, grid) -> None:
        rs = self._recordset
        if rs is None or not rs._has_current():
            return
        table = grid._widget
        if table.currentRow() == rs._pos:
            return
        self.__dict__["_syncing"] = True
        try:
            table.setCurrentCell(rs._pos, max(table.currentColumn(), 0))
        finally:
            self.__dict__["_syncing"] = False

    def _grid_moved(self, row: int) -> None:
        """A row chosen in a bound grid: that record."""
        rs = self._recordset
        if self._syncing or self._arriving or rs is None or row == rs._pos and \
                rs._has_current():
            return
        if 0 <= row < len(rs._records):
            try:
                if not rs._go(lambda: row, ACTION_BOOKMARK):
                    self._sync_grids()  # (Validate kept the record: the grid too)
            except (sqlite3.Error, PermissionError, RuntimeError) as exc:
                self._report(exc)

    # -- the buttons ------------------------------------------------------------------------------
    def _button(self, kind: int) -> None:
        if self._design_mode:
            return
        rs = self.Recordset
        if rs is None:
            return
        try:
            adding = rs._edit_mode == EDIT_ADD
            count = len(rs._records)
            if kind == 0:
                rs.MoveFirst()
            elif kind == 3:
                rs.MoveLast()
            elif kind == 1:
                at_first = not adding and (rs._pos <= 0 and not rs._deleted or count == 0)
                if at_first and self._values.get("BOFAction", 0) == 0:
                    rs.MoveFirst()
                elif not rs.BOF or adding:
                    rs.MovePrevious()
            else:
                at_last = adding or rs._pos >= count - 1 and not (rs._deleted and
                                                                 rs._pos < count)
                action = self._values.get("EOFAction", 0)
                if at_last and action == 2 and rs.Updatable:
                    rs.AddNew()
                elif at_last and action == 0:
                    rs.MoveLast()
                elif not rs.EOF or adding:
                    rs.MoveNext()
        except (sqlite3.Error, PermissionError, RuntimeError) as exc:
            self._report(exc)


for _name in ("TextBox", "Label", "CheckBox", "ComboBox", "ListBox", "RichTextBox", "CodeBox",
              "MarkdownBox", "Image", "PictureBox"):
    _add_binding(CONTROL_TYPES[_name], grid=False)
for _name in BOUND_GRIDS:
    _add_binding(CONTROL_TYPES[_name], grid=True)

# The Toolbox: after the other controls (Menu stays last)
CONTROL_TYPES["Data"] = Data
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
