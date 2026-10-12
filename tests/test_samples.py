"""The New Project dialog's categories (Standard EXE and Console Application
at the top level, the samples in Sample Projects and its folders) and the
sample projects: Projection (a turning model, solid or wireframe, the axes
behind it, in eight parallel projections; an axis, the axes or the model
dragged; its angles and rates on sliders; a cube, a pyramid, a torus, a
house, a few boxes or a downtown, their parts drawn back to front) and
Perspectives (the same models in 1- to 6-point perspective: linear,
cylindrical, fisheye, spherical; vanishing points dragged or at infinity;
perspective lines; the eye nearer, farther or inside the model)."""

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
    assert shown(dialog) == ["Projection", "Perspectives"] and dialog.template == "projection"
    assert "isometric" in dialog.template_help.text() and "torus" in dialog.template_help.text()
    dialog.templates.setCurrentRow(1)
    assert dialog.template == "perspectives" and "6-point" in dialog.template_help.text()
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
    dialog.result_action = None
    dialog.select_template("perspectives")
    dialog._accept()
    assert dialog.result_action == "new" and dialog.template == "perspectives"


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



# --- Perspectives -------------------------------------------------------------------------

def load_perspectives(path):
    spec = importlib.util.spec_from_file_location("perspectives_Form1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def perspectives(qapp, tmp_path):
    path = create_project(str(tmp_path), "Eye", "perspectives")
    project = Project.load(path)
    module = load_perspectives(os.path.join(project.directory, "Form1.py"))
    form = module.Form1()
    form.tmrSpin.Enabled = False  # (turned by hand here)
    form.Show()
    QTest.qWait(20)
    yield project, module, form
    form.Unload()


def middle_of(form):
    pic = form.picView
    return pic.ScaleWidth / 2, pic.ScaleHeight / 2


def choose(form, index):
    form.cboPerspective.ListIndex = index  # (its Click sets it)
    assert form.kind == index


def vanishing(form):
    """The vanishing points: {(axis, sign): [places]} (None: at infinity)."""
    found = {}
    for i, sign, place, _ in form.VanishingPoints():
        found.setdefault((i, sign), []).append(place)
    return found


def test_the_perspectives_project(perspectives):
    project, module, form = perspectives
    assert project.forms == ["Form1.py"] and project.modules == []  # a single form
    assert project.startup == "Form1" and project.type == "exe"
    assert samples.SAMPLES["perspectives"].description == project.description
    assert form.cboPerspective.Text == "3-point (linear)"  # (shown first)
    assert form.Describe() == "3-point perspective (linear)"
    assert "3-point perspective" in form.lblView.Caption


def test_the_six_perspectives(perspectives):
    _, module, form = perspectives
    names = [p[0] for p in module.PERSPECTIVES]
    assert form.cboPerspective.List == names and len(names) == 6
    kinds = ["linear"] * 3 + ["curvilinear: cylindrical", "curvilinear: fisheye",
                              "curvilinear: spherical"]
    # Where each axis's vanishing point is (PLACES: at a point, at infinity up, down,
    # left, right): 1-point: X right and Z up at infinity; 2-point: Z; 3-point: none;
    # cylindrical: Z (straight up); fisheye and the sphere: X and Z on the rim
    places = [[4, 0, 1], [0, 0, 1], [0, 0, 0], [0, 0, 1], [4, 0, 1], [4, 0, 1]]
    for index in range(6):
        choose(form, index)
        assert form.Describe() == f"{index + 1}-point perspective ({kinds[index]})"
        assert form.Count() == index + 1
        assert [form.cboPlace[i].ListIndex for i in range(3)] == places[index]
        assert form.picView.Point(*middle_of(form)) != form.picView.BackColor  # (drawn solid)
    assert [form.cboPlace[i].List for i in range(3)] == [list(module.PLACES)] * 3


def test_linear_perspective(perspectives):
    _, module, form = perspectives
    choose(form, 1)  # 2-point: X and Y meet on the horizon, Z upright
    points = vanishing(form)
    (x_vp,), (y_vp,), (z_vp,) = points[0, 1], points[1, 1], points[2, 1]
    assert z_vp is None and x_vp[1] == pytest.approx(y_vp[1])  # (level: on the horizon)
    assert x_vp[0] < middle_of(form)[0] < y_vp[0]

    def picture(point):
        return form.ToPicture(form.Map(form.Ray(point)))

    # Lines along X head for X's vanishing point; upright ones stay upright
    assert picture((1e6, 0.3, -0.4)) == pytest.approx(x_vp, abs=0.1)
    assert picture((-0.5, 1e6, 0.9)) == pytest.approx(y_vp, abs=0.1)
    bottom, top = picture((0.4, -0.7, -1)), picture((0.4, -0.7, 1))
    assert bottom[0] == pytest.approx(top[0]) and top[1] < bottom[1]
    # Nearer is bigger: the front edge (toward the eye) is taller than the back one
    front = picture((1, -1, -1))[1] - picture((1, -1, 1))[1]
    back = picture((-1, 1, -1))[1] - picture((-1, 1, 1))[1]
    assert front > back > 0
    choose(form, 0)  # 1-point: Y's in the middle of the eye's view, up and right of the center
    (y_vp,) = vanishing(form)[1, 1]
    middle = middle_of(form)
    shift = module.PERSPECTIVES[0][5]
    assert y_vp == pytest.approx((middle[0] + shift[0] * form.Scale(),
                                  middle[1] - shift[2] * form.Scale()))
    assert picture((0, 0, 0)) == pytest.approx(middle)  # (the model's center in the middle)


def test_curvilinear_perspectives(perspectives):
    _, module, form = perspectives
    choose(form, 4)  # fisheye: +Y in the middle, four on the rim
    points = vanishing(form)
    middle = middle_of(form)
    rim = form.focal * math.pi / 2 * form.Scale()
    assert points[1, 1] == [pytest.approx(middle)] and (1, -1) not in points  # (behind)
    for key in ((0, 1), (0, -1), (2, 1), (2, -1)):
        (place,) = points[key]
        assert math.dist(place, middle) == pytest.approx(rim)
    assert points[2, 1][0][1] < middle[1]  # +Z up
    # Straight edges bend: the middle of the cube's top front edge isn't on the chord
    ends = [form.ToPicture(form.Map(form.Ray(p))) for p in ((-1, -1, 1), (1, -1, 1))]
    halfway = form.ToPicture(form.Map(form.Ray((0, -1, 1))))
    assert halfway[1] < (ends[0][1] + ends[1][1]) / 2 - 5  # (bulging away from the middle)
    choose(form, 3)  # cylindrical: the four on the horizon, a quarter turn apart
    points = vanishing(form)
    rim = form.focal * math.pi / 2 * form.Scale()
    across = [points[key][0] for key in ((0, -1), (1, 1), (0, 1), (1, -1))]
    assert all(y == pytest.approx(middle[1]) for _, y in across)
    steps = [b[0] - a[0] for a, b in zip(across, across[1:])]
    assert steps == pytest.approx([rim] * 3)
    assert points[2, 1] == [None] and points[2, -1] == [None]  # upright lines stay upright
    choose(form, 5)  # spherical: the one behind in the middle of the lower half
    points = vanishing(form)
    rim = form.focal * math.pi / 2 * form.Scale()
    assert not form.Beside()  # (the picture is taller than wide)
    assert points[1, -1] == [pytest.approx((middle[0], middle[1] + rim))]
    assert len(points[0, 1]) == 2  # (on the rim: in both halves)
    assert points[2, -1][0] == pytest.approx((middle[0], middle[1]))  # (where they touch)


def test_dragging_a_vanishing_point(perspectives):
    _, module, form = perspectives
    points = vanishing(form)  # 3-point
    (z_vp,), (x_vp,) = points[2, 1], points[0, 1]
    assert form.HitTest(*z_vp) == ("vp", 2, 1)
    target = (round(z_vp[0]) + 60, round(z_vp[1]) - 40)  # (the mouse: on whole pixels)
    drag(form, z_vp, target)
    points = vanishing(form)
    assert points[2, 1] == [pytest.approx(target, abs=1.5)]
    assert points[0, 1] == [pytest.approx(x_vp)]  # (just that one)
    assert form.Describe() == "3-point perspective (linear)"
    form.picView_DblClick()  # back where they belong
    assert vanishing(form)[2, 1] == [pytest.approx(z_vp)]
    # One at infinity is shown at the edge; dragged, it comes to a point
    choose(form, 1)
    assert vanishing(form)[2, 1] == [None]
    marker, edge = form.Marker(None, (0, 1))
    assert edge and marker == pytest.approx((middle_of(form)[0], module.EDGE))
    assert form.HitTest(*marker) == ("vp", 2, 1)
    target = (round(marker[0]) + 20, 60)
    drag(form, marker, target)
    assert vanishing(form)[2, 1] == [pytest.approx(target, abs=1.5)]
    assert form.Describe() == "3-point perspective (linear)" and form.cboPlace[2].ListIndex == 0
    form.cmdReset._widget.click()
    assert form.Describe() == "2-point perspective (linear)"
    # A curvilinear one: the column turns to look there, the other way goes with it
    choose(form, 4)
    (x_vp,) = vanishing(form)[0, 1]
    target = (round(x_vp[0]) - 120, round(x_vp[1]) - 30)
    drag(form, x_vp, target)
    points = vanishing(form)
    assert points[0, 1] == [pytest.approx(target, abs=1.5)]
    assert (0, -1) not in points  # (now behind the eye)
    assert form.Describe() == "4-point perspective (curvilinear: fisheye)"


def test_vanishing_points_at_infinity(perspectives):
    _, module, form = perspectives
    # 3-point: X at infinity to the left: its lines parallel, going left
    form.cboPlace[0].ListIndex = 3
    assert not form.Finite(0) and form.Describe() == "2-point perspective (linear)"
    assert form.columns[0][:2] == pytest.approx((-length_of(form.columns[0]), 0))
    a = form.ToPicture(form.Map(form.Ray((0, 0, 0))))
    b = form.ToPicture(form.Map(form.Ray((1, 0, 0))))
    assert a[1] == pytest.approx(b[1]) and b[0] < a[0]
    form.cboPlace[1].ListIndex = 1  # Y up, Z down: none left: a parallel projection
    form.cboPlace[2].ListIndex = 2
    assert form.Describe() == "A parallel projection (no vanishing points)"
    assert form.Camera()[0] == "direction"  # (the eye infinitely far)
    assert form.picView.Point(*middle_of(form)) != form.picView.BackColor  # (still solid)
    form.cboPlace[2].ListIndex = 0  # Z at a point again: inside the picture
    assert form.Finite(2) and form.Describe() == "1-point perspective (linear)"
    (place,) = vanishing(form)[2, 1]
    assert not form.Marker(place, None)[1]
    # Curvilinear: at infinity is square to the line of sight: on the fisheye's rim
    choose(form, 4)
    form.cboPlace[1].ListIndex = 4  # Y (ahead) to the right
    points = vanishing(form)
    rim = form.focal * math.pi / 2 * form.Scale()
    middle = middle_of(form)
    assert points[1, 1] == [pytest.approx((middle[0] + rim, middle[1]))]
    assert points[1, -1] == [pytest.approx((middle[0] - rim, middle[1]))]
    assert form.Count() == 6


def length_of(v):
    return math.sqrt(sum(c * c for c in v))


def test_turning_the_scene_and_the_model(perspectives):
    _, module, form = perspectives
    choose(form, 1)
    before = vanishing(form)
    drag(form, (5, 5), (45, 5))  # sideways: around Z, upright lines stay upright
    after = vanishing(form)
    assert after[2, 1] == [None] and form.cboPlace[2].ListIndex == 1
    assert after[0, 1][0][1] == pytest.approx(before[0, 1][0][1])  # (along the horizon)
    assert after[0, 1][0][0] != pytest.approx(before[0, 1][0][0])
    assert (form.roll, form.pitch, form.tumble) == (0, 0, 0)  # (the model with it)
    drag(form, (5, 5), (5, 40))  # down: tipped toward the eye, Z comes to a point
    assert form.Finite(2) and form.Describe() == "3-point perspective (linear)"
    form.picView_DblClick()
    columns = list(form.columns)
    drag(form, middle_of(form), (middle_of(form)[0] + 30, middle_of(form)[1]))
    assert form.columns == columns  # the model turned, not the scene
    _, up, _ = form.Rows()
    expected = module.rotation(module.normalized(up), 30 * module.DRAG_SPEED)
    assert flat(form.Orientation()) == pytest.approx(flat(expected))
    assert form.sldTumble.Value == round(form.tumble) and form.tumble != 0


def test_the_eye_nearer_and_farther(perspectives):
    _, module, form = perspectives
    points = vanishing(form)
    corner = form.ToPicture(form.Map(form.Ray((1, -1, 1))))
    middle = middle_of(form)
    form.sldDistance.Value = 60  # farther: the model smaller, the vanishing points stay
    assert form.distance == 6 and form.lblDistanceValue.Caption == "6.0"
    assert vanishing(form) == points
    farther = form.ToPicture(form.Map(form.Ray((1, -1, 1))))
    assert math.dist(farther, middle) < math.dist(corner, middle)
    # Inside the cube: every face seen from inside, all round the eye
    choose(form, 5)
    form.sldDistance.Value = 0
    assert form.Camera() == ("point", pytest.approx((0, 0, 0)))
    parts, inside = form.Faces(form.Camera())
    assert inside == {0} and len(parts[0]) == 6
    pic = form.picView
    for place in vanishing(form)[1, 1] + vanishing(form)[1, -1]:  # ahead and behind
        assert pic.Point(*place) != pic.BackColor
    choose(form, 2)  # (outside, the faces toward the eye only)
    parts, inside = form.Faces(form.Camera())
    assert inside == set() and len(parts[0]) == 3


def test_perspective_lines(perspectives):
    _, module, form = perspectives
    drawn = []
    original = form.Polyline
    form.Polyline = lambda points, color: drawn.append(color)
    form.Draw()
    assert {color for _, color, _ in module.AXES} <= set(drawn)  # the cube's edges, extended
    assert vp6.RGB(200, 200, 210) in drawn  # the horizon
    drawn.clear()
    form.chkLines.Value = vp6.vpUnchecked  # (Click redraws)
    assert drawn == []
    form.Polyline = original
    # The fisheye's rim
    choose(form, 4)
    middle = middle_of(form)
    rim = form.focal * math.pi / 2 * form.Scale()
    angle = math.radians(60)
    x, y = middle[0] + rim * math.cos(angle), middle[1] + rim * math.sin(angle)
    assert any(form.picView.Point(round(x) + dx, round(y) + dy) != form.picView.BackColor
               for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    assert form.picView.Point(x - 20, y - 20) == form.picView.BackColor  # (only the rim)


def test_what_the_mouse_takes_in_perspective(perspectives):
    _, module, form = perspectives
    pic = form.picView
    assert form.HitTest(5, pic.ScaleHeight - 5) == ("space",)
    assert form.HitTest(*middle_of(form)) == ("model",)
    QTest.mouseMove(pic._widget, QPoint(5, pic.ScaleHeight - 5))
    assert pic.MousePointer == vp6.vpDefault
    QTest.mouseMove(pic._widget, QPoint(*map(round, middle_of(form))))
    assert pic.MousePointer == vp6.vpSizeAll
    (y_vp,) = vanishing(form)[1, 1]
    QTest.mouseMove(pic._widget, QPoint(*map(round, y_vp)))
    assert pic.MousePointer == vp6.vpCrosshair


def test_every_model_in_every_perspective(perspectives):
    _, module, form = perspectives
    form.chkRotate.Value = vp6.vpUnchecked
    form.SetAngles(20, 10, 30)
    for index in range(6):
        choose(form, index)
        for i in range(len(module.MODELS)):
            form.optModel[i].Value = True  # (its Click draws it)
            assert form.model is module.model(i)
        form.chkWireframe.Value = vp6.vpChecked
        form.chkWireframe.Value = vp6.vpUnchecked
    form.optModel[4].Value = True  # the boxes turned round: drawn back to front
    choose(form, 2)
    form.SetAngles(0, 0, 0)
    order = form.PartOrder(form.Orientation(), form.Camera(), *form.Faces(form.Camera()))
    assert order.index(0) < order.index(2)  # (the tall blue box in front of the red one)


def test_perspectives_resizing(perspectives):
    _, _, form = perspectives
    form.Width, form.Height = 1400, 760
    QTest.qWait(20)
    assert form.picView.Width == form.ScaleWidth - 312
    assert form.cboPerspective.Left == form.picView.Left + form.picView.Width + 16
    choose(form, 5)
    assert form.Beside()  # (wider than tall: the two halves side by side)
    ahead, behind, _ = form.Centers()
    assert ahead[1] == behind[1] == 0 and ahead[0] < 0 < behind[0]


def test_perspective_geometry():
    module = load_perspectives(os.path.join(os.path.dirname(samples.__file__), "templates",
                                            "perspectives", "Form1.py"))
    square = [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
    half = module.clip(square, (1, 0, 0), 0.0)
    assert sorted(half) == sorted([(0, -1, 1), (1, -1, 1), (1, 1, 1), (0, 1, 1)])
    assert module.clip(square, (0, 0, 1), 2.0) == []
    assert module.clip([(0, 0, -1), (0, 0, 1)], (0, 0, 1), 0.5, closed=False) == \
        [(0, 0, 0.5), (0, 0, 1)]
    assert module.crosses_seam([(1, 0, -1), (-1, 0, -1)], closed=False)
    assert not module.crosses_seam([(1, 0, 1), (-1, 0, 1)], closed=False)  # (in front)
    a, b = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
    assert module.slerp(a, b, 0.5) == pytest.approx((math.sqrt(0.5), math.sqrt(0.5), 0))
    ring = [(0, 0), (10, 0), (10, 10), (5, 3), (0, 10)]  # (not convex)
    assert module.inside((2, 2), ring) and not module.inside((5, 8), ring)
    right, up, forward = module.look(-45, 0)
    assert forward == pytest.approx((-math.sqrt(0.5), math.sqrt(0.5), 0))
    assert up == pytest.approx((0, 0, 1)) and module.dot(right, forward) == pytest.approx(0)
