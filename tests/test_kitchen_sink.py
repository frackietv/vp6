"""The Kitchen Sink template must keep demonstrating everything VP6 offers.

If a test here fails after you added a control, event or API function to
VP6: demonstrate it in vp6/ide/templates/kitchensink/ (see the development
guide, "Keep the Kitchen Sink up to date").
"""

import importlib
import os
import re
import shutil
import sys

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

import vp6
from vp6 import formfile
from vp6.controls import CONTROL_TYPES
from vp6.ide import kitchensink
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.mainwindow import create_project
from vp6.project import SUB_MAIN, Project
from vp6.usercontrol import load_user_control, register_user_control

UPDATE_HINT = "update the Kitchen Sink (vp6/ide/templates/kitchensink/)"


def template_sources() -> dict[str, str]:
    return {name: (kitchensink.TEMPLATE_DIR / name).read_text()
            for name in kitchensink.FORMS + kitchensink.MODULES + kitchensink.USER_CONTROLS}


@pytest.fixture(autouse=True)
def _kitchen_sink_user_controls(qapp):
    """Its user controls are control types, as the IDE makes them when it opens the
    project (the forms using them can be read and designed); gone after each test."""
    for name in kitchensink.USER_CONTROLS:
        register_user_control(load_user_control(str(kitchensink.TEMPLATE_DIR / name)))


def form_defs() -> dict[str, formfile.FormDef]:
    return {name: formfile.parse(source) for name, source in template_sources().items()
            if name in kitchensink.FORMS}


# --- coverage: fails when VP6 grows and the Kitchen Sink doesn't ----------------------------

def test_every_control_type_is_used():
    used = {c.type for form in form_defs().values() for c in form.controls}
    missing = sorted(set(CONTROL_TYPES) - used)
    assert not missing, f"Controls not in the Kitchen Sink: {missing} - {UPDATE_HINT}"


def test_every_public_api_name_is_used():
    code = "\n".join(template_sources().values())
    names = [n for n in vp6.__all__ if not n.startswith("vp")]  # constants are too many
    missing = [n for n in names if not re.search(rf"\b{re.escape(n)}\b", code)]
    assert not missing, f"API names not used in the Kitchen Sink: {missing} - {UPDATE_HINT}"


def test_every_control_type_handles_its_default_event():
    handled = set()
    for filename, form in form_defs().items():
        methods = set(formfile.defined_methods(template_sources()[filename]))
        for control in form.controls:
            event = CONTROL_TYPES[control.type].DefaultEvent
            if f"{control.name}_{event}" in methods:
                handled.add(control.type)
    with_events = {name for name, cls in CONTROL_TYPES.items() if cls.Events}  # not Line
    missing = sorted(with_events - handled)
    assert not missing, f"No default-event handler for: {missing} - {UPDATE_HINT}"


def test_every_color_scheme_is_demonstrated():
    code = "\n".join(template_sources().values())
    for name in ("vpSchemeSystem", "vpSchemeLight", "vpSchemeDark", "vpSchemeIDE"):
        assert name in code, f"{name} not demonstrated - {UPDATE_HINT}"


def test_designer_regions_are_canonical():
    # Regenerating a region must not change it, so the IDE opens the forms cleanly
    for filename, source in template_sources().items():
        if filename in kitchensink.FORMS + kitchensink.USER_CONTROLS:
            assert formfile.replace_region(source, formfile.parse(source)) == source, filename


# --- creating and using the project -----------------------------------------------------------

def test_create_kitchen_sink_project(qapp, tmp_path):
    path = create_project(str(tmp_path), "Sink", "kitchensink")
    project = Project.load(path)
    assert project.forms == list(kitchensink.FORMS)  # the window, its pages, the dialog
    assert project.modules == ["Module1.py"]  # like every new project: Form1 and Module1
    assert project.user_controls == ["ctlRating.py"]
    assert project.group_of("ctlRating.py") == ("User Controls",)
    assert project.startup == SUB_MAIN and project.type == "exe"
    folder = tmp_path / "Sink"
    for name in kitchensink.FORMS + kitchensink.MODULES + kitchensink.USER_CONTROLS:
        assert (folder / name).read_text() == (kitchensink.TEMPLATE_DIR / name).read_text()
    assert not QPixmap(str(folder / kitchensink.PICTURE)).isNull()
    for name in kitchensink.ICONS:  # the ImageLists' pictures
        assert not QPixmap(str(folder / kitchensink.IMAGES / f"{name}.png")).isNull()


def test_designer_opens_every_form(qapp, tmp_path):
    create_project(str(tmp_path), "Sink", "kitchensink")
    for name in kitchensink.FORMS:
        designer = FormDesigner(FormDocument(str(tmp_path / "Sink" / name)),
                                str(tmp_path / "Sink"))
        problems = []
        designer.statusMessage.connect(problems.append)
        designer.load_def(designer.document.form_def)
        assert not problems, problems
        assert set(designer.controls) == {c.key for c in designer.form_def.controls}


@pytest.fixture
def sink(qapp, tmp_path, monkeypatch):
    """A new Kitchen Sink project's window, running in this process. Message
    boxes answer Yes and input boxes "Zed"."""
    create_project(str(tmp_path), "Sink", "kitchensink")
    folder = str(tmp_path / "Sink")
    sys.path.insert(0, folder)
    names = [name[:-3] for name in kitchensink.FORMS]
    modules = {name: importlib.import_module(name) for name in names}
    for module in modules.values():
        monkeypatch.setattr(module, "MsgBox", lambda *args, **kwargs: vp6.vpYes, raising=False)
        monkeypatch.setattr(module, "InputBox", lambda *args, **kwargs: "Zed", raising=False)
    monkeypatch.setattr(modules["pgGlobals"].time, "sleep", lambda seconds: None)
    window = modules["Form1"].Form1()
    window.Show()
    QTest.qWait(20)
    yield window
    if window._loaded:
        window.Unload()
    sys.path.remove(folder)
    for name in names + ["Module1", "ctlRating"]:
        sys.modules.pop(name, None)


def _page(window, key):
    """Show a page like choosing it in the index, and return it."""
    window.tvwIndex_NodeClick(window.tvwIndex.Nodes(key))
    return window.pages[key]


def _status(window):
    """The text in the window's StatusBar."""
    return window.sbStatus.Panels("status").Text


