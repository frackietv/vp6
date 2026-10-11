"""The New Project dialog's categories (Standard EXE and Console Application
at the top level, the samples in Sample Projects and its folders) and the
sample projects: Projection (a turning model, solid or wireframe, the axes
behind it, in eight parallel projections; an axis, the axes or the model
dragged; its angles and rates on sliders; a cube, a pyramid, a torus, a
house, a few boxes or a downtown, their parts drawn back to front)."""

import importlib.util
import math
import os

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

import vp6
from vp6.ide import samples
from vp6.ide.dialogs import FOLDER_ROLE, TEMPLATES, NewProjectDialog, categories
from vp6.ide.mainwindow import create_project
from vp6.project import Project


def shown(dialog):
    return [dialog.templates.item(i).text() for i in range(dialog.templates.count())]


@pytest.fixture
def dialog(qapp):
    dialog = NewProjectDialog([])
    yield dialog
    dialog.close()


def test_categories(dialog):
    assert categories() == ["Sample Projects", "Sample Projects/Graphics"]
    # The top level: the two kinds of project, then the samples' folder
    assert shown(dialog) == ["Standard EXE", "Console Application", "Sample Projects"]
    assert dialog.template == "exe" and dialog.category == ""
    dialog.templates.setCurrentRow(2)  # a folder: no template, its contents described
    assert dialog.template is None and "Kitchen Sink" in dialog.template_help.text()
    dialog._open_item(dialog.templates.currentItem())  # double-click: open it
    assert dialog.category == "Sample Projects"
    assert shown(dialog) == ["Kitchen Sink", "Graphics"] and dialog.template == "kitchensink"
    assert dialog.categories.currentItem().text(0) == "Sample Projects"
    dialog.templates.setCurrentRow(1)
    dialog._accept()  # Open on a folder opens it too
    assert dialog.category == "Sample Projects/Graphics" and dialog.result_action is None
    assert shown(dialog) == ["Projection"] and dialog.template == "projection"
    assert "isometric" in dialog.template_help.text() and "torus" in dialog.template_help.text()
    dialog.select_template("console")
    assert dialog.category == "" and dialog.template == "console"
    item = dialog.templates.currentItem()
    assert item.data(FOLDER_ROLE) is None
    # Every template is in a category the tree has
    tree = set(dialog._category_items)
    assert {t[4] for t in TEMPLATES} <= tree


def test_choosing_a_sample(dialog, tmp_path):
    dialog.location.setText(str(tmp_path))
    dialog.select_template("projection")
    dialog._accept()
    assert dialog.result_action == "new" and dialog.template == "projection"


# --- Projection ---------------------------------------------------------------------------

