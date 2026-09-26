# VP6 source reference

A file-by-file description of the code base: what each file is responsible
for, its main classes and functions, and how it connects to the rest.
Private helpers (leading `_`) are listed where they matter for understanding
or extending the code. For the big picture read
[architecture.md](architecture.md) first.

Line counts are approximate and only give a sense of size.

---

## Runtime library: `vp6/`

### `vp6/__init__.py` (≈30 lines)

The public API surface. It re-exports everything a program gets from
`from vp6 import *`:

* forms and controls,
* `MsgBox` / `InputBox`,
* the `App`, `Screen`, `Clipboard` and `Debug` objects, `DoEvents`, `End`,
  `Beep`,
* `RGB`, `QBColor` and the color constants,
* all `vp*` constants from `constants.py` and the `vpScheme*` constants.

It also defines `__version__`.

`__all__` also feeds the code editor: every exported name is highlighted as a
"VP6 name" and offered by completion (`codeeditor._VP6_NAMES`).

### `vp6/_props.py` (≈100 lines)

The declarative property system shared by forms and controls.

| Name | Purpose |
|---|---|
| `PropSpec(name, kind, default, choices, always, description)` | Frozen dataclass describing one designable property. |
| `P(...)` | Short constructor for `PropSpec`. |
| `enum_choices(*labels)` | `((0, "0 - None"), (1, "1 - Fixed Single"), ...)` for `enum` properties. |
| `normalize(kind, value)` | Coerces a value to its kind (`str`, `int`, `bool`, `color` via `colors.normalize`, `list` from a list or newline-separated string). |
| `PropertyHost` | Base class. `__init_subclass__` builds `cls._specs` (name → spec) and generates a Python `property` per spec (unless the class defines one). `_init_values(props)` applies defaults and values in spec order and rejects unknown names. `_set_prop` normalizes, stores in `self._values` and calls `_apply_<Name>`. |

Hooks a subclass may define per property: `_apply_<Name>(value)` pushes the
value to the widget; `_read_<Name>()` returns the live value.

### `vp6/app.py` (≈180 lines)

Application-level services.

* `ensure_app()` creates the `QApplication` on first use. Every entry point
  that needs Qt calls it.
* `DoEvents()`, `Beep()`, `End()`. `End` closes all windows and calls
  `os._exit(0)`, like VB's `End`, without running `Form_Unload` handlers.
* Singleton objects:
  * `App`: `Title`, `Path` (folder of `__main__`), `EXEName`;
  * `Screen`: `Width`, `Height`, `ActiveForm`;
  * `Clipboard`: `GetText`, `SetText`, `Clear`;
  * `Debug`: `Debug.Print` prints to stdout, which the IDE shows in the
    Immediate window.
* `call_handler(handler, *args)` calls an event handler with only as many
  positional arguments as it declares (the count is cached per function).
  Exceptions go to `report_runtime_error`.
* `report_runtime_error(exc)` prints the traceback to stderr and shows a
  "Run-time error" box with End / Continue, unless the environment variable
  `VP6_NO_ERROR_DIALOG` is set.
* `run_event_loop()` runs `app.exec()` if any top-level window is visible.

### `vp6/appearance.py` (≈230 lines)

Light/dark color schemes for forms (see architecture §4.5).

* **Constants:**
  * `vpSchemeProjectDefault` (0), `vpSchemeSystem` (1), `vpSchemeLight` (2),
    `vpSchemeDark` (3), `vpSchemeIDE` (4);
  * `PROJECT_SCHEMES` (`"system"` → 1, …) and its inverse `SCHEME_NAMES`;
  * `IDE_SCHEME_ENV = "VP6_IDE_SCHEME"`.
* **Resolution:**
  * `resolve(scheme)` turns IDE into its current meaning and anything that
    isn't Light/Dark into System;
  * `ide_scheme()` uses `ide_scheme_provider` (set by the IDE), else the
    `VP6_IDE_SCHEME` environment variable, else System;
  * `project_scheme_for(directory)` uses `project_scheme` (set by the
    runner), else the first `*.vp6p` in the form's folder (cached), else
    System;
  * `scheme_from_name(name)` maps a project's `color_scheme` string.
* **OS appearance:**
  * `system_is_dark()` answers from Qt's color scheme normally, or from the
    OS (`_query_os_dark`) while the IDE forces the application's scheme;
  * `set_app_override()` and `app_override_active()` are the IDE's switch
    for that.
* **Styling:**
  * `fusion_style()` returns the shared Fusion style, parented to the app;
  * `scheme_palette(dark)` builds a complete light or dark palette;
  * `style_tree(widget, style)` sets (or resets, for `None`) the style on a
    widget and all descendants;
  * `match_dialog(dialog, parent)` gives a message box the scheme of the form
    under it.

### `vp6/colors.py` (≈60 lines)

VB-style colors: integers in `&H00BBGGRR` (BGR) order.

* `RGB(r, g, b)`, `QBColor(0..15)`.
* Constants `vpBlack`, `vpRed`, `vpGreen`, `vpYellow`, `vpBlue`, `vpMagenta`,
  `vpCyan`, `vpWhite`.
* `to_qcolor(value)` accepts an int, a `"#RRGGBB"` string, a Qt color name or
  a `QColor`. `from_qcolor(color)` converts back.
* `normalize(value)` converts any accepted form to a BGR int (`None` stays
  `None`, meaning the default color).

### `vp6/constants.py` (≈110 lines)

VB-compatible constants with a `vp` prefix, grouped by use:

* `MsgBox` buttons, icons, default buttons and results;
* `vpModal` / `vpModeless`;
* CheckBox values, mouse buttons and shift masks, alignment;
* form border styles, window states and start-up positions;
* string constants (`vpCrLf`, `vpTab`, …);
* key codes: `vpKeyA`..`vpKeyZ`, `vpKey0`..`vpKey9` and `vpKeyF1`..`vpKeyF12`
  are generated in loops.