def _place(control):
    return control.Left, control.Top, control.Width, control.Height


# --- the explorer window -------------------------------------------------------------------------

def test_explorer_layout(sink):
    w = sink
    assert _place(w.sbStatus) == (0, w.ScaleHeight - 28, w.ScaleWidth, 28)  # a StatusBar
    top = w.tbrMain.Height  # a Toolbar across the top, as tall as its buttons
    assert _place(w.tbrMain) == (0, 0, w.ScaleWidth, top) and top > 20
    assert _place(w.picNav) == (0, top, 220, w.ScaleHeight - 28 - top)  # Left
    assert (w.splNav.Left, w.splNav.Width) == (220, 6)  # the Splitter beside it
    assert _place(w.picHeader) == (226, top, w.ScaleWidth - 226, 44)  # Top of the rest
    assert _place(w.picContent) == (226, top + 44, w.ScaleWidth - 226,
                                    w.ScaleHeight - 72 - top)  # Fill
    assert w.tvwIndex.Parent is w.picNav and w.tvwIndex.Width == 220  # picNav_Resize
    w.Width, w.Height = 1000, 700
    QTest.qWait(20)
    assert _place(w.picContent) == (226, top + 44, 774, 628 - top)  # follows the window
    bar = w.splNav._widget
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, QPoint(3, 100))
    QTest.mouseMove(bar, QPoint(43, 100))  # dragged 40 pixels to the right
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, QPoint(3, 100))
    assert w.picNav.Width == 260 and w.picContent.Left == 266
    assert _status(w) == "The navigation pane is now 260 pixels wide"  # Moved
    w.mnuViewNav._action.trigger()  # View > Navigation pane: hidden panes take no space
    assert not w.picNav.Visible and w.picContent.Left == 0 and not w.mnuViewNav.Checked


def test_status_bar(sink):
    bar = sink.sbStatus
    assert [panel.Key for panel in bar.Panels] == ["status", "caps", "clock"]
    assert bar.Panels("status").AutoSize == vp6.vpSbrSpring  # the space left
    clock = bar.Panels("clock")
    assert clock.Style == vp6.vpSbrTime
    sink.sbStatus_PanelClick(clock)  # a click on the clock: the date, and back
    assert clock.Style == vp6.vpSbrDate and _status(sink) == "The clock shows the date"
    QTest.mouseClick(bar._widget, Qt.LeftButton, Qt.NoModifier, clock._label.geometry().center())
    assert clock.Style == vp6.vpSbrTime


def test_toolbar(sink):
    bar = sink.tbrMain
    assert [b.Key for b in bar.Buttons if b.Style != vp6.vpTbrSeparator] == [
        "back", "forward", "nav", "scheme0", "scheme1", "scheme2"]
    assert all(not b._action.icon().isNull() for b in bar.Buttons if b.Key)  # imlToolbar
    bar.Buttons("forward")._action.trigger()  # ButtonClick: the next page
    assert sink.lblTitle.Caption == "Text and labels"
    bar.Buttons("back")._action.trigger()
    bar.Buttons("back")._action.trigger()  # from the first page: round to the last
    assert sink.current == sink.page_titles()[-1][0]
    nav = bar.Buttons("nav")
    nav._action.trigger()  # a Check button: unpressed hides the pane
    assert nav.Value == vp6.vpTbrUnpressed and not sink.picNav.Visible
    sink.mnuViewNav._action.trigger()  # the menu shows it: the button follows
    assert nav.Value == vp6.vpTbrPressed and sink.picNav.Visible
    bar.Buttons("scheme2")._action.trigger()  # a ButtonGroup: Dark, and the menu follows
    assert sink.scheme == 2 and sink.mnuScheme[2].Checked
    assert [bar.Buttons(f"scheme{i}").Value for i in range(3)] == [0, 0, 1]
    sink.mnuScheme[3]._action.trigger()  # Follow the IDE: none of the group pressed
    assert [bar.Buttons(f"scheme{i}").Value for i in range(3)] == [0, 0, 0]


def test_intro_and_navigation(sink):
    w = sink
    intro = w.pages["intro"]
    assert w.lblTitle.Caption == "Introduction" and intro.Container is w.picContent
    assert intro.lblIntro._widget.textFormat() == Qt.MarkdownText
    intro.lblIntro._widget.linkActivated.emit("lists")  # a link in the introduction
    assert w.lblTitle.Caption == "Lists" and w.pages["lists"].Visible and not intro.Visible
    assert w.tvwIndex.SelectedItem is w.tvwIndex.Nodes("lists")
    assert _status(w) == "Controls\\Lists"
    w.tvwIndex_NodeClick(w.tvwIndex.Nodes("forms_section"))  # a section: its first page
    assert w.lblTitle.Caption == "Dialogs"


def test_every_page_opens_once(sink):
    w = sink
    pages = sink_pages = w.page_titles()
    assert [key for key, _ in pages] == list(sys.modules["Form1"].PAGES)
    for key, title in sink_pages:
        page = _page(w, key)
        assert page.Visible and page.Container is w.picContent and w.lblTitle.Caption == title
        assert page.ScaleWidth >= w.picContent._scroll_area.viewport().width() - 1
        visible = [p for p in w.pages.values() if p.Visible]
        assert visible == [page]  # the page replaces the one shown before
    first = w.pages["text"]
    assert _page(w, "text") is first  # shown again, not loaded again


# --- the pages -------------------------------------------------------------------------------------

def test_text_page(sink):
    page = _page(sink, "text")
    QTest.keyClicks(page.txtUpper._widget, "abc")
    assert page.txtUpper.Text == "ABC"  # KeyPress transformation
    page.cmdGreet._widget.click()  # no name: InputBox asks for one
    assert page.txtName.Text == "Zed" and page.lblInfo.Caption == "Hello, Zed!"  # Change
    page.fraAlign_Click()
    assert "containers" in page.lblInfo.Caption
    assert page.lblAuto.Width < 150  # AutoSize fits the text
    # Access keys: the label's letter underlined; the key focuses the box after it
    assert page.lblPassword.AccessKey == "P" and "<u>P</u>" in page.lblPassword._widget.text()
    page.lblPassword._shortcut.activated.emit()
    assert page._widget.window().focusWidget() is page.txtPassword._widget
    assert page.lblKeys.AccessKey == "" and "Rock & Roll" in page.lblKeys._widget.text()


