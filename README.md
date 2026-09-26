# VP6

Visual Basic 6 style programming for Python: an IDE where you draw forms,
set properties, double-click a control to write its event handler and press
**F5** to run, plus the `vp6` framework that makes the resulting code work
(also usable without the IDE).

Built on PySide6 (Qt).

Detailed documentation is in [docs/](docs/README.md):
[architecture](docs/architecture.md), [source reference](docs/source-reference.md),
[API reference](docs/api.md) and [development guide](docs/development-guide.md).

## Getting started

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/vp6                       # start the IDE (or: python -m vp6.ide)
.venv/bin/vp6 samples/Calculator/Calculator.vp6p
```

The IDE opens with a VB-style **New Project** dialog. Every new project has
`Form1` and `Module1` and starts in `Sub Main`, the `Main()` function in
`Module1`:

* *Standard EXE:* `Main()` shows `Form1` with `run(Form1)`.
* *Console Application:* `Main()` talks through `print()` / `input()`.
* *Kitchen Sink:* a demo project showing every VP6 control and feature. Open
  it to see how things work, and copy code out of it.

## The IDE

| VB6                         | VP6                                                         |
|-----------------------------|--------------------------------------------------------------|
| Toolbox                     | Pointer, PictureBox, Label, TextBox, Frame, CommandButton, CheckBox, OptionButton, ComboBox, ListBox, HScrollBar, VScrollBar, Timer |
| Form designer               | Draw controls, move/resize with 8px grid snapping (hold Alt to skip it), rubber-band select, Ctrl+drag inside a Frame, arrows nudge, Shift+arrows resize, cut/copy/paste, undo/redo |
| Properties window (F4)      | Object combo, alphabetical grid, enum/color/list/font/file editors, multi-select editing, description pane; select the project in the Project Explorer to edit its Name, Type, StartupObject and ColorScheme |
| Code window (F7)            | Object and Procedure dropdowns that create handler stubs, Python highlighting, auto-indent, `self.` / `self.Control.` completion, Ctrl+/ comments |
| Project Explorer (Ctrl+R)   | Forms and modules, View Code / View Object, set startup form; follows the active window |
| Immediate window (Ctrl+G)   | Program output and `Debug.Print`, stdin for console apps, double-click a traceback line to jump to it |
| Format menu                 | Align, Make Same Size, Center in Form, Bring to Front (Ctrl+J), Send to Back (Ctrl+K) |
| Run (F5 or Cmd+Enter / Ctrl+Enter, Shift+F5, End) | Saves everything and runs the project in a separate process; the title shows `[design]` / `[run]` |
| Toolbar and layout          | Sun/moon switch at the right end of the toolbar toggles light/dark; View > Toolbars shows a hidden toolbar; View > Reset Window Layout restores all panels |

### Themes: light and dark

The IDE uses **System** by default: the whole IDE (windows, menus, docks,
icons) and the code editor follow the OS appearance live. Use **View >
Editor Theme** to pick a theme directly. Choosing *Light*, *Dark* or a
custom theme switches the entire IDE to that theme's light or dark
appearance, whatever the OS setting. On platforms that can't switch an
app's appearance, VP6 uses Qt's Fusion style with a light or dark palette.
In the designer, a form set to *System* still shows the OS appearance, since
that's how it will run. In **Tools > Options** you can:

* choose which theme is used for light and for dark system appearance,
* change any color (background, text, selection, current line, line
  numbers, designer region, Immediate output) and each syntax element's
  color, bold and italic, with a live preview,
* create your own themes (**New…**), delete them, or **Reset** a built-in
  theme to its defaults,
* choose the code font and size,
* choose the window frame the form designer draws around forms. *Automatic*
  matches your OS; the others are macOS, Windows 11, GNOME or classic VB6,
  handy when you design on one OS for another. The frame follows the form's
  `BorderStyle`, `ControlBox`, `MinButton` and `MaxButton`, like the real
  window. You can also hide the grid (controls still snap to it).

### Light and dark forms

Each project has a **Color Scheme** (Project > Project Properties):
*System* (the default), *Light*, *Dark* or *Follow the IDE*. Every form inherits it unless its
own `ColorScheme` property overrides it:

| `ColorScheme`                 | Result                                                  |
|-------------------------------|---------------------------------------------------------|
| `0 - Project Default` (default) | The project's color scheme                            |
| `1 - System`                  | Native look, follows the OS light/dark appearance live   |
| `2 - Light` / `3 - Dark`      | Always light / always dark, whatever the OS setting     |
| `4 - IDE`                     | Follows the VP6 IDE's light/dark setting (e.g. the toolbar switch): live in the designer; when run from the IDE, the IDE's setting at launch; when run on its own, System |

Forced light and dark use Qt's Fusion style with a fixed palette, because
native styles such as macOS ignore per-window palettes. `MsgBox` and
`InputBox` take the scheme of the form they appear over. `BackColor` and
`ForeColor` still override the scheme's colors.

The form designer shows the form (controls and title bar) in the form's own
scheme, exactly as it will run. The workspace around the form follows the
IDE's light/dark mode. When a form runs on its own (`python Form1.py`),
"Project Default" is read from a `.vp6p` file in the same folder, if there
is one.

## Files

A project is a folder with a `Name.vp6p` project file listing forms, modules
and the startup object (a form or `Sub Main`). The project file is also an
executable launcher script, so it starts the program by itself:

```bash
./Calculator.vp6p                                  # uses the first python3 on PATH
VP6_PYTHON=/path/to/venv/bin/python ./Calculator.vp6p
python3 Calculator.vp6p                            # also works (e.g. on Windows)
```

It begins with `#!/bin/sh` and the line
`"exec" "${VP6_PYTHON:-python3}" "$0" "$@"`. The shell runs that line to
re-execute the file with Python, and to Python it is just a string. If that
Python doesn't have VP6 installed, the script says so and how to fix it.
The project data is a `PROJECT = {...}` dict in a region the IDE maintains
and reads with `ast`, so opening a project never runs it. Code you add
outside the region is kept when the IDE saves, and saving keeps the file
executable. F5 in the IDE runs this same script.

