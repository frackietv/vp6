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
| `PropSpec(name, kind, default, choices, always, description, category)` | Frozen dataclass describing one designable property. |
| `P(...)` | Short constructor for `PropSpec`. |
| `category_of(spec)` | Its category in the Properties window's Categorized view: `spec.category`, else `PROPERTY_CATEGORIES` (VB's: Appearance, Behavior, Font, List, Position, Text, by property name), else Misc. |
| `enum_choices(*labels)` | `((0, "0 - None"), (1, "1 - Fixed Single"), ...)` for `enum` properties. |
| `normalize(kind, value)` | Coerces a value to its kind (`str`, `int`, `bool`, `color` via `colors.normalize`, `list` from a list or newline-separated string). A `file` value that is a Picture object (it has `_pixmap`) is kept as it is. |
| `PropertyHost` | Base class. `__init_subclass__` builds `cls._specs` (name → spec) and generates a Python `property` per spec (unless the class defines one). `_init_values(props)` applies defaults and values in spec order and rejects unknown names. `_set_prop` normalizes, stores in `self._values` and calls `_apply_<Name>`. |

Hooks a subclass may define per property: `_apply_<Name>(value)` pushes the
value to the widget; `_read_<Name>()` returns the live value.

### `vp6/app.py` (≈520 lines)

Application-level services.

* `ensure_app()` creates the `QApplication` on first use. Every entry point
  that needs Qt calls it. When it creates the application (a VP6 program), it
  also installs the Ctrl+C handler, gives it the VP6 icon and claims the
  program's instance lock (`App._claim_instance`, for PrevInstance).
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
* `SendKeys(Keys, Wait)`: `parse_keys` turns VB's syntax into (key,
  modifiers, text) strokes (`_char_stroke`, `_SPECIAL_KEYS`, `_KEY_TEXT`);
  `_send_stroke` sends a press and a release to the focus widget of the
  moment, after `_trigger_shortcut` (a key with Ctrl or Alt: a matching
  QAction or QShortcut in the window, since Qt handles shortcuts before key
  events; on macOS Alt also as Control+Option, the access keys). Strokes are
  sent one per event-loop turn (QTimer), or all at once with `Wait`.
* `DoEvents()`, `Beep()`, `End()`. `End` flushes stdout and stderr and calls
  `os._exit(0)`, like VB's `End`, without running `Form_Unload` handlers:
  it doesn't close the windows first, since closing them would run them.
