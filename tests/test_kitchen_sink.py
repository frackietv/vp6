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
    assert project.forms == ["Form1.py", "frmDialog.py", "frmEmbedded.py"]
    assert project.modules == ["Module1.py"]  # like every new project: Form1 and Module1
    assert project.startup == SUB_MAIN and project.type == "exe"
    folder = tmp_path / "Sink"
    for name in kitchensink.FORMS + kitchensink.MODULES:
        assert (folder / name).read_text() == (kitchensink.TEMPLATE_DIR / name).read_text()
    assert not QPixmap(str(folder / kitchensink.PICTURE)).isNull()


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
def sink_forms(qapp, tmp_path, monkeypatch):
    """Import the created project's forms in this process."""
    create_project(str(tmp_path), "Sink", "kitchensink")
    folder = str(tmp_path / "Sink")
    sys.path.insert(0, folder)
    modules = {name: importlib.import_module(name)
               for name in ("frmDialog", "frmEmbedded", "Form1")}
    # Answer the Form_Unload confirmation and silence message boxes
    monkeypatch.setattr(modules["Form1"], "MsgBox", lambda *args, **kwargs: vp6.vpYes)
    monkeypatch.setattr(modules["Form1"].time, "sleep", lambda seconds: None)
    yield modules
    sys.path.remove(folder)
    for name in ("Form1", "frmDialog", "frmEmbedded", "Module1"):
        sys.modules.pop(name, None)


def test_kitchen_sink_runs(sink_forms, capsys):
    form = sink_forms["Form1"].Form1()
    form.Show()
    assert form.lblOnPicture.Parent is form.picLogo  # a Label inside the PictureBox
    assert "controls loaded" in form.lblStatus.Caption

    QTest.keyClicks(form.txtUpper._widget, "abc")
    assert form.txtUpper.Text == "ABC"  # KeyPress transformation

    form.txtName.Text = "Delta"
    assert form.cmdAdd.Enabled  # Change event
    form.cmdAdd._widget.click()
    assert "Delta" in form.lstItems.List and form.txtName.Text == ""

    form.lstItems.ListIndex = 0
    form.cmdRemove._widget.click()
    assert form.lstItems.ListCount == 3

    form.hsbSize.Value = 16
    assert form.lblSizeValue.Caption == "16" and form.lblSwatch.FontSize == 16

    form.cboColors.ListIndex = form.cboColors.List.index("Red")
    assert form.lblSwatch.BackColor == vp6.vpRed

    form.optScheme[2].Value = True  # a control array: optScheme_Click(Index=2)
    assert form._effective_scheme() == vp6.vpSchemeDark
    form.optScheme(0).Value = True
    assert form._effective_scheme() == vp6.vpSchemeSystem

    form.chkPicture.Value = vp6.vpUnchecked
    assert not form.picLogo.Visible

    form.cmdCount._widget.click()  # DoEvents loop
    assert form.cmdCount.Caption == "Count to &100"

    def answer_dialog():
        dialog = next(f for f in vp6.Forms if type(f).__name__ == "frmDialog")
        assert dialog._is_dark()  # the dialog's own ColorScheme = 3 - Dark
        dialog.txtItem.Text = "Zulu"
        dialog.cmdOK._widget.click()

    QTimer.singleShot(50, answer_dialog)
    form.cmdDialog._widget.click()  # modal: returns after OK
    assert "Zulu" in form.lstItems.List

    form.tmrClock_Timer()
    assert re.fullmatch(r"\d\d:\d\d:\d\d", form.lblClock.Caption)

    assert form.Unload() is True
    assert "Traceback" not in capsys.readouterr().err


def test_every_kind_of_control_array_use_is_shown():
    code = "\n".join(template_sources().values())
    assert any(form.is_array(c.name) for form in form_defs().values() for c in form.controls)
    for used in ("Load(", "Unload(", ".Count", ".LBound", ".UBound", ", Index):"):
        assert used in code, f"Control arrays: {used!r} not demonstrated - {UPDATE_HINT}"


