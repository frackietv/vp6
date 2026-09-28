"""The Kitchen Sink template must keep demonstrating everything VP6 offers.

If a test here fails after you added a control, event or API function to
VP6: demonstrate it in vp6/ide/templates/kitchensink/ (see the development
guide, "Keep the Kitchen Sink up to date").
"""

import importlib
import re
import sys

import pytest
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest

import vp6
from vp6 import formfile
from vp6.controls import CONTROL_TYPES
from vp6.ide import kitchensink
from vp6.ide.designer import FormDesigner
from vp6.ide.documents import FormDocument
from vp6.ide.mainwindow import create_project
from vp6.project import SUB_MAIN, Project

UPDATE_HINT = "update the Kitchen Sink (vp6/ide/templates/kitchensink/)"


def template_sources() -> dict[str, str]:
    return {name: (kitchensink.TEMPLATE_DIR / name).read_text()
            for name in kitchensink.FORMS + kitchensink.MODULES}


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
        if filename in kitchensink.FORMS:
            assert formfile.replace_region(source, formfile.parse(source)) == source, filename


# --- creating and using the project -----------------------------------------------------------

def test_create_kitchen_sink_project(qapp, tmp_path):
    path = create_project(str(tmp_path), "Sink", "kitchensink")
    project = Project.load(path)
    assert project.forms == list(kitchensink.FORMS)  # the window, its pages, the dialog
    assert project.modules == ["Module1.py"]  # like every new project: Form1 and Module1
    assert project.startup == SUB_MAIN and project.type == "exe"
    folder = tmp_path / "Sink"
    for name in kitchensink.FORMS + kitchensink.MODULES:
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
    for name in names + ["Module1"]:
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
    assert page.lblResult.Caption == "The dialog's Result: 'Yankee'"


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