@pytest.fixture
def projection(qapp, tmp_path):
    path = create_project(str(tmp_path), "Cube", "projection")
    project = Project.load(path)
    spec = importlib.util.spec_from_file_location(
        "projection_Form1", os.path.join(project.directory, "Form1.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    form = module.Form1()
    form.tmrSpin.Enabled = False  # (turned by hand here)
    form.Show()
    QTest.qWait(20)
    yield project, module, form
    form.Unload()


def test_the_project(projection):
    project, module, form = projection
    assert project.forms == ["Form1.py"] and project.modules == []  # a single form
    assert project.startup == "Form1" and project.type == "exe"
    assert sorted(set(os.listdir(project.directory)) - {"__pycache__"}) == ["Cube.vp6p", "Form1.py"]
    assert samples.SAMPLES["projection"].description == project.description


def test_isometric_projection(projection):
    _, module, form = projection
    assert form.cboProjection.Text == "Isometric (orthographic)"
    assert form.elevation == pytest.approx(35.264, abs=1e-3)
    right, up, toward = form.Camera()
    assert toward == pytest.approx((1 / math.sqrt(3),) * 3)  # along the cube's diagonal
    assert form.Toward() == pytest.approx(toward)
    # The axes on the picture: 120 degrees apart, equally long
    origin = form.Project((0, 0, 0))
    ends = [form.Project(axis) for axis, _, _ in module.AXES]
    vectors = [(x - origin[0], y - origin[1]) for x, y in ends]
    lengths = [math.hypot(*v) for v in vectors]
    assert lengths[0] == pytest.approx(lengths[1]) == pytest.approx(lengths[2])
    assert form.AxisAngles() == pytest.approx((120, 120, 120))
    assert ends[2][1] < origin[1]  # Z up
    assert "Isometric" in form.lblView.Caption
    assert form.lblAngles.Caption == "X–Y:  120.0°\nY–Z:  120.0°\nZ–X:  120.0°"


def test_the_projections(projection):
    _, module, form = projection
    names = [p[0] for p in module.PROJECTIONS]
    assert form.cboProjection.List == names and len(names) == 8

    def length(i):
        return math.hypot(*form.AxisVector(i))

    def choose(name):
        form.cboProjection.ListIndex = names.index(name)  # (its Click sets it)
        assert form.Describe() == name and form.kind == names.index(name)
        return form.AxisAngles()

    assert choose("Elevation (orthographic)") == (None, None, pytest.approx(90))  # Y is lost
    assert form.AxisVector(0) == pytest.approx((1, 0))
    assert form.AxisVector(2) == pytest.approx((0, 1))
    assert "X–Y:  —" in form.lblAngles.Caption
    assert choose("Plan (orthographic)") == (pytest.approx(90), None, None)  # Z is lost
    assert form.AxisVector(1) == pytest.approx((0, 1))
    choose("Dimetric (orthographic)")  # X half as long as Y and Z, at 41 and 7 degrees
    assert length(1) == pytest.approx(length(2)) == pytest.approx(2 * length(0))
    x, y = form.AxisVector(1)
    assert math.degrees(math.atan2(y, x)) == pytest.approx(-7.18, abs=0.01)
    choose("Trimetric (orthographic)")
    assert len({round(length(i), 2) for i in range(3)}) == 3
    # The oblique ones: a plane true, the third axis drawn at an angle
    assert choose("Military (oblique)") == pytest.approx((90, 135, 135))
    assert form.AxisVector(2) == pytest.approx((0, 1)) and length(0) == pytest.approx(1)
    assert choose("Cavalier (oblique)") == pytest.approx((45, 45, 90))
    assert length(1) == pytest.approx(1)  # receding at full length
    assert choose("Top-down (oblique)") == pytest.approx((90, 0, 90))
    assert form.AxisVector(2) == pytest.approx((0, 0.5))
    for name in names:  # each draws solid: the faces it can see
        choose(name)
        assert form.Toward() is not None
        assert form.picView.Point(form.picView.ScaleWidth / 2,
                                  form.picView.ScaleHeight / 2) != form.picView.BackColor


def test_solid_and_wireframe(projection):
    _, module, form = projection
    form.SetAngles(20, 10, 30)  # (square to the axes, two corners land on the middle)
    pic = form.picView
    middle = (pic.ScaleWidth / 2, pic.ScaleHeight / 2)
    background = pic.BackColor
    assert form.chkWireframe.Value == vp6.vpUnchecked
    assert pic.Point(*middle) != background  # a face covers the middle
    # The axes are drawn behind the model: Z's end is beyond it, on the background
    z_end = form.Project((0, 0, module.AXIS_LENGTH - 0.05))
    assert pic.Point(*z_end) == module.AXES[2][1]
    form.chkWireframe.Value = vp6.vpChecked  # (Click redraws)
    assert pic.Point(*middle) in (background, module.AXES[0][1], module.AXES[1][1],
                                  module.AXES[2][1])  # the axes show through
    corner = form.Project(form.Turned(module.CORNERS[7]))
    assert pic.Point(*corner) == vp6.RGB(255, 210, 80)  # a corner's dot


def test_the_model_turning(projection):
    _, module, form = projection
    assert (form.roll, form.pitch, form.tumble) == (0, 0, 0)
    rates = (form.sldRollRate.Value, form.sldPitchRate.Value, form.sldTumbleRate.Value)
    assert rates == (15, 10, 40) and form.lblTumbleRateValue.Caption == "40%"
    form.tmrSpin_Timer()  # the timer turns it at the rates
    assert form.roll == pytest.approx(0.15 * module.FULL_RATE)
    assert form.tumble == pytest.approx(0.4 * module.FULL_RATE)
    assert form.sldTumble.Value == round(form.tumble)
    assert form.lblTumbleValue.Caption == f"{round(form.tumble)}°"
    form.sldPitchRate.Value = 0
    assert form.lblPitchRateValue.Caption == "0%"
    pitch = form.pitch
    form.tmrSpin_Timer()
    assert form.pitch == pitch
    form.chkRotate.Value = vp6.vpUnchecked
    roll = form.roll
    form.tmrSpin_Timer()
    assert form.roll == roll
    # The sliders set the angles
    form.sldRoll.Value, form.sldPitch.Value, form.sldTumble.Value = 30, -45, 170
    assert (form.roll, form.pitch, form.tumble) == (30, -45, 170)
    assert form.lblPitchValue.Caption == "-45°"
    turned = form.Turned((1, 0, 0))
    assert turned == pytest.approx(module.times(form.Orientation(), (1, 0, 0)))
    assert module.angles_of(form.Orientation()) == pytest.approx((30, -45, 170))
    form.SetAngles(0, 0, 178)
    form.chkRotate.Value = vp6.vpChecked
    form.sldTumbleRate.Value = 100
    form.tmrSpin_Timer()  # past 180: from -180 again
    assert form.tumble == pytest.approx(-182 + module.FULL_RATE)


def drag(form, start, end, steps=4):
    widget = form.picView._widget
    start, end = QPoint(*map(round, start)), QPoint(*map(round, end))
    QTest.mousePress(widget, Qt.LeftButton, Qt.NoModifier, start)
    for k in range(1, steps + 1):
        QTest.mouseMove(widget, start + (end - start) * k / steps)
    QTest.mouseRelease(widget, Qt.LeftButton, Qt.NoModifier, end)
    assert form.drag is None


def test_what_the_mouse_takes(projection):
    _, module, form = projection
    pic = form.picView
    assert form.HitTest(5, 5) == ("space",)
    assert form.HitTest(pic.ScaleWidth / 2, pic.ScaleHeight / 2) == ("model",)
    for i in range(3):
        end = form.Project(tuple(module.AXIS_LENGTH * a for a in module.AXES[i][0]))
        assert form.HitTest(*end) == ("axis", i)
        assert form.HitTest(*form.LabelPlace(i)) == ("axis", i)
    QTest.mouseMove(pic._widget, QPoint(5, 5))
    assert pic.MousePointer == vp6.vpDefault
    QTest.mouseMove(pic._widget, QPoint(round(pic.ScaleWidth / 2), round(pic.ScaleHeight / 2)))
    assert pic.MousePointer == vp6.vpSizeAll


def test_dragging_an_axis(projection):
    _, module, form = projection
    form.tmrSpin.Enabled = False
    y_axis, z_axis = form.AxisVector(1), form.AxisVector(2)
    end = form.Project((module.AXIS_LENGTH, 0, 0))
    origin = form.Project((0, 0, 0))
    target = (origin[0] - 200, origin[1])  # X straight left
    drag(form, end, target)
    x = form.AxisVector(0)
    assert x[1] == pytest.approx(0, abs=0.01) and x[0] < 0
    assert math.hypot(*x) * form.Scale() * module.AXIS_LENGTH == pytest.approx(200, abs=1)
    assert form.AxisVector(1) == pytest.approx(y_axis)  # just that axis
    assert form.AxisVector(2) == pytest.approx(z_axis)
    angles = form.AxisAngles()
    assert angles[1] == pytest.approx(120)  # Y-Z as they were
    assert angles[0] != pytest.approx(120) and angles[2] != pytest.approx(120)
    assert form.Describe() == "A general parallel projection (oblique)"
    assert "general parallel" in form.lblView.Caption
    assert form.cboProjection.Text == "Isometric (orthographic)"  # (what Reset goes back to)
    # The empty space turns all of them, the skew kept
    skew = form.skew
    drag(form, (5, 5), (45, 5))
    assert form.skew == skew and form.azimuth == pytest.approx(45 - math.degrees(0.4))
    form.picView_DblClick()  # back to isometric
    assert form.Describe() == "Isometric (orthographic)"
    assert form.AxisAngles() == pytest.approx((120, 120, 120))
    form.skew = ((1, 0, 0.3), (0, 1, 0))
    form.cmdReset._widget.click()
    assert form.Describe() == "Isometric (orthographic)"


def test_dragging_the_space_turns_the_axes(projection):
    _, module, form = projection
    drag(form, (5, 5), (55, 25))
    assert form.azimuth == pytest.approx(45 - math.degrees(50 * module.DRAG_SPEED))
    assert form.elevation == pytest.approx(module.ISOMETRIC_ELEVATION
                                           + math.degrees(20 * module.DRAG_SPEED))
    assert form.Describe() == "Trimetric (orthographic)"  # still orthographic
    assert (form.roll, form.pitch, form.tumble) == (0, 0, 0)  # the cube not turned
    drag(form, (5, 5), (5, 900))  # (the elevation stops at straight down)
    assert form.elevation == 90
    form.cboProjection.ListIndex = 0  # another projection: its own view
    assert form.elevation == 0 and form.Describe() == "Elevation (orthographic)"


def flat(matrix):
    return [value for row in matrix for value in row]


def test_dragging_the_model_turns_it(projection):
    _, module, form = projection
    pic = form.picView
    middle = (pic.ScaleWidth / 2, pic.ScaleHeight / 2)
    projection = form.Projection()
    drag(form, middle, (middle[0] + 30, middle[1]))
    assert form.Projection() == projection  # the axes stay
    # Turned right around the camera's up axis
    _, up, _ = form.Camera()
    expected = module.rotation(up, 30 * module.DRAG_SPEED)
    assert flat(form.Orientation()) == pytest.approx(flat(expected))
    assert form.sldTumble.Value == round(form.tumble) and form.tumble != 0
    form.SetAngles(0, 0, 0)
    drag(form, middle, (middle[0], middle[1] + 20))
    right, _, _ = form.Camera()
    assert flat(form.Orientation()) == pytest.approx(
        flat(module.rotation(right, 20 * module.DRAG_SPEED)))


def test_resizing(projection):
    _, _, form = projection
    form.Width, form.Height = 1000, 760
    QTest.qWait(20)
    assert form.picView.Width == form.ScaleWidth - 312
    assert form.cboProjection.Left == form.picView.Left + form.picView.Width + 16
    assert form.sldRoll.Left == form.cboProjection.Left + 76


# --- the models ---------------------------------------------------------------------------

def points_of(part):
    return {c for corners, _, _ in part for c in corners}


def test_the_models_toggles(projection):
    _, module, form = projection
    captions = [form.optModel[i].Caption for i in range(6)]
    assert captions == [c for c, _ in module.MODELS]
    assert captions == ["&Cube", "P&yramid", "&Torus", "&House", "&Boxes", "&Downtown"]
    assert form.optModel[0].Value and form.model.name == "Cube"
    form.chkRotate.Value = vp6.vpUnchecked
    form.SetAngles(0, 0, 0)
    for i, name in enumerate(["Cube", "Pyramid", "Torus", "House", "Boxes", "Downtown"]):
        form.optModel[i].Value = True  # (its Click sets it)
        assert form.model is module.model(i) and form.model.name == name
        assert form.optModel[0].Value == (i == 0)  # (one at a time)
        corners = form.model.parts[0][0][0]
        assert form.HitTest(*form.Project(form.Turned(module.mean(corners)))) == ("model",)
    pic = form.picView
    middle = (pic.ScaleWidth / 2, pic.ScaleHeight / 2)
    form.optModel[2].Value = True  # the torus: its hole shows the axes or the background
    assert form.HitTest(*middle) == ("axis", 0)  # (where the axes meet, not the torus)
    assert pic.Point(*middle) in (pic.BackColor,) + tuple(color for _, color, _ in module.AXES)
    tube = form.Project(form.Turned((module.TORUS_RADII[0], 0, 0)))
    assert form.HitTest(*tube) == ("model",) and pic.Point(*tube) != pic.BackColor
    form.chkWireframe.Value = vp6.vpChecked  # a model's wireframe: its corners dotted
    form.optModel[3].Value = True
    ridge = form.Project(form.Turned((1, 0, 0.9)))
    assert pic.Point(*ridge) == vp6.RGB(255, 210, 80)
    assert len(form.model.edges) == 15 + 4 * 4  # (the house's, then a door's and windows')


def test_the_models_faces(projection):
    _, module, form = projection
    for i in range(len(module.MODELS)):
        model = module.model(i)
        assert model.points and model.edges
        for part in model.parts:
            for corners, normal, _ in part:
                assert math.sqrt(module.dot(normal, normal)) == pytest.approx(1)
                origin = corners[0]
                for c in corners:  # flat
                    assert module.dot(tuple(a - b for a, b in zip(c, origin)),
                                      normal) == pytest.approx(0, abs=1e-9)
                if model.convex and len(part) > 1:  # outward: the rest of the part inside
                    for c in points_of(part):
                        assert module.dot(tuple(a - b for a, b in zip(c, origin)),
                                          normal) <= 1e-9
        assert all(abs(x) <= 1.2 for p in model.points for x in p)  # (within the axes)
    torus = module.model(2)
    assert not torus.convex and torus.separations == {}
    assert len(torus.parts[0]) == module.TORUS_STEPS[0] * module.TORUS_STEPS[1]
    for corners, normal, _ in torus.parts[0]:  # away from the tube's middle
        x, y, z = module.mean(corners)
        ring = math.hypot(x, y)
        tube = (x - x / ring * module.TORUS_RADII[0], y - y / ring * module.TORUS_RADII[0], z)
        assert module.dot(normal, tube) > 0
    house = module.model(3)
    assert len(house.parts) == 5 and len(house.parts[0]) == 7  # walls, gables, roof, floor


def test_the_parts_separations(projection):
    _, module, form = projection
    boxes = module.model(4)
    n = len(boxes.parts)
    assert len(boxes.separations) == n * (n - 1) // 2  # (boxes apart: always a plane)
    for (a, b), normal in boxes.separations.items():
        assert max(module.dot(c, normal) for c in points_of(boxes.parts[a])) <= \
            min(module.dot(c, normal) for c in points_of(boxes.parts[b])) + 1e-9
    downtown = module.model(5)
    assert downtown.separations[0, 1] == pytest.approx((0, 0, 1))  # a street on the ground
    assert module.Model.Separation(module.box((0, 0, 0), (1, 1, 1), (1, 2, 3)),
                                   module.box((0.5, 0.5, 0.5), (2, 2, 2), (1, 2, 3))) is None


def test_the_parts_drawn_back_to_front(projection):
    _, module, form = projection
    form.chkRotate.Value = vp6.vpUnchecked
    order = []
    original = form.PartOrder

    def recording(*args):
        order[:] = original(*args)
        return order

    form.PartOrder = recording
    form.optModel[4].Value = True
    form.SetAngles(0, 0, 0)  # the tall blue box (2) in front of the red one (0)
    assert order.index(0) < order.index(2)
    form.SetAngles(0, 0, 180)  # turned half way round: the red one in front
    assert order.index(0) > order.index(2)
    form.optModel[5].Value = True  # the ground first, the park before its trees
    form.SetAngles(0, 0, 0)
    assert order[0] == 0 and all(order.index(12) < order.index(tree) for tree in range(13, 17))
    form.SetAngles(180, 0, 0)  # upside down: the park, facing away, isn't drawn
    assert 12 not in order and 0 in order
    form.PartOrder = original


def test_hull_and_overlap():
    spec = importlib.util.spec_from_file_location(
        "projection_geometry", os.path.join(os.path.dirname(samples.__file__), "templates",
                                            "projection", "Form1.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    square = module.hull([(0, 0), (10, 0), (10, 10), (0, 10), (5, 5), (10, 5)])
    assert sorted(square) == [(0, 0), (0, 10), (10, 0), (10, 10)]
    assert module.overlap(square, module.hull([(5, 5), (20, 5), (20, 20)]))
    assert not module.overlap(square, module.hull([(11, 0), (20, 0), (20, 10)]))
    assert not module.overlap(square, module.hull([(10.5, 0), (20, 0), (20, 10)]))  # (a pixel)
    assert not module.overlap(square, module.hull([(12, 0), (20, -8), (21, 1)]))
