import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from vp6 import formfile
from vp6.ide.designer import GRID, FormDesigner
from vp6.ide.documents import FormDocument


@pytest.fixture
def designer(qapp, tmp_path):
    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    doc = FormDocument(str(path))
    d = FormDesigner(doc, str(tmp_path))
    d.ask_create_array = lambda name: False  # "No" instead of a blocking message box
    d.resize(900, 700)
    d.show()
    yield d
    d.close()


def form_point(d, x, y) -> QPoint:
    return d.form_canvas_rect().topLeft() + QPoint(x, y)


def test_create_controls_writes_region(designer):
    d = designer
    name = d.create_control("CommandButton", QRect(form_point(d, 10, 10), form_point(d, 110, 45)),
                            None)
    assert name == "Command1"
    props = formfile.parse(d.document.text).control("Command1").props
    assert props["Left"] % GRID == 0 and props["Caption"] == "Command1"
    assert d.document.modified


def test_nested_creation_in_frame(designer):
    d = designer
    d.create_control("Frame", QRect(form_point(d, 16, 16), form_point(d, 216, 176)), None)
    inside = form_point(d, 60, 60)
    assert d.container_at(inside) == "Frame1"
    d.create_control("CheckBox", None, "Frame1", inside)
    assert d.form_def.control("Check1").parent == "Frame1"
    # deleting the frame deletes its children
    d.select(["Frame1"])
    d.delete_selection()
    assert d.form_def.controls == []