def test_rich_text_page(sink, monkeypatch, tmp_path):
    page = _page(sink, "richtext")
    doc = page.rtbDoc
    assert doc.Text.startswith("A RichTextBox has text in colors")
    assert doc.Text.endswith("A larger blue line, added with SelText")
    assert page.lblCount.Caption == f"{len(doc.Text.split())} words, {len(doc.Text)} characters"
    doc.SelStart, doc.SelLength = 0, 13  # "A RichTextBox": SelChange shows its format
    assert page.chkBold.Value == vp6.vpChecked and page.chkItalic.Value == vp6.vpUnchecked
    assert "Line 1, position 0, 13 selected" == page.lblStatus.Caption
    page.chkItalic.Value = vp6.vpChecked  # the buttons format the selection
    assert doc.SelItalic and doc.SelBold
    page.cboColor.ListIndex = 3
    assert doc.SelColor == sys.modules["pgRichText"].BLUE
    page.cboSize.ListIndex = 3
    assert doc.SelFontSize == 18
    page.optAlign[1].Value = True
    assert doc.SelAlignment == vp6.vpCenter
    start = doc.Text.index("colors")
    doc.SelStart, doc.SelLength = start, 6  # red text: the color shown
    assert page.cboColor.ListIndex == 1 and page.optAlign[1].Value  # Red, centered
    page.txtFind.Text = "vp6"
    page.cmdFind_Click()
    assert doc.SelText == "VP6" and "(1 in all)" in page.lblStatus.Caption
    page.chkCase.Value = vp6.vpChecked
    page.cmdFind_Click()
    assert "isn't there" in page.lblStatus.Caption
    page.txtFind.Text, page.chkCase.Value = "line", vp6.vpUnchecked
    page.chkWord.Value = vp6.vpChecked
    page.cmdFind_Click()
    assert doc.SelText == "line" and "(1 in all)" in page.lblStatus.Caption
    module = sys.modules["pgRichText"]
    monkeypatch.setattr(module, "SAVED", str(tmp_path / "saved.html"))
    monkeypatch.setattr(module, "SAVED_TEXT", str(tmp_path / "saved.txt"))
    page.cmdSave_Click()
    assert page.cmdLoad.Enabled and (tmp_path / "saved.txt").read_text() == doc.Text
    text = doc.Text
    doc.Text = ""
    page.cmdLoad_Click()
    assert doc.Text == text
    doc.SelStart, doc.SelLength = 0, 13
    assert doc.SelBold and doc.SelItalic  # (the formatting came back)
    for _ in range(3):
        page.cmdLog_Click()
    log = page.rtbLog
    assert log.Locked and log.Text.count("\n") == 3 and "WARNING message 1" in log.Text
    assert "ERROR message 2" in log.Text and "INFO message 3" in log.Text
    position = log.Text.index("ERROR")
    log.SelStart, log.SelLength = position, 5
    assert log.SelColor == vp6.vpRed and log.SelBold


