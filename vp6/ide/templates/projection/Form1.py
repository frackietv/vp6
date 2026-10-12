"""Projection: a model turning in a choice of parallel projections.

A parallel projection moves every point onto the screen along one direction,
so sizes don't shrink with distance. All of them come down to where the three
axes go on the screen: a point (x, y, z) lands at x times X's screen vector,
plus y times Y's, plus z times Z's.

- Orthographic projections look straight at the screen along that direction:
  elevation (from the front: Y is lost), plan (from above: Z is lost),
  isometric (along the cube's diagonal: the three axes 120 degrees apart and
  equally foreshortened), dimetric (two of them equally: here X half as long
  as Y and Z, at 7 and 41 degrees as in technical drawing) and trimetric (all
  three differently).
- Oblique projections keep one plane true and draw the third axis at an angle:
  cavalier (the front plane true, Y receding at 45 degrees, full length),
  military (the plan true, turned 45 degrees, Z straight up) and top-down (the
  plan true and square to the screen, Z up the screen at half length, as in
  many games).

The projection is `Skew` (how the camera's right, up and toward axes are drawn:
right and up as they are, toward not at all for an orthographic one) after
`Camera` (how the world is turned in front of the camera: azimuth and
elevation). Drag an axis's end to move just that axis (the angles between the
axes are no longer right angles; the Skew changes); drag the empty picture to
turn all of them (the Camera); drag the model to turn it (its roll, pitch and
tumble). Double-click the picture or press Reset view to go back to the
projection chosen.

The model is a cube, a pyramid, a torus, a house, a few boxes or a downtown
(`MODELS`): its parts, each a list of flat faces. The axes are drawn first,
behind it. Wireframe shows its edges, otherwise its faces are drawn solid and
shaded: only those facing the viewer, the parts back to front, a part's faces
farthest first. Every part but the torus is convex, so its faces toward the
viewer never hide each other; which of two parts is in front is found by a
face's plane with one on each side of it (`Model.separations`: worked out
once, in the model's own coordinates).

Where OpenGL works, the picture is an OpenGLView (`glView`): OpenGL draws the
axes and the faces with a depth buffer, so each pixel shows what is nearest
(the model hides just the parts of the axes behind it, and the torus needs no
sorting), shaded by the same light (`Scene`, `VERTEX_SHADER`,
`FRAGMENT_SHADER`); the axes' names and the wireframe are drawn over it by the
same graphics methods as on the PictureBox. Without OpenGL (or with OpenGL
unchecked) the PictureBox (`picView`) shows the picture drawn as above."""

import math
from array import array

from vp6 import *

try:  # (the shaders and buffers OpenGL draws with; without them: the PictureBox)
    from PySide6.QtGui import QMatrix4x4, QVector2D, QVector3D, QVector4D
    from PySide6.QtOpenGL import QOpenGLBuffer, QOpenGLShader, QOpenGLShaderProgram
except ImportError:
    QOpenGLShaderProgram = None

AXIS_LENGTH = 2.4  # (the cube is 2 across: from -1 to 1)
AXES = (((1, 0, 0), RGB(230, 76, 60), "X"), ((0, 1, 0), RGB(80, 200, 100), "Y"),
        ((0, 0, 1), RGB(80, 150, 240), "Z"))

ISOMETRIC_ELEVATION = math.degrees(math.asin(1 / math.sqrt(3)))  # about 35.26 degrees
DIMETRIC_AZIMUTH = math.degrees(math.asin(math.sqrt(1 / 8)))  # about 20.7: X half as long
DIMETRIC_ELEVATION = math.degrees(math.asin(1 / 3))  # about 19.47
ORTHOGRAPHIC = (0.0, 0.0)  # (the toward axis isn't drawn)
HALF = math.sqrt(0.5)
# The projections: their name, the camera's azimuth and elevation (degrees), and
# where the camera's toward axis is drawn on the screen (oblique ones only)
PROJECTIONS = (
    ("Elevation (orthographic)", -90.0, 0.0, ORTHOGRAPHIC),
    ("Plan (orthographic)", -90.0, 90.0, ORTHOGRAPHIC),
    ("Isometric (orthographic)", 45.0, ISOMETRIC_ELEVATION, ORTHOGRAPHIC),
    ("Dimetric (orthographic)", DIMETRIC_AZIMUTH, DIMETRIC_ELEVATION, ORTHOGRAPHIC),
    ("Trimetric (orthographic)", 30.0, 20.0, ORTHOGRAPHIC),
    ("Military (oblique)", 45.0, 90.0, (0.0, 1.0)),
    ("Cavalier (oblique)", -90.0, 0.0, (-HALF, -HALF)),
    ("Top-down (oblique)", -90.0, 90.0, (0.0, 0.5)),
)
ISOMETRIC = 2  # the projection shown first

# A box's corners: index = 4 * (x > 0) + 2 * (y > 0) + (z > 0)
CORNERS = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
BOX_FACES = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))
CUBE_COLORS = ((200, 70, 60), (230, 120, 60), (70, 170, 90), (90, 200, 160), (70, 110, 200),
               (140, 120, 220))  # (red, green, blue) for -X, +X, -Y, +Y, -Z, +Z
DRAG_SPEED = 0.01  # radians a pixel
FULL_RATE = 4.0  # degrees a tick at 100%
GRAB = 10  # pixels: how near an axis's end (or its line) the mouse must be
TOLERANCE = 1e-6


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def normalized(v):
    length = math.sqrt(dot(v, v))
    return tuple(c / length for c in v) if length > TOLERANCE else v


def times(m, v):
    """A 3x3 (or 2x3) matrix, as rows, times a vector."""
    return tuple(dot(row, v) for row in m)


def product(a, b):
    """Two matrices, as rows: a times b (b is 3x3)."""
    columns = list(zip(*b))
    return tuple(tuple(dot(row, column) for column in columns) for row in a)


def rotation(axis, angle):
    """Turning by angle (radians) around a unit axis, right-handed."""
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    return ((t * x * x + c, t * x * y - s * z, t * x * z + s * y),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c))


def angles_of(m):
    """Roll (around X), pitch (around Y) and tumble (around Z) in degrees, for
    m = tumble times pitch times roll."""
    pitch = math.asin(max(-1.0, min(1.0, -m[2][0])))
    if abs(m[2][0]) < 1 - 1e-9:
        roll = math.atan2(m[2][1], m[2][2])
        tumble = math.atan2(m[1][0], m[0][0])
    else:  # pitched straight up or down: only the sum of the other two counts
        roll, tumble = 0.0, math.atan2(-m[0][1], m[1][1])
    return tuple(math.degrees(a) for a in (roll, pitch, tumble))


def mean(points):
    return tuple(sum(c) / len(points) for c in zip(*points))


def newell(points):
    """A polygon's normal (its corners' order decides which way)."""
    n = [0.0, 0.0, 0.0]
    for (x1, y1, z1), (x2, y2, z2) in zip(points, points[1:] + points[:1]):
        n[0] += (y1 - y2) * (z1 + z2)
        n[1] += (z1 - z2) * (x1 + x2)
        n[2] += (x1 - x2) * (y1 + y2)
    return normalized(tuple(n))


def wrapped(degrees):
    """An angle from -180 to 180 degrees."""
    return (degrees + 180) % 360 - 180