`__all__` is every global starting with `vp`. The values are listed in
[api.md](api.md#constants).

### `vp6/controls.py` (≈1070 lines)

The intrinsic controls.

* **Module data:**
  * `EVENT_ARGS` maps each event name to the parameter list VB passes. The
    code window uses it to generate handler stubs.
  * `MOUSE_EVENTS`, `KEY_EVENTS`, `FOCUS_EVENTS`.
  * `CONTROL_TYPES`, at the end of the file: type name → class, in Toolbox
    order. The designer, form-file parser and Toolbox all use it.
* **Translation helpers:**
  * `vp_key_code(qt_key)` converts a Qt key to a VB key code
    (`_QT_TO_VP_KEYS`, letters and digits pass through);
  * `vp_shift(modifiers)` gives the bitmask 1 = Shift, 2 = Ctrl/Cmd,
    4 = Alt;
  * `vp_buttons(buttons)` gives 1 = left, 2 = right, 4 = middle.
* **Other helpers:**
  * `strip_mnemonic("&File") == "File"` (Labels hide `&` access keys);
  * `resolve_path(owner, path)` resolves paths relative to the form's folder
    (`PictureBox.Picture`).
* **Property groups** reused by the controls: `_geometry(w, h)` (Left, Top,
  Width, Height, always written), `_FONT`, `_COLORS`, `_COMMON` (Enabled,
  Visible, TabIndex, ToolTipText, Tag, ZIndex).
* **`_EventBridge`**: a `QObject` event filter forwarding widget events to
  `Control._on_qt_event`.
* **`Control`**, the base class:
  * **Identity:** `Name`, `Parent`, `Container`, `_form`, `_design_mode`.
  * **Widget management:** `_create_widget(parent_widget)` (abstract),
    `_build_widget`, `_rebuild_widget`, `_event_targets` (which widgets get
    the filter), `_connect_signals`.
  * **Dispatch:** `_handler(event)`, `_fire(event, *args)`, `_on_qt_event`,
    `_on_key_press` (KeyPreview, KeyDown, KeyPress transform or cancel,
    Default/Cancel buttons).
  * **Common property implementations:** geometry, Enabled, Visible (not
    applied in design mode), ToolTipText, fonts, colors (style sheet on
    `_qss_type`).
  * **Methods:** `SetFocus`, `Move`, `Refresh`, `ZOrder` (sets `ZIndex`).
  * **Stacking:** `_stackable`, `_siblings`, `_restack` and `_apply_ZIndex`.
    Siblings are ordered by `(ZIndex, creation order)` on creation, on widget
    rebuild and on every `ZIndex` change.
  * **Typo guard:** `__setattr__` raises on unknown capitalized names.
* **Controls** (table below). Each one defines:
  * the metadata `TypeName`, `DefaultSize`, `DefaultEvent`, `Events`,
    `Properties` and `IsContainer`;
  * `_create_widget`, the `_apply_*` / `_read_*` hooks, and extra runtime
    members.

| Class | Qt widget | Notes |
|---|---|---|
| `Label` | `QLabel` | Click synthesized from the mouse; `Caption` has mnemonics stripped; AutoSize/WordWrap/BorderStyle. |
| `TextBox` | `QLineEdit` or `QPlainTextEdit` | `MultiLine` picks the widget (rebuilt when changed); `SelStart`/`SelLength`/`SelText`; Change on every edit. |
| `CommandButton` | `QPushButton` | `Default`/`Cancel`; setting `Value = True` clicks it. |
| `CheckBox` | `QCheckBox` | `Value` 0/1/2 (tri-state for Grayed); Click fires on every change, including from code (VB behavior). |
| `OptionButton` | `QRadioButton` | Buttons in the same container are mutually exclusive; Click when it becomes checked. |
| `Frame` | `QGroupBox` | Container; colors via palette. |
| `ListBox` | `QListWidget` | `_ListMixin` (`AddItem`, `RemoveItem`, `Clear`, `ListCount`, `List`); `ListIndex`, `Text`, `Selected(i)`, `Sorted`, `MultiSelect`. |
| `ComboBox` | `QComboBox` | `Style` 0 (editable) / 2 (list only); Click on selection change, Change on edit. |
| `Timer` | none at run time (`QTimer`) | Stopwatch icon in design mode (`_timer_design_widget`). |
| `HScrollBar`, `VScrollBar` | `QScrollBar` | `_ScrollBar` base; Change on value change, Scroll while dragging. |
| `PictureBox` | `QLabel` | Container; `Picture` is a file path relative to the form's folder; Stretch/AutoSize/BorderStyle; `Cls()`. |

### `vp6/dialogs.py` (≈70 lines)

* `MsgBox(prompt, buttons=vpOKOnly, title=None)` builds a `QMessageBox`:
  * the buttons come from `buttons & 7` (`_BUTTON_SETS`), the icon from
    `buttons & 0x70`, the default button from `buttons & 0xF00`;
  * it returns `vpOK`, `vpYes`, `vpNo` etc. Closing with Esc gives
    `vpCancel` when available.
* `InputBox(prompt, title=None, default="")` returns the text, or `""` when
  cancelled.
* Both default their title to `App.EXEName` and match the color scheme of the
  active form (`appearance.match_dialog`).

### `vp6/form.py` (≈520 lines)

* `_FormsCollection` / `Forms` is the loaded forms (`Count`, iteration,
  indexing).
* `_FormWidget(QWidget)` is the form's window. It overrides Qt event handlers
  to fire the form events:
  * close → unload query, hide → end of a modal loop, Resize, Activate /
    Deactivate;
  * mouse → Click, DblClick and the MouseDown/Move/Up events;
  * keys → KeyDown, KeyPress and KeyUp, plus the Default/Cancel buttons.
* **`Form(PropertyHost)`**:
  * **Construction:**
    * `__init__` (see architecture §4.4);
    * `__setattr__` names controls assigned to attributes;
    * `_register_control`;
    * `_owner_form` / `_container_widget` / `_base_dir`, the same interface
      a container control offers.
  * **Color scheme:** `_project_scheme`, `_effective_scheme`, `_is_dark`,
    `_render_scheme` (the designer overrides it), `_apply_ColorScheme`,
    `_style_widget` (called for every new control widget).
  * **Keyboard:** `_preview_key`, `_handle_default_cancel`,
    `_apply_tab_order`.
  * **Window:** `_apply_window_flags` (BorderStyle → Qt window flags, fixed
    size for fixed styles), `_position_on_first_show` (StartUpPosition).
  * **Property hooks:** Caption, Width/Height (client area), Left/Top,
    WindowState, BorderStyle/ControlBox/MinButton/MaxButton, Enabled,
    colors, fonts.
  * **API:** `Me`, `Name` (the class name), `Controls`,
    `ScaleWidth`/`ScaleHeight`, `Visible`, `Load()`, `Show(Modal, OwnerForm)`,
    `Hide()`, `Unload()`, `Move()`, `Refresh()`, `SetFocus()`,
    `Form.Run()` (classmethod).
* **Module functions:** `Load(form)`, `Unload(form)` and `run(form_or_class)`
  (show the form and run the event loop).

### `vp6/formfile.py` (≈280 lines)

Reading and writing the designer region of form files (format in
architecture §6.1). It has no Qt dependency beyond importing the control
classes for their metadata.

* **Data:**
  * `ControlDef(type, name, parent, props)`;
  * `FormDef(class_name, props, controls)` with `control(name)`;
  * `FormFileError`.
* **Locating:** `find_region(source)` returns the (start, end) line indices,
  and raises if `# endregion` is missing. Also `find_form_class`,
  `is_form_source` and `defined_methods` (indented `def` names, used by the
  code window).
* **Parsing:** `parse(source)` → `FormDef`; `parse_region_body(body,
  class_name)`. It validates the allowed statement shapes, the control types,
  that parents are defined first, and that values are literals.
* **Generating:**
  * `generate_region(form_def, indent)` writes the whole region;
  * `replace_region(source, form_def)` swaps the region into a source text;
  * `format_value(kind, value)` (colors as `0xBBGGRR` hex) and
    `_props_to_args` (skips defaults unless `always`);
  * `_wrap_call` fills arguments into 99-character lines.
* **Templates:** `new_form_source(class_name)`, and
  `new_module_source(with_main, console, startup_form)`. With `with_main`, the
  module gets `Main()` and an `if __name__ == "__main__": Main()` block. The
  console `Main` asks for a name; with `startup_form`, `Main` imports that
  form and calls `run(Form)`.
* **Refactoring:**
  * `rename_form_class` renames the class line and `run(Old)`;
  * `rename_control_references` renames `def Old_Event(` and `self.Old`,
    outside the region only;
  * `rename_class_references(source, old, new)` renames a class in another
    file. In `from Form1 import Form1` only the imported name changes, since
    the module (the file) keeps its name;
  * `rename_module_references(source, old, new)` renames a module in another
    file: `from old import`, `import old` and `old.x`;
  * `event_stub(obj, event, args)` makes a new handler stub.

### `vp6/project.py` (≈170 lines)

Project files, which are executable launcher scripts (format in
architecture §6.2).

* `Project` dataclass:
  * fields `name`, `type` (`"exe"` / `"console"`), `startup` (a form class
    name or `SUB_MAIN = "Sub Main"`), `forms`, `modules`, `color_scheme`,
    `path`;
  * helpers `directory` and `abspath(relative)`;
  * `Project.load(path)`;
  * `project.save(path=None)` rewrites only the region when the file exists,
    else writes `_TEMPLATE`, then makes the file executable;
  * `region()` renders the `PROJECT` dict with comments.
* `parse(text)` → dict. It reads the region, or the whole file if there is no
  region, with `ast`, and raises `ProjectFileError` (a `ValueError`) for
  invalid files.
* `make_executable(path)` adds `x` for every class of user that can read the
  file. It does nothing on Windows.
* Constants: `EXTENSION = ".vp6p"`, `REGION_START` / `REGION_END`, and
  `_FIELDS` (the order the fields are written in).

### `vp6/runner.py` (≈80 lines)

It's deliberately not named `run.py`: importing a `vp6.run` submodule would
replace the public `vp6.run()` function on the package, and `run(Form1)` in
programs would then fail.


Starts a project. `run_project(path)`:

1. loads the project;
2. puts its folder on `sys.path` and `chdir`s into it;
3. sets `App.Title` and `appearance.project_scheme`;
4. starts the program:
   * **`Sub Main`:** calls `find_main(project)()` (modules are searched
     first, then forms). A console project exits with Main's return value if
     it's an int. A GUI project then runs the event loop while forms are open.
   * **A form:** calls `run(find_form_class(project, startup))`. Modules are
     imported by file name (`_import_file`).

`main(argv)` implements `python -m vp6.runner PROJECT.vp6p` and the `vp6-run`
console script.

---

## IDE: `vp6/ide/`

### `vp6/ide/__init__.py`, `vp6/ide/__main__.py`

Package docstring; `python -m vp6.ide [PROJECT.vp6p]` calls
`mainwindow.main()`.

### `vp6/ide/mainwindow.py` (≈870 lines)

The IDE shell. `VP6_ROOT` is the folder containing the `vp6` package; it's
prepended to `PYTHONPATH` for programs started with F5.

`MainWindow(QMainWindow)`:

* **Construction.**
  * Calls `theme_manager().manage_application()` (the IDE follows the theme)
    and sets the icon variant.
  * Creates the MDI area, the four docks, the actions, the toolbar, the menus
    and the status bar.
  * Restores `geometry` and `state` from the settings.
* **Light/dark:**
  * `_on_theme_changed` redraws the icons, the Toolbox, the window icons, the
    Project Explorer and the Properties window, and recolors the MDI
    background;
  * `toggle_dark_mode` is the toolbar switch: it picks the `system_light` or
    `system_dark` theme;
  * `_update_theme_toggle` shows the sun or moon icon.
* **UI helpers:**
  * `_action(text, slot, shortcut, icon, tip)` (the icon is an
    `icons._DRAWERS` name and is redrawn on theme changes);
  * `_dock`, `_create_actions` / `_create_menus` / `_create_toolbar`;
  * **Outline window** (`outline`, dock `outline_dock`, hidden by default):
    `_place_outline` docks it right under Properties, `_show_outline` (View >
    Outline Window) does that when it opens, and `_goto_outline_line` opens
    the code window at a chosen item's line.
  * `_context_path()` is the file the Properties and Outline panels are
    about: the Project panel's selection while it's open, else the active
    window's file. `_update_properties_target()` updates both panels.
  * `_on_dock_moved` / `_tab_bottom_docks`: panels in the bottom dock area
    are always one tab group. This runs on every dock's location, floating
    and visibility changes (coalesced), and after `restoreState`;
  * `_default_layout` / `reset_layout`, `_set_tabbed`, `_show_dock`;
  * `_fill_theme_menu`, `_fill_recent_menu`, `show_options`.
* **Project lifecycle:**
  * `show_start_dialog`, `new_project`, `open_project_dialog`,
    `open_project(path)`, `close_project()`;
  * `save_all()`, `_confirm_save`, `project_properties`, `_set_startup`,
    `_project_scheme`;
  * `add_form`, `add_module`, `add_file`, `remove_file`;
  * `recent_projects` and `_remember`.
  * **What the Properties window shows:** `_properties_target()` follows the
    Project panel's selection while that panel is open, or the active window
    when it's closed. `_update_properties_target()` applies it; `_target_for_path`
    gives a form's designer or a cached `FileTarget` (`_file_targets`). It is
    re-run on explorer selection and visibility changes
    (`_on_explorer_changed`), window activation, and designer selection
    (`_on_designer_selection`).
  * **Renames from the Properties window:** `_rename_file_object` renames a
    form's class or a module; `_rename_module` renames the module's file, the
    project entry and references in other files
    (`formfile.rename_module_references`).
  * **Form renames**, from the designer or the Properties window, go through
    `_on_form_renamed`. It renames references in the other files
    (`formfile.rename_class_references`, e.g. Module1's
    `from Form1 import Form1` / `run(Form1)`) and the startup object.
  * `project_target` (`ProjectTarget`). `_project_changed()` is the one path
    after the project's properties change, whether from the dialog or the
    Properties window.
* **Windows:**
  * `view_object(path)` returns the path's `FormDesigner`, creating it if
    needed, and `view_code(path)` does the same for its `CodeWindow`;
  * `_open_handler` (designer double-click → code), `open_location(path,
    line)` (traceback links);
  * `_on_subwindow_activated` binds the Properties window to the active
    designer, or to the designer of the active code window's form.
* **Command routing:**
  * `_designer_call(method, *args)` for the Format menu;
  * `_edit(op)` for the Edit menu: to the designer, the code editor, or a
    focused text field outside the MDI area;
  * `_view_current`.
* **Running:**
  * `run_project` (F5, ⌘/Ctrl+Enter), `stop_project`, `restart_project`;
  * `_send_input` (stdin), `_on_process_finished` / `_on_process_error`;
  * `running`, `_update_title`, `_update_actions`.
* **`closeEvent`** asks to save, then stores `geometry` and `state`.

`_QuitOnInterrupt` makes **Ctrl+C** in the terminal that started the IDE work
like File > Exit (Quit VP6).

* Qt's event loop keeps Python from running signal handlers, so it uses
  `signal.set_wakeup_fd` with a socket pair and a `QSocketNotifier` to get
  control back to Python.
* It closes any open modal dialog first (e.g. New Project at startup).
* It ignores repeats while the save prompt is showing.
* `main()` installs it. MainWindows created in tests don't have it.

`main()` also starts an `OutputCapture` before the `QApplication` exists, so
Qt's startup messages are included. It attaches the capture to the Output
window (`output`, dock `output_dock`, hidden by default and tabbed with the
Immediate window; View > Output Window) and stops it on quit.

Module functions:

* `create_project(location, name, template)` creates a project folder. Every
  template gets `Form1.py`, `Module1.py` and the `.vp6p`, and starts in Sub
  Main. The console template's `Main` uses `print()`/`input()`; the Standard
  EXE template's `Main` shows Form1. `"kitchensink"` delegates to
  `kitchensink.create`, which also adds `frmDialog.py` and `vp6.png`.
* `main(argv)` is the application entry point.

`open_project` opens a windowed project's startup form designer, or its first
form's when it starts in Sub Main, and a console project's Main module.

### `vp6/ide/designer.py` (≈1000 lines)

The form designer (architecture §5.3).

* **Constants:**
  * `GRID = 8` (snapping), `MARGIN` (space around the frame), `HANDLE`
    (handle size), `DRAG_THRESHOLD`;
  * `NAME_PREFIX` (Toolbox type → default name prefix: `Command`, `Text`, …);
  * `WORKSPACE` (background colors by IDE mode).
* **Helpers:** `snap`, `is_identifier`, `ide_is_dark()`.
* **`DesignForm(Form)`**, the design-mode form:
  * `_base_dir` and `_project_scheme` come from the designer;
  * `_render_scheme`: a System form shows the real OS appearance when the IDE
    forces the other one;
  * `_control_widget_changed` re-prepares rebuilt widgets;
  * `_apply_colors` draws the grid tile over the scheme's window color.
* **`_Canvas`** paints the workspace and the window frame (`chrome.paint`).
  `form_frame_rect()`.
* **`_Overlay`** handles all input:
  * **Painting:** handles and outlines (two-tone, visible on any background),
    the rubber band, and the rectangle of a control being drawn.
  * **Mouse:** drag kinds `draw`, `move`, `resize`, `form_resize` and `band`.
    Alt disables snapping; Shift/Ctrl add to the selection; Ctrl+drag inside
    a container draws a band inside it; double-click requests the default
    event's code; right-click opens the context menu.
  * **Keyboard:** arrows move by the grid (Ctrl: 1 px), Shift+arrows resize,
    Esc cancels the tool or selects the parent, Delete/Backspace deletes.
* **`FormDesigner(QWidget)`** (signals: see architecture §5.3):
  * **Building:** `load_def(form_def)`, `_instantiate`, `_prepare_widget`
    (NoFocus), `_layout_form` (below the frame's title bar),
    `update_canvas_size`. `eventFilter` calls `update_canvas_size` on the
    scroll area viewport's resize, so the canvas fills the window after
    maximize and restore.
  * **Scheme and frame:** `set_project_scheme`, `refresh_scheme`,
    `frame_style()`, `frame_info()`, `_on_ide_theme_changed`.
  * **Geometry:** `form_widget`, `form_canvas_rect`, `canvas_rect(name)`,
    `parent_rect(name)`, `control_at(pos)`, `container_at(pos)`.
  * **Selection:** `select`, `select_by_name`, `selected_objects`,
    `object_name`, `all_objects`, `set_tool`. An empty selection means the
    form.
  * **Commits and undo:** `_snapshot`, `_commit`, `commit_geometry`,
    `commit_form_size`, `undo`, `redo`, `_restore`.
  * **Editing:**
    * `unique_name`, `create_control`, `add_control_centered`;
    * `delete_selection` (with descendants), `copy_selection`,
      `cut_selection`, `paste` (renames and offsets duplicates), `select_all`;
    * `set_property(prop, value)` returns an error message or `None`;
      `rename(new_name)` handles controls and the form class;
    * Format menu: `align`, `make_same_size`, `center_in_form`, `nudge`,
      `z_order`;
    * `show_context_menu`.

### `vp6/ide/chrome.py` (≈330 lines)

Window frames painted around the designed form.

* Styles are `AUTO`, `MACOS`, `WINDOWS`, `GNOME` and `CLASSIC`
  (`FRAME_STYLES` holds their labels); `resolve(style)` maps `AUTO` to the
  running OS's style.
* `FrameInfo` holds what's needed from the form: caption, border style,
  control box, min/max buttons, and whether the title bar and form are dark.
  Its properties `tool`, `can_minimize` and `can_maximize` mirror the runtime
  window-flag logic.
* `metrics(style, info)` gives the title bar height and border width.
  BorderStyle 0 means no frame; tool windows get smaller title bars.
* `frame_rect(client, style, info)` and `paint(p, style, client, info)`.
* Painters `_macos` (traffic lights), `_windows` (Windows 11 caption
  buttons), `_gnome` (Adwaita header bar) and `_classic` (VB6), plus helpers
  `_shadow`, `_top_rounded`, `_draw_title`.
* Title bars are drawn in the **OS** appearance, since the OS draws real
  title bars at run time; only the classic frame follows the form's scheme.

### `vp6/ide/codeeditor.py` (≈780 lines)

* `code_font()` returns the font chosen in Options (via the theme manager).
* **`PythonHighlighter(QSyntaxHighlighter)`:**
  * applies the theme's syntax styles (`set_theme`), and follows the theme
    manager unless created with `follow_theme=False` (the Options preview);
  * rules cover keywords, VP6 names, builtins, `self`, numbers, decorators,
    `def`/`class` names, and strings and comments;
  * block state bits: `IN_SINGLE` / `IN_DOUBLE` (triple-quoted strings) and
    `IN_REGION` (designer region background).
* **`_LineNumbers`** is the gutter widget. It delegates painting and clicks
  to the editor.
* **`CodeEditor(QPlainTextEdit)`:**
  * **Theme:** `apply_theme(theme, font)` sets palette, font, tab width and
    gutter colors.
  * **Gutter:** `paint_gutter` draws line numbers and the fold box;
    `gutter_clicked` toggles the fold.
  * **Region:** `apply_fold` (hidden blocks), `_region_span`,
    `_edit_allowed(key)` and `_reject_edit`; `insertFromMimeData`, `cut` and
    `paste` are guarded.
  * **Editing keys:** `keyPressEvent` handles the completion popup, the
    region guard, Enter with auto-indent (`_newline_with_indent`, which also
    dedents after `return`/`pass`/…), Tab/Shift+Tab (`_indent`),
    `_smart_backspace`, Ctrl+/ (`toggle_comment`) and Ctrl+Space.
  * **Completion and navigation:** `_show_completions` / `_insert_completion`
    (`QCompleter` with a `QStringListModel`); `goto_line(line)` unfolds the
    region if needed.
* **`complete(context, document)`**, the completion provider (see
  architecture §5.4). `_members(cls)` lists a class's spec names plus its
  public capitalized members.
* **`CodeWindow(QWidget)`**, the combos plus the editor:
  * `refresh_combos` (debounced 300 ms after text changes), `_fill_procs`
    (handlers that exist are shown bold);
  * `_on_object_chosen` jumps to an existing handler or the default event;
    `_on_proc_chosen`;
  * `goto_event(obj, event)` jumps to the handler, or inserts a stub after
    `_class_end_line()` and selects `pass`;
  * `_goto_def`, `_sync_combos_to_cursor`.

### `vp6/ide/properties.py` (≈290 lines)

* `TextListDialog` edits a list (one item per line) or multi-line text.
* `PropertiesWindow(QWidget)`:
  * **Binding:** `set_designer(designer)` connects to `selectionChanged` and
    `designChanged`; `refresh()` rebuilds the object combo and the grid
    (common properties across the selection; `_MIXED` marks differing
    values).
  * **Editors:** `_editor(spec, value)` picks an editor by kind;
    `_color_editor`, `_choose_color`, `_edit_list`, `_edit_text` and
    `_browse_file` (stores paths relative to the form folder when possible).
  * `_commit(prop, value)` calls `designer.set_property` and shows any error.
  * The description pane shows the spec's `description`.
  * `select_property(name)` focuses a property's row and editor.
  * The window is bound to a target with `set_designer(target)`: a
    `FormDesigner`, or the `ProjectTarget` (see `projectprops.py`).

### `vp6/ide/projectprops.py` (≈120 lines)

The project, and files without a designer, as targets of the Properties
window.

* `ProjectTarget(QObject)` offers the same interface as `FormDesigner`
  (`selected_objects`, `all_objects`, `object_name`, `select_by_name`,
  `set_property`, `base_dir`, signals `selectionChanged` / `designChanged`).
  The Properties window therefore edits the project without special cases.
* It exposes the project's `(Name)`, `Type`, `StartupObject` and
  `ColorScheme` as `enum` specs. `StartupObject`'s choices are the project's
  forms plus `Sub Main`.
* `set_property` validates the name, updates the `Project`, and calls the main
  window's `_project_changed` (save, update designers, explorer and titles).
* `_ProjectObject` is the "selected object" the grid reads values from.
* `TYPE_CHOICES` and `COLOR_SCHEME_CHOICES` are shared with
  `ProjectPropertiesDialog`.
* `FileTarget(QObject)` is the same interface for a module, or a form whose
  designer isn't open. It shows just `(Name)` (through `_FileObject`, which
  has no specs). `set_property("Name", …)` calls the main window's
  `_rename_file_object`.

### `vp6/ide/outline.py` (≈230 lines)

The Outline window: the structure of a source file.

* `outline(source)` reads the file with `ast` (never runs it) and returns
  `OutlineItem`s (`name`, `kind`, `line`, `children`, `detail`), in file order:
  * module-level assignments are `constant` (ALL_CAPS names) or `variable`;
  * classes are `class`, with their members: `method`s, `attribute`s and
    nested classes;
  * module-level functions are `function`;
  * one `*global code*` item (`code`) points at the first top-level
    statement that isn't an import, definition or assignment. Its `detail` is
    that line.
  * Imports and docstrings are skipped. `InitializeComponent` is listed as a
    method, without its contents.
* `sorted_outline(items, key, descending)` sorts by `"order"` (line),
  `"name"` or `"type"` (the `KINDS` order), recursively.
* `OutlineWindow(QWidget)`:
  * **Sort buttons** (`buttons`, `sort_by`): clicking the active one reverses
    it, and the active one shows ▲/▼.
  * **Problem label:** shown on a syntax error; the last good outline stays.
  * **Tree:** icons from `KIND_ICONS`; tooltips give the kind and line.
  * `set_document(doc)` follows the document's edits, debounced 300 ms
    (`refresh`).
  * Clicking or activating an item emits `lineChosen(line)`.

### `vp6/ide/outputcapture.py` (≈130 lines)

Captures the IDE process's stdout and stderr for the Output window.

* **At the file-descriptor level.** Replacing `sys.stdout` would miss
  libraries that write to fds 1 and 2 directly, such as Qt's warnings and C
  extensions.
* `OutputCapture(streams=((1, "out"), (2, "err")))` points each descriptor at a
  pipe (`os.dup2`) and starts a reader thread per pipe (`_pump`). Each thread:
  * copies the bytes to the original descriptor, so a terminal still shows
    them;
  * decodes them incrementally as UTF-8, so a character split across reads is
    kept whole;
  * delivers the text.
* **Delivery** (`_deliver`): text is kept in a bounded history and sent
  through `_Relay.received`, a signal queued to the GUI thread.
  `attach(append)` replays the history (startup output) and then forwards new
  text.
* `stop()` restores the descriptors, lets the readers drain and finish, then
  closes the duplicates.
* `mainwindow.main()` starts it before Qt, unless `VP6_NO_OUTPUT_CAPTURE` is
  set.

### `vp6/ide/panels.py` (≈370 lines)

* **`Toolbox`:**
  * checkable tool buttons (the pointer plus `CONTROL_TYPES`) with signals
    `toolSelected(type | None)` and `toolActivated(type)` (double-click);
  * `reset()` goes back to the pointer; `refresh_icons()` is used after
    light/dark changes.
* **`ProjectExplorer`:**
  * a tree of Forms and Modules, with the startup object in bold;
  * View Code / View Object buttons, a context menu, and double-click to
    open;
  * signals `openObject`, `openCode`, `removeFile`, `setStartup`, `addForm`,
    `addModule`; `populate(project, names)`;
  * `select_path(path)` selects a file's item without opening it. The main
    window uses it to follow the active designer or code window.
  * `projectSelected` / `fileSelected(path)` fire when the current item
    changes; `select_project()` and `project_selected()`. Selecting the
    project shows its properties in the Properties window.
* **`_OutputPane`** is the shared base of the two output panels:
  * an `output` (`QPlainTextEdit`, read-only);
  * `append(text, kind)` where kind is `out`, `err`, `info` or `in`. The kind
    is stored on the text, so `apply_theme()` can recolor existing output.
    New text keeps the view at the end only if it was already there;
  * `clear()`;
  * a context menu built by the subclass's `_context_menu()`.
* **`ImmediateWindow(_OutputPane)`** shows the running program's output:
  * **Input:** an `input` line, enabled by `set_running(True)` while a console
    program runs, emits `inputSubmitted`.
  * **Traceback links:** double-clicking a `File "...", line N` line emits
    `openLocation`.
  * **Context menu:** the standard text menu plus Clear.
* **`OutputWindow(_OutputPane)`** shows the IDE's own stdout and stderr (see
  `outputcapture.py`). Its context menu is Select All, Copy and Clear.
