# VP6 features

**Version:** 0.3.5
**Date:** 2026-09-29

## Programming model (the `vp6` library)

- Ctrl+C in the terminal that started a VP6 program (`./Project.vp6p`, `python Form1.py`, `vp6-run`) closes its forms like their close buttons would: an open `MsgBox` or modal form closes first, each `Form_Unload` runs and can cancel (a repeated Ctrl+C while it asks is ignored), and the program ends when the last form is gone
- Ctrl+C in a console program (e.g. at `input()`) ends it quietly with exit code 130 instead of a `KeyboardInterrupt` traceback

## IDE

- The IDE's Ctrl+C handling now shares its implementation with programs (`vp6.app.InterruptHandler`)

---

**Version:** 0.3.4
**Date:** 2026-09-29

## IDE

- Outline window, hidden by default (View > Outline Window): the structure of the file selected in the Project panel, or of the active code or designer window when the Project panel is closed. It lists constants and variables at file scope, classes with their members (methods, attributes, nested classes), functions, and `*global code*` for top-level code; the designer-generated code isn't expanded
- Outline items have icons for their type: constant, variable, class, function, method, attribute, top-level code
- Outline sort buttons: file order, name or type; clicking the active one switches between ascending and descending
- Opened from the menu, the Outline window is placed under the Properties panel
- Clicking an Outline item opens the code window at that line (unfolding the designer region if needed)
- The Outline follows edits as you type, and keeps the last outline while the code has a syntax error

---

**Version:** 0.3.3
**Date:** 2026-09-29

## IDE

- Panels at the bottom edge (the bottom dock area) are always tabs: one tab per panel with its title, one panel body shown. This holds when panels are dragged there, placed side by side, shown, hidden, or restored from a saved layout. The left and right edges keep their panels stacked.

---

**Version:** 0.3.2
**Date:** 2026-09-29

## IDE

- Output window, hidden by default (View > Output Window, tabbed with the Immediate window): shows everything the IDE process writes to stdout and stderr, including libraries such as Qt, captured at the file-descriptor level; output still appears in the terminal too, and output from startup is included
- Output window context menu: Select All, Copy and Clear
- The Immediate and Output windows keep following new output only while scrolled to the end, so earlier output can be read while more arrives
- `VP6_NO_OUTPUT_CAPTURE` environment variable turns the capture off

---

**Version:** 0.3.1
**Date:** 2026-09-29

## IDE

- Ctrl+C in the terminal that started VP6 quits it like File > Exit / Quit VP6: unsaved changes are offered for saving (Cancel keeps VP6 open), and an open dialog such as New Project is closed first
- `VP6_SETTINGS_DIR` environment variable: keep the IDE's settings in an INI file in that folder

---

**Version:** 0.3.0
**Date:** 2026-09-29

## IDE

- Modules have a (Name) property in the Properties panel; renaming a module renames its file, its project entry and the `import`s of it in the other project files
- Forms whose designer isn't open show their (Name) in the Properties panel and can be renamed there
- With the Project panel open, the Properties panel shows what's selected in it (the project, a form, a module) and nothing when a folder or nothing is selected
- With the Project panel closed, the Properties panel shows the form or module of the active designer or code window
- Renaming a form (in the designer or the Properties panel) also renames references to it in the other project files, e.g. Module1's `from Form1 import Form1` and `run(Form1)`

## Fixes

- A renamed Form1 no longer breaks new Standard EXE projects, whose Module1 imports and runs Form1

---

**Version:** 0.2.1
**Date:** 2026-09-29

## Documentation and tooling

- `tools/apidocs.py` generates the property, event and constant tables in `docs/api.md` from the code (`python tools/apidocs.py`; `--check` reports stale docs), so the API reference can't drift
- Documentation test (`tests/test_docs.py`): fails when a source file, test file or public API name isn't documented, the generated tables are out of date, or a link in the Markdown files is broken

## IDE

- Every property now has a description, shown in the Properties window's description pane and in the API reference

---

**Version:** 0.2.0
**Date:** 2026-09-29

## Controls

- `ZIndex` property on every control visible at run time (all but Timer): the higher value is drawn on top where controls overlap in the same container; equal values keep creation order
- `ZIndex` can be changed while the program runs, with immediate effect
- `ZOrder(0)` / `ZOrder(1)` bring to front / send to back by setting `ZIndex`

## IDE

- `ZIndex` is editable in the Properties window and saved in the form file
- Format > Order > Bring to Front / Send to Back set `ZIndex`
- Clicking in the designer selects the control that is visibly on top

## Kitchen Sink

- Z-order demo: two overlapping labels, a Swap Z-order button, and click-to-front with `ZOrder(0)`

---

**Version:** 0.1.0
**Date:** 2026-09-29

## Programming model (the `vp6` library)

