"""Perspectives: a model turning in 1-, 2-, 3-, 4-, 5- or 6-point perspective.

In perspective, lines that are parallel in the world meet on the picture at a
vanishing point: one for each direction. Everything here comes down to where
the three axes' vanishing points are, so they are what you move.

Each axis's column (`columns`) is a direction in front of the eye: where a
step along that axis takes a point. A point p of the world is seen along the
ray A p + o (A: the three columns; o: where the eye sees the world's center,
`Distance` away). The axis's lines are seen heading for the column's
direction, so its vanishing point is the picture of that direction:

- Linear perspectives (1-, 2- and 3-point) draw a ray (x, y, z) at
  F (x, y) / z on a flat picture: an axis whose column has no depth (z = 0)
  never meets its vanishing point: it is at infinity, its lines parallel on
  the picture. 1-point: X and Z at infinity; 2-point: Z at infinity;
  3-point: none.
- Curvilinear perspectives draw the ray's angles, so straight lines bend:
  4-point is cylindrical (left-right angle across, vertical lines straight: the
  four vanishing points of X and Y on the horizon, Z's at infinity), 5-point
  a fisheye of the half sphere in front (the one ahead in the middle, four on
  the rim) and 6-point the whole sphere as two fisheyes, in front and behind,
  touching (the sixth in the middle of the one behind). A vanishing point at
  infinity is square to the line of sight there: on the rim.

Drag a vanishing point to move it (its column turns to look there), the model
to turn it, the empty picture to turn the whole scene; each axis's vanishing
point can be put at infinity up, down, left or right. Double-click the
picture or press Reset view to go back to the perspective chosen. Perspective
lines: the edges of the cube around the model, extended to their vanishing
points, and the horizon.

The model is a cube, a pyramid, a torus, a house, a few boxes or a downtown
(`MODELS`, as in the Projection sample): its parts, each a list of flat
faces. Faces are clipped where the picture ends (behind the eye, the rim) and
their edges bent as the perspective bends them; only those facing the eye
are drawn (all of a part the eye is inside), the parts back to front.

Where OpenGL works, the picture is an OpenGLView (`glView`): OpenGL draws the
perspective lines and the faces with a depth buffer, so each pixel shows what
is nearest (`Scene`, `VERTEX_SHADER`, `FRAGMENT_SHADER`). A linear picture is
drawn at once (`View`: the ray A p + o, then F (x, y) / z; a line's far end is
a direction, at infinity: it ends at its vanishing point); a curvilinear one
is drawn as six linear pictures on the faces of a cube around the eye, then
each pixel's ray is looked up on them (`PICTURE_SHADER`), so every line bends
as it should. The rims, the wireframe and the vanishing points are drawn over
it by the same graphics methods as on the PictureBox. Without OpenGL (or with
OpenGL unchecked) the PictureBox (`picView`) shows the picture drawn as above."""

import math
from array import array

from vp6 import *

try:  # (the shaders and buffers OpenGL draws with; without them: the PictureBox)
    from PySide6.QtGui import QMatrix4x4, QVector2D, QVector3D, QVector4D
    from PySide6.QtOpenGL import (QOpenGLBuffer, QOpenGLFramebufferObject, QOpenGLShader,
                                  QOpenGLShaderProgram)
except ImportError:
    QOpenGLShaderProgram = None

AXES = (((1, 0, 0), RGB(230, 76, 60), "X"), ((0, 1, 0), RGB(80, 200, 100), "Y"),
        ((0, 0, 1), RGB(80, 150, 240), "Z"))
LINEAR, CYLINDRICAL, FISHEYE, SPHERICAL = range(4)
# The perspectives: their name, how rays are drawn, where the eye looks (its yaw
# around Z from +Y, and how far it looks down, in degrees), its distance from the
# model's center and how far it is moved from that line (its gaze kept)
PERSPECTIVES = (
    ("1-point (linear)", LINEAR, 0.0, 0.0, 3.2, (0.8, 0.0, 1.4)),
    ("2-point (linear)", LINEAR, -45.0, 0.0, 3.2, (0.0, 0.0, 1.5)),
    ("3-point (linear)", LINEAR, -45.0, 35.0, 3.2, (0.0, 0.0, 0.0)),
    ("4-point (curvilinear: cylindrical)", CYLINDRICAL, 45.0, 0.0, 2.0, (0.0, 0.0, 0.0)),
    ("5-point (curvilinear: fisheye)", FISHEYE, 0.0, 0.0, 2.0, (0.0, 0.0, 0.0)),
    ("6-point (curvilinear: spherical)", SPHERICAL, 0.0, 0.0, 2.0, (0.0, 0.0, 0.0)),
)
THREE_POINT = 2  # the perspective shown first
# Where an axis's vanishing point is (the ComboBoxes' items): at a point, or at
# infinity in a direction on the picture
PLACES = ("At a point", "At infinity: up", "At infinity: down", "At infinity: left",
          "At infinity: right")
DIRECTIONS = {1: (0.0, 1.0), 2: (0.0, -1.0), 3: (-1.0, 0.0), 4: (1.0, 0.0)}
FRAME = 1.0  # the perspective lines: the cube from -FRAME to FRAME, extended
LINEAR_EXTENT = 4.2  # (half the picture's smaller side, in the model's units)
NEAR = 0.05  # how near the eye a linear perspective draws
STEP = math.radians(3)  # a curved edge is drawn in steps of this angle
CYLINDER_HEIGHT = 2.5  # (how far up and down a cylindrical picture goes, times F)
EDGE = 14  # pixels: a vanishing point off the picture is shown this far inside it
FAR = 1000.0  # a line's far ends: this many times farther than where it is seen

# A box's corners: index = 4 * (x > 0) + 2 * (y > 0) + (z > 0)
CORNERS = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
BOX_FACES = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))
CUBE_COLORS = ((200, 70, 60), (230, 120, 60), (70, 170, 90), (90, 200, 160), (70, 110, 200),
               (140, 120, 220))  # (red, green, blue) for -X, +X, -Y, +Y, -Z, +Z
DRAG_SPEED = 0.01  # radians a pixel
FULL_RATE = 4.0  # degrees a tick at 100%
GRAB = 10  # pixels: how near a vanishing point the mouse must be
TOLERANCE = 1e-6


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(v):
    return math.sqrt(dot(v, v))


def normalized(v):
    size = length(v)
    return tuple(c / size for c in v) if size > TOLERANCE else v


def plus(a, b):
    return tuple(x + y for x, y in zip(a, b))


def minus(a, b):
    return tuple(x - y for x, y in zip(a, b))


def scaled(v, k):
    return tuple(c * k for c in v)


def times(m, v):
    """A 3x3 matrix, as rows, times a vector."""
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


def determinant(a, b, c):
    """The determinant of three rows."""
    return dot(a, cross(b, c))


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


def look(yaw, pitch):
    """The eye's right, up and forward directions in the world, looking at yaw
    degrees around Z from +Y (toward +X) and pitch degrees down."""
    y, p = math.radians(yaw), math.radians(pitch)
    forward = (math.sin(y) * math.cos(p), math.cos(y) * math.cos(p), -math.sin(p))
    right = (math.cos(y), -math.sin(y), 0.0)
    return right, cross(right, forward), forward


def slerp(a, b, t):
    """The direction a fraction t of the way from unit a to unit b, along the
    great circle (a and b less than half a turn apart)."""
    omega = math.acos(max(-1.0, min(1.0, dot(a, b))))
    if omega < 1e-9:
        return a
    s = math.sin(omega)
    return plus(scaled(a, math.sin((1 - t) * omega) / s), scaled(b, math.sin(t * omega) / s))


def clip(points, normal, offset, closed=True):
    """The part of a polygon (closed) or a segment (two points) where
    dot(normal, point) >= offset (Sutherland-Hodgman)."""
    def side(p):
        return dot(normal, p) - offset

    if not closed:
        a, b = points
        sa, sb = side(a), side(b)
        if sa < 0 and sb < 0:
            return []
        if sa < 0:
            a = plus(a, scaled(minus(b, a), sa / (sa - sb)))
        elif sb < 0:
            b = plus(b, scaled(minus(a, b), sb / (sb - sa)))
        return [a, b]
    kept = []
    for a, b in zip(points, points[1:] + points[:1]):
        sa, sb = side(a), side(b)
        if sa >= 0:
            kept.append(a)
        if (sa >= 0) != (sb >= 0):
            kept.append(plus(a, scaled(minus(b, a), sa / (sa - sb))))
    return kept