* `pump_process_output(process, window)` connects a `QProcess`'s stdout and
  stderr to the window.

### `vp6/ide/documents.py` (≈140 lines)

* `Document(QObject)`:
  * `path`, `text_document` (`QTextDocument` with a plain-text layout),
    `filename`, `name`, `text`, `modified`, `save()`;
  * signal `modifiedChanged`;
  * `replace_text(text)` does a whole-text replacement as one undoable edit
    (used for renames).
* `FormDocument(Document)`:
  * `form_def`, `name` (the class name found in the text), `region_range()`;
  * `set_form_def(form_def)` regenerates the region;
  * `_on_text_changed` re-parses; signals `designReloaded` and `parseError`.
* `open_document(path)` picks the class by content.

### `vp6/ide/kitchensink.py` (≈70 lines) and `vp6/ide/templates/kitchensink/`

The Kitchen Sink project template: a demo of every control and feature.

* `create(directory, name)` copies `FORMS` (`Form1.py`, `frmDialog.py`) and
  `MODULES` (`Module1.py`) from `TEMPLATE_DIR`, draws the PictureBox image
  `PICTURE` (`vp6.png`, via `draw_picture`, so the package ships no binary),
  and returns a Standard EXE `Project` that starts in Sub Main.
  `mainwindow.create_project(..., "kitchensink")` calls it.