def test_editing_page(sink):
    page = _page(sink, "editing")
    code = page.txtCode
    assert code.LineCount == 10 and not page.cmdUndo.Enabled  # (loading: nothing to undo)
    code.SetFocus()
    code.CurrentLine, code.CurrentColumn = 3, 4  # SelChange: where the caret is
    assert page.lblPosition.Caption == "Line 4, column 5 of 10 lines"
    page.cmdIndent_Click()
    assert code.GetLine(3) == "        print(message)" and code.CurrentColumn == 8
    assert page.cmdUndo.Enabled
    page.cmdUndo_Click()
    assert code.GetLine(3) == "    print(message)" and page.cmdRedo.Enabled
    page.cmdRedo_Click()
    assert code.GetLine(3).startswith("        print")
    page.txtLine.Text = "9"
    page.cmdGoTo_Click()
    assert code.CurrentLine == 8 and "Line 9" in page.lblPosition.Caption
    page.txtLine.Text = "99"
    page.cmdGoTo_Click()
    assert page.lblPosition.Caption == "There are 10 lines"
    code.CurrentLine = 9  # Tab types a tab (AcceptsTab), "pr" offers completions
    QTest.keyClick(code._widget, Qt.Key_Tab)
    QTest.keyClicks(code._widget, "pr")
    assert page.lstComplete.Visible and page.lstComplete.List == ["print"]
    assert page.lstComplete.Left == code.Left + code.CaretLeft  # under the caret
    assert page.lstComplete.Top == code.Top + code.CaretTop + code.CaretHeight + 2
    QTest.keyClick(code._widget, Qt.Key_Return)  # Enter takes it
    assert code.GetLine(9) == "\tprint" and not page.lstComplete.Visible
    QTest.keyClicks(code._widget, "(gr")  # a click takes one
    assert page.lstComplete.List == ["greet"]
    page.lstComplete.ListIndex = 0
    assert code.GetLine(9) == "\tprint(greet" and not page.lstComplete.Visible
    QTest.keyClicks(code._widget, " me")
    assert page.lstComplete.List == ["message"]
    QTest.keyClick(code._widget, Qt.Key_Escape)  # Esc closes them
    assert not page.lstComplete.Visible and code.GetLine(9) == "\tprint(greet me"
    code.SelStart = code.GetCharFromLine(2) + 6  # the word under the mouse
    page.txtCode_MouseMove(0, 0, code.CaretLeft + 2, code.CaretTop + code.CaretHeight // 2)
    assert page.lblMouse.Caption == "Under the mouse: message"


def test_code_page(sink):
    page = _page(sink, "code")
    code = page.codSample
    assert page.region == (6, 10) and code.IsLineProtected(6) and code.IsLineProtected(10)
    assert code.LineMarker(6) == "-" and code.Language == 1
    todo_line = next(n for n in range(code.LineCount) if "TODO" in code.GetLine(n))
    block = code._widget.document().findBlockByNumber(todo_line)
    backgrounds = [QColor(r.format.background().color()).name() for r in block.layout().formats()]
    assert "#ffdc50" in backgrounds  # TODO marked by the Highlight event
    page.codSample_GutterClick(13)  # a breakpoint, and off again
    assert code.LineMarker(13) == "\u25cf" and "Breakpoint on line 14" in page.lblEvent.Caption
    page.codSample_GutterClick(13)
    assert code.LineMarker(13) == ""
    page.codSample_GutterClick(6)  # the region's line: fold it
    assert code.IsLineHidden(7) and code.IsLineHidden(10) and code.LineMarker(6) == "+"
    assert page.cmdFold.Caption == "Un&fold region" and "hidden" in page.lblEvent.Caption
    page.cmdFold_Click()
    assert not code.IsLineHidden(7) and code.LineMarker(6) == "-"
    code.SetFocus()  # typing in the region: refused
    code.CurrentLine, code.CurrentColumn = 8, 0
    QTest.keyClicks(code._widget, "x")
    assert not code.GetLine(8).startswith("x") and "Line 9 is protected" in page.lblEvent.Caption
    code.CurrentLine, code.CurrentColumn = 0, 0  # a line above: the region moves down
    QTest.keyClick(code._widget, Qt.Key_Return)
    assert page.region == (7, 11) and code.IsLineProtected(7)
    page.codSample_GutterClick(7)
    assert code.IsLineHidden(8)
    page.chkNumbers.Value = vp6.vpUnchecked
    page.chkCurrent.Value = vp6.vpUnchecked
    page.chkWrap.Value = vp6.vpChecked
    page.chkPython.Value = vp6.vpUnchecked
    assert not code.LineNumbers and not code.HighlightCurrentLine and code.WordWrap
    assert code.Language == 0


def test_user_control_page(sink):
    page = _page(sink, "usercontrol")
    food, service, critics = page.rtgFood, page.rtgService, page.rtgFixed
    assert (food.Value, food.Max) == (4, 5) and (service.Value, service.Max) == (2, 3)
    assert [s.Visible for s in service.lblStar] == [True, True, True, False, False]
    assert [s.Caption for s in food.lblStar] == ["\u2605"] * 4 + ["\u2606"]
    assert food.lblStar[0].ForeColor == food.StarColor and food.lblStar[4].ForeColor is None
    assert page.lblAverage.Caption == "Average: 3.4 of 5 stars"
    QTest.mouseClick(service.lblStar[2]._widget, Qt.LeftButton)  # its own control's Click
    assert service.Value == 3 and page.lblEvent.Caption == "Service: 3 of 3 stars (Change)"
    QTest.mouseMove(food.lblStar[1]._widget)  # Hover: the rating the mouse is on
    assert page.lblEvent.Caption == "Food: 2 stars? (Hover)"
    page.cmdReset._widget.click()  # Value from code: Change comes here too
    assert food.Value == 0 and page.lblEvent.Caption == "Food: 0 stars (Change)"
    QTest.mouseClick(critics.lblStar[4]._widget, Qt.LeftButton)  # Locked: no change
    assert critics.Value == 3
    food.Max = 9  # (kept from 1 to 5)
    food.Value = -2
    assert food.Max == 5 and food.Value == 0


def test_buttons_page(sink):
    page = _page(sink, "buttons")
    page.cmdAuto._widget.click()  # sets cmdClick.Value = True
    assert page.lblClicks.Caption == "Clicked 1 times"
    page.chkBold.Value = vp6.vpChecked
    assert page.lblSample.FontBold
    page.optLarge.Value = True
    assert page.lblSample.FontSize == 20 and page.optBlack.Value  # another group: unchanged
    page.optBlue.Value = True
    assert page.lblSample.ForeColor == vp6.vpBlue and page.optLarge.Value
    page.chkUnderline._widget.click()  # a Graphical CheckBox: a toggle button
    assert page.chkUnderline.Value == vp6.vpChecked and page.lblSample.FontUnderline
    page.optAlign[2]._widget.click()  # Graphical OptionButtons: one of them pressed
    assert page.lblSample.Alignment == vp6.vpRightJustify and not page.optAlign[0].Value
    assert not page.cmdStar._widget.icon().isNull()  # a picture button
    page.cmdStar._widget.click()
    assert "picture button" in page.lblClicks.Caption
    hop = page.cmdHop  # moved into the Basket frame and out again (Container)
    hop._widget.click()
    assert hop.Container is page.fraBasket and (hop.Left, hop.Top) == (45, 50)
    assert hop._widget.parent() is page.fraBasket._container_widget() and hop.Visible
    assert page.lblClicks.Caption == "cmdHop is in fraBasket" and hop.Caption == "&Hop out"
    hop._widget.click()
    assert hop.Container is page and (hop.Left, hop.Top) == (470, 330)
    assert page.lblClicks.Caption == "cmdHop is in pgButtons"

def test_lists_page(sink):
    page = _page(sink, "lists")
    page.txtItem.Text = "Delta"
    assert page.cmdAdd.Enabled  # Change event
    page.cmdAdd._widget.click()
    assert "Delta" in page.lstItems.List and page.txtItem.Text == ""
    page.lstItems.ListIndex = 0
    assert page.lblSelected.Caption.startswith("Selected 'Alpha'")
    page.cmdRemove._widget.click()
    assert page.lstItems.ListCount == 3
    page.cboColors.ListIndex = page.cboColors.List.index("Red")
    assert page.lblSwatch.BackColor == vp6.vpRed  # from the item's ItemData
    assert page.cboColors.ItemForeColor[1] == vp6.vpRed and page.cboColors.ItemBold[0]
    delta = page.lstItems.List.index("Delta")  # added: a star, in italics, and its time
    assert page.lstItems.ItemImage[delta] == "star" and page.lstItems.ItemItalic[delta]
    assert page.lstItems.ItemData[delta] > 0
    assert page.lstItems.ItemImage[0] == "leaf"
    assert page.lstItems.TopIndex >= 0
    toppings = page.lstToppings  # a Checkbox ListBox: ItemCheck, SelCount
    toppings._widget.item(1).setCheckState(Qt.Checked)  # the user checks Ham
    assert page.lblToppings.Caption == "1 chosen (Ham checked)" and toppings.Selected(1)
    page.cboSimple.ListIndex = 2  # a Simple Combo
    assert page.lblSimple.Caption == "Size: Large"
    page.cboFree.Text = "mango"
    page.cboFree._widget.showPopup()  # DropDown: what was typed is added
    page.cboFree._widget.hidePopup()
    new = page.cboFree.NewIndex
    assert page.cboFree.List[new] == "mango" and page.cboFree.ItemBold[new]
    page.cboFree.Text = "kiwi"
    assert page.lblEcho.Caption == "kiwi"


def test_scroll_bars_page(sink):
    page = _page(sink, "scrollbars")
    page.hsbSize.Value = 16
    assert page.lblSizeValue.Caption == "16" and page.lblSample.FontSize == 16
    page.vsbLevel.Value = 80
    assert page.lblLevel.Caption == "80"


def test_values_page(sink):
    page = _page(sink, "values")
    page.sldVolume.Value = 70  # Slider: Change
    assert page.lblVolumeValue.Caption == "70" and "Change" in page.lblSliderEvent.Caption
    page.sldLevel.Value = 25  # a vertical ProgressBar follows the vertical Slider
    assert page.prgLevel.Value == 25
    page.cmdStart._widget.click()  # a ProgressBar filled by a Timer
    assert page.tmrWork.Enabled and not page.cmdStart.Enabled
    for _ in range(50):
        page.tmrWork_Timer()
    assert page.prgWork.Value == 100 and page.lblWork.Caption == "Done"
    assert not page.tmrWork.Enabled and page.cmdStart.Enabled
    page.udCopies._widget.up.click()  # UpDown with a TextBox buddy
    assert page.txtCopies.Text == "2" and page.lblTotal.Caption == "Total: 8 EUR"
    assert page.lblUpDownEvent.Caption == "UpClick"
    page.udDay._widget.down.click()  # wraps around; a Label buddy
    assert page.lblDay.Caption == "7" and page.lblDayName.Caption == "Sunday"


def test_pictures_page(sink):
    page = _page(sink, "pictures")
    assert page.lblOnPicture.Parent is page.picLogo  # a Label inside the PictureBox
    assert not page.imgThumb._widget.pixmap().isNull() and page.imgThumb.Width == 64
    QTest.mouseClick(page.imgThumb._widget, Qt.LeftButton)
    assert not page.picLogo.Visible and page.chkPicture.Value == vp6.vpUnchecked
    QTest.mouseClick(page.imgThumb._widget, Qt.LeftButton)
    assert page.picLogo.Visible
    page.lblOnPicture_Click()  # InputBox: the Tag
    assert page.picLogo.Tag == "Zed" and page.lblOnPicture.Caption == "Zed"
    # An opaque label (the default) over the picture, and a transparent one
    assert page.lblOnPicture.BackStyle == vp6.vpOpaque
    assert page.lblTransparent.BackStyle == vp6.vpTransparent
    assert not page.lblTransparent._widget.autoFillBackground()


def test_z_order_page(sink):
    page = _page(sink, "zorder")
    widget = page._widget
    overlap = QPoint(100, 50)  # inside both lblZRed (16,16 132x40) and lblZBlue (80,28)

    def on_top():
        return widget.childAt(overlap)._vp_control.Name

    assert on_top() == "lblZRed"  # ZIndex 2 beats 1, although created first
    page.cmdSwapZ._widget.click()
    assert on_top() == "lblZBlue" and page.lblZBlue.Caption == "Blue: ZIndex 2"
    page.lblZRed_Click()  # ZOrder(0): above linZ (3) too
    assert on_top() == "lblZRed" and page.lblZRed.ZIndex == 4
    assert [line.BorderStyle for line in page.linSample] == [1, 2, 3, 4, 5]
    assert page.linZ.ZIndex == 3 and page.linThick.BorderWidth == 5
    # Shapes: every kind in a control array, and one changed from lists
    assert [shape.Shape for shape in page.shpKinds] == list(range(6))
    assert page.shpKinds[3].FillColor == vp6.QBColor(12)
    sample = page.shpSample
    assert (sample.Shape, sample.FillStyle) == (vp6.vpShapeRoundedRectangle,
                                                vp6.vpDiagonalCross)
    page.cboShape.ListIndex = vp6.vpShapeCircle
    page.cboFill.ListIndex = vp6.vpFSSolid
    assert (sample.Shape, sample.FillStyle) == (vp6.vpShapeCircle, vp6.vpFSSolid)
    page.chkOpaque.Value = vp6.vpChecked
    assert sample.BackStyle == vp6.vpOpaque
    page.chkOpaque.Value = vp6.vpUnchecked
    assert sample.BackStyle == vp6.vpTransparent


def test_tree_page(sink):
    page = _page(sink, "tree")
    tree = page.tvwDemo
    assert tree.Nodes("animals").Expanded and tree.Checkboxes
    tree.SelectedItem = "cats"
    page.txtNode.Text = "Lion"
    page.cmdAddChild._widget.click()
    lion = tree.Nodes(tree.Nodes.Count)
    assert lion.FullPath == "Animals\\Cats\\Lion" and page.lblTree.Caption.startswith("Added")
    assert lion.Image == "star" and not lion._item.icon(0).isNull()  # from the ImageList
    assert all(not tree.Nodes(key)._item.icon(0).isNull() for key in ("animals", "cats", "trees"))
    tree.Nodes("plants")._item.setCheckState(0, Qt.Checked)  # the user checks it
    assert page.lblTree.Caption == "Plants is checked"
    tree.SelectedItem = "animals"
    page.cmdRemove._widget.click()
    assert "cats" not in tree.Nodes and tree.Nodes.Count == 2


def test_listview_page(sink):
    page = _page(sink, "listview")
    pets = page.lvwPets
    assert pets.View == vp6.vpLvwReport and pets.ListItems.Count == 5
    assert not pets.ListItems("rex")._cell0.icon().isNull()  # from imlSmall
    page.lvwPets_ItemClick(pets.ListItems("polly"))
    assert page.lblEvent.Caption == "Polly: Parrot, 2 legs (item 3 of 5)"
    kind = pets.ColumnHeaders("kind")
    page.lvwPets_ColumnClick(kind)  # sorted by Kind
    assert [i.Key for i in pets.ListItems][:2] == ["tom", "rex"]  # Cat before Dog
    page.lvwPets_ColumnClick(kind)  # again: reversed
    assert pets.SortOrder == vp6.vpLvwDescending and "Z to A" in page.lblEvent.Caption
    page.cboView.ListIndex = 0  # the Icon view
    assert pets.View == vp6.vpLvwIcon
    page.chkChecks.Value = vp6.vpChecked
    page.chkMulti.Value = vp6.vpChecked
    assert pets.Checkboxes and pets.MultiSelect
    page.txtName.Text = "Nemo"
    page.cmdAdd._widget.click()
    nemo = pets.SelectedItem
    assert nemo.Text == "Nemo" and nemo.SubItems(1) == "Fish" and pets.ListItems.Count == 6
    page.cmdRemove._widget.click()
    assert pets.ListItems.Count == 5 and page.lblEvent.Caption == "Removed Nemo"


def test_grid_page(sink, monkeypatch):
    page = _page(sink, "grid")
    prices = page.grdPrices
    assert prices.Rows == 7 and prices.TextMatrix(0, 1) == "Fruit" and prices.RowData(1) == 100
    header = prices._widget.horizontalHeader()
    point = QPoint(header.sectionViewportPosition(1) + 10, header.height() // 2)
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, point)  # Price
    column = [float(prices.TextMatrix(r, 2)) for r in range(1, 7)]
    assert column == sorted(column) and "Sorted by Price, ascending" in page.lblEvent.Caption
    QTest.mouseClick(header.viewport(), Qt.LeftButton, Qt.NoModifier, point)  # again
    column = [float(prices.TextMatrix(r, 2)) for r in range(1, 7)]
    assert column == sorted(column, reverse=True)
    prices.Row = 2
    prices.Row = 1  # (RowColChange: a move)
    assert page.lblCell.Caption == "Row 1: Cherry costs 4.80 (RowData 300)"
    props, label = page.grdProps, page.lblSample
    assert label.Caption == "A sample label" and label.Width == 292
    props.Row, props.Col = 1, 1  # Caption: a text editor
    props.EditCell()
    editor = props._widget.findChild(QLineEdit)
    editor.setText("Hello")
    QTest.keyClick(editor, Qt.Key_Return)
    QTest.qWait(10)
    assert label.Caption == "Hello" and "Caption = Hello (AfterEdit)" in page.lblEvent.Caption
    props.Row = 2  # Visible: a check box
    props.EditCell()
    assert not label.Visible and props.TextMatrix(2, 1) == "False"
    props.Row = 3  # Alignment: a list
    assert props.CellList == ["Left", "Right", "Center"]
    props._commit(3, 1, "Center")  # (what choosing it in the list does)
    assert label.Alignment == vp6.vpCenter
    monkeypatch.setattr(sys.modules["pgGrid"], "InputBox", lambda *args: "Courier New")
    props.Row = 5  # FontName: a ... button
    props.EditCell()
    assert label.FontName == "Courier New" and props.TextMatrix(5, 1) == "Courier New"
    props._commit(6, 1, "wide")  # Width: ValidateEdit refuses text
    assert props.TextMatrix(6, 1) == "292" and "must be a number" in page.lblEvent.Caption
    props._commit(6, 1, "200")
    assert label.Width == 200
    assert props._editor_of(4, 1) == vp6.vpGridEditColor and label.BackColor is not None


def test_tabs_page(sink):
    page = _page(sink, "tabs")
    strip = page.tbsOptions
    frames = (page.fraGeneral, page.fraColors, page.fraAbout)
    assert [f.Visible for f in frames] == [True, False, False]  # the selected tab's Frame
    assert [strip.Tabs(i).Image for i in (1, 2, 3)] == ["gear", "palette", "info"]
    assert not any(strip._widget.tabIcon(i).isNull() for i in range(3))  # from imlTabs
    assert (page.fraGeneral.Left, page.fraGeneral.Top) == (strip.ClientLeft + 4,
                                                           strip.ClientTop + 4)
    strip.SelectedItem = "colors"
    assert [f.Visible for f in frames] == [False, True, False]
    assert "Colors" in page.lblEvent.Caption
    page.chkLock.Value = vp6.vpChecked  # BeforeClick keeps the tab
    bar = strip._widget.tabBar()
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, bar.tabRect(2).center())
    assert strip.SelectedItem.Key == "colors" and "locked" in page.lblEvent.Caption
    page.cboPlacement.ListIndex = 3  # the tabs on the right: the Frames follow
    assert strip.Placement == vp6.vpTabPlacementRight
    assert page.fraColors.Width == strip.ClientWidth - 8
    page.txtName.Text = "Ada"
    assert page.lblGreeting.Caption == "Hello, Ada!"
    page.optColor[1].Value = True
    assert page.lblSwatch.BackColor == 0x00C000