def screen_angle(a, b):
    """The angle between two screen vectors in degrees (None if one is a point)."""
    la, lb = math.hypot(*a), math.hypot(*b)
    if la < 1e-3 or lb < 1e-3:
        return None
    cos = (a[0] * b[0] + a[1] * b[1]) / (la * lb)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


# --- the models ----------------------------------------------------------------------------
def face(corners, color, inner):
    """A flat face: its corners in order around it, its normal pointing away
    from the point inner, its color (red, green, blue)."""
    corners = [tuple(map(float, c)) for c in corners]
    normal = newell(corners)
    if dot(normal, tuple(a - b for a, b in zip(mean(corners), inner))) < 0:
        normal = tuple(-c for c in normal)
    return tuple(corners), normal, color


def box(low, high, colors):
    """A box's six faces: colors is one color, or six (-X, +X, -Y, +Y, -Z, +Z)."""
    if isinstance(colors[0], int):
        colors = (colors,) * 6
    corners = [tuple(h if c > 0 else lo for c, lo, h in zip(corner, low, high))
               for corner in CORNERS]
    inner = mean(corners)
    return [face([corners[i] for i in indexes], color, inner)
            for indexes, color in zip(BOX_FACES, colors)]


def tower(low, high, apex, color, roof):
    """A box with a pyramid roof up to height apex (convex as a whole)."""
    (x0, y0, z0), (x1, y1, z1) = low, high
    top = ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))
    peak = ((x0 + x1) / 2, (y0 + y1) / 2, apex)
    inner = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    walls = box(low, high, color)[:5]  # (all but the top)
    return walls + [face((top[k], top[(k + 1) % 4], peak), roof, inner) for k in range(4)]


def decal(corners, color, behind):
    """A part that is a single flat face, on a face of another (behind is a
    point inside that one): a door, a window, a street."""
    return [face(corners, color, behind)]


def cube():
    return [box((-1, -1, -1), (1, 1, 1), CUBE_COLORS)]


def pyramid():
    base = ((-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1))
    apex, inner = (0, 0, 1), (0, 0, -0.5)
    sides = ((225, 190, 110), (200, 160, 90), (235, 205, 130), (190, 150, 80))
    return [[face(base, (150, 120, 70), inner)]
            + [face((base[k], base[(k + 1) % 4], apex), sides[k], inner) for k in range(4)]]


TORUS_RADII = (0.7, 0.32)  # the ring's and the tube's
TORUS_STEPS = (20, 10)  # around the ring, around the tube


def torus():
    """A ring of quads (each flat: an isosceles trapezoid), its normals away
    from the tube's center line, checkered."""
    (big, small), (steps, around) = TORUS_RADII, TORUS_STEPS

    def point(i, j):
        u, v = 2 * math.pi * i / steps, 2 * math.pi * j / around
        r = big + small * math.cos(v)
        return r * math.cos(u), r * math.sin(u), small * math.sin(v)

    faces = []
    for i in range(steps):
        u = 2 * math.pi * (i + 0.5) / steps
        center = (big * math.cos(u), big * math.sin(u), 0.0)
        for j in range(around):
            color = (230, 150, 70) if (i + j) % 2 else (200, 90, 120)
            faces.append(face((point(i, j), point(i + 1, j), point(i + 1, j + 1),
                               point(i, j + 1)), color, center))
    return [faces]


def house():
    """Walls under a gable roof (convex as a whole), a door and three windows."""
    x, y, eaves, ridge = 1.0, 0.7, 0.2, 0.9
    inner = (0, 0, -0.4)
    wall, gable, roof = (230, 215, 185), (215, 195, 165), (170, 70, 55)
    walls = [face(((-x, s * y, -1), (x, s * y, -1), (x, s * y, eaves), (-x, s * y, eaves)),
                  wall, inner) for s in (-1, 1)]
    gables = [face(((s * x, -y, -1), (s * x, y, -1), (s * x, y, eaves), (s * x, 0, ridge),
                    (s * x, -y, eaves)), gable, inner) for s in (-1, 1)]
    slopes = [face(((-x, s * y, eaves), (x, s * y, eaves), (x, 0, ridge), (-x, 0, ridge)),
                   roof, inner) for s in (-1, 1)]
    floor = face(((-x, -y, -1), (x, -y, -1), (x, y, -1), (-x, y, -1)), (120, 100, 80), inner)
    front, side = y + 0.01, x + 0.01  # (just outside the walls)
    door, glass = (110, 70, 45), (120, 180, 230)

    def opening(x0, z0, x1, z1, color):  # on the front (+Y) wall
        return decal(((x0, front, z0), (x1, front, z0), (x1, front, z1), (x0, front, z1)),
                     color, inner)

    return [walls + gables + slopes + [floor],
            opening(-0.2, -1, 0.15, -0.35, door), opening(-0.8, -0.55, -0.45, -0.15, glass),
            opening(0.4, -0.55, 0.75, -0.15, glass),
            decal(((side, -0.2, -0.05), (side, 0.2, -0.05), (side, 0.2, 0.35),
                   (side, -0.2, 0.35)), glass, inner)]  # in the gable


def boxes():
    """Boxes of different sizes, apart: five on the floor, one in the air."""
    return [box((-1.0, -1.0, -1.0), (-0.2, -0.2, 0.0), (210, 80, 70)),
            box((0.1, -1.0, -1.0), (1.0, -0.5, -0.6), (90, 190, 110)),
            box((0.3, -0.2, -1.0), (0.8, 0.3, 0.7), (80, 140, 230)),
            box((-0.9, 0.3, -1.0), (-0.2, 1.0, -0.5), (235, 200, 80)),
            box((0.2, 0.6, -1.0), (1.0, 1.0, -0.2), (160, 110, 210)),
            box((-0.4, 0.0, 0.4), (0.0, 0.4, 0.8), (90, 200, 200))]


def downtown():
    """A ground slab, two streets crossing, office blocks, a tower with a
    spire and a park with trees."""
    ground = (-1.2, -1.2, -1.1), (1.2, 1.2, -1.0)
    under = (0, 0, -1.05)  # (inside the ground)
    street, park = (70, 70, 80), (90, 160, 80)

    def flat(x0, y0, x1, y1, color):
        return decal(((x0, y0, -1), (x1, y0, -1), (x1, y1, -1), (x0, y1, -1)), color, under)

    def block(x0, y0, x1, y1, height, color):
        return box((x0, y0, -1.0), (x1, y1, height), color)

    def tree(x, y):
        r = 0.09
        base = ((x - r, y - r, -1), (x + r, y - r, -1), (x + r, y + r, -1), (x - r, y + r, -1))
        inner, top = (x, y, -0.95), (x, y, -0.7)
        return [face(base, (60, 110, 50), inner)] + [
            face((base[k], base[(k + 1) % 4], top), (50, 140, 60), inner) for k in range(4)]

    return [box(*ground, (150, 150, 145)),
            flat(-1.2, -0.15, 1.2, 0.15, street),  # along X
            flat(-0.15, 0.15, 0.15, 1.2, street), flat(-0.15, -1.2, 0.15, -0.15, street),
            tower((0.3, 0.3, -1.0), (0.7, 0.7, 0.6), 1.1, (90, 130, 190), (60, 90, 140)),
            block(0.8, 0.3, 1.1, 0.6, -0.5, (200, 170, 140)),
            block(0.3, 0.8, 1.1, 1.1, -0.3, (180, 120, 100)),
            block(-1.1, 0.3, -0.6, 0.7, 0.2, (170, 180, 200)),
            block(-0.5, 0.3, -0.3, 1.1, -0.6, (210, 190, 120)),
            block(-1.1, 0.8, -0.6, 1.1, -0.4, (140, 150, 170)),
            block(-1.1, -1.1, -0.55, -0.3, 0.4, (120, 140, 160)),
            block(-0.45, -1.1, -0.3, -0.3, -0.5, (200, 140, 110)),
            flat(0.3, -1.1, 1.1, -0.3, park),
            tree(0.5, -0.5), tree(0.85, -0.6), tree(0.6, -0.9), tree(0.95, -0.95)]


