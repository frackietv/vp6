"""The Properties window: object combo, Alphabetic / Categorized tabs, property
grid and description pane.

Categorized (VB's) lists the properties under their categories (Appearance,
Behavior, Font, List, Misc, Position, Text: ``_props.category_of``), each a
heading row that collapses or expands its properties when clicked (and stays
so while the window shows other objects). The view chosen is remembered in
the IDE's settings."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIntValidator, QPalette, QPixmap, QIcon
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton, QSplitter, QTabBar, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .. import colors
from .._props import PropSpec, category_of
from ..formfile import format_value

_MIXED = object()


def _settings_value(key: str):
    from .theme import ide_settings

    return ide_settings().value(key)


def _set_settings_value(key: str, value) -> None:
    from .theme import ide_settings

    ide_settings().setValue(key, value)

INDEX_SPEC = PropSpec(
    "Index", "index", None,
    description="The control's number in a control array: controls sharing a (Name) are an "
                "array, told apart by Index, and their event handlers get Index first. "
                "Empty = not in an array.")


# Properties that are, at run time, a collection (StatusBar.Panels,
# TabStrip.Tabs, ImageList.ListImages, Toolbar.Buttons, ListView.ColumnHeaders and
# ListItems): lines of text in the
# designer, read from the object's _values
COLLECTION_KINDS = ("panels", "tabs", "images", "buttons", "columns", "listitems")


class TextListDialog(QDialog):
    """Edit a list of strings (ListBox.List) or multi-line text, one per line."""

    def __init__(self, title: str, text: str, parent=None, hint: str | None = None,
                 pictures_dir: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.edit = QPlainTextEdit(text)
        self.pictures_dir = pictures_dir
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if pictures_dir is not None:  # ImageList.ListImages: pick picture files
            add = buttons.addButton("Add Pictures…", QDialogButtonBox.ActionRole)
            add.clicked.connect(self._choose_pictures)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        if hint is None:
            hint = "One item per line:" if "List" in title else "Text:"
        label = QLabel(hint)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addWidget(self.edit)
        layout.addWidget(buttons)
        self.resize(320, 280)

    def _choose_pictures(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Pictures", self.pictures_dir,
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.ico *.svg);;All files (*)")
        self.add_pictures(paths)

    def add_pictures(self, paths) -> None:
        """Append a line per picture: its path (relative to the form's folder
        when inside it) and its file name as the key."""
        lines = [line for line in self.edit.toPlainText().split("\n") if line.strip()]
        for path in paths:
            relative = path
            try:
                if not os.path.relpath(path, self.pictures_dir).startswith(".."):
                    relative = os.path.relpath(path, self.pictures_dir)
            except ValueError:  # another drive (Windows)
                pass
            key = os.path.splitext(os.path.basename(path))[0]
            lines.append(f"{relative.replace(os.sep, '/')}|{key}")
        self.edit.setPlainText("\n".join(lines))


def _swatch(value) -> QIcon:
    pixmap = QPixmap(14, 14)
    pixmap.fill(colors.to_qcolor(value) if value is not None else QColor(0, 0, 0, 0))
    return QIcon(pixmap)


class PropertiesWindow(QWidget):
    objectSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.designer = None
        self.object_combo = QComboBox()
        self.object_combo.activated.connect(self._on_object_chosen)
        # VB's tabs: the properties alphabetically, or under their categories
        self.view_tabs = QTabBar()
        self.view_tabs.addTab("Alphabetic")
        self.view_tabs.addTab("Categorized")
        self.view_tabs.setExpanding(False)
        self.view_tabs.setDocumentMode(True)
        self.view_tabs.setCurrentIndex(1 if _settings_value("properties/view") ==
                                       "categorized" else 0)
        self.view_tabs.currentChanged.connect(self._on_view_changed)
        self.collapsed: set[str] = set()  # the categories collapsed
        self.table = QTableWidget(0, 2)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 110)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.currentCellChanged.connect(self._on_row_changed)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.description.setMinimumHeight(40)
        self.description.setFrameStyle(QLabel.Panel | QLabel.Sunken)
        self.description.setMargin(4)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.description)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([400, 50])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.object_combo)
        layout.addWidget(self.view_tabs)
        layout.addWidget(splitter)
        self._specs: list[PropSpec | str] = []  # a row's spec, or its category heading
        self._error_label = None

    # -- binding ------------------------------------------------------------------------
    def set_designer(self, designer) -> None:
        if self.designer is designer:
            return
        if self.designer is not None:
            for signal in (self.designer.selectionChanged, self.designer.designChanged):
                try:
                    signal.disconnect(self.refresh)
                except (RuntimeError, TypeError):
                    pass
        self.designer = designer
        if designer is not None:
            designer.selectionChanged.connect(self.refresh)
            designer.designChanged.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        designer = self.designer
        current_row = self.table.currentRow()
        self.table.setRowCount(0)
        self.object_combo.clear()
        if designer is None:
            self.description.clear()
            return
        objects = designer.selected_objects()
        self._objects = objects
        for name, type_name in designer.all_objects():
            self.object_combo.addItem(f"{name}  {type_name}", name)
        if len(objects) == 1:
            index = self.object_combo.findData(designer.object_name(objects[0]))
            self.object_combo.setCurrentIndex(index)
        else:
            self.object_combo.setCurrentIndex(-1)

        # Properties common to all selected objects, alphabetical like VB
        common = None
        for obj in objects:
            names = set(obj._specs)
            common = names if common is None else common & names
        specs = sorted((objects[0]._specs[n] for n in common or ()), key=lambda s: s.name)
        if len(objects) == 1:
            specs.insert(0, PropSpec("Name", "name", ""))
            supports_index = getattr(designer, "supports_index", None)
            if supports_index is not None and supports_index(objects[0]):
                specs.insert(1, INDEX_SPEC)  # right after (Name), like VB
        rows: list[PropSpec | str] = list(specs)
        if self.categorized():  # headings, then their properties (alphabetically)
            rows = []
            for category in sorted({category_of(spec) for spec in specs}):
                rows.append(category)
                rows += sorted((s for s in specs if category_of(s) == category),
                               key=lambda s: "" if s.name == "Name" else s.name)
        self._specs = rows
        self.table.clearSpans()
        self.table.setRowCount(len(rows))
        for row, spec in enumerate(rows):
            if isinstance(spec, str):
                self._add_heading(row, spec)
                continue
            label = QTableWidgetItem("(Name)" if spec.name == "Name" else spec.name)
            label.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, label)
            self.table.setCellWidget(row, 1, self._editor(spec, self._value(objects, spec)))
            self.table.setRowHidden(row, self.categorized() and
                                    category_of(spec) in self.collapsed)
        if 0 <= current_row < len(rows):
            self.table.setCurrentCell(current_row, 0)

    # -- Alphabetic / Categorized ---------------------------------------------------------------
    def categorized(self) -> bool:
        return self.view_tabs.currentIndex() == 1

    def _on_view_changed(self, index: int) -> None:
        _set_settings_value("properties/view", "categorized" if index == 1 else "alphabetic")
        self.refresh()

    def _add_heading(self, row: int, category: str) -> None:
        """A category's heading row: its name across both columns, with a
        collapse / expand mark."""
        mark = "\u25b8" if category in self.collapsed else "\u25be"  # (closed, open)
        item = QTableWidgetItem(f"{mark}  {category}")
        item.setFlags(Qt.ItemIsEnabled)
        font = QFont(item.font())
        font.setBold(True)
        item.setFont(font)
        item.setBackground(self.palette().color(QPalette.AlternateBase))
        item.setData(Qt.UserRole, category)
        self.table.setItem(row, 0, item)
        self.table.setSpan(row, 0, 1, 2)

    def _on_cell_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._specs) and isinstance(self._specs[row], str):
            self.toggle_category(self._specs[row])

    def toggle_category(self, category: str) -> None:
        """Collapse an expanded category, or expand a collapsed one."""
        if category in self.collapsed:
            self.collapsed.discard(category)
        else:
            self.collapsed.add(category)
        for row, spec in enumerate(self._specs):
            if spec == category:
                self._add_heading(row, category)
            elif not isinstance(spec, str) and category_of(spec) == category:
                self.table.setRowHidden(row, category in self.collapsed)

    def _value(self, objects, spec: PropSpec):
        if spec.name == "Name":  # a control array's elements share their (Name)
            name_value = getattr(self.designer, "name_value", self.designer.object_name)
            return name_value(objects[0])
        if spec.kind in COLLECTION_KINDS:  # (at run time these are the collections)
            values = [obj._values.get(spec.name, spec.default) for obj in objects]
        else:
            values = [getattr(obj, spec.name) for obj in objects]
        return values[0] if all(v == values[0] for v in values) else _MIXED

    def _on_object_chosen(self, index: int) -> None:
        name = self.object_combo.itemData(index)
        if name and self.designer is not None:
            self.designer.select_by_name(name)

    def _on_row_changed(self, row, *_):
        if 0 <= row < len(self._specs):
            spec = self._specs[row]
            if isinstance(spec, str):  # a category's heading
                self.description.setText(f"<b>{spec}</b>")
                return
            doc = spec.description or {
                "name": getattr(self.designer, "name_description",
                                "Returns the name used in code to identify an object."),
            }.get(spec.kind, "")
            self.description.setText(f"<b>{spec.name}</b><br>{doc}")

    def select_property(self, name: str) -> None:
        for row, spec in enumerate(self._specs):
            if not isinstance(spec, str) and spec.name == name:
                if self.table.isRowHidden(row):  # (in a collapsed category: open it)
                    self.toggle_category(category_of(spec))
                self.table.setCurrentCell(row, 0)
                editor = self.table.cellWidget(row, 1)
                if editor is not None:
                    editor.setFocus()
                return

    # -- editors ------------------------------------------------------------------------------
    def _commit(self, prop: str, value) -> None:
        if self.designer is None:
            return
        error = self.designer.set_property(prop, value)
        if error:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Properties", error)
            self.refresh()

    def _editor(self, spec: PropSpec, value) -> QWidget:
        mixed = value is _MIXED
        kind = spec.kind
        if kind in ("bool", "enum", "shortcut"):
            combo = QComboBox()
            choices = ((False, "False"), (True, "True")) if kind == "bool" else spec.choices
            for choice_value, label in choices:
                combo.addItem(label, choice_value)
            combo.setCurrentIndex(-1 if mixed else combo.findData(value))
            combo.activated.connect(
                lambda i, c=combo, n=spec.name: self._commit(n, c.itemData(i)))
            return combo
        if kind == "color":
            return self._color_editor(spec, None if mixed else value, mixed)
        if kind in ("list", "outline", *COLLECTION_KINDS):
            if kind == "list":
                text = f"(List: {len(value)} items)"
            elif kind in COLLECTION_KINDS:
                title = {"columns": "Columns", "listitems": "Items"}.get(kind, kind.title())
                text = f"({title}: {len(value)})"
            else:
                text = f"(Tree: {sum(1 for line in value if str(line).strip())} nodes)"
            button = QPushButton("" if mixed else text)
            button.setStyleSheet("text-align: left; padding-left: 4px;")
            button.clicked.connect(
                lambda _=False, n=spec.name, v=value, k=kind: self._edit_list(n, v, k))
            return button
        if spec.name in ("DataSource", "DataField") and kind == "str":
            return self._data_editor(spec, "" if mixed else value)
        if kind == "font":
            combo = QComboBox()
            combo.addItem("(Default)", None)
            for family in QFontDatabase.families():
                combo.addItem(family, family)
            combo.setCurrentIndex(-1 if mixed else max(combo.findData(value), 0))
            combo.activated.connect(
                lambda i, c=combo, n=spec.name: self._commit(n, c.itemData(i)))
            return combo

        edit = QLineEdit("" if mixed or value is None else str(value).replace("\n", "¶"))
        edit.setFrame(False)
        if kind == "int":
            edit.setValidator(QIntValidator(-1_000_000, 1_000_000))
            if value is None and not mixed:
                edit.setPlaceholderText("(Default)")
        elif kind == "index":
            edit.setValidator(QIntValidator(0, 32767))

        def commit(e=edit, n=spec.name, k=kind, original=value):
            text = e.text()
            if k == "int":
                if text == "":
                    new = None if original is None else original
                else:
                    new = int(text)
            elif k == "index":
                new = int(text) if text else None  # empty: not in a control array
            elif k == "text":
                new = text.replace("¶", "\n")
            else:
                new = text
            if new != original:
                self._commit(n, new)

        edit.editingFinished.connect(commit)
        if kind not in ("text", "file"):
            return edit
        # "..." button: multi-line text or file browser
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(edit)
        more = QToolButton()
        more.setText("…")
        layout.addWidget(more)
        if kind == "text":
            more.clicked.connect(lambda _=False, n=spec.name, v=value: self._edit_text(n, v))
        else:
            more.clicked.connect(lambda _=False, n=spec.name: self._browse_file(n))
        container.setFocusProxy(edit)
        return container

    def _data_choices(self, name: str) -> list[str]:
        """DataSource: the form's Data controls; DataField: the fields of the
        selected control's Data control's RecordSource (read from its database)."""
        from ..data import field_names

        controls = list(getattr(self.designer, "controls", {}).values())
        sources = {c.Name: c for c in controls if c.TypeName == "Data"}
        if name == "DataSource":
            return sorted(sources)
        objects = getattr(self, "_objects", [])
        data = sources.get(objects[0]._values.get("DataSource", "")) if objects else None
        if data is None:
            return []
        database = data._values.get("DatabaseName", "")
        if database and not os.path.isabs(database):
            database = os.path.join(getattr(self.designer, "base_dir", ""), database)
        return field_names(database, data._values.get("RecordSource", ""))

    def _data_editor(self, spec: PropSpec, value) -> QWidget:
        """An editable list: VB's DataSource and DataField drop-downs."""
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(self._data_choices(spec.name))
        combo.setCurrentText(str(value or ""))
        combo.setProperty("vp6_value", str(value or ""))

        def commit(c=combo, n=spec.name):
            text = c.currentText()
            if text != c.property("vp6_value"):  # (once: Enter, then losing the focus)
                c.setProperty("vp6_value", text)
                self._commit(n, text)

        combo.lineEdit().editingFinished.connect(commit)
        combo.activated.connect(lambda _i: commit())
        return combo

    def _color_editor(self, spec: PropSpec, value, mixed: bool) -> QWidget:
        button = QPushButton()
        button.setStyleSheet("text-align: left; padding-left: 4px;")
        if not mixed:
            button.setIcon(_swatch(value))
            button.setText("(Default)" if value is None else format_value("color", value))
        menu = QMenu(button)
        menu.addAction("(Default)", lambda: self._commit(spec.name, None))
        menu.addAction("Choose…", lambda: self._choose_color(spec.name, value))
        palette = menu.addMenu("Palette")
        for name in ("vpBlack", "vpWhite", "vpRed", "vpGreen", "vpBlue", "vpYellow",
                     "vpCyan", "vpMagenta"):
            color_value = getattr(colors, name)
            palette.addAction(_swatch(color_value), name,
                              lambda v=color_value: self._commit(spec.name, v))
        button.setMenu(menu)
        return button

    def _choose_color(self, prop: str, value) -> None:
        initial = colors.to_qcolor(value) if value is not None else QColor(Qt.white)
        color = QColorDialog.getColor(initial, self, prop)
        if color.isValid():
            self._commit(prop, colors.from_qcolor(color))

    def _edit_list(self, prop: str, value, kind: str = "list") -> None:
        hint = {
            "outline": "One node per line. Indent a node (spaces or a tab) to make it a child "
                       "of the node above; add |key at the end to give it a key, e.g. "
                       "\"Cats|cats\".",
            "panels": "One panel per line: Text|Key|options. The options are words: a width "
                      "in pixels, spring (shares the space left) or contents (as wide as its "
                      "text), caps, num, ins, scrl, time or date (what it shows), center or "
                      "right. E.g. \"Ready|status|spring\" or \"|clock|time 80 right\".",
            "tabs": "One tab per line: Caption|Key|ToolTipText|Image, e.g. \"&General|general|"
                    "Name and size|gear\". An & in the Caption underlines the letter of its "
                    "access key; the Image is a Key or Index in the TabStrip's ImageList.",
            "images": "One picture per line: path|key, the path relative to the form's "
                      "folder, e.g. \"images/open.png|open\". Add Pictures… adds files.",
            "buttons": "One button per line: Caption|Key|Image|ToolTipText|options, the Image "
                       "a Key or Index in the Toolbar's ImageList, the options words: check "
                       "or group (a button of a group, one of which is pressed), pressed, "
                       "disabled, hidden. A line of just - is a separator. E.g. "
                       "\"Open|open|open|Open a file\" or \"|bold|bold|Bold|check\".",
            "columns": "One column per line: Text|Key|Width|alignment, the alignment left, "
                       "right or center, e.g. \"Size|size|80|right\". The first column shows "
                       "the items' Text, the next ones their SubItems.",
            "listitems": "One item per line: Text|Key|Icon|SmallIcon|SubItem 1|SubItem 2..., "
                         "the icons Keys or Indexes in the Icons and SmallIcons ImageLists, "
                         "e.g. \"Earth|earth|planet|planet|12756 km|1 moon\".",
        }.get(kind)
        if kind == "outline":
            hint += (" A third part is the node's Image: a Key or Index in the TreeView's "
                     "ImageList, e.g. \"Cats|cats|cat\".")
        title = {"list": "List", "outline": "Tree", "panels": "Panels", "tabs": "Tabs",
                 "images": "Pictures", "buttons": "Buttons", "columns": "Columns",
                 "listitems": "Items"}[kind]
        base = self.designer.base_dir if kind == "images" and self.designer else None
        dialog = TextListDialog(f"{prop} ({title})",
                                "\n".join(value or []), self, hint, pictures_dir=base)
        if dialog.exec():
            items = dialog.edit.toPlainText().split("\n")
            while items and items[-1] == "":
                items.pop()
            self._commit(prop, items)

    def _edit_text(self, prop: str, value) -> None:
        dialog = TextListDialog(prop, value or "", self)
        if dialog.exec():
            self._commit(prop, dialog.edit.toPlainText())

    def _browse_file(self, prop: str) -> None:
        base = self.designer.base_dir if self.designer else ""
        path, _ = QFileDialog.getOpenFileName(
            self, prop, base, "Images (*.png *.jpg *.jpeg *.gif *.bmp *.ico);;All files (*)")
        if not path:
            return
        try:
            relative = os.path.relpath(path, base)
            if not relative.startswith(".."):
                path = relative
        except ValueError:
            pass
        self._commit(prop, path)