def test_files_page(sink, tmp_path):
    page = _page(sink, "files")
    assert page.dirFolder.Path == page.filFiles.Path == os.getcwd()
    folder = tmp_path / "Pictures"
    (folder / "Holidays").mkdir(parents=True)
    (folder / "notes.txt").write_text("hello")
    shutil.copy(sink._base_dir() + "/images/sun.png", folder / "sun.png")
    page.dirFolder.Path = str(folder)  # Change: the FileListBox follows (PathChange)
    assert page.filFiles.Path == str(folder) and page.filFiles.List == ["notes.txt", "sun.png"]
    assert "PathChange" in page.lblEvent.Caption and "2 matching" in page.lblEvent.Caption
    page.cboPattern.ListIndex = 2  # pictures: PatternChange
    assert page.filFiles.Pattern == "*.png;*.jpg" and page.filFiles.List == ["sun.png"]
    assert "PatternChange" in page.lblEvent.Caption
    page.filFiles.ListIndex = 0  # Click: its size and picture
    assert page.lblChosen.Caption.startswith("sun.png\n") and page.imgPreview.Picture
    page.dirFolder.ListIndex = 0  # a subfolder (Click), then the folder's parent
    assert "List(0): Holidays" in page.lblEvent.Caption
    page.dirFolder.ListIndex = -2
    assert f"List(-2): {tmp_path.name}" in page.lblEvent.Caption
    page.drvDrive.Drive = str(folder)  # (the same drive: no Change)
    assert page.dirFolder.Path == str(folder)
    page.drvDrive_Change()
    assert page.dirFolder.Path == os.path.abspath(page.drvDrive.Drive)  # its folders
    page.chkHidden.Value = vp6.vpChecked
    assert page.dirFolder.ShowHidden and page.filFiles.Hidden