- Visual Basic 6 style GUI programming in Python: `from vp6 import *`
- Usable without the IDE; every form runs on its own with `python Form1.py`
- Forms are `Form` subclasses; controls are created in `InitializeComponent` (generated by the designer) or in code at run time
- Assigning a control to a form attribute names it (`self.Command1 = ...`)
- Event handlers are methods named `Object_Event` (`Command1_Click`, `Form_Load`); they're looked up when the event fires, so they can be attached at run time
- Handlers may declare fewer parameters than VB passes
- VB `ByRef` arguments emulated with return values:
  - `KeyPress` returning `0` swallows the key; another code replaces it
  - `Form_KeyDown`/`KeyUp` with `KeyPreview` returning `0` cancel the key
  - `Form_Unload` returning `True` cancels closing
- VB-style run-time error box (End / Continue) with the traceback sent to stderr
- Misspelled properties raise `AttributeError` (VB error 438) instead of silently creating attributes
- Pixel units; a form's `Width`/`Height` are its client area
- `Sub Main` programs: a `Main()` function in a module as the startup object
- Console programs using `print()` / `input()`

## Forms

- Properties:
  - window: `Caption`, `Width`, `Height`, `Left`, `Top`, `StartUpPosition`, `BorderStyle` (6 styles, including tool windows), `WindowState`, `ControlBox`, `MinButton`, `MaxButton`;
  - behavior and appearance: `KeyPreview`, `BackColor`, `ForeColor`, font properties, `Enabled`, `Tag`, `ColorScheme`
- Run-time members: `Me`, `Name`, `Controls`, `ScaleWidth`, `ScaleHeight`, `Visible`
- Methods: `Show`, `Show(vpModal, OwnerForm)`, `Hide`, `Load`, `Unload`, `Move`, `Refresh`, `SetFocus`, `Form.Run()`
- Events: `Initialize`, `Load`, `Unload`, `Activate`, `Deactivate`, `Resize`, `Click`, `DblClick`, `MouseDown`, `MouseMove`, `MouseUp`, `KeyDown`, `KeyPress`, `KeyUp`
- Default button (Enter) and Cancel button (Esc)
- Tab order from `TabIndex`
- Modal forms
- The `Forms` collection, and `Load` / `Unload` / `run` functions

## Controls

- 12 intrinsic controls:
  - **PictureBox:** container; `Picture`, `Stretch`, `AutoSize`, `BorderStyle`, `Cls`
  - **Label:** `Alignment`, `AutoSize`, `WordWrap`, `BorderStyle`, `&` mnemonics
  - **TextBox:** `MultiLine`, `ScrollBars`, `PasswordChar`, `MaxLength`, `Locked`, `Alignment`, `SelStart` / `SelLength` / `SelText`
  - **Frame:** container; option buttons in it form their own group
  - **CommandButton:** `Default`, `Cancel`, `Value = True` clicks it
  - **CheckBox:** `Value` unchecked, checked or grayed
  - **OptionButton:** mutually exclusive per container
  - **ComboBox:** dropdown combo or dropdown list, `List`, `Sorted`, `ListIndex`, `AddItem`, `RemoveItem`, `Clear`
  - **ListBox:** `List`, `Sorted`, `MultiSelect`, `ListIndex`, `Text`, `Selected()`, `AddItem`, `RemoveItem`, `Clear`, `ListCount`
  - **HScrollBar / VScrollBar:** `Min`, `Max`, `Value`, `SmallChange`, `LargeChange`, `Change` and `Scroll` events
  - **Timer:** `Interval`, `Enabled`, `Timer` event; invisible at run time
- Common properties: `Left`, `Top`, `Width`, `Height`, `Enabled`, `Visible`, `TabIndex`, `ToolTipText`, `Tag`, `BackColor`, `ForeColor`, `FontName`, `FontSize`, `FontBold`, `FontItalic`, `FontUnderline`
- Common methods: `SetFocus`, `Move`, `Refresh`, `ZOrder`
- Events: `Click`, `DblClick`, `Change`, `Scroll`, `Timer`, `GotFocus`, `LostFocus`, `MouseDown`, `MouseMove`, `MouseUp` (with button, shift and coordinates), `KeyDown`, `KeyUp` (VB key codes), `KeyPress`
- Nested containers (controls in Frames and PictureBoxes)

## Functions, objects and constants

- Dialogs:
  - `MsgBox` with VB button sets, icons, default buttons and results;
  - `InputBox`;
  - both follow the color scheme of the form they appear over.
- Program control: `DoEvents`, `End`, `Beep`
- Global objects: `App` (`Title`, `Path`, `EXEName`), `Screen` (`Width`, `Height`, `ActiveForm`), `Clipboard` (`GetText`, `SetText`, `Clear`), `Debug.Print`
- Colors: VB-style BGR integers, `RGB()`, `QBColor()`, color constants, `"#RRGGBB"` strings accepted
- VB constants with a `vp` prefix: MsgBox, key codes, mouse, shift, alignment, border styles, window states, start-up positions, strings

