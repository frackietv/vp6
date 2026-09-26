"""The Menu Editor (Tools > Menu Editor, Ctrl+E): designs a form's menus.

Like VB's, it edits the menus as one indented list: an item's level is how
deep it is (0 = the menu bar, 1 = an item of a menu bar menu, ...). Each
entry has a Caption ("-" for a separator), a Name, an optional Index (menu
control arrays), a Shortcut and the Checked, Enabled and Visible flags.

``entries_from(form_def)`` reads a form's menus as ``MenuEntry``s,
``validate(entries, ...)`` checks them, and ``menu_defs(entries)`` turns them
back into the form's ``Menu`` ``ControlDef``s. ``MenuEditorDialog`` is the
dialog.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
                               QPushButton, QVBoxLayout)

from ..controls import SHORTCUT_CHOICES
from ..formfile import ControlDef, FormDef, control_key

MAX_LEVEL = 5  # like VB: the menu bar plus five levels of submenus
INDENT = "····"


@dataclass
class MenuEntry:
    level: int = 0
    caption: str = ""
    name: str = ""
    index: int | None = None
    shortcut: str = ""
    checked: bool = False
    enabled: bool = True
    visible: bool = True
    props: dict = field(default_factory=dict)  # other properties (e.g. Tag), kept as they are
    original: str | None = None  # the menu's key before editing (None = new)

    @property
    def key(self) -> str:
        return control_key(self.name, self.index)

    def is_blank(self) -> bool:
        return not self.caption and not self.name


def entries_from(form_def: FormDef) -> list[MenuEntry]:
    """The form's menus in menu order (depth first)."""
    menus = [c for c in form_def.controls if c.type == "Menu"]
    entries = []

    def add(parent: str | None, level: int) -> None:
        for control in menus:
            if control.parent == parent:
                props = dict(control.props)
                entries.append(MenuEntry(
                    level, props.pop("Caption", ""), control.name, control.index,
                    props.pop("Shortcut", ""), props.pop("Checked", False),
                    props.pop("Enabled", True), props.pop("Visible", True), props,
                    control.key))
                add(control.key, level + 1)

    add(None, 0)
    return entries


def validate(entries: list[MenuEntry], taken: set[str]) -> str | None:
    """An error message for the first problem, or None. ``taken`` are names
    used by the form and its other controls."""
    seen: dict[str, bool] = {}  # name -> whether it has an Index
    keys = set()
    previous_level = -1
    for number, entry in enumerate(entries, 1):
        where = f"Item {number} ({entry.caption or entry.name or 'blank'})"
        if not entry.name:
            return f"{where}: every menu item needs a Name"
        if not entry.name.isidentifier():
            return f"{where}: '{entry.name}' is not a valid name"
        if entry.name in taken:
            return f"{where}: the name '{entry.name}' is already used on the form"
        if entry.key in keys:
            return f"{where}: '{entry.key}' is used twice"
        has_index = entry.index is not None
        if seen.get(entry.name, has_index) != has_index:
            return (f"{where}: menus named '{entry.name}' form a control array, so each "
                    "needs an Index")
        if has_index and not 0 <= entry.index <= 32767:
            return f"{where}: Index must be from 0 to 32767"
        if entry.level > previous_level + 1:
            return f"{where}: it is indented more than one level below the item above"
        if entry.level > MAX_LEVEL:
            return f"{where}: menus can be at most {MAX_LEVEL} levels deep"
        if entry.caption == "-" and entry.level == 0:
            return f"{where}: a separator can't be on the menu bar"
        following = entries[number] if number < len(entries) else None
        if entry.caption == "-" and following is not None and following.level > entry.level:
            return f"{where}: a separator can't have items of its own"
        seen[entry.name] = has_index
        keys.add(entry.key)
        previous_level = entry.level
    return None