* **`templates/kitchensink/Form1.py`** contains all 12 control types:
  * Frames and a PictureBox as containers (a Label inside the picture);
  * text boxes (multi-line, password, upper-casing KeyPress);
  * Default and Cancel buttons;
  * option buttons switching the form's `ColorScheme` at run time;
  * check boxes, scroll bars, combo boxes, a sorted list with Add/Remove;
  * a `DoEvents` loop, a Timer clock, and MsgBox/InputBox;
  * Clipboard, App, Screen and Forms;
  * a `KeyPreview` F1 help and Ctrl+Q `End()`;
  * a `Form_Unload` confirmation, and a status bar kept at the bottom by
    `Form_Resize`.
* **`frmDialog.py`** is a modal dialog (`Show(vpModal)`) with its own Dark
  color scheme, using `Load`/`Unload` and a `Result` attribute.
* **`Module1.py`** is `Main()` with `run(Form1)`.
* The files are package data (`pyproject.toml`). `tests/test_kitchen_sink.py`
  keeps them covering every control and API name (development guide §5.11).

### `vp6/ide/dialogs.py` (≈230 lines)

* `NewProjectDialog` has the New tab (templates `exe`, `console` and
  `kitchensink`, with name and location), the Existing tab (browse) and the
  Recent tab. After `exec()`, `result_action` is `"new"` (see `template`,
  `project_name`, `project_location`) or `"open"` (see `open_path`).
  Also `DEFAULT_LOCATION` (`~/VP6 Projects`), `TEMPLATES` and
  `next_free_name`.