def crosses_seam(points, closed=True):
    """Whether a polygon or segment (rays) crosses the half plane behind the
    eye where a cylindrical picture is cut (x = 0, z < 0)."""
    pairs = zip(points, points[1:] + points[:1]) if closed else [points]
    for a, b in pairs:
        if a[0] == 0 and a[2] < 0:
            return True
        if (a[0] > 0) != (b[0] > 0) and a[0] != b[0]:
            t = a[0] / (a[0] - b[0])
            if a[2] + t * (b[2] - a[2]) < 0:
                return True
    return False


# --- the models (as in the Projection sample) ----------------------------------------------
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
        # (a, b): a plane between part a and part b: its normal, from a's side toward
        # b's, and a point on it
        self.separations = {}
        if convex:
            for a in range(len(parts)):
                for b in range(a + 1, len(parts)):
                    plane = self.Separation(parts[a], parts[b])
                    if plane is not None:
                        self.separations[a, b] = plane

    @staticmethod
    def Separation(first, second):
        """A face's plane with one convex part inside and the other outside
        (or on it), as its normal from the first part toward the second and
        a point on it; None when no face's plane parts them."""
        for faces, others, sign in ((first, second, 1), (second, first, -1)):
            points = [c for f in others for c in f[0]]
            for corners, normal, _ in faces:
                origin = corners[0]
                if all(dot(minus(point, origin), normal) >= -TOLERANCE for point in points):
                    return tuple(sign * c for c in normal), origin
        return None

    def Closed(self, index):
        """Whether a part is a closed convex solid (the eye can be inside it)."""
        return self.convex and len(self.parts[index]) >= 4


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
GL_LINES, GL_TRIANGLES, GL_TRIANGLE_STRIP = 0x0001, 0x0004, 0x0005
GL_DEPTH_BUFFER_BIT, GL_COLOR_BUFFER_BIT = 0x0100, 0x4000
GL_DEPTH_TEST, GL_LEQUAL, GL_POLYGON_OFFSET_FILL, GL_FLOAT = 0x0B71, 0x0203, 0x8037, 0x1406
GL_TEXTURE_2D, GL_TEXTURE0, GL_LINEAR = 0x0DE1, 0x84C0, 0x2601
GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER = 0x2800, 0x2801
EVEN = 1e-6  # (how much nearer than infinity the farthest depth is: lines to it are kept)
FACE_NEAR = 0.02  # how near the eye a face of the cube around it draws
MARGIN = 0.98  # (a cube's face reaches a little past 45 degrees: no seams between them)
# The faces of the cube around the eye a curvilinear picture is taken from: each
# one's forward, right and up directions (as PICTURE_SHADER picks them)
CUBE = (((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
        ((1, 0, 0), (0, 0, -1), (0, 1, 0)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        ((0, 1, 0), (1, 0, 0), (0, 0, -1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)))

# The shaders: OpenGL's own language (GLSL 1.10, which OpenGL ES 2 takes too). A
# vertex's position goes through the model's turn (turn: none for the perspective
# lines) and the projection (view: the ray A p + o, then the picture); a line's
# other end gives its direction on the picture, along which dash makes it dotted
# (on, period: OpenGL's pixels; period 0: solid). A face
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
# A curvilinear picture: each pixel's ray (as Direction finds it: none past the
# rim) looked up on the cube's faces (face0 to face5, drawn by VERTEX_SHADER and
# FRAGMENT_SHADER as linear pictures); mode is CYLINDRICAL, FISHEYE or SPHERICAL
PICTURE_VERTEX_SHADER = """
attribute vec4 position;
void main() {
    gl_Position = vec4(position.xy, 0.0, 1.0);
}
"""
PICTURE_SHADER = """
#ifdef GL_ES
precision highp float;
#endif
uniform sampler2D face0;
uniform sampler2D face1;
uniform sampler2D face2;
uniform sampler2D face3;
uniform sampler2D face4;
uniform sampler2D face5;
uniform float mode;
uniform vec2 middle;
uniform float size;
uniform vec2 pan;
uniform float focal;
uniform float height;
uniform vec2 ahead;
uniform vec2 behind;
uniform float beside;
uniform float margin;
vec4 look(sampler2D face, vec2 t) {
    return texture2D(face, (margin * t + 1.0) * 0.5);
}
vec4 cube(vec3 d) {
    vec3 a = abs(d);
    if (a.z >= a.x && a.z >= a.y) {
        if (d.z > 0.0) return look(face0, d.xy / d.z);
        return look(face1, vec2(-d.x, d.y) / -d.z);
    }
    if (a.x >= a.y) {
        if (d.x > 0.0) return look(face2, vec2(-d.z, d.y) / d.x);
        return look(face3, vec2(d.z, d.y) / -d.x);
    }
    if (d.y > 0.0) return look(face4, vec2(d.x, -d.z) / d.y);
    return look(face5, d.xz / -d.y);
}
void main() {
    vec2 uv = (gl_FragCoord.xy - middle) / size + pan;
    vec3 d;
    if (mode < 1.5) {
        float phi = uv.x / focal;
        if (abs(phi) > 3.14159265 || abs(uv.y) > height) discard;
        d = vec3(sin(phi), uv.y / focal, cos(phi));
    } else {
        vec2 center = ahead;
        bool back = mode > 2.5 && distance(uv, behind) < distance(uv, ahead);
        if (back) center = behind;
        vec2 q = uv - center;
        float rho = length(q);
        float theta = rho / focal;
        if (theta > 1.5707963) discard;
        d = rho < 1e-9 ? vec3(0.0, 0.0, 1.0) : vec3(sin(theta) * q / rho, cos(theta));
        if (back) d = beside > 0.5 ? vec3(-d.x, d.y, -d.z) : vec3(d.x, -d.y, -d.z);
    }
    gl_FragColor = cube(d);
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


def line_vertices():
    """The perspective lines for OpenGL: the cube's edges along each axis from
    their middle to infinity both ways (axis i), and the horizon: the
    directions of the world's XY plane all the way round, at infinity."""
    pieces = []
    for i, (axis, color, _) in enumerate(AXES):
        others, color, lines = [k for k in range(3) if k != i], rgb(color), []
        for a in (-FRAME, FRAME):
            for b in (-FRAME, FRAME):
                point = [0.0, 0.0, 0.0]
                point[others[0]], point[others[1]] = a, b
                for sign in (1, -1):
                    far = (*scaled(axis, sign), 0.0)
                    lines += [vertex(point, far, color=color), vertex(far, point, color=color)]
        pieces.append((f"axis {i}", lines))
    steps, color, horizon = 24, rgb(RGB(200, 200, 210)), []
    directions = [(math.cos(2 * math.pi * k / steps), math.sin(2 * math.pi * k / steps), 0.0, 0.0)
                  for k in range(steps)]
    for a, b in zip(directions, directions[1:] + directions[:1]):
        horizon += [vertex(a, b, color=color), vertex(b, a, color=color)]
    pieces.append(("horizon", horizon))
    return pieces


class Scene:
    """What OpenGL draws with, made in InitializeGL (its context current): the
    shader programs, buffers of vertices made the first time they're drawn
    (their pieces: name -> (first vertex, count)), and the cube's faces
    (framebuffers) for a curvilinear picture."""

    def __init__(self):
        program = QOpenGLShaderProgram()
        if not (program.addShaderFromSourceCode(QOpenGLShader.Vertex, VERTEX_SHADER)
                and program.addShaderFromSourceCode(QOpenGLShader.Fragment, FRAGMENT_SHADER)
                and program.link()):
            raise RuntimeError(program.log())
        self.program = program
        self.buffers = {}
        picture = QOpenGLShaderProgram()
        if not (picture.addShaderFromSourceCode(QOpenGLShader.Vertex, PICTURE_VERTEX_SHADER)
                and picture.addShaderFromSourceCode(QOpenGLShader.Fragment, PICTURE_SHADER)
                and picture.link()):
            raise RuntimeError(picture.log())
        self.picture = picture
        self.faces = []  # (the cube's faces: framebuffers, all the same size)

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

    def Faces(self, gl, size):
        """The cube's six faces, size pixels square, each with a depth buffer."""
        if not self.faces or self.faces[0].width() != size:
            self.faces = []
            for _ in CUBE:
                face = QOpenGLFramebufferObject(size, size, QOpenGLFramebufferObject.Depth)
                gl.glBindTexture(GL_TEXTURE_2D, face.texture())  # (looked up smoothly)
                gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                gl.glBindTexture(GL_TEXTURE_2D, 0)
                self.faces.append(face)
        return self.faces

    def Picture(self, gl, values):
        """The curvilinear picture from the cube's faces: a rectangle over the
        whole view, each pixel looked up by PICTURE_SHADER (values: its uniforms)."""
        program = self.picture
        program.bind()
        for k, face in enumerate(self.faces):
            gl.glActiveTexture(GL_TEXTURE0 + k)
            gl.glBindTexture(GL_TEXTURE_2D, face.texture())
            program.setUniformValue1i(f"face{k}", k)
        for name, value in values.items():
            if isinstance(value, tuple):
                program.setUniformValue(name, QVector2D(*value))
            else:
                program.setUniformValue1f(name, float(value))
        corners = [vertex((x, y, 0.0)) for x, y in ((-1, -1), (1, -1), (-1, 1), (1, 1))]
        buffer, pieces = self.Buffer("corners", lambda: [("corners", corners)])
        buffer.bind()
        program.enableAttributeArray("position")
        program.setAttributeBuffer("position", GL_FLOAT, 0, 4, FLOATS * 4)
        gl.glDrawArrays(GL_TRIANGLE_STRIP, *pieces["corners"])
        program.disableAttributeArray("position")
        buffer.release()
        for k in reversed(range(len(self.faces))):  # (texture unit 0 left active)
            gl.glActiveTexture(GL_TEXTURE0 + k)
            gl.glBindTexture(GL_TEXTURE_2D, 0)
        program.release()

    def Destroy(self):
        for buffer, _ in self.buffers.values():
            buffer.destroy()
        self.buffers.clear()
        self.faces = []
        self.program.removeAllShaders()
        self.picture.removeAllShaders()


class Form1(Form):
    # region VP6 Designer - generated by the form designer, do not edit
    def InitializeComponent(self):
        self.Caption = 'Perspectives'
        self.Width = 900
        self.Height = 800
        self.picView = PictureBox(self, Left=12, Top=12, Width=588, Height=740, AutoRedraw=True,
                                  BackColor=0x302420, ForeColor=0xE0E0E0, TabIndex=1,
                                  ToolTipText='Drag a vanishing point to move it, the model to turn it, the space around them to turn the scene; double-click: the perspective again')
        self.glView = OpenGLView(self, Left=12, Top=12, Width=588, Height=740, Samples=4,
                                 Visible=False, TabIndex=2,
                                 ToolTipText='Drag a vanishing point to move it, the model to turn it, the space around them to turn the scene; double-click: the perspective again')
        self.lblPerspective = Label(self, Caption='&Perspective:', Left=616, Top=12, Width=268,
                                    Height=20, TabIndex=3)
        self.cboPerspective = ComboBox(self, Style=2, Left=616, Top=34, Width=268, Height=25,
                                       List=['1-point (linear)', '2-point (linear)', '3-point (linear)', '4-point (curvilinear: cylindrical)', '5-point (curvilinear: fisheye)', '6-point (curvilinear: spherical)'],
                                       TabIndex=4,
                                       ToolTipText='The perspective to draw with: how many vanishing points')
        self.cmdReset = CommandButton(self, Caption='&Reset view', Left=616, Top=68, Width=176,
                                      Height=30, TabIndex=5,
                                      ToolTipText='The perspective chosen again, its vanishing points where they belong')
        self.chkOpenGL = CheckBox(self, Caption='Open&GL', Left=800, Top=71, Width=84, Height=24,
                                  Value=1, TabIndex=6,
                                  ToolTipText="Draw the perspective lines and the model with OpenGL (each pixel the nearest, by a depth buffer), or with the PictureBox's graphics methods; off where there is no OpenGL")
        self.chkWireframe = CheckBox(self, Caption='&Wireframe', Left=616, Top=106, Width=88,
                                     Height=24, TabIndex=7,
                                     ToolTipText="The model's edges, or its faces solid and shaded")
        self.chkRotate = CheckBox(self, Caption='R&otate', Left=706, Top=106, Width=88, Height=24,
                                  Value=1, TabIndex=8,
                                  ToolTipText='Turn the model at the rates below')
        self.chkLines = CheckBox(self, Caption='&Lines', Left=796, Top=106, Width=88, Height=24,
                                 Value=1, TabIndex=9,
                                 ToolTipText='The perspective lines: the edges of a cube around the model extended to their vanishing points, and the horizon')
        self.lblModel = Label(self, Caption='Model', Left=616, Top=142, Width=268, Height=20,
                              FontBold=True, TabIndex=10)
        self.optModel = ControlArray()
        self.optModel[0] = OptionButton(self, Caption='&Cube', Left=616, Top=164, Width=88,
                                        Height=24, Value=True, TabIndex=11,
                                        ToolTipText='The model to draw')
        self.optModel[1] = OptionButton(self, Caption='P&yramid', Left=706, Top=164, Width=88,
                                        Height=24, TabIndex=12, ToolTipText='The model to draw')
        self.optModel[2] = OptionButton(self, Caption='&Torus', Left=796, Top=164, Width=88,
                                        Height=24, TabIndex=13, ToolTipText='The model to draw')
        self.optModel[3] = OptionButton(self, Caption='&House', Left=616, Top=190, Width=88,
                                        Height=24, TabIndex=14, ToolTipText='The model to draw')
        self.optModel[4] = OptionButton(self, Caption='&Boxes', Left=706, Top=190, Width=88,
                                        Height=24, TabIndex=15, ToolTipText='The model to draw')
        self.optModel[5] = OptionButton(self, Caption='&Downtown', Left=796, Top=190, Width=88,
                                        Height=24, TabIndex=16, ToolTipText='The model to draw')
        self.lblTurns = Label(self, Caption="The model's turn (degrees)", Left=616, Top=222,
                              Width=268, Height=20, FontBold=True, TabIndex=17)
        self.lblRoll = Label(self, Caption='Roll (X)', Left=616, Top=250, Width=76, Height=20,
                             TabIndex=18)
        self.sldRoll = Slider(self, Left=692, Top=244, Width=146, Height=30, Min=-180, Max=180,
                              LargeChange=15, TickStyle=3, TabIndex=19,
                              ToolTipText="The model's turn around X")
        self.lblRollValue = Label(self, Caption='0°', Left=840, Top=250, Width=44, Height=20,
                                  Alignment=1, TabIndex=20)
        self.lblPitch = Label(self, Caption='Pitch (Y)', Left=616, Top=284, Width=76, Height=20,
                              TabIndex=21)
        self.sldPitch = Slider(self, Left=692, Top=278, Width=146, Height=30, Min=-180, Max=180,
                               LargeChange=15, TickStyle=3, TabIndex=22,
                               ToolTipText="The model's turn around Y")
        self.lblPitchValue = Label(self, Caption='0°', Left=840, Top=284, Width=44, Height=20,
                                   Alignment=1, TabIndex=23)
        self.lblTumble = Label(self, Caption='Tumble (Z)', Left=616, Top=318, Width=76, Height=20,
                               TabIndex=24)
        self.sldTumble = Slider(self, Left=692, Top=312, Width=146, Height=30, Min=-180, Max=180,
                                LargeChange=15, TickStyle=3, TabIndex=25,
                                ToolTipText="The model's turn around Z")
        self.lblTumbleValue = Label(self, Caption='0°', Left=840, Top=318, Width=44, Height=20,
                                    Alignment=1, TabIndex=26)
        self.lblRates = Label(self, Caption='Rates (of full speed)', Left=616, Top=356, Width=268,
                              Height=20, FontBold=True, TabIndex=27)
        self.lblRollRate = Label(self, Caption='Roll', Left=616, Top=384, Width=76, Height=20,
                                 TabIndex=28)
        self.sldRollRate = Slider(self, Left=692, Top=378, Width=146, Height=30, Max=100, Value=15,
                                  LargeChange=10, TickStyle=3, TabIndex=29,
                                  ToolTipText='How fast Rotate rolls the model')
        self.lblRollRateValue = Label(self, Caption='15%', Left=840, Top=384, Width=44, Height=20,
                                      Alignment=1, TabIndex=30)
        self.lblPitchRate = Label(self, Caption='Pitch', Left=616, Top=418, Width=76, Height=20,
                                  TabIndex=31)
        self.sldPitchRate = Slider(self, Left=692, Top=412, Width=146, Height=30, Max=100,
                                   Value=10, LargeChange=10, TickStyle=3, TabIndex=32,
                                   ToolTipText='How fast Rotate pitches the model')
        self.lblPitchRateValue = Label(self, Caption='10%', Left=840, Top=418, Width=44, Height=20,
                                       Alignment=1, TabIndex=33)
        self.lblTumbleRate = Label(self, Caption='Tumble', Left=616, Top=452, Width=76, Height=20,
                                   TabIndex=34)
        self.sldTumbleRate = Slider(self, Left=692, Top=446, Width=146, Height=30, Max=100,
                                    Value=40, LargeChange=10, TickStyle=3, TabIndex=35,
                                    ToolTipText='How fast Rotate tumbles the model')
        self.lblTumbleRateValue = Label(self, Caption='40%', Left=840, Top=452, Width=44,
                                        Height=20, Alignment=1, TabIndex=36)
        self.lblPoints = Label(self, Caption='Vanishing points', Left=616, Top=490, Width=268,
                               Height=20, FontBold=True, TabIndex=37)
        self.lblPlace = ControlArray()
        self.lblPlace[0] = Label(self, Caption='X', Left=616, Top=516, Width=76, Height=20,
                                 ForeColor=0x3C4CE6, FontBold=True, TabIndex=38)
        self.cboPlace = ControlArray()
        self.cboPlace[0] = ComboBox(self, Style=2, Left=692, Top=512, Width=192, Height=25,
                                    List=['At a point', 'At infinity: up', 'At infinity: down', 'At infinity: left', 'At infinity: right'],
                                    TabIndex=39,
                                    ToolTipText="Where X's vanishing point is: at a point (drag it), or at infinity that way")
        self.lblPlace[1] = Label(self, Caption='Y', Left=616, Top=548, Width=76, Height=20,
                                 ForeColor=0x64C850, FontBold=True, TabIndex=40)
        self.cboPlace[1] = ComboBox(self, Style=2, Left=692, Top=544, Width=192, Height=25,
                                    List=['At a point', 'At infinity: up', 'At infinity: down', 'At infinity: left', 'At infinity: right'],
                                    TabIndex=41,
                                    ToolTipText="Where Y's vanishing point is: at a point (drag it), or at infinity that way")
        self.lblPlace[2] = Label(self, Caption='Z', Left=616, Top=580, Width=76, Height=20,
                                 ForeColor=0xF09650, FontBold=True, TabIndex=42)
        self.cboPlace[2] = ComboBox(self, Style=2, Left=692, Top=576, Width=192, Height=25,
                                    List=['At a point', 'At infinity: up', 'At infinity: down', 'At infinity: left', 'At infinity: right'],
                                    TabIndex=43,
                                    ToolTipText="Where Z's vanishing point is: at a point (drag it), or at infinity that way")
        self.lblDistance = Label(self, Caption='Di&stance', Left=616, Top=620, Width=76, Height=20,
                                 TabIndex=44)
        self.sldDistance = Slider(self, Left=692, Top=614, Width=146, Height=30, Max=80, Value=32,
                                  TickStyle=3, TabIndex=45,
                                  ToolTipText="How far the eye is from the model's center (tenths); the vanishing points stay")
        self.lblDistanceValue = Label(self, Caption='3.2', Left=840, Top=620, Width=44, Height=20,
                                      Alignment=1, TabIndex=46)
        self.lblView = Label(self, Caption='', Left=616, Top=656, Width=268, Height=96,
                             WordWrap=True, TabIndex=47)
        self.tmrSpin = Timer(self, Left=616, Top=720, Interval=30)
    # endregion

    def Form_Load(self):
        self.roll = self.pitch = self.tumble = 0.0  # the model's turns (degrees)
        self.drag = None  # what the mouse is dragging: ("vp", axis, sign), ("model",), ("space",)
        self.model = model(0)
        self.syncing = False  # (the controls being set from the state: no Change)
        self.opengl = False  # (drawing with OpenGL: see UseOpenGL)
        self.scene = None  # what OpenGL draws with (made in glView_InitializeGL)
        self.SetPerspective(THREE_POINT)
        self.cboPerspective.ListIndex = THREE_POINT  # (its Click sets it again)
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
        shift = pic.Left + pic.Width + 16 - self.cboPerspective.Left
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

    # --- the perspective -------------------------------------------------------------------
    def SetPerspective(self, index):
        """One of PERSPECTIVES, its vanishing points where they belong: the
        columns are the eye's right, up and forward rows' entries for each axis
        (a real camera), o where the eye sees the world's center."""
        _, mode, yaw, pitch, distance, shift = PERSPECTIVES[index]
        self.kind, self.mode = index, mode
        rows = look(yaw, pitch)
        self.columns = [tuple(row[i] for row in rows) for i in range(3)]
        eye = minus(shift, scaled(rows[2], distance))  # (where the eye is in the world)
        o = scaled(times(rows, eye), -1)
        self.distance = length(o)
        self.toward_center = normalized(o)  # (o's direction: Distance moves along it)
        # A linear picture is F (x, y) / z: F the center's depth, so the model's
        # middle is drawn about as big as it is; a curvilinear one is fitted to the picture
        self.focal = o[2] if mode == LINEAR else 1.0
        self.pan = (self.focal * o[0] / o[2], self.focal * o[1] / o[2])  # (the center's place)
        self.ShowPlaces()
        self.Draw()

    def Eye(self):
        """o: the ray along which the world's center is seen."""
        return scaled(self.toward_center, self.distance)

    def Rows(self):
        """The three columns as rows (x, y and depth): A."""
        return tuple(zip(*self.columns))

    def Ray(self, point, rows=None, eye=None):
        """The ray along which a point of the world is seen: A p + o."""
        return plus(times(rows or self.Rows(), point), eye or self.Eye())

    def Camera(self):
        """Where the eye is in the world: ("point", position), or ("direction",
        toward the eye) when it is infinitely far (a parallel projection);
        None when the columns are all on one plane and it can't tell."""
        rows, eye = self.Rows(), self.Eye()
        m = [tuple(row) + (o,) for row, o in zip(rows, eye)]  # (3x4: A, then o)

        def minor(skip):
            return determinant(*[tuple(v for k, v in enumerate(row) if k != skip) for row in m])

        n = (minor(0), -minor(1), minor(2), -minor(3))  # (A p + o w = 0)
        if math.hypot(*n) < 1e-9:
            return None
        if abs(n[3]) > 1e-9 * math.hypot(*n):
            return "point", scaled(n[:3], 1 / n[3])
        toward = normalized(n[:3])
        if dot(toward, cross(rows[0], rows[1])) < 0:
            toward = scaled(toward, -1)
        return "direction", toward

    @staticmethod
    def Facing(camera, normal, point):
        """How much a plane (its normal, a point on it) faces the eye: > 0 when
        the eye is on the normal's side."""
        kind, value = camera
        if kind == "point":
            return dot(normal, minus(value, point))
        return dot(normal, value)

    @staticmethod
    def Depth(camera, point):
        """How far from the eye a point is (or how far back, for a parallel one)."""
        kind, value = camera
        if kind == "point":
            return length(minus(point, value))
        return -dot(point, value)

    # --- drawing rays on the picture ------------------------------------------------------
    def Beside(self):
        """Whether a spherical picture has its two halves side by side (or one
        above the other, when the picture is taller than wide)."""
        return self.Surface().ScaleWidth >= self.Surface().ScaleHeight

    def Scale(self):
        """Pixels a unit of the picture's plane."""
        pic = self.Surface()
        w, h = pic.ScaleWidth, pic.ScaleHeight
        rim = self.focal * math.pi / 2  # (a quarter turn from the line of sight)
        if self.mode == LINEAR:
            return min(w, h) / 2 / LINEAR_EXTENT
        if self.mode == CYLINDRICAL:
            return 0.96 * min(w / 2 / (2 * rim), h / 2 / (CYLINDER_HEIGHT * self.focal))
        if self.mode == FISHEYE:
            return 0.94 * min(w, h) / 2 / rim
        if self.Beside():
            return 0.96 * min(w / 4, h / 2) / rim
        return 0.96 * min(w / 2, h / 4) / rim

    def Centers(self):
        """A spherical picture's halves: where the one ahead and the one behind
        are centered (in the picture's plane), and how a ray is turned round
        to be seen in the one behind."""
        rim = self.focal * math.pi / 2
        if self.Beside():  # (turned round about up: they touch at the right)
            return (-rim, 0.0), (rim, 0.0), lambda r: (-r[0], r[1], -r[2])
        return (0.0, rim), (0.0, -rim), lambda r: (r[0], -r[1], -r[2])  # (at the bottom)

    def Fisheye(self, ray):
        """A ray at its angle from the line of sight, as far from the middle."""
        x, y, z = ray
        rho = math.hypot(x, y)
        if rho < 1e-12:
            return 0.0, 0.0
        theta = math.atan2(rho, z)
        return self.focal * theta * x / rho, self.focal * theta * y / rho

    def Map(self, ray, region=0):
        """Where a ray is drawn, in the picture's plane (y up). A region is the
        piece of a picture it is in: the cylindrical one's right (1) or left (2)
        half behind the eye, the spherical one's half behind (1)."""
        x, y, z = ray
        f = self.focal
        if self.mode == LINEAR:
            u, v = f * x / z, f * y / z
        elif self.mode == CYLINDRICAL:
            phi = math.atan2(x, z)
            if region == 1 and phi < 0:
                phi += 2 * math.pi
            elif region == 2 and phi > 0:
                phi -= 2 * math.pi
            across = math.hypot(x, z)
            limit = CYLINDER_HEIGHT * f
            v = max(-limit, min(limit, f * y / across)) if across > 1e-12 \
                else math.copysign(limit, y)
            u = f * phi
        elif self.mode == FISHEYE:
            u, v = self.Fisheye(ray)
        else:
            ahead, behind, turned = self.Centers()
            if region == 1:
                u, v = self.Fisheye(turned(ray))
                u, v = u + behind[0], v + behind[1]
            else:
                u, v = self.Fisheye(ray)
                u, v = u + ahead[0], v + ahead[1]
        return u - self.pan[0], v - self.pan[1]

    def ToPicture(self, place):
        pic, size = self.Surface(), self.Scale()
        return pic.ScaleWidth / 2 + size * place[0], pic.ScaleHeight / 2 - size * place[1]

    def FromPicture(self, X, Y):
        pic, size = self.Surface(), self.Scale()
        return (X - pic.ScaleWidth / 2) / size, (pic.ScaleHeight / 2 - Y) / size

    def Direction(self, X, Y):
        """The direction of the ray drawn at a point of the picture (the
        nearest one drawn, beyond the rim)."""
        u, v = self.FromPicture(X, Y)
        u, v = u + self.pan[0], v + self.pan[1]
        f = self.focal
        if self.mode == LINEAR:
            return normalized((u, v, f))
        if self.mode == CYLINDRICAL:
            phi = max(-math.pi, min(math.pi, u / f))
            return normalized((math.sin(phi), v / f, math.cos(phi)))

        def fisheye(u, v):
            theta = min(math.pi / 2, math.hypot(u, v) / f)
            rho = math.hypot(u, v)
            if rho < 1e-12:
                return 0.0, 0.0, 1.0
            return (math.sin(theta) * u / rho, math.sin(theta) * v / rho, math.cos(theta))

        if self.mode == FISHEYE:
            return fisheye(u, v)
        ahead, behind, turned = self.Centers()
        if math.dist((u, v), behind) < math.dist((u, v), ahead):
            return turned(fisheye(u - behind[0], v - behind[1]))  # (turning is its own undoing)
        return fisheye(u - ahead[0], v - ahead[1])

    def Pieces(self, rays, closed=True):
        """A polygon (closed) or segment of rays cut where the picture is: its
        pieces as (region, rays): in front of the eye (linear), where the
        cylinder is cut behind it, in the half in front (fisheye), or into the
        halves in front and behind (spherical)."""
        least = 3 if closed else 2

        def kept(piece, region):
            return [(region, piece)] if len(piece) >= least else []

        if self.mode == LINEAR:
            return kept(clip(rays, (0, 0, 1), NEAR, closed), 0)
        if self.mode == FISHEYE:
            return kept(clip(rays, (0, 0, 1), 0.0, closed), 0)
        if self.mode == SPHERICAL:
            return (kept(clip(rays, (0, 0, 1), 0.0, closed), 0)
                    + kept(clip(rays, (0, 0, -1), 0.0, closed), 1))
        if not crosses_seam(rays, closed):
            return [(0, rays)]
        return (kept(clip(rays, (1, 0, 0), 0.0, closed), 1)
                + kept(clip(rays, (-1, 0, 0), 0.0, closed), 2))

    def Arc(self, a, b, region, last=True):
        """The picture of the segment between two rays: straight in a linear
        perspective, otherwise in steps along the great circle between them."""
        if self.mode == LINEAR:
            points = [a, b]
        else:
            a, b = normalized(a), normalized(b)
            steps = max(1, math.ceil(math.acos(max(-1.0, min(1.0, dot(a, b)))) / STEP))
            points = [slerp(a, b, k / steps) for k in range(steps + 1)]
        if not last:
            points = points[:-1]
        return [self.ToPicture(self.Map(r, region)) for r in points]

    def Outline(self, region, rays):
        """A polygon of rays drawn: its edges bent as the perspective bends them."""
        outline = []
        for a, b in zip(rays, rays[1:] + rays[:1]):
            outline += self.Arc(a, b, region, last=False)
        return outline

    def Lines(self, a, b):
        """A segment of rays drawn: a polyline for each piece of it."""
        return [self.Arc(*piece, region) for region, piece in self.Pieces([a, b], closed=False)]

    def Places(self, ray):
        """Where a single ray is drawn (none, one or, on a spherical rim, two)."""
        return [self.ToPicture(self.Map(ray, region))
                for region, _ in self.Pieces([ray, ray], closed=False)]

    # --- the vanishing points -------------------------------------------------------------
    def Finite(self, i):
        """Whether axis i's vanishing point is at a point (its column has depth)."""
        c = self.columns[i]
        return abs(c[2]) > 1e-9 * max(length(c), 1e-12)

    def VanishingPoints(self):
        """Every vanishing point drawn: (axis, sign, place on the picture or
        None, direction on the picture when it is at infinity). A linear
        perspective has one for each axis (both ways meet there); a
        curvilinear one has one for each way."""
        found = []
        for i in range(3):
            c = self.columns[i]
            if self.mode == LINEAR:
                if self.Finite(i):
                    found.append((i, 1, self.ToPicture(self.Map(c)), None))
                else:
                    found.append((i, 1, None, (c[0], c[1])))
                continue
            for sign in (1, -1):
                d = scaled(c, sign)
                if self.mode == CYLINDRICAL and math.hypot(d[0], d[2]) < 1e-9 * length(d):
                    found.append((i, sign, None, (0.0, d[1])))  # (straight up or down)
                    continue
                if self.mode == FISHEYE and d[2] < -1e-9 * length(d):
                    continue  # (behind the eye)
                if self.mode == FISHEYE:
                    d = (d[0], d[1], max(0.0, d[2]))
                if self.mode == SPHERICAL:
                    regions = [region for region, z in ((0, d[2]), (1, -d[2]))
                               if z >= -1e-9 * length(d)]
                else:
                    regions = [0]
                for region in regions:
                    found.append((i, sign, self.ToPicture(self.Map(d, region)), None))
        return found

    def Count(self):
        """How many vanishing points the perspective has (its N-point)."""
        if self.mode == LINEAR:
            return sum(self.Finite(i) for i in range(3))
        return len({(i, sign) for i, sign, place, _ in self.VanishingPoints()
                    if place is not None})

    def Marker(self, place, direction):
        """Where a vanishing point is shown: its place, or (off the picture or
        at infinity) at the edge, on the way to it from the middle; and
        whether it is at the edge."""
        pic = self.Surface()
        w, h = pic.ScaleWidth, pic.ScaleHeight
        if place is not None and EDGE <= place[0] <= w - EDGE and EDGE <= place[1] <= h - EDGE:
            return place, False
        if place is not None:
            dx, dy = place[0] - w / 2, place[1] - h / 2
        else:
            dx, dy = direction[0], -direction[1]
        size = math.hypot(dx, dy)
        if size < 1e-12:
            return (w / 2, h / 2), True
        dx, dy = dx / size, dy / size
        reach = min((w / 2 - EDGE) / abs(dx) if abs(dx) > 1e-12 else math.inf,
                    (h / 2 - EDGE) / abs(dy) if abs(dy) > 1e-12 else math.inf)
        return (w / 2 + dx * reach, h / 2 + dy * reach), True

    def Name(self, i, sign):
        name = AXES[i][2]
        return name if self.mode == LINEAR else ("+" if sign > 0 else "−") + name

    def Place(self, i):
        """Where axis i's vanishing point is, as an index of PLACES."""
        if self.Finite(i):
            return 0
        x, y = self.columns[i][:2]
        return max(DIRECTIONS, key=lambda k: x * DIRECTIONS[k][0] + y * DIRECTIONS[k][1])

    def SetPlace(self, i, place):
        """Axis i's vanishing point at a point, or at infinity in one of
        DIRECTIONS: its column turned, keeping its length."""
        c = self.columns[i]
        size = length(c)
        if place == 0:
            if self.Finite(i):
                return
            x, y = normalized((c[0], c[1], 0.0))[:2]
            if self.mode == LINEAR:  # (toward the picture's edge)
                u = (x * 0.8 * LINEAR_EXTENT + self.pan[0], y * 0.8 * LINEAR_EXTENT + self.pan[1])
                d = normalized((u[0], u[1], self.focal))
            else:  # (50 degrees from the line of sight)
                a = math.radians(50)
                d = (math.sin(a) * x, math.sin(a) * y, math.cos(a))
        else:
            x, y = DIRECTIONS[place]
            d = (x, y, 0.0)
        self.columns[i] = scaled(d, size)
        self.ShowPlaces()
        self.Draw()

    def MoveVanishingPoint(self, i, sign, X, Y):
        """A vanishing point to where the mouse is: its column turned to look
        that way, keeping its length (a linear one keeps its side of the eye)."""
        c = self.columns[i]
        d = self.Direction(X, Y)
        if self.mode == LINEAR:
            if dot(d, c) < 0:
                d = scaled(d, -1)  # (the same place: the axis still the same way)
        else:
            d = scaled(d, sign)
        self.columns[i] = scaled(d, length(c))
        self.ShowPlaces()
        self.Draw()

    def ShowPlaces(self):
        """The vanishing points' ComboBoxes from the columns."""
        if not hasattr(self, "cboPlace"):
            return
        self.syncing = True
        try:
            for i in range(3):
                if self.cboPlace[i].ListIndex != self.Place(i):
                    self.cboPlace[i].ListIndex = self.Place(i)
            self.sldDistance.Value = round(self.distance * 10)
            self.lblDistanceValue.Caption = f"{self.distance:.1f}"
        finally:
            self.syncing = False

    def Describe(self):
        """What the perspective is now: how many vanishing points, and of
        which kind."""
        n = self.Count()
        if self.mode == LINEAR:
            if n == 0:
                return "A parallel projection (no vanishing points)"
            return f"{n}-point perspective (linear)"
        kind = {CYLINDRICAL: "cylindrical", FISHEYE: "fisheye", SPHERICAL: "spherical"}
        return f"{n}-point perspective (curvilinear: {kind[self.mode]})"

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
        if not hasattr(self, "columns"):  # (a Resize before Form_Load)
            return
        if self.opengl:
            self.glView.Update()  # (glView_Paint draws it)
        else:
            self.picView.Cls()
            self.DrawRims()
            if self.chkLines.Value == vpChecked:
                self.DrawLines()
            camera = self.Camera()
            if self.Solid(camera):
                self.DrawSolid(camera)
            else:
                self.DrawWireframe()
            self.DrawVanishingPoints()
        self.lblView.Caption = (
            f"{self.Describe()}\n\n"
            "Drag a vanishing point to move it, the model to turn it, the space around "
            "them to turn the scene; double-click for the perspective again.")

    def Solid(self, camera):
        """Whether the model is drawn solid (not as a wireframe, and the eye is
        somewhere: near and far can be told apart)."""
        return self.chkWireframe.Value != vpChecked and camera is not None

    def Light(self):
        """Where the light comes from: above the eye's left shoulder."""
        rows = self.Rows()
        right, up = normalized(rows[0]), normalized(rows[1])
        toward = normalized(cross(rows[0], rows[1]))
        return normalized(tuple(0.75 * t + 0.55 * u - 0.35 * r
                                for r, u, t in zip(right, up, toward)))

    def Polyline(self, points, color):
        pic = self.Surface()
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            pic.Line(x1, y1, x2, y2, color)

    def DrawRims(self):
        """Where a curvilinear picture ends: the fisheyes' rims, the cylinder's
        cut behind the eye."""
        pic = self.Surface()
        color = RGB(110, 110, 125)
        pic.DrawWidth, pic.DrawStyle = 1, vpSolid
        rim = self.focal * math.pi / 2
        if self.mode == FISHEYE:
            centers = [(-self.pan[0], -self.pan[1])]
        elif self.mode == SPHERICAL:
            centers = [minus(center, self.pan) for center in self.Centers()[:2]]
        else:
            centers = []
            if self.mode == CYLINDRICAL:
                for u in (-2 * rim, 2 * rim):
                    top = self.ToPicture((u - self.pan[0], CYLINDER_HEIGHT * self.focal))
                    bottom = self.ToPicture((u - self.pan[0], -CYLINDER_HEIGHT * self.focal))
                    pic.Line(*top, *bottom, color)
        for center in centers:
            x, y = self.ToPicture(center)
            pic.Circle(x, y, rim * self.Scale(), color)

    def DrawLines(self):
        """The perspective lines: the edges of the cube around the model
        (from -FRAME to FRAME) along each axis, extended both ways to their
        vanishing points, dotted; and the horizon, dashed: where every
        horizontal direction is drawn."""
        pic = self.Surface()
        rows, eye = self.Rows(), self.Eye()
        pic.DrawWidth = 1
        for i, (axis, color, _) in enumerate(AXES):
            c = self.columns[i]
            pic.DrawStyle = vpDot
            others = [k for k in range(3) if k != i]
            for a in (-FRAME, FRAME):
                for b in (-FRAME, FRAME):
                    point = [0.0, 0.0, 0.0]
                    point[others[0]], point[others[1]] = a, b
                    near = self.Ray(point, rows, eye)
                    far = FAR * max(1.0, length(near)) / max(length(c), 1e-12)
                    for end in (plus(near, scaled(c, far)), minus(near, scaled(c, far))):
                        for line in self.Lines(near, end):
                            self.Polyline(line, color)
        # The horizon: the directions of the world's XY plane, all the way round
        pic.DrawStyle = vpDash
        x, y = self.columns[0], self.columns[1]
        steps = 24
        far = FAR / max(length(x), length(y), 1e-12)
        directions = [scaled(plus(scaled(x, math.cos(2 * math.pi * k / steps)),
                                  scaled(y, math.sin(2 * math.pi * k / steps))), far)
                      for k in range(steps)]
        for a, b in zip(directions, directions[1:] + directions[:1]):
            for line in self.Lines(a, b):
                self.Polyline(line, RGB(200, 200, 210))
        pic.DrawStyle = vpSolid

    def DrawVanishingPoints(self):
        """Each vanishing point: a dot in its axis's color, named; one off the
        picture or at infinity at the edge, an arrow pointing its way."""
        pic = self.Surface()
        pic.DrawWidth, pic.DrawStyle = 1, vpSolid
        pic.FillStyle = vpFSSolid
        for i, sign, place, direction in self.VanishingPoints():
            color = AXES[i][1]
            (x, y), edge = self.Marker(place, direction)
            pic.FillColor = color
            if self.drag == ("vp", i, sign):
                pic.Circle(x, y, 8, RGB(255, 255, 255))
            pic.Circle(x, y, 5, RGB(20, 20, 30))
            name = self.Name(i, sign) + (" ∞" if place is None else "")
            if edge:  # (an arrow toward it)
                w, h = pic.ScaleWidth / 2, pic.ScaleHeight / 2
                dx, dy = x - w, y - h
                size = math.hypot(dx, dy) or 1.0
                pic.Line(x, y, x + 10 * dx / size, y + 10 * dy / size, color)
            pic.ForeColor = color
            pic.CurrentX = min(max(2, x + 8), pic.ScaleWidth - pic.TextWidth(name) - 2)
            pic.CurrentY = min(max(2, y - pic.TextHeight(name) - 2),
                               pic.ScaleHeight - pic.TextHeight(name) - 2)
            pic.Print(name)
        pic.FillStyle = vpFSTransparent

    def DrawWireframe(self):
        """The model's edges, bent as the perspective bends them, its corners dotted."""
        pic = self.Surface()
        orientation, rows, eye = self.Orientation(), self.Rows(), self.Eye()
        rays = {point: self.Ray(self.Turned(point, orientation), rows, eye)
                for point in self.model.points}
        pic.DrawWidth = 2 if len(rays) <= 40 else 1
        for a, b in self.model.edges:
            for line in self.Lines(rays[a], rays[b]):
                self.Polyline(line, RGB(240, 240, 240))
        pic.FillStyle, pic.FillColor = vpFSSolid, RGB(255, 210, 80)
        pic.DrawWidth = 1
        radius = 3 if len(rays) <= 40 else 2
        for ray in rays.values():
            for x, y in self.Places(ray):
                pic.Circle(x, y, radius, RGB(255, 210, 80))
        pic.FillStyle = vpFSTransparent

    def Faces(self, camera, orientation=None):
        """The model's faces to draw, part by part: (depth, outlines on the
        picture, normal, color, and its rays if it was cut) for those facing
        the eye (each face of a closed part the eye is inside, seen from
        inside); and the parts the eye is inside."""
        orientation = orientation or self.Orientation()
        rows, eye = self.Rows(), self.Eye()
        parts, inside = [], set()
        for index, part in enumerate(self.model.parts):
            turned = [([self.Turned(c, orientation) for c in corners],
                       self.Turned(normal, orientation), color)
                      for corners, normal, color in part]
            facing = [self.Facing(camera, normal, corners[0]) > 0
                      for corners, normal, _ in turned]
            within = camera[0] == "point" and self.model.Closed(index) and not any(facing)
            if within:
                inside.add(index)
            faces = []
            for (corners, normal, color), toward in zip(turned, facing):
                if not toward and not within:
                    continue  # (facing away: hidden)
                if within:
                    normal = scaled(normal, -1)
                rays = [self.Ray(c, rows, eye) for c in corners]
                pieces = self.Pieces(rays)
                outlines = [self.Outline(region, piece) for region, piece in pieces]
                if outlines:
                    depth = sum(self.Depth(camera, c) for c in corners) / len(corners)
                    whole = len(pieces) == 1 and pieces[0][1] == rays
                    faces.append((depth, outlines, normal, color, None if whole else rays))
            parts.append(sorted(faces, key=lambda f: -f[0]))  # (farthest first)
        return parts, inside

    def DrawSolid(self, camera):
        """The faces toward the eye, the parts back to front (a part's own
        faces farthest first), lit from above the eye's left shoulder."""
        pic = self.Surface()
        light = self.Light()
        orientation = self.Orientation()
        parts, inside = self.Faces(camera, orientation)
        pic.FillStyle, pic.DrawWidth = vpFSSolid, 1
        outline = RGB(20, 20, 30)
        for index in self.PartOrder(orientation, camera, parts, inside):
            for _, outlines, normal, (red, green, blue), cut in parts[index]:
                shade = 0.35 + 0.65 * max(0.0, dot(normal, light))
                pic.FillColor = RGB(int(red * shade), int(green * shade), int(blue * shade))
                if cut:  # (outlined along its own edges, not where it was cut)
                    pic.DrawStyle = vpInvisible
                for corners in outlines:
                    pic.Polygon(corners, outline)
                pic.DrawStyle = vpSolid
                for a, b in zip(cut or [], (cut or [])[1:] + (cut or [])[:1]):
                    for line in self.Lines(a, b):
                        self.Polyline(line, outline)
        pic.FillStyle = vpFSTransparent

    def PartOrder(self, orientation, camera, parts, inside=()):
        """The parts with faces to draw (parts: each one's faces from Faces),
        in the order to draw them: those the eye is inside first; then, of two
        whose pictures overlap, the one on the far side of the plane between
        them first; otherwise (and for what that leaves open) the farthest
        first."""
        model = self.model
        depths = [self.Depth(camera, self.Turned(c, orientation)) for c in model.centers]
        outlines = {index: hull([p for _, pieces, _, _, _ in faces for piece in pieces
                                 for p in piece])
                    for index, faces in enumerate(parts) if faces}
        before = {index: set() for index in outlines}  # before[b]: the parts to draw before b
        for (a, b), (normal, point) in model.separations.items():
            if a not in outlines or b not in outlines or a in inside or b in inside:
                continue  # (nothing of it to draw, or around the eye)
            if not overlap(outlines[a], outlines[b]):
                continue  # (apart on the picture: either order)
            side = self.Facing(camera, self.Turned(normal, orientation),
                               self.Turned(point, orientation))
            if side > TOLERANCE:  # the eye on b's side: a is behind
                before[b].add(a)
            elif side < -TOLERANCE:
                before[a].add(b)
        left = sorted(outlines, key=lambda i: (i not in inside, -depths[i]))
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

    def Rays(self):
        """The world to rays for OpenGL (rows of a 4x4 matrix): A p + o, a
        direction (w = 0) staying one."""
        return tuple(tuple(row) + (o,) for row, o in zip(self.Rows(), self.Eye())) + (
            (0.0, 0.0, 0.0, 1.0),)

    def View(self, face=None):
        """The projection for OpenGL (rows of a 4x4 matrix): a linear picture
        (F (x, y) / z, placed as ToPicture places it, from -1 to 1 across), or
        one of the CUBE's faces (a square linear picture, 90 degrees across).
        The depth grows with z: a direction (at infinity) the farthest."""
        if face is None:
            pic, size, f = self.Surface(), self.Scale(), self.focal
            across, up = 2 * size / pic.ScaleWidth, 2 * size / pic.ScaleHeight
            picture = ((across * f, 0.0, -across * self.pan[0], 0.0),
                       (0.0, up * f, -up * self.pan[1], 0.0),
                       (0.0, 0.0, 1 - EVEN, -2 * NEAR), (0.0, 0.0, 1.0, 0.0))
        else:
            forward, right, up = CUBE[face]
            picture = (tuple(MARGIN * c for c in right) + (0.0,),
                       tuple(MARGIN * c for c in up) + (0.0,),
                       tuple((1 - EVEN) * c for c in forward) + (-2 * FACE_NEAR,),
                       tuple(forward) + (0.0,))
        rays = self.Rays()
        return tuple(tuple(sum(row[k] * rays[k][j] for k in range(4)) for j in range(4))
                     for row in picture)

    def FaceSize(self):
        """The cube's faces' size in pixels: about as many as the picture has
        at its middle (OpenGL's: the screen's)."""
        pixels = 2 * self.Scale() * self.focal * self.glView.PixelRatio / MARGIN
        return max(256, min(2048, round(pixels)))

    def glView_Paint(self):
        """The perspective lines and the faces by OpenGL, nearest first by the
        depth buffer: a linear picture at once, a curvilinear one from the
        cube's faces; then the rims, the wireframe and the vanishing points
        over them, by the graphics methods."""
        gl, scene = self.glView.GL, self.scene
        if gl is None or scene is None or not hasattr(self, "columns"):
            return
        camera = self.Camera()
        solid = self.Solid(camera)
        pic, ratio = self.glView, self.glView.PixelRatio  # (OpenGL counts the screen's pixels)
        width, height = round(pic.ScaleWidth * ratio), round(pic.ScaleHeight * ratio)
        eye = (0.0, 0.0, 1.0, 0.0) if camera is None else \
            (*camera[1], 1.0 if camera[0] == "point" else 0.0)
        light = self.Light() if solid else (0.0, 0.0, 1.0)
        if self.mode == LINEAR:
            self.DrawScene(gl, self.View(), (width, height), eye, light, solid, ratio)
        else:
            size = self.FaceSize()
            faces = scene.Faces(gl, size)
            scale = size * MARGIN / 2 / (self.Scale() * self.focal)  # (its pixels to ours)
            for k, face in enumerate(faces):
                face.bind()
                gl.glViewport(0, 0, size, size)
                self.DrawScene(gl, self.View(k), (size, size), eye, light, solid, scale)
                face.release()
            gl.glViewport(0, 0, width, height)
            gl.glClearColor(*rgb(self.picView.BackColor), 1.0)
            gl.glClear(GL_COLOR_BUFFER_BIT)
            # (a fisheye is centered; a spherical picture's halves are beside each other)
            ahead, behind, _ = self.Centers() if self.mode == SPHERICAL else ((0, 0),) * 3
            scene.Picture(gl, {
                "mode": self.mode, "middle": (width / 2, height / 2),
                "size": self.Scale() * ratio, "pan": self.pan, "focal": self.focal,
                "height": CYLINDER_HEIGHT * self.focal, "ahead": tuple(ahead), "behind": tuple(behind),
                "beside": 1.0 if self.Beside() else 0.0, "margin": MARGIN})
        self.DrawRims()
        if not solid:
            self.DrawWireframe()
        self.DrawVanishingPoints()

    def DrawScene(self, gl, view, pixels, eye, light, solid, scale):
        """One linear picture by OpenGL: the perspective lines (dotted, the
        horizon dashed) and the model's faces with their edges (solid); scale
        is its pixels to one of the picture's."""
        scene, model = self.scene, self.model
        gl.glClearColor(*rgb(self.picView.BackColor), 1.0)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        scene.Begin(view, pixels, eye, light)
        if self.chkLines.Value == vpChecked:
            for i in range(3):
                scene.Draw(gl, "lines", line_vertices, [f"axis {i}"], GL_LINES, width=scale,
                           dash=(scale, 3 * scale))
            scene.Draw(gl, "lines", line_vertices, ["horizon"], GL_LINES, width=scale,
                       dash=(4 * scale, 6 * scale))
        if solid:
            turn, key = self.Orientation(), ("model", model.name)
            gl.glEnable(GL_POLYGON_OFFSET_FILL)
            # The faces a little behind their edges, and behind the decals on them
            for piece, offset in (("faces", 4.0), ("decals", 2.0)):
                gl.glPolygonOffset(offset, offset)
                scene.Draw(gl, key, lambda: model_vertices(model), [piece], GL_TRIANGLES,
                           turn, lit=True)
            gl.glDisable(GL_POLYGON_OFFSET_FILL)
            scene.Draw(gl, key, lambda: model_vertices(model), ["edges"], GL_LINES, turn,
                       width=scale)
        scene.End()
        gl.glDisable(GL_DEPTH_TEST)

    # --- the mouse -------------------------------------------------------------------------
    def HitTest(self, X, Y):
        """What is at a point of the picture: a vanishing point, the model or
        the space around it."""
        for i, sign, place, direction in self.VanishingPoints():
            (x, y), _ = self.Marker(place, direction)
            if math.hypot(X - x, Y - y) <= GRAB:
                return ("vp", i, sign)
        orientation, rows, eye = self.Orientation(), self.Rows(), self.Eye()
        for part in self.model.parts:
            for corners, _, _ in part:
                rays = [self.Ray(self.Turned(c, orientation), rows, eye) for c in corners]
                for region, piece in self.Pieces(rays):
                    if inside((X, Y), self.Outline(region, piece)):
                        return ("model",)
        return ("space",)

    def picView_MouseDown(self, Button, Shift, X, Y):
        if Button != vpLeftButton:
            return
        self.drag = self.HitTest(X, Y)
        self.last = (X, Y)
        self.Draw()

    def picView_MouseMove(self, Button, Shift, X, Y):
        if self.drag is None or not Button & vpLeftButton:
            self.Surface().MousePointer = {"vp": vpCrosshair, "model": vpSizeAll}.get(
                self.HitTest(X, Y)[0], vpDefault)
            return
        x, y = self.last
        if self.drag[0] == "vp":
            self.MoveVanishingPoint(self.drag[1], self.drag[2], X, Y)
        elif self.drag[0] == "model":
            self.TurnModel(X - x, Y - y)
        else:
            self.TurnScene(X - x, Y - y)
        self.last = (X, Y)

    def picView_MouseUp(self, Button, Shift, X, Y):
        self.drag = None
        self.Draw()

    def Turn(self, dx, dy, upright=False):
        """The turn for a drag: right around the eye's up axis (or the world's
        Z when upright), down around its right axis."""
        rows = self.Rows()
        right = normalized(rows[0])
        up = (0.0, 0.0, 1.0) if upright else normalized(rows[1])
        return product(rotation(up, dx * DRAG_SPEED), rotation(right, dy * DRAG_SPEED))

    def TurnModel(self, dx, dy):
        """The model turned as it is dragged."""
        turn = self.Turn(dx, dy)
        self.SetAngles(*angles_of(product(turn, self.Orientation())))

    def TurnScene(self, dx, dy):
        """The whole scene turned around its center as the space is dragged (the
        vanishing points with it): A p becomes A (turn p); sideways around the
        world's Z, so upright lines stay upright."""
        turn = self.Turn(dx, dy, upright=True)
        rows = product(self.Rows(), turn)
        self.columns = [tuple(row[i] for row in rows) for i in range(3)]
        self.ShowPlaces()
        self.Draw()

    def picView_DblClick(self):
        self.SetPerspective(self.kind)

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

    def cboPerspective_Click(self):
        if self.cboPerspective.ListIndex >= 0:
            self.SetPerspective(self.cboPerspective.ListIndex)

    def cboPlace_Click(self, Index):
        if not self.syncing and self.cboPlace[Index].ListIndex >= 0:
            self.SetPlace(Index, self.cboPlace[Index].ListIndex)

    def cmdReset_Click(self):
        self.SetPerspective(self.kind)

    def chkWireframe_Click(self):
        self.Draw()

    def chkRotate_Click(self):
        self.Draw()

    def chkLines_Click(self):
        self.Draw()

    def chkOpenGL_Click(self):
        self.UseOpenGL(self.chkOpenGL.Value == vpChecked)

    def DistanceSlid(self):
        if not self.syncing:
            self.distance = self.sldDistance.Value / 10
            self.lblDistanceValue.Caption = f"{self.distance:.1f}"
            self.Draw()

    def sldDistance_Scroll(self):
        self.DistanceSlid()

    def sldDistance_Change(self):
        self.DistanceSlid()

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
    """Whether a point is inside a polygon (crossings of a ray to its right)."""
    x, y = point
    within = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            within = not within
    return within


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
            size = math.hypot(*axis)
            if size < 1e-9:
                continue
            ours = [(x * axis[0] + y * axis[1]) / size for x, y in first]
            theirs = [(x * axis[0] + y * axis[1]) / size for x, y in second]
            if max(ours) <= min(theirs) + 1 or max(theirs) <= min(ours) + 1:
                return False
    return True


if __name__ == "__main__":
    run(Form1)