def menu_defs(entries: list[MenuEntry]) -> list[ControlDef]:
    """``Menu`` ControlDefs for valid entries, parents from the levels."""
    defs, parents = [], []  # parents[level] = key of the latest entry at that level
    for entry in entries:
        props = dict(entry.props)
        props["Caption"] = entry.caption
        for name, value, default in (("Checked", entry.checked, False),
                                     ("Enabled", entry.enabled, True),
                                     ("Visible", entry.visible, True),
                                     ("Shortcut", entry.shortcut, "")):
            if value != default:  # like the form file: only what differs from the default
                props[name] = value
        parent = parents[entry.level - 1] if entry.level > 0 else None
        defs.append(ControlDef("Menu", entry.name, parent, props, entry.index))
        del parents[entry.level:]
        parents.append(entry.key)
    return defs


class MenuEditorDialog(QDialog):
    """VB's Menu Editor: fields for the current item, the arrow buttons that
    indent and move it, Next / Insert / Delete, and the list of all items."""

    def __init__(self, entries: list[MenuEntry], taken: set[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Menu Editor")
        self.entries = copy.deepcopy(entries)
        self.taken = set(taken)
        self._loading = False

        self.caption = QLineEdit()
        self.name = QLineEdit()
        self.index = QLineEdit()
        self.index.setValidator(QIntValidator(0, 32767))
        self.index.setMaximumWidth(70)
        self.shortcut = QComboBox()
        for value, label in SHORTCUT_CHOICES:
            self.shortcut.addItem(label, value)
        self.checked = QCheckBox("&Checked")
        self.enabled = QCheckBox("&Enabled")
        self.visible = QCheckBox("&Visible")

        fields = QGridLayout()
        for row, (text, widget) in enumerate((("Ca&ption:", self.caption),
                                              ("Na&me:", self.name))):
            label = QLabel(text)
            label.setBuddy(widget)
            fields.addWidget(label, row, 0)
            fields.addWidget(widget, row, 1, 1, 3)
        index_label, shortcut_label = QLabel("&Index:"), QLabel("&Shortcut:")
        index_label.setBuddy(self.index)
        shortcut_label.setBuddy(self.shortcut)
        fields.addWidget(index_label, 2, 0)
        fields.addWidget(self.index, 2, 1)
        fields.addWidget(shortcut_label, 2, 2, Qt.AlignRight)
        fields.addWidget(self.shortcut, 2, 3)
        flags = QHBoxLayout()
        for box in (self.checked, self.enabled, self.visible):
            flags.addWidget(box)
        flags.addStretch(1)

        self.buttons = {}
        tools = QHBoxLayout()
        for key, text, tip, slot in (
                ("left", "←", "Move out one level", self.outdent),
                ("right", "→", "Move in one level (make it an item of the menu above)",
                 self.indent),
                ("up", "↑", "Move up", self.move_up),
                ("down", "↓", "Move down", self.move_down),
                ("next", "&Next", "Go to the next item (a new one at the end)", self.next),
                ("insert", "Inse&rt", "Insert a new item above this one", self.insert),
                ("delete", "De&lete", "Delete this item", self.delete)):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.setAutoDefault(False)
            button.clicked.connect(slot)
            self.buttons[key] = button
            tools.addWidget(button)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._show_entry)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(fields)
        layout.addLayout(flags)
        layout.addLayout(tools)
        layout.addWidget(self.list, 1)
        layout.addWidget(box)
        self.resize(460, 480)

        self.caption.textEdited.connect(self._on_caption_edited)
        self.name.textEdited.connect(self._store)
        self.index.textEdited.connect(self._store)
        self.shortcut.activated.connect(self._store)
        for box_ in (self.checked, self.enabled, self.visible):
            box_.toggled.connect(self._store)
        if not self.entries:
            self.entries.append(MenuEntry())
        self._fill_list(0)

    # -- the list -----------------------------------------------------------------------------------
    @staticmethod
    def _text(entry: MenuEntry) -> str:
        caption = entry.caption or (f"({entry.name})" if entry.name else "")
        return INDENT * entry.level + caption

    def _fill_list(self, row: int) -> None:
        self._loading = True
        self.list.clear()
        for entry in self.entries:
            self.list.addItem(self._text(entry))
        self._loading = False
        self.list.setCurrentRow(max(0, min(row, len(self.entries) - 1)))
        self._show_entry(self.list.currentRow())

    @property
    def row(self) -> int:
        return self.list.currentRow()

    @property
    def current(self) -> MenuEntry:
        return self.entries[self.row]

    def _show_entry(self, row: int) -> None:
        if self._loading or not 0 <= row < len(self.entries):
            return
        entry = self.entries[row]
        self._loading = True
        self.caption.setText(entry.caption)
        self.name.setText(entry.name)
        self.index.setText("" if entry.index is None else str(entry.index))
        self.shortcut.setCurrentIndex(max(self.shortcut.findData(entry.shortcut), 0))
        self.checked.setChecked(entry.checked)
        self.enabled.setChecked(entry.enabled)
        self.visible.setChecked(entry.visible)
        self._loading = False
        self._update_buttons()
        self.caption.setFocus()

    def _update_buttons(self) -> None:
        row, entry = self.row, self.current
        above = self.entries[row - 1].level if row > 0 else -1
        self.buttons["left"].setEnabled(entry.level > 0)
        self.buttons["right"].setEnabled(entry.level <= above and entry.level < MAX_LEVEL)
        self.buttons["up"].setEnabled(row > 0)
        self.buttons["down"].setEnabled(row < len(self.entries) - 1)

    # -- editing the current item ---------------------------------------------------------------
    def _on_caption_edited(self, text: str) -> None:
        self._store()

    def _store(self, *_) -> None:
        if self._loading:
            return
        entry = self.current
        entry.caption = self.caption.text()
        entry.name = self.name.text().strip()
        entry.index = int(self.index.text()) if self.index.text() else None
        entry.shortcut = self.shortcut.currentData() or ""
        entry.checked = self.checked.isChecked()
        entry.enabled = self.enabled.isChecked()
        entry.visible = self.visible.isChecked()
        self.list.item(self.row).setText(self._text(entry))

    def outdent(self) -> None:
        if self.current.level > 0:
            self.current.level -= 1
            self._fill_list(self.row)

    def indent(self) -> None:
        row = self.row
        above = self.entries[row - 1].level if row > 0 else -1
        if self.current.level <= above and self.current.level < MAX_LEVEL:
            self.current.level += 1
            self._fill_list(row)

    def move_up(self) -> None:
        row = self.row
        if row > 0:
            self.entries[row - 1], self.entries[row] = self.entries[row], self.entries[row - 1]
            self._fill_list(row - 1)

    def move_down(self) -> None:
        row = self.row
        if row < len(self.entries) - 1:
            self.entries[row + 1], self.entries[row] = self.entries[row], self.entries[row + 1]
            self._fill_list(row + 1)

    def next(self) -> None:
        """The next item; at the end, a new one at the same level (like VB)."""
        row = self.row
        if row == len(self.entries) - 1:
            if self.current.is_blank():
                return
            self.entries.append(MenuEntry(level=self.current.level))
        self._fill_list(row + 1)

    def insert(self) -> None:
        row = self.row
        self.entries.insert(row, MenuEntry(level=self.current.level))
        self._fill_list(row)

    def delete(self) -> None:
        row = self.row
        del self.entries[row]
        if not self.entries:
            self.entries.append(MenuEntry())
        self._fill_list(min(row, len(self.entries) - 1))

    # -- OK ------------------------------------------------------------------------------------------
    def result_entries(self) -> list[MenuEntry]:
        """The entries without blank ones (e.g. the empty item Next adds)."""
        return [e for e in self.entries if not e.is_blank()]

    def error(self) -> str | None:
        return validate(self.result_entries(), self.taken)

    def accept(self) -> None:
        error = self.error()
        if error:
            QMessageBox.warning(self, "Menu Editor", error)
            return
        super().accept()