class Model:
    """A model to draw: its parts (each a list of faces), its corners and
    edges for the wireframe, and which side of which the parts are."""

    def __init__(self, name, parts, convex=True):
        self.name = name
        self.parts = parts
        self.convex = convex  # (every part; otherwise its faces are drawn farthest first)
        self.points = list(dict.fromkeys(c for part in parts for f in part for c in f[0]))
        edges = {}
        for part in parts:
            for corners, _, _ in part:
                for a, b in zip(corners, corners[1:] + corners[:1]):
                    edges.setdefault(frozenset((a, b)), (a, b))
        self.edges = list(edges.values())
        self.centers = [mean([c for f in part for c in f[0]]) for part in parts]
        self.separations = {}  # (a, b): a direction from part a's side to part b's
        if convex:
            for a in range(len(parts)):
                for b in range(a + 1, len(parts)):
                    normal = self.Separation(parts[a], parts[b])
                    if normal is not None:
                        self.separations[a, b] = normal

    @staticmethod
    def Separation(first, second):
        """A face's plane with one convex part inside and the other outside
        (or on it), as its normal from the first part toward the second; None
        when no face's plane parts them."""
        for faces, others, sign in ((first, second, 1), (second, first, -1)):
            points = [c for f in others for c in f[0]]
            for corners, normal, _ in faces:
                origin = corners[0]
                if all(dot(tuple(p - o for p, o in zip(point, origin)), normal) >= -TOLERANCE
                       for point in points):
                    return tuple(sign * c for c in normal)
        return None


MODELS = (("&Cube", cube), ("P&yramid", pyramid), ("&Torus", torus), ("&House", house),
          ("&Boxes", boxes), ("&Downtown", downtown))
NONCONVEX = {"&Torus"}
_built = {}


def model(index):
    """One of MODELS, made the first time it's asked for."""
    if index not in _built:
        caption, make = MODELS[index]
        _built[index] = Model(caption.replace("&", ""), make(), caption not in NONCONVEX)
    return _built[index]


# --- OpenGL ----------------------------------------------------------------------------------
# OpenGL's numbers (Qt's OpenGL functions take them as they are)
GL_LINES, GL_TRIANGLES = 0x0001, 0x0004
GL_DEPTH_BUFFER_BIT, GL_COLOR_BUFFER_BIT = 0x0100, 0x4000
GL_DEPTH_TEST, GL_LEQUAL, GL_POLYGON_OFFSET_FILL, GL_FLOAT = 0x0B71, 0x0203, 0x8037, 0x1406
DEPTH = 4.0  # how far in front of and behind the center the depth buffer reaches

# The shaders: OpenGL's own language (GLSL 1.10, which OpenGL ES 2 takes too). A
# vertex's position goes through the model's turn (turn: none for the axes) and the
# projection (view); a line's other end gives its direction on the picture, along
# which dash makes it dotted (on, period: OpenGL's pixels; period 0: solid). A face
# is shaded as in DrawSolid; facing away from the eye, it is hidden (unless its part
# is closed: then the eye is inside it, and it is seen from inside).
VERTEX_SHADER = """
attribute vec4 position;
attribute vec4 other;
attribute vec3 normal;
attribute vec3 color;
attribute float closed;
uniform mat4 view;
uniform mat4 turn;
uniform vec2 pixels;
varying vec3 v_world;
varying vec3 v_normal;
varying vec3 v_color;
varying float v_closed;
varying vec2 v_along;
void main() {
    vec4 world = turn * position;
    vec4 here = view * world;
    vec4 there = view * (turn * other);
    vec2 along = (there.xy * here.w - here.xy * there.w) * pixels;
    if (along.x < 0.0 || (along.x == 0.0 && along.y < 0.0)) along = -along;
    v_along = length(along) > 0.0 ? normalize(along) : vec2(1.0, 0.0);
    v_world = world.xyz;
    v_normal = (turn * vec4(normal, 0.0)).xyz;
    v_color = color;
    v_closed = closed;
    gl_Position = here;
}
"""
FRAGMENT_SHADER = """
#ifdef GL_ES
precision highp float;
#endif
uniform vec4 eye;
uniform vec3 light;
uniform float lit;
uniform vec2 dash;
varying vec3 v_world;
varying vec3 v_normal;
varying vec3 v_color;
varying float v_closed;
varying vec2 v_along;
void main() {
    vec3 color = v_color;
    if (lit > 0.5) {
        vec3 n = normalize(v_normal);
        if (dot(n, eye.xyz - eye.w * v_world) <= 0.0) {
            if (v_closed < 0.5) discard;
            n = -n;
        }
        color *= 0.35 + 0.65 * max(0.0, dot(n, light));
    }
    if (dash.y > 0.0 && mod(dot(gl_FragCoord.xy, v_along), dash.y) >= dash.x) discard;
    gl_FragColor = vec4(color, 1.0);
}
"""
# A vertex in a buffer: its position (x, y, z, w: 0 for a direction), a line's
# other end, its normal, its color and whether its part is closed: (name, floats)
ATTRIBUTES = (("position", 4), ("other", 4), ("normal", 3), ("color", 3), ("closed", 1))
FLOATS = sum(size for _, size in ATTRIBUTES)


def vertex(position, other=None, normal=(0.0, 0.0, 0.0), color=(1.0, 1.0, 1.0), closed=0.0):
    """A vertex's floats: a point is (x, y, z), or (x, y, z, w)."""
    position = tuple(position) + (1.0,) * (4 - len(position))
    other = position if other is None else tuple(other) + (1.0,) * (4 - len(other))
    return (*position, *other, *normal, *color, float(closed))


def rgb(color):
    """A color (RGB()) as OpenGL's red, green and blue, from 0 to 1."""
    return (color & 0xFF) / 255, (color >> 8 & 0xFF) / 255, (color >> 16 & 0xFF) / 255


def matrix(rows):
    """A 4x4 matrix (rows) for OpenGL; a 3x3 one is a turn."""
    if len(rows) == 3:
        rows = [tuple(row) + (0.0,) for row in rows] + [(0.0, 0.0, 0.0, 1.0)]
    return QMatrix4x4(*[float(v) for row in rows for v in row])


