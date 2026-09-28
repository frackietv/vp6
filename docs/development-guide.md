# VP6 development guide

How to set up a development environment, the rules the code base follows,
and step-by-step recipes for extending the VP6 runtime and IDE. Read
[architecture.md](architecture.md) first for the big picture;
[source-reference.md](source-reference.md) says where everything lives.

## 1. Setting up

```bash
cd VP6
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # editable install: vp6, vp6-run, pytest, build
.venv/bin/pip install -e ".[dev,make]" # ...and PyInstaller, for vp6-make

.venv/bin/vp6                          # start the IDE (or: .venv/bin/python -m vp6.ide)
.venv/bin/vp6 samples/Calculator/Calculator.vp6p
.venv/bin/python -m pytest -q          # run the tests (headless, a few seconds)
```

Requirements: Python ≥ 3.10 and PySide6 ≥ 6.6. Some features use newer Qt
APIs: `QStyleHints.setColorScheme` needs Qt 6.8, and older versions fall back
to Fusion + palette.

Tips:

* Start the IDE from a terminal while developing. Python exceptions raised in
  Qt slots are printed there.
* Run a project without the IDE:
  `VP6_PYTHON=.venv/bin/python ./samples/Calculator/Calculator.vp6p`.
* The `vp6` command runs from the editable install, so code changes take
  effect on the next start. There's no build step.

## 2. Ground rules

These keep VP6 coherent. Please keep them when adding code.

1. **The runtime doesn't import the IDE.** `vp6/*.py` must work without
   `vp6/ide`. If the IDE needs to plug into the runtime, add a small hook in
   the runtime (e.g. `appearance.ide_scheme_provider`,
   `Form._control_widget_changed`) and set it from the IDE.
2. **The IDE never executes user code.** Form and project files are read with
   `ast` / `ast.literal_eval` (`formfile.parse`, `project.parse`). Programs
   run in a separate process started by F5.
3. **The text is the source of truth.** Designer changes go through
   `FormDocument.set_form_def`, which regenerates the designer region inside
   the document's `QTextDocument`. Don't write form files behind the
   document's back.
4. **Declare, don't hard-code.** Properties are `PropSpec`s, events go in
   `Events` + `EVENT_ARGS`, controls in `CONTROL_TYPES`, icons in
   `icons._DRAWERS`, theme roles in `UI_ROLES` / `SYNTAX_ROLES`. The UI is
   built from these tables.
5. **VB naming for the public API; Python naming inside.**
   * The public API uses PascalCase properties and methods (`Caption`,
     `AddItem`), handlers named `Object_Event`, and constants prefixed `vp`.
   * Everything internal is `_private` and snake_case.
   * `Control.__setattr__` treats unknown capitalized attributes as typos, so
     internal attributes **must** start with `_` or be lower case.
6. **Settings go through `theme.ide_settings()`.** Never construct
   `QSettings("VP6", "VP6 IDE")` directly: the tests redirect settings to a
   temporary INI file, and a direct construction would write to the
   developer's real preferences.
7. **Style.** Lines are at most 99 characters. Start modules with
   `from __future__ import annotations`. Give every module a docstring saying
   what it's for, and comment the *why*, not the *what*. Match the
   surrounding code.
8. **Test what you add** (§6). The suite must stay headless and fast.
9. **Keep the Kitchen Sink up to date** (§5.11). Every new control, event or
   API function must be demonstrated in the Kitchen Sink template.
   `tests/test_kitchen_sink.py` fails when it isn't.
10. **Keep the documentation up to date** (§5.12). Run
    `python tools/apidocs.py` after changing properties, events or constants.
    `tests/test_docs.py` fails when the docs fall behind.

## 3. How a change flows through the system

The IDE mostly works through a few paths. Knowing them makes most features
easy to place.