def test_mouse_move_and_undo(designer):
    d = designer
    d.create_control("Label", QRect(form_point(d, 16, 16), form_point(d, 112, 40)), None)
    start = d.canvas_rect("Label1").center()
    QTest.mousePress(d.overlay, Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(d.overlay, start + QPoint(20, 5))
    QTest.mouseMove(d.overlay, start + QPoint(41, 17))
    QTest.mouseRelease(d.overlay, Qt.LeftButton, Qt.NoModifier, start + QPoint(41, 17))
    props = d.form_def.control("Label1").props
    assert (props["Left"], props["Top"]) == (56, 32)
    assert "Left=56, Top=32" in d.document.text
    d.undo()
    assert d.form_def.control("Label1").props["Left"] == 16
    d.redo()
    assert d.form_def.control("Label1").props["Left"] == 56


def test_rubber_band_selection(designer):
    d = designer
    for x in (16, 136):
        d.create_control("CommandButton", QRect(form_point(d, x, 16), form_point(d, x + 96, 48)),
                         None)
    d.create_control("CommandButton", QRect(form_point(d, 16, 200), form_point(d, 112, 232)), None)
    a, b = form_point(d, 4, 4), form_point(d, 260, 60)
    QTest.mousePress(d.overlay, Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(d.overlay, b)
    QTest.mouseRelease(d.overlay, Qt.LeftButton, Qt.NoModifier, b)
    assert sorted(d.selection) == ["Command1", "Command2"]


def test_set_property_and_rename(designer):
    d = designer
    d.create_control("CommandButton", None, None, form_point(d, 16, 16))
    d.document.text_document.setPlainText(
        d.document.text + "\n    def Command1_Click(self):\n        self.Command1.Caption = 'x'\n")
    d.select(["Command1"])
    assert d.set_property("Caption", "&Go") is None
    assert d.controls["Command1"].Caption == "&Go"
    assert d.set_property("Name", "cmdGo") is None
    text = d.document.text
    assert "self.cmdGo = CommandButton(self, Caption='&Go'" in text
    assert "def cmdGo_Click(self):" in text and "self.cmdGo.Caption" in text
    assert d.set_property("Name", "not valid") is not None
    d.select([])
    assert d.set_property("Name", "frmMain") is None
    assert "class frmMain(Form):" in d.document.text


def test_copy_paste(designer):
    d = designer
    d.create_control("Frame", QRect(form_point(d, 16, 16), form_point(d, 216, 176)), None)
    d.create_control("OptionButton", None, "Frame1", form_point(d, 40, 40))
    d.select(["Frame1"])
    d.copy_selection()
    d.paste()
    names = [c.name for c in d.form_def.controls]
    assert names == ["Frame1", "Option1", "Frame2", "Option2"]
    assert d.form_def.control("Option2").parent == "Frame2"
    assert d.selection == ["Frame2"]


def _tab_order(d) -> dict[str, int]:
    return {c.name: c.props.get("TabIndex", 0) for c in d.form_def.controls
            if c.type != "Timer"}


def test_tab_index_is_renumbered(designer):
    d = designer
    for x in (16, 136, 256):
        d.create_control("CommandButton", QRect(form_point(d, x, 16), form_point(d, x + 96, 48)),
                         None)
    d.create_control("Timer", None, None, form_point(d, 16, 200))  # no TabIndex
    assert _tab_order(d) == {"Command1": 0, "Command2": 1, "Command3": 2}  # added at the end
    assert d.controls["Command3"].TabIndex == 2

    d.select(["Command1"])
    d.delete_selection()  # the others close the gap
    assert _tab_order(d) == {"Command2": 0, "Command3": 1}
    assert formfile.parse(d.document.text).control("Command3").props["TabIndex"] == 1

    d.select(["Command3"])
    d.copy_selection()
    d.select(["Command2"])
    d.paste()  # Command1 again; pasted controls go to the end, instead of sharing Command3's number
    assert _tab_order(d) == {"Command2": 0, "Command3": 1, "Command1": 2}

    d.select(["Command1"])
    assert d.set_property("TabIndex", 0) is None  # takes place 0, the others make room
    assert _tab_order(d) == {"Command1": 0, "Command2": 1, "Command3": 2}
    assert d.controls["Command2"].TabIndex == 1
    d.select(["Command1"])
    assert d.set_property("TabIndex", 99) is None  # past the end: the last place
    assert _tab_order(d) == {"Command2": 0, "Command3": 1, "Command1": 2}
    d.undo()  # one undo step, renumbering included
    assert _tab_order(d) == {"Command1": 0, "Command2": 1, "Command3": 2}


def test_z_order_and_format(designer):
    d = designer
    d.create_control("Label", QRect(form_point(d, 16, 16), form_point(d, 112, 40)), None)
    d.create_control("Label", QRect(form_point(d, 40, 80), form_point(d, 200, 120)), None)
    d.select(["Label2", "Label1"])  # Label1 is the reference (last selected)
    d.align("left")
    d.make_same_size("width")
    label2 = d.form_def.control("Label2").props
    assert label2["Left"] == 16 and label2["Width"] == 96


def test_z_order_uses_zindex_and_clicks_pick_the_top_control(designer):
    d = designer
    # Two overlapping buttons: Command2 (created later) starts on top
    d.create_control("CommandButton", QRect(form_point(d, 16, 16), form_point(d, 112, 48)), None)
    d.create_control("CommandButton", QRect(form_point(d, 48, 24), form_point(d, 144, 56)), None)
    overlap = form_point(d, 80, 36)
    assert d.control_at(overlap) == "Command2"
    d.select(["Command1"])
    d.z_order(True)  # Bring to Front
    assert d.controls["Command1"].ZIndex > d.controls["Command2"].ZIndex
    assert d.control_at(overlap) == "Command1"
    assert "ZIndex=1" in d.document.text
    d.undo()
    assert d.control_at(overlap) == "Command2"
    d.select(["Command2"])
    d.z_order(False)  # Send to Back
    assert d.control_at(overlap) == "Command1"
    d.select(["Command1"])
    assert d.set_property("ZIndex", -5) is None  # from the Properties window
    assert d.control_at(overlap) == "Command2"


def test_code_side_undo_reloads_designer(designer):
    d = designer
    d.create_control("Timer", None, None, form_point(d, 16, 16))
    assert "Timer1" in d.controls
    d.document.text_document.undo()
    assert "Timer1" not in d.controls
    d.document.text_document.redo()
    assert "Timer1" in d.controls


def test_form_resize_via_property(designer):
    d = designer
    d.select([])
    assert d.set_property("Width", 640) is None
    assert d.form_widget().width() == 640
    assert "self.Width = 640" in d.document.text


def test_region_is_protected_in_code_editor(designer):
    from vp6.ide.codeeditor import CodeEditor

    editor = CodeEditor(designer.document)
    start, end = designer.document.region_range()
    cursor = QTextCursor(editor.document().findBlockByNumber(start + 2))
    editor.setTextCursor(cursor)
    before = designer.document.text
    QTest.keyClicks(editor, "junk")
    assert designer.document.text == before
    cursor = QTextCursor(editor.document().findBlockByNumber(end + 2))
    editor.setTextCursor(cursor)
    QTest.keyClicks(editor, "#ok")
    assert "#ok" in designer.document.text


def test_workspace_fills_designer_after_maximize_and_restore(qapp, tmp_path):
    from PySide6.QtWidgets import QMdiArea

    path = tmp_path / "Form1.py"
    path.write_text(formfile.new_form_source("Form1"))
    mdi = QMdiArea()
    mdi.resize(1400, 900)
    mdi.show()
    d = FormDesigner(FormDocument(str(path)), str(tmp_path))
    sub = mdi.addSubWindow(d)
    sub.resize(700, 500)
    sub.show()

    def canvas_covers_viewport():
        viewport, canvas = d.scroll.viewport().size(), d.canvas.size()
        return canvas.width() >= viewport.width() and canvas.height() >= viewport.height()

    for change in (lambda: None, sub.showMaximized, sub.showNormal, sub.showMaximized):
        change()
        QTest.qWait(20)
        assert canvas_covers_viewport()
        assert d.overlay.geometry() == d.canvas.rect()  # mouse handling covers it too
    mdi.close()
