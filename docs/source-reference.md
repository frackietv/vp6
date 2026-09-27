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

### `vp6/app.py` (≈300 lines)

Application-level services.

* `ensure_app()` creates the `QApplication` on first use. Every entry point
  that needs Qt calls it. When it creates the application (a VP6 program), it
  also installs the Ctrl+C handler and gives it the VP6 icon.
* **Icons:** `icon_from(paths)` is a `QIcon` of image files (sizes of one
  picture; missing files skipped); `vp6_icon()` is the VP6 icon
  (`project.VP6_ICON_FILES`), also the IDE's; `set_program_icon(paths)` makes
  files the application's icon (windows, Dock, taskbar), creating the
  application first (Qt can't read images before), and returns False,
  keeping the old icon, if none can be read.
* **Ctrl+C:**
  * `InterruptHandler(action)` makes SIGINT run `action` inside Qt's event
    loop. Qt keeps Python from running signal handlers, so it uses
    `signal.set_wakeup_fd`, a socket pair and a `QSocketNotifier`. Before
    `action` it closes any open modal window, and it ignores repeats while
    `action` runs.
  * `install_interrupt_handler(action, parent)` returns None outside the main
    thread.
  * `close_all_windows()` is the action for programs: it closes every open
    window, so each `Form_Unload` runs and may cancel. The IDE's action is
    File > Exit.
* `DoEvents()`, `Beep()`, `End()`. `End` flushes stdout and stderr and calls
  `os._exit(0)`, like VB's `End`, without running `Form_Unload` handlers:
  it doesn't close the windows first, since closing them would run them.
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

### `vp6/controls.py` (≈3390 lines)

The intrinsic controls.

* **Module data:**
  * `EVENT_ARGS` maps each event name to the parameter list VB passes. The
    code window uses it to generate handler stubs.
  * `MOUSE_EVENTS`, `KEY_EVENTS`, `FOCUS_EVENTS`.
  * `CONTROL_TYPES`, at the end of the file: type name → class, in Toolbox
    order. The designer, form-file parser and Toolbox all use it. `Menu` is
    in it but has `InToolbox = False` (the Menu Editor designs menus).
  * `parse_outline(lines)` reads a TreeView outline into `(level, text, key)`
    (indentation for levels, a tab counting as 4 spaces, `|key` at the end).
  * `SHORTCUT_CHOICES`: VB's list of menu shortcut keys, in Qt's key names
    (`_shortcut_choices()`), for `Menu.Shortcut`.
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
* **Containers for `Form.ShowIn`:** `Control._fill_widget()` (the widget a
  filling form follows) and `_fill_rect(designed)` (where it goes; a
  scrolling PictureBox overrides both).
* **`_EventBridge`**: a `QObject` event filter forwarding widget events to
  `Control._on_qt_event`.
* **`Control`**, the base class:
  * **Identity:** `Name`, `Index` (read-only: the element's number in a
    control array, `_index`, else `None`), `Parent`, `Container`, `_form`,
    `_design_mode`, `_loaded_at_runtime` (added with `ControlArray.Load`).
  * **Widget management:** `_create_widget(parent_widget)` (abstract),
    `_build_widget`, `_rebuild_widget`, `_event_targets` (which widgets get
    the filter), `_connect_signals`.
  * **Dispatch:** `_handler(event)`, `_fire(event, *args)` (an array
    element passes its `Index` first), `_on_qt_event`,
    `_on_key_press` (KeyPreview, KeyDown, KeyPress transform or cancel,
    Default/Cancel buttons).
  * **Common property implementations:** geometry, Enabled, Visible (not
    applied in design mode), ToolTipText, fonts, colors (style sheet on
    `_qss_type`).
  * **Methods:** `SetFocus`, `Move`, `Refresh`, `ZOrder` (sets `ZIndex`).
  * **Control arrays:** `_place_after(other)` (where a loaded element goes;
    menus override it) and `_dispose()` (an unloaded element's Qt objects).
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
| `Label` | `QLabel` | Click synthesized from the mouse; `Caption` (multi-line) has mnemonics stripped in plain text; `TextFormat` (before Caption in `Properties`) picks plain, rich or Markdown (`_TEXT_FORMATS`) and makes links clickable at run time; `_on_link` fires `LinkClick(URL)`, or opens the URL (`QDesktopServices`) without a handler; AutoSize/WordWrap/BorderStyle. |
| `TextBox` | `QLineEdit` or `QPlainTextEdit` | `MultiLine` picks the widget (rebuilt when changed); `SelStart`/`SelLength`/`SelText`; Change on every edit. |
| `CommandButton` | `QPushButton` | `Default`/`Cancel`; setting `Value = True` clicks it. |
| `CheckBox` | `QCheckBox` | `Value` 0/1/2 (tri-state for Grayed); Click fires on every change, including from code (VB behavior). |
| `OptionButton` | `QRadioButton` | Buttons in the same container are mutually exclusive; Click when it becomes checked. |
| `Frame` | `QGroupBox` | Container; colors via palette. |
| `ListBox` | `QListWidget` | `_ListMixin` (`AddItem`, `RemoveItem`, `Clear`, `ListCount`, `List`); `ListIndex`, `Text`, `Selected(i)`, `Sorted`, `MultiSelect`. |
| `ComboBox` | `QComboBox` | `Style` 0 (editable) / 2 (list only); Click on selection change, Change on edit. |
| `Timer` | none at run time (`QTimer`) | Stopwatch icon in design mode (`_timer_design_widget`). |
| `HScrollBar`, `VScrollBar` | `QScrollBar` | `_ScrollBar` base; Change on value change, Scroll while dragging. |
| `PictureBox` | `QLabel` | Container; `Picture` is a file path relative to the form's folder; Stretch/AutoSize/BorderStyle; `Cls()`. `Align` docks it (`Form._layout_aligned`); changing Align, its size, place or Visible calls `_relayout` (a docked pane's size is left to the layout). `Resize` event when its widget is resized. Always opaque (`autoFillBackground`), with the scheme's window color when BackColor is unset. `ScrollBars` (run time only): `_start_scrolling` puts the controls on a content widget in a `QScrollArea` over the picture (`_stop_scrolling` undoes it), `_container_widget()` is then the content, `_ScrollWatcher` keeps it as large as the visible controls need (`_update_scroll_size`, deferred once per round of changes; the full area when everything fits), `ScrollLeft` / `ScrollTop` (their setters update the size first) and the `Scroll` event; `_fill_widget` / `_fill_rect` make a form shown in it fill the visible area but keep its own size. |
| `Line` | `_LineWidget` (transparent to the mouse, covering the line's box) | `X1`, `Y1`, `X2`, `Y2` instead of Left/Top/Width/Height (`_update_geometry` sizes the widget, with `_padding` for the width); `BorderColor` (unset: the palette's text color), `BorderStyle` (`_PEN_STYLES`; 0 = Transparent), `BorderWidth`, `Visible`, `Tag`, `ZIndex`; no events (`DefaultEvent` is empty); `_moved_points()` for the designer. |
| `Image` | `QLabel` | Not a container, `NoFocus`, no `TabIndex`, no colors (transparent). `Stretch` and `BorderStyle` come before `Picture` in `Properties`, because loading a picture sizes the control: without Stretch `_fit_to_picture` gives it the picture's size (plus the border). `Enabled` doesn't gray it: `_on_qt_event` drops events instead. |
| `TreeView` | `QTreeWidget` (header hidden, one column) | `Nodes` is a `_Nodes` collection (`_list` in the order added, `_by_key`; `_resolve` takes a key, an Index from 1 or a Node; `Add` places a `QTreeWidgetItem` by relationship, `Remove` with descendants, `Clear`). Each `Node` wraps its item (stored in the item's `Qt.UserRole` data; `UserRole + 1` holds its `Sorted`) with Text, Key, Tag, Index, FullPath, Expanded, Selected, Checked, Bold, ForeColor, Image, the relatives and `EnsureVisible`. `Items` (kind `outline`) rebuilds the tree from `parse_outline` (expanded in design mode). Events: NodeClick on `currentItemChanged`, or `itemClicked` on the node that was current at the press (`_current_at_press`); Expand/Collapse; NodeCheck when the check state changes (`Node._check_state`). Code changes run under `_quietly()` (`_Quiet`), so only the user's actions fire events. `SelectedItem`, `HitTest`, `LineStyle`, `Indentation`, `Checkboxes`, `Sorted` (`_keep_sorted`), `PathSeparator`. |
| `Splitter` | `_SplitterBar` (paints the bar and a grip, handles the mouse) | Docks by `Align` (Left by default) like an aligned PictureBox; `_pane()` is the nearest earlier visible control docked to the same edge; dragging calls `_resize_pane`, which clamps the pane between `MinSize` and what leaves `MinSize` of the form's `_free_area`, and `Moved` fires on release. `_vertical()`: Left/Right. Thickness changes relayout. |
| `ProgressBar` | `QProgressBar` (no text, `NoFocus`) | `Min`/`Max`/`Value`; `_apply_Value` keeps Value inside Min..Max (`_clamp`), and changing Min or Max re-applies it; `Orientation` (`_ORIENTATION`, `_QT_ORIENTATION`, shared with Slider and UpDown). Click synthesized from the mouse; no focus or key events. |
| `Slider` | `QSlider` | `valueChanged` fires `Scroll` while the thumb is down (`isSliderDown`, remembering `_changed_while_dragging`) and `Change` otherwise; `sliderReleased` then fires the one `Change` of a drag. `SmallChange`/`LargeChange` are the single and page steps; `TickStyle` maps through `_TICKS` to the tick position, `TickFrequency` to the tick interval. |
| `UpDown` | `_UpDownWidget` (two auto-repeating, `NoFocus` `QToolButton`s in a `QBoxLayout`; `set_vertical` swaps up/down for right/left arrows) | `_step(±1)` (not while designing): `_value_from_buddy` first (a number typed into the buddy, clamped, becomes the Value without a Change), then `Value ± Increment`, wrapping with `Wrap`, then `_sync_to_buddy` and UpClick/DownClick. `_apply_Value` clamps and fires `Change` when the value really changed (`_shown_value`), syncing the buddy. `Buddy` looks `BuddyControl` up on the form by name when needed (it may be created after the UpDown); `_buddy_property` is `BuddyProperty`, else the buddy's `Text` or `Caption`. |
| `StatusBar` | `QFrame` with a `QHBoxLayout`: a `QLabel` per shown panel (sunken, transparent to the mouse), and `_simple_label` for Style = Simple | Docked like an aligned PictureBox (`_Docked`; Align None/Top/Bottom, Bottom by default). `Panels` is a `_Panels` collection of `Panel` objects (`_list`, `_by_key`; `_resolve` takes an Index from 1, a key or a Panel; `Add`, `Remove`, `Clear`); the designer's `Panels` property (kind `panels`, read from `_values` by the Properties window) is lines parsed by `parse_panel` (`Text\|Key\|options`) and rebuilds the collection. Any change calls `_update_panels`, which rebuilds the layout: Spring panels get stretch, Contents ones their text's width (at least Width), others a fixed Width; a stretch keeps the panels left when none springs. `Panel._shown_text` is the Text, the time or date (`QLocale` short format) or CAPS/NUM/INS/SCRL; a 250 ms `_timer` (not while designing) refreshes those, dimming a lock key that is off (`_lock_key_on`: `GetKeyState` on Windows, `CGEventSourceFlagsState` for Caps Lock on macOS, off elsewhere). The bar gets the mouse and finds the panel by position (`_panel_at`) for `PanelClick` / `PanelDblClick`. |
| `TabStrip` | `_TabWidget` (a `QTabWidget` with an empty page per tab; `contents_rect()` asks the style for the pages' area, as Qt's layout does, which works before the widget is shown) | Not a container. `Tabs` is a `_Tabs` collection of `Tab` objects; the designer's `Tabs` property (kind `tabs`, read from `_values` by the Properties window) is lines parsed by `parse_tab` (`Caption\|Key\|ToolTipText`). Any change calls `_update_tabs`, which adds or removes pages and sets texts and tooltips without firing Click (`_quiet`), keeping the selected Tab (`_current_tab`). `currentChanged` fires `Click`; `BeforeClick` comes from a mouse press on another tab in the tab bar (an event target), and True swallows the press. `ClientLeft`… are `contents_rect()` moved by the widget's position; `Placement` maps to `setTabPosition`. |
| `Menu` | a `QAction` (none in design mode) | Parent: the form (the menu bar, `Form._add_menu_item`) or a `Menu`, whose `QMenu` (`_submenu`, created for its first item by `_add_menu_item`) holds it. Caption `-` is a separator; `Checked` (Qt's own toggling is undone in `_on_triggered`), `Enabled`, `Visible`, `NegotiatePosition` (rebuilds the window's bar when merged), `Shortcut` (also added to the form widget so it works in the window). Click on `triggered`, and for a menu with items on `aboutToShow`. `_menu_container`, `_place_after` (loaded array elements follow the last one), `_dispose`. |

`_KeyedItem` and `_KeyedCollection` are shared by `Panel`/`_Panels` and
`Tab`/`_Tabs`: an item's `Index` (from 1) and unique `Key`; the collection's
`Count`, `Item`/call (an Index, a Key or an item: `_resolve`), iteration,
`Remove` and `Clear`, and `_insert`/`_reset` for the control; each change
calls the control's update (`changed`).

`_Docked` is the mixin of the controls with an `Align` property (PictureBox,
Splitter, StatusBar): while docked, changing their Align, size, place or
visibility asks the form to place its docked controls again
(`_relayout`, `Form._layout_aligned`, which docks any control with `Align`).

* **`ControlArray`**, a VB control array (after `CONTROL_TYPES`, which it
  isn't part of). The form's `__setattr__` gives it its name.
  `__setitem__(index, control)` makes a control an element: it checks the
  Index (0 - 32767, `_check_index`), that it's free and that all elements
  have one type, then sets the control's `_name` and `_index`. Elements
  are read with `[i]`, VB's `(i)` (`__call__`) or `Item(i)`; also
  iteration in Index order, `len`, `in`, `Count`, `LBound`, `UBound`.
  `Load(i)` creates a new element from the lowest one's property values
  (hidden, last in the tab order, same container); `Unload(i)` removes
  one created that way (widget deleted, taken out of the form's controls,
  a Timer stopped).

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
    * `__setattr__` names controls and `ControlArray`s assigned to
      attributes;
    * `_register_control`;
    * `_owner_form` / `_container_widget` / `_base_dir`, the same interface
      a container control offers.
  * **Shown in a container** (`ShowIn`, `Container`): `_enter_container`
    makes the form's widget a child of the container's widget (no longer a
    window) and installs a `_ContainerWatcher`, which calls
    `_fit_to_container` when the container is resized; `_leave_container`
    makes it a window again (a form in a container gets Deactivate first).
    `_FormWidget.showEvent` / `hideEvent` call `_embedded_visibility`, which
    fires Activate/Deactivate once each way while in a container
    (`_active_in_container`); `changeEvent` leaves window activation to
    windows. `ShowIn` with Fill hides the other forms filling the same
    container. The host form lists these forms in
    `_embedded`, and `_query_unload` unloads them after itself (`force`:
    they can't cancel). `_apply_window_flags`, `_apply_fixed_size`,
    `_apply_WindowState` and `Show`'s positioning are skipped while it is in
    a container. `_hosts(form)` prevents showing a form inside itself.
  * **Color scheme:** `_project_scheme`, `_effective_scheme`, `_is_dark`,
    `_render_scheme` (the designer overrides it), `_apply_ColorScheme`,
    `_style_widget` (called for every new control widget).
  * **Keyboard:** `_preview_key`, `_handle_default_cancel`,
    `_apply_tab_order`.
  * **Docked panes:** `_layout_aligned()` places the PictureBoxes with an
    `Align` (and Splitters) at the edges of the client area, in creation
    order, each taking its edge of what the earlier ones left, with the
    thickness from its Width/Height value; then `Fill` ones (Align 5) get
    all of what is left. It computes every place first,
    then applies moves before resizes, so a pane's Resize handler sees
    everything in place; it records the space left in `_free_area`. It runs
    after
    `InitializeComponent`, on every resize (before `Form_Resize`), after the
    menu bar's layout, and when an aligned control is registered or changed.
  * **Menu negotiation:** a form in a container has no menu bar of its own
    (`_layout_menu_bar` hides it, never the system's). `_negotiate(visible)`,
    called from `_embedded_visibility` and `_leave_container`, adds it to or
    removes it from its window's `_merged_forms` (`_menu_window()` walks up
    the containers); the window's `_update_menu_bar()` rebuilds its bar from
    its own menus (`_top_menus`) and the merged forms' ones by
    `NegotiatePosition` (Left, Middle after the first, Right before its own
    Right menus), unless `NegotiateMenus` is off. `_ensure_menu_bar` creates
    a bar for a window without menus; menus added in code are merged too
    (`_register_control`). Popped out, a form gets its own bar back
    (`_native_menu_bar` remembers whether it was the system's).
  * **Menus:** `_add_menu_item(menu)` puts a top-level `Menu` on the menu
    bar (`_menubar`, a `QMenuBar` created with the first one). When Qt draws
    it in the window (not the macOS menu bar), `_make_client` moves the
    controls onto `_client`, a `_FormClient` below the bar (which passes its
    mouse events to the form widget), and `_layout_menu_bar` (also on every
    resize) keeps the bar at the top and grows the window by
    `_menu_height`. `Height`, `ScaleHeight` and `_container_widget()` are
    the client area's.
  * **Window:** `_apply_window_flags` (BorderStyle → Qt window flags, fixed
    size for fixed styles), `_position_on_first_show` (StartUpPosition).
  * **Property hooks:** Caption, Width/Height (client area), Left/Top,
    WindowState, BorderStyle/ControlBox/MinButton/MaxButton, Enabled,
    colors, fonts.
  * **API:** `Me`, `Name` (the class name), `Controls`,
    `ScaleWidth`/`ScaleHeight`, `Visible`, `Load()`, `Show(Modal, OwnerForm)`,
    `Hide()`, `Unload()`, `Move()`, `Refresh()`, `SetFocus()`,
    `Form.Run()` (classmethod).
* **Module functions:** `Load(form)` / `Load(array, Index)`,
  `Unload(form)` / `Unload(array, Index)` (forms, or control array elements)
  and `run(form_or_class)` (show the form and run the event loop).

### `vp6/formfile.py` (≈280 lines)

Reading and writing the designer region of form files (format in
architecture §6.1). It has no Qt dependency beyond importing the control
classes for their metadata.

* **Data:**
  * `control_key(name, index)` is how the IDE identifies a control:
    `"Command1"`, or `"cmdDigit(3)"` for a control array element;
  * `ControlDef(type, name, parent, props, index)` with `key`; `parent` is
    the container's key;
  * `FormDef(class_name, props, controls)` with `control(key)`,
    `elements(name)` (a name's controls in Index order) and `is_array(name)`;
  * `FormFileError`.
* **Locating:** `find_region(source)` returns the (start, end) line indices,
  and raises if `# endregion` is missing. Also `find_form_class`,
  `is_form_source` and `defined_methods` (indented `def` names, used by the
  code window).
* **Parsing:** `parse(source)` → `FormDef`; `parse_region_body(body,
  class_name)`. It validates the allowed statement shapes, the control types,
  that parents are defined first, and that values are literals. Control
  arrays: `self.X = ControlArray()` declares one (`_self_element`,
  `_is_control_call`, `_add_control` check that elements come after it, are
  unique and of one type); containers can be elements (`self.fra[1]`).
  Generation writes the declaration before the first element (`_reference`
  gives `self.X` or `self.X[i]`).
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
  * `set_index_parameter(source, name, events, present)` adds or removes the
    `Index` parameter of the name's event handlers (a control becoming a
    control array, or no longer one);
  * `event_stub(obj, event, args, index)` makes a new handler stub (`index`:
    `Index` first, for a control array).

### `vp6/project.py` (≈440 lines)

Project files, which are executable launcher scripts (format in
architecture §6.2).

* `Project` dataclass:
  * fields `name`, `type` (`"exe"` / `"console"`), `startup` (a form class
    name or `SUB_MAIN = "Sub Main"`), `forms`, `modules`, `color_scheme`,
    `icon`, `path`;
  * **the icon:** `icon` lists image files relative to the project (`load`
    turns a single string into a list); `icon_paths()` gives them as absolute
    paths. `add_default_icon()` copies the VP6 icon (`VP6_ICON_FILES`, four
    sizes in the package's `images` folder) into the project's
    `ICON_FOLDER` (`icons`), keeping files already there, and lists them;
  * helpers `directory`, `abspath(relative)` and `kind_of(relative)`
    (`"form"`, `"module"` or None);
  * **groups** (`groups`, how the Project panel shows the files; not folders
    on disk). A group is addressed by its path, a tuple of names (`()` is the
    project), and an item is a file's relative path or a group's path:
    * `tree()` is the normalized list of entries (a file, or
      `{"group": name, "items": [...]}`): the default groups Forms and
      Modules when `groups` is None, files no longer in the project dropped,
      duplicates and junk dropped, unplaced files placed;
    * `group_paths()`, `group_of(relative)`;
    * `place_file(relative, group=None)` puts a new file in a group, by
      default the first group (depth first) holding a file of the same kind,
      else the top level; `remove_file` and `rename_file` keep `forms`,
      `modules` and the groups in step;
    * `add_group(parent, name)` and `rename_group(path, name)` return the new
      path; `delete_group(path)` moves what it held up, in its place;
      `move(item, target)` moves a file or group into a group. A name must be
      non-empty and unique among its siblings, and a group can't go into
      itself: `ValueError` otherwise;
    * `groups` isn't compared as is (`compare=False`); `__eq__` compares
      `tree()`, so a project without groups equals its saved and reloaded
      self;
  * `Project.load(path)`;
  * `project.save(path=None)` rewrites only the region when the file exists,
    else writes `_TEMPLATE`, then makes the file executable;
  * `region()` renders the `PROJECT` dict with comments; `"groups"` is
    written as indented JSON over several lines.
* `parse(text)` → dict. It reads the region, or the whole file if there is no
  region, with `ast`, and raises `ProjectFileError` (a `ValueError`) for
  invalid files.
* `make_executable(path)` adds `x` for every class of user that can read the
  file. It does nothing on Windows.
* Constants: `EXTENSION = ".vp6p"`, `REGION_START` / `REGION_END`, and
  `_FIELDS` (the order the fields are written in).

### `vp6/runner.py` (≈95 lines)

It's deliberately not named `run.py`: importing a `vp6.run` submodule would
replace the public `vp6.run()` function on the package, and `run(Form1)` in
programs would then fail.


Starts a project. `run_project(path)`:

1. loads the project;
2. puts `import_folders(project)` on `sys.path` (the project's folder, then
   every folder holding a form or module, so files in subfolders import each
   other by name) and `chdir`s into the project's folder;
3. sets `App.Title` and `appearance.project_scheme`, and for a windowed
   project with an `icon`, the application's icon (`app.set_program_icon`;
   otherwise the VP6 icon `ensure_app` gives it);
4. starts the program:
   * **`Sub Main`:** calls `find_main(project)()` (modules are searched
     first, then forms). A console project exits with Main's return value if
     it's an int. A GUI project then runs the event loop while forms are open.
     Ctrl+C before any window exists (e.g. at a console `input()`) ends the
     program quietly with exit code 130.
   * **A form:** calls `run(find_form_class(project, startup))`. Modules are
     imported by file name (`_import_file`).

`main(argv)` implements `python -m vp6.runner PROJECT.vp6p` and the `vp6-run`
console script.

---

## IDE: `vp6/ide/`

### `vp6/ide/__init__.py`, `vp6/ide/__main__.py`

Package docstring; `python -m vp6.ide [PROJECT.vp6p]` calls
`mainwindow.main()`.

### `vp6/ide/mainwindow.py` (≈1600 lines)

The IDE shell. `VP6_ROOT` is the folder containing the `vp6` package; it's
prepended to `PYTHONPATH` for programs started with F5.

`MainWindow(QMainWindow)`:

* **Construction.**
  * Calls `theme_manager().manage_application()` (the IDE follows the theme)
    and sets the icon variant.
  * Creates the MDI area, the docks, the actions, the toolbar, the menus
    and the status bar. Panels sharing a place get their tabs above them
    (`setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)`; Qt puts them
    below by default).
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
  * **Outline window** (`outline`, dock `outline_dock`): it shares the
    Properties panel's place (`_place_outline` tabifies it with Properties).
    `_show_side_panel(outline, force)` shows one and hides the other:
    `_on_subwindow_activated` shows the Outline for a code window and the
    Properties panel otherwise, and `_after_last_window` (run when an MDI
    window hides, see `eventFilter`) shows Properties once none is open.
    Automatic switching only happens while one of the two is showing; View >
    Outline Window (`_show_outline`) and F4 (`_show_properties`) force it.
    `_goto_outline_line` opens the code window at a chosen item's line.
  * `_context_path()` is the file the Properties and Outline panels are
    about: the Project panel's selection while it's open, else the active
    window's file. `_update_properties_target()` updates both panels.
  * `_on_dock_moved` / `_tab_bottom_docks`: panels in the bottom dock area
    are always one tab group. This runs on every dock's location, floating
    and visibility changes (coalesced), and after `restoreState`;
  * `_default_layout` / `reset_layout`, `_set_tabbed`, `_show_dock`;
  * `_fill_theme_menu`, `_fill_recent_menu`, `show_options`.
  * **Find, Replace and Go to Line** (Edit menu): `show_find`, `show_replace`,
    `find_next` / `find_previous` (F3 / Shift+F3 everywhere: the standard
    keys include Ctrl+G, the Immediate window's), `goto_line` (Ctrl+L / ⌘L).
    Replace is Ctrl+H like VB6, or ⌥⌘F on macOS (where ⌘H hides the app). They work on `_code_editor()`: the current code
    window's editor, or with a designer current, its form's code window
    (opened if needed). `find_dialog` is one non-modal `FindReplaceDialog`,
    created when first needed.
  * **Placing windows:** `_activate(sub, content_size)` fits a subwindow
    that wasn't showing into the MDI area with `_fit_subwindow`: a new
    designer's window is just large enough for `FormDesigner.preferred_size()`
    plus the subwindow's title bar and borders (`contentsMargins`), or fills
    the area when that doesn't fit (a geometry, not the maximized state,
    which would maximize later windows too); others keep their size, shrunk
    if needed, and are moved inside. Before the main window is shown the
    area has no size, so they wait in `_pending_fits` for `showEvent`.
  * **Menu Editor:** `act_menu_editor` (Tools > Menu Editor, Ctrl+E) runs
    `show_menu_editor`, which opens it for `_current_designer()`: the active
    designer, or the designer of the form whose code window is active.
* **Project lifecycle:**
  * `show_start_dialog`, `new_project`, `open_project_dialog`,
    `open_project(path)`, `close_project()`;
  * `save_all()`, `_confirm_save`, `project_properties`, `_set_startup`,
    `_project_scheme`;
  * `add_form`, `add_module`, `add_file` (new files go in
    `explorer.selected_group(kind)`, else where the project puts that kind),
    `remove_file`;
  * **the Files view's changes on disk:** Project > Add Folder…
    (`act_add_folder`, `add_folder`) switches the Project panel to the Files
    view and makes a folder in its selected folder; `new_folder(parent)` and
    `rename_path(path)` ask with `QInputDialog.getText`; `move_paths(paths,
    folder)` moves each (failures in one message). Renaming and moving go
    through `_relocate(old, new)` (`relocate` also saves and shows it, like
    `_after_relocating` after several), which returns an error message or None: the project file and folder stay put,
    files stay in the project's folder, a folder can't go into itself, and
    nothing is overwritten. A form's or module's file name is its import name,
    so it must stay a `.py` file named like an identifier and unique in the
    project (`_import_names`); a renamed one is changed in the other files'
    imports (`formfile.rename_module_references`). The file or folder is
    renamed with `os.rename`, and the forms and modules in it follow: their
    documents, windows, designers and `FileTarget`s are re-keyed and
    `project.rename_file` keeps their place in the groups. `delete_path(path)`
    asks first, naming the forms and modules that leave the project (and
    lost changes), moves the file or folder to the Trash (`_move_to_trash`,
    `QFile.moveToTrash`; the tests replace it) and forgets its documents
    (`_forget_document`, shared with `remove_file`). `_unique_file` picks a
    new form's or module's name and file in `explorer.selected_folder()`;
    `_relative(path)` is a path as the project lists it;
  * **groups** (the Project panel's, not folders): `new_group(parent)`
    (suggests an unused `GroupN`) and `rename_group(group)` ask with
    `QInputDialog.getText`; `delete_group(group)`; `move_items(items, target)`
    moves each (a failure doesn't stop the others: the failures are shown in
    one message) and selects the moved ones, groups at their new paths. All go
    through `_organize(change, select)`, which shows a `ValueError` (a
    name already used, a group into itself) in a message box, else saves the
    project and repopulates the explorer. A selected group shows its
    `(Name)` in the Properties panel (`group_target`, a `GroupTarget`);
    `_rename_group_object` renames it from there and keeps it selected.
    `_refresh_explorer` keeps a selected group selected;
  * `recent_projects` and `_remember`.
  * **What the Properties window shows:** `_properties_target()` follows the
    Project panel's selection while that panel is open, or the active window
    when it's closed. `_update_properties_target()` applies it; `_target_for_path`
    gives a form's designer, or a module's cached `FileTarget` (`_file_targets`).
    A form always gets a designer, so all its properties and controls show:
    `_designer_for(path)` creates one that isn't in a window yet (kept in
    `_designers`, which holds every designer; `view_object` later puts that
    same designer in a window), and `_discard_designers` deletes those when
    the file or the project is closed. Designers get `form_name_taken`, so a
    form can't be renamed to another form's name. It is
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

**Ctrl+C** in the terminal that started the IDE works like File > Exit (Quit
VP6). `main()` installs `app.install_interrupt_handler(act_exit.trigger)`,
which closes any open modal dialog first (e.g. New Project at startup) and
ignores repeats while the save prompt is showing. MainWindows created in
tests don't have it.

`main()` also starts an `OutputCapture` before the `QApplication` exists, so
Qt's startup messages are included. It attaches the capture to the Output
window (`output`, dock `output_dock`, hidden by default and tabbed with the
Immediate window; View > Output Window) and stops it on quit.

Module functions:

* `create_project(location, name, template)` creates a project folder. Every
  template gets `Form1.py`, `Module1.py` and the `.vp6p`, and starts in Sub
  Main. The console template's `Main` uses `print()`/`input()`; the Standard
  EXE template's `Main` shows Form1. `"kitchensink"` delegates to
  `kitchensink.create`, which also adds its pages (`pg*.py`), `frmDialog.py`
  and `vp6.png`. Every template's project gets the VP6 icon
  (`Project.add_default_icon`: the `icons` folder).
* `main(argv)` is the application entry point. It gives the application the
  VP6 icon (`app.vp6_icon`: the Dock or taskbar); `MainWindow` sets it on
  itself too.

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
    a Line's two end handles (`_line_handles`), the rubber band, and the
    rectangle of a control being drawn.
  * **Mouse:** drag kinds `draw` (a Line goes from the press to the release),
    `move` (snapping `snap_anchor`: the top-left corner, or a Line's start),
    `resize`, `endpoint` (a Line's end), `form_resize` and `band`.
    Alt disables snapping; Shift/Ctrl add to the selection; Ctrl+drag inside
    a container draws a band inside it; double-click requests the default
    event's code; right-click opens the context menu.
  * **Keyboard:** arrows move by the grid (Ctrl: 1 px), Shift+arrows resize,
    Esc cancels the tool or selects the parent, Delete/Backspace deletes.
* **`FormDesigner(QWidget)`** (signals: see architecture §5.3):
  * **Keys:** controls are identified by their key (`formfile.control_key`):
    `Command1`, or `cmdDigit(3)` for a control array element. `controls`,
    `selection`, `canvas_rect(key)` and the containers of `ControlDef`s all
    use keys; `key_of(control)` gives a live control's key.
  * **Building:** `load_def(form_def)`, `_instantiate`, `_prepare_widget`
    (NoFocus), `_layout_form` (below the frame's title bar),
    `update_canvas_size`, `preferred_size()` (what shows the whole form, used
    to size its window). `eventFilter` calls `update_canvas_size` on the
    scroll area viewport's resize, so the canvas fills the window after
    maximize and restore.
  * **Scheme and frame:** `set_project_scheme`, `refresh_scheme` (also on
    OS light/dark changes, via `_on_os_scheme_changed`),
    `frame_style()`, `frame_info()`, `_on_ide_theme_changed`.
  * **Geometry:** `form_widget`, `form_canvas_rect`, `canvas_rect(name)`,
    `parent_rect(name)`, `control_at(pos)`, `container_at(pos)`.
  * **Selection:** `select`, `select_by_name`, `selected_objects`,
    `object_name` (the key), `name_value` (the `(Name)`), `supports_index`,
    `all_objects`, `set_tool`. An empty selection means the form.
  * **Commits and undo:** `_snapshot`, `_commit` (which first calls
    `_sync_aligned`, storing where the form docks its aligned PictureBoxes,
    also after they were dragged or the form resized), `commit_geometry`,
    `commit_form_size`, `undo`, `redo`, `_restore`.
  * **Editing:**
    * `unique_name`, `create_control`, `add_control_centered`;
    * `delete_selection` (with descendants), `copy_selection`,
      `cut_selection`, `paste` (offsets duplicates; `_paste_identity` gives a
      copy a new name, or makes it an element of a control array),
      `select_all`;
    * `_renumber_tab_order(moved, last)` keeps `TabIndex` values 0, 1, 2, …
      without gaps or duplicates, like VB: added and pasted controls go to
      the end, deleting closes the gap, and setting a control's `TabIndex`
      moves it to that place (clamped to the last one) while the others make
      room. It runs inside the same commit, so one undo reverts it;
    * `set_property(prop, value)` returns an error message or `None`;
      `rename(new_name)` handles controls (the name of another control of
      the same type joins its control array) and the form class
      (`_rename_form`, which `form_name_taken` checks against the project);
    * **lines:** `is_line`, `line_points` / `line_point` (the ends on the
      canvas), `line_at(pos)` (a Line near a point, within its width; checked
      first by `control_at`, since a Line's widget ignores the mouse and its
      box may cover other controls), `move_line_point` (dragging an end,
      snapped in the Line's container) and `snap_anchor`. `create_control`
      takes the release point (`end_pos`) for a Line; `commit_geometry` stores
      a moved Line's points (`Line._moved_points`); pasted Lines are offset
      by their points; Shift+arrows don't resize them;
    * **menus:** `is_menu`, `menu_selected`, `menu_bar_keys` (the visible
      top-level menus, drawn by `chrome`), `menu_rect`, `menu_at(pos)`,
      `menu_popup(key)` (the drop-down as it will look; choosing an item
      emits `viewCodeRequested(name, "Click")`), `show_menu_popup`,
      `menu_entries`, `show_menu_editor` and `set_menus(entries)` (the Menu
      Editor's OK: validates, replaces the `Menu` ControlDefs, renames the
      handlers of renamed menus, adds or removes `Index` in them, reloads,
      one undo step). Menus have no widget: selecting one keeps it alone,
      and `select_all`, the band, `commit_geometry`, copying and the Format
      commands skip them;
    * **control arrays:** `set_index(value)` (the Index property),
      `ask_create_array(name)` (VB's question; tests replace it),
      `_make_array(name)`, `_next_index`, `_rekey(key, name, index)` (renames
      or re-indexes a control everywhere it is referred to by key) and
      `_set_index_parameter(name, present)` (adds or removes `Index` in the
      handlers);
    * Format menu: `align`, `make_same_size`, `center_in_form`, `nudge`,
      `z_order`;
    * `show_context_menu`.

### `vp6/ide/chrome.py` (≈330 lines)

Window frames painted around the designed form.

* Styles are `AUTO`, `MACOS`, `WINDOWS`, `GNOME` and `CLASSIC`
  (`FRAME_STYLES` holds their labels); `resolve(style)` maps `AUTO` to the
  running OS's style.
* `FrameInfo` holds what's needed from the form: caption, border style,
  control box, min/max buttons, whether the title bar and form are dark, and
  the captions of the form's menu bar (`menus`). Its properties `tool`, `can_minimize` and `can_maximize` mirror the runtime
  window-flag logic.
* `metrics(style, info)` gives the title bar height and border width.
  BorderStyle 0 means no frame; tool windows get smaller title bars.
* `frame_rect(client, style, info)` and `paint(p, style, client, info)`.
  With menus, a menu bar (`MENU_HEIGHT`, `menu_height(info)`, drawn by
  `_menu_bar` in the form's light/dark scheme) goes between the title bar
  and the form; `menu_item_rects(client, info)` gives where each caption is,
  for clicks.
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
    `_edit_allowed(key)`, `range_editable(start, end)` and `_reject_edit`;
    `insertFromMimeData`, `cut` and `paste` are guarded.
  * **Editing keys:** `keyPressEvent` handles the completion popup, the
    region guard, Enter with auto-indent (`_newline_with_indent`, which also
    dedents after `return`/`pass`/…), Tab/Shift+Tab (`_indent`),
    `_smart_backspace`, Ctrl+/ (`toggle_comment`) and Ctrl+Space.
  * **Completion and navigation:** `_show_completions` / `_insert_completion`
    (`QCompleter` with a `QStringListModel`); `goto_line(line)` and
    `select_range(start, end)` unfold the region if needed (`_unfold_for`);
    `current_line()`.
* **`complete(context, document)`**, the completion provider (see
  architecture §5.4). `_members(cls)` lists a class's spec names plus its
  public capitalized members. For a control array, `self.cmdDigit.` gives
  the `ControlArray` members and `self.cmdDigit[i].` / `self.cmdDigit(i).`
  the control's.
* **`CodeWindow(QWidget)`**, the combos plus the editor:
  * `refresh_combos` (debounced 300 ms after text changes), `_fill_procs`
    (handlers that exist are shown bold);
  * `_on_object_chosen` jumps to an existing handler or the default event;
    `_on_proc_chosen`;
  * `_objects()` lists the form and each control name once (a control
    array is one object);
  * `goto_event(obj, event)` jumps to the handler, or inserts a stub after
    `_class_end_line()` and selects `pass` (with `Index` for a control
    array);
  * `_goto_def`, `_sync_combos_to_cursor`.

### `vp6/ide/properties.py` (≈290 lines)

* `TextListDialog` edits a list (one item per line) or multi-line text.
* `PropertiesWindow(QWidget)`:
  * **Binding:** `set_designer(designer)` connects to `selectionChanged` and
    `designChanged`; `refresh()` rebuilds the object combo and the grid
    (common properties across the selection; `_MIXED` marks differing
    values). A single control also gets the `Index` row (`INDEX_SPEC`, kind
    `index`, empty = not in a control array) under `(Name)`, when the target
    has `supports_index`; `(Name)` shows the target's `name_value`. The
    `shortcut` kind (`Menu.Shortcut`) is edited with a combo box, and the
    `outline` kind (`TreeView.Items`) like a list, in a `TextListDialog` with
    a hint about indentation and keys.
  * **Editors:** `_editor(spec, value)` picks an editor by kind;
    `_color_editor`, `_choose_color`, `_edit_list`, `_edit_text` and
    `_browse_file` (stores paths relative to the form folder when possible).
  * `_commit(prop, value)` calls `designer.set_property` and shows any error.
  * The description pane shows the spec's `description`.
  * `select_property(name)` focuses a property's row and editor.
  * The window is bound to a target with `set_designer(target)`: a
    `FormDesigner`, or the `ProjectTarget` (see `projectprops.py`).

### `vp6/ide/projectprops.py` (≈250 lines)

The project, files without a designer and Project panel groups, as targets
of the Properties window.

* `ProjectTarget(QObject)` offers the same interface as `FormDesigner`
  (`selected_objects`, `all_objects`, `object_name`, `select_by_name`,
  `set_property`, `base_dir`, signals `selectionChanged` / `designChanged`).
  The Properties window therefore edits the project without special cases.
* It exposes the project's `(Name)`, `Type`, `StartupObject` and
  `ColorScheme` as `enum` specs. `StartupObject`'s choices are the project's
  forms plus `Sub Main`. `Icon` is a `file`: the icon's last file (the
  largest size, as new projects list them); setting it makes that one file
  the icon, and an empty value none (the VP6 icon).
* `set_property` validates the name, updates the `Project`, and calls the main
  window's `_project_changed` (save, update designers, explorer and titles).
* `_ProjectObject` is the "selected object" the grid reads values from.
* `TYPE_CHOICES` and `COLOR_SCHEME_CHOICES` are shared with
  `ProjectPropertiesDialog`.
* `FileTarget(QObject)` is the same interface for a module (the IDE gives
  forms a designer instead, even when it isn't open). It shows just `(Name)`
  (through `_FileObject`, which has no specs). `set_property("Name", …)`
  calls the main window's `_rename_file_object`, which also handles forms.
* `GroupTarget(QObject)` is the same interface for a Project panel group
  (`group`, its path): just `(Name)`, through `_GroupObject`. One instance
  serves every group: `set_group(path)` switches to another and emits
  `selectionChanged`, so the Properties window refreshes even though its
  target object stays the same. `set_property("Name", …)` calls the main
  window's `_rename_group_object`. It has a `name_description` for the
  description pane, which the Properties window uses instead of its default
  "the name used in code" text.

### `vp6/ide/findreplace.py` (≈300 lines)

Find and Replace in the code window, and Go to Line.

* **The search, plain Python:** `SearchOptions` (`find`, `replace`,
  `match_case`, `whole_word`, `regex`); `compile_pattern(options)` (the text
  is escaped unless `regex`; whole word adds `(?<!\w)…(?!\w)`; always
  `re.MULTILINE`, plus `re.IGNORECASE` without match case);
  `replacement(match, options)` (`match.expand` for regular expressions, so
  `\1`, `\g<name>`, `\n` and `\t` work; literal otherwise);
  `find_in(text, pattern, start, backward, skip)` finds the next or previous
  match, wrapping around, never the current selection (`skip`) again.
* **`_Positions`** maps Python string indexes to Qt text positions, which
  count characters outside the BMP (emoji) as two.
* **On a `CodeEditor`:** `find_as_you_type(editor, options)` selects the
  first match at or after the start of the selection (wrapping; nothing
  selected without a match or text; an unfinished regex leaves it alone),
  `find_next(editor, options, backward)`,
  `replace_one` (replaces the selection if it is a match, then finds the
  next one) and `replace_all` (one undo step, from the end backwards so
  positions stay valid). Matches in a form's designer region are found (the
  region unfolds) but never replaced (`CodeEditor.range_editable`). Each
  returns a `Result(found, message)`.
* **`FindReplaceDialog(get_editor)`**, non-modal: find and replace fields,
  *Match case*, *Find whole word only*, *Use regular expressions*, a status
  line, and Find Next / Find Previous / Replace / Replace All / Close.
  `show_find(replace)` shows it as Find or Replace, taking the selected text
  (one line) as the text to find. Typing in the find field, or changing an
  option, runs `find_as_you_type`, so the first match is highlighted as you
  type.
* **`ask_line(editor, parent)`**, the Go to Line box (`QInputDialog.getInt`,
  1 to the line count, the current line suggested).

### `vp6/ide/menueditor.py` (≈330 lines)

The Menu Editor.

* `MenuEntry` is one menu as the editor sees it: `level` (0 = the menu bar),
  `caption`, `name`, `index`, `shortcut`, `checked`, `enabled`, `visible`,
  other `props` kept as they are, and `original` (its key before editing,
  so renames can move its handlers).
* `entries_from(form_def)` lists the form's menus depth first;
  `menu_defs(entries)` turns entries into `Menu` ControlDefs (parents from
  the levels, only non-default values); `validate(entries, taken)` checks
  names (valid, unused by other controls, unique keys, arrays with an Index
  each), levels (at most one deeper than the item above, `MAX_LEVEL`) and
  separators (not on the menu bar, no items of their own).
* `MenuEditorDialog(entries, taken)`, like VB's: Caption, Name, Index,
  Shortcut, NegotiatePosition (kept in the entry's `props`) and Checked /
  Enabled / Visible for the current item, the arrow
  buttons (`outdent`, `indent`, `move_up`, `move_down`), `next` (a new item
  at the end), `insert`, `delete`, and the indented list (`····` per
  level). `result_entries()` drops blank items; OK refuses invalid menus
  with the `validate` message.

### `vp6/ide/outline.py` (≈300 lines)

The Outline window: the structure of a source file.

* `outline(source)` reads the file with `ast` (never runs it) and returns
  `OutlineItem`s (`name`, `kind`, `line`, `children`, `detail`, `spans`), in
  file order. `spans` are the (first, last) lines an item covers (`_span`): a
  definition from its first decorator to its last line (`end_lineno`):
  * module-level assignments are `constant` (ALL_CAPS names) or `variable`;
  * classes are `class`, with their members: `method`s, `attribute`s and
    nested classes;
  * module-level functions are `function`;
  * one `*global code*` item (`code`) points at the first top-level
    statement that isn't an import, definition or assignment. Its `detail` is
    that line; its `spans` are all such statements.
  * Imports and docstrings are skipped. `InitializeComponent` is listed as a
    method, without its contents.
* `sorted_outline(items, key, descending)` sorts by `"order"` (line),
  `"name"` or `"type"` (the `KINDS` order), recursively.
* `item_path_at(items, line)` is the items covering a line, outermost first
  (`[class, method]`); empty on a blank line between definitions or an
  import.
* `OutlineWindow(QWidget)`:
  * **Sort buttons** (`buttons`, `sort_by`): clicking the active one reverses
    it, and the active one shows ▲/▼.
  * **Problem label:** shown on a syntax error; the last good outline stays.
  * **Tree:** icons from `KIND_ICONS`; tooltips give the kind and line.
  * `set_document(doc)` follows the document's edits, debounced 300 ms
    (`refresh`).
  * Clicking or activating an item emits `lineChosen(line)`.
  * **Following the cursor:** `set_line(line)` (the main window's
    `_sync_outline_line`, on every code editor's `cursorPositionChanged` and
    whenever the Outline's document changes, passes the active code window's
    cursor line when it shows that file, else None) makes the innermost item
    at that line current (`_highlight`, `_node_for`: found by name, kind and
    line at each level, so it works in any sort order); nothing is current
    off any item. It is applied again after every re-read and re-sort.

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

### `vp6/ide/panels.py` (≈920 lines)

* **`Toolbox`:**
  * checkable tool buttons (the pointer plus the `CONTROL_TYPES` whose
    `InToolbox` is true: not `Menu`) with signals
    `toolSelected(type | None)` and `toolActivated(type)` (double-click);
  * `reset()` goes back to the pointer; `refresh_icons()` is used after
    light/dark changes.
* **`ProjectExplorer`:**
  * a tree of the project's groups, forms and modules (`project.tree()`: groups,
    not folders on disk), with the startup object in bold. The project item
    can't be collapsed: the tree doesn't decorate top-level items
    (`setRootIsDecorated(False)`), and `_keep_project_expanded` re-expands
    it on `itemCollapsed` (double-click, Left or minus key).
    The `expand_button` ("+" / "-", `toggle_expanded`) expands every group
    (`expand_all`) when any is collapsed, else collapses them all
    (`collapse_all`; the project item stays open, showing the top level).
    `all_expanded()` decides; `_update_expand_button` follows
    `itemExpanded` / `itemCollapsed`. `populate` keeps collapsed groups
    collapsed (`_collapsed`, by group path) unless it's another project,
    which starts with everything open.
  * **Two views** (`project_button` / `files_button`, `set_view(files,
    hidden)`, `viewChanged(files, hidden)` for the user's choice, stored by
    the main window under `explorer/files` and `explorer/hidden`):
    * the Project view (`files_mode` False) described above;
    * the Files view shows the project's folder as it is on disk
      (`_add_folder`): folders (kind `"folder"`) and every file, sorted like
      the groups ("Folders, Name ▲" …). Forms and modules are `_add_file`
      items as in the Project view (labelled with the file name), so opening,
      View Object, Set as Start Up, Remove and following the active window
      work the same; any other file is a `"file"` item with the system's icon
      (`QFileIconProvider`) and nothing to open. Item data `+3` is the absolute
      path of every item. Hidden files and folders (a leading dot, or
      `QFileInfo.isHidden`) are left out unless `show_hidden`
      (`hidden_button`, shown only in this view). Never shown, whatever the
      Hidden button says (`_never_shown`): the project file, and anything
      named `.git` or `__pycache__` (`NEVER_SHOWN`), in any folder. Symbolic
      links to folders are listed, not followed;
    * there are no groups in the Files view (no New Group…; `selected_group`
      is None, so new files go in the default group). Instead it changes the
      disk: its context menu (`_files_menu`) has New Folder… (in a folder or
      the project's folder, or next to a file), Rename…, Delete and **Move to** (the project's folder and
      every folder shown but its own and, for a folder, itself and its
      subfolders), emitting `newFolder(folder)`, `renamePath(path)`,
      `deletePath(path)` and `movePaths(paths, folder)`; dragging onto a folder,
      a file (its folder) or the project item (the project's folder) emits
      `movePaths` too (`_request_move`). The project file (`_is_project_file`)
      isn't listed, and `relocate` / `delete_path` refuse it anyway. For a
      form or module, "Remove …
      from the Project" (not deleting the file) stays;
    * the `new_folder_button` (shown in the Files view only) emits
      `newFolder(selected_folder())`;
    * `selected_folder()` is where a new form, module or folder goes: the selected
      folder, the selected file's folder, or the project's folder. `_item_path`
      (the project's folder for the top item) and `_folders()` help;
    * a `QFileSystemWatcher` on the folders shown calls `refresh()` (the last
      `populate` again, keeping the selection) 150 ms after the last change;
    * switching views keeps a selected form or module selected (by path);
      `+`/`-` works on folders, and collapsed groups and folders are
      remembered for each view (`_collapsed[files_mode]`). Within each group
    everything is sorted by name, case-insensitively: A to Z or Z to A
    (`sort_descending`), with the subgroups first or sorted in among the
    files (`groups_first`). The `sort_button` ("Groups, Name ▲", "Name ▲",
    "Groups, Name ▼", "Name ▼") calls `toggle_sort`, which moves to the next
    of the four `SORT_ORDERS` and emits `sortChanged(descending,
    groups_first)`. `set_sort(descending, groups_first=True)` re-sorts the
    last `populate`, keeping the selection. The main window stores the
    choice under `explorer/descending` and `explorer/groupsFirst` in the
    settings;
  * View Code / View Object buttons, and double-click to open;
  * `context_menu(item)` builds the context menu (testable without showing
    it): View Code / View Object / Set as Start Up / Remove for a file;
    Rename Group… / Delete Group for a group; a **Move to** submenu for files
    and groups ("(Project)" and every group but the current one and, for a
    group, its own subgroups); New Group…, Add Form, Add Module;
  * **drag and drop** (`_ProjectTree`, a `QTreeWidget` with `InternalMove`
    and `ExtendedSelection`, so several items can be selected with Ctrl/Cmd-
    and Shift-click and dragged at once): its `dropEvent` doesn't move
    anything itself but calls `_request_move(selected items, target)`, which
    emits `moveItems(items, group)` into the group dropped on, the dropped-on
    file's group, or the top level for the project; the main window changes
    the project and repopulates;
  * **moving several items:** `move_sources(item)` is what a move moves: the
    selected items (or `item` alone when it isn't selected), only movable
    ones (not the project item or file), and not those inside a selected
    group or folder, which move with it (`_sources_of`); each is `(kind,
    ref, place)` (`_source`). `_can_move_to(sources, target)` leaves out
    targets where they all are already and targets inside one of them. The
    Move to submenu ("Move N Items to" for several) and drops use them.
    Right-clicking an item of the selection keeps the selection
    (`_on_context_menu`). `select_refs(refs)` and `select_paths(paths)`
    select the moved items afterwards (`_select_all`);
  * signals `openObject`, `openCode`, `removeFile`, `setStartup`, `addForm`,
    `addModule`, `newGroup(parent)`, `renameGroup(group)`,
    `deleteGroup(group)`, `moveItems(items, group)`; `populate(project, names)`.
    Item data: `UserRole` a file's absolute path, `+1` the kind (`"form"`,
    `"module"`, `"group"`, `"project"`), `+2` the name, `+3` the relative
    path or the group's path (a list of names);
  * `items()` walks every item by `child()`. `QTreeWidgetItemIterator` isn't
    used: the Python wrappers of its items crashed the next `clear()`;
  * `selected_group(kind)` is the group a new file goes in: the selected
    group, or the selected file's group when it's the same kind; else None,
    and the project's default applies. `select_group(path)`;
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

The Kitchen Sink project template: a demo of every control and feature,
explorer-style.

* `create(directory, name)` copies `FORMS` (the window, its pages in the
  index's order, and the dialog) and `MODULES` (`Module1.py`) from
  `TEMPLATE_DIR`, draws the picture `PICTURE` (`vp6.png`, via
  `draw_picture`, so the package ships no binary), and returns a Standard
  EXE `Project` that starts in Sub Main. `mainwindow.create_project(...,
  "kitchensink")` calls it.
* **`templates/kitchensink/Form1.py`**, the explorer window. It is laid out
  with docked controls: the StatusBar `sbStatus` (Bottom; a Spring status
  panel that `status(text)` sets, Caps Lock, and a clock that
  `sbStatus_PanelClick` switches between the time and the date), `picNav`
  (Left, holding the TreeView `tvwIndex`), the Splitter `splNav`, `picHeader`
  (Top, the page title) and `picContent` (Fill, with scroll bars). The
  PictureBoxes' Resize events size what is on them.
  * `PAGES` maps each index key to a page's form class. `show_page(key)`
    creates a page once (giving it `shell`, the window), shows it in
    `picContent` with `ShowIn` (replacing the one there), selects its node
    and shows its title; `tvwIndex_NodeClick` calls it (a section node shows
    its first page). `page_titles()` lists the pages for the Menus page.
  * Menus: File (End with Ctrl+Q, Close), View (the navigation pane, and the
    color schemes as the menu control array `mnuScheme`), Bookmarks (the
    menu control array `mnuBookmark`, grown by `add_bookmark`) and Help
    (Keys with F1, About).
  * `set_scheme(index)` keeps the window's ColorScheme, the View menu and
    the Color schemes page in step; `show_navigation(visible)` hides or
    shows the navigation pane and its Splitter.
  * `Form_Unload` asks first, then unloads the pages (also one popped out).
* **The pages** (one form each, shown in the content pane):
  * `pgIntro.py`: the introduction, a Markdown Label whose links show pages;
  * `pgText.py`: Labels (alignment, AutoSize, access keys) and TextBoxes
    (multi-line, password, upper-casing KeyPress), GotFocus/LostFocus,
    Change, a Default button with InputBox/MsgBox, a Frame's Click;
  * `pgButtons.py`: CommandButtons (Value = True clicks), CheckBoxes (also
    grayed), OptionButtons in two Frames (two groups);
  * `pgLists.py`: a sorted ListBox with Add/Remove, Click and DblClick,
    ComboBoxes (a list with colors from `vpRed`, `RGB` and `QBColor`, and an
    editable one);
  * `pgScrollBars.py`: HScrollBar and VScrollBar, Change and Scroll;
  * `pgTabs.py`: a TabStrip with a Frame per tab over its client area
    (placed in Form_Load, shown in Click), BeforeClick cancelling while "Lock
    the tabs" is checked, and Placement from a ComboBox;
  * `pgValues.py`: Slider (Scroll and Change, a vertical one with ticks on
    both sides), ProgressBar (filled by a Timer, and a vertical one following
    the Slider), UpDown with a TextBox buddy (UpClick, DownClick, Change) and a
    horizontal, wrapping one with a Label buddy;
  * `pgPictures.py`: a PictureBox with a Label on it (Click, MouseDown, a
    Tag from InputBox) and an Image thumbnail;
  * `pgZOrder.py`: ZIndex and ZOrder, Lines (a dashed one above the labels,
    a control array of Lines with BorderStyle 1 to 5, a thick one);
  * `pgTree.py`: a TreeView with check boxes, adding and removing nodes,
    NodeClick/NodeCheck/Expand/Collapse;
  * `pgTimer.py`: a clock whose Timer runs only while the page is visible
    (Form_Activate / Form_Deactivate);
  * `pgLayout.py`: how the window is laid out, hiding and widening the
    navigation pane;
  * `pgScrolling.py`: a page 1000 pixels tall, and ScrollTop;
  * `pgEmbedded.py`: a page popping out into a window of its own and back
    (`ShowIn(None)`), laid out with a Bottom and a Fill pane, with a clock
    that runs while it is visible;
  * `pgDialogs.py`: MsgBox, InputBox, the modal `frmDialog`, Beep;
  * `pgSchemes.py`: the color schemes as the option-button control array
    `optScheme` (`SCHEMES`);
  * `pgKeyboard.py`: KeyPreview, KeyDown/KeyUp, KeyPress replacing or
    swallowing keys, Default and Cancel buttons;
  * `pgMouse.py`: MouseDown/MouseMove/MouseUp with buttons, Click, DblClick;
  * `pgArrays.py`: the `cmdMore` control array loading and unloading
    elements;
  * `pgMenus.py`: the menus, adding bookmarks (a menu control array grown
    at run time), and a Page menu of its own that joins the window's menu
    bar while the page is visible (NegotiatePosition; the window's Help is
    Right too, so it stays last);
  * `pgGlobals.py`: App, Screen, Forms, Clipboard, DoEvents, Debug.Print and
    End.
  Pages that talk to the window use their `shell` attribute (None when a
  page runs on its own).
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
* `AboutDialog` shows the logo (`logo_pixmap(width)`: `LOGO_PATH`,
  `vp6/ide/images/vp6logo.png`, a 720-pixel-wide copy of the repository's
  `images/vp6logo.png`, shown `LOGO_WIDTH` = 360 pixels wide at device pixel
  ratio 2, so it is sharp on high-DPI screens) above `ABOUT_HTML`. The
  image is package data (`pyproject.toml`).
* The main window's `show_about()` opens it from Help > About VP6
  (`act_about`, `QAction.NoRole`, so Qt doesn't move it out of the Help
  menu on macOS) and, on macOS, from the application menu (`act_about_app`,
  `AboutRole`).

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
  * one per Toolbox control, keyed by `TypeName` (`Line`: `_line`, `Image`:
    `_image`, `TreeView`: `_treeview`, `Splitter`: `_splitter`),
    plus `Pointer`;
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
* fails a test when Python code called by Qt raised (an event handler
  override or a slot run from the event loop), which PySide only prints
  through `sys.excepthook` (`_fail_on_errors_in_qt_callbacks`);
* provides `wait_for(predicate, timeout_ms)` (PySide has no
  `QTest.qWaitFor`).

| File | Covers |
|---|---|
| `test_runtime.py` | Events (click, Default/Cancel keys, KeyPress transform/cancel), Value properties, lists, Timer, Unload cancel, the typo guard, TextBox MultiLine rebuild, colors, handler arity and error reporting, MsgBox results, `End()` ending a program (in a process of its own) without Form_Unload. |
| `test_formfile.py` | Region round trips, default elision, line wrapping, invalid regions, renames (controls, form classes, class and module references in other files), the console template. |
| `test_control_arrays.py` | Control arrays: elements, `[i]` / `(i)` / `Item`, iteration, bounds, read-only `Index`, handlers getting `Index` first, `Load`/`Unload` of run-time elements (copied properties, hidden, last in the tab order; designer elements can't be unloaded), one type per array; the form file round trip (elements as containers too) and invalid arrays; adding/removing the `Index` parameter and stubs; in the designer: paste asking to create an array, renaming into an array (and out, and into another type's name), the Index property (one-element arrays, moving, clearing, undo), containers that are elements; the Properties window's `(Name)`, `Index` row and object list; the code window's Object list, new handlers with `Index`, completion. |
| `test_menus.py` | Menus at run time: the menu bar and items, separators, shortcuts; an in-window menu bar keeping `Height`, `ScaleHeight` and control positions for the area below it (the window grows), form mouse events there; Click on choosing an item and before a menu opens; `Checked` changing only in code; Enabled, Visible, Caption and Shortcut changes; menu control arrays loading after their last element and unloading; the parent check; the form file round trip; the Menu Editor's entries and ControlDefs, validation messages and dialog editing (Next, indent, shortcut, Insert, Delete, moving, outdent); menu negotiation (merged by NegotiatePosition, left out for None, the inner handlers, leaving when hidden or replaced, popped out with its own bar, NegotiateMenus off, a position changed and a menu added while merged, a window without menus, the Menu Editor's NegotiatePosition); the designer's menu bar (layout, hit testing, the drop-down opening Click code), menus kept off the canvas and edited in the Properties window, deleting a menu with its items, renames and arrays updating handlers, undo; the IDE's Tools > Menu Editor (Ctrl+E). |
| `test_image.py` | The Image control: taking the picture's size without Stretch (and with a border), filling the control with Stretch, switching back, clearing the picture; mouse events, no focus or Tab stop, not grayed but silent when disabled, transparent; its properties in order and the form file; in the designer: sized by a new picture, resized with Stretch, the Properties rows; the Toolbox button and icon. |
| `test_embedded_forms.py` | Activate/Deactivate in a container (Load then Activate; hidden and shown, the container hidden and shown, popped out, unloaded), a filling form replacing another (no second Load; Fill=False forms staying), window activation not applying; `Form.ShowIn`: filling a PictureBox and following its size (Load before the first Resize), controls working, window-only properties not popping it out; a Frame's inside, a form as the container, `Fill=False` at Left/Top; popping out, moving between containers, Hide/Show; unloading only itself, going with its host (unable to cancel), a host that cancels keeping it; invalid containers and cycles; nested forms and Default buttons. |
| `test_align.py` | PictureBox `Align`: docking in creation order, Fill panes taking the space left (after the others, several sharing it), following the form (before Form_Resize), changing a pane's thickness, place, visibility and Align; only on the form; panes created in code; under an in-window menu bar; in a form shown in a container; in the designer (Align stored with the docked geometry, the form resized, a pane dragged back, undo); the constants. |
| `test_splitter.py` | The Splitter: docking beside its pane, cursors, dragging (live Resize with everything in place, Moved on release), Bottom/Top/Right panes growing the right way, MinSize on both sides, disabled, no pane; the PictureBox Resize event; the file, the designer (docked after the pane) and the Toolbox. |
| `test_statusbar.py` | The StatusBar: the designer's panel lines (`parse_panel`); docking at the bottom beside other docked controls, following the window (Spring panels growing), Top, hidden taking no space; the Panels collection (Index and Key, Add at an Index, unique keys, errors, Contents and fixed widths, Alignment, ToolTipText, hidden panels, Remove, Clear, changing a Key); time and date panels kept up to date, lock keys dimmed when off; Simple style; PanelClick, Click and PanelDblClick from the mouse; the form file round trip; creating it in the designer (docked, one panel to start, no clock running, the Properties window's Panels); Toolbox, icon and constants. |
| `test_tabstrip.py` | The TabStrip: the designer's tab lines (`parse_tab`); tabs, captions and tooltips; the selection (the first to begin with, no Click while loading, SelectedItem by Key, Index or Tab, `Selected`, Click from code); the user's clicks, BeforeClick cancelling, no BeforeClick for the selected tab; Add before the others keeping the selection without Click, Caption and ToolTipText, errors, Remove, Key changes, Clear; the client area for every Placement (equal to Qt's layout, and already right in Form_Load), a Frame over it on top; the form file round trip; the designer (one tab to start, the Properties window's Tabs); Toolbox, icon and constants. |
| `test_scrolling.py` | PictureBox ScrollBars: bars appearing for controls beyond the edges (both directions), ScrollLeft/ScrollTop and the Scroll event moving the contents, bars following moved, added and hidden controls, one direction only, turning it off, controls and Click on the empty area still working, a taller form shown inside scrolling, the designer not scrolling. |
| `test_label_text.py` | Label TextFormat: plain text hiding access keys, rich text and Markdown (really rendered), switching back; links firing LinkClick or opening the browser without a handler, only for formatted captions; the file and the designer (links off while designing, the multi-line Caption editor); the constants. |
| `test_treeview.py` | The TreeView: reading outlines; the Nodes collection (key, Index from 1, errors for unknown or duplicate keys); every relationship of `Add`; relatives, FullPath and PathSeparator; removing with children and clearing; node Text/Key/Tag/Bold/ForeColor/Image, EnsureVisible, sorting the tree and a node's children; code changes firing no events; NodeClick on clicks (also on the selected node) and keyboard moves, Expand/Collapse from the keyboard, HitTest; check boxes and NodeCheck; LineStyle, Indentation, Items; the form file; in the designer (Items building an expanded tree, the Properties button, a `Node` handler stub); the Toolbox button, icon and constants. |
| `test_values.py` | ProgressBar (Value kept inside Min..Max, also when they change; orientation; Click), Slider (Scroll while dragging and one Change after, Change for code and keys, LargeChange, tick styles and frequency, orientation), UpDown (steps, Max without Wrap, Change / UpClick / DownClick, a TextBox buddy shown and read back, typed numbers clamped or ignored, Increment, wrapping, a Label buddy's Caption, BuddyProperty, a missing buddy, SyncBuddy off, horizontal arrows); the form file round trip; creating them in the designer (arrows inactive there); Toolbox, icons, default events and constants. |
| `test_line.py` | The Line control: its widget following the points, drawing (color, Transparent, Visible, the scheme's text color by default), clicks going through it, ZIndex; the form file; in the designer: drawing from press to release and by a click, selecting near the line (not its box), dragging an end, the move cursor over an end, moving, arrow keys (no resizing), undo, pasting with an offset, the Properties rows, no event stub; the Toolbox button and icon. |
| `test_designer.py` | Creating controls, nesting in frames, mouse move with snapping and undo, rubber band, properties and rename, copy/paste, TabIndex renumbering (add, delete, paste, setting one, undo), z-order and Format, code-side undo reloading the designer, region protection in the editor, the workspace filling the window after maximize/restore. |
| `test_findreplace.py` | Match case and whole word; wrapping forwards and backwards; regular expressions with escapes across lines, groups in the find and replace text and per-line `^`/`$`; Find Next/Previous, Replace and Replace All (one undo step) in an editor; invalid patterns and replacements; positions after emoji; the designer region skipped when replacing and unfolded when found; the dialog; highlighting the first match as you type (growing matches, options, wrapping, not found, unfinished regexes, clearing); in the IDE: the Edit menu, Find from a designer opening the code window, Go to Line. |
| `test_ide.py` | New projects (every template has Form1 and Module1 with `Main()`; the Standard EXE's `Main` really shows Form1; it opens in the designer), adding forms and modules, double-click creating handlers, completion, running a console project with stdin, traceback reporting, toolbar and layout reset, bottom-edge panels always tabbed (also after restoring a side-by-side layout), the theme toggle, ⌘/Ctrl+Enter, the Immediate Clear menu, `VP6_IDE_SCHEME` passing, the Project Explorer following the active window, project properties in the Properties window, the Properties panel following the Project panel's selection (or the active window when that panel is closed), module Names and all properties of unopened forms, renaming modules and forms from the Properties window (not to another form's name), a renamed Form1 still running, the IDE exiting without errors, Ctrl+C (SIGINT) quitting the IDE like File > Exit (also from the New Project dialog), `VP6_SETTINGS_DIR`, a form's window sized to show the whole form (or filling the MDI area when it can't, without maximizing), code and other windows kept inside the MDI area (also when reopened), and windows opened before the IDE is shown fitted when it is., the Project panel sorted by name within each group (not the project's order), its Name button cycling through A to Z with groups first, A to Z with groups among the files, and the same Z to A (keeping the selection, new files in their place), remembered; a group's (Name) in the Properties panel (any name but a sibling's, refused with a message; renamed in the project file, kept selected; its own description; switching groups refreshes the panel); Project panel groups (default Forms and Modules; New Group, Rename, Delete keeping the contents, Move to, drag and drop onto a group, a file or the project, a module in a group of forms, duplicate names refused with a message, new files in the selected group, saved in the project file without moving files on disk); the project item not collapsible (no arrow, keys and double-click), its groups still are; the +/- button expanding and collapsing every group (collapsed groups staying collapsed when the panel is refilled, another project starting open); the Project panel's Files view (folders first, hidden files on request, never the project file, `.git` or `__pycache__`, forms and modules working as in the Project view, no groups, other files not opened, following changes on disk, +/- on folders, the selection kept when switching, remembered); the Files view's changes on disk (new folders and subfolders, new modules in the selected folder, Move to and drag and drop with open windows and group places following, renaming files and folders, a renamed form's imports updated, names refused for forms and modules, deleting a folder to the Trash with its modules leaving the project, the project file protected); new folders and subfolders from Project > Add Folder… (switching to the Files view), the New Folder button (in the selected folder or the selected file's) and a file's context menu; moving several items at once in both views (Move N Items to from the context menu of one of them, dropping the selection onto a group, folder or file, a group or folder moving with what is in it, the moved items staying selected, failures in one message while the others move); the IDE's icon and every new project's (all templates), the project's Icon in the Properties panel; About VP6 (the logo, in the Help menu and, on macOS, the application menu). |
| `test_theme.py` | Built-in theme contrast (WCAG ratios), editor and System-mode following, persistence and reset of customizations, Immediate recoloring, the Options dialog. |
| `test_ide_theme.py` | Dark icon variants, disabled icons, the whole IDE following the theme, System forms in a forced IDE, frame styles and metrics, the grid toggle. |
| `test_appearance.py` | Forced schemes styling forms and controls, System/Light switching, BackColor overrides, project defaults (runner and `.vp6p` lookup), dialogs matching forms, the project scheme field, designer schemes, the IDE scheme. |
| `test_docs.py` | The docs keep up with the code: every source file in the source reference, every test file in the test table, every public API name in `api.md` (key-code ranges count), the generated `api.md` tables up to date with a section per control, every property with a description, and every relative link and anchor in the Markdown files resolving. |
| `test_outline.py` | The Outline replacing the Properties panel (in the same place) while a code window is active and giving it back for designers, View > Outline Window and F4, a closed panel staying closed, closing the last window, the default layout; the outline of the Kitchen Sink's Form1; kinds, lines and skipped statements; syntax errors; sorting (order, name, type, both directions, members too); the panel's sort buttons, icons, tooltips, live updates and syntax-error handling; in the IDE: following the Project panel or active window, clicking items goes to the line (unfolding the designer region); the items at a line (a method inside its class, from the first decorator, blank lines and imports at none), and the Outline highlighting the item at the code window's cursor (in a body, none on an import, after re-sorting and edits, another code window's cursor, none for a designer). |
| `test_output.py` | Output capture: copy to the original descriptor, replay of output captured before attaching, split UTF-8 characters, restoring on `stop()`; real Python, C-level and Qt output in a separate process; the Output window's Select All / Copy / Clear menu; the real IDE `main()` showing its own output in the Output window. |
| `test_interrupt.py` | Ctrl+C (a real SIGINT) in VP6 programs run as separate processes: a project's forms close and `Form_Unload` runs; a form run on its own; `Form_Unload` cancelling the first Ctrl+C; an open `MsgBox` closed first; a console program at `input()` exiting quietly with code 130; programs that don't create the application (the IDE, the tests) keep their own Ctrl+C. |
| `test_kitchen_sink.py` | The Kitchen Sink covers every control type, default event, public API name, color scheme and use of control arrays; its regions are canonical; the project is created with all its forms; the designer opens every form; the explorer window (the docked panes, following the window, the Splitter, hiding the navigation pane), the introduction's links and the index (a section shows its first page), every page opening once and replacing the one before; each page's demo (text, buttons, lists, scroll bars, sliders, progress bars and spinners, the TabStrip page, pictures, z-order and lines, the TreeView, the Timer running only while visible, the layout, scrolling, popping out and back, dialogs with the modal form, color schemes with the View menu, keys, the mouse, control arrays, menus and bookmarks, globals); closing unloads the pages. |
| `test_project.py` | The project script: hash-bang, validity, executable bit, round trip, keeping user code, never executing on load, invalid files, running via hash-bang / python / without VP6, modules in subfolders importing each other by name; groups: the default Forms and Modules (also for older files without groups), nesting groups holding anything, the top level, rename, delete (contents move up), refused moves and names, new files placed by kind or chosen group, remove and rename of files, repairing an inconsistent tree, saving and loading; the icon (the VP6 icon copied into a project, your own copy kept, saved and loaded, one file as a string, none in older projects) and a program showing its project's icon, or the VP6 icon without one. |

## Samples: `samples/`

* `Calculator/`: `frmCalculator.py` (a fixed dialog with a display TextBox,
  digit and operator buttons whose Click handlers are attached in `Form_Load`
  like a control array, `KeyPreview` keyboard input, Default `=` and Cancel
  `C` buttons) and `Calculator.vp6p`.
* `GuessNumber/`: `modGame.py` (a console `Main()` using `input()`/`print()`)
  and `GuessNumber.vp6p` (`startup: "Sub Main"`, `type: "console"`).