* `ProjectPropertiesDialog` edits the name, type, startup object and color
  scheme (System / Light / Dark / Follow the IDE); `apply(project)`.
* `ABOUT_HTML` is the Help > About text.

### `vp6/ide/options.py` (≈330 lines)

The Tools > Options dialog. It edits a copy of the theme manager's
`EditorSettings` and applies it on OK or Apply.

* **Theme:** the selection, plus which themes to use for light and dark
  System appearance.
* **Colors:** pick the theme to customize (New… / Delete / Reset), then a
  table of every UI and syntax role with color, bold and italic.
* **Font:** monospaced families and the size.
* **Form Designer:** window frame style and Show grid.
* **Preview:** a read-only `CodeEditor` on a sample form, with
  `follow_theme=False`, showing the theme being edited.

### `vp6/ide/theme.py` (≈330 lines)

* **Constants:** `SYSTEM`, `LIGHT`, `DARK`. `UI_ROLES` and `SYNTAX_ROLES` are
  the customizable roles, with their labels.
* **`TextStyle`**(color, bold, italic) and **`Theme`**(name, dark, colors,
  syntax), with `to_dict` and `from_dict(data, fallback)`. `from_dict` fills
  in missing roles, so older saved themes keep working after new roles are
  added.
* **`BUILTIN_THEMES`**: Light (VB6-like) and Dark (VS Code Dark+-like).
* **Store and font:** `ide_settings()` is the IDE's `QSettings` store (always
  use it). With `VP6_SETTINGS_DIR` set, it's `VP6 IDE.ini` in that folder.
  Also `default_code_font()`.