| You want to… | Path |
|---|---|
| change what a control *can do* | `vp6/controls.py`: its `Properties`, `Events`, `_apply_*` / `_read_*` hooks, methods |
| change what the designer *writes* | `vp6/formfile.py` (generation and parsing) + `FormDesigner` operations |
| add something the user *does in the designer* | `FormDesigner` method → `_snapshot()` … `_commit(before)`, called from `_Overlay`, a menu (`MainWindow._designer_call`) or the context menu |
| add an IDE command | `MainWindow._create_actions` / `_create_menus` / `_create_toolbar` |
| react to light/dark or setting changes | connect to `theme_manager().changed` and re-apply |
| change how programs start | `vp6/runner.py` (inside the program) and `MainWindow.run_project` (the IDE side) |

---

## 4. Recipes: runtime

### 4.1 Add a property to an existing control

Example: a `Label.BackStyle` (0 - Transparent, 1 - Opaque).

1. **Declare it** in the control's `Properties` in `vp6/controls.py`.
   Position matters: properties are applied in this order when a control is
   created, so put it after anything it depends on.

   ```python
   P("BackStyle", "enum", 0, enum_choices("Transparent", "Opaque"),
     description="Whether the background is painted"),
   ```

2. **Apply it** with a hook named `_apply_<Name>`:

   ```python
   def _apply_BackStyle(self, v):
       self._widget.setAutoFillBackground(bool(v))
   ```

   If the live value can change without going through the property (user
   input, for example), also add `_read_<Name>()` returning it from the
   widget.

3. **Guard for design mode** if the property shouldn't take effect in the
   designer (see `Control._apply_Visible`) or if the widget can be `None`
   (`Timer` at run time).

4. **That's all for the IDE.** The Properties window, the designer region
   (defaults are omitted automatically) and completion all pick it up from the
   spec. Give it a `description`: the Properties window shows it, and so does
   the API reference after you run `python tools/apidocs.py`.

5. **Test it** in `tests/test_runtime.py`: set it, check the widget. If
   generation matters, add a `tests/test_formfile.py` round trip.

Kinds and their editors: `str`, `int` (line edit), `text` (line edit + …
dialog), `bool` / `enum` (combo box), `color` (swatch + menu), `list`
(dialog), `font` (family combo), `file` (line edit + browse).

### 4.2 Add a new property kind

For example a `"point"` kind:

1. `vp6/_props.py` `normalize()`: coerce values to the new kind.
2. `vp6/formfile.py` `format_value()`: how to write it into the region. The
   result must be a literal that `ast.literal_eval` can read back.
3. `vp6/ide/properties.py` `PropertiesWindow._editor()`: create its editor
   and call `self._commit(spec.name, value)` when edited.
4. Tests for all three.

### 4.3 Add an event

1. If the event name is new, add it and its VB parameter list to
   `EVENT_ARGS` in `vp6/controls.py`, e.g. `"ItemCheck": "Item"`. The code
   window uses this to generate stubs.
2. Add it to the control's `Events` tuple, so it appears in the code window's
   Procedure combo.
3. Fire it:
   * from a Qt signal in `_connect_signals`:
     `self._widget.itemChanged.connect(lambda item: self._fire("ItemCheck", self._widget.row(item)))`;
   * or from a Qt event in `_on_qt_event` (override it, call `super()`, and
     return `True` only to swallow the event).
4. If VB passes an argument `ByRef`, emulate it with the handler's return
   value, as `_on_key_press` does for `KeyPress`.

`_fire` returns the handler's return value (or `None` when there is no
handler), and already goes through `call_handler` (argument trimming and
error reporting).

### 4.4 Add a new control

Example: a `ProgressBar`.

