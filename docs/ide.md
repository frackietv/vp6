# VP6 documentation

VP6 is a VB6-style IDE and GUI framework for Python, vibe-coded using Claude,
and built on PySide6 (Qt).

## The IDE

| VB6                         | VP6                                                         |
|-----------------------------|--------------------------------------------------------------|
| Toolbox                     | Pointer, PictureBox, Label, TextBox, Frame, CommandButton, CheckBox, OptionButton, ComboBox, ListBox, HScrollBar, VScrollBar, Timer, DriveListBox, DirListBox, FileListBox, Shape, Line, Image, TreeView, Splitter, ProgressBar, Slider, UpDown, StatusBar, TabStrip, ImageList, CommonDialog, Toolbar, ListView, RichTextBox, CodeBox, FlexGrid, WebView, WebBrowser, Process, Terminal, DockPanel, MarkdownBox, Data, SpinBox, DTPicker, MonthView, Dial, LCDNumber, FontComboBox, HotKey, CommandLink, ToolButton, ButtonBox, ToolBox, PageFrame, ScrollPanel, ColumnView, DBGrid, GraphicsView, Chart, SvgImage, MediaPlayer, PdfViewer, OpenGLView, QuickView, UndoView; resizable (snapping to whole columns of icons); the buttons along its top switch to a list view (each tool's icon and name, top to bottom) and group the tools by category (Common, Input, Buttons, Containers, Graphics, Lists, Text, Files, Media, System, Web, Data, then the project's User Controls), each under a heading; a third button orders the tools: their own order, by name A to Z, or Z to A (when grouped, the categories by name too, and the tools in each); all remembered |
| Form designer               | Draw controls, move/resize with 8px grid snapping (hold Alt to skip it), rubber-band select, Ctrl+drag inside a Frame, arrows nudge, Shift+arrows resize, cut/copy/paste, undo/redo; `TabIndex` values are renumbered automatically when controls are added, deleted or given a new `TabIndex` |
| Properties window (F4)      | Object combo (control array elements as `cmdDigit(0)`), VB's Alphabetic and Categorized tabs (`(Name)` and `Index` first, then an alphabetical grid; or under Appearance, Behavior, Font, List, Misc, Position and Text headings that collapse and expand), enum/color/list/font/file editors, multi-select editing, description pane; select a form in the Project Explorer to edit its properties and controls without opening it, or the project to edit its Name, Type, StartupObject, ColorScheme and Icon |
| Object Browser (F2)         | View > Object Browser, as VB's: VP6's classes (controls, Form, Picture...), objects (App, Screen, Printer...), functions and constants, and the project's forms, user controls and modules with their controls, methods, properties, events and variables; a library list, search, each member's declaration and description; double-click a project member to go to its code (or a control to its form) |
| Code window (F7)            | Object and Procedure dropdowns that create handler stubs, Python highlighting, auto-indent, `self.` / `self.Control.` completion, Ctrl+/ comments; Edit > Find (Ctrl+F; the first match is highlighted as you type), Find Next/Previous (F3 / Shift+F3), Replace (Ctrl+H, or ⌥⌘F on macOS), with match case, whole word and Python regular expressions (escapes such as `\n`, groups such as `\1` in find and replace), in the current module or the whole project (VB's Search: Find Next goes from file to file, Replace All replaces in every file, Find All lists the matches); Edit > Go to Line (Ctrl+L) |
| Project Explorer (Ctrl+R)   | Forms and modules organized in groups and subgroups (Forms and Modules to begin with; New Group, Rename, Delete, Move to, or drag and drop, several items at once; not folders on disk; +/- expands or collapses them all; Rename File… and Delete File… for a form's or module's file, its imports following a new name), or a Files view of the project's folder as it is on disk (hidden files on request; new folders and subfolders with its New Folder button or Project > Add Folder…, rename, delete, and move files and folders by drag and drop), sorted by name (the Name button cycles through A to Z with the groups first, A to Z with the groups among the files, and the same Z to A; remembered), a group's name editable in the Properties window, View Code / View Object, set startup form; follows the active window |
| Save Project As             | File > Save Project As… copies the project, unsaved changes included, to a new folder named after the new project file (or into an empty folder chosen), not its dist, build or hidden files; then the IDE works on the copy and the original stays as last saved |
| Immediate window (Ctrl+G)   | Program output and `Debug.Print`, stdin for console apps, double-click a traceback line to jump to it |
| Outline window              | The structure of the current file: constants, variables, classes and their members, functions, top-level code, with type icons; sort by file order, name or type; click an item to go to its line; the item the cursor is in is highlighted. It takes the Properties panel's place while a code window is active, and gives it back for designers (also View > Outline Window and F4) |
| Output window               | The IDE's own output, including library messages such as Qt warnings (hidden by default; View > Output Window) |
| Claude window               | View > Claude Window: Claude Code's login (Log In / Log Out; one login lasts across projects and sessions) and the project folder's sessions with Claude (New, Open, Rename, Delete); each session opens in a window next to the designers and code windows (see [Claude](#claude)) |
| Codex window                | View > Codex Window: OpenAI's Codex, as the Claude window: its login (Log In opens ChatGPT's login in the browser; one login lasts across projects and sessions) and the project folder's sessions with Codex (New, Open, Rename, Delete), each in a window among the designers and code windows |
| Menu Editor (Ctrl+E)        | Tools > Menu Editor designs the form's menus like VB's: Caption (`-` for a separator), Name, Index, Shortcut, Group (items that are choices), Picture, Checked, Enabled, Visible, with arrows to indent and move items. The designer shows the menu bar; click a menu to see it and an item to open its Click code |
| Pages                       | Controls in a ToolBox, a PageFrame or a WizardForm are on one of its pages: the designer edits the page shown (its `CurrentPage`). Click a ToolBox's page header, or choose Previous Page / Next Page in the designer's context menu (with the container, or a control in it, selected), to edit another; controls drawn or pasted there go on that page, and selecting a control on another page (in the Properties window's list) shows its page. The mouse wheel over a ScrollPanel scrolls it, to reach its controls further away |
| Wizard forms and splash screens | Project > Add Wizard Form: a WizardForm, a window that is a wizard (its Pages, Back/Next/Finish/Cancel, ValidatePage and NextPage in the code window's Form list); Project > Add Splash Screen: a borderless form with the project's title, version and company that closes itself after a few seconds |
| MDI forms                   | Project > Add MDI Form: an MDIForm, a window for the forms whose MDIChild is True (its workspace around docked controls, Arrange, ActiveForm, the active child's menus, a WindowList menu, the children in tabs with ViewMode); `ShowPopup` shows a form as a popup that doesn't take the focus |
| Format menu                 | Align, Make Same Size, Center in Form, Bring to Front (Ctrl+J), Send to Back (Ctrl+K), Lock Controls (the form's controls can't be moved or resized with the mouse or the arrow keys; hollow handles; remembered per form) |
| Help (F1)                   | Help > Contents, Index and Search open VP6's help (see [Help](#help)); F1 is help on what you're on: the word in the code, the property, the control, the tool or the Object Browser's member |
| Run (F5 or Cmd+Enter / Ctrl+Enter, Shift+F5, End) | Saves everything and runs the project in a separate process; the title shows `[design]` / `[run]` |
| Toolbar and layout          | Sun/moon switch at the right end of the toolbar toggles light/dark; View > Toolbars shows a hidden toolbar; View > Reset Window Layout restores all panels; panels at the bottom edge are always tabs; a form's window opens just large enough to show the whole form (or filling the main area when it can't), and every window opens inside the main area |

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

### Help

VP6's help works like VB6's `.chm` help, in a window of its own: on the
left its **Contents** (these documents, the API reference, the development
guides, the release notes and the Python reference of every `vp6` module),
an **Index** of keywords (every control, property, event, function, class,
method and constant; type to narrow it down, with *Regular expression* and
*Match case*) and **Search** (all of the help, text or a regular expression;
the topics with the most matches first, and the matches highlighted on the
page); on the right the page, with Back, Forward, Home and Locate (the page
in the contents).

* **Help > Contents, Index, Search…** open it at that tab.
* **F1** (Help > Context Help) is help on what you're on: in a code window,
  the word at the cursor (a control's name: its type's help; `Caption` in
  `self.Label1.Caption`); in the Properties window, the property, for the
  selected control's type; in a form's designer, the selected control; in
  the Toolbox, the tool chosen; in the Object Browser, the member or class
  chosen. A word the index doesn't have is searched for.

The help is made from VP6's documents and code: an installed VP6 has it
ready; run from its source, VP6 makes it again after a change (in about a
second, the first time F1 is pressed). Programs can have help of their own:
see [Help](api.md#help) in the API reference.

### Claude

<!-- keywords: Claude, Claude Code, AI, chat, session -->

VP6 works with **Claude Code** (Anthropic's `claude` command, which has to
be installed: see [its setup](https://docs.anthropic.com/en/docs/claude-code/setup)).
View > Claude Window opens the **Claude window** at the bottom, as a tab
with the Immediate window:

* **The login.** It says whether Claude Code is logged in. **Log In** runs
  `claude auth login` in the Terminal window (answer it there; the window
  notices when it's done); **Log Out** logs out. The login is Claude Code's
  own, kept by it (in the system's keychain or its folder), so it lasts:
  every project, every session and the next start of the IDE use it, and so
  does `claude` in a terminal. If the `claude` command isn't found (the IDE
  looks on the PATH and in the installers' usual places), **Locate…** chooses
  it.
* **The sessions** of the project's folder (or of the home folder without a
  project), the latest first: Claude Code's own, so sessions started with
  `claude` in a terminal are listed too. **New** starts one; **Open** (or a
  double click) goes on with the one selected; **Rename** names it (in the
  IDE); **Delete** deletes its transcript; **Refresh** lists them again.

A session opens in a **window of its own**, among the form designers and
code windows. It shows the conversation (Claude's answers as Markdown, each
tool it uses on a line of its own) and takes your next message: **Enter**
sends it, **Shift+Enter** starts a new line, and **Stop** stops Claude.
Claude works in the project's folder. When it wants to use a tool (run a
command, change a file) it asks: **Allow**, **Always Allow** (that tool,
for the rest of the session) or **Deny**. The box at the bottom chooses
what it may do without asking: *Ask Before Using Tools*, *Accept Edits*,
*Plan Only* or *Bypass Permissions* (new sessions start in the last one
chosen).

Files Claude changes show at once: the form designer and the code window of
an open form or module read the file again (and so they do when any other
program changes it). Only what changed is replaced, as one edit that Undo
takes back, and the cursor stays where it was. Before each message the IDE
saves the files changed in it, so Claude works on them as they are; a file
changed both in the IDE and on disk is read again only if you say so.

### Codex

<!-- keywords: Codex, OpenAI, ChatGPT, AI, chat, session -->

VP6 works with OpenAI's **Codex** too (the `codex` command, which has to be
installed: see [Codex CLI](https://developers.openai.com/codex/cli)), the
same way as with Claude. View > Codex Window opens the **Codex window** at
the bottom, as a tab with the Immediate window:

* **The login.** It says whether Codex is logged in (and as whom). **Log In**
  opens ChatGPT's login page in the browser; the window notices when it's
  done (**Cancel Login** gives up). **Log Out** logs out. The login is
  Codex's own, kept in its folder (`~/.codex`), so every project, every
  session, the next start of the IDE and `codex` in a terminal use it.
  **Locate…** chooses the `codex` command if it isn't found.
* **The sessions** of the project's folder, the latest first: Codex's own,
  so sessions started with `codex` in a terminal (or Codex's app) are listed
  too. **New**, **Open**, **Rename** (the name Codex keeps), **Delete** and
  **Refresh**, as in the Claude window.

A session opens in a **window of its own** among the form designers and code
windows: Codex's answers as Markdown, each command it runs and each file it
changes on a line of its own; **Enter** sends, **Shift+Enter** starts a new
line, **Stop** stops it. Codex works in the project's folder. When it wants
to do what its mode doesn't allow (run a command outside the sandbox, change
files) it asks: **Allow**, **Always Allow** (for the rest of the session) or
**Deny**. The box at the bottom chooses the mode: *Ask Outside the Folder*
(it changes the project's files and runs commands in it freely), *Ask
Before Running Commands*, *Read Only* or *Full Access*.

Files Codex changes show at once in the form designer and the code window,
and the files changed in the IDE are saved before each message, as for
Claude.

## Files

A project is a folder with a `Name.vp6p` project file listing forms, modules,
user controls (controls of your own, designed like forms and placed on forms
from the Toolbox, as VB's UserControl) and the startup object (a form or
`Sub Main`), and how the Project panel groups them. Groups are only for the panel: files stay where they are on
disk. A group can hold forms, modules and other groups. Forms and modules
can also be in subfolders of the project's folder (organize them in the
Project panel's Files view); they import each other by file name wherever
they are, so their file names are unique in a project. The program's icon
(its windows, and the Dock or taskbar) is the project's `icon`: new projects
have none and show the VP6 icon from the VP6 installation until you set your
own (the project's `Icon` in the Properties window). The project file is
also an executable launcher script, so it starts the program by itself:

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
* **Menus**: `Menu` controls on the menu bar or in other menus, with `Click`
  events, `Checked`, `Enabled`, `Visible` and `Shortcut`; menus can be control
  arrays (e.g. a recent files list). On macOS they are in the macOS menu bar.
* **Formatted labels**: a Label's `TextFormat` can be Rich Text (HTML) or
  Markdown, with headings, bold text and links (`LinkClick` event).
* **Docked panes**: a PictureBox with `Align` (Top, Bottom, Left, Right) sticks
  to that edge of the form and follows its size, e.g. a sidebar or a status bar.
  A `Splitter` docked beside it lets the user drag its size, and `ScrollBars`
  makes a PictureBox scroll the controls (or form) in it.
* **Forms inside forms**: `frmPage().ShowIn(self.picContent)` shows a form
  designed on its own inside a PictureBox or Frame of another form, filling
  it and following its size; `ShowIn(None)` makes it a window again.
* **Control arrays**: controls sharing a name, told apart by `Index`, with
  one handler that gets the `Index` first (`def cmdDigit_Click(self,
  Index)`). Elements are `self.cmdDigit[i]` or VB's `self.cmdDigit(i)`;
  `Load(self.cmdDigit, i)` / `Unload(self.cmdDigit, i)` add and remove
  elements at run time. In the designer, paste a copy of a control (VB asks
  whether to create a control array), give a control another control's
  name, or set its `Index`.
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

## Tests

```bash
.venv/bin/python -m pytest
```

The tests run headless (`QT_QPA_PLATFORM=offscreen`). They cover the
runtime, the form file format, designer operations and the IDE, including
running a console project through the Immediate window.