def model_vertices(model):
    """A model's pieces for OpenGL: its faces as triangles (fans), those of
    parts that are a single face (decals: on another part's face) apart, and
    its edges as lines."""
    triangles, decals, lines = [], [], []
    for part in model.parts:
        closed = model.convex and len(part) >= 4  # (a solid: the eye can be inside it)
        into = decals if len(part) == 1 else triangles
        for corners, normal, color in part:
            color = tuple(c / 255 for c in color)
            for k in range(1, len(corners) - 1):
                into += [vertex(c, normal=normal, color=color, closed=closed)
                              for c in (corners[0], corners[k], corners[k + 1])]
    outline = rgb(RGB(20, 20, 30))
    for a, b in model.edges:
        lines += [vertex(a, b, color=outline), vertex(b, a, color=outline)]
    return [("faces", triangles), ("decals", decals), ("edges", lines)]


def axis_vertices():
    """The axes for OpenGL: each one's negative half (back) and positive half (front)."""
    pieces = []
    for i, (axis, color, _) in enumerate(AXES):
        end = tuple(AXIS_LENGTH * a for a in axis)
        back, color = tuple(-c for c in end), rgb(color)
        pieces += [(f"back {i}", [vertex(back, (0, 0, 0), color=color),
                                  vertex((0, 0, 0), back, color=color)]),
                   (f"front {i}", [vertex((0, 0, 0), end, color=color),
                                   vertex(end, (0, 0, 0), color=color)])]
    return pieces


class Scene:
    """What OpenGL draws with, made in InitializeGL (its context current): the
    shader program, and buffers of vertices made the first time they're drawn
    (their pieces: name -> (first vertex, count))."""

    def __init__(self):
        program = QOpenGLShaderProgram()
        if not (program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER)
                and program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT_SHADER)
                and program.link()):
            raise RuntimeError(program.log())
        self.program = program
        self.buffers = {}

    def Buffer(self, key, make):
        """The buffer called key, made from make()'s pieces: [(name, vertices)]."""
        if key not in self.buffers:
            data, pieces = array("f"), {}
            for name, vertices in make():
                pieces[name] = (len(data) // FLOATS, len(vertices))
                for v in vertices:
                    data.extend(v)
            buffer = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer)
            buffer.create()
            buffer.bind()
            buffer.allocate(data.tobytes(), len(data) * data.itemsize)
            buffer.release()
            self.buffers[key] = buffer, pieces
        return self.buffers[key]

    def Begin(self, view, pixels, eye, light):
        """The program with what every piece shares: the projection (rows), the
        picture's size (OpenGL's pixels), the eye (x, y, z, w: 0 for the way
        toward it) and the light."""
        program = self.program
        program.bind()
        program.setUniformValue("view", matrix(view))
        program.setUniformValue("pixels", QVector2D(*pixels))
        program.setUniformValue("eye", QVector4D(*eye))
        program.setUniformValue("light", QVector3D(*light))

    def Draw(self, gl, key, make, names, mode, turn=None, lit=False, width=1.0,
             dash=(0.0, 0.0)):
        """Pieces of a buffer: triangles (lit: shaded) or lines (width, dash)."""
        buffer, pieces = self.Buffer(key, make)
        program = self.program
        program.setUniformValue("turn", matrix(turn or ((1, 0, 0), (0, 1, 0), (0, 0, 1))))
        program.setUniformValue1f("lit", 1.0 if lit else 0.0)
        program.setUniformValue("dash", QVector2D(*dash))
        gl.glLineWidth(width)
        buffer.bind()
        offset = 0
        for name, size in ATTRIBUTES:
            program.enableAttributeArray(name)
            program.setAttributeBuffer(name, GL_FLOAT, offset * 4, size, FLOATS * 4)
            offset += size
        for name in names:
            first, count = pieces[name]
            gl.glDrawArrays(mode, first, count)
        for name, _ in ATTRIBUTES:
            program.disableAttributeArray(name)
        buffer.release()

    def End(self):
        self.program.release()  # (the graphics methods draw next)

    def Destroy(self):
        for buffer, _ in self.buffers.values():
            buffer.destroy()
        self.buffers.clear()
        self.program.removeAllShaders()