* **`EditorSettings`**: `selection`, `system_light`, `system_dark`,
  `font_family`, `font_size`, `frame_style`, `show_grid`, `themes`.
* **`ThemeManager(QObject)`** (signal `changed`):
  * **Loading and saving:** `_load`, `apply(state)` (persist and notify),
    `select(name)`.
  * **Queries:** `resolve(state)`, `current()`, `font()`, `app_is_dark()`,
    `ide_scheme()`. `ide_scheme` is registered as
    `appearance.ide_scheme_provider`.
  * **Application scheme:** `manage_application()`,
    `release_application()`, `_apply_app_scheme()` (with the Fusion
    fallback), `_restore_native_style()`, `_on_system_changed()`.
* `theme_manager()` returns the singleton. `reset_theme_manager()` releases
  it (used by tests).

### `vp6/ide/icons.py` (≈300 lines)

Icons drawn with `QPainter`, in light and dark variants.

* `_Colors` palettes `_LIGHT` / `_DARK`. The drawing functions read the
  module-level palette `C`, which `_render` switches.
* One drawer per icon in `_DRAWERS`:
  * one per control, keyed by `TypeName`, plus `Pointer`;
  * project icons `Form`, `Module`, `Project`, `Console`;
  * toolbar icons `New`, `Open`, `Save`, `Run`, `Stop`, `Sun`, `Moon`;
  * the `KitchenSink` template icon;
  * Outline item badges `OutlineConstant`, `OutlineVariable`, `OutlineClass`,
    `OutlineFunction`, `OutlineMethod`, `OutlineAttribute`, `OutlineCode`
    (`_badge`: a colored square with a white letter, readable in both
    schemes).
