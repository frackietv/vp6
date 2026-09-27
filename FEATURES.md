# VP6 features

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
