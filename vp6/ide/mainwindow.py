"""The VP6 IDE main window."""

from __future__ import annotations

import os
import shutil
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QLineEdit, QMainWindow, QMdiArea,
    QMdiSubWindow, QMessageBox, QPlainTextEdit, QSizePolicy, QWidget,
)

import vp6

from .. import formfile
from ..app import install_interrupt_handler
from ..appearance import IDE_SCHEME_ENV, SCHEME_NAMES, scheme_from_name
from ..project import EXTENSION, SUB_MAIN, Project
from . import icons, kitchensink
from .codeeditor import CodeWindow
from .designer import FormDesigner, is_identifier
from .dialogs import ABOUT_HTML, NewProjectDialog, ProjectPropertiesDialog
from .documents import Document, FormDocument, open_document
from .findreplace import FindReplaceDialog, ask_line
from .options import OptionsDialog
from .outline import OutlineWindow
from .outputcapture import OutputCapture
from .panels import (ImmediateWindow, OutputWindow, ProjectExplorer, Toolbox,
                     pump_process_output)
from .projectprops import FileTarget, ProjectTarget
from .properties import PropertiesWindow
from .theme import SYSTEM, ide_settings, theme_manager

VP6_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(vp6.__file__)))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = ide_settings()
        self.project: Project | None = None
        self.documents: dict[str, Document] = {}
        self.designer_windows: dict[str, QMdiSubWindow] = {}
        # Every form designer, also those not open in a window: a form selected
        # in the Project panel shows all its properties through one
        self._designers: dict[str, FormDesigner] = {}
        self.code_windows: dict[str, QMdiSubWindow] = {}
        self.process: QProcess | None = None
        self.current_tool: str | None = None
        self._last_designer: FormDesigner | None = None
        self.find_dialog: FindReplaceDialog | None = None  # created when first needed
        self._icon_actions: list[tuple[QAction, str]] = []

        # The whole IDE follows the light/dark choice of the editor theme
        manager = theme_manager()
        manager.manage_application()
        icons.set_dark(manager.app_is_dark())
        manager.changed.connect(self._on_theme_changed)

        self.mdi = QMdiArea()
        self.mdi.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mdi.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.mdi.subWindowActivated.connect(self._on_subwindow_activated)
        self.setCentralWidget(self.mdi)

        self.toolbox = Toolbox()
        self.explorer = ProjectExplorer()
        self.properties = PropertiesWindow()
        self.immediate = ImmediateWindow()
        self.output = OutputWindow()  # the IDE's own stdout/stderr (hidden by default)
        self.outline = OutlineWindow()  # structure of the current file (hidden by default)
        self.toolbox_dock = self._dock("Toolbox", self.toolbox, Qt.LeftDockWidgetArea, "toolbox")
        self.explorer_dock = self._dock("Project", self.explorer, Qt.RightDockWidgetArea,
                                        "project")
        self.properties_dock = self._dock("Properties", self.properties,
                                          Qt.RightDockWidgetArea, "properties")
        self.immediate_dock = self._dock("Immediate", self.immediate, Qt.BottomDockWidgetArea,
                                         "immediate")
        self.output_dock = self._dock("Output", self.output, Qt.BottomDockWidgetArea, "output")
        self.outline_dock = self._dock("Outline", self.outline, Qt.RightDockWidgetArea,
                                       "outline")
        self.outline.lineChosen.connect(self._goto_outline_line)
        self.toolbox_dock.setFixedWidth(84)
        # Opening/closing the Project panel changes what Properties follows
        self.explorer_dock.visibilityChanged.connect(self._on_explorer_changed)

        self.toolbox.toolSelected.connect(self._on_tool_selected)
        self.toolbox.toolActivated.connect(self._on_tool_activated)
        self.explorer.openObject.connect(self.view_object)
        self.explorer.openCode.connect(self.view_code)
        self.explorer.removeFile.connect(self.remove_file)
        self.explorer.setStartup.connect(self._set_startup)
        self.explorer.addForm.connect(self.add_form)
        self.explorer.addModule.connect(self.add_module)
        # Bound methods, not lambdas: PySide disconnects those automatically
        # when the window is destroyed (the signals still fire during shutdown)
        self.explorer.tree.currentItemChanged.connect(self._on_explorer_changed)
        self._file_targets: dict[str, FileTarget] = {}
        self.project_target = ProjectTarget(
            lambda: self.project, self._form_names, self._project_changed)
        self.immediate.openLocation.connect(self.open_location)
        self.immediate.inputSubmitted.connect(self._send_input)

        self._create_actions()
        self._create_toolbar()  # before the menus: View > Toolbars refers to it
        self._create_menus()
        self.statusBar()
        self.resize(1280, 820)
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        self._default_layout()
        state = self.settings.value("state")
        if state is not None:
            self.restoreState(state)
        self._tab_bottom_docks()  # a layout saved before may have them side by side
        self._update_title()
        self._update_actions()
        self._apply_workspace_colors()

    # -- light / dark -----------------------------------------------------------------------------
    def _apply_workspace_colors(self):
        dark = theme_manager().app_is_dark()
        self.mdi.setBackground(QColor("#1f1f21" if dark else "#a3a8ae"))

    def _on_theme_changed(self):
        icons.set_dark(theme_manager().app_is_dark())
        for action, name in self._icon_actions:
            action.setIcon(icons.icon(name))
        self.toolbox.refresh_icons()
        self._update_theme_toggle()
        for sub in self.designer_windows.values():
            sub.setWindowIcon(icons.icon("Form"))
        for sub in self.code_windows.values():
            sub.setWindowIcon(icons.icon("Module"))
        self._refresh_explorer()
        self.properties.refresh()  # its editors have style sheets: rebuild them
        self._apply_workspace_colors()

    # -- UI construction --------------------------------------------------------------------------
    def _dock(self, title, widget, area, name) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        # Bound methods (not lambdas), so they're disconnected on shutdown
        dock.dockLocationChanged.connect(self._on_dock_moved)
        dock.topLevelChanged.connect(self._on_dock_moved)
        dock.visibilityChanged.connect(self._on_dock_moved)
        return dock

    # -- bottom edge: panels there are always tabs ---------------------------------------------
    def _on_dock_moved(self, *_):
        # Coalesce: dragging a panel emits several signals in a row
        if not getattr(self, "_bottom_tabs_pending", False):
            self._bottom_tabs_pending = True
            QTimer.singleShot(0, self, self._tab_bottom_docks)

    def _tab_bottom_docks(self):
        """When more than one open panel is docked at the bottom edge, join them
        into one tab group (a tab with the title of each, one body shown). Qt's
        ForceTabbedDocks would do this for every edge, but the right edge keeps
        Project and Properties stacked."""
        self._bottom_tabs_pending = False
        docks = [dock for dock in self.findChildren(QDockWidget)
                 if self.dockWidgetArea(dock) == Qt.BottomDockWidgetArea
                 and not dock.isFloating()
                 and dock.toggleViewAction().isChecked()]  # open, even if not the current tab
        if len(docks) < 2:
            return
        first = docks[0]
        grouped = {first, *self.tabifiedDockWidgets(first)}
        for dock in docks[1:]:
            if dock not in grouped:
                self.tabifyDockWidget(first, dock)  # adds it as a tab and shows it
                grouped.add(dock)

    def _action(self, text, slot, shortcut=None, icon=None, tip=None) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        if icon is not None:
            action.setIcon(icons.icon(icon))  # icon name; redrawn on theme changes
            self._icon_actions.append((action, icon))
        if tip:
            action.setStatusTip(tip)
        action.triggered.connect(slot)
        return action

    def _create_actions(self):
        a = self._action
        self.act_new = a("&New Project…", self.new_project, QKeySequence.New, "New")
        self.act_open = a("&Open Project…", self.open_project_dialog, QKeySequence.Open, "Open")
        self.act_save = a("&Save Project", self.save_all, QKeySequence.Save, "Save")
        self.act_close = a("&Close Project", self.close_project)
        self.act_add_form = a("Add &Form", self.add_form, None, "Form")
        self.act_add_module = a("Add &Module", self.add_module, None, "Module")
        self.act_add_file = a("Add F&ile…", self.add_file, "Ctrl+D")
        self.act_project_props = a("Project P&roperties…", self.project_properties)
        self.act_exit = a("E&xit", self.close, QKeySequence.Quit)

        self.act_undo = a("&Undo", lambda: self._edit("undo"), QKeySequence.Undo)
        self.act_redo = a("&Redo", lambda: self._edit("redo"), QKeySequence.Redo)
        self.act_cut = a("Cu&t", lambda: self._edit("cut"), QKeySequence.Cut)
        self.act_copy = a("&Copy", lambda: self._edit("copy"), QKeySequence.Copy)
        self.act_paste = a("&Paste", lambda: self._edit("paste"), QKeySequence.Paste)
        self.act_delete = a("&Delete", lambda: self._edit("delete"), QKeySequence.Delete)
        self.act_select_all = a("Select &All", lambda: self._edit("select_all"),
                                QKeySequence.SelectAll)
        self.act_find = a("&Find…", self.show_find, QKeySequence.Find)
        # F3 / Shift+F3 like VB6 on every platform: the standard keys include
        # Ctrl+G (Cmd+G on macOS), which is the Immediate window's
        self.act_find_next = a("Find &Next", self.find_next, "F3")
        self.act_find_previous = a("Find Pre&vious", self.find_previous, "Shift+F3")
        self.act_replace = a("R&eplace…", self.show_replace)
        # Ctrl+H like VB6; on macOS Cmd+H hides the app, so Cmd+Option+F like Xcode
        self.act_replace.setShortcut(QKeySequence(
            "Ctrl+Alt+F" if sys.platform == "darwin" else "Ctrl+H"))
        self.act_goto_line = a("&Go to Line…", self.goto_line, "Ctrl+L")
        self.act_menu_editor = a("&Menu Editor…", self.show_menu_editor, "Ctrl+E",
                                 tip="Design the menus of the current form")

        self.act_view_code = a("&Code", lambda: self._view_current("code"), "F7")
        self.act_view_object = a("O&bject", lambda: self._view_current("object"), "Shift+F7")
        self.act_view_project = a("Project E&xplorer", lambda: self._show_dock(
            self.explorer_dock), "Ctrl+R")
        self.act_view_props = a("Properties &Window", self._show_properties, "F4")
        self.act_view_toolbox = a("Toolbo&x", lambda: self._show_dock(self.toolbox_dock))
        self.act_view_immediate = a("&Immediate Window", lambda: self._show_dock(
            self.immediate_dock), "Ctrl+G")
        self.act_view_output = a("O&utput Window", lambda: self._show_dock(self.output_dock),
                                 tip="The IDE's own output, including library messages")
        self.act_view_outline = a("Outli&ne Window", self._show_outline,
                                  tip="The structure of the current file")

        self.act_run = a("&Start", self.run_project, "F5", "Run", "Run the project")
        # Also Cmd+Enter on macOS / Ctrl+Enter elsewhere (Qt's "Ctrl" is Command on macOS),
        # from the main keyboard or the keypad
        self.act_run.setShortcuts([QKeySequence("F5"), QKeySequence("Ctrl+Return"),
                                   QKeySequence("Ctrl+Enter")])
        self.act_run.setToolTip("Run the project (F5 or " +
                                QKeySequence("Ctrl+Return").toString(
                                    QKeySequence.NativeText) + ")")
        self.act_end = a("&End", self.stop_project, None, "Stop", "Stop the running program")
        self.act_restart = a("&Restart", self.restart_project, "Shift+F5")

    def _create_menus(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        for act in (self.act_new, self.act_open, None, self.act_save, self.act_close, None,
                    self.act_exit):
            file_menu.addSeparator() if act is None else file_menu.addAction(act)
        self.recent_menu = file_menu.addMenu("Recent Projects")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)

        edit = bar.addMenu("&Edit")
        for act in (self.act_undo, self.act_redo, None, self.act_cut, self.act_copy,
                    self.act_paste, self.act_delete, None, self.act_select_all, None,
                    self.act_find, self.act_find_next, self.act_find_previous,
                    self.act_replace, None, self.act_goto_line):
            edit.addSeparator() if act is None else edit.addAction(act)

        view = bar.addMenu("&View")
        for act in (self.act_view_code, self.act_view_object, None, self.act_view_immediate,
                    self.act_view_output, self.act_view_project, self.act_view_props,
                    self.act_view_outline, self.act_view_toolbox):
            view.addSeparator() if act is None else view.addAction(act)
        view.addSeparator()
        toolbars = view.addMenu("Tool&bars")
        toolbars.addAction(self.toolbar.toggleViewAction())
        view.addAction(self._action("&Reset Window Layout", self.reset_layout))
        view.addSeparator()
        self.theme_menu = view.addMenu("Editor &Theme")
        self.theme_menu.aboutToShow.connect(self._fill_theme_menu)
        self.view_menu = view

        project = bar.addMenu("&Project")
        for act in (self.act_add_form, self.act_add_module, self.act_add_file, None,
                    self.act_project_props):
            project.addSeparator() if act is None else project.addAction(act)

        fmt = bar.addMenu("F&ormat")
        align = fmt.addMenu("&Align")
        for text, how in (("&Lefts", "left"), ("&Centers", "center"), ("&Rights", "right"),
                          ("&Tops", "top"), ("&Middles", "middle"), ("&Bottoms", "bottom"),
                          ("to &Grid", "grid")):
            align.addAction(text, lambda h=how: self._designer_call("align", h))
        size = fmt.addMenu("&Make Same Size")
        for text, how in (("&Width", "width"), ("&Height", "height"), ("&Both", "both")):
            size.addAction(text, lambda h=how: self._designer_call("make_same_size", h))
        center = fmt.addMenu("&Center in Form")
        center.addAction("&Horizontally", lambda: self._designer_call("center_in_form", True))
        center.addAction("&Vertically", lambda: self._designer_call("center_in_form", False))
        order = fmt.addMenu("&Order")
        order.addAction(self._action("&Bring to Front",
                                     lambda: self._designer_call("z_order", True), "Ctrl+J"))
        order.addAction(self._action("&Send to Back",
                                     lambda: self._designer_call("z_order", False), "Ctrl+K"))

        run = bar.addMenu("&Run")
        for act in (self.act_run, self.act_end, self.act_restart):
            run.addAction(act)

        tools = bar.addMenu("&Tools")
        tools.addAction(self.act_menu_editor)
        tools.addSeparator()
        tools.addAction(self._action("&Options…", self.show_options, QKeySequence.Preferences))

        window = bar.addMenu("&Window")
        window.addAction("&Cascade", self.mdi.cascadeSubWindows)
        window.addAction("&Tile", self.mdi.tileSubWindows)
        self.act_tabbed = QAction("Ta&bbed Documents", self, checkable=True)
        self.act_tabbed.toggled.connect(self._set_tabbed)
        window.addAction(self.act_tabbed)
        if self.settings.value("tabbed", False, bool):
            self.act_tabbed.setChecked(True)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction("&About VP6", lambda: QMessageBox.about(self, "About VP6",
                                                                     ABOUT_HTML))

    def _create_toolbar(self):
        toolbar = self.toolbar = self.addToolBar("Standard")
        toolbar.setObjectName("standard")
        toolbar.setMovable(False)
        for act in (self.act_new, self.act_add_form, self.act_add_module, self.act_open,
                    self.act_save, None, self.act_run, self.act_end):
            toolbar.addSeparator() if act is None else toolbar.addAction(act)
        # Light/dark switch at the right end
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        self.act_theme_toggle = QAction(self)
        self.act_theme_toggle.triggered.connect(self.toggle_dark_mode)
        toolbar.addAction(self.act_theme_toggle)
        self._update_theme_toggle()

    def toggle_dark_mode(self):
        """Switch to the opposite look, using the themes chosen for light and
        dark in Tools > Options (so custom themes are respected)."""
        manager = theme_manager()
        state = manager.state
        manager.select(state.system_light if manager.app_is_dark() else state.system_dark)

    def _update_theme_toggle(self):
        dark = theme_manager().app_is_dark()
        # Show what a click switches to: the sun in dark mode, the moon in light mode
        self.act_theme_toggle.setIcon(icons.icon("Sun" if dark else "Moon"))
        tip = "Switch to the light theme" if dark else "Switch to the dark theme"
        self.act_theme_toggle.setText(tip)
        self.act_theme_toggle.setToolTip(tip)
        self.act_theme_toggle.setStatusTip(tip)

    def _default_layout(self):
        """Toolbar and panels in their default places (also View > Reset
        Window Layout, to recover anything hidden, closed or undocked)."""
        self.toolbar.show()
        for dock, area in ((self.toolbox_dock, Qt.LeftDockWidgetArea),
                           (self.explorer_dock, Qt.RightDockWidgetArea),
                           (self.properties_dock, Qt.RightDockWidgetArea),
                           (self.immediate_dock, Qt.BottomDockWidgetArea)):
            dock.setFloating(False)
            self.addDockWidget(area, dock, Qt.Vertical)
            dock.show()
        # The Output window shares the bottom area with the Immediate window, as a
        # tab, and is hidden by default (View > Output Window)
        self.output_dock.setFloating(False)
        self.tabifyDockWidget(self.immediate_dock, self.output_dock)
        self.output_dock.hide()
        self.immediate_dock.raise_()
        self._place_outline()  # under Properties, hidden by default (View > Outline Window)
        self.outline_dock.hide()
        self.resizeDocks([self.immediate_dock], [150], Qt.Vertical)
        self.resizeDocks([self.explorer_dock, self.properties_dock], [180, 420], Qt.Vertical)
        self.resizeDocks([self.properties_dock], [290], Qt.Horizontal)

    def reset_layout(self):
        self._default_layout()
        self.settings.remove("state")
        self.settings.remove("geometry")

    def _fill_theme_menu(self):
        manager = theme_manager()
        self.theme_menu.clear()
        group = QActionGroup(self.theme_menu)
        for label, value in [("System (follow appearance)", SYSTEM)] + \
                [(name, name) for name in manager.state.themes]:
            action = self.theme_menu.addAction(label, lambda v=value: manager.select(v))
            action.setCheckable(True)
            action.setChecked(manager.state.selection == value)
            group.addAction(action)
        self.theme_menu.addSeparator()
        self.theme_menu.addAction("Customize…", self.show_options)

    def show_options(self):
        OptionsDialog(self).exec()

    def _set_tabbed(self, tabbed: bool):
        self.mdi.setViewMode(QMdiArea.TabbedView if tabbed else QMdiArea.SubWindowView)
        if tabbed:
            self.mdi.setTabsClosable(True)
            self.mdi.setTabsMovable(True)
        self.settings.setValue("tabbed", tabbed)

    def _show_dock(self, dock: QDockWidget):
        dock.show()
        dock.raise_()

    def _show_properties(self):
        self._show_dock(self.properties_dock)
        self.properties.table.setFocus()

    # -- state -------------------------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self.process is not None

    def _update_title(self):
        if self.project is None:
            self.setWindowTitle("VP6")
            return
        mode = "run" if self.running else "design"
        self.setWindowTitle(f"{self.project.name} - VP6 [{mode}]")

    def _update_actions(self):
        has_project = self.project is not None
        for act in (self.act_save, self.act_close, self.act_add_form, self.act_add_module,
                    self.act_add_file, self.act_project_props):
            act.setEnabled(has_project)
        self.act_run.setEnabled(has_project and not self.running)
        self.act_restart.setEnabled(has_project)
        self.act_end.setEnabled(self.running)

    def _doc_display_name(self, doc: Document) -> str:
        return doc.name

    def _refresh_explorer(self):
        names = {path: self._doc_display_name(doc) for path, doc in self.documents.items()}
        project_was_selected = self.explorer.project_selected()
        selected_path, _kind = self.explorer._current()
        self.explorer.populate(self.project, names)
        if project_was_selected:
            self.explorer.select_project()
        elif selected_path in self.documents:  # keep what was selected
            self.explorer.select_path(selected_path)
        else:
            active = self._active_widget()  # keep the active window's file selected
            if active is not None:
                self.explorer.select_path(self._path_of(active))
        self._update_properties_target()

    def _update_window_titles(self):
        if self.project is None:
            return
        for path, sub in list(self.designer_windows.items()) + list(self.code_windows.items()):
            doc = self.documents.get(path)
            if doc is None:
                continue
            kind = "Form" if path in self.designer_windows and \
                sub is self.designer_windows[path] else "Code"
            star = "*" if doc.modified else ""
            sub.setWindowTitle(f"{self.project.name} - {doc.name} ({kind}){star}")

    # -- recent projects ----------------------------------------------------------------------------
    def recent_projects(self) -> list[str]:
        value = self.settings.value("recent", [])
        if isinstance(value, str):
            value = [value]
        return [p for p in value or [] if isinstance(p, str)]

    def _remember(self, path: str):
        recent = [p for p in self.recent_projects() if p != path]
        self.settings.setValue("recent", [path] + recent[:9])

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        for path in self.recent_projects():
            self.recent_menu.addAction(path, lambda p=path: self._open_if_closed(p))

    def _open_if_closed(self, path):
        if self.close_project():
            self.open_project(path)

    # -- project lifecycle ------------------------------------------------------------------------------
    def show_start_dialog(self):
        dialog = NewProjectDialog(self.recent_projects(), self)
        if dialog.exec():
            self._handle_project_dialog(dialog)

    def new_project(self):
        dialog = NewProjectDialog(self.recent_projects(), self)
        if dialog.exec() and self.close_project():
            self._handle_project_dialog(dialog)

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "",
                                              f"VP6 projects (*{EXTENSION})")
        if path and self.close_project():
            self.open_project(path)

    def _handle_project_dialog(self, dialog: NewProjectDialog):
        if dialog.result_action == "open":
            self.open_project(dialog.open_path)
        elif dialog.result_action == "new":
            path = create_project(dialog.project_location, dialog.project_name, dialog.template)
            self.open_project(path)

    def open_project(self, path: str) -> bool:
        try:
            project = Project.load(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open Project", f"Can't open {path}:\n{exc}")
            return False
        self.project = project
        missing = []
        for relative in project.forms + project.modules:
            full = project.abspath(relative)
            try:
                self._add_document(open_document(full))
            except (OSError, formfile.FormFileError) as exc:
                missing.append(f"{relative}: {exc}")
        if missing:
            QMessageBox.warning(self, "Open Project",
                                "Some files could not be loaded:\n\n" + "\n".join(missing))
        self._remember(project.path)
        self._refresh_explorer()
        self._update_title()
        self._update_actions()
        # Show the startup object. A windowed project opens a form's designer: the
        # startup form, or the first form when it starts in Sub Main (which
        # normally shows that form). A console project opens its Main module.
        forms = [p for p, d in self.documents.items() if isinstance(d, FormDocument)]
        startup_form = next((p for p in forms if self.documents[p].name == project.startup),
                            None)
        if project.type != "console" and (startup_form or forms):
            self.view_object(startup_form or forms[0])
        elif project.startup == SUB_MAIN:
            module = next((p for p, d in self.documents.items()
                           if "def Main(" in d.text), None)
            if module:
                self.view_code(module)
        elif startup_form:
            self.view_object(startup_form)
        self.statusBar().showMessage(f"Opened {project.path}", 5000)
        return True

    def _add_document(self, doc: Document):
        self.documents[doc.path] = doc
        doc.modifiedChanged.connect(lambda *_: self._update_window_titles())
        if isinstance(doc, FormDocument):
            doc.parseError.connect(
                lambda msg: self.statusBar().showMessage(f"Designer region: {msg}", 6000))

    def _confirm_save(self) -> bool:
        """Ask to save modified files. Returns False if the user cancelled."""
        modified = [d for d in self.documents.values() if d.modified]
        if not modified:
            return True
        names = "\n".join(d.filename for d in modified)
        answer = QMessageBox.question(
            self, "VP6", f"Save changes to the following files?\n\n{names}",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_all()
        return True

    def close_project(self) -> bool:
        if self.project is None:
            return True
        if self.running:
            self.stop_project()
        if not self._confirm_save():
            return False
        self.properties.set_designer(None)
        self._last_designer = None
        for sub in self.mdi.subWindowList():
            sub.setAttribute(Qt.WA_DeleteOnClose, True)
            sub.close()
        self._discard_designers(list(self._designers))
        self.designer_windows.clear()
        self.code_windows.clear()
        self.documents.clear()
        self._file_targets.clear()
        self.project = None
        self._refresh_explorer()
        self._update_title()
        self._update_actions()
        return True

    def save_all(self) -> bool:
        if self.project is None:
            return False
        try:
            for doc in self.documents.values():
                if doc.modified:
                    doc.save()
            self.project.save()
        except OSError as exc:
            QMessageBox.critical(self, "Save", str(exc))
            return False
        self._update_window_titles()
        self.statusBar().showMessage("Project saved", 3000)
        return True

    def project_properties(self):
        if self.project is None:
            return
        dialog = ProjectPropertiesDialog(self.project, self._form_names(), self)
        if dialog.exec():
            dialog.apply(self.project)
            self._project_changed()
            self.project_target.designChanged.emit()

    def _project_changed(self):
        """The project's properties changed (dialog or Properties window)."""
        self.project.save()
        for designer in self._designers.values():
            designer.set_project_scheme(self._project_scheme())
        self._refresh_explorer()
        self._update_title()
        self._update_window_titles()

    def _form_names(self) -> list[str]:
        return [d.name for d in self.documents.values() if isinstance(d, FormDocument)]

    # -- what the Properties panel shows ---------------------------------------------------
    def _context_path(self) -> str | None:
        """The file the Properties and Outline panels are about: the one
        selected in the Project panel while it's open, else the file of the
        active window. None for the project, a folder or no selection."""
        if self.project is None:
            return None
        if self.explorer_dock.isVisibleTo(self):
            path, _kind = self.explorer._current()
            return path
        widget = self._active_widget()
        return self._path_of(widget) if widget is not None else None

    def _properties_target(self):
        """With the Project panel open, Properties follows its selection: the
        project, a form (its designer, or just its Name if the designer isn't
        open) or a module (its Name); nothing for folders or no selection.
        With the Project panel closed, it follows the active window."""
        if self.project is None:
            return None
        if self.explorer_dock.isVisibleTo(self) and self.explorer.project_selected():
            return self.project_target
        path = self._context_path()
        return self._target_for_path(path) if path else None

    def _target_for_path(self, path: str):
        doc = self.documents.get(path)
        if doc is None:
            return None
        if isinstance(doc, FormDocument):
            return self._designer_for(path)  # open or not: all the form's properties
        if path not in self._file_targets:
            self._file_targets[path] = FileTarget(doc, self._rename_file_object)
        return self._file_targets[path]

    def _update_properties_target(self):
        """Point the Properties and Outline panels at the current context."""
        self.properties.set_designer(self._properties_target())
        path = self._context_path()
        self.outline.set_document(self.documents.get(path) if path else None)

    # -- Outline window ---------------------------------------------------------------------------
    def _place_outline(self):
        """Dock the Outline window right under the Properties panel."""
        self.outline_dock.setFloating(False)
        if self.properties_dock.isVisibleTo(self) and \
                self.dockWidgetArea(self.properties_dock) != Qt.NoDockWidgetArea and \
                not self.properties_dock.isFloating():
            self.splitDockWidget(self.properties_dock, self.outline_dock, Qt.Vertical)
        else:
            self.addDockWidget(Qt.RightDockWidgetArea, self.outline_dock)

    def _show_outline(self):
        """View > Outline Window: opens under the Properties panel."""
        if self.outline_dock.isHidden():
            self._place_outline()
        self._show_dock(self.outline_dock)

    def _goto_outline_line(self, line: int):
        """Clicking an outline item: that line in the file's code window."""
        document = self.outline.document
        if document is None:
            return
        window = self.view_code(document.path)
        if window is not None:
            window.editor.goto_line(line)

    def _on_explorer_changed(self, *_):
        self._update_properties_target()

    def _on_designer_selection(self, designer: FormDesigner):
        """Working in a designer selects its form in the explorer, so the
        Properties panel shows the designer's selection."""
        path = self._path_of(designer)
        if path is not None:
            self.explorer.select_path(path)
        self._update_properties_target()

    # -- renaming from the Properties panel ------------------------------------------------------
    def _rename_file_object(self, doc: Document, new_name: str) -> str | None:
        """(Name) of a FileTarget: a form's class, or a module's file."""
        if not is_identifier(new_name):
            return f"'{new_name}' is not a valid name"
        if new_name == doc.name:
            return None
        if isinstance(doc, FormDocument):
            if new_name in self._form_names():
                return f"The name '{new_name}' is already used"
            old = doc.name
            doc.replace_text(formfile.rename_form_class(doc.text, old, new_name))
            self._on_form_renamed(old, new_name)
            return None
        return self._rename_module(doc, new_name)

    def _rename_module(self, doc: Document, new_name: str) -> str | None:
        """A module's name is its file name (what `import` uses): rename the
        file, the project entry and imports of it in the other files."""
        old_name, old_path = doc.name, doc.path
        new_path = os.path.join(os.path.dirname(old_path), new_name + ".py")
        clash = any(d is not doc and d.name.lower() == new_name.lower()
                    for d in self.documents.values())
        if clash or (os.path.exists(new_path) and new_name.lower() != old_name.lower()):
            return f"The name '{new_name}' is already used"
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
        doc.path = new_path
        for table in (self.documents, self.code_windows, self.designer_windows,
                      self._designers, self._file_targets):
            if old_path in table:
                table[new_path] = table.pop(old_path)
        old_rel = os.path.relpath(old_path, self.project.directory)
        self.project.modules = [os.path.relpath(new_path, self.project.directory)
                                if m == old_rel else m for m in self.project.modules]
        for other in self.documents.values():
            if other is not doc:
                other.replace_text(
                    formfile.rename_module_references(other.text, old_name, new_name))
        self.project.save()
        self._refresh_explorer()
        self.explorer.select_path(new_path)
        self._update_window_titles()
        return None

    def _project_scheme(self) -> int:
        return scheme_from_name(self.project.color_scheme if self.project else None)

    def _set_startup(self, name: str):
        if self.project:
            self.project.startup = name
            self.project.save()
            self._refresh_explorer()

    def _unique_file(self, base: str) -> tuple[str, str]:
        taken = {d.name for d in self.documents.values()}
        i = 1
        while f"{base}{i}" in taken or os.path.exists(self.project.abspath(f"{base}{i}.py")):
            i += 1
        return f"{base}{i}", f"{base}{i}.py"

    def add_form(self):
        if self.project is None:
            return
        name, filename = self._unique_file("Form")
        path = self.project.abspath(filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(formfile.new_form_source(name))
        self.project.forms.append(filename)
        self.project.save()
        self._add_document(open_document(path))
        self._refresh_explorer()
        self.view_object(path)

    def add_module(self):
        if self.project is None:
            return
        name, filename = self._unique_file("Module")
        path = self.project.abspath(filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(formfile.new_module_source())
        self.project.modules.append(filename)
        self.project.save()
        self._add_document(open_document(path))
        self._refresh_explorer()
        self.view_code(path)

    def add_file(self):
        if self.project is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Add File", self.project.directory,
                                              "Python files (*.py)")
        if not path:
            return
        relative = os.path.relpath(path, self.project.directory)
        if relative.startswith(".."):
            target = self.project.abspath(os.path.basename(path))
            if os.path.exists(target):
                QMessageBox.warning(self, "Add File", f"{os.path.basename(path)} already exists "
                                                      "in the project folder.")
                return
            shutil.copy(path, target)
            path, relative = target, os.path.basename(path)
        if os.path.abspath(path) in self.documents:
            return
        doc = open_document(path)
        (self.project.forms if isinstance(doc, FormDocument) else self.project.modules).append(
            relative)
        self.project.save()
        self._add_document(doc)
        self._refresh_explorer()

    def remove_file(self, path: str):
        doc = self.documents.get(path)
        if doc is None or self.project is None:
            return
        if doc.modified:
            answer = QMessageBox.question(self, "Remove", f"Save changes to {doc.filename}?",
                                          QMessageBox.Save | QMessageBox.Discard |
                                          QMessageBox.Cancel)
            if answer == QMessageBox.Cancel:
                return
            if answer == QMessageBox.Save:
                doc.save()
        self._discard_designers([path])  # before its window is forgotten
        for windows in (self.designer_windows, self.code_windows):
            sub = windows.pop(path, None)
            if sub is not None:
                sub.setAttribute(Qt.WA_DeleteOnClose, True)
                sub.close()
        relative = os.path.relpath(path, self.project.directory)
        for files in (self.project.forms, self.project.modules):
            if relative in files:
                files.remove(relative)
        del self.documents[path]
        self._file_targets.pop(path, None)
        self.project.save()
        self._refresh_explorer()

    # -- windows ------------------------------------------------------------------------------------------
    def _add_subwindow(self, widget, icon_name) -> QMdiSubWindow:
        sub = self.mdi.addSubWindow(widget)
        sub.setAttribute(Qt.WA_DeleteOnClose, False)
        sub.setWindowIcon(icons.icon(icon_name))
        sub.resize(760, 520)
        return sub

    def _activate(self, sub: QMdiSubWindow):
        # Closing a subwindow keeps it for reuse (WA_DeleteOnClose is off), but
        # Qt also closes - i.e. hides - the widget inside it. Show both, or a
        # reopened code window or designer would be an empty frame.
        sub.widget().show()
        sub.show()
        if sub.isMinimized():
            sub.showNormal()
        self.mdi.setActiveSubWindow(sub)
        sub.widget().setFocus()
        # Also here, not only on subWindowActivated: that isn't emitted while
        # the main window itself is inactive (e.g. at startup)
        self.explorer.select_path(self._path_of(sub.widget()))

    def _designer_for(self, path: str) -> FormDesigner:
        """The form's designer, created (not shown) if it doesn't exist yet."""
        designer = self._designers.get(path)
        if designer is None:
            designer = FormDesigner(self.documents[path], self.project.directory, self,
                                    project_scheme=self._project_scheme())
            designer.hide()  # until View Object puts it in a window
            designer.set_tool(self.current_tool)
            # (captures the document, not the designer: no reference cycle)
            designer.form_name_taken = lambda name, doc=designer.document: any(
                other is not doc and other.name == name
                for other in self.documents.values() if isinstance(other, FormDocument))
            designer.viewCodeRequested.connect(
                lambda obj, event, d=designer: self._open_handler(self._path_of(d), obj, event))
            designer.toolConsumed.connect(self.toolbox.reset)
            designer.selectionChanged.connect(
                lambda d=designer: self._on_designer_selection(d))
            designer.formRenamed.connect(self._on_form_renamed)
            designer.statusMessage.connect(lambda m: self.statusBar().showMessage(m, 5000))
            self._designers[path] = designer
        return designer

    def _discard_designers(self, paths: list[str]) -> None:
        """Forget these forms' designers; delete those not in a window (a
        closed window deletes its own)."""
        for path in paths:
            designer = self._designers.pop(path, None)
            if designer is None:
                continue
            if self.properties.designer is designer:
                self.properties.set_designer(None)
            if self._last_designer is designer:
                self._last_designer = None
            if path not in self.designer_windows:
                designer.deleteLater()

    def view_object(self, path: str) -> FormDesigner | None:
        doc = self.documents.get(path)
        if not isinstance(doc, FormDocument):
            return None
        sub = self.designer_windows.get(path)
        if sub is None:
            sub = self._add_subwindow(self._designer_for(path), "Form")
            self.designer_windows[path] = sub
            self._update_window_titles()
        self._activate(sub)
        return sub.widget()

    def view_code(self, path: str) -> CodeWindow | None:
        doc = self.documents.get(path)
        if doc is None:
            return None
        sub = self.code_windows.get(path)
        if sub is None:
            window = CodeWindow(doc)
            sub = self._add_subwindow(window, "Module")
            self.code_windows[path] = sub
            self._update_window_titles()
        self._activate(sub)
        return sub.widget()

    def _open_handler(self, path: str, obj: str, event: str):
        window = self.view_code(path)
        if window is not None:
            window.goto_event(obj, event)

    def open_location(self, path: str, line: int):
        path = os.path.abspath(path)
        if path in self.documents:
            window = self.view_code(path)
            window.editor.goto_line(line)

    def _active_widget(self):
        sub = self.mdi.activeSubWindow()
        return sub.widget() if sub is not None else None

    def _path_of(self, widget) -> str | None:
        for windows in (self.designer_windows, self.code_windows):
            for path, sub in windows.items():
                if sub.widget() is widget:
                    return path
        return next((p for p, d in self._designers.items() if d is widget), None)

    def _view_current(self, which: str):
        widget = self._active_widget()
        path = self._path_of(widget) if widget is not None else None
        if path is None:
            path, _ = self.explorer._current()
        if path is None:
            return
        if which == "code":
            self.view_code(path)
        else:
            self.view_object(path)

    def _on_subwindow_activated(self, sub):
        if sub is None:
            return
        widget = sub.widget()
        self.explorer.select_path(self._path_of(widget))
        if isinstance(widget, FormDesigner):
            self._last_designer = widget
            widget.set_tool(self.current_tool)
        # A form's code window shows the form's properties, like VB
        self._update_properties_target()

    def _on_form_renamed(self, old: str, new: str):
        # Other files refer to the form class, e.g. Module1's
        # `from Form1 import Form1` / `run(Form1)`: rename those references too
        renamed = next((p for p, d in self.documents.items()
                        if isinstance(d, FormDocument) and d.name == new), None)
        for path, doc in self.documents.items():
            if path != renamed:
                doc.replace_text(formfile.rename_class_references(doc.text, old, new))
        if self.project and self.project.startup == old:
            self.project.startup = new
            self.project.save()
        self._refresh_explorer()
        self._update_window_titles()

    # -- toolbox / designer routing -------------------------------------------------------------------
    def _on_tool_selected(self, tool):
        self.current_tool = tool
        for designer in self._designers.values():
            designer.set_tool(tool)

    def _on_tool_activated(self, tool: str):
        designer = self._last_designer
        if designer is not None:
            designer.add_control_centered(tool)

    def _designer_call(self, method: str, *args):
        widget = self._active_widget()
        if isinstance(widget, FormDesigner):
            getattr(widget, method)(*args)

    def _edit(self, op: str):
        focus = QApplication.focusWidget()
        widget = self._active_widget()
        in_window = widget is not None and focus is not None and \
            (focus is widget or widget.isAncestorOf(focus))
        if not in_window and isinstance(focus, (QLineEdit, QPlainTextEdit)):
            # A text field outside the MDI area (property editor, Immediate input)
            if op == "delete":
                if isinstance(focus, QLineEdit):
                    focus.del_()
                elif not focus.isReadOnly():
                    focus.textCursor().removeSelectedText()
            else:
                getattr(focus, {"select_all": "selectAll"}.get(op, op))()
            return
        if isinstance(widget, FormDesigner):
            {"undo": widget.undo, "redo": widget.redo, "cut": widget.cut_selection,
             "copy": widget.copy_selection, "paste": widget.paste,
             "delete": widget.delete_selection, "select_all": widget.select_all}[op]()
        elif isinstance(widget, CodeWindow):
            editor = widget.editor
            if op == "delete":
                if editor._edit_allowed():
                    editor.textCursor().removeSelectedText()
            else:
                getattr(editor, {"select_all": "selectAll"}.get(op, op))()

    # -- Find / Replace / Go to Line --------------------------------------------------------------------
    def _code_editor(self, open_code: bool = True):
        """The editor of the current code window. With a form designer current,
        its form's code window (opened if needed); None otherwise."""
        sub = self.mdi.currentSubWindow()  # also while the Find dialog is active
        widget = sub.widget() if sub is not None else None
        if isinstance(widget, CodeWindow):
            return widget.editor
        path = self._path_of(widget) if widget is not None else None
        if path is not None and open_code:
            window = self.view_code(path)
            return window.editor if window is not None else None
        return None

    def _find_dialog(self) -> FindReplaceDialog:
        if self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(self._code_editor, self)
        return self.find_dialog

    def show_find(self):
        self._code_editor()
        self._find_dialog().show_find(replace=False)

    def show_replace(self):
        self._code_editor()
        self._find_dialog().show_find(replace=True)

    def _find_again(self, backward: bool):
        dialog = self._find_dialog()
        if not dialog.find_edit.text():
            self.show_find()
            return
        result = dialog.find_previous() if backward else dialog.find_next()
        if result.message:
            self.statusBar().showMessage(result.message, 4000)

    def find_next(self):
        self._find_again(backward=False)

    def find_previous(self):
        self._find_again(backward=True)

    def _current_designer(self) -> FormDesigner | None:
        """The active designer, or the designer of the form whose code window
        is active (not necessarily open)."""
        sub = self.mdi.currentSubWindow()
        widget = sub.widget() if sub is not None else None
        if isinstance(widget, FormDesigner):
            return widget
        path = self._path_of(widget) if widget is not None else None
        if path is not None and isinstance(self.documents.get(path), FormDocument):
            return self._designer_for(path)
        return None

    def show_menu_editor(self):
        """Tools > Menu Editor (Ctrl+E), for the current form."""
        designer = self._current_designer()
        if designer is None:
            self.statusBar().showMessage("Open a form to design its menus", 4000)
            return
        designer.show_menu_editor()

    def goto_line(self):
        editor = self._code_editor()
        if editor is None:
            self.statusBar().showMessage("Open a code window to go to a line", 4000)
            return
        line = ask_line(editor, self)
        if line is not None:
            editor.goto_line(line)

    # -- running ----------------------------------------------------------------------------------------------
    def run_project(self):
        if self.project is None or self.running:
            return
        if not self.save_all():
            return
        self._show_dock(self.immediate_dock)
        self.immediate.append(f"▶ Running {self.project.name}…\n", "info")
        process = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        python_path = env.value("PYTHONPATH", "")
        env.insert("PYTHONPATH", VP6_ROOT + (os.pathsep + python_path if python_path else ""))
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        # Forms set to the "IDE" color scheme take the IDE's appearance at launch
        env.insert(IDE_SCHEME_ENV, SCHEME_NAMES[theme_manager().ide_scheme()])
        process.setProcessEnvironment(env)
        process.setWorkingDirectory(self.project.directory)
        pump_process_output(process, self.immediate)
        process.finished.connect(self._on_process_finished)
        process.errorOccurred.connect(self._on_process_error)
        self.process = process
        # The project file is itself the program's launcher script
        process.start(sys.executable, ["-u", self.project.path])
        self.immediate.set_running(self.project.type == "console")
        self._update_title()
        self._update_actions()

    def stop_project(self):
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(2000)

    def restart_project(self):
        if self.running:
            self.process.finished.connect(lambda *_: self.run_project())
            self.stop_project()
        else:
            self.run_project()

    def _send_input(self, text: str):
        if self.process is not None:
            self.process.write((text + "\n").encode("utf-8"))

    def _on_process_finished(self, code, status):
        process = self.process
        if process is not None:
            rest_out = bytes(process.readAllStandardOutput()).decode("utf-8", "replace")
            rest_err = bytes(process.readAllStandardError()).decode("utf-8", "replace")
            if rest_out:
                self.immediate.append(rest_out)
            if rest_err:
                self.immediate.append(rest_err, "err")
        how = "was stopped" if status == QProcess.CrashExit else f"exited with code {code}"
        self.immediate.append(f"■ Program {how}.\n", "info")
        self.process = None
        self.immediate.set_running(False)
        self._update_title()
        self._update_actions()

    def _on_process_error(self, error):
        if error == QProcess.FailedToStart:
            self.immediate.append(f"Failed to start {sys.executable}\n", "err")
            self.process = None
            self._update_title()
            self._update_actions()

    # -- closing ---------------------------------------------------------------------------------------------------
    def closeEvent(self, event):
        if not self.close_project():
            event.ignore()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("state", self.saveState())
        event.accept()


def create_project(location: str, name: str, template: str) -> str:
    """Create a new project folder from a template; returns the .vp6p path."""
    # Every new project has Form1 and Module1, and starts in Module1's Main():
    # a console Main talks through print()/input(), a windowed one shows Form1.
    directory = os.path.join(location, name)
    os.makedirs(directory, exist_ok=True)
    if template == "kitchensink":
        project = kitchensink.create(directory, name)
        path = os.path.join(directory, name + EXTENSION)
        project.save(path)
        return path
    console = template == "console"
    with open(os.path.join(directory, "Form1.py"), "w", encoding="utf-8") as f:
        f.write(formfile.new_form_source("Form1"))
    with open(os.path.join(directory, "Module1.py"), "w", encoding="utf-8") as f:
        f.write(formfile.new_module_source(with_main=True, console=console,
                                           startup_form=None if console else "Form1"))
    project = Project(name=name, type="console" if console else "exe", startup=SUB_MAIN,
                      forms=["Form1.py"], modules=["Module1.py"])
    path = os.path.join(directory, name + EXTENSION)
    project.save(path)
    return path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    # Capture the IDE's stdout/stderr (for the Output window) before Qt starts,
    # so its startup messages are included. VP6_NO_OUTPUT_CAPTURE turns it
    # off, e.g. to see the last messages of a hard crash directly.
    capture = None if os.environ.get("VP6_NO_OUTPUT_CAPTURE") else OutputCapture()
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("VP6")
    app.setOrganizationName("VP6")
    window = MainWindow()
    # Ctrl+C in the terminal works like File > Exit (Quit VP6): unsaved
    # changes are still offered for saving
    window._interrupt_handler = install_interrupt_handler(window.act_exit.trigger, window)
    if capture is not None:
        capture.attach(window.output.append)
        app.aboutToQuit.connect(capture.stop)
    window.show()
    if len(argv) > 1 and os.path.exists(argv[1]):
        window.open_project(argv[1])
    else:
        window.show_start_dialog()
    return app.exec()
