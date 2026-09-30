"""The Kitchen Sink project template.

A ready-made project that demonstrates every VP6 control and most of the
API, explorer-style: Form1 is a window with a TreeView of topics on the left
and a content pane, in which each topic's page (a form of its own, pg*.py)
is shown with ShowIn. The first page is an introduction.

The sources live in ``templates/kitchensink/`` next to this file. **When VP6
gains a control, event or API function, demonstrate it there**:
``tests/test_kitchen_sink.py`` fails when a control type, a public API name
or a control's default event isn't covered.
"""

from __future__ import annotations

import math
import os
import shutil
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPen)

from ..app import ensure_app
from ..project import SUB_MAIN, Project

TEMPLATE_DIR = Path(__file__).parent / "templates" / "kitchensink"
FORMS = (  # the window, its pages (in the index's order) and the modal dialog
    "Form1.py", "pgIntro.py", "pgText.py", "pgButtons.py", "pgLists.py", "pgScrollBars.py",
    "pgValues.py", "pgPictures.py", "pgZOrder.py", "pgTree.py", "pgListView.py", "pgTabs.py",
    "pgFiles.py", "pgTimer.py", "pgLayout.py", "pgScrolling.py", "pgEmbedded.py", "pgDialogs.py",
    "pgSchemes.py", "pgKeyboard.py", "pgMouse.py", "pgArrays.py", "pgMenus.py", "pgGlobals.py",
    "frmDialog.py",
)
MODULES = ("Module1.py",)
PICTURE = "vp6.png"  # shown on the Pictures page
IMAGES = "images"  # small pictures for the ImageLists (TreeView and TabStrip pages)
ICONS = ("folder", "paw", "leaf", "star", "gear", "palette", "info",  # TreeView, TabStrip
         "back", "forward", "sidebar", "system", "sun", "moon")  # the window's Toolbar


def create(directory: str, name: str) -> Project:
    """Copy the Kitchen Sink sources into ``directory`` and return its project
    (not saved yet)."""
    for filename in FORMS + MODULES:
        shutil.copyfile(TEMPLATE_DIR / filename, os.path.join(directory, filename))
    draw_picture(os.path.join(directory, PICTURE))
    draw_icons(os.path.join(directory, IMAGES))
    pages = [name for name in FORMS if name.startswith("pg")]
    groups = [  # the Project panel: the pages in a group of their own
        {"group": "Forms", "items": [name for name in FORMS if name not in pages] +
         [{"group": "Pages", "items": pages}]},
        {"group": "Modules", "items": list(MODULES)},
    ]
    return Project(name=name, type="exe", startup=SUB_MAIN, forms=list(FORMS), groups=groups,
                   modules=list(MODULES), color_scheme="system")


def draw_icons(folder: str) -> None:
    """The ImageLists' pictures (32 x 32, shown at 16 x 16 on high-DPI
    screens), drawn here so the template ships no binaries: images/<name>.png
    for each name in ICONS."""
    ensure_app()
    os.makedirs(folder, exist_ok=True)
    for name in ICONS:
        image = QImage(32, 32, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#333333"), 1.5))
        _ICON_DRAWERS[name](painter)
        painter.end()
        image.save(os.path.join(folder, name + ".png"))


def _folder(p):
    p.setBrush(QColor("#f5c542"))
    p.drawRoundedRect(QRectF(3, 8, 26, 19), 2, 2)
    p.drawRoundedRect(QRectF(3, 5, 11, 6), 2, 2)


def _paw(p):
    p.setBrush(QColor("#8b5a2b"))
    p.drawEllipse(QRectF(9, 15, 14, 12))
    for x, y in ((5, 9), (11, 4), (18, 4), (24, 9)):
        p.drawEllipse(QRectF(x, y, 6, 7))


def _leaf(p):
    p.setBrush(QColor("#3fa34d"))
    p.drawEllipse(QRectF(6, 4, 20, 24))
    p.drawLine(QPointF(16, 6), QPointF(16, 30))


def _star(p):
    p.setBrush(QColor("#ffcc00"))
    points = []
    for i in range(10):
        radius = 14 if i % 2 == 0 else 6
        angle = math.radians(-90 + i * 36)
        points.append(QPointF(16 + radius * math.cos(angle), 17 + radius * math.sin(angle)))
    p.drawPolygon(points)


def _gear(p):
    p.setBrush(QColor("#9aa0a6"))
    for i in range(8):
        p.save()
        p.translate(16, 16)
        p.rotate(i * 45)
        p.drawRect(QRectF(-3, -15, 6, 7))
        p.restore()
    p.drawEllipse(QRectF(6, 6, 20, 20))
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QRectF(12, 12, 8, 8))