* `set_dark(dark)` / `is_dark()` select the variant;
  `icon(name)` gives 24 px icons (drawn at 2×), `large_icon(name)` 48 px.
  Results are cached per name and variant.
* Every icon includes a 35 %-opacity **disabled** pixmap, so disabled buttons
  stay visible.

---

## Tools: `tools/`

### `tools/apidocs.py` (≈200 lines)

Generates the reference tables in `docs/api.md` from the code, so they can't
drift.

* **Generated blocks:** `docs/api.md` has blocks between
  `<!-- BEGIN GENERATED: <key> -->` and `<!-- END GENERATED -->`. `update(text)`
  re-renders all of them and `block_keys(text)` lists them.
* **Keys and their renderers:**
  * `form-properties` and `form-events` (`form_properties`, `form_events`);
  * `control <TypeName>` (`control`): the default size, container flag,
    shared property groups, a table of the control's own properties, and its
    events;
  * `common-properties` (`common_properties`): the shared groups `GROUPS`,
    taken from `controls._geometry`, `_COLORS`, `_FONT` and `_COMMON`;
  * `event-arguments` (`event_arguments`), from `controls.EVENT_ARGS`;
  * `constants` (`constants_block`), from the `# --- Title ---` sections of
    `constants.py`, the color and scheme constants, and the key-code ranges.