def test_timer_page(sink):
    page = _page(sink, "timer")
    assert page.tmrClock.Enabled  # Form_Activate: visible
    assert re.fullmatch(r"\d\d:\d\d:\d\d", page.lblClock.Caption)
    _page(sink, "intro")  # another page: Form_Deactivate stops it
    assert not page.tmrClock.Enabled
    _page(sink, "timer")
    page.chkTimer.Value = vp6.vpUnchecked
    assert not page.tmrClock.Enabled


def test_layout_page(sink):
    page = _page(sink, "layout")
    page.chkNav.Value = vp6.vpUnchecked
    assert not sink.picNav.Visible and not sink.splNav.Visible and sink.picContent.Left == 0
    page.chkNav.Value = vp6.vpChecked
    page.cmdWider._widget.click()
    assert sink.picNav.Width == 260 and sink.picContent.Left == 266
    sink.show_navigation(False)  # also from the View menu: the check box follows
    assert page.chkNav.Value == vp6.vpUnchecked


def test_docking_page(sink):
    page = _page(sink, "docking")
    tools, props, output = page.dckTools, page.dckProps, page.dckOutput
    assert [page.grdProps.TextMatrix(r, 1) for r in (1, 2, 3)] == ["left", "right", "bottom"]
    page.cmdSave_Click()
    assert page.cmdRestore.Enabled and "Layout saved" in page.rtbLog.Text
    page.cmdFloat_Click()  # Float: the Output panel in its own window
    assert output.Floating and page.cmdFloat.Caption == "&Dock output"
    assert "Output: floating (DockChange)" in page.rtbLog.Text
    assert page.grdProps.TextMatrix(3, 1) == "floating"
    page.cmdFloat_Click()
    assert not output.Floating and output.Align == vp6.vpAlignBottom
    page.chkKeep.Value = vp6.vpChecked  # Close cancelled
    output._caption_button("close")
    assert output.Visible and "stays open" in page.rtbLog.Text
    tools._caption_button("close")  # closed, then back from the list
    assert not tools.Visible and page.grdProps.TextMatrix(1, 1) == "closed"
    assert "double-click its row" in page.lblHelp.Caption
    page.grdProps.Row = 1
    page.grdProps_DblClick()
    assert tools.Visible and page.grdProps.TextMatrix(1, 1) == "left"
    props.Dock(vp6.vpAlignTop)  # moved, then the saved layout back
    page.cmdRestore_Click()
    assert props.Align == vp6.vpAlignRight and "Layout restored" in page.rtbLog.Text
    props.Width = 200  # the grid follows its panel
    assert page.grdProps.Width == 188
    page.cmdShowAll_Click()
    assert all(p.Visible for p in (tools, props, output))