def _palette(p):
    p.setBrush(QColor("#e8d3b0"))
    p.drawEllipse(QRectF(3, 4, 26, 24))
    for x, y, color in ((9, 9, "#e53935"), (16, 7, "#43a047"), (22, 12, "#1e88e5"),
                        (9, 17, "#fdd835")):
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(x - 3, y - 3, 6, 6))


def _info(p):
    p.setBrush(QColor("#1e88e5"))
    p.drawEllipse(QRectF(3, 3, 26, 26))
    font = QFont()
    font.setPixelSize(20)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(3, 3, 26, 26), Qt.AlignCenter, "i")


def _arrow(p, direction):
    p.setBrush(QColor("#1e88e5"))
    points = [QPointF(4, 16), QPointF(16, 5), QPointF(16, 11), QPointF(28, 11),
              QPointF(28, 21), QPointF(16, 21), QPointF(16, 27)]
    if direction > 0:  # pointing right
        points = [QPointF(32 - point.x(), point.y()) for point in points]
    p.drawPolygon(points)


def _sidebar(p):
    p.setBrush(QColor("#ffffff"))
    p.drawRect(QRectF(3, 5, 26, 22))
    p.setBrush(QColor("#90caf9"))
    p.drawRect(QRectF(3, 5, 9, 22))  # the pane on the left


def _system(p):  # half light, half dark
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(QRectF(4, 4, 24, 24))
    p.setBrush(QColor("#37474f"))
    p.drawChord(QRectF(4, 4, 24, 24), 90 * 16, 180 * 16)


def _sun(p):
    p.setBrush(QColor("#ffb300"))
    p.save()
    p.setPen(QPen(QColor("#ffb300"), 2.5))  # rays that show on light and dark toolbars
    for i in range(8):
        angle = math.radians(i * 45)
        p.drawLine(QPointF(16 + 9 * math.cos(angle), 16 + 9 * math.sin(angle)),
                   QPointF(16 + 14 * math.cos(angle), 16 + 14 * math.sin(angle)))
    p.restore()
    p.drawEllipse(QRectF(9, 9, 14, 14))


def _moon(p):
    path = QPainterPath()
    path.addEllipse(QRectF(5, 4, 22, 22))
    bite = QPainterPath()
    bite.addEllipse(QRectF(12, 1, 20, 20))
    p.setBrush(QColor("#5c6bc0"))
    p.drawPath(path.subtracted(bite))


_ICON_DRAWERS = {"folder": _folder, "paw": _paw, "leaf": _leaf, "star": _star, "gear": _gear,
                 "palette": _palette, "info": _info,
                 "back": lambda p: _arrow(p, -1), "forward": lambda p: _arrow(p, 1),
                 "sidebar": _sidebar, "system": _system, "sun": _sun, "moon": _moon}


def draw_picture(path: str) -> None:
    """The PictureBox image, drawn here so the template ships no binary."""
    ensure_app()
    image = QImage(320, 240, QImage.Format_ARGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, 320, 240)
    gradient.setColorAt(0, QColor("#0a246a"))
    gradient.setColorAt(1, QColor("#3f8fd8"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(Qt.NoPen)
    for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(20 + i * 30, 18, 18, 18))
    font = QFont()
    # Text stays in the top two thirds: Form1 puts a Label over the bottom
    font.setPixelSize(88)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#ffffff"))
    painter.drawText(QRectF(0, 26, 320, 100), Qt.AlignCenter, "VP6")
    font.setPixelSize(24)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(QRectF(0, 124, 320, 34), Qt.AlignCenter, "Kitchen Sink")
    painter.end()
    image.save(path)
