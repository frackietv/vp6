"""Views over items: ``ColumnView`` (Finder-style columns) and ``UndoView``
(an undo history) with its ``UndoStack``.

* **ColumnView** browses a tree in columns, as the macOS Finder does: a
  node's children open in the next column. Its ``Nodes`` are like a
  TreeView's (``Nodes.Add(Relative, Relationship, Key, Text, Image)``, by Key
  or Index from 1; a node's ``Text``, ``Key``, ``Image``, ``Tag``, ``Parent``,
  ``Children``, ``Child``, ``FullPath``), set in the designer as an indented
  outline (``Items``). ``SelectedItem`` is the chosen node; ``NodeClick
  (Node)`` fires when one is chosen, ``Expand(Node)`` when a node's children
  open. ``PreviewWidget`` names a control of the form shown in the last
  column for a leaf node (update it in NodeClick). With ``FileSystem`` it
  browses the folders and files under ``Path`` instead: the nodes it gives
  have the file's ``Key`` (its full path) and ``Text`` (its name);
  ``SelectedPath`` is the chosen one.
* **UndoStack** keeps what was done, to undo and redo it:
  ``Push(Text, DoCode, UndoCode)`` runs ``DoCode`` (a function, or Python
  code run in the form's methods' globals with ``self`` the form) and
  remembers ``UndoCode``; ``Undo()``, ``Redo()``, ``CanUndo``, ``CanRedo``,
  ``UndoText``, ``RedoText``, ``Count``, ``Index``, ``Clear()``; ``SetClean()``
  marks where the work was saved (``IsClean``, ``CleanIndex``). Make one with
  ``UndoStack(self)`` in a form's code (its code runs as the form's), or use
  an UndoView's ``Stack``.
* **UndoView** lists an undo history: its ``Stack`` (an UndoStack) by
  default, or the undo history of a multi-line TextBox, a RichTextBox, a
  CodeBox or a MarkdownBox (``Editor``: its name; each change typed is a step); clicking a line goes back (or forward)
  to that point. ``EmptyLabel`` is the first line (the state before
  everything). ``Change`` fires when the history's position changes.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QDir, QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QAbstractItemView, QColumnView, QFileSystemModel, QUndoView,
                               QWidget)

from ._props import P
from .app import call_handler
from .controls import (_COLORS, _COMMON, _FONT, _TVW_CHILD, _TVW_FIRST, _TVW_LAST, _TVW_NEXT,
                       _TVW_PREVIOUS, CONTROL_TYPES, EVENT_ARGS, Control, _add_mouse_members,
                       _add_validation, _geometry, _picture_icon, _UsesImageList, parse_outline)

_NODE_ROLE = Qt.UserRole + 20


# --- ColumnView ------------------------------------------------------------------------------

class ColumnNode:
    """One node of a ColumnView (its Nodes), like a TreeView's Node."""

    def __init__(self, view: "ColumnView", item: QStandardItem | None, key: str,
                 path: str = ""):
        self._view, self._item, self._key = view, item, key
        self._path = path  # (FileSystem: the file's path)
        self._image = ""
        self.Tag = ""
        if item is not None:
            item.setData(self, _NODE_ROLE)

    def __repr__(self):
        return f"<ColumnNode {self.Text!r}{f' key={self._key!r}' if self._key else ''}>"

    @property
    def Text(self) -> str:
        return self._item.text() if self._item is not None else os.path.basename(self._path) \
            or self._path

    @Text.setter
    def Text(self, value):
        self._check_item()
        self._item.setText(str(value))

    @property
    def Key(self) -> str:
        return self._key

    @property
    def Image(self):
        """The picture before its text: a Key or Index in the ImageList, or a file."""
        return self._image

    @Image.setter
    def Image(self, value):
        self._check_item()
        value = "" if value is None else value
        self._item.setIcon(_picture_icon(self._view, value, strict=True))
        self._image = value

    def _check_item(self) -> None:
        if self._item is None:
            raise AttributeError("A FileSystem ColumnView's nodes are the files: they can't "
                                 "be changed")

    @property
    def Parent(self) -> "ColumnNode | None":
        if self._item is None:
            parent = os.path.dirname(self._path)
            return self._view._file_node(parent) if parent != self._path else None
        parent = self._item.parent()
        return parent.data(_NODE_ROLE) if parent is not None else None

    @property
    def Children(self) -> int:
        """How many children it has."""
        if self._item is None:
            return len(os.listdir(self._path)) if os.path.isdir(self._path) else 0
        return self._item.rowCount()

    @property
    def Child(self) -> "ColumnNode | None":
        """Its first child."""
        if self._item is None or not self._item.rowCount():
            return None
        return self._item.child(0).data(_NODE_ROLE)

    def _siblings(self) -> QStandardItem:
        return self._item.parent() or self._view._model.invisibleRootItem()

    @property
    def Next(self) -> "ColumnNode | None":
        if self._item is None:
            return None
        siblings = self._siblings()
        row = self._item.row() + 1
        return siblings.child(row).data(_NODE_ROLE) if row < siblings.rowCount() else None

    @property
    def Previous(self) -> "ColumnNode | None":
        if self._item is None:
            return None
        row = self._item.row() - 1
        return self._siblings().child(row).data(_NODE_ROLE) if row >= 0 else None

    @property
    def FullPath(self) -> str:
        """Its texts from the top, joined by the PathSeparator (FileSystem: its path)."""
        if self._item is None:
            return self._path
        parts, item = [], self._item
        while item is not None:
            parts.append(item.text())
            item = item.parent()
        return self._view._values.get("PathSeparator", "\\").join(reversed(parts))

    @property
    def IsFolder(self) -> bool:
        """FileSystem: whether it is a folder (else: whether it has children)."""
        return os.path.isdir(self._path) if self._item is None else self._item.rowCount() > 0

    @property
    def Index(self) -> int:
        """Its number in Nodes (from 1)."""
        return self._view._nodes._list.index(self) + 1

    @property
    def Selected(self) -> bool:
        return self._view.SelectedItem is self

    @Selected.setter
    def Selected(self, value):
        if value:
            self._view.SelectedItem = self