def test_scrolling_page(sink):
    page = _page(sink, "scrolling")
    assert page.ScaleHeight == 1000  # taller than the pane
    sink.picContent.ScrollTop = 300
    assert sink.picContent.ScrollTop == 300 and _status(sink) == "Scrolled to 0, 300"
    page.cmdTop._widget.click()
    assert sink.picContent.ScrollTop == 0


def test_embedded_page(sink):
    page = _page(sink, "embedded")
    buttons, info = page.picButtons, page.picInfo  # Align = Bottom, Align = Fill
    assert (buttons.Top, buttons.Width) == (page.ScaleHeight - 40, page.ScaleWidth)
    assert (info.Top, info.Height) == (0, page.ScaleHeight - 40)
    assert page.tmrShown.Enabled  # Form_Activate
    page.lblInfo._widget.linkActivated.emit("popout")  # [Pop it out](popout)
    assert page.Container is None and page._widget.isWindow() and page.Visible
    assert page.cmdPop.Caption == "Put &back"
    page.cmdPop._widget.click()
    assert page.Container is sink.picContent and page.cmdPop.Caption == "Pop &out"
    page.cmdPop._widget.click()  # out again: closing the window still unloads it
    assert sink.Unload() is True
    assert not page._loaded and not page.Visible


def test_dialogs_page(sink):
    page = _page(sink, "dialogs")
    page.cmdMsgBox._widget.click()
    assert page.lblResult.Caption == f"MsgBox returned {vp6.vpYes} (Yes)"
    page.cmdInputBox._widget.click()
    assert page.lblResult.Caption == "InputBox returned 'Zed'"

    def answer_dialog():
        dialog = next(f for f in vp6.Forms if type(f).__name__ == "frmDialog")
        assert dialog._is_dark()  # the dialog's own ColorScheme = 3 - Dark
        dialog.txtItem.Text = "Yankee"
        dialog.cmdOK._widget.click()

    QTimer.singleShot(50, answer_dialog)
    page.cmdModal._widget.click()  # modal: returns after OK
    assert page.lblResult.Caption == \
        "The dialog's Result: 'Yankee' (closed by Unload in code)"
    dialog = sys.modules["frmDialog"].frmDialog
    assert dialog.Icon == "images/star.png"
    assert not dialog._vp_default._widget.windowIcon().isNull()
    first = dialog._vp_default

    def close_it():  # its close button this time: Result None, Form_QueryUnload knows
        dialog._vp_default._widget.close()

    QTimer.singleShot(50, close_it)
    page.cmdModal._widget.click()
    assert page.lblResult.Caption == "The dialog's Result: None (closed by its close button)"
    assert dialog._vp_default is first and dialog.txtItem.Text == ""  # the same, loaded again


def test_schemes_page_and_menu(sink):
    page = _page(sink, "schemes")
    page.optScheme[2].Value = True  # a control array: optScheme_Click(Index=2)
    assert sink._effective_scheme() == vp6.vpSchemeDark
    assert [m.Checked for m in sink.mnuScheme] == [False, False, True, False]
    sink.mnuScheme[1]._action.trigger()  # View > Light: the page follows
    assert sink._effective_scheme() == vp6.vpSchemeLight and page.optScheme[1].Value
    page.optScheme(0).Value = True
    assert sink._effective_scheme() == vp6.vpSchemeSystem