* **Where table notes come from:** each property's `description` and enum
  choices. Improving a description improves the Properties window's
  description pane and the API reference at the same time.
* `main(argv)`: `python tools/apidocs.py` rewrites the file;
  `--check` exits 1 if it's out of date.

## Tests: `tests/`

All tests run headless. `conftest.py`:

* sets `QT_QPA_PLATFORM=offscreen` and `VP6_NO_ERROR_DIALOG=1`;
* provides the session `qapp` fixture;
* redirects `QSettings` to a per-test INI file in `tmp_path`, and asserts
  that `ide_settings()` is really isolated;
* resets the theme manager before and after each test (undoing any
  application-wide scheme a test forced);
* provides `wait_for(predicate, timeout_ms)` (PySide has no
  `QTest.qWaitFor`).

| File | Covers |
|---|---|
| `test_runtime.py` | Events (click, Default/Cancel keys, KeyPress transform/cancel), Value properties, lists, Timer, Unload cancel, the typo guard, TextBox MultiLine rebuild, colors, handler arity and error reporting, MsgBox results. |
| `test_formfile.py` | Region round trips, default elision, line wrapping, invalid regions, renames (controls, form classes, class and module references in other files), the console template. |
| `test_designer.py` | Creating controls, nesting in frames, mouse move with snapping and undo, rubber band, properties and rename, copy/paste, z-order and Format, code-side undo reloading the designer, region protection in the editor, the workspace filling the window after maximize/restore. |
| `test_ide.py` | New projects (every template has Form1 and Module1 with `Main()`; the Standard EXE's `Main` really shows Form1; it opens in the designer), adding forms and modules, double-click creating handlers, completion, running a console project with stdin, traceback reporting, toolbar and layout reset, bottom-edge panels always tabbed (also after restoring a side-by-side layout), the theme toggle, ⌘/Ctrl+Enter, the Immediate Clear menu, `VP6_IDE_SCHEME` passing, the Project Explorer following the active window, project properties in the Properties window, the Properties panel following the Project panel's selection (or the active window when that panel is closed), module and unopened-form Names, renaming modules and forms from the Properties window, a renamed Form1 still running, the IDE exiting without errors, Ctrl+C (SIGINT) quitting the IDE like File > Exit (also from the New Project dialog), `VP6_SETTINGS_DIR`. |
| `test_theme.py` | Built-in theme contrast (WCAG ratios), editor and System-mode following, persistence and reset of customizations, Immediate recoloring, the Options dialog. |
| `test_ide_theme.py` | Dark icon variants, disabled icons, the whole IDE following the theme, System forms in a forced IDE, frame styles and metrics, the grid toggle. |
| `test_appearance.py` | Forced schemes styling forms and controls, System/Light switching, BackColor overrides, project defaults (runner and `.vp6p` lookup), dialogs matching forms, the project scheme field, designer schemes, the IDE scheme. |
| `test_docs.py` | The docs keep up with the code: every source file in the source reference, every test file in the test table, every public API name in `api.md` (key-code ranges count), the generated `api.md` tables up to date with a section per control, every property with a description, and every relative link and anchor in the Markdown files resolving. |
| `test_outline.py` | The outline of the Kitchen Sink's Form1 matches the backlog example exactly; kinds, lines and skipped statements; syntax errors; sorting (order, name, type, both directions, members too); the panel's sort buttons, icons, tooltips, live updates and syntax-error handling; in the IDE: hidden by default, opened under Properties, following the Project panel or active window, clicking items goes to the line (unfolding the designer region). |
| `test_output.py` | Output capture: copy to the original descriptor, replay of output captured before attaching, split UTF-8 characters, restoring on `stop()`; real Python, C-level and Qt output in a separate process; the Output window's Select All / Copy / Clear menu; the real IDE `main()` showing its own output in the Output window. |
| `test_kitchen_sink.py` | The Kitchen Sink covers every control type, default event, public API name and color scheme; its regions are canonical; the project is created correctly; the designer opens its forms; the demo runs (typing, lists, scroll bars, colors, schemes, the modal dialog, the clock, unload). |
| `test_project.py` | The project script: hash-bang, validity, executable bit, round trip, keeping user code, never executing on load, invalid files, running via hash-bang / python / without VP6. |

## Samples: `samples/`

* `Calculator/`: `frmCalculator.py` (a fixed dialog with a display TextBox,
  digit and operator buttons whose Click handlers are attached in `Form_Load`
  like a control array, `KeyPreview` keyboard input, Default `=` and Cancel
  `C` buttons) and `Calculator.vp6p`.
* `GuessNumber/`: `modGame.py` (a console `Main()` using `input()`/`print()`)
  and `GuessNumber.vp6p` (`startup: "Sub Main"`, `type: "console"`).