class _ColumnNodes:
    """A ColumnView's Nodes (as a TreeView's): by Key or Index from 1, ``Add``,
    ``Remove``, ``Clear``, ``Count``."""

    def __init__(self, view: "ColumnView"):
        self._view = view
        self._list: list[ColumnNode] = []
        self._by_key: dict[str, ColumnNode] = {}

    def _resolve(self, ref) -> ColumnNode:
        if isinstance(ref, ColumnNode):
            if ref not in self._list:
                raise ValueError(f"{ref!r} is not in ColumnView '{self._view.Name}'")
            return ref
        if isinstance(ref, str):
            if ref not in self._by_key:
                raise KeyError(f"ColumnView '{self._view.Name}' has no node with key {ref!r}")
            return self._by_key[ref]
        if isinstance(ref, int) and not isinstance(ref, bool):
            if not 1 <= ref <= len(self._list):
                raise IndexError(f"ColumnView '{self._view.Name}' has no node {ref} "
                                 f"(1 to {len(self._list)})")
            return self._list[ref - 1]
        raise TypeError(f"A node is chosen by key, Index or ColumnNode, not {ref!r}")

    def Item(self, ref) -> ColumnNode:
        return self._resolve(ref)

    __getitem__ = __call__ = Item

    def __iter__(self):
        return iter(list(self._list))

    def __len__(self) -> int:
        return len(self._list)

    def __contains__(self, ref) -> bool:
        return ref in self._by_key if isinstance(ref, str) else ref in self._list

    @property
    def Count(self) -> int:
        return len(self._list)

    def Add(self, Relative=None, Relationship=None, Key: str = "", Text: str = "",
            Image="") -> ColumnNode:
        """Add a node, as a TreeView's Nodes.Add: at the end of the first column,
        or by ``Relationship`` to ``Relative`` (vpTvwFirst, vpTvwLast, vpTvwNext,
        vpTvwPrevious among its siblings, or vpTvwChild)."""
        if Key and Key in self._by_key:
            raise ValueError(f"ColumnView '{self._view.Name}': the key {Key!r} is not unique")
        item = QStandardItem(str(Text))
        item.setEditable(False)
        if Relative is None:
            parent = self._view._model.invisibleRootItem()
            row = 0 if Relationship == _TVW_FIRST else parent.rowCount()
        else:
            relative = self._resolve(Relative)
            relationship = _TVW_NEXT if Relationship is None else Relationship
            if relationship == _TVW_CHILD:
                parent, row = relative._item, relative._item.rowCount()
            else:
                parent = relative._siblings()
                row = {_TVW_FIRST: 0, _TVW_LAST: parent.rowCount(),
                       _TVW_NEXT: relative._item.row() + 1,
                       _TVW_PREVIOUS: relative._item.row()}.get(relationship)
                if row is None:
                    raise ValueError(f"Unknown relationship {Relationship!r}")
        node = ColumnNode(self._view, item, str(Key or ""))
        parent.insertRow(row, item)
        if Image:
            node.Image = Image
        self._list.append(node)
        if Key:
            self._by_key[str(Key)] = node
        return node

    def Remove(self, ref) -> None:
        """Remove a node and its children."""
        node = self._resolve(ref)
        gone, stack = [], [node._item]
        while stack:
            item = stack.pop()
            gone.append(item.data(_NODE_ROLE))
            stack.extend(item.child(i) for i in range(item.rowCount()))
        node._siblings().removeRow(node._item.row())
        for doomed in gone:
            self._list.remove(doomed)
            self._by_key.pop(doomed._key, None)

    def Clear(self) -> None:
        self._view._model.clear()
        self._list.clear()
        self._by_key.clear()