1. **Write the class** in `vp6/controls.py`:

   ```python
   class ProgressBar(Control):
       TypeName = "ProgressBar"
       DefaultSize = (121, 25)
       Events = ("Click", "MouseDown", "MouseMove", "MouseUp")
       _synthesize_click = True          # QProgressBar has no clicked signal
       _qss_type = "QProgressBar"        # for BackColor/ForeColor style sheets
       Properties = (
           *_geometry(*DefaultSize),
           P("Min", "int", 0), P("Max", "int", 100), P("Value", "int", 0),
           *_COLORS, *_COMMON,
       )

       def _create_widget(self, parent):
           return QProgressBar(parent)

       def _apply_Min(self, v):
           self._widget.setMinimum(v)

       def _apply_Max(self, v):
           self._widget.setMaximum(v)

       def _read_Value(self):
           return self._widget.value()

       def _apply_Value(self, v):
           self._widget.setValue(v)
   ```

   * `DefaultEvent` defaults to `Click`; set it if another event is the
     natural one.
   * A container sets `IsContainer = True`, uses `_container_palette` for
     colors, and may override `_container_widget()` if children belong in a
     sub-widget.
   * If the widget is a scroll area, return its viewport too from
     `_event_targets()` so mouse events arrive.
   * Keep the widget as `self._widget`. Use `_rebuild_widget()` if a property
     requires a different widget class.

2. **Register it:**
   * add it to `CONTROL_TYPES` at the end of `controls.py` (the order is the
     Toolbox order);
   * export it from `vp6/__init__.py` (the import and `__all__`).
3. **Designer name prefix:** add it to `NAME_PREFIX` in `vp6/ide/designer.py`
   (`"ProgressBar": "Progress"` → `Progress1`, `Progress2`, …).
4. **Toolbox icon:** add a drawer to `vp6/ide/icons.py` and register it in
   `_DRAWERS` under the exact `TypeName` (see §5.8).
5. **Kitchen Sink:** demonstrate it on a Kitchen Sink page (a new page for
   a new kind of control) and handle its default event (§5.11). `test_kitchen_sink.py` fails until you do.
   **API reference:** add its section to `docs/api.md` and run
   `python tools/apidocs.py` (§5.12). `test_docs.py` fails until you do.
6. **Nothing else.** The Toolbox, the form-file parser and generator, the
   Properties window, completion and the code window's object list all come
   from `CONTROL_TYPES` and the class metadata.
7. **Tests:**
   * runtime behaviour in `test_runtime.py`;
   * `test_designer.py`: create it with `designer.create_control("ProgressBar",
     …)` and check the generated region;
   * add its name to the icon tests in `test_ide_theme.py`.

### 4.5 Add a function, object or constant

* **A constant:** add it to `vp6/constants.py` with the `vp` prefix. It is
  exported automatically (`__all__` collects every `vp*` name) and
  highlighted in the editor.
* **A function or object:** put it in the most fitting runtime module
  (`app.py` for program-level services, `dialogs.py` for dialogs), then import
  it in `vp6/__init__.py` and add it to `__all__`. Everything in
  `vp6.__all__` is highlighted as a VP6 name and offered by completion.
* Anything that needs Qt must call `ensure_app()` first. A program may call
  it before any form exists.

---

## 5. Recipes: IDE

### 5.1 Add a designer operation

Every designer change follows the snapshot/commit pattern, which gives undo
and region regeneration for free:

```python
def space_evenly(self, horizontal: bool) -> None:
    """Format > Horizontal/Vertical Spacing > Make Equal."""
    if len(self.selection) < 3:
        return
    key = (lambda r: r.x()) if horizontal else (lambda r: r.y())
    rects = sorted(self._selected_rects(), key=lambda nr: key(nr[1]))
    first, last = key(rects[0][1]), key(rects[-1][1])
    step = (last - first) / (len(rects) - 1)
    for i, (name, rect) in enumerate(rects):
        if horizontal:
            rect.moveLeft(round(first + i * step))
        else:
            rect.moveTop(round(first + i * step))
        self.controls[name]._widget.setGeometry(rect)
    self.commit_geometry(self.selection)      # snapshot + form_def + region + undo
```

* **Geometry changes:** move the widgets, then call `commit_geometry(names)`.
* **Property changes:** call `set_property(prop, value)`. It applies to the
  selection, validates, commits and returns an error message or `None`.
* **Structural changes** (adding, removing, reordering, reparenting):

  ```python
  before = self._snapshot()
  ...change self.form_def.controls and the live controls
     (_instantiate, widget.deleteLater, …)...
  self._commit(before)
  ```

  Keep **parents before children** in `form_def.controls`, which the parser
  requires. The list order is creation order: it decides stacking only among
  controls with equal `ZIndex`.