## Light and dark color schemes

- Per-form `ColorScheme`: Project Default, System, Light, Dark, IDE
- Per-project color scheme inherited by forms (System, Light, Dark, Follow the IDE)
- System forms follow the OS appearance live
- Light and Dark forms are forced with Fusion and a full palette, including their controls and message boxes
- The scheme can be changed while the program runs
- The IDE's current appearance is passed to programs started from it

## Projects and files

- **Form files** are plain Python: a designer-owned region inside the class, read with `ast` (never executed) and regenerated on changes; user code outside it is untouched
- **Project files (`.vp6p`)** are executable Python launcher scripts:
  - a shell/Python hash-bang; the interpreter can be chosen with `VP6_PYTHON`;
  - `chmod +x` on save;
  - a clear message when VP6 is missing;
  - project data in an IDE-maintained `PROJECT` region; user code kept.
- **Running outside the IDE:** `./Project.vp6p`, `python3 Project.vp6p`, the `vp6-run` command, `python -m vp6.runner`
- **New project templates:**
  - Standard EXE (Sub Main shows Form1);
  - Console Application (Sub Main with `print`/`input`);
  - Kitchen Sink (a demo of every control and feature).
- Every new project gets `Form1` and `Module1` (with `Main()` and an `if __name__` block)
- Project properties: name, type, startup object, color scheme

## IDE

### Main window

- VB6-like MDI layout:
  - Toolbox, Project Explorer, Properties window and Immediate window as dock panels;
  - MDI or tabbed documents;
  - window cascade and tile.
- New Project dialog with New / Existing / Recent tabs; recent projects menu
- Standard toolbar with a light/dark switch; View > Toolbars and View > Reset Window Layout
- The title bar shows `[design]` / `[run]`
- Window layout and settings remembered between sessions
- Add Form, Add Module, Add File, Remove File, Project Properties
- Prompt to save changes when closing

### Form designer

- Real runtime controls in design mode: what you see is what runs
- Drawing controls from the Toolbox; double-click a tool to add a control in the middle
- Selection, multi-selection, rubber band, Ctrl+drag selection inside containers
- Moving and resizing with 8-pixel grid snapping (Alt to skip), 8 resize handles, form resize handles
- Keyboard: arrows move (Ctrl for 1 px), Shift+arrows resize, Esc selects the parent, Delete removes
- Cut, copy and paste (with renaming), delete (with children), undo and redo
- Format menu: align (lefts, centers, rights, tops, middles, bottoms, grid), make same size, center in form, bring to front, send to back
- Right-click context menu
- Double-click a control to write its default event handler
- Renaming a control also renames its handlers and `self.X` references in the code
- Window frame painted to match the OS (macOS, Windows 11, GNOME) or classic VB6, reflecting `BorderStyle`, `ControlBox`, `MinButton` and `MaxButton`
- Optional grid dots
- The form shows its own color scheme, independent of the IDE
- The workspace fills the window when resized, maximized or restored

### Code window

- Object and Procedure dropdowns that jump to or create event handlers with VB's parameters
- Python syntax highlighting
- Line numbers and current-line highlight
- Auto-indent, Tab/Shift+Tab indent, smart backspace, Ctrl+/ comment toggle
- Completion for `self.` and `self.Control.` members, VP6 names, keywords and words in the file
- The designer region is folded and protected from edits
- Undo in the code window can also undo designer changes

### Properties window

- Object selector, alphabetical property grid, description pane
- Editors by type: text, number, true/false, lists of values, colors (Default / Choose… / Palette), item lists, fonts, files
- Editing several selected controls at once
- Selecting the project in the Project Explorer shows and edits the project's properties

### Project Explorer

- Forms and modules tree with the startup object in bold
- View Code / View Object, a context menu, set start-up form
- Follows the active window

### Running programs

- F5 or ⌘/Ctrl+Enter to start, End to stop, Shift+F5 to restart
- Programs run in a separate process; everything is saved first
- The Immediate window shows output and `Debug.Print`, with errors in red
- Input line for console programs
- Double-click a traceback line to jump to the code
- Clear command in the Immediate window's context menu

### Themes and appearance

- The whole IDE follows the OS light/dark appearance, or is forced light or dark by the chosen theme
- Built-in Light (VB6-like) and Dark editor themes
- Every editor color and syntax style is customizable (color, bold, italic), with a live preview
- Custom themes; built-in themes can be reset
- Choice of theme for light and for dark OS appearance
- Code font and size
- Icons drawn in code with light and dark variants

## Quality and documentation

- Headless test suite (pytest, 136 tests) covering the runtime, file formats, designer, IDE, themes and the Kitchen Sink
- Tests are isolated from the user's real IDE settings
- The Kitchen Sink coverage tests fail when a new control or API name isn't demonstrated
- Documentation in `docs/`: architecture, source reference, API reference, development guide
- Samples: Calculator (GUI) and GuessNumber (console)