A **form** is one Python file. The designer owns a clearly marked region
inside the class; everything else is yours:

```python
from vp6 import *


class Form1(Form):
    # region VP6 Designer - generated by the form designer, do not edit
    def InitializeComponent(self):
        self.Caption = 'Hello'
        self.Width = 480
        self.Height = 360
        self.Command1 = CommandButton(self, Caption='&Say Hello', Left=16, Top=16,
                                      Width=104, Height=32)
    # endregion

    def Command1_Click(self):
        MsgBox("Hello, world!", vpInformation)


if __name__ == "__main__":
    run(Form1)
```

The IDE parses the region with `ast` (your code is never executed while
designing) and rewrites only that region. In the code window it is folded
and read-only. Forms run on their own too: `python Form1.py`.

## The framework

```python
from vp6 import *
```

* **Events** are methods named `Object_Event`: `Command1_Click`,
  `Text1_Change`, `Form_Load`, `List1_DblClick`, `Timer1_Timer`,
  `Picture1_MouseDown(self, Button, Shift, X, Y)`,
  `Text1_KeyPress(self, KeyAscii)`, ... Handlers may declare fewer
  parameters than VB passes.
* **Return values replace ByRef arguments:** return `0` from `KeyPress` to
  swallow a key (or another char code to replace it); return `True` from
  `Form_Unload` to cancel closing.
* **Properties** have VB names and pixel units: `Caption`, `Text`, `Left`,
  `Top`, `Width`, `Height`, `Enabled`, `Visible`, `BackColor`, `ForeColor`,
  `FontName`, `FontSize`, `FontBold`, `TabIndex`, `ToolTipText`, `Tag`,
  `Value`, `List`, `ListIndex`, `ListCount`, `Interval`, ... A misspelled
  property raises instead of silently creating an attribute.
* **Form**: `Show(vpModal)`, `Hide()`, `Unload()`, `Controls`, `Me`,
  `KeyPreview`, `BorderStyle`, `StartUpPosition`, `WindowState`; a Default
  button reacts to Enter and a Cancel button to Esc.
* **Globals**: `MsgBox`, `InputBox`, `RGB`, `QBColor`, `DoEvents`, `End`,
  `Beep`, `Load`, `Unload`, `Forms`, `App`, `Screen`, `Clipboard`,
  `Debug.Print`, and the `vp*` constants (`vpYesNo`, `vpYes`, `vpKeyReturn`,
  `vpRed`, `vpChecked`, `vpModal`, ...).
* Colors are VB-style BGR integers (`RGB(255, 0, 0) == vpRed == 0x0000FF`).
  Color properties also accept `"#RRGGBB"`.
* Unhandled exceptions in event handlers show a VB-style *Run-time error*
  box with **End** / **Continue**, and the traceback goes to the Immediate
  window.

## Samples

* `samples/Calculator`: a calculator form with keyboard support. Its button
  handlers are assigned in `Form_Load`, like a VB control array.
* `samples/GuessNumber`: a console application (`Sub Main`).

## Tests

```bash
.venv/bin/python -m pytest
```

The tests run headless (`QT_QPA_PLATFORM=offscreen`). They cover the
runtime, the form file format, designer operations and the IDE, including
running a console project through the Immediate window.

## Features and backlog

[FEATURES.md](FEATURES.md) lists everything VP6 implements.
[BACKLOG.md](BACKLOG.md) lists what isn't implemented yet. The biggest gaps are:

* control arrays;
* menus (the Menu Editor);
* debugging (breakpoints, stepping, evaluating code in the Immediate window);
* graphics methods (`Line`, `Circle`, `PSet`);
* more controls (Shape, Line, Image, DriveListBox, common controls);
* MDI forms;
* packaging an app as an executable.