class Form1(Form):
    # region VP6 Designer - generated by the form designer, do not edit
    def InitializeComponent(self):
        self.Caption = 'Projection'
        self.Width = 900
        self.Height = 780
        self.picView = PictureBox(self, Left=12, Top=12, Width=588, Height=720, AutoRedraw=True,
                                  BackColor=0x302420, ForeColor=0xE0E0E0, TabIndex=1,
                                  ToolTipText="Drag an axis's end to move it, the model to turn it, the space around them to turn the axes; double-click: the projection again")
        self.glView = OpenGLView(self, Left=12, Top=12, Width=588, Height=720, Samples=4,
                                 Visible=False, TabIndex=2,
                                 ToolTipText="Drag an axis's end to move it, the model to turn it, the space around them to turn the axes; double-click: the projection again")
        self.lblProjection = Label(self, Caption='&Projection:', Left=616, Top=12, Width=268,
                                   Height=20, TabIndex=3)
        self.cboProjection = ComboBox(self, Style=2, Left=616, Top=34, Width=268, Height=25,
                                      List=['Elevation (orthographic)', 'Plan (orthographic)', 'Isometric (orthographic)', 'Dimetric (orthographic)', 'Trimetric (orthographic)', 'Military (oblique)', 'Cavalier (oblique)', 'Top-down (oblique)'],
                                      TabIndex=4,
                                      ToolTipText='The parallel projection to draw with')
        self.cmdReset = CommandButton(self, Caption='&Reset view', Left=616, Top=68, Width=176,
                                      Height=30, TabIndex=5,
                                      ToolTipText='The projection chosen again, its axes where they belong')
        self.chkOpenGL = CheckBox(self, Caption='Open&GL', Left=800, Top=71, Width=84, Height=24,
                                  Value=1, TabIndex=6,
                                  ToolTipText="Draw the axes and the model with OpenGL (each pixel the nearest, by a depth buffer), or with the PictureBox's graphics methods; off where there is no OpenGL")
        self.chkWireframe = CheckBox(self, Caption='&Wireframe', Left=616, Top=106, Width=130,
                                     Height=24, TabIndex=7,
                                     ToolTipText="The model's edges, or its faces solid and shaded")
        self.chkRotate = CheckBox(self, Caption='R&otate', Left=754, Top=106, Width=130, Height=24,
                                  Value=1, TabIndex=8,
                                  ToolTipText='Turn the model at the rates below')
        self.lblModel = Label(self, Caption='Model', Left=616, Top=142, Width=268, Height=20,
                              FontBold=True, TabIndex=9)
        self.optModel = ControlArray()
        self.optModel[0] = OptionButton(self, Caption='&Cube', Left=616, Top=164, Width=88,
                                        Height=24, Value=True, TabIndex=10,
                                        ToolTipText='The model to draw')
        self.optModel[1] = OptionButton(self, Caption='P&yramid', Left=706, Top=164, Width=88,
                                        Height=24, TabIndex=11, ToolTipText='The model to draw')
        self.optModel[2] = OptionButton(self, Caption='&Torus', Left=796, Top=164, Width=88,
                                        Height=24, TabIndex=12, ToolTipText='The model to draw')
        self.optModel[3] = OptionButton(self, Caption='&House', Left=616, Top=190, Width=88,
                                        Height=24, TabIndex=13, ToolTipText='The model to draw')
        self.optModel[4] = OptionButton(self, Caption='&Boxes', Left=706, Top=190, Width=88,
                                        Height=24, TabIndex=14, ToolTipText='The model to draw')
        self.optModel[5] = OptionButton(self, Caption='&Downtown', Left=796, Top=190, Width=88,
                                        Height=24, TabIndex=15, ToolTipText='The model to draw')
        self.lblTurns = Label(self, Caption="The model's turn (degrees)", Left=616, Top=222,
                              Width=268, Height=20, FontBold=True, TabIndex=16)
        self.lblRoll = Label(self, Caption='Roll (X)', Left=616, Top=250, Width=76, Height=20,
                             TabIndex=17)
        self.sldRoll = Slider(self, Left=692, Top=244, Width=146, Height=30, Min=-180, Max=180,
                              LargeChange=15, TickStyle=3, TabIndex=18,
                              ToolTipText="The model's turn around X")
        self.lblRollValue = Label(self, Caption='0°', Left=840, Top=250, Width=44, Height=20,
                                  Alignment=1, TabIndex=19)
        self.lblPitch = Label(self, Caption='Pitch (Y)', Left=616, Top=284, Width=76, Height=20,
                              TabIndex=20)
        self.sldPitch = Slider(self, Left=692, Top=278, Width=146, Height=30, Min=-180, Max=180,
                               LargeChange=15, TickStyle=3, TabIndex=21,
                               ToolTipText="The model's turn around Y")
        self.lblPitchValue = Label(self, Caption='0°', Left=840, Top=284, Width=44, Height=20,
                                   Alignment=1, TabIndex=22)
        self.lblTumble = Label(self, Caption='Tumble (Z)', Left=616, Top=318, Width=76, Height=20,
                               TabIndex=23)
        self.sldTumble = Slider(self, Left=692, Top=312, Width=146, Height=30, Min=-180, Max=180,
                                LargeChange=15, TickStyle=3, TabIndex=24,
                                ToolTipText="The model's turn around Z")
        self.lblTumbleValue = Label(self, Caption='0°', Left=840, Top=318, Width=44, Height=20,
                                    Alignment=1, TabIndex=25)
        self.lblRates = Label(self, Caption='Rates (of full speed)', Left=616, Top=356, Width=268,
                              Height=20, FontBold=True, TabIndex=26)
        self.lblRollRate = Label(self, Caption='Roll', Left=616, Top=384, Width=76, Height=20,
                                 TabIndex=27)
        self.sldRollRate = Slider(self, Left=692, Top=378, Width=146, Height=30, Max=100, Value=15,
                                  LargeChange=10, TickStyle=3, TabIndex=28,
                                  ToolTipText='How fast Rotate rolls the model')
        self.lblRollRateValue = Label(self, Caption='15%', Left=840, Top=384, Width=44, Height=20,
                                      Alignment=1, TabIndex=29)
        self.lblPitchRate = Label(self, Caption='Pitch', Left=616, Top=418, Width=76, Height=20,
                                  TabIndex=30)
        self.sldPitchRate = Slider(self, Left=692, Top=412, Width=146, Height=30, Max=100,
                                   Value=10, LargeChange=10, TickStyle=3, TabIndex=31,
                                   ToolTipText='How fast Rotate pitches the model')
        self.lblPitchRateValue = Label(self, Caption='10%', Left=840, Top=418, Width=44, Height=20,
                                       Alignment=1, TabIndex=32)
        self.lblTumbleRate = Label(self, Caption='Tumble', Left=616, Top=452, Width=76, Height=20,
                                   TabIndex=33)
        self.sldTumbleRate = Slider(self, Left=692, Top=446, Width=146, Height=30, Max=100,
                                    Value=40, LargeChange=10, TickStyle=3, TabIndex=34,
                                    ToolTipText='How fast Rotate tumbles the model')
        self.lblTumbleRateValue = Label(self, Caption='40%', Left=840, Top=452, Width=44,
                                        Height=20, Alignment=1, TabIndex=35)
        self.lblAxes = Label(self, Caption='Angles between the axes', Left=616, Top=490, Width=268,
                             Height=20, FontBold=True, TabIndex=36)
        self.lblAngles = Label(self, Caption='', Left=616, Top=512, Width=268, Height=64,
                               TabIndex=37)
        self.lblView = Label(self, Caption='', Left=616, Top=584, Width=268, Height=148,
                             WordWrap=True, TabIndex=38)
        self.tmrSpin = Timer(self, Left=616, Top=700, Interval=30)
    # endregion

    def Form_Load(self):
        self.roll = self.pitch = self.tumble = 0.0  # the model's turns (degrees)
        self.drag = None  # what the mouse is dragging: ("axis", i), ("model",), ("space",)
        self.model = model(0)
        self.syncing = False  # (the sliders being set from the angles: no Change)
        self.opengl = False  # (drawing with OpenGL: see UseOpenGL)
        self.scene = None  # what OpenGL draws with (made in glView_InitializeGL)
        self.SetProjection(ISOMETRIC)
        self.cboProjection.ListIndex = ISOMETRIC  # (its Click sets it again)
        self.ShowAngles()
        # OpenGL where it works: otherwise the PictureBox, and no choice
        available = self.glView.Available and QOpenGLShaderProgram is not None
        self.chkOpenGL.Enabled = available
        self.chkOpenGL.Value = vpChecked if available else vpUnchecked
        self.UseOpenGL(available)

    def Form_Resize(self):
        # The picture takes what the controls on the right leave
        for pic in (self.picView, self.glView):
            pic.Width = max(120, self.ScaleWidth - 312)
            pic.Height = max(120, self.ScaleHeight - 24)
        pic = self.picView
        shift = pic.Left + pic.Width + 16 - self.cboProjection.Left
        for control in self.PanelControls():
            control.Left += shift
        self.Draw()

    def Form_Unload(self):
        if self.scene is not None:  # (its buffers and shaders go with OpenGL's context)
            self.glView.MakeCurrent()
            self.scene.Destroy()
            self.scene = None

    def PanelControls(self):
        return [c for c in self.Controls
                if c is not self.picView and c is not self.glView and not isinstance(c, Timer)]

    # --- the surface: OpenGL or the PictureBox ---------------------------------------------
    def UseOpenGL(self, on):
        """Draw with OpenGL, on the OpenGLView, or with the graphics methods, on
        the PictureBox (where OpenGL doesn't work, always)."""
        self.opengl = bool(on) and self.glView.Available
        self.glView.Visible = self.opengl
        self.picView.Visible = not self.opengl
        self.Draw()

    def Surface(self):
        """What the picture is drawn on (the same size either way)."""
        return self.glView if self.opengl else self.picView

    # --- the projection --------------------------------------------------------------------
    def SetProjection(self, index):
        """One of PROJECTIONS, its axes where they belong."""
        _, azimuth, elevation, (a, b) = PROJECTIONS[index]
        self.kind = index
        self.azimuth, self.elevation = azimuth, elevation
        self.skew = ((1.0, 0.0, a), (0.0, 1.0, b))
        self.Draw()

    def Camera(self):
        """The camera's right, up and toward axes in the world (the rows of the
        turn that brings the world in front of it)."""
        a, e = math.radians(self.azimuth), math.radians(self.elevation)
        toward = (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))
        right = (-math.sin(a), math.cos(a), 0.0)
        up = (-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e))
        return right, up, toward

    def Projection(self):
        """The world to the screen (x right, y up): two rows, the skew after
        the camera. Its columns are the axes' screen vectors."""
        return product(self.skew, self.Camera())

    def AxisVector(self, i, projection=None):
        """Where a unit along axis i goes on the screen (x right, y up)."""
        rows = projection or self.Projection()
        return rows[0][i], rows[1][i]

    def Toward(self, projection=None):
        """The direction the projection looks along, toward the viewer (None
        when the axes are all on one line, and it can't tell)."""
        rows = projection or self.Projection()
        toward = cross(rows[0], rows[1])  # (every point along it lands on the same place)
        return normalized(toward) if dot(toward, toward) > TOLERANCE else None

    def Scale(self):
        pic = self.Surface()
        return min(pic.ScaleWidth, pic.ScaleHeight) / (2.4 * AXIS_LENGTH)

    def Project(self, point, projection=None):
        """A point's place on the picture: x times X's screen vector, plus y
        times Y's, plus z times Z's (how far it is along the view is lost)."""
        sx, sy = times(projection or self.Projection(), point)
        pic, size = self.Surface(), self.Scale()
        return pic.ScaleWidth / 2 + size * sx, pic.ScaleHeight / 2 - size * sy

    def AxisAngles(self):
        """The angles on the screen between X and Y, Y and Z, Z and X."""
        vectors = [self.AxisVector(i) for i in range(3)]
        return tuple(screen_angle(vectors[a], vectors[b]) for a, b in ((0, 1), (1, 2), (2, 0)))

    def Describe(self):
        """What the projection is now: one of PROJECTIONS, or what kind of
        orthographic one, or a general parallel one."""
        projection = self.Projection()
        for name, azimuth, elevation, (a, b) in PROJECTIONS:
            if self.SameAs(projection, azimuth, elevation, (a, b)):
                return name
        (r0, r1) = projection
        if (abs(dot(r0, r0) - 1) < 1e-6 and abs(dot(r1, r1) - 1) < 1e-6
                and abs(dot(r0, r1)) < 1e-6):
            lengths = [round(math.hypot(*self.AxisVector(i, projection)), 3) for i in range(3)]
            if 0 in lengths:
                return "Plan (orthographic)" if lengths[2] == 0 else "Elevation (orthographic)"
            kind = {1: "Isometric", 2: "Dimetric", 3: "Trimetric"}[len(set(lengths))]
            return f"{kind} (orthographic)"
        return "A general parallel projection (oblique)"

    def SameAs(self, projection, azimuth, elevation, receding):
        a, b = receding
        saved = self.azimuth, self.elevation, self.skew
        self.azimuth, self.elevation, self.skew = azimuth, elevation, ((1.0, 0.0, a),
                                                                        (0.0, 1.0, b))
        try:
            other = self.Projection()
        finally:
            self.azimuth, self.elevation, self.skew = saved
        return all(abs(p - q) < 1e-6 for row, other_row in zip(projection, other)
                   for p, q in zip(row, other_row))

    # --- the model -------------------------------------------------------------------------
    def SetModel(self, index):
        """One of MODELS to draw, turned as the last one was."""
        self.model = model(index)
        self.Draw()

    def Orientation(self):
        """The model's turn: roll around X, then pitch around Y, then tumble around Z."""
        m = rotation((1, 0, 0), math.radians(self.roll))
        m = product(rotation((0, 1, 0), math.radians(self.pitch)), m)
        return product(rotation((0, 0, 1), math.radians(self.tumble)), m)

    def Turned(self, point, orientation=None):
        return times(orientation or self.Orientation(), point)

    def SetAngles(self, roll, pitch, tumble):
        self.roll, self.pitch, self.tumble = wrapped(roll), wrapped(pitch), wrapped(tumble)
        self.ShowAngles()
        self.Draw()

    def ShowAngles(self):
        """The sliders and their labels from the angles and rates."""
        self.syncing = True
        try:
            for slider, label, value in ((self.sldRoll, self.lblRollValue, self.roll),
                                         (self.sldPitch, self.lblPitchValue, self.pitch),
                                         (self.sldTumble, self.lblTumbleValue, self.tumble)):
                slider.Value = round(value)
                label.Caption = f"{round(value)}°"
        finally:
            self.syncing = False
        for slider, label in ((self.sldRollRate, self.lblRollRateValue),
                              (self.sldPitchRate, self.lblPitchRateValue),
                              (self.sldTumbleRate, self.lblTumbleRateValue)):
            label.Caption = f"{slider.Value}%"

    def AnglesSlid(self):
        if not self.syncing:
            self.SetAngles(self.sldRoll.Value, self.sldPitch.Value, self.sldTumble.Value)

    # --- drawing ---------------------------------------------------------------------------
    def Draw(self):
        if not hasattr(self, "skew"):  # (a Resize before Form_Load)
            return
        projection = self.Projection()
        if self.opengl:
            self.glView.Update()  # (glView_Paint draws it)
        else:
            self.picView.Cls()
            self.DrawAxes(projection)
            if self.Solid(projection):
                self.DrawSolid(projection)
            else:
                self.DrawWireframe(projection)
        angles = self.AxisAngles()
        self.lblAngles.Caption = "\n".join(
            f"{pair}:  " + ("—" if angle is None else f"{angle:.1f}°")
            for pair, angle in zip(("X–Y", "Y–Z", "Z–X"), angles))
        lengths = ", ".join(f"{name} {math.hypot(*self.AxisVector(i, projection)):.2f}"
                            for i, (_, _, name) in enumerate(AXES))
        self.lblView.Caption = (
            f"{self.Describe()}\n"
            f"Azimuth {self.azimuth % 360:.1f}°, elevation {self.elevation:.1f}°\n"
            f"Axis lengths: {lengths}\n\n"
            "Drag an axis's end to move it, the model to turn it, the space around them to "
            "turn the axes; double-click for the projection again.")

    def Solid(self, projection):
        """Whether the model is drawn solid (not as a wireframe, and the
        projection tells near from far)."""
        return self.chkWireframe.Value != vpChecked and self.Toward(projection) is not None

    def Light(self, projection):
        """Where the light comes from: above the viewer's left shoulder."""
        toward = self.Toward(projection)
        right, up = normalized(projection[0]), normalized(projection[1])
        return normalized(tuple(0.75 * t + 0.55 * u - 0.35 * r
                                for r, u, t in zip(right, up, toward)))

    def DrawAxes(self, projection, lines=True):
        """The axes through the model's center: the negative halves dotted, then
        the positive ones with their names (the one being dragged thicker);
        just the names over the axes OpenGL drew (lines False)."""
        pic = self.Surface()
        origin = self.Project((0, 0, 0), projection)
        for i, (axis, color, name) in enumerate(AXES):
            end = self.Project(tuple(AXIS_LENGTH * a for a in axis), projection)
            back = self.Project(tuple(-AXIS_LENGTH * a for a in axis), projection)
            if lines:
                pic.DrawWidth, pic.DrawStyle = 1, vpDot
                pic.Line(back[0], back[1], origin[0], origin[1], color)
                pic.DrawWidth, pic.DrawStyle = (4 if self.drag == ("axis", i) else 2), vpSolid
                pic.Line(origin[0], origin[1], end[0], end[1], color)
            label = self.LabelPlace(i, projection)
            pic.CurrentX = label[0] - pic.TextWidth(name) / 2
            pic.CurrentY = label[1] - pic.TextHeight(name) / 2
            pic.ForeColor = color
            pic.Print(name)
        pic.DrawWidth = 1

    def LabelPlace(self, i, projection=None):
        return self.Project(tuple((AXIS_LENGTH + 0.25) * a for a in AXES[i][0]), projection)

    def DrawWireframe(self, projection):
        """The model's edges, its corners dotted."""
        pic = self.Surface()
        orientation = self.Orientation()
        place = {point: self.Project(self.Turned(point, orientation), projection)
                 for point in self.model.points}
        pic.DrawWidth = 2 if len(place) <= 40 else 1
        for a, b in self.model.edges:
            pic.Line(*place[a], *place[b], RGB(240, 240, 240))
        pic.FillStyle, pic.FillColor = vpFSSolid, RGB(255, 210, 80)
        pic.DrawWidth = 1
        radius = 3 if len(place) <= 40 else 2
        for x, y in place.values():
            pic.Circle(x, y, radius, RGB(255, 210, 80))
        pic.FillStyle = vpFSTransparent

    def DrawSolid(self, projection):
        """The faces toward the viewer, the parts back to front (a part's own
        faces farthest first), lit from above the viewer's left shoulder."""
        pic = self.Surface()
        toward, light = self.Toward(projection), self.Light(projection)
        orientation = self.Orientation()
        place = {point: self.Project(self.Turned(point, orientation), projection)
                 for point in self.model.points}
        parts = []
        for part in self.model.parts:
            faces = []
            for corners, normal, (red, green, blue) in part:
                normal = self.Turned(normal, orientation)
                if dot(normal, toward) <= 0:  # facing away: hidden
                    continue
                depth = sum(dot(self.Turned(c, orientation), toward) for c in corners)
                shade = 0.35 + 0.65 * max(0.0, dot(normal, light))
                faces.append((depth / len(corners), [place[c] for c in corners],
                              RGB(int(red * shade), int(green * shade), int(blue * shade))))
            parts.append(sorted(faces, key=lambda f: f[0]))
        pic.FillStyle, pic.DrawWidth = vpFSSolid, 1
        outline = RGB(20, 20, 30)
        for index in self.PartOrder(orientation, toward, parts):
            for _, corners, color in parts[index]:
                pic.FillColor = color
                pic.Polygon(corners, outline)
        pic.FillStyle = vpFSTransparent

    def PartOrder(self, orientation, toward, parts):
        """The parts with faces to draw (parts: each one's faces toward the
        viewer, their corners on the picture), in the order to draw them: of
        two whose pictures overlap, the one on the far side of the plane
        between them first; otherwise (and for what that leaves open) the
        farthest first."""
        model = self.model
        depths = [dot(self.Turned(c, orientation), toward) for c in model.centers]
        outlines = {index: hull([c for _, corners, _ in faces for c in corners])
                    for index, faces in enumerate(parts) if faces}
        before = {index: set() for index in outlines}  # before[b]: the parts to draw before b
        for (a, b), normal in model.separations.items():
            if a not in outlines or b not in outlines:
                continue  # (nothing of it to draw)
            if not overlap(outlines[a], outlines[b]):
                continue  # (apart on the picture: either order)
            side = dot(self.Turned(normal, orientation), toward)
            if side > TOLERANCE:  # the viewer on b's side: a is behind
                before[b].add(a)
            elif side < -TOLERANCE:
                before[a].add(b)
        left = sorted(outlines, key=lambda i: depths[i])
        order = []
        while left:
            waiting = set(left)
            index = next((i for i in left if not before[i] & waiting), left[0])
            left.remove(index)
            order.append(index)
        return order

    # --- drawing with OpenGL ----------------------------------------------------------------
    def glView_InitializeGL(self):
        """OpenGL is ready: the shaders (if they can't be made, the PictureBox
        draws, and says why in its tooltip)."""
        try:
            self.scene = Scene()
        except RuntimeError as error:
            self.scene = None
            self.chkOpenGL.ToolTipText = f"OpenGL's shaders didn't compile: {error}"
            self.chkOpenGL.Value = vpUnchecked  # (its Click: the PictureBox)
            self.chkOpenGL.Enabled = False

    def View(self, projection):
        """The projection for OpenGL (rows of a 4x4 matrix): x and y as Project
        places them, from -1 to 1 across the picture; the depth (z) nearer the
        nearer a point is toward the viewer."""
        pic, size = self.Surface(), self.Scale()
        across, up = 2 * size / pic.ScaleWidth, 2 * size / pic.ScaleHeight
        toward = self.Toward(projection) or (0.0, 0.0, 0.0)
        return (tuple(across * c for c in projection[0]) + (0.0,),
                tuple(up * c for c in projection[1]) + (0.0,),
                tuple(-c / DEPTH for c in toward) + (0.0,), (0.0, 0.0, 0.0, 1.0))

    def glView_Paint(self):
        """The axes and the faces by OpenGL, nearest first by the depth buffer
        (the faces' edges drawn on them); then the axes' names and the
        wireframe over them, by the graphics methods."""
        gl, scene = self.glView.GL, self.scene
        if gl is None or scene is None or not hasattr(self, "skew"):
            return
        projection = self.Projection()
        solid = self.Solid(projection)
        pic, ratio = self.glView, self.glView.PixelRatio  # (OpenGL counts the screen's pixels)
        gl.glClearColor(*rgb(self.picView.BackColor), 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        toward = self.Toward(projection) or (0.0, 0.0, 1.0)
        scene.Begin(self.View(projection), (pic.ScaleWidth * ratio, pic.ScaleHeight * ratio),
                    (*toward, 0.0), self.Light(projection) if solid else toward)
        for i in range(3):
            scene.Draw(gl, "axes", axis_vertices, [f"back {i}"], GL_LINES, width=ratio,
                       dash=(ratio, 3 * ratio))
            scene.Draw(gl, "axes", axis_vertices, [f"front {i}"], GL_LINES,
                       width=(4 if self.drag == ("axis", i) else 2) * ratio)
        if solid:
            turn, key = self.Orientation(), ("model", self.model.name)
            model = self.model
            gl.glEnable(GL_POLYGON_OFFSET_FILL)
            # The faces a little behind their edges, and behind the decals on them
            for piece, offset in (("faces", 4.0), ("decals", 2.0)):
                gl.glPolygonOffset(offset, offset)
                scene.Draw(gl, key, lambda: model_vertices(model), [piece], GL_TRIANGLES,
                           turn, lit=True)
            gl.glDisable(GL_POLYGON_OFFSET_FILL)
            scene.Draw(gl, key, lambda: model_vertices(model), ["edges"], GL_LINES, turn,
                       width=ratio)
        scene.End()
        gl.glDisable(GL_DEPTH_TEST)
        self.DrawAxes(projection, lines=False)
        if not solid:
            self.DrawWireframe(projection)

    # --- the mouse -------------------------------------------------------------------------
    def HitTest(self, X, Y):
        """What is at a point of the picture: an axis's end, the model, an
        axis's line, or the space around them."""
        projection = self.Projection()
        origin = self.Project((0, 0, 0), projection)
        ends = [(math.hypot(X - p[0], Y - p[1]), i) for i in range(3)
                for p in (self.Project(tuple(AXIS_LENGTH * a for a in AXES[i][0]), projection),
                          self.LabelPlace(i, projection))]
        near, i = min(ends)
        if near <= GRAB:
            return ("axis", i)
        orientation = self.Orientation()
        place = {point: self.Project(self.Turned(point, orientation), projection)
                 for point in self.model.points}
        for part in self.model.parts:
            for corners, _, _ in part:
                if inside((X, Y), [place[c] for c in corners]):
                    return ("model",)
        for i in range(3):
            end = self.Project(tuple(AXIS_LENGTH * a for a in AXES[i][0]), projection)
            if from_segment((X, Y), origin, end) <= GRAB / 2:
                return ("axis", i)
        return ("space",)

    def picView_MouseDown(self, Button, Shift, X, Y):
        if Button != vpLeftButton:
            return
        self.drag = self.HitTest(X, Y)
        self.start = (X, Y, self.azimuth, self.elevation)
        self.last = (X, Y)
        if self.drag[0] == "axis":
            # How far along the axis it was taken: that point stays under the mouse
            i = self.drag[1]
            sx, sy = self.AxisVector(i)
            origin = self.Project((0, 0, 0))
            size = self.Scale() * AXIS_LENGTH
            length = math.hypot(sx, sy) * size
            along = ((X - origin[0]) * sx - (Y - origin[1]) * sy) * size / length ** 2 \
                if length > 1 else 1.0
            self.grip = max(0.25, min(1.2, along))
        self.Draw()

    def picView_MouseMove(self, Button, Shift, X, Y):
        if self.drag is None or not Button & vpLeftButton:
            self.Surface().MousePointer = {"axis": vpCrosshair, "model": vpSizeAll}.get(
                self.HitTest(X, Y)[0], vpDefault)
            return
        if self.drag[0] == "axis":
            self.MoveAxis(self.drag[1], X, Y)
        elif self.drag[0] == "model":
            x, y = self.last
            self.TurnModel(X - x, Y - y)
        else:
            x, y, azimuth, elevation = self.start
            # The axes follow the mouse: right turns them right, down tips them toward you
            self.azimuth = azimuth - math.degrees((X - x) * DRAG_SPEED)
            self.elevation = max(-90.0, min(90.0, elevation + math.degrees((Y - y) * DRAG_SPEED)))
            self.Draw()
        self.last = (X, Y)

    def picView_MouseUp(self, Button, Shift, X, Y):
        self.drag = None
        self.Draw()

    def MoveAxis(self, i, X, Y):
        """Axis i's screen vector to where the mouse is, the others staying:
        a new skew, so that the skew after the camera gives it."""
        origin = self.Project((0, 0, 0))
        size = self.Scale() * AXIS_LENGTH * self.grip
        vector = ((X - origin[0]) / size, (origin[1] - Y) / size)
        projection = [list(row) for row in self.Projection()]
        projection[0][i], projection[1][i] = vector
        camera = self.Camera()  # (a turn: its inverse is its transpose)
        self.skew = product(projection, tuple(zip(*camera)))
        self.Draw()

    def TurnModel(self, dx, dy):
        """The model turned as it is dragged: right around the camera's up axis,
        down around its right axis."""
        right, up, _ = self.Camera()
        turn = product(rotation(up, dx * DRAG_SPEED), rotation(right, dy * DRAG_SPEED))
        self.SetAngles(*angles_of(product(turn, self.Orientation())))

    def picView_DblClick(self):
        self.SetProjection(self.kind)

    def glView_MouseDown(self, Button, Shift, X, Y):
        self.picView_MouseDown(Button, Shift, X, Y)

    def glView_MouseMove(self, Button, Shift, X, Y):
        self.picView_MouseMove(Button, Shift, X, Y)

    def glView_MouseUp(self, Button, Shift, X, Y):
        self.picView_MouseUp(Button, Shift, X, Y)

    def glView_DblClick(self):
        self.picView_DblClick()

    # --- the controls ----------------------------------------------------------------------
    def tmrSpin_Timer(self):
        if self.chkRotate.Value == vpChecked and self.drag != ("model",):
            rates = [s.Value / 100 * FULL_RATE
                     for s in (self.sldRollRate, self.sldPitchRate, self.sldTumbleRate)]
            if any(rates):
                self.SetAngles(self.roll + rates[0], self.pitch + rates[1],
                               self.tumble + rates[2])

    def optModel_Click(self, Index):
        self.SetModel(Index)

    def cboProjection_Click(self):
        if self.cboProjection.ListIndex >= 0:
            self.SetProjection(self.cboProjection.ListIndex)

    def cmdReset_Click(self):
        self.SetProjection(self.kind)

    def chkWireframe_Click(self):
        self.Draw()

    def chkRotate_Click(self):
        self.Draw()

    def chkOpenGL_Click(self):
        self.UseOpenGL(self.chkOpenGL.Value == vpChecked)

    def sldRoll_Scroll(self):
        self.AnglesSlid()

    def sldRoll_Change(self):
        self.AnglesSlid()

    def sldPitch_Scroll(self):
        self.AnglesSlid()

    def sldPitch_Change(self):
        self.AnglesSlid()

    def sldTumble_Scroll(self):
        self.AnglesSlid()

    def sldTumble_Change(self):
        self.AnglesSlid()

    def sldRollRate_Scroll(self):
        self.ShowAngles()

    def sldRollRate_Change(self):
        self.ShowAngles()

    def sldPitchRate_Scroll(self):
        self.ShowAngles()

    def sldPitchRate_Change(self):
        self.ShowAngles()

    def sldTumbleRate_Scroll(self):
        self.ShowAngles()

    def sldTumbleRate_Change(self):
        self.ShowAngles()


def inside(point, polygon):
    """Whether a point is inside a convex polygon (either way around)."""
    x, y = point
    sides = set()
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        side = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
        if abs(side) > 1e-9:
            sides.add(side > 0)
    return len(sides) == 1


def hull(points):
    """The convex hull of points on the picture, counterclockwise (Andrew's
    monotone chain)."""
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def half(points):
        chain = []
        for p in points:
            while len(chain) >= 2 and ((chain[-1][0] - chain[-2][0]) * (p[1] - chain[-2][1])
                                       - (chain[-1][1] - chain[-2][1]) * (p[0] - chain[-2][0])
                                       ) <= 0:
                chain.pop()
            chain.append(p)
        return chain[:-1]

    return half(points) + half(points[::-1])


def overlap(first, second):
    """Whether two convex polygons overlap by more than a pixel: no side of
    either has the other on its far side (the separating axis theorem)."""
    for polygon in (first, second):
        for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
            axis = (y1 - y2, x2 - x1)
            length = math.hypot(*axis)
            if length < 1e-9:
                continue
            ours = [(x * axis[0] + y * axis[1]) / length for x, y in first]
            theirs = [(x * axis[0] + y * axis[1]) / length for x, y in second]
            if max(ours) <= min(theirs) + 1 or max(theirs) <= min(ours) + 1:
                return False
    return True


def from_segment(point, a, b):
    """How far a point is from the segment a-b."""
    (x, y), (x1, y1), (x2, y2) = point, a, b
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length < 1e-9 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


if __name__ == "__main__":
    run(Form1)