* Singleton objects:
  * `App`: `Title` (`_title`, else `EXEName`), `Path` (folder of
    `__main__`), `EXEName`; `Major`, `Minor`, `Revision`, `ProductName`,
    `CompanyName` and `FileDescription`, which `_set_project(project)` (the
    runner) fills in; `PrevInstance` is `_claim_instance()`: a `QLockFile` in
    the temporary folder named by a hash of Path and EXEName, taken once
    (`ensure_app`, or the first PrevInstance), held while the program runs;
    True when another process holds it;
  * `Screen`: `MousePointer` (`QApplication.setOverrideCursor`, all
    overrides restored first), `MouseIcon`, `Width`, `Height`, `Fonts`
    (`_font_families()`: `QFontDatabase.families()` without private ones,
    sorted, as a `_Fonts` list, which can be called with an index too),
    `FixedFonts` (those `QFontDatabase.isFixedPitch`), `FontCount`, `ActiveForm`,
    `ActiveControl`
    (`control_of_widget` of the focus widget, `outer_control` for user
    controls);
  * `Clipboard`: `GetText` / `SetText` (with vpCFRTF: the `text/rtf` MIME
    data), `GetFormat` (text, an image, RTF, local files), `GetData` (the
    clipboard's image as a `picture.Picture`, or local files' paths),
    `SetData` (`picture.to_picture(...)`'s image), `Clear`; `_CF_*` are the
    format numbers;
  * `Debug`: `Debug.Print` prints to stdout, which the IDE shows in the
    Immediate window.
* `Command()` joins `sys.argv[1:]` (`shlex.join`; `list2cmdline` on
  Windows).
* **Settings:** `SaveSetting`, `GetSetting`, `GetAllSettings`, `DeleteSetting`
  use `_settings(AppName)`, a `QSettings` in the native format under the
  organization `SETTINGS_ORGANIZATION` ("VP6 Program Settings"), or, when
  `SETTINGS_DIR` is set (the tests' conftest does), `AppName.ini` in that
  folder. Sections are QSettings groups; values are stored as text.
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
  * `IDE_SCHEME_ENV = "VP6_IDE_SCHEME"`, `IDE_SCHEME_FILE_ENV =
    "VP6_IDE_SCHEME_FILE"`, `OS_POLL_MS`.
* **Resolution:**
  * `resolve(scheme)` turns IDE into its current meaning and anything that
    isn't Light/Dark into System;
  * `ide_scheme()` uses `ide_scheme_provider` (set by the IDE), else the
    file `VP6_IDE_SCHEME_FILE` names (`_ide_scheme_file_text`: run from the
    IDE, as it is now), else the `VP6_IDE_SCHEME` environment variable, else
    System; `write_ide_scheme_file(path, scheme)` is the IDE's side;
  * `project_scheme_for(directory)` uses `project_scheme` (set by the
    runner), else the first `*.vp6p` in the form's folder (cached), else
    System;
  * `scheme_from_name(name)` maps a project's `color_scheme` string.
* **OS appearance:**
  * `system_is_dark()` answers from Qt's color scheme normally, or from the
    OS (`_query_os_dark`) while the IDE forces the application's scheme;
  * `set_app_override()` and `app_override_active()` are the IDE's switch
    for that (it starts or stops the watcher's polling);
  * `watcher()`: the application's one `AppearanceWatcher` (a QObject child
    of the application, made by `_make_watcher`): `changed` when `check()`
    sees `system_is_dark()` flip (from Qt's `colorSchemeChanged`, or a
    `QTimer` every `OS_POLL_MS` while the scheme is forced, Qt being silent
    then; the OS query cache cleared first), or when the IDE's scheme file
    changes (a `QFileSystemWatcher`, watching again a replaced file); `dark`
    is the OS appearance it last saw.
* **Styling:**
  * `fusion_style()` returns the shared Fusion style, parented to the app.
    Don't keep what it returns: PySide invalidates the style's wrapper when a
    widget it was set on is destroyed (the C++ style lives on), so it
    remembers the style's C++ address (`_fusion_address`) and finds a fresh
    wrapper among the application's children. `Form._scheme_style` is a
    property that calls it (the form keeps only `_scheme_forced`);
  * `scheme_palette(dark)` builds a complete light or dark palette;
  * `style_tree(widget, style)` sets (or resets, for `None`) the style on a
    widget and all descendants;
  * `match_dialog(dialog, parent)` gives a message box the scheme of the form
    under it.

### `vp6/drawing.py` (≈470 lines)

VB's graphics methods, for `Form` (and so a user control's surface) and
`PictureBox`: the `Drawing` mixin and `DRAWING_PROPERTIES` (AutoRedraw,
DrawWidth, DrawStyle, FillStyle, FillColor), which both put in their
Properties.

* **What the class provides:** `_drawing_surface()` (the widget drawn on: a
  form's `_container_widget()`, the client area below an in-window menu bar;
  a PictureBox's label), `_drawing_origin()` (inside a PictureBox's border)
  and `_handles_paint()` (whether there is a Paint handler); its widgets'
  `paintEvent` calls `_paint_drawing(widget)` after drawing their background,
  picture and border (`_FormWidget`, `_FormClient`, `controls._PictureWidget`).
* **State** (`_draw_state()`, in the object's `__dict__`): the persistent
  image, the current point (`CurrentX`, `CurrentY`) and the painter of a Paint
  in progress. The helpers are all named `_draw_...`, since a Form has
  attributes of its own (e.g. `_fill`).
* **The persistent image** (`_draw_image()`): an ARGB `QImage` at the
  screen's device pixel ratio, at least the drawing area's size; it grows
  (keeping its contents) and never shrinks. `Cls` drops it.
* **`_draw_painter()`** is the painter a graphics method draws with: the
  Paint's when one is in progress (AutoRedraw False, inside the handler:
  straight to the screen), else one on the persistent image, after which the
  surface is updated.
* **`_paint_drawing(widget)`**: translates and clips to the drawing area,
  draws the persistent image, then with AutoRedraw False (not at design time,
  not nested) fires Paint with its painter set as the drawing state's.
* **Pens and fills:** `_draw_pen` (DrawWidth, DrawStyle at any width; flat
  caps, so a one-pixel line doesn't cover its end point, as in VB, round for
  wider solid lines; Transparent: no pen). `Line` keeps the dash pattern going
  across lines that join: the drawing state's `dash` is where the last line
  ended and how far its pattern had got (`setDashOffset`, in pen widths),
  reset by `Cls`; `_draw_inset` (Inside Solid), `_draw_fill`
  (FillStyle with FillColor, else ForeColor; hatches with `controls._hatch`).
* **Pictures:** `_background_picture()` (None; a form's Picture) is drawn
  first by `_paint_drawing`. `Image` renders the drawing area of the surface
  without its children into a new `picture.Picture`; `PaintPicture` draws a
  picture's image (a file through `picture_pixmap`, relative to the form's
  folder) scaled into a rectangle, or a part of it.
* **ScaleMode:** the drawing state stays in pixels; the public side converts.
  `_scale_factors()` is (ScaleLeft, ScaleTop, pixels per unit across, down):
  a User scale (`_user_scale`: left, top, width, height, from `Scale`, or
  `_set_scale_part` when ScaleLeft... is set) against `_draw_area_size()`,
  else `_UNITS` (VP6's pixel 1/96 inch; characters 8 x 16). `_to_px`,
  `_to_px_size`, `_from_px`, `_point` (Step: a size from the current
  point) are used by every method, CurrentX / CurrentY, Point, TextWidth /
  TextHeight (divided back) and PaintPicture's destination; Circle's radius
  is a size across. `_apply_ScaleMode` (User: the pixels it has, to begin);
  `ScaleX` / `ScaleY` (`_units_per_pixel`); `_mouse_xy` (from the drawing
  area's top left, in its units) for the form's mouse events and, through
  `Control._mouse_xy`, a PictureBox's.
* **The methods:** `PSet` (a pixel, or a round dot), `Line` (a line, a box
  covering both corners, "BF" filled), `Circle` (a `QPainterPath`: an
  ellipse, or an arc from `arcMoveTo`/`arcTo` with radius lines for negative
  ends, `math.copysign` so -0.0 counts; a closed one is filled), `Print`
  (`QFontMetricsF` of the surface's font; lines at ascent below the current
  point), `Cls`, `Point` (renders that one pixel of the surface without its
  children: `DrawWindowBackground`), `TextWidth`, `TextHeight`.

### `vp6/printer.py` (≈420 lines)

VB's `Printer` object and `Printers` collection.

* `_Printer(Drawing, PropertyHost)`, the one `Printer`: the drawing
  properties without AutoRedraw, ForeColor, the font's, Orientation,
  PaperSize, Copies, ColorMode, Duplex and OutputFile (`__setattr__`
  refuses others). `_drawing_surface()` is a `_PrinterSurface` (the
  printable area's size, the font with its size in VP6's pixels: points * 96
  / 72, a no-op `update`); `_draw_text_color` is black without a ForeColor.
* **The page:** `_page_size()` (PaperSize, else the printer's default paper,
  else Letter or A4 by the locale, `_default_paper`), `_layout()` (a
  `QPageLayout` with the printer's margins, probed with a `QPrinter`, or half
  an inch for a PDF); `Width`, `Height`, `ScaleWidth`, `ScaleHeight` from it in
  VP6's pixels (`_units`).
* **The document:** `_draw_painter()` is the document's painter: `_begin()`
  makes a high-resolution `QPrinter` for the printer (`_info()`, by
  DeviceName: `_device`, None for the default) or, when `_target()` names one
  (OutputFile, else a file in `REDIRECT_DIR`), a PDF file; sets its layout,
  copies, colors, duplex; begins a `QPainter` scaled from VP6's pixels to the
  printer's resolution (`_scale`), and connects `aboutToQuit` to
  `_end_at_exit`. `NewPage` applies the layout again, `newPage()`, rescales;
  `EndDoc` ends the painter; `KillDoc` aborts (and removes a PDF begun).
  `Page` counts pages.
* `Cls`, `Point` and `Image` raise AttributeError; `_adopt(qprinter)` takes a
  Print dialog's choices (CommonDialog.ShowPrinter with PrinterDefault).
* `Printers` (`_Printers`): `QPrinterInfo.availablePrinters()` as
  `PrinterInfo` objects (DeviceName, DriverName, Port, IsDefault), by index,
  `Count`, iteration. `PAPER_SIZES` maps VB's paper numbers to `QPageSize`.

### `vp6/picture.py` (≈210 lines)

VB's Picture objects.

* `Picture(Drawing, PropertyHost)`: a `QImage` (ARGB32 premultiplied, device
  pixel ratio 1) in `_image`. `Picture(Width, Height, BackColor)` makes one
  (filled, or transparent); `_image=` wraps an existing image (converted).
  Its properties are the drawing ones without AutoRedraw, ForeColor,
  BackColor and the font's; `__setattr__` refuses others. The graphics
  methods draw straight on its image: `_drawing_surface()` is a
  `_PictureSurface` (the size, a font from its values, the application's
  palette, a no-op `update`), `_draw_image()` its image (it never grows),
  and it has its own `Cls` (its BackColor), `Point` (-1 where transparent)
  and `Image` (a copy). `Width`, `Height`, `Type`; `_pixmap()` for controls.
* `LoadPicture(FileName)` (empty without one; FileNotFoundError /
  ValueError), `SavePicture(Picture, FileName)` (`QImage.save`, BMP without
  an extension; OSError).
* `to_picture(value)`: a Picture from a Picture, a QPixmap / QImage or a
  file. `picture_pixmap(owner, value)`: a picture property's value as a
  QPixmap (a Picture's, or a file relative to `owner._base_dir()`).
* `is_picture(value)`.

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

### `vp6/controls.py` (≈5280 lines)

The intrinsic controls.

* **Module data:**
  * `EVENT_ARGS` maps each event name to the parameter list VB passes. The
    code window uses it to generate handler stubs.
  * `MOUSE_EVENTS`, `KEY_EVENTS`, `FOCUS_EVENTS`.
  * **Validate:** `_add_validation` gives every control type with GotFocus
    the `CausesValidation` property and the `Validate` event. On FocusOut,
    `Control._validation_cancels` fires Validate when the new focus widget's
    control (`control_of_widget`) is another control of the same window
    with CausesValidation; True puts the focus back (a QTimer), with the
    focus events that causes skipped (`_VALIDATION["skip"]`, checked by
    `_skip_focus_event`) and the target's Click held back for a moment
    (`_VALIDATION["blocked"]`, checked in `_fire`).
  * **The mouse:** `_add_mouse_members` gives the visible control types
    (`_NO_MOUSE_MEMBERS` aside) MousePointer, MouseIcon, DragMode, DragIcon,
    OLEDropMode and the drag events. `pointer_cursor(value, icon)` makes the
    QCursor (`_CURSORS`; None for vpDefault; the icon a QPixmap, a Picture or
    a file); `_update_cursor` sets it on the
    control's widgets, remembering their own cursors (`_saved_cursors`) to
    give back for vpDefault. `Drag` runs a `QDrag` with `_VP6_DRAG_MIME`
    (its DragIcon or a faded grab of the widget), recording it in
    `_DRAGGING` (source, the QDrag, the target and position), and ends or
    cancels it with `QDrag.cancel`. Control widgets accept drops; their drag
    events go through `_on_qt_event` to `handle_drag_event(owner, event,
    pos)`, which fires DragOver (enter/over/leave) and DragDrop for a VP6
    drag, OLEDragOver and OLEDragDrop (a `DataObject`: text, files, an image
    as a Picture) for others when
    OLEDropMode is Manual, and `_accept_drag` (refused: accepted with
    IgnoreAction, so the container doesn't take it). DragMode Automatic
    starts a drag on the left button's press.
  * `CONTROL_TYPES`, at the end of the file: type name → class, in Toolbox
    order. The designer, form-file parser and Toolbox all use it. `Menu` is
    in it but has `InToolbox = False` (the Menu Editor designs menus).
  * `parse_outline(lines)` reads a TreeView outline into `(level, text, key,
    image)` (indentation for levels, a tab counting as 4 spaces,
    `Text|key|image`); `_image_ref` makes a designer image of digits an
    Index. `parse_panel`, `parse_tab` and `parse_list_image` read the other
    designer line formats.
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
  * `resolve_path(owner, path)` resolves paths relative to the form's folder;
    picture properties go through `picture.picture_pixmap(owner, value)`
    instead (a Picture object, or a file resolved the same way): PictureBox,
    Image, the buttons' pictures, ListImages (`ListImage` keeps a Picture
    as it is), `_picture_icon`, MouseIcon, DragIcon.
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
    Setting `Container` moves the control at run time: it checks the target
    (its form, or an `IsContainer` control on it, not itself or something on
    it), sets `Parent`, re-parents the widget into the new container's
    `_container_widget()` with the same geometry (shown again if it was),
    then `_restack`, the form's `_layout_aligned` (a docked control) and
    `_apply_tab_order`.
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
| `Label` | `QLabel` | Click synthesized from the mouse; `Caption` (multi-line) in plain text: `parse_mnemonic` finds the access key, shown underlined (the label switches to rich text, the text HTML-escaped in a `white-space: pre-wrap` span) with a `QShortcut` on the form widget (`_set_access_key`, `access_key_sequence`: `ACCESS_KEY_MODIFIERS`, Alt, or Control+Option on macOS; none while designing, replaced when the Caption changes) whose `_on_access_key` focuses the next control by `TabIndex` that is visible, enabled and takes Tab focus, going round; `UseMnemonic` False shows the `&` as it is; `AccessKey`; `TextFormat` (before Caption in `Properties`) picks plain, rich or Markdown (`_TEXT_FORMATS`) and makes links clickable at run time; `_on_link` fires `LinkClick(URL)`, or opens the URL (`QDesktopServices`) without a handler; AutoSize/WordWrap/BorderStyle. `BackStyle` (its own `_apply_colors`, also for BackColor and ForeColor): Opaque paints `BackColor` with a style sheet, or without one auto-fills the inherited palette (the container's color; not in a Frame, whose panel the platform draws), Transparent sets `background: transparent` and ignores BackColor. |
| `RichTextBox` | `_RichEdit` (a `QTextEdit` whose paste keeps formatting but not pictures or tables: `insertFromMimeData` loads the HTML into a `QTextDocument` and inserts its paragraphs' text runs with their character formats, dropping picture placeholders and trailing empty paragraphs) | `Text` is the plain text, `TextHTML`/`SelHTML` the HTML (`toHtml`, `QTextDocumentFragment`, `insertHtml`). The `Sel...` formats: `_formats()` gives the selection's character formats (one per character, read through a probe cursor; with no selection `currentCharFormat`), `_sel_value` reduces them to one value or None (mixed), `_font_of` resolves a format's font against the document's default; setting merges a `QTextCharFormat` with `mergeCurrentCharFormat` (the selection, else what is typed next). `SelColor` None is an empty `QBrush` (the palette's color). `SelAlignment` reads the selected blocks (`_blocks`). `SelChange` fires from `cursorPositionChanged`/`selectionChanged` when `(start, end)` changes. `MaxLength` trims the end of an insertion in `contentsChange` (`_limit_length`). `AppendText` inserts with its own format through a separate cursor at the end and keeps the view at the end if it was there. `Find` uses `QTextDocument.find` (flags from the `vpRtf...` options). |
| `CodeBox` | `_CodeEdit` (a `QPlainTextEdit` with a `_CodeGutter` widget in its left viewport margin) | `_CodeHighlighter` (a `QSyntaxHighlighter`) colors each block: Python (`_python`: regex rules, then strings and comments with the triple-quote state, colors from `_PY_COLORS` for a light or dark `_base_color`) and then the Highlight event (`_highlight`, which sets `_highlighting` so `HighlightText` can merge formats character by character); the block state is the event's State × 4 + the language's state. A Highlight fired before the control had its name schedules `_named` (also called by the form after `InitializeComponent`). `_paint_shading` paints the protected lines' tint and the current line's shade in `paintEvent` before the text, so the text's own backgrounds stay visible (extra selections would replace them). `_paint_gutter` draws numbers, `_markers` (`[QTextCursor, text]` pairs, so a marker moves with its line; `_LineMarkers` is the `LineMarker` view) and a + box before hidden blocks; `_gutter_width` makes room only for what is shown. `HideLines`/`ShowLines` set blocks' visibility and `markContentsDirty`, moving the caret out. `_protected` holds `(start, end)` cursor pairs (the end cursor keeps its position on insert, so Enter at the end adds a line outside); `_may_edit(key)` checks the selection (widened for Backspace and Delete) against them, from `_key_press`, `insertFromMimeData` (paste, drop), `inputMethodEvent` and the context menu (Cut, Paste, Delete disabled); `_reject_edit` fires ProtectedEdit or beeps. `_key_press` also does auto-indent (`_new_line`) and Tab/Shift+Tab (`_indent`). `_restyle` (palette, font or style changes) sets tab stops, the language's colors, the gutter. Sel… from `_EditorSelection`, shared with RichTextBox. |
| `FlexGrid` | `_GridTable` (a `QTableWidget` recording the cell under the mouse from its viewport and its headers' viewports in `_mouse_cell`) | The fixed row and column are the table's horizontal and vertical header items (`_frows`, `_fcols`, each 0 or 1; the corner's text is `_corner`), so they stay put while scrolling; `_item(row, col)` maps grid coordinates to a cell or heading item (made on demand with its column's alignment), `_fill_headers` gives every section an empty item (else Qt shows numbers) and every cell of a check column its item. Changing FixedRows or FixedCols moves the texts between the headings and the first row or column. `TextMatrix` is a `_TextMatrix` view; ColWidth, RowHeight, ColAlignment, RowData (in the row's heading item), ColEditor and ColList are `_GridIndexed` views. Editors: a cell's `_GRID_EDITOR_ROLE` else `_col_editors` (`_editor_of`); a check cell shows its value as the item's check state (`_show_value`). `_GridDelegate` makes the editors (`createEditor`: a QLineEdit, a QComboBox committing on `activated`, none for check, color (a `QColorDialog` from `_pick_color`) and button cells), toggles check cells and catches the `...` button in `editorEvent`, paints color swatches and buttons; every user change goes through `_commit` (ValidateEdit, then AfterEdit), BeforeEdit through `_fire_cancel`. `Sort` takes all items out (`takeItem`, `takeVerticalHeaderItem`), sorts them by the mode's key (`_as_number`) and puts them back. TopRow and LeftCol are the per-item scroll bars' values (`updateGeometries` first). |
| `TextBox` | `QLineEdit` or `QPlainTextEdit` | `MultiLine` picks the widget (rebuilt when changed); `SelStart`/`SelLength`/`SelText`; Change on every edit. The editing API comes from `_TextEditing`, which RichTextBox shares: `_editor()` is the multi-line editor (None for a `QLineEdit`, which has one line); lines are the document's blocks; `_caret_rect` maps `cursorRect` from the viewport to the control (a `QLineEdit`'s rectangle is narrowed to its center); `FirstVisibleLine` reads `firstVisibleBlock` (`QPlainTextEdit`, scrolled by lines of text: setting it adds up the earlier blocks' `lineCount`) or the block at the top margin (`QTextEdit`, scrolled by pixels); undo goes to the widget, `CanUndo`/`ClearUndo` to the document (a `QLineEdit` clears its history by setting its text again with signals blocked); `SelChange` fires when `_selection_range()` changes; `AcceptsTab` sets `tabChangesFocus`. |
| `CommandButton` | `QPushButton`, or a `QToolButton` when Graphical (`_Graphical`) | `Default`/`Cancel`; setting `Value = True` clicks it. |
| `CheckBox` | `QCheckBox`, or a checkable `QToolButton` when Graphical (a toggle button: `toggled` fires Click; Grayed shows not pressed) | `Value` 0/1/2 (tri-state for Grayed); Click fires on every change, including from code (VB behavior). |
| `OptionButton` | `QRadioButton`, or a checkable, auto-exclusive `QToolButton` when Graphical (exclusive with the container's other option buttons of either kind) | Buttons in the same container are mutually exclusive; Click when it becomes checked. |
| `Frame` | `QGroupBox` | Container; colors via palette. |
| `ListBox` | `QListWidget` | `_ListMixin` (`AddItem`, `RemoveItem`, `Clear`, `ListCount`, `List`); `ListIndex`, `Text`, `Selected(i)`, `Sorted`, `MultiSelect`. Per-item properties: see `_PerItem` below. `Style` 1 (Checkbox): checkable items (`_make_checkable`, also for new ones); `itemChanged` fires `ItemCheck` only when the check state differs from the one last seen (`_CHECKED_ROLE`: other changes of an item come there too) and not for code (`_quietly`); `Selected` (a `_PerItem`: the check state or the selection), `SelCount`, `TopIndex` (`indexAt` the top / `scrollToItem`). |
| `ComboBox` | `_ComboWidget` (a `QComboBox` whose `showPopup` emits `aboutToDropDown` first: `DropDown`), or `_SimpleCombo` for Style 1 (a `QLineEdit` above a `QListWidget`, with the part of `QComboBox`'s interface ComboBox uses) | `Style` 0 (editable) / 2 (list only); Click on selection change, Change on edit. Per-item properties as for ListBox. The Style is seeded in `__init__` to build the right widget; changing to or from Simple rebuilds it, keeping the List, Text and ListIndex, without Click or Change (`_restyling`). `_insert` adds items with the combo's signals blocked: no Click when an item moves the choice, and none chosen when the first ones are added (Qt would choose the first; VB's ListIndex stays -1, and an edit text stays). `TopIndex` scrolls `view()`. |
| `DriveListBox` | `QComboBox` (the label shown, the root path as item data) | `user_drives()` lists the drives with `QStorageInfo.mountedVolumes()`: every drive letter on Windows; elsewhere `/` and volumes under `/Volumes`, `/media`, `/mnt` and `/run/media`. `Drive` is the current item's root; setting it picks `_drive_index(path)`, the drive with the longest matching root. `currentIndexChanged` fires `Change` (not while it fills: `_quiet`). |
| `DirListBox` | `_DirTree` (a `QTreeWidget` that draws no branch arrows; header hidden, not expandable) | `_show(path)` puts the chain of ancestors (`_ancestors`, open-folder icons, each a child of the one before) and the subfolders (`_subfolders`, closed-folder icons) under it; each item keeps its full path (`UserRole`). `List` is a `_DirList` view: negative indexes are ancestors (`-1` = Path), others subfolders. Double-click sets `Path` (`Change` if it differs); `currentItemChanged` fires `Click` except while filling. `_is_hidden_entry` hides dot files and hidden ones unless `ShowHidden`. `_walk_tree` finds items by recursion (no `QTreeWidgetItemIterator`). |
| `FileListBox` | `QListWidget` (it subclasses `ListBox`) | `_fill` lists `Path`'s files matching `Pattern` (`file_matches`: `fnmatch` on lower-case names, `;`-separated, `*.*` matching everything) with signals blocked; `_apply_Pattern` fires `PatternChange` once the control is made (`_ready`, set after `__init__`); `Path` fires `PathChange`. `FileName` reads the current item and, set, changes Path, Pattern or the selection. `AddItem`, `RemoveItem` and `Clear` raise. |
| `Timer` | none at run time (`QTimer`) | Stopwatch icon in design mode (`_timer_design_widget`). |
| `HScrollBar`, `VScrollBar` | `QScrollBar` | `_ScrollBar` base; Change on value change, Scroll while dragging. |
| `DockPanel` | `_DockFrame` (a `QFrame` with a `_DockCaption` bar, the `content` widget its controls are on, and a `_DockSizer` on its inner edge) | Docked, it is laid out like an aligned PictureBox (`_Docked`; `_place_parts` puts the caption, content and sizer by its Align). `_float(rect)` moves the frame into a `_FloatWindow` (a frameless `Qt.Tool` window of the form's window, with a `QSizeGrip`) and sets `_floating`, which `Form._layout_aligned` skips; `_dock(align)` moves it back (remembering `_float_rect`). The caption bar handles its buttons (`button_rects`), double-clicks (`_toggle_floating`) and drags: `_drag_start` floats it under the mouse (grabbing the mouse), `_drag_move` moves the window and shows a `QRubberBand` where `_drop_edge` (within `_DOCK_ZONE` of an edge) would dock it, `_drag_end` docks it there after `_move_outermost` (first among the form's DockPanels). Close goes through `_ask_close` (the Close event can cancel); `_apply_Visible` shows or hides a floating window and fires DockChange when Visible changes. A `_DockWatcher` on the form's widget shows and hides the floating window with the form. Its Width, Height, Left and Top don't move a floating window (`FloatMove` does). |
| `PictureBox` | `_PictureWidget` (a `QLabel` whose `paintEvent` then draws the graphics methods' drawing) | Container; `Picture` is a file path relative to the form's folder; Stretch/AutoSize/BorderStyle. The graphics methods, Paint and the drawing properties are `drawing.Drawing`'s (inside its border: `_drawing_origin`, `ScaleWidth`, `ScaleHeight`); it has the Font properties (for Print). `Align` docks it (`Form._layout_aligned`); changing Align, its size, place or Visible calls `_relayout` (a docked pane's size is left to the layout). `Resize` event when its widget is resized. Always opaque (`autoFillBackground`), with the scheme's window color when BackColor is unset. `ScrollBars` (run time only): `_start_scrolling` puts the controls on a content widget in a `QScrollArea` over the picture (`_stop_scrolling` undoes it), `_container_widget()` is then the content, `_ScrollWatcher` keeps it as large as the visible controls need (`_update_scroll_size`, deferred once per round of changes; the full area when everything fits), `ScrollLeft` / `ScrollTop` (their setters update the size first) and the `Scroll` event; `_fill_widget` / `_fill_rect` make a form shown in it fill the visible area but keep its own size. |
| `Shape` | `_ShapeWidget` (transparent to the mouse, `NoFocus`) | No events. `paintEvent` builds a `QPainterPath` for its kind (a square, circle or rounded square centered and as wide as high, inset by half the border width so the border stays inside), fills it with BackColor when Opaque, then the FillStyle: solid, or `_hatch` (lines clipped to the path, `_HATCHES` directions `_HATCH_SPACING` apart: drawn rather than a brush pattern, which is faint on high-resolution screens), then the border with Line's `_PEN_STYLES`. Every property just repaints (`_repaint`). |
| `Line` | `_LineWidget` (transparent to the mouse, covering the line's box) | `X1`, `Y1`, `X2`, `Y2` instead of Left/Top/Width/Height (`_update_geometry` sizes the widget, with `_padding` for the width); `BorderColor` (unset: the palette's text color), `BorderStyle` (`_PEN_STYLES`; 0 = Transparent), `BorderWidth`, `Visible`, `Tag`, `ZIndex`; no events (`DefaultEvent` is empty); `_moved_points()` for the designer. |
| `Image` | `QLabel` | Not a container, `NoFocus`, no `TabIndex`, no colors (transparent). `Stretch` and `BorderStyle` come before `Picture` in `Properties`, because loading a picture sizes the control: without Stretch `_fit_to_picture` gives it the picture's size (plus the border). `Enabled` doesn't gray it: `_on_qt_event` drops events instead. |
| `TreeView` | `QTreeWidget` (header hidden, one column) | `Nodes` is a `_Nodes` collection (`_list` in the order added, `_by_key`; `_resolve` takes a key, an Index from 1 or a Node; `Add` places a `QTreeWidgetItem` by relationship, `Remove` with descendants, `Clear`). Each `Node` wraps its item (stored in the item's `Qt.UserRole` data; `UserRole + 1` holds its `Sorted`) with Text, Key, Tag, Index, FullPath, Expanded, Selected, Checked, Bold, ForeColor, Image, the relatives and `EnsureVisible`. `Items` (kind `outline`) rebuilds the tree from `parse_outline` (expanded in design mode). Events: NodeClick on `currentItemChanged`, or `itemClicked` on the node that was current at the press (`_current_at_press`); Expand/Collapse; NodeCheck when the check state changes (`Node._check_state`). Code changes run under `_quietly()` (`_Quiet`), so only the user's actions fire events. `SelectedItem`, `HitTest`, `LineStyle`, `Indentation`, `Checkboxes`, `Sorted` (`_keep_sorted`), `PathSeparator`. |
| `Splitter` | `_SplitterBar` (paints the bar and a grip, handles the mouse) | Docks by `Align` (Left by default) like an aligned PictureBox; `_pane()` is the nearest earlier visible control docked to the same edge; dragging calls `_resize_pane`, which clamps the pane between `MinSize` and what leaves `MinSize` of the form's `_free_area`, and `Moved` fires on release. `_vertical()`: Left/Right. Thickness changes relayout. |
| `ProgressBar` | `QProgressBar` (no text, `NoFocus`) | `Min`/`Max`/`Value`; `_apply_Value` keeps Value inside Min..Max (`_clamp`), and changing Min or Max re-applies it; `Orientation` (`_ORIENTATION`, `_QT_ORIENTATION`, shared with Slider and UpDown). Click synthesized from the mouse; no focus or key events. |
| `Slider` | `QSlider` | `valueChanged` fires `Scroll` while the thumb is down (`isSliderDown`, remembering `_changed_while_dragging`) and `Change` otherwise; `sliderReleased` then fires the one `Change` of a drag. `SmallChange`/`LargeChange` are the single and page steps; `TickStyle` maps through `_TICKS` to the tick position, `TickFrequency` to the tick interval. |
| `UpDown` | `_UpDownWidget` (two auto-repeating, `NoFocus` `QToolButton`s in a `QBoxLayout`; `set_vertical` swaps up/down for right/left arrows) | `_step(±1)` (not while designing): `_value_from_buddy` first (a number typed into the buddy, clamped, becomes the Value without a Change), then `Value ± Increment`, wrapping with `Wrap`, then `_sync_to_buddy` and UpClick/DownClick. `_apply_Value` clamps and fires `Change` when the value really changed (`_shown_value`), syncing the buddy. `Buddy` looks `BuddyControl` up on the form by name when needed (it may be created after the UpDown); `_buddy_property` is `BuddyProperty`, else the buddy's `Text` or `Caption`. |
| `WebView` | `_new_web_view`: Qt WebView's `QWebView` (a native `QWindow`, imported only here; a clear error before PySide6 6.11) in `QWidget.createWindowContainer`; in the designer a placeholder label (`_web_design_widget`) | `_allow_local_files` turns on its file access settings. `_url` makes a QUrl of a web address, an existing file (relative to the form's folder) or a domain (`fromUserInput`, http made https). `loadingChanged` gives DocumentComplete (Succeeded) and NavigateError (Failed, its error string); `titleChanged` TitleChange; `loadProgressChanged` ProgressChange. URL applied at run time navigates; reading it is LocationURL. Not given the mouse members (`_NO_MOUSE_MEMBERS`): the system has its mouse. `app.ensure_app` sets `AA_ShareOpenGLContexts` before the application exists, which Qt's web views need. |
| `WebBrowser` | a `QWebEngineView` (`_new_web_engine_view`; Qt WebEngine imported only there) with its own `QWebEnginePage` subclass; in the designer a placeholder | A subclass of `WebView`: `_EngineView` gives the QWebEngineView the method names WebView uses (the history's canGoBack, `setHtml`, the page's `runJavaScript`, the progress it last reported). The page's `acceptNavigationRequest` fires BeforeNavigate (not for its own HTML: data and about URLs), its `createWindow` returns a page waiting for its URL, then fires NewWindow and opens it here unless cancelled. The page's `loadingChanged` (WebEngine's LoadSucceededStatus...) goes to WebView's `_on_loading`; `linkHovered` is StatusTextChange. `_watch_focus_proxy` puts the event filter on the widget Chromium takes the focus in (after each load, a new child widget, SetFocus), for GotFocus and LostFocus. Its local file settings allow file pages to use files and the web. |
| `CommonDialog` | none at run time (a small-dialog icon while designing, `_commondialog_design_widget`) | Its `Show...` methods make the Qt dialog each time: `_file_dialog(save)` (a `QFileDialog`: `parse_filter` turns VB's Filter into name filters, InitDir or FileName's folder, `DefaultExt` as the default suffix, multi-select and overwrite prompt from Flags; FileName, FileNames and FilterIndex from the result), `QColorDialog`, `QFontDialog` (the current color and font when accepted), `QPrintDialog` on a `QPrinter` (starting with the Printer's printer; copies, orientation, page range from Min/Max/FromPage/ToPage; with PrinterDefault its choices go to `printer.Printer._adopt`), and `QDesktopServices.openUrl` for ShowHelp. `_cancelled` raises `DialogCancelled` with CancelError, else gives False. Its Font... properties don't touch a widget (`_apply_font` does nothing). |
| `ImageList` | none at run time (a stack-of-pictures icon while designing, `_imagelist_design_widget`) | `ListImages` is a `_ListImages` collection of `ListImage` objects (`Picture` a file path, resolved like a PictureBox's; `_pixmap()` scaled to `_size()`: ImageWidth × ImageHeight, or the first picture's size while 0); the designer's `ListImages` (kind `images`) is `path\|key` lines (`parse_list_image`). Any change `_notify`s the controls whose `ImageList` is its name (`_refresh_images`). |
| `Toolbar` | `QToolBar` (not movable or floatable), a `QAction` per shown button (`addSeparator` for separators; `NoFocus` tool buttons) | Docked like an aligned PictureBox (`_Docked`, Align None/Top/Bottom/Left/Right, Top by default; Left and Right make it vertical) and shows ImageList pictures (`_UsesImageList`). `Buttons` is a `_Buttons` collection of `Button` objects; the designer's `Buttons` (kind `buttons`) is lines parsed by `parse_button` (`Caption\|Key\|Image\|ToolTipText\|options`, `-` a separator). Any change calls `_update_buttons`, which rebuilds the actions: check and group buttons are checkable, each run of adjacent ButtonGroup buttons shares a `QActionGroup` (`ExclusiveOptional`, so code can leave none pressed; `_on_triggered` re-presses a clicked pressed one, as in VB); the icon size is the ImageList's; `TextAlignment` picks the tool button style; then `_fit` makes it as tall (or wide) as its `sizeHint`. `_on_triggered` updates `Value`s (`_group_of`) and fires `ButtonClick`. A Button's `Left`… come from `widgetForAction` (after activating the layout). |
| `ListView` | a `QWidget` with a `QStackedLayout`: a `QListView` (Icon, SmallIcon and List views: `_QT_VIEWS` modes and flows) and a `QTreeView` (Report), sharing one `QStandardItemModel` (`_model`: a row per item, column 0 the Text, then the SubItems) and one selection model | `ListItems` is a `_ListItems` collection kept by the model itself (Index = row + 1, so sorting re-numbers, as in VB; `_by_key`); each `ListItem` is stored in its first cell (`UserRole`); `SubItems` is a `_SubItems` view (call or `[]` to read, `[n] =` to set, creating cells with their column's alignment). `ColumnHeaders` is a `_ColumnHeaders` keyed collection of `ColumnHeader` objects; `_update_columns` sets the header labels, widths and alignments and hides any extra model columns. The designer's `ColumnHeaders` and `ListItems` (kinds `columns` and `listitems`) are lines parsed by `parse_column` and `parse_list_item`. Two ImageLists (`_IMAGE_LIST_PROPS = ("Icons", "SmallIcons")`): `_show_icon` puts the Icon in the Icon view, the SmallIcon in the others. `_keep_sorted` sorts the model by `SortKey` when `Sorted`. `clicked` fires `ItemClick`, the header's `sectionClicked` `ColumnClick`, `itemChanged` of a check state `ItemCheck` (not for code: `_quietly`). |
| `StatusBar` | `QFrame` with a `QHBoxLayout`: a `QLabel` per shown panel (sunken, transparent to the mouse), and `_simple_label` for Style = Simple | Docked like an aligned PictureBox (`_Docked`; Align None/Top/Bottom, Bottom by default). `Panels` is a `_Panels` collection of `Panel` objects (`_list`, `_by_key`; `_resolve` takes an Index from 1, a key or a Panel; `Add`, `Remove`, `Clear`); the designer's `Panels` property (kind `panels`, read from `_values` by the Properties window) is lines parsed by `parse_panel` (`Text\|Key\|options`) and rebuilds the collection. Any change calls `_update_panels`, which rebuilds the layout: Spring panels get stretch, Contents ones their text's width (at least Width), others a fixed Width; a stretch keeps the panels left when none springs. `Panel._shown_text` is the Text, the time or date (`QLocale` short format) or CAPS/NUM/INS/SCRL; a 250 ms `_timer` (not while designing) refreshes those, dimming a lock key that is off (`_lock_key_on`: `GetKeyState` on Windows, `CGEventSourceFlagsState` for Caps Lock on macOS, off elsewhere). The bar gets the mouse and finds the panel by position (`_panel_at`) for `PanelClick` / `PanelDblClick`. |
| `TabStrip` | `_TabWidget` (a `QTabWidget` with an empty page per tab; `contents_rect()` asks the style for the pages' area, as Qt's layout does, which works before the widget is shown) | Not a container. `Tabs` is a `_Tabs` collection of `Tab` objects; the designer's `Tabs` property (kind `tabs`, read from `_values` by the Properties window) is lines parsed by `parse_tab` (`Caption\|Key\|ToolTipText`). Any change calls `_update_tabs`, which adds or removes pages and sets texts and tooltips without firing Click (`_quiet`), keeping the selected Tab (`_current_tab`). `currentChanged` fires `Click`; `BeforeClick` comes from a mouse press on another tab in the tab bar (an event target), and True swallows the press. `ClientLeft`… are `contents_rect()` moved by the widget's position; `Placement` maps to `setTabPosition`. |
| `Menu` | a `QAction` (none in design mode) | Parent: the form (the menu bar, `Form._add_menu_item`) or a `Menu`, whose `QMenu` (`_submenu`, created for its first item by `_add_menu_item`) holds it. Caption `-` is a separator; `Checked` (Qt's own toggling is undone in `_on_triggered`), `Enabled`, `Visible`, `NegotiatePosition` (rebuilds the window's bar when merged), `Shortcut` (also added to the form widget so it works in the window). Click on `triggered`, and for a menu with items on `aboutToShow`. `_menu_container`, `_place_after` (loaded array elements follow the last one), `_dispose`. |

`_UsesImageList` is the mixin of the controls showing an ImageList's
pictures (TreeView, TabStrip, Toolbar, ListView): `_image_list(prop)` finds the
ImageList named by their `ImageList` (or another of `_IMAGE_LIST_PROPS`, a
ListView's `Icons` and `SmallIcons`) among the form's controls (by name, so it works in the
designer too), and `_refresh_images()` shows every item's Image again.
`_picture_icon(control, ref, strict)` turns an Image into an icon: a Key or
Index in the ImageList, or without one a picture file; `strict` (code
setting an Image) raises for an unknown Key or Index. `Form.__init__` calls
every control's `_refresh_images` after `InitializeComponent`, since an
ImageList may be created after the controls using it, and its `_named` (the
controls have their names then: a CodeBox colors its lines again for its
Highlight event, which it couldn't find while it was being made).

`_KeyedItem` and `_KeyedCollection` are shared by `ListImage`/`_ListImages`,
`Button`/`_Buttons`, `ColumnHeader`/`_ColumnHeaders`, `Panel`/`_Panels` and
`Tab`/`_Tabs`: an item's `Index` (from 1) and unique `Key`; the collection's
`Count`, `Item`/call (an Index, a Key or an item: `_resolve`), iteration,
`Remove` and `Clear`, and `_insert`/`_reset` for the control; each change
calls the control's update (`changed`).

`_ListMixin.AddItem` sets `NewIndex`: in a Sorted list the new item is
marked (`_NEW_ITEM_ROLE`, before inserting it into a ListBox, which sorts at
once), the list sorted (`_sort`), and the mark found and removed;
`RemoveItem` and `Clear` make it -1.

`_PerItem` is a ListBox's or ComboBox's per-item property (`_ListMixin`'s
`ItemData`, `ItemImage`, `ItemBold`, `ItemItalic`, `ItemForeColor`): call or
`[]` to read, `[i] =` to set, with the index checked against `ListCount`.
The values are Qt item data roles (`_ITEM_DATA_ROLE`, `_ITEM_IMAGE_ROLE`
for the Image's Key, `DecorationRole` for its icon, `FontRole`,
`ForegroundRole`), so they move with their items; each widget provides
`_role(index, role)` and `_set_role(index, role, value)` (a
`QListWidgetItem`'s data, a `QComboBox`'s item data). Pictures come from
the control's `ImageList` like a TreeView's (`_refresh_images`, which the
ImageList calls through `_IMAGE_LIST_PROPS`).

`_Graphical` is the mixin of CommandButton, CheckBox and OptionButton for
`Style = Graphical` (`_graphical_props`: Style, Picture, DownPicture,
DisabledPicture). Their `__init__` seeds `_values` with the Style so the
right widget is built up front (`_graphical_widget`: a `QToolButton`); a
later change rebuilds it (`_rebuild_widget`, after `_before_rebuild` keeps
a CheckBox's or OptionButton's checked state, with no Click: `_restyling`).
`_update_picture` (on pressed, released, toggled, Enabled and the picture
properties) shows Picture, DownPicture while down or checked, or
DisabledPicture while disabled, above the Caption (`ToolButtonTextUnderIcon`;
text or picture only when the other is missing); `_qss_type` follows the
widget; `_apply_font` gives a tool button an ordinary button's font size
unless FontSize is set.

`_Docked` is the mixin of the controls with an `Align` property (PictureBox,
Splitter, StatusBar, Toolbar): while docked, changing their Align, size, place or
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

### `vp6/process.py` (≈230 lines)

Running other programs.

* `Process(Control)`: invisible at run time (`_process_design_widget`, a
  console icon, in the designer; Width and Height fixed at 32), registered
  in `CONTROL_TYPES` here (before Menu, which stays last), its events'
  arguments added to `EVENT_ARGS`. `Start` makes a `QProcess` child of the
  form's widget (`split_command`: `QProcess.splitCommand` for a string, a
  list as it is; WorkingDirectory through `resolve_path`), connects its
  signals to `_read` (an incremental UTF-8 decoder for each stream: Output
  / ErrorOutput), `_finished` (the rest of the output, `_exit_code`: the
  code, or -1 for a crash or kill; Exited) and `_error` (FailedToStart
  only: Error); each handler ignores a QProcess that isn't the current one.
  `Write`, `WriteLine`, `CloseInput`, `Terminate`, `Kill`, `WaitForExit`;
  `Running`, `ExitCode`, `ProcessID`. `_form_unloaded` (called by
  `Form._finish_unload`) kills it.
* `Shell(PathName, WindowStyle)`: `QProcess.startDetached`; its process ID,
  or FileNotFoundError.

### `vp6/terminal.py` (≈1720 lines)

The Terminal control.

* `TERMINAL_TYPES` (TerminalType's order: xterm-256color, xterm, vt100,
  vt102, vt220, ansi), `TERM` (the default), `_XTERMS`, `_EIGHT_BIT`,
  `_DEVICE_ATTRIBUTES`, `DEC_GRAPHICS` and `_CHARSETS`, `color_rgb(index)`
  (the 256 colors), `_xcolor`; true color: `COLORTERM` (`truecolor`, the
  xterm types' environment) and `_TRUE_COLOR_CAPABILITIES` (XTGETTCAP's
  `RGB`, `Tc` (a flag: `None`), `setrgbf`, `setrgbb`).
* `AnsiScreen(rows, cols, scrollback, term)`: the terminal in plain Python.
  `lines` (rows of `(char, Attr)` cells), `history` (scrolled off the top
  of the main screen, at most `scrollback`), `row`, `col`, `attr`,
  `top`/`bottom` (the scroll region), `wrap_pending` (a character in the last
  column wraps with the next one; an SGR keeps it), `modes` (private modes
  on: 1 cursor keys, 5 reverse video, 6 origin, 7 autowrap, 25 the cursor,
  mouse 9/1000/1002/1003 one at a time, 1004, 1006, 2004...), `ansi_modes`
  (4 insert, 20 new line), `keypad_app`, `charsets` (G0-G3) and `gl`,
  `tabs`, `cursor_style`, `title`, `replies` (answers for the program: the
  Terminal sends them), `colors` (a callable: the default colors, for OSC
  10 / 11). Properties `cursor_visible`, `cursor_shape`, `mouse_mode`.
  `_reset()` is the power-on state (ESC c; the history stays). `feed(text)`
  is a state machine (text, ESC, ESC with an intermediate, CSI, and strings
  up to ST: OSC, DCS, APC (`graphics.kitty`, xterms only), SOS/PM
  ignored; CAN / SUB cancel, ESC starts over; a string's text is collected
  in `_parts`, in bulk up to `_STRING_STOP`, since pictures are long): `_text_char` (CR, LF (and CR in new line mode), BS, TAB, SO / SI,
  C1 controls as ESC sequences for `_EIGHT_BIT` types, printable `_put`:
  the character set, insert mode, autowrap, `_last` for REP), `_escape`
  (7 / 8 with `_cursor_state` / `_restore_cursor`, D, E, M, H, = / >,
  N / O, n / o, c), `_escape_final` (character sets; `#8`: all E's),
  `_csi` (the prefix `?` `>` `<` `=` and intermediates split off: `!p`
  `_soft_reset`, ` q` the cursor's style, `$p` `_report_mode`; `>c`, `>q`;
  `?h`/`?l` `_set_modes` (47/1047/1049 `_alternate_screen`, 1048, 6 homes,
  3 clears), `?s`/`?r`, `?6n`, `?S` (`_graphics_attribute`: XTSMGRAPHICS); A-G, a, e, `` ` ``, d, H/f (`_goto`: origin
  mode), J, K, L, M, P, @, X, b, S, T, I, Z, g, r, s, u, m, h/l, c, n, x,
  t (18, 22, 23)), `_sgr` (attributes in `_SGR_FLAGS`, the colors,
  `_extended_color` for 38/48 with semicolons or colons, `4:n`), `_osc`
  (0 and 2: the title; 10 / 11 / 4 questions; 1337: `graphics.iterm2`, xterms only), `_dcs` (sixel strings,
  `_SIXEL_START`: `graphics.sixel`; xterm's DECRQSS
  with `_sgr_text`, XTGETTCAP: TN, Co and the true color capabilities). `resize` keeps the cursor's line on the
  screen (lines above go to the history, and come back), the main screen
  behind the alternate one and the tab stops follow. Pictures: `graphics`
  (a `TerminalGraphics`; the alternate screen has its own, the main one's in
  `_main_graphics`; `sixel_colors`: the sixel registers shared while mode 1070
  is reset), `scrolled` (lines gone into the history ever: the
  placements' lines count from the first), `cell_pixels` (a cell in device
  pixels, set by the Terminal, with `pixel_ratio`; `CSI 14 t` / `16 t`
  answer with it);
  `_scroll_up`, `_scroll_down`, `L` / `M`, `_erase_display` (2, 3), `resize`
  and `_reset` keep them in step. `text()`,
  `all_lines()`, `line_text`. `Attr` (frozen: fg, bg, bold, dim, italic,
  underline, blink, inverse, invisible, strike), `PLAIN`.
* **The program:** `_PtyProgram` (`pty.openpty`, `subprocess.Popen` on the
  slave with `start_new_session` and `TIOCSCTTY` so it is the controlling
  terminal, `TIOCSWINSZ` for its size, a `QSocketNotifier` on the master
  reading output; EOF / EIO: `_finish` waits for the exit code) and
  `_PipeProgram` (Windows: a `QProcess`, merged channels); both get the
  TERM to set (and `COLORTERM` for the xterm types; the outer terminal's is
  dropped) and the size in pixels (`pixels`, and `resize(rows, cols,
  width, height)`: `TIOCSWINSZ`'s pixel fields). `default_shell()`.
* **Keys:** `key_text(key, modifiers, text, screen=None)`: as the screen's
  terminal type and modes (`_CURSOR_KEYS` with CSI or SS3, `_EDITING_KEYS`,
  `_PF_KEYS`, `_FUNCTION_KEYS`, `_VT100_KEYS`, `_KEYPAD_KEYS` in keypad
  application mode, xterm's modifier number, a vt220's Home / End, an
  xterm's F13-F20 as Shift+F1-F8, Enter as CR LF in new line mode, `_KEYS`;
  the Control key, `_CONTROL`, is Meta on macOS, makes ^A-^Z and the like;
  Alt+key: ESC and the key except on macOS); `_copy_or_paste(event)`.
  `_BOX_LINES`: the box drawing characters the view draws as lines;
  `_BOX_PART` (a regex: one of them, or text without them, trimmed of
  spaces), `_text_parts(text, ligatures)` (a run's text in the parts drawn
  at once, with their columns: with ligatures, the text between box lines
  whole; without, a character a part), `_fits_cells(font, text, width)`
  (the font's advance for the text is its cells' width: no wider glyphs
  from a fallback font).
* **`_TerminalView(QWidget)`**: paints the history and screen from the
  scroll bar's value (runs of one `Attr`, split at the cursor's cell when
  `Ligatures` is on; each run's `_text_parts` drawn whole when they
  `_fits_cells` (the font's ligatures), else cell by cell on a fixed grid, a font per bold / italic, bold dark colors brightened, dim, inverse,
  invisible, underline, strikethrough, `_draw_box` for box lines, reverse
  video, selection, `_color` for 16 / 256 / RGB colors, the cursor: a block
  (an outline without the focus), an underline or a bar); the runs are
  collected first so `_pictures` (the placements showing, where, scaled
  from the screen's `cell_pixels` to the font's cells) are drawn by
  `_draw_pictures` in three layers: z below `UNDER_BACKGROUNDS`, then the
  cells' backgrounds, z below 0, the text, the rest;
  `grid_size()` from the font's cell size; resizing resizes the screen and
  the program; keys (`ShortcutOverride` accepted for what the program gets,
  so the menus don't take them; `focusNextPrevChild` keeps Tab), input
  method text, mouse selection (a word on a double-click), the wheel;
  `_report_mouse` sends presses, releases, moves and the wheel to the
  program in its mouse mode (SGR or X10 bytes; not with Shift);
  focusIn/Out reported in mode 1004.
* **`Terminal(Control)`** (registered in `CONTROL_TYPES` before Menu):
  `_on_key_press` returns False (the form doesn't see its keys: no
  Default / Cancel buttons); `Start` (`process.split_command`, else
  `default_shell()`; a pty, or pipes on Windows, with the screen's TERM),
  `_on_data` (an incremental UTF-8 decoder, `feed`, the screen's replies
  sent back, a 15 ms `_refresh` timer, TitleChange), `_on_exit` (Exited),
  `_resize_screen` (also the screen's `cell_pixels` from the font and the
  device pixel ratio; `_pixels()` for the program), `_send` /
  `_send_bytes`, `Write`, `Kill`, `Clear` (the pictures too),
  `Copy`, `Paste` (bracketed in mode 2004); `TerminalType`
  (`_apply_TerminalType` sets the screen's `term`), `TermName`,
  `_default_rgb` (the screen's `colors`);
  `_shown` starts it (AutoStart) the first time it shows; `_form_unloaded`
  kills it. In the designer, `_terminal_design_widget` (a dark box, `$ _`).

### `vp6/termgraphics.py` (≈690 lines)

Pictures in the Terminal: the Kitty graphics protocol, iTerm2's inline
images and sixel graphics, for `AnsiScreen`.

* `TerminalGraphics(screen)`: `images` (id: `TerminalImage(id, number, image,
  order, anonymous)`, the QImage premultiplied; anonymous: iTerm2's, dropped
  by `_drop_unplaced` once no longer placed) and `placements` (`Placement`: the
  image, its placement id, `line` (counted from the screen's first,
  `screen.scrolled` of them in the history), `col`, the `cols` x `rows`
  cells it covers, `source` (a QRect of the image), `width` x `height` in
  device pixels, `offset` into the first cell, `z`).
* `kitty(text)` (an APC string's text: `G`, keys, `;`, base64): chunks
  (`m=1`) collect in `_loading` with the first chunk's keys; `_run` by the
  action: transmit (`t`, `T`, `q` only checks): `_image_from` (base64,
  `t=d`, `t=f` / `t=t` with `_read_file` (`S`, `O`; a temporary file with
  `tty-graphics-protocol` in its name in the temp folder is deleted),
  `o=z`, `f=100` PNG, 24 / 32 with `s` x `v`, `MAX_SIDE`), `_store` (the
  same id replaces a picture; else `_new_id` from 2³¹; `_keep` stores it,
  and `_within_quota` drops the oldest, hidden ones first, beyond `QUOTA`); place (`p`):
  `_find` (by `i`, or `I`: the newest with that number), `_place` (`x`,
  `y`, `w`, `h`, `X`, `Y`, `c`, `r` (one: the shape kept), `z`, `p`
  replacing the same placement, `U=1` not drawn; `_put` places it at the
  cursor and moves the cursor unless `C=1`); delete (`d`): `_delete` (`a`, `i`, `n`, `c`, `p`, `q`, `x`, `y`,
  `z`, `r`; capitals free pictures, `_remove`); animation: an error.
  `GraphicsError` messages go back by `_answer` (only with `i` or `I`;
  `q=1` no OK, `q=2` nothing) through the screen's `_reply`.
* `iterm2(text)` (an OSC 1337 string's text after `1337;`): `File=args:data`
  (`_iterm2_file`: `inline=1` only, any picture Qt reads, `_iterm2_size`
  from `width` / `height` in cells, `px`, `%` or `auto` (no wider than the
  screen) and `preserveAspectRatio`, `_put` unless `doNotMoveCursor=1`),
  `MultipartFile` / `FilePart` / `FileEnd` (`_multipart`),
  `ReportCellSize` (points: `cell_pixels` / `pixel_ratio`). No answers,
  no errors.
* `sixel(params, data)` (a sixel DCS string: what comes before `q`, and
  after): `_sixel_image` decodes it with `_SIXEL_TOKENS` (runs of sixels,
  `#` colors, `!` repeats, `"` raster attributes, `$`, `-`) into one
  `array('I')` of ARGB values per pixel row (`make_room` grows them,
  `_SIXEL_BITS` gives each sixel's bits), the pixels' shape from P1
  (`_SIXEL_ASPECT`) or the raster attributes (rows repeated at the end),
  `SIXEL_REGISTERS` registers from `_VT340_COLORS` (`_sixel_rgb`; HLS through
  QColor; the screen's `sixel_colors` when shared, mode 1070 reset), the
  terminal's foreground before a color is picked, P2=1 clear (else the
  background), `MAX_SIDE`; an anonymous `TerminalImage`, `_put` at the
  cursor, the cursor then below it at its column (mode 8452: `_put`'s own
  move; mode 80: at the screen's top left, cut to it, the cursor stays).
* Following the screen: `screen_row(placement)`, `scrolled(top, bottom,
  step, into_history)` (a region's lines moving; out of it: gone),
  `clear(history)` (ED 2 / 3), `prune()` (lines gone from the history or
  below the screen; and `_drop_unplaced`), `reset()`.

### `vp6/mdi.py` (≈280 lines)

MDI forms.

* `MDIForm(Form)` (`_vp_base`: only its subclasses have default instances):
  Form's properties but `_NOT_ON_MDI` (given fixed class values instead:
  BorderStyle 2...), plus AutoShowChildren and ScrollBars; `_fire` tries
  `MDIForm_<event>` first, then `Form_<event>`.
* **The workspace:** `_workspace()` makes the `QMdiArea` in the container
  widget on first use; `_layout_aligned` (after Form's) puts it in
  `_free_area`, what the aligned controls leave. `_apply_workspace_look`:
  the Picture (a tiled brush), else BackColor, else the palette's Dark;
  `_apply_window_flags` / `_apply_fixed_size`: always a sizable window.
* **Children:** `_show_child(child)` wraps the child's widget in a
  `QMdiSubWindow` (its Icon, else the program's), sized to keep the child's
  Width and Height inside, at Left/Top when StartUpPosition is Manual, in
  its WindowState; `_remove_child` takes it out again (the widget back to a
  parentless window, the subwindow deleted). `_on_child_activated`
  (`subWindowActivated`; None from a deactivated window keeps the active
  child) fires Deactivate and Activate and updates the menu bar;
  `ActiveForm`, `_activate_child`, `Arrange` (Qt's cascade; tiling rows or
  columns by hand; minimized ones along the bottom).
* `_update_menu_bar`: the active child's top menus replace its own on its
  bar, or its own again.
* `_query_unload`: its QueryUnload, then each child's `_query_unload`
  (`VP_FORM_MDI_FORM`; one refusing cancels), then `_finish_unload`.
* `mdi_form_for(child)`: the loaded MDIForm, else the last subclass of
  `MDIForm` (`_subclasses`; not the designer's) by its default instance,
  shown; a RuntimeError without one. `show_child`, `after_unload` (a
  QTimer: the subwindow goes once its close is over), `window_list_actions`
  (for Menu.WindowList).

### `vp6/form.py` (≈520 lines)

* `_FormsCollection` / `Forms` is the loaded forms (`Count`, iteration,
  indexing).
* `_FormWidget(QWidget)` is the form's window. It overrides Qt event handlers
  to fire the form events:
  * close → unload query, hide → end of a modal loop, Resize, Activate /
    Deactivate (not an MDI child's: its MDI form's workspace tells those);
  * mouse → Click, DblClick and the MouseDown/Move/Up events;
  * keys → KeyDown, KeyPress and KeyUp, plus the Default/Cancel buttons;
  * paint → the graphics methods' drawing and Paint (`drawing.Drawing`, a base
    class of Form; `_FormClient` too when the controls are on it).
  * the appearance watcher's `changed` → `Form._appearance_changed` (a slot
    of the widget: disconnected when it goes): the scheme applied again when
    forced (an IDE scheme may now mean another), then `_dark_changed`, which
    fires `ColorSchemeChanged(Dark)` when `_is_dark()` differs from
    `_was_dark` (not while loading) and tells the forms shown in it.
    `DarkMode` is `_is_dark()`: a System form shown in another (`ShowIn`)
    looks like its window (`_menu_window()`); ShowIn and leaving the container
    note the new look quietly.
* **MDI children** (`MDIChild`): `Show` hands them to `mdi.show_child` (not
  modally), `Load` shows them while the MDI form's AutoShowChildren;
  `_mdi_sub`, `_mdi_parent` once shown; `Hide`, `Unload` (the subwindow's
  close, which asks the form), `_frame()` (Left and Top move the
  subwindow), `_fit_mdi_sub` (Width, Height), `_apply_WindowState`, the
  window flags left alone; `_finish_unload` (Form_Unload and the unloading,
  split from `_query_unload` for the MDI form) calls `mdi.after_unload` and
  each control's `_form_unloaded` when it has one (a Process ends). Their
  menu bar is never the system's and stays hidden; `_menu_window` is the MDI
  form.
* **`ShowPopup(X, Y, Owner)`**: Tool, frameless, on top,
  `WindowDoesNotAcceptFocus` flags and `WA_ShowWithoutActivating`, at the
  owner's client point (mapped to the screen) or the mouse; hidden when the
  application leaves the active state (`_FormWidget._on_application_state`);
  the next `Show` makes it a window again (`_popup`).
* **`_FormType`**, Form's metaclass: default instances. For a form class (not
  `Form` itself, `_vp_base`; not one with `_vp_no_default`, the designer's
  `DesignForm` and user controls' surfaces), `__getattribute__` forwards
  public functions and properties to `_vp_default_instance()` (made on first
  use and kept in the class's `_vp_default`), `__getattr__` forwards what
  the class doesn't have (controls, variables), `__setattr__` forwards
  properties and the instance's existing variables. `_vp_ready` (set when
  the class body is done) keeps class creation (PropertyHost's
  `__init_subclass__`) from forwarding. `run(cls)` shows the default instance.
* **`Form(PropertyHost)`**:
  * **Closing:** `_query_unload(force, mode)` fires `QueryUnload(UnloadMode)`
    then `Unload` (each can cancel unless forced); the mode is
    `VP_FORM_CONTROL_MENU` from the close button (`_FormWidget.closeEvent`),
    `VP_FORM_CODE` from `Unload()` (set in `_unload_mode` before closing the
    window), 3 from `app.close_all_windows` (Ctrl+C), `VP_FORM_OWNER` for the
    forms shown in a closing form.
  * **Drag and drop, the pointer:** `_FormWidget` and `_FormClient` accept drops; their drag events go to `handle_drag_event` with the form (`_form_drag_event`; a user control's surface: the user control); `_apply_MousePointer` sets the window's cursor.
  * **Icon:** `_apply_Icon` sets the window icon from a Picture or a file
    relative to `_base_dir()` (`picture_pixmap`; none or unreadable: an empty
    QIcon, so the program's).
  * **Picture:** `_apply_Picture` keeps the background picture's pixmap
    (`_background`), which `_background_picture()` gives the drawing's
    `_paint_drawing` to draw first, at the top left.
  * **Construction:**
    * `__init__` (see architecture §4.4);
    * `__setattr__` names controls and `ControlArray`s assigned to
      attributes;
    * `_register_control`;
    * `_owner_form` / `_container_widget` / `_base_dir`, the same interface
      a container control offers.
  * **Popup menus:** `PopupMenu(Menu, Flags, X, Y, DefaultMenu)` maps X, Y
    (or the mouse's place) from the client area to the screen, moves the
    point for the center and right alignments by the menu's width, sets the
    default action, and runs the menu's `_submenu.exec`; the chosen item
    records itself in `_popup_chosen` (`Menu._on_triggered`, only while
    PopupMenu waits), which PopupMenu returns.
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
    everything in place; it records the space left in `_free_area`. A
    floating DockPanel (`_floating`) takes no space. `DockLayout` reads the
    DockPanels' places as JSON (`_dock_panels`, keyed by `_dock_key`) and,
    set, reorders them in their slots of `_controls`, then sets each one's
    Align, Floating, floating window, size and Visible. It runs
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
classes for their metadata. A user control's file is read the same way
(`find_form_kind`: "usercontrol" for `class X(UserControl)`; `FormDef.kind`):
its own properties are its surface's, `self.Surface.Width = 160`
(`_is_surface_attr`, `surface_specs`, written in `generate_region`).
`new_user_control_source` is a new user control's file; `import_insertion`
and `ensure_import` add `from ctlX import ctlX` after a file's imports. A
control whose class isn't known (a user control that couldn't be loaded)
keeps its values when the region is written (`_props_to_args`).

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
    `icon`, `version`, `product_name`, `company_name`, `description`,
    `arguments`, `arguments_help`, `path` (the ones missing from older projects get their
    defaults); `version_numbers()` is `version` as (major, minor, revision);
  * **the icon:** `icon` lists image files relative to the project (`load`
    turns a single string into a list); `icon_paths()` gives them as absolute
    paths. An empty `icon` (new projects) means the VP6 icon,
    `VP6_ICON_FILES` (four sizes in the package's `images` folder), used from
    the installation, never copied into the project;
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
* **Save Project As:** `copy_destination(project_file)` is (folder, project
  file) for a copy: the folder chosen if it's empty or new, else a new folder
  in it named after the file. `copy_project(project, project_file, texts)`
  copies `make.project_files` (not build, dist, caches, hidden files) there,
  the given texts (the IDE's documents, unsaved changes included) in their
  files' place and the project file under its new name (keeping code of its
  own around the region), then saves the project's fields as they are with
  the new name (the file's stem: an identifier) and returns the new
  `Project`. A ValueError for a bad name, a folder in the project's, or one
  that isn't empty.
* Constants: `EXTENSION = ".vp6p"`, `REGION_START` / `REGION_END`, and
  `_FIELDS` (the order the fields are written in).

### `vp6/usercontrol.py` (≈300 lines)

Your own controls (VB's UserControl).

* `Property(Name, Kind, Default, description, choices)` makes a `PropSpec`
  (an enum's names numbered from 0; a default by kind); `parse_events`
  splits `"Change(Value)"` declarations into names and `EventArgs`.
* `UserControl(Control)`: `__init_subclass__` puts the base properties
  (geometry and `_COMMON`) before the author's (`_author_properties`), parses
  `Events`, and makes the class name its `TypeName` (in the Toolbox, its first
  event the default). `_create_widget` makes its `_UserControlSurface` and
  uses the surface's widget; `_build_widget` then runs `InitializeComponent`
  (its controls go on the surface: `_owner_form` and `_container_widget` are
  the surface's; `__setattr__` names controls and control arrays), records
  the designed size (`_design_size`, the default Width and Height in
  `_init_values`) and fires its own `Initialize`. `_set_prop` fires
  `PropertyChanged` for the author's properties; `_own_event` calls
  `UserControl_<event>` methods; `RaiseEvent` fires a declared event on the
  form (`Control._fire`). `Surface`, `UserMode`, `Controls`.
* `_UserControlSurface(Form)` is never loaded (not in `Forms`). Its
  `__getattr__` forwards handler names (`_is_handler_name`: `cmdUp_Click`,
  not `Form_...` or `InitializeComponent`) to the user control, except at
  design time; its `_fire` passes `_SURFACE_EVENTS` (Resize, Click, mouse,
  keys, Paint) on as the user control's own, at design time only
  `_DESIGN_TIME_EVENTS`.
* `SURFACE_PROPERTIES`, `DEFAULT_SURFACE`, `OWN_EVENTS` and `OWN_EVENT_ARGS`
  (the code window's "UserControl" object).
* The IDE's registry: `register_user_control` adds a class to
  `CONTROL_TYPES` (not over a built-in name), `unregister_user_controls`,
  `user_control_types`; `load_user_control(path, text)` executes a file's
  text as a module named after the file (as forms import it) and sets the
  class's DefaultSize to its designed surface.

### `vp6/make.py` (≈330 lines)

Packages a project: a wheel (`vp6-make Name.vp6p [--dist DIR]`, the IDE's
Project > Build Wheel) or a standalone executable with PyInstaller
(`vp6-make --exe Name.vp6p [--onefile] [--dist DIR]`, the IDE's File > Make
Executable…); `python -m vp6.make` is the same. PyInstaller makes
executables for the system it runs on only.

* **Wheels** (written with `zipfile`, no build tools): `make_wheel(project_path,
  dist, log)` puts `project_files` into the package `wheel_package(project)`
  (the name in lowercase), adds an `__init__.py` (unless the project has
  one) and `__main__.py` (`_wheel_launcher`: `main()` runs the project file
  next to it with `run_project`; a project's own `__main__.py` is a
  MakeError), and the `.dist-info`: METADATA (`_metadata`: name, version
  `wheel_version` from `version_numbers`, summary, author, Python 3.10+,
  `wheel_requirements`: `vp6>=` this version and the distributions
  `importlib.metadata.packages_distributions()` gives for the imported
  modules, not `sys.stdlib_module_names`, PySide6 or VP6, noting those not
  installed), WHEEL (`py3-none-any`), entry_points.txt (`gui_scripts` for a
  windowed project, `console_scripts` for a console one) and RECORD
  (`_record_line`: sha256, size). `wheel_name(project)` is its file name.
  Its last line is `Made <path>`.

* `project_files(project)`: the files that go in (relative, with `/`), all
  but `EXCLUDED_FOLDERS` (`build`, `dist`, `__pycache__`, `venv`), hidden
  files and folders, and compiled files.
* The project's code goes in as files, not as PyInstaller-analyzed modules,
  so the runner imports it from the bundle as from the project's folder and
  forms find their pictures relative to their files (`__file__`).
  PyInstaller can't see what it imports, so `imported_modules(project)`
  reads every `.py` file with `ast` for its top-level imports (absolute
  ones; not the project's own modules) and they become `--hidden-import`s.
* `launcher_source(project)` is the entry script: `run_project` on the
  project file in `sys._MEIPASS` (where PyInstaller unpacks the bundle).
* `pyinstaller_command(project, launcher, dist, work, onefile, platform)`:
  `--console` or `--windowed` from the project's type; `--onefile` when
  `can_be_one_file` (not a windowed program on macOS: apps are folders);
  `--icon` (`icon_file`: the project's largest icon, else VP6's; none
  without Pillow, which PyInstaller needs to convert PNGs); `--paths` to
  VP6's own folder only for an editable install (`vp6_search_path`: its
  import hook is invisible to PyInstaller; a normal install is in
  site-packages, which PyInstaller searches and refuses as `--paths`), and
  VP6's `images` as data; an `--add-data` per project file,
  into the same folder (`os.pathsep` between source and destination, as
  PyInstaller wants on every system).
* `make(project_path, dist, onefile, log)` writes the launcher into a
  temporary work folder (also PyInstaller's work and spec folder, removed
  afterwards), runs the command, passes its output to `log` line by line and
  returns `output_path(...)`; `MakeError` without PyInstaller (`pip install
  "vp6[make]"`), when PyInstaller fails, or when the result isn't there.
  Its last line is `Made <path>`, which the IDE reads.
* `main(argv)`: the `vp6-make` command: a wheel, or with `--exe` (or
  `--onefile`) an executable (exit code 1 with the reason on stderr).

### `vp6/runner.py` (≈95 lines)

It's deliberately not named `run.py`: importing a `vp6.run` submodule would
replace the public `vp6.run()` function on the package, and `run(Form1)` in
programs would then fail.


Starts a project. `run_project(path)`:

1. loads the project; with `--help` (`HELP_OPTION`) among the program's
   arguments, shows `program_help(project, prog)` (name, version,
   description, usage, the project's `arguments_help`, VP6_PYTHON when
   run by its project file) with `show_help` (stdout, or a MsgBox when there is none: a
   windowed executable on Windows) and returns 0 without starting anything;
2. puts `import_folders(project)` on `sys.path` (the project's folder, then
   every folder holding a form or module, so files in subfolders import each
   other by name) and `chdir`s into the project's folder;
3. sets `App`'s title, version and descriptions (`App._set_project`) and
   `appearance.project_scheme`, and for a windowed
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

`main(argv)` implements `python -m vp6.runner PROJECT.vp6p [ARGUMENTS...]`
and the `vp6-run` console script (`argument_parser()`: argparse, the
program's arguments a REMAINDER, so `--help` after the project is the
program's). It makes `sys.argv` the project and its
arguments, as when the project file runs itself, so `sys.argv[1:]` (and
`Command()`) are the program's arguments either way.

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
  * `save_project_as(path=None)` (File > Save Project As…, `act_save_as`;
    asks with a save dialog, `.vp6p` added): `copy_project` with every
    document's text, then marks them unchanged (their changes are in the
    copy), closes the project and opens the copy;
  * `add_form(base)`, `add_mdi_form` (Project > Add MDI Form: one a project),
    `add_module`, `add_file` (new files go in
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
  * **File > Make Executable…** (`act_make`, `make_executable`) and
    **Project > Build Wheel** (`act_wheel`, `build_wheel`): save everything
    (the executable asks with a `MakeDialog`), then `start_make(onefile,
    wheel)` runs `python -u -m vp6.make` (`_make_command`: `--exe`, `--onefile`
    for an executable; `_make_title`, `_make_what` name it in messages) in a
    `QProcess` of its own
    (`make_process`; the action is disabled meanwhile) with VP6 on its
    PYTHONPATH, its output merged into the Output window
    (`_on_make_output`, which notes the `Made <path>` line). When it ends
    (`_on_make_finished`), a message box gives the path with **Show in
    Folder**, or says it failed;
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
  * View > Object Browser (`act_view_browser`, F2; `show_object_browser`,
    made once and refreshed when shown again): `_browser_project` gives the
    project's name and documents in its order, `_browser_goto` shows a member
    (a control selected in its form's designer, else its line with
    `open_location`, or the file's code window);
  * `_designer_call(method, *args)` for the Format menu; Format > Lock
    Controls (`act_lock`, checkable; `lock_controls`) locks the current
    form's designer (`_current_designer`: also from its code window) and keeps
    it in the IDE's settings (`_lock_key(path)`), read when the designer is
    made (`_designer_for`); `_update_lock_action` checks or disables it as
    windows are activated;
  * `_edit(op)` for the Edit menu: to the designer, the code editor, or a
    focused text field outside the MDI area;
  * `_view_current`.
* **Running:**
  * `run_project` (F5, ⌘/Ctrl+Enter: the project file, with
    `run_arguments()`, the project's `arguments` split as a shell would; the
    IDE's scheme in `VP6_IDE_SCHEME` and, live, in the file
    `_write_ide_scheme` keeps (`VP6_IDE_SCHEME_FILE`: rewritten whenever the
    theme manager changes, removed when the IDE closes)),
    `stop_project`, `restart_project`;
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
  and `vp6.png`. No template's project gets an icon of its own: they show
  the installed VP6 icon until one is set.
* `main(argv)` is the application entry point. It gives the application the
  VP6 icon (`app.vp6_icon`: the Dock or taskbar); `MainWindow` sets it on
  itself too. Unless `--no-splash` is given, it shows the splash screen
  (`splash.SplashScreen`) first, builds the window meanwhile, and shows the
  window once the splash screen has finished (`wait`).
  `parse_arguments(argv)` gives `(project, splash)` from `vp6 [--help]
  [--no-splash] [Project.vp6p]` (options may come before or after the
  project), with `argument_parser()` (argparse: `--help` prints the options
  and the environment variables, and exits; options it doesn't know are left
  to Qt).

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
* **`_Designed`**, a mixin, makes `DesignForm(Form)` and
  `DesignMDIForm(MDIForm)` (chosen by `formfile.find_form_base`: an MDI
  form's file; its workspace shows, its BackColor colors it) the
  design-mode forms:
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
  * **Locked** (`FormDesigner.locked`, `set_locked`; Format > Lock Controls):
    `_handle_at` gives no control handles (the form's still resize), a press
    on a control selects it without starting a move, the handles are drawn
    hollow, and `nudge` refuses with a status message.
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
    OS light/dark changes, via `_on_os_scheme_changed` on the appearance
    watcher, which sees them while the IDE forces its scheme too),
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

* `TextListDialog` edits a list (one item per line) or multi-line text. With
  `pictures_dir` (an ImageList's `ListImages`) it has an **Add Pictures…**
  button; `add_pictures(paths)` appends `path|key` lines, relative to that
  folder when inside it, with the file name as the key.
* `PropertiesWindow(QWidget)`:
  * **Binding:** `set_designer(designer)` connects to `selectionChanged` and
    `designChanged`; `refresh()` rebuilds the object combo and the grid
    (common properties across the selection; `_MIXED` marks differing
    values). A single control also gets the `Index` row (`INDEX_SPEC`, kind
    `index`, empty = not in a control array) under `(Name)`, when the target
    has `supports_index`; `(Name)` shows the target's `name_value`. The
    `shortcut` kind (`Menu.Shortcut`) is edited with a combo box, and the
    `outline` kind (`TreeView.Items`) like a list, in a `TextListDialog` with
    a hint about indentation, keys and images; so are the `panels`, `tabs`
    and `images` kinds (StatusBar.Panels, TabStrip.Tabs, ImageList.ListImages),
    each with a hint about its line format, shown as "(Panels: N)" and so on
    and read from `_values` (at run time those names are the collections).
  * **Editors:** `_editor(spec, value)` picks an editor by kind;
    `_color_editor`, `_choose_color`, `_edit_list`, `_edit_text` and
    `_browse_file` (stores paths relative to the form folder when possible).
  * `_commit(prop, value)` calls `designer.set_property` and shows any error.
  * The description pane shows the spec's `description`.
  * `select_property(name)` focuses a property's row and editor.
  * The window is bound to a target with `set_designer(target)`: a
    `FormDesigner`, or the `ProjectTarget` (see `projectprops.py`).
  * **Alphabetic / Categorized:** `view_tabs` (a `QTabBar`; the choice kept
    in the IDE's settings, `properties/view`); `categorized()`. Categorized,
    `refresh` puts a heading row (`_add_heading`: bold, across both columns,
    ▾ or ▸) before each category's properties (`category_of`, (Name) first);
    `_specs` has the category's name in a heading's place. Clicking a heading
    (`_on_cell_clicked`) calls `toggle_category`, which hides or shows its
    rows; `collapsed` keeps the closed ones across refreshes, and
    `select_property` opens a property's category.

### `vp6/ide/projectprops.py` (≈250 lines)

The project, files without a designer and Project panel groups, as targets
of the Properties window.

* `ProjectTarget(QObject)` offers the same interface as `FormDesigner`
  (`selected_objects`, `all_objects`, `object_name`, `select_by_name`,
  `set_property`, `base_dir`, signals `selectionChanged` / `designChanged`).
  The Properties window therefore edits the project without special cases.
* It exposes the project's `(Name)`, `Type`, `StartupObject` and
  `ColorScheme` as `enum` specs, and `Version` (validated as up to three
  numbers, stored as major.minor.revision), `ProductName`, `CompanyName`,
  `Description` and `Arguments` as text, and `ArgumentsHelp` as multi-line
  text. `StartupObject`'s choices are the project's
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

### `vp6/ide/findreplace.py` (≈560 lines)

Find and Replace in the code window or the whole project, and Go to Line.

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
* **In the whole project:** a `ProjectFiles` (the main window's
  `_ProjectFiles`) gives `documents()` (the project's forms, user controls
  and modules as (path, QTextDocument), in the project's order),
  `current_path()` and `editor_for(path)` (opening its code window).
  `_matches` lists a document's matches as `Found` (path, Qt positions, line,
  its text); `find_all(files, options, only)` all of them (or one file's);
  `show_found` opens the code window and selects one.
  `find_next_in_project(files, options, backward)`: after (before) the
  selection in the current file, then the other files in turn, then round
  to the current file's other end ("Passed the end of the project" when it
  went round); `replace_one_in_project` replaces the selection
  (`_replace_selection`, shared with `replace_one`) then finds on;
  `replace_all_in_project` replaces in every document, each one undo step,
  the files left unsaved, never in a designer region (`region_span`: the
  region's positions in a document, from `formfile.find_region`).
  `_replace_in_document(document, pattern, options, editable)` does the
  replacing for both `replace_all`s.
* **`FindReplaceDialog(get_editor, parent, files)`**, non-modal: find and
  replace fields, *Match case*, *Find whole word only*, *Use regular
  expressions*, VB's *Search* (Current module / Current project, the latter
  only with `files`; `in_project()`), a status line, Find Next / Find
  Previous / Find All / Replace / Replace All / Close, and the Find All list
  (`results`, `found`; activating a row shows that match).
  `show_find(replace)` shows it as Find or Replace, taking the selected text
  (one line) as the text to find. Typing in the find field, or changing an
  option, runs `find_as_you_type`, so the first match is highlighted as you
  type.
* **`ask_line(editor, parent)`**, the Go to Line box (`QInputDialog.getInt`,
  1 to the line count, the current line suggested).

### `vp6/ide/objectbrowser.py` (≈480 lines)

The Object Browser (View > Object Browser, F2).

* **The model** (plain Python): `ClassInfo` (name, kind: Class, Object,
  Globals, Constants, Form, UserControl, Module; library, description, path
  and line for the project's, `type_name` for a control class) whose
  `members()` (made when first asked, alphabetical) are `Member`s (name,
  kind: Property, Method, Event, Constant, Variable, Control, Class;
  declaration, description, path and line, `type_name` for a control).
* `vp6_library()` (made once): every class in `vp6.__all__`
  (`_class_members`: spec'd properties with their kind's type
  (`_KIND_TYPES`), description, choices and default (`_property_member`);
  other properties with their docstrings, read-only marked; methods with
  `inspect.signature` and their docstring's first paragraph; plain data
  attributes; events with `EVENT_ARGS`; not `_NOT_MEMBERS`), the global
  objects (by their types), "Globals" (the functions), a Constants class per
  `constants.py` group (`_constant_groups`: its `# --- title ---` comments),
  Colors and Color schemes.
* `project_library(name, documents)`: modules (`_module_members`: functions,
  classes, constants in capitals, variables with their values from the
  source) and forms and user controls (`_form_class`: their controls from
  `form_def`, once per control array; a user control's Properties and Events
  from its registered class; methods but `InitializeComponent`), parsed with
  `ast` from the documents' current text (`_parse`: before a syntax error,
  what can be parsed).
* `search(classes, text)`: classes and members whose names contain it.
* **`ObjectBrowser(get_project, goto, parent)`**, a window of its own: the
  library combo (All Libraries, VP6, the project; `library_classes()`), the
  search field and Search button (`run_search`: the results list, choosing
  one selects its class and member), the Classes and Members lists with
  `kind_icon`s (a control's Toolbox icon, else a colored letter badge), and
  the details pane (declaration, "Member of Library.Class", description).
  `show_class(name, member)` selects them; `refresh()` reads the project
  again; activating a project member calls `goto(path, line, control)`.

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
  Shortcut, NegotiatePosition and WindowList (kept in the entry's `props`)
  and Checked / Enabled / Visible for the current item, the arrow
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
    it): View Code / View Object / Set as Start Up / Remove for a file, and
    in the Project view Rename File… and Delete File… (`renamePath` and
    `deletePath`, which the main window handles as in the Files view);
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
* `FormDocument(Document)` (a form's or a user control's file):
  * `form_def`, `kind` (`form_def.kind`: "form" or "usercontrol"), `name`
    (the class name found in the text), `region_range()`;
  * `set_form_def(form_def)` regenerates the region and, in the same undoable
    edit, adds the imports of the user controls on the form
    (`_missing_imports`, `formfile.import_insertion`);
  * `_on_text_changed` re-parses; signals `designReloaded` and `parseError`.
* `open_document(path)` picks the class by content.

### `vp6/ide/kitchensink.py` (≈70 lines) and `vp6/ide/templates/kitchensink/`

The Kitchen Sink project template: a demo of every control and feature,
explorer-style.

* `create(directory, name)` copies `FORMS` (the window, its pages in the
  index's order, and the dialog), `USER_CONTROLS` (`ctlRating.py`, in a User
  Controls group) and `MODULES` (`Module1.py`) from
  `TEMPLATE_DIR`, draws the picture `PICTURE` (`vp6.png`, via
  `draw_picture`, so the package ships no binary) and the ImageLists'
  pictures (`draw_icons`: `IMAGES/<name>.png` for each of `ICONS`, 32 × 32),
  and returns a Standard
  EXE `Project` that starts in Sub Main. `mainwindow.create_project(...,
  "kitchensink")` calls it.
* **`templates/kitchensink/Form1.py`**, the explorer window. It is laid out
  with docked controls: the StatusBar `sbStatus` (Bottom; a Spring status
  panel that `status(text)` sets, Caps Lock, and a clock that
  `sbStatus_PanelClick` switches between the time and the date), the
  Toolbar `tbrMain` (Top; pictures from the ImageList `imlToolbar`: Back and
  Forward (`step_page`), the navigation pane as a Check button, and the
  color schemes as a ButtonGroup, kept in step with the View menu by
  `show_navigation` and `set_scheme`; `tbrMain_ButtonClick`), `picNav`
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
  * `Form_Unload` unloads the pages (also one popped out).
* **The pages** (one form each, shown in the content pane):
  * `pgIntro.py`: the introduction, a Markdown Label whose links show pages;
  * `pgText.py`: Labels (alignment, AutoSize, access keys) and TextBoxes
    (multi-line, password, upper-casing KeyPress), GotFocus/LostFocus,
    Change, a Default button with InputBox/MsgBox, a Frame's Click;
  * `pgRichText.py`: a RichTextBox word processor (Graphical B/I/U CheckBoxes,
    color and size ComboBoxes and alignment OptionButtons formatting the
    selection, kept in step in SelChange with a `syncing` flag; Find next,
    wrapping; SaveFile/LoadFile as HTML in the temp folder; the line from
    GetLineFromChar) and a Locked RichTextBox as a log filled by AppendText;
  * `pgEditing.py`: the editing API as a small code editor (a Courier
    TextBox with AcceptsTab): line and column in SelChange, Undo/Redo buttons
    following CanUndo/CanRedo (ClearUndo after loading), Indent at the line's
    start (GetCharFromLine), Go to line (CurrentLine, FirstVisibleLine), the
    word under the mouse (GetCharFromPoint, GetLine, GetColumnFromChar), and a
    completion ListBox moved under the caret (CaretLeft/Top/Height) that
    Enter, Tab or a click accepts and Esc closes (KeyPress returning 0);
  * `pgCode.py`: a CodeBox with Python colors and the page's own in
    Highlight (TODO and FIXME on yellow), breakpoints toggled by GutterClick
    (LineMarker), a "# region" block protected with ProtectLines (its
    ProtectedEdit message) and folded with HideLines/ShowLines from the gutter
    or a button (its marker - or +), the region found again in Change with
    IsLineProtected after edits above it, and check boxes for LineNumbers,
    HighlightCurrentLine, WordWrap and Language;
  * `pgGrid.py`: a FlexGrid price list (FormatString, AddItem with RowData,
    sorting by the heading clicked, found with MouseRow and MouseCol, the
    other way on a second click; the current row in RowColChange) and an
    Editable property sheet with an editor per cell (text, check, list,
    color, a `...` button asking with InputBox in CellButtonClick), Width
    checked in ValidateEdit, and a sample Label following it in AfterEdit;
  * `pgButtons.py` (with Graphical buttons: `cmdStar`, a picture button with
    a DownPicture; `chkUnderline`, a toggle CheckBox; `optAlign`, toggle
    OptionButtons in the Alignment frame): CommandButtons (Value = True clicks), CheckBoxes (also
    grayed), OptionButtons in two Frames (two groups), and `cmdHop` moving
    itself into the Basket frame and back (Container);
  * `pgLists.py`: a sorted ListBox with Add/Remove, Click and DblClick,
    pictures from the ImageList `imlLists` (`ItemImage`; added items get a
    star, italics and their time as `ItemData`, `NewIndex` and `TopIndex`),
    ComboBoxes (a list of colors from `vpRed`, `RGB` and `QBColor` kept in
    `ItemData`, each name in its color with `ItemForeColor`; an editable one
    adding what was typed in `DropDown`; a Simple Combo), and a Checkbox
    ListBox of toppings (`ItemCheck`, `SelCount`);
  * `pgScrollBars.py`: HScrollBar and VScrollBar, Change and Scroll;
  * `pgListView.py`: a ListView of pets (a Report view with three columns,
    pictures from two ImageLists), the view chosen in a ComboBox, ColumnClick
    sorting by the clicked column (again: reversed), ItemClick and
    ItemCheck, check boxes and multiple selection, adding and removing items;
  * `pgFiles.py`: a DriveListBox, DirListBox and FileListBox linked in
    their Change events, the Pattern from a ComboBox (PatternChange), hidden
    files and folders from a CheckBox, PathChange, the DirListBox's negative
    List indexes in Click, and the chosen file's size and picture;
  * `pgTabs.py`: a TabStrip with a Frame per tab over its client area
    (placed in Form_Load, shown in Click), BeforeClick cancelling while "Lock
    the tabs" is checked, and Placement from a ComboBox;
  * `pgValues.py`: Slider (Scroll and Change, a vertical one with ticks on
    both sides), ProgressBar (filled by a Timer, and a vertical one following
    the Slider), UpDown with a TextBox buddy (UpClick, DownClick, Change) and a
    horizontal, wrapping one with a Label buddy;
  * `pgPictures.py`: a PictureBox with a Label on it (Click, MouseDown, a
    Tag from InputBox) and an Image thumbnail; Picture objects: one made in
    memory (Picture with a BackColor, PaintPicture of the logo file, Circle,
    Print) as a PictureBox's Picture and a small one as its MouseIcon,
    SavePicture of its Image and LoadPicture into an Image, Copy and Paste
    with Clipboard.SetData / GetFormat / GetData, and the form's own
    background Picture from a CheckBox;
  * `pgDrawing.py`: a sketch pad (a PictureBox with AutoRedraw: PSet on
    MouseDown, `Line(X, Y)` on MouseMove, DrawWidth from an HScrollBar,
    DrawStyle from a ComboBox, Cls), shapes (Line boxes, hatched and solid
    fills, Circle, an ellipse, a pie and an arc, PSet, Print centered with
    TextWidth and TextHeight, Point), a clock drawn in its Paint (AutoRedraw
    False) that a Timer refreshes, in a User scale (Scale(-1.1, 1.1, 1.1,
    -1.1): the center 0, 0), and the page's own Form_Paint;
  * `pgZOrder.py`: ZIndex and ZOrder, Lines (a dashed one above the labels,
    a control array of Lines with BorderStyle 1 to 5, a thick one), Shapes
    (a control array of every kind in QBColor colors, and one whose Shape and
    FillStyle come from ComboBoxes and BackStyle from a CheckBox);
  * `pgTree.py`: a TreeView with check boxes, adding and removing nodes,
    NodeClick/NodeCheck/Expand/Collapse;
  * `pgTimer.py`: a clock whose Timer runs only while the page is visible
    (Form_Activate / Form_Deactivate);
  * `pgLayout.py`: how the window is laid out, hiding and widening the
    navigation pane;
  * `pgDocking.py`: three DockPanels (Tools with buttons, Properties with a
    FlexGrid listing where each panel is, Output with a RichTextBox log) and a
    Fill PictureBox in the middle; DockChange logged and the list updated,
    Output's Close cancelled while "Keep Output open" is checked, a closed
    panel shown again by double-clicking its row, Float/Dock from a button,
    DockLayout saved and restored, the panels' contents following their
    Resize;
  * `pgWeb.py`: a WebView and a WebBrowser in the same place, chosen by
    option buttons (`self.web` is the one shown), both starting with HTML of
    the program's own (LoadHTML); an address box with Go (the Default
    button), Back and Forward following CanGoBack/CanGoForward in
    DocumentComplete, Refresh, RunScript counting the page's links, a status
    line from TitleChange, ProgressChange and NavigateError, and the
    WebBrowser's BeforeNavigate (keeping it from example.org), NewWindow and
    StatusTextChange;
  * `pgScrolling.py`: a page 1000 pixels tall, and ScrollTop;
  * `pgEmbedded.py`: a page popping out into a window of its own and back
    (`ShowIn(None)`), laid out with a Bottom and a Fill pane, with a clock
    that runs while it is visible;
  * `pgDialogs.py`: MsgBox, InputBox, the modal `frmDialog` by its default
    instance (`frmDialog.Show(vpModal)`, `frmDialog.Result`), Beep, and the
    CommonDialog `cdlFiles`: Open (a Filter, several files), Save As (the
    sample written to the file, DefaultExt, the overwrite prompt), Color
    (CancelError and DialogCancelled), Font and Print (a page range), applied
    to a sample label; printing (`print_pages`: a heading, the sample in its
    font, a frame, a circle and the logo with PaintPicture, NewPage, EndDoc)
    after ShowPrinter, or to a PDF file chosen with ShowSave
    (`Printer.OutputFile`), and a ComboBox of `Printers` choosing
    `Printer.DeviceName`;
  * `pgSchemes.py`: the color schemes as the option-button control array
    `optScheme` (`SCHEMES`); the page's DarkMode and Screen.DarkMode, and
    Form_ColorSchemeChanged counting the changes and drawing a sun or a moon
    again (`show_mode`) in an AutoRedraw PictureBox;
  * `pgKeyboard.py`: KeyPreview, KeyDown/KeyUp, KeyPress replacing or
    swallowing keys, Default and Cancel buttons, an Age box checked in
    Validate with a Help button that has CausesValidation = False,
    ActiveControl and Screen.ActiveControl shown by a Timer, and SendKeys
    typing into the upper-case box and pressing Enter;
  * `pgMouse.py`: MouseDown/MouseMove/MouseUp with buttons, Click, DblClick;
    the pad's MousePointer from a list and Screen.MousePointer's hourglass
    for a second (a Timer); fruit labels (a control array, DragMode
    Automatic, one with a DragIcon) dragged into a basket (DragOver lighting
    it, DragDrop moving the fruit in with Container) and out onto the page
    (Form_DragDrop); a drop zone for text and files from other programs
    (OLEDropMode Manual, OLEDragDrop);
  * `pgProcess.py`: a Process running a small Python program (`ECHO`) that
    answers the lines sent with WriteLine (upper-cased; "error" on its
    standard error; "quit" ends it with code 3): Output and ErrorOutput in a
    TextBox, Exited and Error in a label, Kill, a missing program, and Shell
    opening the project's folder in the file manager;
  * `pgTerminal.py`: a Terminal running your shell (AutoStart), Demo
    typing a command (Write) that writes bold, underlined, inverse and
    colored text, a DEC line drawing box and its TERM, sets the title
    (TitleChange) and shows VP6's icon three times (`ICON_FILE`): by the Kitty
    graphics protocol (`ICON`: the path, `t=f`) and, beside it (`CSI 2 A`),
    as an iTerm2 inline image (the shell's `base64` of the file) and in sixel
    graphics (`cat` of `SIXEL_FILE`, written by `icon_sixel` on Demo: the
    icon `SIXEL_SIZE` pixels square through a Picture's PaintPicture and
    Point, 64 registers, runs and `!` repeats; mode 8452 keeps the cursor
    beside it), then a gradient in true color (`48;2;r;g;b`, a shell loop)
    and a few ligatures with `COLORTERM=[...]`, a ComboBox of terminal types
    (TerminalType: the shell restarted as one), a Font ComboBox (`SYSTEM_FONT`
    first: FontName unset, then `Screen.FixedFonts`), a Ligatures CheckBox, Clear,
    Restart (Kill, then Start in Exited), and the
    shell's end;
  * `pgMDI.py`: a button opening the Notes window (`frmMDI`), and a TextBox
    showing `frmSuggest` with ShowPopup under it as you type (fruits starting
    with the text), Up and Down choosing in it from the TextBox's KeyDown,
    Enter taking one, Esc hiding it, and hiding it when the page is left;
  * `pgArrays.py`: the `cmdMore` control array loading and unloading
    elements;
  * `pgMenus.py`: the menus, adding bookmarks (a menu control array grown
    at run time), a Page menu of its own that joins the window's menu
    bar while the page is visible (NegotiatePosition; the window's Help is
    Right too, so it stays last), and an invisible Popup menu shown by
    PopupMenu on a label's right-click (MouseUp, a bold DefaultMenu, None when
    closed without a choice) and centered under a button;
  * `pgGlobals.py`: App (its version and descriptions, from the project,
    and PrevInstance), Command(), Screen (and its Fonts in a ComboBox
    changing a label's font), Forms, Clipboard, settings (the text box's text
    saved with SaveSetting and read back in Form_Load, GetAllSettings shown,
    DeleteSetting), DoEvents, Debug.Print and End;
  * `pgUserControl.py`: three `ctlRating`s with different Value, Max,
    StarColor and Locked, their Change and Hover events, an average, and a
    Value set from code;
  * `ctlRating.py` (in `USER_CONTROLS`): a user control, a star rating: its
    Properties and Events, a control array of Labels on its surface, Max and
    Value kept in range in `UserControl_PropertyChanged`, Change raised there,
    Hover from its stars' MouseMove.
  Pages that talk to the window use their `shell` attribute (None when a
  page runs on its own).
* **`frmMDI.py`** is an MDI form (`MDIForm_Load` opening two notes; a tool
  pane docked at its top with New note, Cascade and Tile; a Notes menu; a
  Window menu with WindowList and the Arrange choices; ActiveForm shown in
  a label); **`frmNote.py`** an MDI child (a MultiLine TextBox filling it in
  Form_Resize; its own Note and Window menus, which replace the MDI form's
  while it is active; Form_Activate and Form_Unload telling the MDI form);
  **`frmSuggest.py`** a popup form (a ListBox of suggestions: `fill`,
  `move`, a DblClick calling the page's `chosen`).
* **`frmDialog.py`** is a modal dialog (`Show(vpModal)`) with its own Dark
  color scheme and window Icon, used through its default instance with a
  `Result` attribute; `Form_Load` resets it each time, `Form_QueryUnload`
  records why it closed (`ClosedBy`).
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
  scheme (System / Light / Dark / Follow the IDE), and as VB's Make tab the
  version (three spin boxes, `version`), product name, company name,
  description, command line arguments and the arguments' help (a
  `QPlainTextEdit`); `apply(project)`.
* `MakeDialog(project)`: File > Make Executable…: what will be made and
  where (`make.output_path`), and a "One file" check box, disabled where it
  can't apply (`make.can_be_one_file`).
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

### `vp6/ide/splash.py` (≈90 lines)

The splash screen shown while the IDE starts.

* `SplashScreen(duration=None)`: a frameless `Qt.SplashScreen` window (it
  can't be moved) of a fixed size (it can't be resized), with the logo
  (`dialogs.logo_pixmap`) and "VP6 <version>" centered under it, in a thin
  border. `duration` defaults to `DURATION` (2000 ms), read when it is made.
  Its stylesheet sets its own colors, `BACKGROUND` (light grey) and
  `VERSION_COLOR` (dark blue-grey), so a Dark palette (the OS's, or the
  IDE's, applied while it shows) doesn't make the text white.
* `start()` shows it in the middle of the primary screen and starts its
  timer; `finish()` (the timer) sets `done`, closes it and emits `finished`;
  `wait()` runs an event loop until then (at once if already finished).
* Only the timer closes it: `closeEvent` ignores close requests until
  `done`, and mouse presses and keys (Esc) are swallowed.

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
  that `ide_settings()` is really isolated; the programs' settings
  (`app.SETTINGS_DIR`) to a folder of the test's own;
* makes a Terminal without a CommandLine run `/bin/sh` rather than the
  user's own shell (`_a_plain_shell_for_terminals`);
* sends every Printer document to PDF files in a folder of the test's own
  (`printer.REDIRECT_DIR`), so nothing is printed, and puts the Printer back
  as it was (`_printing_to_pdf_files`);
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
| `test_focus_keys.py` | Validate keeping the focus (no LostFocus or GotFocus), passing, only for the control left; CausesValidation = False; a button clicked while invalid not clicked; which controls have Validate; Form.ActiveControl and Screen.ActiveControl (a user control's inside: the user control); SendKeys parsing (modifiers, groups, specials, repeats, escaped characters, errors) and sending (at once, later, Tab moving the focus, Enter on the Default button, Shift seen by KeyDown, a menu Shortcut, a Label's access key, editing keys). |
| `test_form_instances.py` | Default form instances (made on first use; methods, controls, properties and variables through the class; an instance of its own apart; class constants and classmethods the class's; Form itself untouched; Unload and Show again: the same instance), run() showing the default instance; Form_QueryUnload's UnloadMode from code, the close button, Ctrl+C and a closing owner form, cancelling before Form_Unload; a form's Icon (relative, absolute, unreadable, none). |
| `test_formfile.py` | Region round trips, default elision, line wrapping, invalid regions, renames (controls, form classes, class and module references in other files), the console template. |
| `test_graphical_buttons.py` | Style = Graphical: a picture button (the picture above the Caption, DownPicture while pressed, DisabledPicture, no picture on a Standard button, Value = True and Default still working, picture-only and text-only), CheckBox toggle buttons (pressed while checked, Click from the user and code, Grayed not pressed), OptionButton toggle buttons exclusive with the container's ordinary ones (a pressed one staying pressed), changing Style keeping the Value without Click, the font size; the form file round trip and the designer. |
| `test_control_arrays.py` | Control arrays: elements, `[i]` / `(i)` / `Item`, iteration, bounds, read-only `Index`, handlers getting `Index` first, `Load`/`Unload` of run-time elements (copied properties, hidden, last in the tab order; designer elements can't be unloaded), one type per array; the form file round trip (elements as containers too) and invalid arrays; adding/removing the `Index` parameter and stubs; in the designer: paste asking to create an array, renaming into an array (and out, and into another type's name), the Index property (one-element arrays, moving, clearing, undo), containers that are elements; the Properties window's `(Name)`, `Index` row and object list; the code window's Object list, new handlers with `Index`, completion. |
| `test_menus.py` | Menus at run time: the menu bar and items, separators, shortcuts; an in-window menu bar keeping `Height`, `ScaleHeight` and control positions for the area below it (the window grows), form mouse events there; Click on choosing an item and before a menu opens; `Checked` changing only in code; Enabled, Visible, Caption and Shortcut changes; menu control arrays loading after their last element and unloading; the parent check; the form file round trip; the Menu Editor's entries and ControlDefs, validation messages and dialog editing (Next, indent, shortcut, Insert, Delete, moving, outdent); menu negotiation (merged by NegotiatePosition, left out for None, the inner handlers, leaving when hidden or replaced, popped out with its own bar, NegotiateMenus off, a position changed and a menu added while merged, a window without menus, the Menu Editor's NegotiatePosition); the designer's menu bar (layout, hit testing, the drop-down opening Click code), menus kept off the canvas and edited in the Properties window, deleting a menu with its items, renames and arrays updating handlers, undo; the IDE's Tools > Menu Editor (Ctrl+E). |
| `test_image.py` | The Image control: taking the picture's size without Stretch (and with a border), filling the control with Stretch, switching back, clearing the picture; mouse events, no focus or Tab stop, not grayed but silent when disabled, transparent; its properties in order and the form file; in the designer: sized by a new picture, resized with Stretch, the Properties rows; the Toolbox button and icon. |
| `test_imagelist.py` | The ImageList: its designer lines; the ListImages collection (Index and Key, one size from the first picture or ImageWidth/ImageHeight, Add, errors, Remove), invisible at run time, a ListImage's Picture shown by an Image; a TreeView and TabStrip created before it showing its pictures by key and Index, code setting Images (unknown ones raising), `Nodes.Add` with an Image, following Clear and Add, no ImageList (picture files, an Index an error); the form file round trip; the designer (its icon, the pictures shown while designing, the Properties window's ListImages); Add Pictures… in the list dialog; Toolbox and icon. |
| `test_embedded_forms.py` | Activate/Deactivate in a container (Load then Activate; hidden and shown, the container hidden and shown, popped out, unloaded), a filling form replacing another (no second Load; Fill=False forms staying), window activation not applying; `Form.ShowIn`: filling a PictureBox and following its size (Load before the first Resize), controls working, window-only properties not popping it out; a Frame's inside, a form as the container, `Fill=False` at Left/Top; popping out, moving between containers, Hide/Show; unloading only itself, going with its host (unable to cancel), a host that cancels keeping it; invalid containers and cycles; nested forms and Default buttons. |
| `test_align.py` | PictureBox `Align`: docking in creation order, Fill panes taking the space left (after the others, several sharing it), following the form (before Form_Resize), changing a pane's thickness, place, visibility and Align; only on the form; panes created in code; under an in-window menu bar; in a form shown in a container; in the designer (Align stored with the docked geometry, the form resized, a pane dragged back, undo); the constants. |
| `test_splitter.py` | The Splitter: docking beside its pane, cursors, dragging (live Resize with everything in place, Moved on release), Bottom/Top/Right panes growing the right way, MinSize on both sides, disabled, no pane; the PictureBox Resize event; the file, the designer (docked after the pane) and the Toolbox. |
| `test_splash.py` | The command line (`parse_arguments`: a project, `--no-splash` before or after it, a missing file); the splash screen (2 seconds by default, frameless and of a fixed size, the logo with the version centered under it, not closed by `close()`, a click or Esc, closing itself when its time is up, its colors the same under a light and a dark palette); `main()` showing the window after the splash screen, and no splash screen with `--no-splash`. |
| `test_statusbar.py` | The StatusBar: the designer's panel lines (`parse_panel`); docking at the bottom beside other docked controls, following the window (Spring panels growing), Top, hidden taking no space; the Panels collection (Index and Key, Add at an Index, unique keys, errors, Contents and fixed widths, Alignment, ToolTipText, hidden panels, Remove, Clear, changing a Key); time and date panels kept up to date, lock keys dimmed when off; Simple style; PanelClick, Click and PanelDblClick from the mouse; the form file round trip; creating it in the designer (docked, one panel to start, no clock running, the Properties window's Panels); Toolbox, icon and constants. |
| `test_tabstrip.py` | The TabStrip: the designer's tab lines (`parse_tab`); tabs, captions and tooltips; the selection (the first to begin with, no Click while loading, SelectedItem by Key, Index or Tab, `Selected`, Click from code); the user's clicks, BeforeClick cancelling, no BeforeClick for the selected tab; Add before the others keeping the selection without Click, Caption and ToolTipText, errors, Remove, Key changes, Clear; the client area for every Placement (equal to Qt's layout, and already right in Form_Load), a Frame over it on top; the form file round trip; the designer (one tab to start, the Properties window's Tabs); Toolbox, icon and constants. |
| `test_terminal.py` | The ANSI screen: text and controls (CR, LF, TAB, BS, wrapping), cursor movement and erasing, inserting and deleting lines and characters, saving the cursor, colors and attributes (16, bright, 256, RGB), true color (semicolons and colons, at most 255, DECRQSS, XTGETTCAP's RGB, Tc, setrgbf and setrgbb; drawn, inverse too), ligatures (`_text_parts` with and without, `_fits_cells` refusing wider characters, runs drawn whole and split at the cursor, a character at a time with Ligatures off), scrolling and the history's limit, a scroll region, the title, the alternate screen, reset, resizing; the terminal types (their Device Attributes and other answers: status, the cursor, the size, colors, modes, settings, terminfo, the version; a vt100 not answering xterm's), character sets (DEC line drawing, SO/SI, single shifts), 8-bit controls (not a vt100's), DCS/APC/PM/SOS strings left out, REP, the alignment test, modes (autowrap, the wrap kept by SGR, insert, new line, origin, soft reset, tab stops, the cursor's shape, reverse video, mouse modes one at a time, full reset), the title stack and the alternate screen keeping the cursor and resizing, more attributes (dim, italic, blink, invisible, strike, colon forms, xterm's key options not taken for SGR), keys by terminal type and mode (xterm's modifiers, application cursor and keypad keys, new line Enter, a vt220's Find and Select, a vt100's PF and keypad keys); the mouse (SGR and X10, Shift selecting), focus and bracketed pastes reported to a stand-in program, and the terminal's answers sent to it; the TerminalType property (TermName, out of range, its default); keys as a terminal sends them; a real shell in a pseudo-terminal (its TERM, its tty and size, the title, Ctrl+C interrupting, its exit code, another program with Start), a program seeing its terminal type (vt100, xterm: its TERM, COLORTERM for the xterm only, and its Device Attributes answered), resizing telling the program, typing, copy and paste, Clear; ended with its form; not started without AutoStart; the Toolbox, icon, events and the designer's placeholder; pictures by the Kitty graphics protocol (RGB, RGBA, PNG, zlib, chunks, files and temporary files, queries, numbers, answers and errors and their quietness, placing part of a picture scaled, offset, at a z-index, moved by its placement id, the cursor after it), scrolling with the text and in a scroll region, inserted and deleted lines, erased, deleted every way (capitals freeing them), reset, the alternate screen's own, resizing, the pixel sizes asked, not on a vt100, a long one in bulk, the quota; iTerm2's inline images (its own size, the cursor after it, width and height in cells, pixels, percent and auto, within the box or stretched, no wider than the screen, the cursor kept, in parts, with ST, downloads and broken ones left out, not on a vt100, ReportCellSize, forgotten with their placements); sixel pictures (colors set and picked in RGB and HLS, `$`, `-`, repeats, the pixels' shape by P1 and the raster attributes, the VT340's colors, the foreground before a color, clear or the background, private or shared registers, nothing drawn, an 8-bit DCS; the cursor below or to the right, scrolling into the history, sixel display mode, the modes reported, XTSMGRAPHICS, not on a vt220, erased, reset); drawn over and under the text and under the cells' backgrounds, Clear; a sixel picture drawn; a program in the pseudo-terminal learning the pixel size and placing one. |
| `test_toolbar.py` | The Toolbar: its designer lines (`parse_button`); docking at the top as tall as its buttons, following the window, vertical when Left; the Buttons collection (Index and Key, separators, hidden and disabled buttons, tooltips, Add at an Index, errors, Remove, read-only placement); clicks on default, Check and ButtonGroup buttons (one pressed, a pressed one staying pressed), code setting Values (no ButtonClick, none pressed allowed); ImageList pictures by key and Index at its size, TextAlignment, an unknown Image; the form file round trip; the designer (docked at the top, the Properties window's Buttons); Toolbox, icon and constants. |
| `test_scrolling.py` | PictureBox ScrollBars: bars appearing for controls beyond the edges (both directions), ScrollLeft/ScrollTop and the Scroll event moving the contents, bars following moved, added and hidden controls, one direction only, turning it off, controls and Click on the empty area still working, a taller form shown inside scrolling, the designer not scrolling. |
| `test_label_text.py` | Label TextFormat: plain text hiding access keys, rich text and Markdown (really rendered), switching back; links firing LinkClick or opening the browser without a handler, only for formatted captions; the file and the designer (links off while designing, the multi-line Caption editor); the constants; access keys: `parse_mnemonic`, the key sequence per platform, the letter underlined, focusing the next control (skipping hidden, disabled and focusless ones, going round), none for a disabled label, a new Caption replacing the key, UseMnemonic False, && and rich text without keys, none while designing.; BackStyle (Opaque by default, filled with the container's color, a Frame's panel kept, Transparent ignoring BackColor, switching back, BackColor None). |
| `test_treeview.py` | The TreeView: reading outlines (outline images (a key, an Index or a file)); the Nodes collection (key, Index from 1, errors for unknown or duplicate keys); every relationship of `Add`; relatives, FullPath and PathSeparator; removing with children and clearing; node Text/Key/Tag/Bold/ForeColor/Image, EnsureVisible, sorting the tree and a node's children; code changes firing no events; NodeClick on clicks (also on the selected node) and keyboard moves, Expand/Collapse from the keyboard, HitTest; check boxes and NodeCheck; LineStyle, Indentation, Items; the form file; in the designer (Items building an expanded tree, the Properties button, a `Node` handler stub); the Toolbox button, icon and constants. |
| `test_values.py` | ProgressBar (Value kept inside Min..Max, also when they change; orientation; Click), Slider (Scroll while dragging and one Change after, Change for code and keys, LargeChange, tick styles and frequency, orientation), UpDown (steps, Max without Wrap, Change / UpClick / DownClick, a TextBox buddy shown and read back, typed numbers clamped or ignored, Increment, wrapping, a Label buddy's Caption, BuddyProperty, a missing buddy, SyncBuddy off, horizontal arrows); the form file round trip; creating them in the designer (arrows inactive there); Toolbox, icons, default events and constants. |
| `test_line.py` | The Line control: its widget following the points, drawing (color, Transparent, Visible, the scheme's text color by default), clicks going through it, ZIndex; the form file; in the designer: drawing from press to release and by a click, selecting near the line (not its box), dragging an end, the move cursor over an end, moving, arrow keys (no resizing), undo, pasting with an offset, the Properties rows, no event stub; the Toolbox button and icon. |
| `test_codebox.py` | The CodeBox: Python colors (and none), light and dark colors, the Highlight event (the State chain, HighlightText merging with the language's format, only during the event, Rehighlight) also for a control named after it was made; the gutter (line numbers on and off, LineMarker moving with its line, GutterClick from a mouse click, cleared by a new Text); hidden lines (the caret moved out, ShowLines, errors); protected lines (typing, Backspace, Delete, paste and cut refused with ProtectedEdit, Enter beside them allowed and moving them, code changing them, UnprotectLines, a beep without a handler); indenting (Python's auto-indent, keeping indentation, Tab to a tab stop, indenting and unindenting lines, UseTabs and TabWidth, AutoIndent off); the fixed-width font, WordWrap, tab stops, Locked, AcceptsTab, the colors; the editing API; Toolbox, icon and EVENT_ARGS. |
| `test_flexgrid.py` | The FlexGrid: parse_format_string; cells, headings, the corner, alignment by column, Clear, IndexErrors; Rows and Cols, FixedRows and FixedCols moving texts to and from the headings; the current cell and its events (LeaveCell, RowColChange, EnterCell), Text, RowSel/ColSel and SelChange, SelectionMode; the Cell... formats; AddItem, RemoveItem, RowData and every Sort mode (headings and RowData moving with their rows); ColWidth, RowHeight, TopRow, LeftCol and Scroll, MouseRow/MouseCol over cells and headings; not editable by default; text editing (BeforeEdit cancelling, ValidateEdit refusing, AfterEdit, typing to start); column and cell editors (none, list with column or cell choices); check boxes (from text, new rows, clicks only when Editable, the events, back to text); color (the dialog) and button cells (F2 and a click on the button); Toolbox, icon and EVENT_ARGS. |
| `test_dockpanel.py` | DockPanels: docked places (beside each other, a Fill PictureBox in the rest, controls in the content, moving to another edge); floating and docking (the window, the others taking its space, FloatMove and the Float... properties, Width not moving the window, back to its edge, where it last floated); closing by its button (Close cancelling, DockChange), Visible showing it again, also floating, and the window manager's close; the caption's float button and double-click, Floatable and Closable; dragging (the window following, the rubber band near an edge, docking there and outermost, staying floating in the middle); resizing by the inner edge with limits, Resizable; the floating window hiding and showing with the form; DockLayout (saved, everything changed, put back with the order; empty and invalid text); Floating from the start; Toolbox, icon, default event and EVENT_ARGS. |
| `test_shape.py` | The Shape: its defaults and no events; drawn pixels: the solid fill, the border inside its box, transparent fill and border, Opaque with BackColor; the round kinds leaving their corners, the circle and square centered, the oval filling its box; every hatched FillStyle drawing lines; Inside Solid and dashed borders; clicks going through; Toolbox (Shape before Line), icon and constants. |
| `test_usercontrol.py` | User controls: declarations (Property kinds and enum choices, Events with arguments, the default event, the merged Properties); at run time the designed size, property values through PropertyChanged, Initialize first, its own controls' events (control arrays too), RaiseEvent to the form and its cancel, Resize, the surface's Click, Surface, Controls, not in Forms; at design time PropertyChanged and Resize but not its controls' events; form files (find_form_kind, Surface properties round trip, a new one loading, imports, unknown values kept); the registry (built-in names refused); the project's user_controls (round trip, kind, the User Controls group, rename and remove); the IDE (Add User Control, its group and Toolbox button, its surface's properties and no frame, not on itself, its code window's UserControl events, reloading after an edit, placing it on a form with its import and Properties, an event stub, unregistered on close, loaded before forms on open); a broken user control reported; a program using one, run without the IDE. |
| `test_file_controls.py` | DriveListBox, DirListBox and FileListBox: `file_matches` patterns; the drives (`user_drives`, Drive set from any path, a missing one raising, Refresh); the DirListBox's Path, negative and positive `List` indexes, ListIndex and Click, ShowHidden, Refresh, no Change for the same folder, opening a folder by double-click (and the FileListBox following); the FileListBox's Pattern (case-insensitive, several, `*.*`), Hidden, FileName selecting, setting Pattern and Path, Refresh keeping the selection, no AddItem/RemoveItem/Clear, MultiSelect; clicking a file; Toolbox, icons and Toolbox order. |
| `test_text_editing.py` | The editing API of a multi-line TextBox and a RichTextBox (each test runs on both) and a single-line TextBox: LineCount, GetLine, GetLineFromChar, GetCharFromLine, GetColumnFromChar and IndexErrors; CurrentLine/CurrentColumn (keeping the column, clamping to the line) and SelChange (once per move, also for a selection); CaretLeft/Top/Height against the lines and GetCharFromPoint; FirstVisibleLine, ScrollToCaret and ScrollLeft; Undo, Redo, CanUndo, CanRedo, ClearUndo (no Change, the caret kept); AcceptsTab (and across a MultiLine rebuild). |
| `test_richtextbox.py` | The RichTextBox: text and selection (SelText across lines, replacing, clamping, Change and SelChange); formatting the selection (every Sel... property, None when mixed, the ForeColor where no color was set, None resetting the color); the format of what is typed next; paragraph alignment (one, mixed); AppendText (its own format, the selection kept, the view following the end only when it was there); Find (after the selection, match case, whole word, End, no highlight); GetLineFromChar; TextHTML, SelHTML, SaveFile/LoadFile by extension and FileType; MaxLength trimming; Locked against typing; pasting HTML without pictures or tables; ScrollBars and BorderStyle; Toolbox, icon and constants. |
| `test_list_items.py` | ListBox and ComboBox per-item properties: ItemData read and set (any value, None until set, `IndexError` past the end), values and fonts moving with their items when sorted or another is removed, VB's `ItemData(ListIndex)`, ItemBold, ItemItalic and ItemForeColor (and None again), ItemImage by Key or Index in the ImageList (an unknown one raising, following its changes, cleared), a picture file without one.; NewIndex (at an Index, sorted in, the mark removed, -1 after RemoveItem and Clear), TopIndex, Selected set and SelCount with MultiSelect, a Checkbox ListBox (ItemCheck from the user only, not for other item changes, new items checkable, back to Standard), a Simple Combo (its list shown, choosing an item, free text, ItemData, changing Style keeping everything without Click), DropDown. |
| `test_listview.py` | The ListView: its designer lines (`parse_column`, `parse_list_item`); ListItems (Index and Key, SubItems read and set, Add at an Index, Text, Key changes, errors, Remove, Clear); ColumnHeaders (labels, widths, alignments of existing and new cells, a new column, HideColumnHeaders); the four views keeping one selection, MultiSelect; sorting by the Text or a SubItem (as text), new and renamed items sorted in; ItemClick, HitTest and ColumnClick from the mouse, ItemCheck from the user but not code, Checkboxes off; Icons in the Icon view and SmallIcons in the others, unknown ones raising, an ImageList's changes; the form file round trip; the designer (the Properties window's Columns and Items); Toolbox, icon and constants. |
| `test_make.py` | Wheels: the package of the project's files and its launcher, METADATA (version, summary, author, requirements: VP6, not the standard library), console or GUI scripts, WHEEL and RECORD; requirements from the installed distributions (noting missing ones); a project's own `__main__.py`; the command line (a wheel by default, `--exe`, `--onefile` implying it); a wheel installed with pip run by its command and `python -m`; Project > Build Wheel. Making executables: the files that go in (not `dist`, `build`, caches or hidden files), the modules their code imports (not the project's own, nor relative imports; files with syntax errors skipped), the launcher, where the result goes on each system (apps, folders, one file, `.exe`), the PyInstaller command (console or windowed, one file, the project's or VP6's icon and none without Pillow, `--add-data` into the same folders with `os.pathsep`, hidden imports, VP6's folder and icons), the message without PyInstaller, `make()` with PyInstaller faked, File > Make Executable… with the process faked (success with the path, failure); with `VP6_TEST_MAKE=1` a real one-file executable made and run (its output, its data file, a module in a subfolder, its exit code). |
| `test_designer.py` | Creating controls, nesting in frames, mouse move with snapping and undo, rubber band, properties and rename, copy/paste, TabIndex renumbering (add, delete, paste, setting one, undo), z-order and Format, code-side undo reloading the designer, region protection in the editor, the workspace filling the window after maximize/restore. |
| `test_findreplace.py` | Match case and whole word; wrapping forwards and backwards; regular expressions with escapes across lines, groups in the find and replace text and per-line `^`/`$`; Find Next/Previous, Replace and Replace All (one undo step) in an editor; invalid patterns and replacements; positions after emoji; the designer region skipped when replacing and unfolded when found; the dialog; highlighting the first match as you type (growing matches, options, wrapping, not found, unfinished regexes, clearing); in the IDE: the Edit menu, Find from a designer opening the code window, Go to Line; in the whole project: Find Next and Previous from file to file and round (the designer region found too), the only match, not found; Find All (the list, going to a match, just the module); Replace All in every file (not designer regions, unsaved, one undo step each) and Replace going on to the next match; no project scope without a project. |
| `test_app_settings.py` | SaveSetting, GetSetting (its Default), GetAllSettings, DeleteSetting of a setting, a section or everything (in INI files of the test's own); App's title, version and descriptions from a project; the new project fields saved and loaded, and older projects' defaults; Command(); Screen.Fonts, FixedFonts and FontCount; the Project Properties dialog's version and text fields; PrevInstance in real programs (a second copy sees the first, a third after it ends doesn't); a project's arguments reaching Command() and `sys.argv` from the project file and from `vp6.runner`. |
| `test_command_line.py` | `--help`: the IDE's (its options and environment variables, exit 0; Qt's options left alone), the runner's (and no project: exit 2); a program's help text (name, version, description, usage, the project's ArgumentsHelp, the VP6 version), a message box without stdout; a real program showing its help from its project file and from `vp6.runner` without starting, and starting with other arguments; ArgumentsHelp saved and in the Project Properties dialog. |
| `test_categories_and_lock.py` | Property categories (VB's by name, a spec's own, a user control Property's, Misc otherwise); the Properties window's Categorized view (the tabs, headings in order, (Name) first in Misc, the same properties as Alphabetic, editing there, collapsing and expanding, kept across selections, opened by select_property, the heading's description, the view remembered); Lock Controls in the designer (no dragging, resizing or arrow keys; the Properties window and form resizing still work; unlocked again) and in the IDE (the Format menu's checkable item, enabled only for forms, remembered for the form when the project is opened again). |
| `test_objectbrowser.py` | VP6's classes (properties with types, descriptions and choices, events with their arguments, methods with signatures, run-time properties), objects (App's plain attributes), Globals, constants groups, colors and schemes; the project's forms (controls, methods, not InitializeComponent), modules (constants, variables, functions with their lines, classes, a syntax error) and user controls (their Properties and Events); search; the window (libraries, details, search results choosing a class and member); in the IDE: View > Object Browser (F2), all libraries, the project's, going to a member's code or a control in its designer, refreshed with new code. |
| `test_light_dark.py` | Form.DarkMode and Form_ColorSchemeChanged (not while loading, on ColorScheme changes, on the OS switching for System forms only), Screen.DarkMode; the watcher polling only while the scheme is forced; the IDE's scheme file (over the environment variable); designers refreshed by the watcher; the IDE writing its scheme file and rewriting it when its theme changes (removed when it closes); a real program's IDE form following the file live; a form shown in another looking like it. |
| `test_mdi.py` | MDI forms: children shown in the workspace (the MDI form loaded and shown first, around a docked pane), Activate and Deactivate, ActiveForm, Left/Top/Width/WindowState of a child, not modally; Load showing a child while AutoShowChildren; Arrange (tiles, cascade); the active child's menus replacing the MDI form's (its own bar hidden, never the system's), WindowList (the children, checked, activating, filled once); unloading a child (shown again later) and the MDI form (children first, vpFormMDIForm, cancelled by one); no MDIForm; the properties; ShowPopup (flags, not activating, at the owner's point, hidden in the background, a window again with Show); the form file (MDIForm, MDIForm_Load), the designer's DesignMDIForm and its properties, Project > Add MDI Form (one a project), MDIChild on forms, WindowList in the Menu Editor. |
| `test_scalemode.py` | ScaleMode: pixels by default; twips, points, inches, centimeters, millimeters, characters (boxes where they belong, CurrentX following); a User scale (Scale upwards, ScaleWidth and ScaleLeft... making one, back to pixels, errors, User from pixels); Circle's radius, TextWidth and PaintPicture in other units; ScaleX / ScaleY and Screen.TwipsPerPixel; the form's mouse X, Y in its scale; a PictureBox (inside its border, its mouse events); a Picture's and the Printer's scales (an inch square in a PDF). |
| `test_ide.py` | New projects (every template has Form1 and Module1 with `Main()`; the Standard EXE's `Main` really shows Form1; it opens in the designer), adding forms and modules, double-click creating handlers, completion, running a console project with stdin, traceback reporting, toolbar and layout reset, bottom-edge panels always tabbed (also after restoring a side-by-side layout), the theme toggle, ⌘/Ctrl+Enter, the Immediate Clear menu, `VP6_IDE_SCHEME` passing, the Project Explorer following the active window, project properties in the Properties window, the Properties panel following the Project panel's selection (or the active window when that panel is closed), module Names and all properties of unopened forms, renaming modules and forms from the Properties window (not to another form's name), a renamed Form1 still running, the IDE exiting without errors, Ctrl+C (SIGINT) quitting the IDE like File > Exit (also from the New Project dialog), `VP6_SETTINGS_DIR`, a form's window sized to show the whole form (or filling the MDI area when it can't, without maximizing), code and other windows kept inside the MDI area (also when reopened), and windows opened before the IDE is shown fitted when it is., the Project panel sorted by name within each group (not the project's order), its Name button cycling through A to Z with groups first, A to Z with groups among the files, and the same Z to A (keeping the selection, new files in their place), remembered; a group's (Name) in the Properties panel (any name but a sibling's, refused with a message; renamed in the project file, kept selected; its own description; switching groups refreshes the panel); Project panel groups (default Forms and Modules; New Group, Rename, Delete keeping the contents, Move to, drag and drop onto a group, a file or the project, a module in a group of forms, duplicate names refused with a message, new files in the selected group, saved in the project file without moving files on disk); the project item not collapsible (no arrow, keys and double-click), its groups still are; the +/- button expanding and collapsing every group (collapsed groups staying collapsed when the panel is refilled, another project starting open); the Project panel's Files view (folders first, hidden files on request, never the project file, `.git` or `__pycache__`, forms and modules working as in the Project view, no groups, other files not opened, following changes on disk, +/- on folders, the selection kept when switching, remembered); the Files view's changes on disk (new folders and subfolders, new modules in the selected folder, Move to and drag and drop with open windows and group places following, renaming files and folders, a renamed form's imports updated, names refused for forms and modules, deleting a folder to the Trash with its modules leaving the project, the project file protected); new folders and subfolders from Project > Add Folder… (switching to the Files view), the New Folder button (in the selected folder or the selected file's) and a file's context menu; moving several items at once in both views (Move N Items to from the context menu of one of them, dropping the selection onto a group, folder or file, a group or folder moving with what is in it, the moved items staying selected, failures in one message while the others move); the IDE's icon and every new project's (all templates), the project's Icon in the Properties panel; About VP6 (the logo, in the Help menu and, on macOS, the application menu). |
| `test_theme.py` | Built-in theme contrast (WCAG ratios), editor and System-mode following, persistence and reset of customizations, Immediate recoloring, the Options dialog. |
| `test_ide_theme.py` | Dark icon variants, disabled icons, the whole IDE following the theme, System forms in a forced IDE, frame styles and metrics, the grid toggle. |
| `test_appearance.py` | Forced schemes styling forms and controls, System/Light switching, BackColor overrides, project defaults (runner and `.vp6p` lookup), dialogs matching forms, the project scheme field, designer schemes, the IDE scheme. |
| `test_webbrowser.py` | A real WebBrowser (Chromium, headless): a file and its title, a link (BeforeNavigate, DocumentComplete), Busy and Progress, Back and Forward; BeforeNavigate keeping it on its page; new windows opened here or ignored (NewWindow); a name that doesn't resolve (NavigateError); LoadHTML, TitleChange, RunScript's result, StatusTextChange; GotFocus through the page's focus widget; the designer's placeholder, Toolbox, icon and events. |
| `test_webview.py` | The WebView with a stand-in view (`FakeView`): navigating to a file, a file relative to the form, a domain (https), an error, back and forward, Refresh, Stop, URL set at run time, the events; LoadHTML and RunScript with and without a callback; the designer's placeholder; a clear error without Qt WebView; Toolbox, icon and events. A real web view in a process of its own with VP6_TEST_WEBVIEW=1. |
| `test_commondialog.py` | The CommonDialog: parse_filter; invisible at run time, in the Toolbox; the Open dialog (title, filters, the starting filter and folder, the file chosen, FileTitle, FileNames, FilterIndex, multi-select), Save As (the overwrite prompt only with the flag, DefaultExt), cancelling (False, FileName kept; CancelError raising DialogCancelled 32755), Color, Font, Printer (copies, page range) and Help; in the designer an icon without a size of its own. |
| `test_container.py` | Container set at run time: to a Frame, PictureBox, DockPanel and back to the form, Left and Top kept, events still handled; a hidden control staying hidden, ZIndex in the new container; option buttons joining the new group; a container moving with its controls; a docked control leaving the form's layout; the tab order (Tab into a control moved into a frame); errors (not a container, another form's, into itself or something on it, a Menu, None). |
| `test_drawing.py` | The graphics methods, checked with Point: lines (ForeColor, the end point not covered, from the current point, Step, DrawWidth, a dotted and an invisible DrawStyle), boxes (B, BF, FillStyle solid and hatched, Inside Solid), circles (fill, edge, an ellipse, an arc not filled, a pie from -0.0, Step), points (a round wide one, outside: -1), Print and the current point, TextWidth/TextHeight and the Font, Cls; AutoRedraw and Paint (Paint on show and Refresh, none with AutoRedraw), the drawing kept when the form shrinks and grows, under the controls; a PictureBox (inside its border, Cls keeping the Picture, its Paint), a form with a menu bar in the window, a user control's Paint; the properties, events and form file; no Paint in the designer, and the properties in its Properties window. |
| `test_docs.py` | The docs keep up with the code: every source file in the source reference, every test file in the test table, every public API name in `api.md` (key-code ranges count), the generated `api.md` tables up to date with a section per control, every property with a description, and every relative link and anchor in the Markdown files resolving. |
| `test_outline.py` | The Outline replacing the Properties panel (in the same place) while a code window is active and giving it back for designers, View > Outline Window and F4, a closed panel staying closed, closing the last window, the default layout; the outline of the Kitchen Sink's Form1; kinds, lines and skipped statements; syntax errors; sorting (order, name, type, both directions, members too); the panel's sort buttons, icons, tooltips, live updates and syntax-error handling; in the IDE: following the Project panel or active window, clicking items goes to the line (unfolding the designer region); the items at a line (a method inside its class, from the first decorator, blank lines and imports at none), and the Outline highlighting the item at the code window's cursor (in a body, none on an import, after re-sorting and edits, another code window's cursor, none for a designer). |
| `test_packaging.py` | The package as published: `pyproject.toml`'s version is `vp6.__version__`, the MIT license and its file, the author without an email, the dependencies and the `make` extra; every data file in `vp6/` (not a module of a package) matched by the package data, so the wheel has it; the `vp6`, `vp6-run` and `vp6-make` commands; the source distribution's docs and tests; the release workflow's version check and trusted publishing. |
| `test_output.py` | Output capture: copy to the original descriptor, replay of output captured before attaching, split UTF-8 characters, restoring on `stop()`; real Python, C-level and Qt output in a separate process; the Output window's Select All / Copy / Clear menu; the real IDE `main()` showing its own output in the Output window. |
| `test_interrupt.py` | Ctrl+C (a real SIGINT) in VP6 programs run as separate processes: a project's forms close and `Form_Unload` runs; a form run on its own; `Form_Unload` cancelling the first Ctrl+C; an open `MsgBox` closed first; a console program at `input()` exiting quietly with code 130; programs that don't create the application (the IDE, the tests) keep their own Ctrl+C. |
| `test_kitchen_sink.py` | The Kitchen Sink covers every control type, default event, public API name, color scheme and use of control arrays; its regions are canonical; the project is created with all its forms; the designer opens every form; the explorer window (the docked panes, following the window, the Splitter, hiding the navigation pane), the introduction's links and the index (a section shows its first page), every page opening once and replacing the one before; each page's demo (text and the Text page's access keys, the Docking panels page (Float and Dock, Close cancelled, a closed panel shown again, the layout saved and restored, the grid following its panel), the FlexGrid page (sorting by a clicked heading both ways, RowColChange with RowData, editing the property sheet with each kind of editor, ValidateEdit refusing a Width), the CodeBox page (TODO marked by Highlight, breakpoints and folding from the gutter, typing refused in the protected region, which moves down with an edit above it, the options), the Terminal page (the shell started, the demo's colors, line drawing, title and pictures (Kitty's, iTerm2's and sixel, side by side), the true color gradient and COLORTERM, the Ligatures check box, the Font box (the fixed-width fonts, the grid following the font, back to the system's), Restart, a vt220 chosen restarting the shell as one (no COLORTERM), Clear, the shell's end); the Running programs page (a program answering, its error output, exit code, Kill, a missing one, Shell stubbed); the MDI and popup forms page (the Notes window and its notes, their menus, tiling, closing; suggestions in a popup taken with the keys); the Web pages page (a stand-in WebView: navigating, an error, Back and Forward, RunScript, Refresh; the WebBrowser chosen instead, its BeforeNavigate, NewWindow and StatusTextChange), the Dialogs page's CommonDialog (Open, Save As writing the sample, Color and its cancelling, Font, Print), the Mouse page's pointers, fruit dragged into the basket and out, and drops from other programs, the Buttons page's cmdHop moving into the Basket frame and out (Container), the Keyboard page's Validate (the focus kept, Help regardless), ActiveControl and SendKeys (typed, upper-cased, Enter on the Default button), the Dialogs page's default instance (Result, closed by code or by its close button, the same instance loaded again, its icon), the Your own controls page (ctlRating's stars, a click's Change, Hover, Value from code, Locked, Max and Value kept in range), the Editing text page (line and column, Undo/Redo, Indent, Go to line, Tab, completions under the caret taken by Enter or a click and closed by Esc, the word under the mouse), the RichTextBox page (formatting buttons following the selection, Find with its options, saving and loading HTML, the word count, the colored log), buttons, lists, scroll bars, sliders, progress bars and spinners, the Lists page's ItemData, pictures and fonts, Checkbox ListBox, Simple Combo and DropDown, the Buttons page's Graphical buttons (a picture button, a toggle CheckBox, toggle OptionButtons), the ListView page (sorting by a column, views, check boxes, adding and removing), the TabStrip page, the files page (the three file system controls linked, the pattern, the chosen picture, hidden files), the window's Toolbar (pages, the navigation pane and the color schemes, in step with the View menu), pictures (with opaque and transparent labels on one), z-order, lines and shapes, the TreeView, the Timer running only while visible, the layout, scrolling, popping out and back, dialogs with the modal form, color schemes with the View menu, keys, the mouse, control arrays, menus and bookmarks, the popup menu (right-click, the bold default, under a button), globals); closing unloads the pages. |
| `test_mouse.py` | MousePointer (a control's own pointer given back, a custom MouseIcon, a form's), Screen.MousePointer; which controls have the mouse members and events; VB drag and drop: DragOver's enter, over and leave, DragDrop, refusing in DragOver, dropping on a user control, Drag starting (its data and picture, its DragIcon), ending where it is and cancelling, DragMode Automatic (no MouseDown or Click); drops from other programs (OLEDragOver, OLEDragDrop, refusing, a TextBox's own drop with OLEDropMode None, a form's), the DataObject. |
| `test_popupmenu.py` | Form.PopupMenu: the chosen item returned after its Click (and the menu's own Click first), the bold DefaultMenu only for that time, None when closed without a choice, nothing recorded outside PopupMenu; left, right and center alignment at X, Y, the mouse's place for what is left out; not a Menu, a menu without items, a visible menu-bar menu; at design time. |
| `test_picture.py` | Picture objects: one in memory (the graphics methods on it, transparent and filled, Cls, Image a copy, no unknown properties), LoadPicture (empty, a missing file, not a picture), SavePicture (by extension, BMP without one, a file's picture, an empty one failing); Pictures as a PictureBox's, Image's, button's Picture, the Icon, a MouseIcon, an ImageList's picture, clearing with LoadPicture(); a PictureBox's Image and PaintPicture (at its size, scaled part, a file, an empty one), a form's Image; a form's background Picture (a file relative to its folder, under the drawing, a Picture, cleared; the form file); the clipboard (pictures, files' pictures, text, RTF, files); a dropped picture in a DataObject; the exports. |
| `test_printer.py` | The Printer, to PDF files (rendered back with QtPdf): the page's size in VP6's pixels and its margins, a box, a filled circle, a Picture and text in points where they belong; pages, NewPage first, Orientation from the next page, A4; KillDoc printing nothing; a document for the printer redirected (conftest) and printed when the program ends; no printer (RuntimeError); no Cls, Point, Image or unknown properties; Printers and choosing DeviceName; ShowPrinter's choices with and without PrinterDefault; the exports. |
| `test_project_files.py` | Save Project As: where the copy goes (an empty or new folder, else one named after the file), what it holds (the project's files, unsaved texts, the project file renamed with its own code, the project's fields with the new name; not dist, caches or hidden files), the original untouched, errors (a bad name, the project's own folder or one in it, a folder that isn't empty), File > Save Project As in the IDE working on the copy; renaming and deleting a module's file from the Project view's menu (out of the project, to the Trash). |
| `test_process.py` | The Process control: running a program and talking with it (WorkingDirectory, UTF-8 both ways, standard output and error, Write and WriteLine, its exit code, not started twice, no writing when not running), CloseInput, Kill (-1), Terminate, WaitForExit, a command line with quotes, a program that can't be started (Error), no CommandLine, `split_command`; ended with its form; Shell (a program run on its own, a missing one, none); the Toolbox (before Menu), its icon, events and designer placement. |
| `test_project.py` | The project script: hash-bang, validity, executable bit, round trip, keeping user code, never executing on load, invalid files, running via hash-bang / python / without VP6, modules in subfolders importing each other by name; groups: the default Forms and Modules (also for older files without groups), nesting groups holding anything, the top level, rename, delete (contents move up), refused moves and names, new files placed by kind or chosen group, remove and rename of files, repairing an inconsistent tree, saving and loading; the icon (none by default, nothing copied; its own files, saved and loaded, one file as a string, none in older projects) and a program showing its project's icon, or the VP6 icon without one. |