def test_keyboard_page(sink):
    page = _page(sink, "keyboard")
    QTest.keyClicks(page.txtDigits._widget, "a1b2")
    assert page.txtDigits.Text == "12"  # KeyPress returning 0 swallows the key
    assert page.lblLastKey.Caption.startswith("KeyDown: key code")  # KeyPreview
    QTest.keyClick(page.txtUpper._widget, Qt.Key_Return)  # the page's Default button
    assert page.lblButtons.Caption.startswith("OK")
    QTest.keyClick(page.txtUpper._widget, Qt.Key_Escape)  # its Cancel button
    assert page.lblButtons.Caption.startswith("Cancel")
    # Validate: an age that isn't one keeps the focus; Help doesn't wait for it
    sink._widget.activateWindow()
    page.txtAge.Text = "old"
    page.txtAge.SetFocus()
    QTest.qWait(10)
    page.txtCity.SetFocus()
    QTest.qWait(20)
    assert page.ActiveControl is page.txtAge and "isn't an age" in page.lblValid.Caption
    page.cmdHelp._widget.click()
    assert page.lblValid.Caption.startswith("Help:")
    page.txtAge.Text = "42"
    page.txtAge.SetFocus()
    page.txtCity.SetFocus()
    QTest.qWait(20)
    assert page.ActiveControl is page.txtCity and page.lblValid.Caption == "Age 42: fine"
    page.tmrActive_Timer()  # ActiveControl
    assert page.lblActive.Caption == ("Screen.ActiveControl: txtCity; "
                                      "this page's ActiveControl: txtCity")
    assert sink.ActiveControl is None  # (the window's own controls don't have the focus)
    page.cmdType._widget.click()  # SendKeys: typed, upper-cased by KeyPress, then Enter
    page.lblButtons.Caption = ""
    QTest.qWait(100)
    assert page.txtUpper.Text == "TYPED FOR YOU" and page.lblButtons.Caption.startswith("OK")


def test_mouse_page(sink):
    page = _page(sink, "mouse")
    QTest.mousePress(page.picPad._widget, Qt.RightButton, Qt.NoModifier, QPoint(50, 60))
    assert page.lblMouse.Caption == "right button down at 50, 60"
    QTest.mouseRelease(page.picPad._widget, Qt.RightButton, Qt.NoModifier, QPoint(50, 60))
    assert page.lblMouse.Caption.endswith("released")


def test_control_arrays_page(sink):
    page = _page(sink, "arrays")
    more = page.cmdMore
    more[0]._widget.click()  # "+" loads cmdMore(1)
    more[0]._widget.click()
    assert [b.Caption for b in more] == ["+", "1", "2"] and more[2].Visible
    assert more[2].Left == more[0].Left + 88
    more[1]._widget.click()  # clicking an added one unloads it
    assert list(more) == [more[0], more[2]] and "Index 0 to 2" in page.lblMore.Caption
    for _ in range(4):
        more[0]._widget.click()  # fills the free places 1, 3 and 4, then says enough
    assert more.Count == 5 and page.lblMore.Caption == "That's enough buttons"


def test_menus_page_and_bookmarks(sink):
    page = _page(sink, "menus")
    assert page.cboPages.ListCount == len(sink.page_titles())
    page.cboPages.ListIndex = page.cboPages.List.index("Timer")
    page.cmdBookmark._widget.click()  # Load(mnuBookmark, 1)
    assert [m.Caption for m in sink.mnuBookmark] == ["&Introduction", "Timer"]
    assert sink.mnuBookmark[1].Visible
    page.cmdBookmark._widget.click()  # not twice
    assert sink.mnuBookmark.Count == 2 and "already" in _status(sink)
    sink.mnuBookmark[1]._action.trigger()
    assert sink.lblTitle.Caption == "Timer"
    assert sink.mnuHelpKeys._action.shortcut().toString() == "F1"
    assert sink.mnuFileEnd._action.shortcut().toString() == "Ctrl+Q"
    sink.mnuView._submenu.aboutToShow.emit()  # a menu's Click before it opens
    assert sink.mnuViewNav.Checked
    sink.mnuHelpAbout._action.trigger()  # MsgBox (answered by the test)


def test_popup_menu(sink, monkeypatch):
    page = _page(sink, "menus")
    assert not page.mnuPopup.Visible  # only a popup: not on the window's menu bar
    assert "Popup" not in [a.text() for a in sink._menubar.actions()]
    shown = []

    def popup(point):  # (instead of the real one, which waits for a choice)
        menu = page.mnuPopup._submenu
        shown.append((point, menu.defaultAction()))
        page.mnuPopupShout._action.trigger()

    monkeypatch.setattr(page.mnuPopup._submenu, "exec", popup)
    QTest.mouseClick(page.lblPopup._widget, Qt.RightButton)  # MouseUp, the right button
    assert page.lblPage.Caption == "HELLO FROM THE POPUP MENU!"
    assert shown[0][1] is page.mnuPopupHello._action  # the default item, in bold
    QTest.mouseClick(page.lblPopup._widget, Qt.LeftButton)  # (not for the left one)
    assert len(shown) == 1
    page.cmdPopup._widget.click()  # centered under the button
    point, default = shown[1]
    button = page.cmdPopup
    under = page._container_widget().mapToGlobal(
        QPoint(button.Left + button.Width // 2, button.Top + button.Height))
    assert point.y() == under.y() and point.x() < under.x() and default is None


def test_page_menus_join_the_window(sink):
    bar = lambda: [a.text() for a in sink._menubar.actions()]  # noqa: E731
    assert bar() == ["&File", "&View", "&Bookmarks", "&Help"]
    page = _page(sink, "menus")  # its own Page menu joins, before Help (both Right)
    assert bar() == ["&File", "&View", "&Bookmarks", "&Page", "&Help"]
    page.mnuPageHello._action.trigger()
    assert page.lblPage.Caption.startswith("Hello from the Menus page")
    _page(sink, "intro")  # another page: its menu leaves
    assert bar() == ["&File", "&View", "&Bookmarks", "&Help"]


def test_globals_page(sink, capsys):
    page = _page(sink, "globals")
    assert "App.Title" in page.lblInfo.Caption and "Screen:" in page.lblInfo.Caption
    page.txtClip.Text = "clip"
    page.cmdCopy._widget.click()
    page.txtClip.Text = ""
    page.cmdPaste._widget.click()
    assert page.txtClip.Text == "clip"
    page.cmdCount._widget.click()  # DoEvents loop
    assert page.cmdCount.Caption == "Count to &100"
    page.cmdDebug._widget.click()
    assert "Hello from the Kitchen Sink" in capsys.readouterr().out


def test_closing_unloads_the_pages(sink):
    pages = [_page(sink, key) for key in ("text", "timer")]
    assert sink.Unload() is True
    assert not any(page._loaded for page in pages)