* Then expose the operation:
  * through a menu, via `MainWindow._designer_call("space_evenly", True)`
    (§5.2);
  * through the right-click menu, in `FormDesigner.show_context_menu`;
  * through a key, in `_Overlay.keyPressEvent`.

### 5.2 Add an IDE command (menu, toolbar, shortcut)

In `vp6/ide/mainwindow.py`:

1. **Create the action** in `_create_actions` with the helper:

   ```python
   self.act_space_h = self._action("Make &Equal", lambda: self._designer_call(
       "space_evenly", True), "Ctrl+Shift+H", icon=None, tip="Space controls evenly")
   ```

   * The shortcut is a `QKeySequence` string; `Ctrl` means ⌘ on macOS.
   * `icon` is a name from `icons._DRAWERS`. Actions created with an icon
     name are redrawn automatically when light/dark changes.
   * Several shortcuts: `action.setShortcuts([...])` (see `act_run`).

2. **Add it** to a menu in `_create_menus` and/or to the toolbar in
   `_create_toolbar`.
3. **Enabling:** if the command depends on state (a project is open, a
   program is running), set `setEnabled` in `_update_actions()`. It runs
   after every state change.
4. **Routing:**
   * `_designer_call(method, *args)` targets the active designer window;
   * `_edit(op)` shows how to route to whichever window has the focus;
   * `self._active_widget()` returns the active MDI window's widget.