def test_kitchen_sink_control_array_demo(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    more = form.cmdMore
    more[0]._widget.click()  # "+" loads cmdMore(1)
    more[0]._widget.click()
    assert [b.Caption for b in more] == ["+", "1", "2"] and more[2].Visible
    assert more[2].Left == more[0].Left + 88
    more[1]._widget.click()  # clicking an added one unloads it
    assert list(more) == [more[0], more[2]] and "Index 0 to 2" in form.lblStatus.Caption
    for _ in range(4):
        more[0]._widget.click()  # fills the free places 1, 3 and 4, then says enough
    assert more.Count == 5 and form.lblStatus.Caption == "That's enough buttons"
    form.Unload()


def test_kitchen_sink_menus(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    assert [a.text() for a in form._menubar.actions()] == ["&File", "&View", "&Help"]
    form.mnuScheme[2]._action.trigger()  # View > Dark, a menu control array
    assert form.optScheme[2].Value and form._effective_scheme() == vp6.vpSchemeDark
    assert [m.Checked for m in form.mnuScheme] == [False, False, True, False]
    form.optScheme[0].Value = True  # the option buttons update the menu too
    assert [m.Checked for m in form.mnuScheme] == [True, False, False, False]
    form.mnuViewClock._action.trigger()  # the check mark follows the clock
    assert not form.tmrClock.Enabled and not form.mnuViewClock.Checked
    assert form.chkTimer.Value == vp6.vpUnchecked
    form.mnuViewClock._action.trigger()
    assert form.tmrClock.Enabled and form.mnuViewClock.Checked
    form.mnuView._submenu.aboutToShow.emit()  # a menu's Click before it opens
    assert "View menu" in form.lblStatus.Caption
    assert form.mnuFileDialog._action.shortcut().toString() == "Ctrl+D"
    form.Unload()


def test_kitchen_sink_image(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    thumb = form.imgThumb
    assert (thumb.Width, thumb.Height) == (40, 30) and thumb.Stretch  # scaled, not resized
    assert not thumb._widget.pixmap().isNull()
    QTest.mouseClick(thumb._widget, Qt.LeftButton)
    assert not form.picLogo.Visible and form.chkPicture.Value == vp6.vpUnchecked
    QTest.mouseClick(thumb._widget, Qt.LeftButton)
    assert form.picLogo.Visible
    form.Unload()


def test_kitchen_sink_embedded_form(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    embedded = form.embedded
    assert embedded.Container is form.picEmbed
    assert not embedded._widget.isWindow() and embedded._widget.isVisible()
    view = form.picEmbed._scroll_area.viewport()  # ScrollBars = Vertical
    assert embedded.ScaleWidth == view.width()  # it fills the visible width...
    assert embedded.ScaleHeight == 300 > view.height()  # ...and keeps its height: it scrolls
    form.picEmbed.ScrollTop = 1000
    assert form.picEmbed.ScrollTop == 300 - view.height()  # scrolled to the bottom
    buttons = embedded.picButtons  # Align = Bottom: docked, following the form's size
    assert (buttons.Left, buttons.Top, buttons.Width) == (0, embedded.ScaleHeight - 40,
                                                          embedded.ScaleWidth)
    assert embedded.cmdPop.Width == buttons.Width - 16  # picButtons_Resize ran
    info = embedded.picInfo  # Align = Fill: the rest of the form
    assert (info.Left, info.Top, info.Width, info.Height) == (0, 0, embedded.ScaleWidth,
                                                              embedded.ScaleHeight - 40)
    assert embedded.lblInfo.Width == info.Width - 16  # picInfo_Resize ran
    assert embedded.lblInfo._widget.textFormat() == Qt.MarkdownText  # a Markdown caption
    embedded.lblInfo._widget.linkActivated.emit("popout")  # its [Pop it out](popout) link
    assert embedded.Container is None
    embedded.cmdPop._widget.click()  # put back
    assert embedded.Container is form.picEmbed
    embedded.cmdPop._widget.click()  # pop out
    assert embedded.Container is None and embedded._widget.isWindow()
    assert embedded._widget.isVisible() and embedded.cmdPop.Caption == "Put &back"
    embedded.cmdPop._widget.click()  # put back
    assert embedded.Container is form.picEmbed and not embedded._widget.isWindow()
    embedded.cmdPop._widget.click()  # out again: closing Form1 still unloads it
    assert form.Unload() is True
    assert not embedded._loaded and not embedded._widget.isVisible()


def test_kitchen_sink_tree_view(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    tree = form.tvwIndex
    assert tree.Nodes("fraText").Children == 3  # from the designer's Items outline
    assert tree.Nodes("mnuView").Parent is tree.Nodes("mnuFile")  # added in Form_Load
    tree.Nodes("fraOptions").Expanded = True
    item = tree.Nodes("hsbSize")._item
    rect = tree._widget.visualItemRect(item)
    QTest.mouseClick(tree._widget.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    assert tree.SelectedItem is tree.Nodes("hsbSize")
    assert form.lblStatus.Caption == "Options\\Font size - the HScrollBar hsbSize"
    tree._widget.expandItem(tree.Nodes("fraText")._item)  # the user expanding a node
    assert form.lblStatus.Caption == "Text and buttons has 3 items"
    form.Unload()


def test_kitchen_sink_side_pane_and_splitter(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    side, splitter = form.picSide, form.splSide
    assert (side.Left, side.Width, side.Height) == (760, 160, form.ScaleHeight)  # docked right
    assert (splitter.Left, splitter.Width) == (754, 6)  # beside it
    assert form.tvwIndex.Parent is side and form.picEmbed.Parent is side
    bar = splitter._widget
    # One move: the bar itself moves while dragged (live), and QTest positions are its own
    QTest.mousePress(bar, Qt.LeftButton, Qt.NoModifier, QPoint(3, 100))
    QTest.mouseMove(bar, QPoint(-37, 100))  # dragged 40 pixels to the left
    QTest.mouseRelease(bar, Qt.LeftButton, Qt.NoModifier, QPoint(3, 100))
    assert side.Width == 200 and side.Left == 720 and splitter.Left == 714
    assert form.tvwIndex.Width == 184 and form.picEmbed.Width == 184  # picSide_Resize
    assert form.embedded.ScaleWidth == form.picEmbed._scroll_area.viewport().width()
    assert form.lblStatus.Caption == "The side pane is now 200 pixels wide"  # Moved
    assert form.lblStatus.Left + form.lblStatus.Width <= splitter.Left - 16  # clear of it
    form.Unload()


def test_kitchen_sink_lines(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    form.Width, form.Height = 1000, 600  # Form_Resize stretches the line above the status bar
    QTest.qWait(20)
    assert (form.linStatus.X2, form.linStatus.Y1) == (form.splSide.Left - 16, 600 - 39)
    assert form.splSide.Left == 1000 - 160 - 6  # up to the docked side pane
    assert form.linStatus.Y1 == form.linStatus.Y2 < form.lblStatus.Top
    assert form.linZ.ZIndex == 3 and form.linZ.BorderStyle == 2
    form.Unload()


def test_kitchen_sink_z_order_demo(sink_forms):
    form = sink_forms["Form1"].Form1()
    form.Show()
    widget = form._container_widget()  # the area below a menu bar in the window
    overlap = QPoint(100, 460)  # inside both lblZRed (16,440 132x40) and lblZBlue (80,452)

    def on_top():
        return widget.childAt(overlap)._vp_control.Name

    assert on_top() == "lblZRed"  # ZIndex 2 beats 1, although created first
    form.cmdSwapZ._widget.click()
    assert on_top() == "lblZBlue" and form.lblZBlue.Caption == "Blue: ZIndex 2"
    form.lblZRed_Click()  # ZOrder(0)
    assert on_top() == "lblZRed" and form.lblZRed.ZIndex == 4  # above linZ (3) too
    form.Unload()
