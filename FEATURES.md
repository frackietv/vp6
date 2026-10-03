# VP6 features

**Version:** 0.4.39
**Date:** 2026-10-02

## Controls

- The Terminal control: your shell (or another program) in a terminal on the form, speaking ANSI: colors, bold, underline, inverse, cursor movement, erasing, scroll regions, the alternate screen, the title; in a pseudo-terminal on macOS and Linux (an interactive shell, Ctrl+C, its size following the control's), pipes on Windows; your keys go to it, copy and paste, mouse selection, a scrollback; CommandLine, WorkingDirectory, AutoStart, Start, Write, Kill, Clear, Text, Title, Exited and TitleChange

## Kitchen Sink

- A Terminal page: your shell, a demo of colors and a title, Clear and Restart

---

**Version:** 0.4.38
**Date:** 2026-10-02

## Language and runtime

- `ScaleMode` on forms, PictureBoxes, Picture objects and the Printer: the graphics methods, CurrentX / CurrentY, ScaleWidth / ScaleHeight and the mouse events' X, Y in pixels (the default), twips, points, characters, inches, millimeters or centimeters, or a User scale (`Scale(X1, Y1, X2, Y2)`, or setting `ScaleLeft`, `ScaleTop`, `ScaleWidth`, `ScaleHeight`)
- `ScaleX` / `ScaleY` convert between units; `Screen.TwipsPerPixelX` / `TwipsPerPixelY`
- A PictureBox's mouse events' X, Y are from inside its border, where its drawing is (they were off by the border's width)

## Kitchen Sink

- The Drawing page's clock is drawn in a User scale (its center 0, 0, up is up)

---

**Version:** 0.4.37
**Date:** 2026-10-02

## Language and runtime

- The `Process` control: running another program while the form keeps working (`Start` with a command line or a list, `WorkingDirectory`); its standard output and error as they come (`Output`, `ErrorOutput` events), its end (`Exited(ExitCode)`), a program that can't be started (`Error`); `Write` / `WriteLine` to its input, `CloseInput`, `Terminate`, `Kill`, `WaitForExit`; `Running`, `ExitCode`, `ProcessID`; ended with its form
- VB's `Shell(PathName, WindowStyle)`: a program started on its own, its process ID returned (with VB's WindowStyle constants)

## Kitchen Sink

- A Running programs page: a program that answers what you send it, its output and errors, its exit code, Kill, a missing program, and Shell opening the project's folder

---

**Version:** 0.4.36
**Date:** 2026-10-01

## Language and runtime

- MDI forms, as VB's: an `MDIForm` is a window whose workspace holds the forms with `MDIChild = True` (showing or loading one shows it there, loading the MDI form first; AutoShowChildren); aligned controls stay around the workspace; `ActiveForm`, `Arrange` (vpCascade, vpTileHorizontal, vpTileVertical, vpArrangeIcons), the children's Activate and Deactivate; the active child's menus replace the MDI form's; a Menu's `WindowList` lists the children; closing the MDI form unloads its children first (vpFormMDIForm); handlers `MDIForm_Load` and so on
- `Form.ShowPopup(X, Y, Owner)`: a form shown as a popup, borderless and on top, without taking the focus from the form that opened it (e.g. suggestions under a TextBox)

## IDE

- Project > Add MDI Form (one a project), designed with its workspace; MDIChild in a form's properties; WindowList in the Menu Editor

## Kitchen Sink

- An MDI and popup forms page: a Notes window (an MDI form with note forms, their menus, Window list, tiling) and fruit suggestions in a popup under a TextBox

---

**Version:** 0.4.35
**Date:** 2026-10-01

## Language and runtime

- `Form.DarkMode` (whether the form looks dark now; a form shown in another: like it) and `Screen.DarkMode` (the OS appearance)
- `Form_ColorSchemeChanged(Dark)`: the form turned light or dark (its ColorScheme or its window's, the OS switching, the IDE's theme), to draw again what it draws itself
- Programs run from the IDE with the "IDE" color scheme follow the IDE's theme live, not only its theme at launch

## IDE

- The designers pick up the OS switching between light and dark live for System forms, also while the IDE is forced to Light or Dark

## Kitchen Sink

- The Color schemes page shows DarkMode and Screen.DarkMode, and redraws its picture (a sun or a moon) in Form_ColorSchemeChanged

---

**Version:** 0.4.34
**Date:** 2026-10-01

## IDE

- File > Save Project As…: a copy of the project in a new folder (named after the new project file, or the empty folder chosen), unsaved changes included, without its dist, build or hidden files; the IDE then works on the copy, and the original stays as it was last saved
- The Project Explorer's Project view renames and deletes a form's or module's file too (Rename File…, Delete File…: imports follow a new name; a deleted file goes to the Trash and leaves the project)

---

**Version:** 0.4.33
**Date:** 2026-10-01

## IDE

- The Object Browser (View > Object Browser, F2), as VB's: a library list (All Libraries, VP6, the project), the classes and their members, and each member's declaration and description in the details pane
- VP6: the controls and Form (properties with their types, choices and defaults, methods with their arguments, events with theirs), the other classes (Picture, ControlArray...), the objects (App, Screen, Clipboard, Debug, Printer, Printers, Forms), the functions (Globals) and every group of constants
- The project: its forms and user controls (controls, methods, a user control's properties and events) and modules (functions, classes, constants, variables), read from the code as it is; double-click one to go to its code, or a control to its form's designer
- Search lists the classes and members whose names match

---

**Version:** 0.4.32
**Date:** 2026-10-01

## IDE

- The Properties window's Alphabetic and Categorized tabs, as VB's: Categorized lists the properties under Appearance, Behavior, Font, List, Misc, Position and Text headings, which collapse and expand with a click; the view chosen is remembered
- A user control's `Property(..., category="Appearance")` chooses its category
- Format > Lock Controls: the form's controls can't be moved or resized with the mouse or the arrow keys (hollow handles, as in VB); the Properties window and the Format menu still place them; remembered for each form

---

**Version:** 0.4.31
**Date:** 2026-10-01

## IDE

- Find and Replace in the whole project, as VB's Search: Current project: Find Next and Find Previous go from file to file (opening each code window), Replace All replaces in every form, user control and module (not in designer regions; unsaved, one undo step a file); Find All lists every match (in the module or the project), a double-click goes there

---

**Version:** 0.4.30
**Date:** 2026-10-01

## Packaging

- `vp6-make Name.vp6p` builds a wheel by default: the program as a Python package to install with pip, with a command named after the project (a GUI script for a windowed program, a console script for a console one; also `python -m name`), requiring VP6 and the packages its code imports; its version, summary and author from the project's Version, Description and CompanyName; built by VP6 itself, no extra tools
- Project > Build Wheel in the IDE builds it too, its output in the Output window
- Standalone executables are now `vp6-make --exe` (or `--onefile`); File > Make Executable is unchanged

---

**Version:** 0.4.29
**Date:** 2026-10-01

## Language and runtime

- The `Printer` object: printing text and graphics with the graphics methods (`Print`, `Line`, `Circle`, `PSet`, `PaintPicture`, `TextWidth` / `TextHeight`) page by page (`NewPage`, `EndDoc`, `KillDoc`, `Page`), with `Orientation`, `PaperSize`, `Copies`, `ColorMode`, `Duplex`, the page's `Width` / `Height` / `ScaleWidth` / `ScaleHeight` (96 an inch) and fonts in points; `OutputFile` prints to a PDF file
- The `Printers` collection: the system's printers; `Printer.DeviceName` chooses one
- `CommonDialog.ShowPrinter` with `PrinterDefault`: the Printer prints with the Print dialog's choices
- The `VP6_PRINT_TO_PDF` environment variable sends every document to PDF files in a folder instead of the printer

## Kitchen Sink

- The Dialogs page prints: Print (ShowPrinter, then the pages chosen), Print to PDF, and a list of the printers

---

**Version:** 0.4.28
**Date:** 2026-10-01

## Language and runtime

- Picture objects: `LoadPicture` and `SavePicture`; `Picture(Width, Height, BackColor)`, a picture in memory drawn on with the graphics methods (Line, Circle, PSet, Print, PaintPicture...); every picture property (Picture, Icon, MouseIcon, DragIcon, the buttons' pictures, ListImages) takes a Picture as it takes a file
- A form's or PictureBox's `Image` (what it shows, as a Picture) and `PaintPicture` (a picture, or a part of it, scaled)
- A form's `Picture`: a picture on its background
- The clipboard: pictures (`Clipboard.GetData`, `SetData`, `GetFormat` with `vpCFBitmap` / `vpCFDIB`), rich text (`GetText` / `SetText` with `vpCFRTF`) and files; a picture dropped from another program in OLEDragDrop's Data

## Kitchen Sink

- The Pictures page makes a Picture in memory (also its MouseIcon), saves and loads it, copies and pastes it, and sets the form's own Picture

---

**Version:** 0.4.27
**Date:** 2026-10-01

## Language and runtime

- Drawing on forms and PictureBoxes (and a user control's Surface) with VB's graphics methods: `Line` (lines, from the current point, Step, boxes with "B" and "BF"), `Circle` (circles, ellipses with Aspect, arcs, pie slices), `PSet`, `Print` (like Python's print, at CurrentX / CurrentY), `Cls` (the drawing, not the Picture), `Point`, and `TextWidth` / `TextHeight` for measuring text
- Drawing properties: `DrawWidth`, `DrawStyle` (with the new `vpSolid` ... `vpInsideSolid` constants; dashed at any width, and a line drawn bit by bit, e.g. following the mouse, keeps its pattern going), `FillStyle`, `FillColor`, `CurrentX` / `CurrentY`, and PictureBox's `ScaleWidth` / `ScaleHeight` and Font
- `AutoRedraw` keeps what is drawn; without it the `Paint` event (`Form_Paint`, a PictureBox's, `UserControl_Paint`) fires whenever it needs drawing again, e.g. after `Refresh()`
- `PictureBox.Cls()` now clears the drawing and keeps the Picture, as in VB

## Kitchen Sink

- A Drawing page: a sketch pad drawn with the mouse, shapes, DrawWidth and DrawStyle, Cls, a clock drawn in its Paint event, and the page's own Form_Paint

---

**Version:** 0.4.26
**Date:** 2026-10-01

## IDE

- The splash screen's version is dark blue-grey in every appearance (it was white on the grey splash screen when macOS or the IDE was Dark)

---

**Version:** 0.4.25
**Date:** 2026-10-01

## Command line

- `--help` everywhere: `vp6 --help` (the IDE: a project to open, `--no-splash`, its environment variables), `vp6-run --help` (and `python -m vp6.runner --help`), `vp6-make --help`
- VP6 programs take `--help` too (the project file, `vp6-run PROJECT --help`, a made executable): the product name, version and description, the usage, and the program's own arguments from the project's new ArgumentsHelp property (Project Properties and the Properties window); a windowed executable without a console shows it in a message box
- The Kitchen Sink's `--help` lists its `--page NAME`

---

**Version:** 0.4.24
**Date:** 2026-10-01

## Language and runtime

- Per-user settings as in VB: `SaveSetting`, `GetSetting` (with a default), `GetAllSettings` and `DeleteSetting` (a setting, a section or all of a program's), kept where the system keeps settings (the registry on Windows, a preferences file on macOS, ~/.config on Linux)
- More of VB's `App`: `Major`, `Minor`, `Revision`, `ProductName`, `CompanyName`, `FileDescription` from the project's new Version, ProductName, CompanyName and Description properties, and `PrevInstance`; `App.Title` without a project is the program's name
- `Command()`: the program's command line arguments; the project's Arguments property is what the IDE runs it with (`python -m vp6.runner` passes arguments on too)
- `Screen.Fonts` (also `Screen.Fonts(i)`) and `Screen.FontCount`: the installed fonts
- ComboBox: adding items no longer chooses the first one or fires Click, as in VB (ListIndex stays -1)

## IDE

- Project Properties: Version (Major, Minor, Revision), Product Name, Company Name, Description and Command Line Arguments, also in the Properties window

## Kitchen Sink

- The App, Screen, settings page shows the App information, PrevInstance and Command(), remembers its text with SaveSetting, and lists the fonts; the project has a version and descriptions, and `--page NAME` on its command line opens that page

---

**Version:** 0.4.23
**Date:** 2026-10-01

## Controls

- WebBrowser: a web browser in the form, Qt WebEngine (Chromium), with the WebView's VB WebBrowser names and more: `BeforeNavigate(URL)` (return True to stay), `NewWindow(URL)` (new windows open in it, unless True), `StatusTextChange(Text)` (the link under the mouse), GotFocus and LostFocus
- The Kitchen Sink's Web pages page shows a WebView or a WebBrowser, with the browser's own events

---

**Version:** 0.4.22
**Date:** 2026-10-01

## Controls

- WebView: a web page shown by the platform's own web view (Qt WebView's QWebView: WebKit on macOS, WebView2 on Windows), with VB's WebBrowser names: `URL`, `Navigate` (web addresses, files, domains), `GoBack`, `GoForward`, `Refresh`, `Stop`, `LoadHTML`, `RunScript` (with a callback for the result), `LocationURL`, `LocationName`, `Busy`, `Progress`, `CanGoBack`, `CanGoForward`, and the `DocumentComplete`, `NavigateError`, `TitleChange` and `ProgressChange` events
- The Kitchen Sink's Web page: an address box, Back, Forward, Refresh, HTML of its own and a script

---

**Version:** 0.4.21
**Date:** 2026-10-01

## Controls

- CommonDialog, as in VB: `ShowOpen` and `ShowSave` (VB's Filter syntax, FilterIndex, InitDir, DefaultExt, FileName, FileTitle, FileNames with multi-select, the overwrite prompt), `ShowColor` (Color), `ShowFont` (FontName, FontSize, FontBold, FontItalic, FontUnderline, FontStrikethru), `ShowPrinter` (Copies, Orientation, FromPage to ToPage) and `ShowHelp` (HelpFile); DialogTitle, Flags (`vpOFN...`, `vpCC...`, `vpCF...`, `vpPD...`); each returns True or False, or with CancelError raises `DialogCancelled` (error 32755)
- The Kitchen Sink's Dialogs page uses one for Open, Save As, Color, Font and Print setup

## IDE

- Fixed: moving an ImageList in the designer gave it Width and Height in the form file, which then failed to run; icons such as Timer, ImageList and CommonDialog keep no size of their own

---

**Version:** 0.4.20
**Date:** 2026-10-01

## Language and runtime

- `MousePointer` and `MouseIcon` on controls and forms (VB's pointer shapes, or a picture with vpCustom), and `Screen.MousePointer` for every window (e.g. vpHourglass)
- VB drag and drop: `DragMode` (Automatic: pressing drags), `Drag` (begin, end, cancel), `DragIcon`, and the `DragOver(Source, X, Y, State)` and `DragDrop(Source, X, Y)` events on controls and forms
- Drops from other programs: `OLEDropMode` Manual, `OLEDragOver` and `OLEDragDrop` with a Data object (`GetFormat`, `GetData`, `Files`) for text and files
- The Kitchen Sink's Mouse page: pointers, fruit dragged into a basket, and a drop zone for text and files

---

**Version:** 0.4.19
**Date:** 2026-10-01

## Language and runtime

- Moving a control to another container at run time, as VB's `Set Command1.Container = Frame1`: `Command1.Container = self.Frame1` (its form, a Frame, PictureBox or DockPanel); its Left and Top stay, now in the new container; option buttons join the new container's group
- The Kitchen Sink's Buttons page: a button hopping into a frame and out

---

**Version:** 0.4.18
**Date:** 2026-10-01

## Language and runtime

- The `Validate` event and `CausesValidation` property, as in VB, for every control that takes the focus: returning True from Validate keeps the focus in the control (no LostFocus, GotFocus or Click elsewhere); controls with CausesValidation = False (a Help button) don't wait for it
- `Form.ActiveControl` and `Screen.ActiveControl`: the control with the focus
- `SendKeys(Keys, Wait)` with VB's syntax (`+` `^` `%`, groups, `~`, `{ENTER}`, `{TAB}`, `{F1}`, `{LEFT 3}`...), reaching whatever has the focus as each key arrives, including menu shortcuts and Label access keys
- The Kitchen Sink's Keyboard page: a validated Age box, the active control, and keys typed by SendKeys

---

**Version:** 0.4.17
**Date:** 2026-10-01

## Language and runtime

- Default form instances, as in VB: a form's class name stands for one instance made on first use (`frmOptions.Show()`, `frmOptions.txtName.Text`, `frmOptions.Caption = "x"`); `run(Form1)` makes the running form the default one
- `Form_QueryUnload(UnloadMode)` before `Form_Unload`, telling why the form closes (`vpFormControlMenu`, `vpFormCode`, `vpAppTaskManager`, `vpFormOwner`); returning True keeps it open
- A form's `Icon` property: its own window icon (an image file), else the program's
- The Kitchen Sink's dialog is used through its default instance, has its own icon and tells why it closed

---

**Version:** 0.4.16
**Date:** 2026-10-01

## Kitchen Sink

- Closing the Kitchen Sink no longer asks for confirmation; its File > End menu item is now "End (at once)"

---

**Version:** 0.4.15
**Date:** 2026-10-01

## Language and runtime

- `PopupMenu(Menu, Flags, X, Y, DefaultMenu)`, a Form method, as in VB: one of the form's menus (typically an invisible menu-bar menu) shown as a context menu at the mouse or at X, Y, aligned left, centered or right (`vpPopupMenuLeftAlign`, `vpPopupMenuCenterAlign`, `vpPopupMenuRightAlign`), with DefaultMenu in bold; it waits for the choice and returns the chosen item (or None)
- The Kitchen Sink's Menus page: a popup menu on a right-click, and one under a button

---

**Version:** 0.4.14
**Date:** 2026-10-01

## Controls

- User controls (VB's UserControl): your own controls, designed like forms and placed on forms from the Toolbox
  - A `UserControl` subclass with its constituent controls on its `Surface`, its properties declared with `Property(...)` and its events with `Events` (with arguments, `"Change(Value)"`), raised with `RaiseEvent`
  - Its own events: `UserControl_Initialize`, `UserControl_PropertyChanged(PropertyName)`, `UserControl_Resize`, Click, mouse and key events; its controls' events are its methods; `UserMode`
  - It runs on forms in the designer (showing its property values), without its controls' events

## IDE

- Project > Add User Control (and in the Project panel), a User Controls group, the project's `user_controls`
- A user control's designer: its surface without a window frame, its own properties only; its code window's UserControl events
- The project's user controls in the Toolbox; placed on a form, the form imports their class, and the Properties window and code window know their properties and events
- User controls are loaded from their current text and again a moment after an edit; forms using them are redrawn

## Kitchen Sink

- A user control, `ctlRating` (stars), and a "Your own controls" page using it three times

## Other

- The backlog's related items combined

---

**Version:** 0.4.13
**Date:** 2026-10-01

## Controls

- Shape, as in VB: a rectangle, square, oval, circle, rounded rectangle or rounded square (`Shape`), with a border (`BorderStyle`, `BorderColor`, `BorderWidth`), a solid or hatched fill (`FillStyle`, `FillColor`) and, opaque, a `BackColor` (`BackStyle`); no events, clicks go through
- Constants `vpShape...`, `vpFS...` and the hatch styles, and `vpBS...` border styles (for Shape and Line)
- The Kitchen Sink's "Lines, shapes and z-order" page shows every kind of Shape and changes one from lists

---

**Version:** 0.4.12
**Date:** 2026-10-01

## Controls

- DockPanel, a dockable tool window (a container with a caption bar):
  - Docked to an edge of its form (`Align`), sharing the edges with the form's other docked controls; its inner edge resizes it (`Resizable`)
  - Floating in a window of its own (`Floating`, `Float()`, `Dock(Align)`, `FloatLeft`, `FloatTop`, `FloatWidth`, `FloatHeight`, `FloatMove`), showing and hiding with its form
  - Dragging its caption bar floats it and docks it on the edge it is dropped near (a frame shows where); double-clicking it or its float button floats or docks it (`Floatable`)
  - Its close button hides it (`Closable`; the `Close` event can cancel); `Visible = True` shows it again where it was
  - `DockChange` and `Resize` events
- The form's `DockLayout`: where all its DockPanels are, as text to keep and set again
- A Kitchen Sink page, "Docking panels": Tools, Properties and Output panels to float, dock, close, show again and save the layout of

---

**Version:** 0.4.11
**Date:** 2026-10-01

## Projects

- New projects (and the Kitchen Sink) no longer get a copy of the VP6 icon in an `icons` folder: without an icon of their own they use the VP6 icon from the VP6 installation (their windows, the Dock or taskbar, and executables made with vp6-make)

---

**Version:** 0.4.10
**Date:** 2026-10-01

## Controls

- FlexGrid, a grid like VB's MSFlexGrid:
  - `Rows`, `Cols`, `FixedRows` and `FixedCols` (headings that stay put while scrolling), `TextMatrix(r, c)` and `TextMatrix[r, c] = "x"`, `FormatString`
  - The current cell and the selection: `Row`, `Col`, `Text`, `RowSel`, `ColSel`, `SelectionMode`; `EnterCell`, `LeaveCell`, `RowColChange`, `SelChange`
  - `CellBackColor`, `CellForeColor`, `CellFontBold`, `CellFontItalic`, `CellAlignment`; `ColWidth`, `RowHeight`, `ColAlignment`, `RowData`
  - `AddItem`, `RemoveItem`, `Clear`, `Sort` (generic, numeric, text with or without case, both ways); `TopRow`, `LeftCol`, `Scroll`, `MouseRow`, `MouseCol`; `AllowUserResizing`, `GridLines`
  - Editing (beyond MSFlexGrid): `Editable`, editors per column (`ColEditor`, `ColList`) or cell (`CellEditor`, `CellList`): text, list, check box, color, a `...` button (`CellButtonClick`) or none; `BeforeEdit`, `ValidateEdit`, `AfterEdit`; `EditCell()`
- Constants `vpGridEdit...`, `vpGridSort...` and `vpGridSelection...`
- A Kitchen Sink page, "FlexGrid": a sortable price list and an editable property sheet with an editor per cell

---

**Version:** 0.4.9
**Date:** 2026-10-01

## Controls

- CodeBox, a code editor control:
  - Syntax coloring: `Language` (Python, in light or dark colors) and a `Highlight(Line, Text, State)` event coloring parts of each line with `HighlightText`, its returned State carried to the next line; `Rehighlight()`
  - A gutter with line numbers (`LineNumbers`), markers (`LineMarker[Line] = "●"`, moving with their lines) and `GutterClick(Line)`
  - The current line shaded (`HighlightCurrentLine`, `CurrentLineColor`)
  - Hidden (folded) lines: `HideLines`, `ShowLines`, `IsLineHidden`, a + in the gutter
  - Protected lines the user can't change but code can: `ProtectLines`, `UnprotectLines`, `IsLineProtected`, `ProtectedColor`, the `ProtectedEdit(Line)` event
  - Auto-indent (`AutoIndent`), Tab and Shift+Tab indenting (`TabWidth`, `UseTabs`, `AcceptsTab`), `WordWrap`, `Locked`, a fixed-width font, and the TextBox editing API
- A Kitchen Sink page, "CodeBox": Python code with TODO and FIXME marked, breakpoints and a foldable, protected region in the gutter

---

**Version:** 0.4.8
**Date:** 2026-10-01

## Controls

- An editing API shared by TextBox and RichTextBox (a line is a paragraph, lines and columns count from 0):
  - Lines and columns: `LineCount`, `GetLine`, `GetLineFromChar`, `GetCharFromLine`, `GetColumnFromChar`, and the caret's `CurrentLine` and `CurrentColumn` (setting them moves it)
  - The caret on screen: `CaretLeft`, `CaretTop`, `CaretHeight`; `GetCharFromPoint(X, Y)`
  - Scrolling: `FirstVisibleLine`, `ScrollLeft`, `ScrollToCaret()`
  - Undo: `Undo()`, `Redo()`, `CanUndo`, `CanRedo`, `ClearUndo()`
  - `AcceptsTab`: Tab types a tab instead of moving to the next control
  - TextBox gets the `SelChange` event
- A Kitchen Sink page, "Editing text": a small code editor with line and column, Undo/Redo, Indent, Go to line, Tab, the word under the mouse, and completions under the caret

---

**Version:** 0.4.7
**Date:** 2026-10-01

## Controls

- RichTextBox: text with fonts, colors, bold, italic, underline and strikethrough, and aligned paragraphs
- The selection's format: `SelBold`, `SelItalic`, `SelUnderline`, `SelStrikeThru`, `SelColor`, `SelFontName`, `SelFontSize`, `SelAlignment`; None (VB's Null) when the selection is mixed; with nothing selected, the format of what is typed next
- `SelStart`, `SelLength`, `SelText`, and the `SelChange` event
- `AppendText(Text, Color, Bold, Italic, Underline)`: formatted text added at the end without moving the selection, following the end like a log
- `Find` (whole word, match case, no highlight: `vpRtfWholeWord`, `vpRtfMatchCase`, `vpRtfNoHighlight`), `GetLineFromChar`
- Formatting as HTML instead of VB's RTF: `TextHTML`, `SelHTML`, `LoadFile`/`SaveFile` with `vpRtfHTML` or `vpRtfText`
- `Locked`, `MaxLength`, `ScrollBars`, `BorderStyle`; pasting keeps formatting but leaves out pictures and tables
- A RichTextBox Toolbox icon
- A Kitchen Sink page, "RichTextBox": a small word processor (formatting buttons kept in step with the selection, Find, Save and Load as HTML, a word count) and a colored log

---

**Version:** 0.4.6
**Date:** 2026-09-30

## Controls

- DriveListBox, DirListBox and FileListBox, VB's file system controls, linked in their Change events (`Dir1.Path = Drive1.Drive`, `File1.Path = Dir1.Path`)
- DriveListBox: `Drive` (drive letters on Windows; `/` and the mounted volumes on macOS and Linux), `Refresh`, `Change`
- DirListBox: `Path` under its parent folders and above its subfolders, opened by double-click (`Change`); VB's negative `List` indexes (`List(-1)` is Path, `List(-2)` its parent, `List(0)`... its subfolders), `ListIndex`, `ShowHidden`, `Refresh`, `Click`
- FileListBox: the files in `Path` matching `Pattern` (`"*.png;*.jpg"`, not case-sensitive), `FileName` (setting it changes Path, Pattern or the selection), `Hidden`, `Refresh`, `PathChange` and `PatternChange`; otherwise a ListBox (selection, MultiSelect, Click, DblClick)
- Toolbox icons for all three
- A Kitchen Sink page, "Drives, folders and files": the three linked, a pattern chooser, hidden files, and the chosen file's size and picture

---

**Version:** 0.4.5
**Date:** 2026-09-30

## Controls

- Label `BackStyle`, as in VB: Opaque (the default) fills the label's box with its BackColor, or its container's color, hiding what is behind it; Transparent lets a picture or other controls behind it show through, and ignores BackColor. Constants `vpTransparent` and `vpOpaque`
- The Kitchen Sink's Pictures page has an opaque and a transparent label on its picture

---

**Version:** 0.4.4
**Date:** 2026-09-30

## Controls

- Label access keys, as in VB: an `&` before a letter in a Label's Caption underlines it, and Alt+the letter (on macOS Control+Option+the letter, which leaves Option+letter for typing accented letters) moves the focus to the next control in the tab order (going round, skipping hidden and disabled ones)
- Label `UseMnemonic`: False shows the `&` as it is, with no access key; `AccessKey` gives the key's letter
- The Kitchen Sink's Text page has access keys on its labels, and a label with UseMnemonic = False

---

**Version:** 0.4.3
**Date:** 2026-09-30

## Repository

- The Calculator and GuessNumber samples are gone (the Kitchen Sink template demonstrates every feature); the executables workflow no longer makes the Calculator sample, and the source distribution has the docs and the tests

---

**Version:** 0.4.2
**Date:** 2026-09-30

## Controls

- ListBox and ComboBox `NewIndex` (where the item AddItem added last is, also when Sorted moved it) and `TopIndex` (the item at the top of the list; setting it scrolls)
- ListBox `SelCount`, and `Selected` can be set: `List1.Selected[2] = True` (VB's `List1.Selected(2) = True`)
- ListBox `Style = 1` (Checkbox): a check box in front of every item, `Selected` while checked, and the `ItemCheck(Item)` event when the user checks or unchecks one
- ComboBox `Style = 1` (Simple Combo): an editable text above a list that is always shown; and the ComboBox `DropDown` event, just before its list drops down
- The Kitchen Sink's Lists page has a Checkbox ListBox, a Simple Combo, a ComboBox adding what was typed when it drops down, and uses NewIndex and TopIndex

---

**Version:** 0.4.1
**Date:** 2026-09-30

## Controls

- ListBox and ComboBox `ItemData`: a value kept with each item, like VB's (`ItemData(i)` reads it, `ItemData[i] = 42` sets it), moving with its item when the list is sorted or items are removed
- Per-item pictures and fonts for ListBox and ComboBox: `ItemImage` (a Key or Index in the control's new `ImageList`, or a picture file), `ItemBold`, `ItemItalic` and `ItemForeColor`
- The Kitchen Sink's Lists page keeps its colors in `ItemData`, shows each color's name in its color, and gives the list pictures, with a star and italics for added items

---

**Version:** 0.4.0
**Date:** 2026-09-30

## Distribution

- VP6 is ready to publish on PyPI as `vp6` (`pip install vp6`, `pip install "vp6[make]"` for standalone executables): MIT license (`LICENSE`), author, classifiers and keywords in `pyproject.toml`; the wheel has the package with its pictures and Kitchen Sink templates and the `vp6`, `vp6-run` and `vp6-make` commands, the source distribution also the docs, samples and tests
- Publishing: pushing a tag `v<version>` runs a GitHub Actions workflow that checks the tag against the version, builds and checks the distributions and uploads them with PyPI's trusted publishing; "Releasing" in the development guide has the one-time PyPI setup and the manual alternative
- `vp6-make` no longer gives PyInstaller VP6's folder when VP6 is a normal install (in site-packages), which PyInstaller warned about and will refuse

---

**Version:** 0.3.36
**Date:** 2026-09-30

## IDE

- File > Make Executable… makes the project a standalone program that runs without Python, PySide6 or VP6 installed (VB's Make Project1.exe): a macOS app, a Windows .exe or a Linux program, in the project's `dist` folder, optionally as one file; its output shows in the Output window, and a message gives where it is (Show in Folder)

## Projects and programs

- `vp6-make Name.vp6p [--onefile] [--dist DIR]` (or `python -m vp6.make`) makes the executable from the command line, with PyInstaller (`pip install "vp6[make]"`)
- The executable has the project's files in their folders (so forms find their pictures and code its data files), everything its code imports, VP6 and PySide6, and the project's icon
- Executables are made for the system they are made on; a GitHub Actions workflow makes and runs one on Linux, Windows and macOS, and makes the Calculator sample for each

---

**Version:** 0.3.35
**Date:** 2026-09-30

## Controls

- Graphical buttons (`Style = 1`, as in VB): a CommandButton shows its `Picture` above its Caption, its `DownPicture` while pressed and its `DisabledPicture` while disabled (else the Picture grayed)
- Toggle buttons: a Graphical CheckBox stays pressed while its Value is `vpChecked`; Graphical OptionButtons are pressed one at a time, like a toolbar's group (exclusive with the container's ordinary option buttons too); both show pictures like a Graphical CommandButton
- A Graphical button's Caption is as large as an ordinary button's; changing Style keeps a CheckBox's or OptionButton's Value without a Click
- The Kitchen Sink's Buttons page has a picture button, a toggle CheckBox (Underline) and toggle OptionButtons (Alignment)

---

**Version:** 0.3.34
**Date:** 2026-09-30

## Controls

- ListView: items shown as large icons, small icons, a list, or a report with columns (`View`), keeping the selection when the view changes. Items have a Text, pictures from two ImageLists (`Icon` for the Icon view, `SmallIcon` for the others) and SubItems, their texts in the Report view's other columns; columns have a title, a width and an alignment. With `Sorted` the items stay sorted by the `SortKey` column, A to Z or Z to A (`SortOrder`). `MultiSelect`, `Checkboxes`, `HideColumnHeaders`, `SelectedItem`, `HitTest`. `ItemClick` gets the ListItem, `ColumnClick` the ColumnHeader, `ItemCheck` the ListItem
- The ListItems collection (`ListItems(Index)` or `ListItems(Key)`, `Count`, `Add`, `Remove`, `Clear`) and ListItem objects (`Text`, `Key`, `Index`, `Icon`, `SmallIcon`, `SubItems`, `Selected`, `Checked`, `ToolTipText`, `Tag`, `EnsureVisible`); `item.SubItems(1)` reads and `item.SubItems[1] = "x"` sets a SubItem
- The ColumnHeaders collection and ColumnHeader objects (`Text`, `Key`, `Index`, `Width`, `Alignment`, `SubItemIndex`, `Tag`)
- In the designer, `ColumnHeaders` and `ListItems` are lists of lines: `Text|Key|Width|alignment` and `Text|Key|Icon|SmallIcon|SubItem 1|SubItem 2...`
- Constants `vpLvwIcon`, `vpLvwSmallIcon`, `vpLvwList`, `vpLvwReport`, `vpLvwColumnLeft`, `vpLvwColumnRight`, `vpLvwColumnCenter`, `vpLvwAscending`, `vpLvwDescending`
- A new Kitchen Sink page, "ListView"

## Fixes

- Pictures from an ImageList shown smaller than they are (e.g. 32-pixel pictures in a 16-pixel ImageList) are sharp on high-DPI screens

---

**Version:** 0.3.33
**Date:** 2026-09-30

## IDE

- A splash screen when the IDE starts: the VP6 logo with the version centered under it, for two seconds, while the IDE window is built; it can't be moved, resized or closed, and closes itself. `vp6 --no-splash` starts without it (options may come before or after a project file)

---

**Version:** 0.3.32
**Date:** 2026-09-30

## Controls

- ImageList: a collection of pictures for other controls, invisible at run time. A TreeView's, TabStrip's or Toolbar's `ImageList` names it, and their nodes', tabs' and buttons' `Image` is a picture's Key or Index. All its pictures get one size (`ImageWidth` × `ImageHeight`, or the first picture's); the controls using it follow its changes, and it may come before or after them
- The ListImages collection: `ListImages(Index)` or `ListImages(Key)`, `Count`, `Add`, `Remove`, `Clear`; a ListImage's `Picture` (its file, also usable as an Image's or PictureBox's `Picture`), `Key`, `Index`, `Tag`, `Width`, `Height`
- In the designer, `ListImages` is a list of `path|key` lines, with an **Add Pictures…** button to pick files
- TreeView: `ImageList`, and `Image` in the designer's outline (`Text|key|image`); TabStrip: `ImageList`, and a tab's `Image` (`Caption|Key|ToolTipText|Image`)
- Toolbar: a row of buttons docked to the top of a form (or the bottom, or the sides as a vertical toolbar), as tall as its buttons need. Buttons show a picture from an ImageList and a Caption (under the picture or beside it: `TextAlignment`); they are ordinary buttons, Check buttons (pressed or not), ButtonGroup buttons (adjacent ones of which one is pressed) or separators. `ButtonClick` gets the Button
- The Buttons collection: `Buttons(Index)` or `Buttons(Key)`, `Count`, `Add`, `Remove`, `Clear`; a Button's `Caption`, `Key`, `Index`, `Image`, `Style`, `Value`, `ToolTipText`, `Enabled`, `Visible`, `Tag`, and its `Left`, `Top`, `Width`, `Height`
- In the designer, `Buttons` is a list: one button per line, `Caption|Key|Image|ToolTipText|options` (check, group, pressed, disabled, hidden), `-` for a separator
- Constants `vpTbrDefault`, `vpTbrCheck`, `vpTbrButtonGroup`, `vpTbrSeparator`, `vpTbrUnpressed`, `vpTbrPressed`, `vpTbrTextAlignBottom`, `vpTbrTextAlignRight`
- The Kitchen Sink's TreeView and TabStrip pages show pictures from ImageLists, drawn when the project is created
- The Kitchen Sink window has a Toolbar: previous and next page, the navigation pane (a Check button) and the color schemes (a ButtonGroup), in step with the View menu

## Fixes

- Opening a new Kitchen Sink in the IDE could fail with "Internal C++ object (QCommonStyle) already deleted": a form with a forced light or dark scheme kept the shared Fusion style's Python wrapper, which PySide invalidated when a widget it was set on (a Toolbar's rebuilt button) was destroyed. The style is now fetched each time it is needed, with a fresh wrapper when the old one was invalidated

---

**Version:** 0.3.31
**Date:** 2026-09-30

## Controls

- TabStrip: a row of tabs, on any side (`Placement`). Like VB's it isn't a container: each tab's Frame goes over its client area (`ClientLeft`, `ClientTop`, `ClientWidth`, `ClientHeight`, right already in `Form_Load`) and `Click` shows the selected one. `Click` fires when another tab is selected, by the user or by code; returning `True` from `BeforeClick` keeps the current tab
- The Tabs collection: `Tabs(Index)` or `Tabs(Key)`, `Count`, `Add`, `Remove`, `Clear`; a Tab's `Caption`, `Key`, `Index`, `ToolTipText`, `Tag`, `Selected`; `SelectedItem` (a Tab, Index or Key), kept when tabs are added or removed
- In the designer, `Tabs` is a list: one tab per line, `Caption|Key|ToolTipText`
- Constants `vpTabPlacementTop`, `vpTabPlacementBottom`, `vpTabPlacementLeft`, `vpTabPlacementRight`
- A new Kitchen Sink page, "TabStrip"

---

**Version:** 0.3.30
**Date:** 2026-09-30

## Controls

- StatusBar: a bar of panels docked to the bottom of a form (or the top), like an aligned PictureBox. Panels show a text, the time, the date, or the state of Caps Lock, Num Lock, Insert or Scroll Lock (dimmed while off); they are Spring (sharing the space left), as wide as their contents, or a fixed width, aligned left, center or right. `PanelClick` and `PanelDblClick` get the Panel. Style = Simple shows `SimpleText` across the bar
- The Panels collection: `Panels(Index)` or `Panels(Key)`, `Count`, `Add`, `Remove`, `Clear`; a Panel's `Text`, `Key`, `Width`, `AutoSize`, `Style`, `Alignment`, `ToolTipText`, `Visible`, `Enabled`, `Tag`, `Left`
- In the designer, `Panels` is a list: one panel per line, `Text|Key|options` (e.g. `Ready|status|spring`, `|clock|time 80 right`)
- Constants `vpSbrNormal`, `vpSbrSimple`, `vpSbrText` … `vpSbrDate`, `vpSbrNoAutoSize`, `vpSbrSpring`, `vpSbrContents`, `vpSbrLeft`, `vpSbrCenter`, `vpSbrRight`
- The Kitchen Sink window has a StatusBar (status text, Caps Lock, and a clock that shows the date when clicked) instead of a PictureBox with a Label

---

**Version:** 0.3.29
**Date:** 2026-09-30

## IDE

- VP6 has an icon: the VP6 cubes, in four sizes (32 to 256 pixels), for the IDE's window and in the Dock or taskbar
- New projects (Standard EXE, Console Application and the Kitchen Sink) get the VP6 icon as the program's icon, in an `icons` folder, to replace with your own
- The project's `Icon` in the Properties panel: choose an image file in the project's folder (empty: the VP6 icon)

## Projects and programs

- The project file's `icon`: image files relative to the project, sizes of one picture (or one file); a windowed program shows it for its windows and in the Dock or taskbar
- A VP6 program without an icon of its own shows the VP6 icon

---

**Version:** 0.3.28
**Date:** 2026-09-30

## Controls

- ProgressBar: a bar filled from `Min` to `Max` as `Value` grows (a Value outside them is kept at the nearer end), horizontal or vertical
- Slider: a thumb on a scale with tick marks (`TickStyle`, `TickFrequency`), `SmallChange` / `LargeChange`, horizontal or vertical; `Scroll` while the thumb is dragged, `Change` once the value has changed
- UpDown: arrow buttons stepping a `Value` by `Increment` between `Min` and `Max` (`Wrap` to go round), vertical or horizontal, repeating while held; `Change`, `UpClick`, `DownClick`. A buddy control (`BuddyControl`, `BuddyProperty`, `SyncBuddy`) shows the value, and a number typed into it is where the next click starts
- Constants `vpOrientationHorizontal` / `vpOrientationVertical` and `vpTickBottomRight`, `vpTickTopLeft`, `vpTickBoth`, `vpTickNone`
- All three in the Toolbox (with icons), the designer, the API reference, and a new Kitchen Sink page, "Sliders, progress and spinners"

---

**Version:** 0.3.27
**Date:** 2026-09-30

## IDE

- The Project panel is organized in groups and subgroups instead of reflecting folders on disk: a group can hold forms, modules and other groups, and files can also sit at the top level. Forms and Modules are the default groups, and new forms and modules go where files of their kind are; nothing else about them is special. The context menu has New Group…, Rename Group…, Delete Group (what it held moves up), and Move to (the project or any other group); items can also be dragged onto a group, a file (into its group) or the project. A new form or module goes in the selected group. Within each group, subgroups come first, then files, each sorted by name. Duplicate names among siblings are refused with a message
- Selecting a group shows its (Name) in the Properties panel, where it can be renamed (any name except a sibling's)
- The Project panel's Name button cycles through four orders: A to Z with the groups first, A to Z with the groups among the forms and modules, and the same two Z to A; the IDE remembers the choice
- The project file stores the groups (`"groups"` in `PROJECT`, written over several lines); `forms` and `modules` still say what each file is, and projects without groups get the two default groups
- The Kitchen Sink's pages are in a Pages subgroup of Forms
- The project item at the top of the Project panel can't be collapsed (no arrow; double-click and the Left/minus keys leave it open)
- The Project panel's +/- button expands every group, or collapses them all when everything is open; groups you collapse stay collapsed when the panel is refilled (e.g. after adding a form)
- The Project panel has two views: Project (the groups) and Files, the project's folder as it is on disk, with folders and all files (hidden files and folders with the Hidden button; never the project file, `.git` or `__pycache__`). In the Files view forms and modules open, set the startup object and are removed as in the Project view; it follows changes on disk; sorting and +/- work on its folders. The IDE remembers the view
- The Files view changes the project's folder: new folders and subfolders (its New Folder button, New Folder… in the context menu of a folder or file, or Project > Add Folder…, which shows the Files view), Rename… (files and folders), Delete (to the Trash; forms and modules in it leave the project, after asking) and Move to, or drag and drop onto a folder. The forms and modules in a renamed or moved file or folder stay in the project, in their groups, with their windows open; renaming a form's or module's file updates the imports of it in the other files. A form's or module's file keeps a Python name, unique in the project. New forms and modules go in the selected folder
- Several items can be selected in the Project panel (Ctrl/Cmd-click, Shift-click) and moved at once, in both views: dragged onto a group or folder, or with the context menu's Move N Items to. A selected group or folder takes what is in it; the moved items stay selected; any that can't move are listed in one message while the others move
- Forms and modules in subfolders run: the program imports them by name from every folder holding one
- The Outline highlights the item the code editor's cursor is in: the function or method (inside its class), class, variable or top-level code, from a definition's first decorator to its last line; it follows as you move and type, in any sort order
- Panels sharing a place (Immediate and Output, Properties and Outline) have their tabs above them instead of below
- About VP6 shows the VP6 logo, and is in the Help menu on every platform (on macOS Qt had moved it to the application menu, where it also stays)

## Fixes

- The Project panel no longer uses `QTreeWidgetItemIterator`, whose items' Python wrappers could crash the IDE the next time the panel was refilled (e.g. after a drag and drop)

---

**Version:** 0.3.26
**Date:** 2026-09-30

## IDE

- The Project panel lists its forms and modules sorted by name, A to Z by default (they were in the order they were added to the project); its Name ▲/▼ button reverses the order, keeping the selected file selected, and the IDE remembers the choice

---

**Version:** 0.3.25
**Date:** 2026-09-30

## IDE

- The Outline window and the Properties panel take turns in one place: while a code window is active the Outline window replaces the Properties panel, and for a designer (or when no window is open) the Properties panel is back; View > Outline Window and F4 switch them by hand
- A panel closed with its close button stays closed (neither comes back by itself) until View > Outline Window or F4 opens it

---

**Version:** 0.3.24
**Date:** 2026-09-30

## Programming model (the `vp6` library)

- Menu negotiation, like VB's: a form shown in another form (`ShowIn`) has no menu bar of its own; while it is visible, its menu bar menus join the window's menu bar, placed by their `NegotiatePosition`: None (the default, not shown), Left (before the window's menus), Middle (after its first menu), Right (after its menus, before its own Right ones, e.g. Help); constants `vpNegotiateNone`, `vpNegotiateLeft`, `vpNegotiateMiddle`, `vpNegotiateRight`
- The merged menus leave when the form is hidden, replaced or unloaded; popped out with `ShowIn(None)` it has its own menu bar again; choosing a merged item or its Shortcut fires the inner form's handler; menus added in code and changed positions apply at once
- `Form.NegotiateMenus` (default True) on the window turns this on or off; a window without menus gets a menu bar for the merged ones
- Also on macOS: the merged menus are on the window's system menu bar, instead of an embedded form's bar attached to a child widget

## IDE

- The Menu Editor has VB's NegotiatePosition box

## Kitchen Sink

- The Menus page has a Page menu of its own that joins the window's menu bar while the page is visible; the window's Help menu has NegotiatePosition = Right, so it stays last

---

**Version:** 0.3.23
**Date:** 2026-09-30

## Programming model (the `vp6` library)

- Fix: `End()` ran every form's `Form_Unload` before ending the program (it closed the windows first), so e.g. a "Close?" question appeared and its answer was ignored; now it ends at once without any Unload event, like VB's `End` (the Kitchen Sink's File > End and the End button on its App page)

---

**Version:** 0.3.22
**Date:** 2026-09-30

## Kitchen Sink

- Redesigned explorer-style: Form1 is a window with a TreeView index of the topics on the left (with a Splitter), the page title across the top, a status bar across the bottom, and a scrolling content pane showing the chosen topic's page; all laid out with docked PictureBoxes (Align Bottom, Left, Top and Fill), without layout code
- Each topic is a page, a form of its own designed on its own (pgText, pgLists, …), shown in the content pane with `ShowIn`; a page is loaded the first time it's chosen and shown again afterwards; the first page is an introduction (a Markdown Label whose links open the pages)
- Pages: Text and labels, Buttons and options, Lists, Scroll bars, Pictures, Lines and z-order, TreeView, Timer (runs only while visible), Docked panes and Splitter, Scrolling (a page taller than the pane), Forms inside forms (pops out and back), Dialogs (MsgBox, InputBox, the modal dialog, Beep), Color schemes, Keyboard, Mouse, Control arrays, Menus, App/Screen/Clipboard/Debug/DoEvents/End
- Menus: File (End with Ctrl+Q, Close), View (the navigation pane, the color schemes as a menu control array kept in step with the Color schemes page), Bookmarks (a menu control array the Menus page adds pages to at run time), Help (Keys with F1, About)
- Closing the window asks first, then unloads every page (also one popped out)

## Controls

- The Splitter's bar uses the button color when it has no BackColor (it was drawn black in the designer)

---

**Version:** 0.3.21
**Date:** 2026-09-30

## Programming model (the `vp6` library)

- A form shown in a container (`ShowIn`) gets `Form_Activate` when it becomes visible there (after `Form_Load` the first time, and whenever it or its container is shown again) and `Form_Deactivate` when it stops being visible (hidden, its container hidden, replaced, moved out with `ShowIn(None)`); window activation no longer fires them for it; an unloaded form gets `Form_Unload`, not `Form_Deactivate`
- A form shown filling a container replaces the other forms filling it: they are hidden and deactivated, not unloaded, so coming back to one doesn't fire `Form_Load` again (forms shown with `Fill=False` are left alone)
- Fix: moving a form that was showing as a window into a container now activates it there

## Kitchen Sink

- frmEmbedded counts the seconds it has been visible in its pane: `Form_Activate` starts its Timer and `Form_Deactivate` stops it (e.g. when the pane is hidden)

---

**Version:** 0.3.20
**Date:** 2026-09-30

## Controls

- PictureBox `Align = 5 - Fill` (`vpAlignFill`): the PictureBox takes all the space the edge panes (Top, Bottom, Left, Right, Splitters) leave, placed after them whatever its creation order, and follows that space as the form resizes or a Splitter is dragged; several Fill panes share the space (hidden ones take none), e.g. one page per pane

## Kitchen Sink

- frmEmbedded is laid out with two docked panes instead of Form_Resize code: `picButtons` at the bottom and `picInfo` filling the rest, each sizing what is on it in its Resize event

---

**Version:** 0.3.19
**Date:** 2026-09-30

## Controls

- Label `TextFormat`: Plain (the default, as before), Rich Text (HTML: bold, italic, headings, colors, links) or Markdown (`**bold**`, `# heading`, lists, `[text](link)`); constants `vpPlainText`, `vpRichText`, `vpMarkdown`
- Label `LinkClick(URL)` event when a link in a formatted caption is clicked (also with the keyboard); without a handler, the link opens in the default browser; links aren't clickable in the designer
- A Label's Caption can have several lines, edited with the "…" button in the Properties window; in plain text `&` access-key marks are still hidden, formatted captions are shown as written

## Kitchen Sink

- frmEmbedded's description is a Markdown Label with bold text, code and a link that pops the form out

---

**Version:** 0.3.18
**Date:** 2026-09-30

## Controls

- PictureBox `ScrollBars` (None, Horizontal, Vertical, Both): the PictureBox scrolls the controls in it, with scroll bars that appear only when they reach beyond its edges in that direction (at run time); controls keep their positions and the picture stays in place
- `ScrollLeft` and `ScrollTop` read or set the scroll position (setting it right after adding controls works), and the PictureBox `Scroll` event fires when it changes (also by the mouse wheel); clicks on the empty area are still the PictureBox's `Click`
- Constants `vpSBNone`, `vpHorizontal`, `vpVertical`, `vpBoth` for `ScrollBars` (TextBox and PictureBox), like VB's
- A form shown in a scrolling PictureBox (`ShowIn`) fills the visible width and height but keeps at least its own designed size, so a taller form scrolls

## Kitchen Sink

- `picEmbed` has vertical scroll bars, and `frmEmbedded` is designed taller than the pane, which therefore scrolls down to its Pop out button

---

**Version:** 0.3.17
**Date:** 2026-09-30

## Controls

- Splitter control: a bar the user drags to resize a docked pane; it docks with `Align` (Left by default) like an aligned PictureBox, right after the pane it resizes (the nearest earlier control docked to the same edge)
- Dragging resizes the pane's Width (Left, Right) or Height (Top, Bottom) live, the right way for every edge; `Moved` fires when the user lets go; `MinSize` keeps both the pane and the space beside it from getting smaller; `BackColor`, `Enabled`, split cursors and a grip
- PictureBox `Resize` event, like VB's: fires when the PictureBox's size changes, e.g. when the form or a Splitter resizes a docked pane
- A PictureBox always paints its background (its `BackColor`, or the color scheme's window color), like VB's, so a docked pane covers what is underneath
- Docked panes are all in place before any `Resize` handler runs (moves are applied before resizes), and a docked pane's `Width`/`Height` is its thickness, applied by the form's layout

## IDE

- Splitter in the Toolbox, with its own icon; in the designer it docks beside the pane before it

## Kitchen Sink

- The TreeView index and the embedded form are in a side pane docked to the right, with a Splitter beside it; dragging it resizes the pane, whose `Resize` event keeps the index and the embedded form as wide as the pane, and the status bar stops at the Splitter

---

**Version:** 0.3.16
**Date:** 2026-09-30

## Controls

- PictureBox `Align` like VB (`vpAlignNone`, `vpAlignTop`, `vpAlignBottom`, `vpAlignLeft`, `vpAlignRight`): a PictureBox directly on the form docks to that edge of its client area and follows the form's size; Top and Bottom panes span the width and keep their Height, Left and Right panes span the height and keep their Width
- Several docked panes stack in the order they were created, each taking its edge of the space the earlier ones left; hidden panes take no space; setting a pane's Left or Top has no effect, its thickness can be changed at run time
- Panes are placed before `Form_Resize` fires, below an in-window menu bar, and also in a form shown in a container (`ShowIn`)

## IDE

- The designer docks aligned PictureBoxes live, also while the form is resized, and stores where they are docked; a docked pane dragged away goes back to its edge

## Kitchen Sink

- frmEmbedded's button sits on a PictureBox docked to the bottom (`Align = 2 - Bottom`) instead of being moved in `Form_Resize`

---

**Version:** 0.3.15
**Date:** 2026-09-29

## Programming model (the `vp6` library)

- Forms inside forms: `form.ShowIn(Container)` shows a form designed on its own inside a PictureBox or Frame of another form, or inside another form; `Form_Load` fires as for `Show`
- A form shown in a container fills it (inside a Frame: below the caption) and follows its size, firing `Form_Resize`; with `ShowIn(Container, Fill=False)` it keeps its size at its `Left` and `Top`
- `ShowIn(None)` makes it a window again, and `ShowIn` another container moves it there; `Form.Container` tells where it is (None for a window)
- While in a container, the form has no title bar and its `Caption`, `BorderStyle`, `WindowState` and `StartUpPosition` apply only as a window; it hides and shows with its container; its Default and Cancel buttons work inside it
- `Unload()` unloads just that form; when the host form unloads, the forms shown in it get `Form_Unload` after the host's own and can't cancel it, then become (hidden) windows again; a form can't be shown inside itself or a form it holds

## Kitchen Sink

- A new form, `frmEmbedded`, shown in Form1's PictureBox `picEmbed` below the TreeView index; its button pops it out into a window of its own and puts it back; closing the Kitchen Sink also closes it when popped out

---

**Version:** 0.3.14
**Date:** 2026-09-29

## IDE

- A form's designer window (the startup form when the IDE opens a project, or any form opened later) is just large enough to show the whole form with its window frame; if that doesn't fit, it fills the main area, like maximized but without maximizing (which would make the following windows open maximized too)
- Code windows and other windows open entirely inside the main area: they are made smaller if needed and moved in, also when a closed window is reopened
- Windows opened before the IDE's window is shown are fitted once it is

---

**Version:** 0.3.13
**Date:** 2026-09-29

## Controls

- TreeView control, like VB's: a hierarchical list of nodes with `LineStyle` (tree lines or root lines), `Indentation`, `Checkboxes`, `Sorted`, `PathSeparator`, colors, font and the common properties
- The `Nodes` collection: `Nodes(key)`, `Nodes[key]` or by Index from 1, `Count`, iteration, `in`, `Add(Relative, Relationship, Key, Text, Image)` with VB's relationships (`vpTvwFirst`, `vpTvwLast`, `vpTvwNext`, `vpTvwPrevious`, `vpTvwChild`), `Remove` (with the node's children) and `Clear`
- `Node` objects: `Text`, `Key`, `Tag`, `Index`, `FullPath`, `Expanded`, `Selected`, `Checked`, `Bold`, `ForeColor`, `Image` (a picture file), `Sorted` (its children), `EnsureVisible()`, and the relatives `Parent`, `Child`, `Children`, `Next`, `Previous`, `FirstSibling`, `LastSibling`, `Root`
- `SelectedItem` (read, or select a node by Node or key) and `HitTest(X, Y)`
- Events `NodeClick`, `Expand`, `Collapse` and `NodeCheck` get the Node; they fire for the user's actions (clicks, also on the selected node, and keyboard moves), not when code changes the tree; also Click, DblClick, the mouse, key and focus events
- Filling a TreeView in the designer, which VB couldn't: the `Items` property is an outline, one node per line, indented under its parent, with `|key` at the end to give a node a key; in code, assigning `Items` rebuilds the tree
- Constants `vpTvwFirst`, `vpTvwLast`, `vpTvwNext`, `vpTvwPrevious`, `vpTvwChild`, `vpTvwTreeLines`, `vpTvwRootLines`

## IDE

- TreeView in the Toolbox, with its own icon; the designer shows the whole outline expanded; the Properties window edits `Items` in a dialog ("(Tree: N nodes)")

## Kitchen Sink

- A TreeView index of the Kitchen Sink's sections on the right (the form is wider): nodes typed in the designer, one added in code with `vpTvwChild`, `NodeClick` naming the control a node's key points at, and `Expand` counting a node's children

---

**Version:** 0.3.12
**Date:** 2026-09-29

## Controls

- Image control, a lightweight picture like VB's: `Picture`, `Stretch`, `BorderStyle` (None or Fixed Single), `Enabled`, `Visible`, `ToolTipText`, `Tag`, `ZIndex` and position/size; events `Click`, `DblClick`, `MouseDown`, `MouseMove`, `MouseUp`
- Unlike a PictureBox, an Image isn't a container, never takes the focus (no `TabIndex`) and has a transparent background; a disabled Image isn't grayed, it just gets no events
- With `Stretch = False` an Image takes the size of its picture (plus its border), also when the picture or the border changes at run time; with `Stretch = True` the picture is scaled to fill it

## IDE

- Image in the Toolbox, with its own icon; in the designer, choosing a picture for an Image without Stretch resizes it to the picture

## Kitchen Sink

- A stretched Image thumbnail of the logo under the big picture; clicking it shows or hides the big picture

---

**Version:** 0.3.11
**Date:** 2026-09-29

## IDE

- Fix: hovering the mouse over an end of a selected Line in the designer raised an error (`KeyError: 'p2'`) instead of showing the move cursor

## Tests

- A test now fails when Python code called by Qt raises (an event handler such as `mouseMoveEvent`, or a slot run from the event loop); PySide only printed those errors, so such bugs could hide behind a passing run

---

**Version:** 0.3.10
**Date:** 2026-09-29

## Controls

- Line control: a straight line from (`X1`, `Y1`) to (`X2`, `Y2`) in its container's coordinates, with `BorderColor` (unset: the color scheme's text color, so it follows light/dark), `BorderStyle` (Transparent, Solid, Dash, Dot, Dash-Dot, Dash-Dot-Dot, Inside Solid), `BorderWidth`, `Visible`, `Tag` and `ZIndex`; all changeable at run time with immediate effect
- A Line has no events and never takes the focus; clicks go through it to what is underneath

## IDE

- Line in the Toolbox (with its own icon): draw it from where the mouse is pressed to where it's released (a click makes a 100-pixel horizontal line)
- Selecting a Line by clicking near it (not anywhere in its bounding box, which may cover other controls); handles at its two ends drag one end, dragging the line moves it; the ends snap to the grid of its container (Alt: no snapping)
- Arrow keys move a Line, Shift+arrows don't resize it; pasted Lines are offset like other controls

## Kitchen Sink

- A dashed white Line over the Z-order labels (ZIndex 3), and a gray divider above the status bar that `Form_Resize` stretches to the window width

---

**Version:** 0.3.9
**Date:** 2026-09-29

## Programming model (the `vp6` library)

- Menus on forms: the `Menu` control, whose parent is the form (a menu on the menu bar) or another menu (an item or submenu of it), e.g. `self.mnuFileOpen = Menu(self.mnuFile, Caption='&Open...', Shortcut='Ctrl+O')`
- Menu properties: `Caption` (`&` access keys; `-` makes a separator line), `Checked`, `Enabled`, `Visible`, `Shortcut` (VB's list of keys: Ctrl+A..Z, F1..F12, Ctrl/Shift/Ctrl+Shift+F-keys, Ctrl+Shift+A..Z, Ctrl+Ins, Shift+Ins, Del, Shift+Del, Alt+Backspace) and `Tag`, all changeable at run time
- Menu `Click` event: when an item is chosen (also with its shortcut), and for a menu with items just before it opens; choosing an item doesn't change `Checked` (the handler does, like VB)
- Menu control arrays, e.g. a recent files list: `Load(self.mnuRecent, i)` adds an item right after the array's last element, `Unload` removes it
- On Windows and Linux the menu bar is inside the window, above the form's area: the window grows, and `Height`, `ScaleHeight` and control positions stay those of the area below the menu bar; on macOS the menus are in the macOS menu bar

## IDE

- Menu Editor (Tools > Menu Editor, Ctrl+E, also in the designer's context menu), like VB's: Caption, Name, Index, Shortcut, Checked, Enabled and Visible for each item; ← → to change an item's level, ↑ ↓ to move it, Next, Insert and Delete; the indented list of all items; OK checks the menus (names, arrays, levels, separators)
- Renaming a menu in the Menu Editor renames its event handlers; making it a control array (or not) adds (or removes) their `Index` parameter; one undo step
- The designer shows the form's menu bar under the title bar in every frame style; clicking a menu there shows its drop-down as it will look (shortcuts, check marks, separators, submenus), and choosing an item opens its Click code
- Menus appear in the Properties window's object list and can be edited there (including the Shortcut list); they aren't on the canvas, so selecting, aligning, copying and moving leave them out
- Menus appear in the code window's Object list with their Click event

## Kitchen Sink

- File (Dialog... with Ctrl+D, a separator, Close), View (Clock running, checked while the clock runs; the color schemes as the menu control array `mnuScheme`, whose check marks follow the option buttons) and Help (Keys, About) menus

---

**Version:** 0.3.8
**Date:** 2026-09-29

## Programming model (the `vp6` library)

- Control arrays: controls of one type sharing a name, told apart by `Index` (0 - 32767, not necessarily contiguous), declared as `self.cmdDigit = ControlArray()` with elements `self.cmdDigit[0] = CommandButton(...)`
- One event handler per control array, getting the element's `Index` first: `def cmdDigit_Click(self, Index)`, `def cmdDigit_MouseDown(self, Index, Button, Shift, X, Y)`
- Elements as `self.cmdDigit[i]`, VB's `self.cmdDigit(i)` or `Item(i)`; iteration in Index order, `Count`, `len()`, `LBound`, `UBound`, `i in array`
- `Load(self.cmdDigit, i)` / `self.cmdDigit.Load(i)` adds an element at run time (a hidden copy of the lowest element, last in the tab order); `Unload(self.cmdDigit, i)` removes elements added that way
- Every control has a read-only `Index` (`None` outside control arrays); control array elements can be containers (`CheckBox(self.fraGroup[1], ...)`)

## IDE

- Creating control arrays in the designer like VB: pasting a copy of a control asks "You already have a control named ... Do you want to create a control array?"; further copies join the array without asking
- Giving a control the name of another control of the same type asks the same question and makes it an element of that array; giving it a new name takes it out
- Index property in the Properties window, right under (Name): makes a control a one-element array, moves an element to another Index, or (cleared) makes a lone element a plain control again
- When a control becomes a control array (or stops being one), its event handlers get the `Index` parameter added (or removed); new handlers are created with it
- The Properties window lists elements as `cmdDigit(0)`; the code window's Object list shows an array once; completion knows `ControlArray` members (`self.cmdDigit.`) and element members (`self.cmdDigit[i].`, `self.cmdDigit(i).`)
- Fix: possible crashes when a code window or designer was closed or deleted while a deferred update was pending (deferred calls now have a context object; the designer follows OS light/dark changes through a bound method)

## Kitchen Sink and samples

- Kitchen Sink: the color-scheme option buttons are the control array `optScheme` with one handler, and the `cmdMore` "+" button loads and unloads control array elements at run time
- The Calculator sample uses control arrays (`cmdDigit`, `cmdOperator`) instead of attaching handlers in code

---

**Version:** 0.3.7
**Date:** 2026-09-29

## IDE

- Find as you type: while you type the text to find (or change Match case, Whole word or Regular expressions), the code window highlights the first match from the cursor, wrapping around the file; the match grows as you type, nothing stays highlighted when there's no match, and an unfinished regular expression doesn't move the selection

---

**Version:** 0.3.6
**Date:** 2026-09-29

## IDE

- Edit > Go to Line (Ctrl+L / ⌘L): jump to a line of the current code window; the current line is suggested, and a line in the folded designer region unfolds it
- Edit > Find (Ctrl+F / ⌘F), Find Next (F3), Find Previous (Shift+F3) and Replace (Ctrl+H, or ⌥⌘F on macOS) in the code window: a non-modal Find/Replace window with Find Next, Find Previous, Replace and Replace All; searches wrap around the file; the selected text is the default text to find; with a form designer active, its form's code is searched
- Find and Replace options: Match case, Find whole word only, and Use regular expressions (Python `re`: escape sequences such as `\n` and `\t`, matches across lines, `^`/`$` on every line, groups in the find text such as `(\w+) \1` and in the replace text such as `\1`, `\g<1>`, `\g<name>`)
- Replace All is one undo step and reports how many occurrences it replaced; matches in a form's designer region are found (unfolding it) but never replaced
- A form selected in the Project Explorer shows all its properties and controls in the Properties panel, editable, without opening its designer (also for a form's code window when the Project panel is closed)
- `TabIndex` is renumbered automatically, like VB: new and pasted controls go to the end of the tab order, deleting controls closes the gap, and giving a control a `TabIndex` moves it to that place while the others make room (one undo step)
- Fix: a form can no longer be renamed to the name of another form in the project

---

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

- VB6-style GUI programming in Python: `from vp6 import *`
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
