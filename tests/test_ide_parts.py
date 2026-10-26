"""What VP6 gained for building IDEs with it: FlexGrid's shown check boxes, ColorPicker, ButtonStyle,
SelectionMode None and StretchCol; SpinBox's SpecialValueText; CodeBox's fold
markers, text-only protected shading, selection colors and gutter; Label's
VerticalAlignment, Selectable and access keys drawn by the style; ListView's
icon grid; PictureBox's BackStyle; DrawCap, DrawJoin, FontScale and a Picture's
fractional FontSize; GraphicsPath's Unite, Subtract and Intersect; ListBox's
ItemToolTip; InputNumber; MsgBox's Save/Discard/Cancel and ExtraButton;
ShowHelp's Tab; Screen.FontDPI; and the splitter's system grip."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QInputDialog, QMessageBox,
                               QPushButton)

import vp6
from vp6 import (CheckBox, CodeBox, FlexGrid, Form, GraphicsPath, Label, ListBox, ListView,
                 Picture, PictureBox, SpinBox, Splitter, Unload)
from vp6.constants import (vpCapRound, vpCapSquare, vpDiscard, vpExtraButton, vpGridEditCheck,
                           vpGridEditColor, vpJoinBevel, vpOKOnly, vpSave, vpSaveDiscardCancel)


class Parts(Form):
    def InitializeComponent(self):
        self.Width, self.Height = 500, 400
        self.grid = FlexGrid(self, Left=0, Top=0, Width=300, Height=150, Rows=3, Cols=3,
                             FixedCols=0, Editable=True, EditorsShown=True, ColorPicker=1,
                             ButtonStyle=1, SelectionMode=3, StretchCol=0)
        self.spin = SpinBox(self, Left=310, Top=0, Max=10, SpecialValueText="(Default)")
        self.code = CodeBox(self, Left=0, Top=160, Width=300, Height=120, Language=1,
                            ProtectedShading=1, SelBackColor=0x0000FF, FoldMarkerColor=0x808080)
        self.label = Label(self, Caption="&Name:", Left=310, Top=40, Width=80, Height=40,
                           VerticalAlignment=1, Selectable=True)
        self.icons = ListView(self, Left=310, Top=90, Width=180, Height=100, GridWidth=90,
                              GridHeight=60)
        self.pic = PictureBox(self, Left=310, Top=200, Width=100, Height=60, BackStyle=0,
                              BorderStyle=0)
        self.lst = ListBox(self, Left=310, Top=270, Width=180, Height=60)
        self.bar = Splitter(self, Align=3, Style=1)
        self.clicked = []

    def grid_CellButtonClick(self, Row, Col):
        self.clicked.append((Row, Col))


def test_flexgrid_shown_editors(qapp):
    form = Parts()
    form.Show()
    try:
        grid = form.grid
        grid.ColEditor[1] = vpGridEditColor
        grid.ColEditor[2] = vpGridEditCheck
        grid.TextMatrix[1, 1] = "#ff0000"
        grid.TextMatrix[1, 2] = "True"
        QApplication.processEvents()
        table = grid._widget
        check = table.cellWidget(0, 2).findChild(QCheckBox)
        assert check is not None and check.isChecked()  # (a check box in the middle)
        check.setChecked(False)
        assert grid.TextMatrix(1, 2) == "False"
        button = table.cellWidget(0, 1)
        assert isinstance(button, QPushButton) and "padding: 2px 6px" in button.styleSheet()
        button.click()  # (ColorPicker CellButtonClick: the program's own picker)
        assert form.clicked == [(1, 1)]
        assert table.selectionMode() == table.SelectionMode.NoSelection
        assert table.horizontalHeader().sectionResizeMode(0) == \
            table.horizontalHeader().ResizeMode.Stretch
        assert form.spin.Value == 0 and form.spin.Text == "(Default)"
    finally:
        Unload(form)


def test_codebox_fold_markers_and_shading(qapp):
    form = Parts()
    form.Show()
    try:
        box = form.code
        box.Text = "a = 1\n# region\nb = 2\n# endregion\nc = 3\n"
        box.ProtectLines(1, 3)
        box.SetFoldMarker(1, False)
        assert box._folds and box._folds[0][1] is False
        box.HideLines(2, 3)
        box.SetFoldMarker(1, True)
        box.SetFoldMarker(1, None)
        assert not box._folds
        palette = box._widget.palette()
        assert palette.color(palette.ColorRole.Highlight).name() == "#ff0000"
        assert box._widget.styleSheet() == ""  # (colors in the palette)
        assert box._gutter_width() > 14 + 18  # (markers, numbers, folds)
        assert not box._widget.grab().isNull()  # (the shading and the gutter painted)
    finally:
        Unload(form)


def test_label_alignment_selection_and_access_keys(qapp):
    form = Parts()
    form.Show()
    try:
        widget = form.label._widget
        assert widget.alignment() & Qt.AlignVCenter
        assert widget.textInteractionFlags() & Qt.TextSelectableByMouse
        assert widget.text() == "Name:" and widget.mnemonic == "&Name:"
        form.label.Caption = "Plain"
        assert widget.mnemonic is None
    finally:
        Unload(form)


def test_lists_and_pictures(qapp):
    form = Parts()
    form.Show()
    try:
        assert form.icons._icons.gridSize().width() == 90
        assert not form.pic._widget.autoFillBackground()  # (BackStyle Transparent)
        form.lst.AddItem("Demo.vp6p")
        form.lst.ItemToolTip[0] = "/projects/Demo.vp6p"
        assert form.lst.ItemToolTip(0) == "/projects/Demo.vp6p"
        assert form.bar.PreferredWidth > 0
    finally:
        Unload(form)


def test_drawing_caps_joins_font_scale_and_paths(qapp):
    picture = Picture(40, 40, BackColor=0xFFFFFF)
    picture.DrawWidth = 6
    picture.DrawCap = vpCapSquare
    picture.Line(10, 20, 30, 20, 0)
    assert picture.Point(8, 20) == 0  # (a square end goes beyond the end point)
    picture.Cls()
    picture.DrawCap = vpCapRound
    picture.DrawJoin = vpJoinBevel
    picture.Line(10, 20, 30, 20, 0)
    picture.FontSize = 7.5  # (a fraction kept)
    assert picture.FontSize == 7.5
    width = picture.TextWidth("Aa")
    picture.FontScale = 2
    assert abs(picture.TextWidth("Aa") - 2 * width) < 0.01
    disc = GraphicsPath().AddEllipse(0, 0, 20, 20)
    bite = GraphicsPath().AddEllipse(10, 0, 20, 20)
    moon = Picture(40, 40, BackColor=0xFFFFFF)
    moon.DrawPath(disc.Subtract(bite), 0, 0)
    assert moon.Point(3, 10) == 0 and moon.Point(18, 10) == 0xFFFFFF  # (the bite)
    both = Picture(40, 40, BackColor=0xFFFFFF)
    both.DrawPath(disc.Intersect(bite), 0, 0)
    assert both.Point(15, 10) == 0 and both.Point(3, 10) == 0xFFFFFF
    union = Picture(40, 40, BackColor=0xFFFFFF)
    union.DrawPath(disc.Unite(bite), 0, 0)
    assert union.Point(3, 10) == 0 and union.Point(27, 10) == 0


def test_input_number_and_msgbox(qapp, monkeypatch):
    def answer(set_value, accept):
        def run(dialog):
            set_value(dialog)
            return 1 if accept else 0
        return run

    monkeypatch.setattr(QInputDialog, "exec", answer(lambda d: d.setIntValue(7), True))
    assert vp6.InputNumber("Line:", "Go to Line", 1, 1, 10) == 7
    monkeypatch.setattr(QInputDialog, "exec", answer(lambda d: None, False))
    assert vp6.InputNumber("Line:") is None

    def click(which):
        def run(box):
            which(box).click()
            return 0
        return run

    monkeypatch.setattr(QMessageBox, "exec", click(lambda box: box.button(QMessageBox.Save)))
    assert vp6.MsgBox("Save?", vpSaveDiscardCancel) == vpSave
    monkeypatch.setattr(QMessageBox, "exec", click(lambda box: box.button(QMessageBox.Discard)))
    assert vp6.MsgBox("Save?", vpSaveDiscardCancel) == vpDiscard
    monkeypatch.setattr(QMessageBox, "exec", click(
        lambda box: next(b for b in box.buttons() if b.text() == "Show in Folder")))
    assert vp6.MsgBox("Made it", vpOKOnly, "Make", ExtraButton="Show in Folder") == \
        vpExtraButton


def test_screen_and_help_tab(qapp):
    assert vp6.Screen.FontDPI in (72.0, 96.0) or vp6.Screen.FontDPI > 0
    viewer = vp6.ShowHelp(Tab="Search")
    try:
        assert viewer.tabs.currentIndex() == 2
    finally:
        viewer.close()
    with pytest.raises(ValueError):
        vp6.ShowHelp(Tab="Glossary")