Shortcuts only fire in the active window. Text editors take precedence for
standard editing keys (Qt's `ShortcutOverride`), so the code editor keeps
Cut/Copy/Paste/Delete.

### 5.3 Add a dock panel

1. Write the panel widget, e.g. in `vp6/ide/panels.py`. Emit signals for
   anything the main window must act on; don't reach into `MainWindow`.
2. In `MainWindow.__init__`:
   * create it and `self.xxx_dock = self._dock("Title", widget, area,
     "objectname")`. The object name is how Qt saves the layout; make it
     unique and stable.
   * connect its signals.
3. Add the dock to `_default_layout()`, so View > Reset Window Layout
   restores it.
4. Add a View menu action that calls `self._show_dock(self.xxx_dock)`.
5. If it shows code-like content, theme it: connect
   `theme_manager().changed` to an `apply_theme()` method, as
   `ImmediateWindow` does.

### 5.4 Add a code editor feature

* **Keys** are handled in `CodeEditor.keyPressEvent`, in this order:
  1. the completion popup;
  2. the designer-region guard (`_edit_allowed`);
  3. undo/redo;
  4. Enter, Tab, Backspace, Ctrl+/ and Ctrl+Space;
  5. the default handling.

  **Any new editing key must respect `_edit_allowed()`**, otherwise it could
  corrupt the designer region. Call `self._reject_edit()` to refuse an edit.
* **Completion** comes from `complete(context, document)`. `context` is the
  dotted text before the word being typed, e.g. `"self.Text1."`. Add cases
  there.
* **Syntax colors:** add a rule to `PythonHighlighter.rules` producing a
  style name, and add that style as a syntax role (§5.5).
* **Code window combos:** `CodeWindow._objects()` lists objects and their
  events; stub insertion is in `goto_event` / `_class_end_line`.

### 5.5 Add a theme color or syntax style

In `vp6/ide/theme.py`:

1. Add `(key, "Label")` to `UI_ROLES` (surface colors) or `SYNTAX_ROLES`
   (text styles).
2. Add a value for the key to **both** `BUILTIN_THEMES`: a color string in
   `colors`, or a `TextStyle` in `syntax`. Pick colors with enough contrast:
   `tests/test_theme.py::test_builtin_themes_are_readable` checks text
   against the backgrounds.
3. Use it: `theme.colors["key"]` in `CodeEditor.apply_theme` /
   `ImmediateWindow.apply_theme`, or emit the style name from a highlighter
   rule.

Nothing else is needed:

* the Options dialog lists every role automatically;
* `Theme.from_dict` fills in the new role for custom themes saved before it
  existed.

### 5.6 Add an IDE setting

1. Add a field with a default to `EditorSettings` in `vp6/ide/theme.py`.
2. Read it in `ThemeManager._load` and write it in `ThemeManager.apply`,
   under a new key (`section/name`). Remember that QSettings may return
   strings; convert types explicitly, as `show_grid` does.
3. Add a control to `OptionsDialog`:
   * set it from `self.state` in `_reload()`;
   * update `self.state` in its handler, guarded by `self._loading`.

   The change is applied on OK or Apply.
4. Consumers read `theme_manager().state.<field>` and connect to
   `theme_manager().changed` to react. For example `FormDesigner` redraws on
   `frame_style` and `show_grid` changes in `_on_ide_theme_changed`.
5. Document the key in [architecture.md §7](architecture.md#7-settings-and-environment).

### 5.7 Add a designer window frame style

In `vp6/ide/chrome.py`:

1. Add a constant and a label to `FRAME_STYLES`. It appears in Options
   automatically.
2. Add its `(title height, tool-window title height, border)` to the table
   in `metrics()`.
3. Write a painter `_mystyle(p, frame, client, info)`. `frame` is the whole
   window rectangle and `client` is the form area; don't paint over `client`.
   Use `info.title_dark` for the title bar, and `info.can_minimize` /
   `info.can_maximize` / `info.control_box` for the buttons.
4. Register it in the dispatch dict in `paint()`. If it's the native style
   of a platform, map that platform in `resolve()`.
5. Add it to the parametrized test `test_every_frame_paints`.

### 5.8 Add an icon

In `vp6/ide/icons.py`:

1. Write a drawer `def _myicon(p):` that paints in a 24 × 24 coordinate
   space.
2. Take outline and fill colors from the palette `C` (`C.ink`, `C.face`,
   `C.paper`, `C.blue`, `C.button_top`, `C.button_bottom`), not hard-coded
   dark colors. That's what makes the dark variant readable. Fixed accent
   colors (green Run, red Stop) are fine.
3. Register it in `_DRAWERS` under its name, which is the `TypeName` for a
   control's Toolbox icon.
4. Use it with `icons.icon("MyIcon")`, or by name in `MainWindow._action`.
   Cache, HiDPI and disabled variants are handled for you.
5. Add the name to `test_dark_icons_have_light_ink` in
   `tests/test_ide_theme.py` if it has outlines.

### 5.9 Add a field to the project file

1. `vp6/project.py`:
   * add the field (with a default) to the `Project` dataclass;
   * append its name to `_FIELDS`, which sets the order it's written in;
   * add a comment to `_COMMENTS` if helpful.

   Projects without the field load with the default: `Project.load` only
   takes known keys.
2. Edit it in `ProjectPropertiesDialog` (`vp6/ide/dialogs.py`): add a widget,
   then read it in `apply(project)`.
3. Use it where it matters: `vp6/runner.py` inside the running program, or
   `MainWindow` in the IDE.
4. Test the round trip in `tests/test_project.py`.

### 5.10 Change the form file format

Rarely needed, and it affects every existing form, so be deliberate.

* The parser (`formfile.parse_region_body`) and the generator
  (`generate_region`, `_props_to_args`, `format_value`, `_wrap_call`) must
  stay inverse to each other. `test_replace_region_keeps_user_code` and
  `test_long_lines_are_wrapped` check this.
* The region markers are `REGION_START` / `_START_RE` in `formfile.py`. The
  code editor's folding and protection rely on `_START_RE` / `_END_RE` too.
* Update the samples (`samples/*/`) and the templates (`new_form_source`,
  `options.PREVIEW`, and the Kitchen Sink forms, whose regions must stay
  canonical, see §5.11).

### 5.11 Keep the Kitchen Sink up to date

The **Kitchen Sink** project template (New Project > Kitchen Sink)
demonstrates every VP6 control and feature. It is a living example for users,
so **every change that adds or changes something users can use must update
it**.

**Where it lives:**

* The sources are in `vp6/ide/templates/kitchensink/`:
  * `Form1.py` is the explorer window: a TreeView index of the topics on the
    left, and a content pane in which the chosen topic's page is shown;
  * each topic is a page, a form of its own (`pgText.py`, `pgLists.py`, …),
    listed in `Form1.PAGES` and in the index (the TreeView's `Items`);
  * `frmDialog.py` is a modal dialog with its own Dark color scheme;
  * `Module1.py` holds `Main()`, which shows Form1.
* `vp6/ide/kitchensink.py` copies them into a new project, draws the
  PictureBox image (`vp6.png`) and returns the `Project`.

**What `tests/test_kitchen_sink.py` enforces:**

| Check | Fails when |
|---|---|
| `test_every_control_type_is_used` | a type in `CONTROL_TYPES` isn't on any Kitchen Sink form |
| `test_every_control_type_handles_its_default_event` | no control of a type has a handler for its `DefaultEvent` |
| `test_every_public_api_name_is_used` | a non-constant name in `vp6.__all__` (a function, class or object) isn't referenced |
| `test_every_color_scheme_is_demonstrated` | a `vpScheme*` value isn't used |
| `test_designer_regions_are_canonical` | a form's designer region isn't exactly what the designer would write |
| the page tests (`test_text_page`, …) | a page raises errors or its demo stops working |

**How to update it:**

1. Create a Kitchen Sink project in the IDE and open the page the feature
   belongs on, or add a new form for a new topic (Project > Add Form, sized
   like the others, 640 × 440).
2. Add your control or feature with the designer and write the handler code
   in the code window, like any VP6 user would. Keep the handlers short and
   self-explanatory, and show what happened in a Label on the page.
3. A new page: add its node to the index (Form1's TreeView `Items`, with its
   key after `|`), import it in Form1 and add it to `PAGES` under that key.
4. Copy the changed files back into `vp6/ide/templates/kitchensink/`.
   Because you edited them with the designer, their regions are canonical.
5. If you added a file, list it in `kitchensink.FORMS` / `MODULES`.
6. Run `pytest tests/test_kitchen_sink.py`, and add a test for the page's
   demo (`_page(sink, key)` shows it).

New constants don't need to appear individually, since there are too many to
require. Do demonstrate a new *group* of constants that changes behavior, as
the color schemes are.

### 5.12 Keep the documentation up to date

`tests/test_docs.py` fails when the docs fall behind the code. The fix
depends on what it reports:

| Failure | Fix |
|---|---|
| a source file isn't in the source reference | add a section for it to `docs/source-reference.md` (it must mention the path, e.g. `` `vp6/ide/newthing.py` ``) |
| a test file isn't in the test table | add a row to the test table in `docs/source-reference.md` |
| a public API name isn't in the API reference | document it in `docs/api.md`, usually in §5 (functions and objects) |
| `docs/api.md is out of date` | run `python tools/apidocs.py` |
| a control has no generated section | add `### Name`, a sentence about it, and an empty `<!-- BEGIN GENERATED: control Name -->` / `<!-- END GENERATED -->` pair to `docs/api.md` §4, then run the generator |
| a broken link | fix the link, or the heading it points to (anchors are GitHub-style) |

**How `tools/apidocs.py` works.** It rewrites only the blocks between the
`BEGIN GENERATED` / `END GENERATED` markers, from:

* each class's `Properties`, `Events`, `DefaultEvent` and `DefaultSize`;
* `EVENT_ARGS`;
* the constants modules.

Everything outside the markers is hand-written and stays as it is.

**Where each kind of change goes:**

* A property's notes in the tables are its `description` and enum choices,
  so improve them in the code, not in the Markdown.
* The run-time members and the prose around each control are yours to edit.
* A new section of constants in `vp6/constants.py` (`# --- Title ---`)
  becomes a row automatically.

---

## 6. Testing

```bash
.venv/bin/python -m pytest -q                        # everything
.venv/bin/python -m pytest -q tests/test_designer.py -k rubber
```

`tests/conftest.py` provides:

| Fixture / helper | Purpose |
|---|---|
| `qapp` | the shared `QApplication` (session scope) |
| `_isolated_settings` (autouse) | redirects `QSettings` to an INI file in `tmp_path`, **asserts** that `ide_settings()` is isolated, and resets the theme manager before and after each test |
| `_fail_on_errors_in_qt_callbacks` (autouse) | fails the test if Python code called by Qt raised: an event handler override (`mouseMoveEvent`...) or a slot run from the event loop. PySide only prints those ("Error calling Python override of ...") through `sys.excepthook`, so a test would otherwise pass |
| `wait_for(predicate, timeout_ms)` | processes events until a condition holds (PySide lacks `QTest.qWaitFor`) |

The environment is set to `QT_QPA_PLATFORM=offscreen` (no display) and
`VP6_NO_ERROR_DIALOG=1` (run-time errors don't open a blocking box).

Code that can open a modal box (`QMessageBox.question` and the like) blocks
a test forever. Replace it in the test, e.g. `designer.ask_create_array =
lambda name: False` before pasting a copy of an existing control.

Typical patterns:

* **A designer on a temporary form:**

  ```python
  path = tmp_path / "Form1.py"
  path.write_text(formfile.new_form_source("Form1"))
  d = FormDesigner(FormDocument(str(path)), str(tmp_path))
  d.create_control("CommandButton", None, None, None)
  assert "self.Command1 = CommandButton(self" in d.document.text
  ```

* **Mouse input on the designer:** send `QTest.mousePress`, `mouseMove` and
  `mouseRelease` to `d.overlay`, using canvas coordinates
  (`d.form_canvas_rect().topLeft() + QPoint(x, y)`).
* **The whole IDE:** create `MainWindow()`, then
  `open_project(create_project(str(tmp_path), "Demo", "exe"))`.
* **Running programs:** `window.run_project()`, then
  `wait_for(lambda: window.process is None, 15000)`, then check
  `window.immediate.output.toPlainText()`. For the project script alone, use
  `subprocess.run` with `PYTHONPATH` pointing at the repo (see
  `tests/test_project.py`).

Offscreen caveats:

* **Keyboard shortcuts** fire only in the active window. Call
  `QTest.qWaitForWindowActive(window)` before sending them.
* **`setColorScheme`** isn't honored offscreen, so IDE-appearance tests take
  the Fusion fallback path. Write assertions that accept either path (see
  `test_whole_ide_follows_explicit_theme`).
* **Modal dialogs and menus block.** Test the code that *builds* them (e.g.
  `ImmediateWindow._context_menu()`), or close them from a
  `QTimer.singleShot` callback (see `test_msgbox_returns_vp_constants`).
* **Style names.** The offscreen platform's default style is Fusion. To check
  that a widget was *forced* to Fusion, test `Qt.WA_SetStyle` as well as the
  style name.

**Looking at the UI from a script.** Any widget can be rendered offscreen and
saved:

```python
w = MainWindow(); w.resize(1200, 760); w.show()
w.open_project("samples/Calculator/Calculator.vp6p")
w.grab().save("ide.png")
```

Set `QSettings.setDefaultFormat(QSettings.IniFormat)` and a temporary
`setPath` first, so the script doesn't touch your real IDE settings.

---

## 7. Pitfalls

* **Spec order is application order.** A property whose `_apply_` relies on
  another must come after it in `Properties`. For example `TextBox.MultiLine`
  is before `Text`, `ComboBox.Style` is before `Text`, and `Image.Stretch` is
  before `Picture`.
* **Timer has no widget at run time.** Code in `Control` that touches
  `self._widget` must allow `None`.
* **Design mode.** Runtime behavior that shouldn't happen in the designer
  (firing events, hiding invisible controls, starting timers, window flags)
  must check `self._design_mode`.
* **PySide object ownership.** A Qt object that outlives the widgets using it
  (the shared Fusion style, for example) must have a Qt parent. Otherwise
  PySide may delete it with the first widget that used it.
* **Deferred calls and signals must not outlive their object.** Use
  `QTimer.singleShot(0, self, self.method)`, with `self` as the context
  object: Qt cancels the call if `self` is deleted first. Without it, a
  code window closed right after an edit crashed the process later. Connect
  long-lived signals (the theme manager, `QGuiApplication.styleHints()`) to
  bound methods, not lambdas: PySide disconnects bound methods when their
  object is deleted.
* **No reference cycles through Qt objects.** Don't store a bound method or
  a lambda that captures a widget on the widget itself (e.g.
  `designer.callback = lambda: designer...`): capture what it needs instead,
  or make it a method.
* **Control arrays share a name.** In the designer, identify controls by
  their key (`ControlDef.key`, `FormDesigner.key_of`), not their name:
  `cmdDigit(0)` and `cmdDigit(1)` are both named `cmdDigit`.
* **Styles don't propagate to children.** Use `appearance.style_tree`, and
  remember that controls created later need `Form._style_widget` (already
  called by `Control._build_widget`).
* **Palettes and style sheets.** Style sheets cascade to children, so
  containers use palettes. When setting a palette, set only the roles you
  mean to change (start from `QPalette()`), or later scheme changes won't
  reach the widget.
* **Widgets with style sheets don't follow application palette changes.**
  Rebuild them on theme changes. For example `MainWindow._on_theme_changed`
  refreshes the Properties window.
* **The designer region is protected in the editor.** Code that changes it
  must go through `FormDocument.set_form_def` or `replace_text`, never
  through the editor's key handling.
* **Real preferences.** Construct settings only through `ide_settings()`. The
  test guard fails loudly if isolation breaks.

## 8. Releasing

VP6 is published on PyPI as `vp6` (`pip install vp6`), under the MIT license
(`LICENSE`). A release is a version in `pyproject.toml` and
`vp6/__init__.py` (`tests/test_packaging.py` checks they agree), with its
entry at the top of `FEATURES.md`.

**Check the distributions locally first:**

```bash
.venv/bin/python -m build                    # dist/vp6-<version>.tar.gz and ...whl
.venv/bin/twine check --strict dist/*
python3 -m venv /tmp/vp6-try                 # install the wheel somewhere clean
/tmp/vp6-try/bin/pip install dist/vp6-*.whl
/tmp/vp6-try/bin/vp6                         # the IDE, from the wheel
```

* The **wheel** has the `vp6` package with its data files (pictures, the
  Kitchen Sink templates: `[tool.setuptools.package-data]`, which
  `tests/test_packaging.py` checks covers every one), the license and the
  `vp6`, `vp6-run` and `vp6-make` commands. The **source distribution** also
  has the docs, the samples and the tests (`MANIFEST.in`).
* PyPI shows `README.md` as the project's page; its relative links (to
  `docs/`, `FEATURES.md`, `BACKLOG.md`) only work in the repository. Once the
  repository is public, add its address under `[project.urls]` and make those
  links absolute.

**Publishing** is done by GitHub Actions (`.github/workflows/publish.yml`)
with PyPI's *trusted publishing*, so no password or token is stored anywhere:

1. Once: on pypi.org (logged in), *Your account > Publishing > Add a new
   pending publisher*: project name `vp6`, the repository's owner and name,
   workflow `publish.yml`, environment `pypi`. (Test it first on
   test.pypi.org the same way if you like.) In the GitHub repository's
   settings, add an environment named `pypi`.
2. For each release: commit the new version, then tag and push it:

   ```bash
   git tag v0.4.0 && git push origin v0.4.0
   ```

   The workflow checks the tag is `v` + the version in `pyproject.toml`,
   builds and checks the distributions, and uploads them. A version can be
   uploaded only once: a mistake needs a new version.

Without GitHub, upload from your machine with an API token from pypi.org
(*Account settings > API tokens*): `.venv/bin/twine upload dist/*` (it asks
for the token; the user name is `__token__`).