class ColumnView(_UsesImageList, Control):
    """A Finder-style column browser (the module's documentation)."""

    TypeName = "ColumnView"
    DefaultEvent = "NodeClick"
    DefaultSize = (401, 201)
    Events = ("NodeClick", "Expand", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp")
    _qss_type = "QColumnView"
    Properties = (
        *_geometry(*DefaultSize),
        P("ColumnWidth", "int", 160, description="Each column's width, in pixels"),
        P("ResizeGrips", "bool", True,
          description="A grip under each column to make it wider or narrower"),
        P("PathSeparator", "str", "\\", description="Separates the texts in a node's FullPath"),
        P("ImageList", "str", "",
          description="The name of an ImageList on the form: the nodes' Image is then a "
                      "picture's Key or Index in it"),
        P("Items", "outline", [],
          description="The nodes, set in the designer: one per line, indented under its "
                      "parent; a vertical bar and a key at the end give the node that key"),
        P("PreviewWidget", "str", "",
          description="The name of a control of the form shown in the last column when a node "
                      "without children is chosen"),
        P("FileSystem", "bool", False,
          description="Browse the folders and files under Path instead of the Items"),
        P("Path", "str", "",
          description="FileSystem: the folder it starts in (relative to the form's folder); "
                      "empty = your home folder"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__["_nodes"] = _ColumnNodes(self)
        self.__dict__["_quiet"] = 0
        self.__dict__["_files"] = None  # FileSystem: its QFileSystemModel
        view = QColumnView(parent)
        model = QStandardItemModel(view)
        self.__dict__["_model"] = model
        view.setModel(model)
        view.setSelectionMode(QAbstractItemView.SingleSelection)
        return view

    def _connect_signals(self):
        self._connect_selection()

    def _connect_selection(self) -> None:
        selection = self._widget.selectionModel()
        if selection is not None:
            selection.currentChanged.connect(self._on_current_changed)

    def _on_current_changed(self, current: QModelIndex, _previous):
        if self._quiet or not current.isValid():
            return
        node = self._node_at(current)
        self._fire("NodeClick", node)
        if node is not None and node.IsFolder:
            self._fire("Expand", node)

    def _node_at(self, index: QModelIndex) -> "ColumnNode | None":
        if not index.isValid():
            return None
        if self._files is not None:
            return self._file_node(self._files.filePath(index))
        return index.data(_NODE_ROLE)

    def _file_node(self, path: str) -> ColumnNode:
        return ColumnNode(self, None, path, path)

    # -- the nodes ------------------------------------------------------------------------------
    @property
    def Nodes(self) -> _ColumnNodes:
        return self._nodes

    def _apply_Items(self, lines):
        self._nodes.Clear()
        parents: list[ColumnNode] = []
        for level, text, key, image in parse_outline(lines):
            del parents[level:]
            parent = parents[-1] if parents else None
            node = self._nodes.Add(parent, _TVW_CHILD if parent else None, key, text)
            if image:
                node._image = image
                node._item.setIcon(_picture_icon(self, image))
            parents.append(node)

    def _refresh_images(self) -> None:
        for node in self._nodes._list:
            node._item.setIcon(_picture_icon(self, node._image))

    @property
    def SelectedItem(self) -> "ColumnNode | None":
        """The chosen node (its column, and the ones before it, open); set it to
        a node, its Key or Index to choose it (no NodeClick)."""
        return self._node_at(self._widget.currentIndex())

    @SelectedItem.setter
    def SelectedItem(self, node):
        self.__dict__["_quiet"] = self._quiet + 1
        try:
            if node is None:
                self._widget.setCurrentIndex(QModelIndex())
            elif self._files is not None:
                path = node._path if isinstance(node, ColumnNode) else str(node)
                self._widget.setCurrentIndex(self._files.index(path))
            else:
                self._widget.setCurrentIndex(self._nodes._resolve(node)._item.index())
        finally:
            self.__dict__["_quiet"] = self._quiet - 1

    @property
    def SelectedPath(self) -> str:
        """FileSystem: the chosen file's or folder's path ("" if none); set it to
        choose one."""
        node = self.SelectedItem
        return node._path if node is not None and self._files is not None else ""

    @SelectedPath.setter
    def SelectedPath(self, value):
        self.SelectedItem = str(value) if value else None

    # -- the preview -----------------------------------------------------------------------------
    def _apply_PreviewWidget(self, v):
        if self._design_mode:
            return
        control = self._form.__dict__.get(v) if v else None
        if isinstance(control, Control) and control._widget is not None and control is not self:
            self._widget.setPreviewWidget(control._widget)
            self.__dict__["_preview"] = control

    def _form_loaded(self) -> None:
        if self.__dict__.get("_preview") is None:  # (it may come after this in the region)
            self._apply_PreviewWidget(self._values.get("PreviewWidget", ""))

    # -- the file system -------------------------------------------------------------------------
    def _apply_FileSystem(self, v):
        if self._design_mode:
            return
        view = self._widget
        if v and self._files is None:
            files = QFileSystemModel(view)
            files.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.AllDirs)
            self.__dict__["_files"] = files
            view.setModel(files)
            self._apply_Path(self._values.get("Path", ""))
            self._connect_selection()  # (a new model: a new selection model)
        elif not v and self._files is not None:
            view.setModel(self._model)
            self._files.deleteLater()
            self.__dict__["_files"] = None
            self._connect_selection()

    def _apply_Path(self, v):
        files = self._files
        if files is None:
            return
        folder = os.path.join(self._form._base_dir(), v) if v and not os.path.isabs(v) \
            else (v or os.path.expanduser("~"))
        files.setRootPath(folder)
        self._widget.setRootIndex(files.index(folder))

    def _apply_ColumnWidth(self, v):
        self._widget.setColumnWidths([max(40, int(v))] * 16)

    def _apply_ResizeGrips(self, v):
        self._widget.setResizeGripsVisible(bool(v))


# --- UndoStack and UndoView ------------------------------------------------------------------

class _Command(QUndoCommand):
    def __init__(self, stack: "UndoStack", text: str, do, undo):
        super().__init__(text)
        self._stack, self._do, self._undo = stack, do, undo

    def redo(self):
        self._stack._run(self._do)

    def undo(self):
        self._stack._run(self._undo)


class UndoStack:
    """What was done, to undo and redo it (the module's documentation)."""

    def __init__(self, Owner=None, _stack: QUndoStack | None = None):
        from .app import ensure_app

        ensure_app()
        self._owner = Owner  # (the form whose code DoCode and UndoCode run as)
        self._stack = _stack if _stack is not None else QUndoStack()
        self._changed_handlers = []

    def __repr__(self):
        return f"<UndoStack {self.Index}/{self.Count}>"

    def _run(self, code) -> None:
        if code is None or code == "":
            return
        if callable(code):
            call_handler(code)
            return
        owner = self._owner
        namespace = {}
        if owner is not None:
            module = sys.modules.get(type(owner).__module__)
            if module is not None:
                namespace.update(vars(module))
            namespace["self"] = owner
        exec(compile(str(code), "<UndoStack>", "exec", dont_inherit=True), namespace)

    def Push(self, Text: str, DoCode, UndoCode) -> None:
        """Do something and remember how to undo it: DoCode runs now (and on
        Redo), UndoCode on Undo. Each is a function, or Python code to run
        (with ``self`` the form). It drops what was undone before."""
        self._stack.push(_Command(self, str(Text), DoCode, UndoCode))

    def Undo(self) -> None:
        self._stack.undo()

    def Redo(self) -> None:
        self._stack.redo()

    def Clear(self) -> None:
        self._stack.clear()

    @property
    def CanUndo(self) -> bool:
        return self._stack.canUndo()

    @property
    def CanRedo(self) -> bool:
        return self._stack.canRedo()

    @property
    def UndoText(self) -> str:
        """What Undo would undo ("" if nothing)."""
        return self._stack.undoText()

    @property
    def RedoText(self) -> str:
        return self._stack.redoText()

    @property
    def Count(self) -> int:
        """How many steps it holds."""
        return self._stack.count()

    @property
    def Index(self) -> int:
        """How many of them are done (the others were undone); setting it undoes
        or redoes up to there."""
        return self._stack.index()

    @Index.setter
    def Index(self, value):
        self._stack.setIndex(int(value))

    def Text(self, Index: int) -> str:
        """Step Index's text (from 0)."""
        return self._stack.text(int(Index))

    @property
    def UndoLimit(self) -> int:
        """How many steps it keeps (0: all)."""
        return self._stack.undoLimit()

    @UndoLimit.setter
    def UndoLimit(self, value):
        self._stack.setUndoLimit(int(value))

    def SetClean(self) -> None:
        """Mark the present state as saved."""
        self._stack.setClean()

    @property
    def IsClean(self) -> bool:
        """Whether it is at the state marked by SetClean."""
        return self._stack.isClean()

    @property
    def CleanIndex(self) -> int:
        """The Index SetClean marked (-1: none, or it was dropped)."""
        return self._stack.cleanIndex()


def _editor_document(control):
    """The QTextDocument of a text control (its undo history), or None."""
    widget = getattr(control, "_widget", None)
    if widget is None:
        return None
    for name in ("document", "editor"):
        getter = getattr(widget, name, None)
        if callable(getter):
            document = getter()
            if hasattr(document, "undo"):
                return document
    for child in widget.findChildren(QWidget):
        getter = getattr(child, "document", None)
        if callable(getter):
            return getter()
    return None


class UndoView(Control):
    """An undo history list (the module's documentation)."""

    TypeName = "UndoView"
    DefaultEvent = "Change"
    DefaultSize = (185, 161)
    Events = ("Change", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp")
    _qss_type = "QUndoView"
    Properties = (
        *_geometry(*DefaultSize),
        P("EmptyLabel", "str", "<empty>",
          description="The first line: the state before anything was done"),
        P("Editor", "str", "",
          description="The name of a TextBox, RichTextBox, CodeBox or MarkdownBox on the form "
                      "whose undo history it shows; empty = its own Stack"),
        *_COLORS, *_FONT, *_COMMON,
    )

    def _create_widget(self, parent):
        stack = UndoStack(self._form)
        self.__dict__["_stack"] = stack
        self.__dict__["_editor_stack"] = None
        view = QUndoView(stack._stack, parent)
        stack._stack.indexChanged.connect(self._on_index_changed)
        return view

    def _on_index_changed(self, *_):
        self._fire("Change")

    @property
    def Stack(self) -> UndoStack:
        """Its UndoStack (Push, Undo, Redo...); with an Editor, the editor's history."""
        return self.__dict__.get("_editor_stack") or self._stack

    def _apply_EmptyLabel(self, v):
        self._widget.setEmptyLabel(v)

    def _apply_Editor(self, v):
        if self._design_mode:
            return
        control = self._form.__dict__.get(v) if v else None
        document = _editor_document(control) if control is not None else None
        if document is None:
            self.__dict__["_editor_stack"] = None
            self._widget.setStack(self._stack._stack)
            return
        stack = _DocumentHistory(document, self._form)
        self.__dict__["_editor_stack"] = stack
        self._widget.setStack(stack._stack)
        stack._stack.indexChanged.connect(self._on_index_changed)

    def _form_loaded(self) -> None:
        if self._values.get("Editor") and self.__dict__.get("_editor_stack") is None:
            self._apply_Editor(self._values["Editor"])


class _DocumentHistory(UndoStack):
    """A text control's undo history as an UndoStack: each change to its text
    is a step (undoing it is the document's own undo)."""

    def __init__(self, document, owner):
        super().__init__(owner)
        self._document = document
        self._replaying = False
        self._syncing = False
        document.undoCommandAdded.connect(self._added)
        document.contentsChanged.connect(self._sync)

    def _added(self):
        if self._replaying:
            return
        self._stack.push(_DocumentStep(self, f"Typing {self._stack.count() + 1}"))

    def _sync(self):
        """The editor's own Undo or Redo (Ctrl+Z): the history follows."""
        if self._replaying or self._syncing:
            return
        steps = self._document.availableUndoSteps()
        if steps != self._stack.index() and steps <= self._stack.count():
            self._syncing = True
            try:
                self._stack.setIndex(steps)
            finally:
                self._syncing = False

    def Push(self, Text: str, DoCode, UndoCode) -> None:
        raise TypeError("An editor's undo history is its own: type in the editor")


class _DocumentStep(QUndoCommand):
    def __init__(self, history: _DocumentHistory, text: str):
        super().__init__(text)
        self._history = history
        self._first = True

    def redo(self):
        if self._first:  # (pushed after the document did it)
            self._first = False
            return
        history = self._history
        if history._syncing:
            return
        history._replaying = True
        try:
            history._document.redo()
        finally:
            history._replaying = False

    def undo(self):
        history = self._history
        if history._syncing:
            return
        history._replaying = True
        try:
            history._document.undo()
        finally:
            history._replaying = False


EVENT_ARGS.update({"NodeClick": "Node", "Expand": "Node"})
_TYPES = (ColumnView, UndoView)
for _cls in _TYPES:
    _add_validation(_cls)
    _add_mouse_members(_cls)
    CONTROL_TYPES[_cls.TypeName] = _cls  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
