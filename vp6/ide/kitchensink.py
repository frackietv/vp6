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

import os
import shutil
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

from ..app import ensure_app
from ..project import SUB_MAIN, Project

TEMPLATE_DIR = Path(__file__).parent / "templates" / "kitchensink"
FORMS = (  # the window, its pages (in the index's order) and the modal dialog
    "Form1.py", "pgIntro.py", "pgText.py", "pgButtons.py", "pgLists.py", "pgScrollBars.py",
    "pgValues.py", "pgPictures.py", "pgZOrder.py", "pgTree.py", "pgTimer.py", "pgLayout.py",
    "pgScrolling.py", "pgEmbedded.py", "pgDialogs.py", "pgSchemes.py", "pgKeyboard.py",
    "pgMouse.py", "pgArrays.py", "pgMenus.py", "pgGlobals.py", "frmDialog.py",
)
MODULES = ("Module1.py",)
PICTURE = "vp6.png"  # shown on the Pictures page


def create(directory: str, name: str) -> Project:
    """Copy the Kitchen Sink sources into ``directory`` and return its project
    (not saved yet)."""
    for filename in FORMS + MODULES:
        shutil.copyfile(TEMPLATE_DIR / filename, os.path.join(directory, filename))
    draw_picture(os.path.join(directory, PICTURE))
    pages = [name for name in FORMS if name.startswith("pg")]
    groups = [  # the Project panel: the pages in a group of their own
        {"group": "Forms", "items": [name for name in FORMS if name not in pages] +
         [{"group": "Pages", "items": pages}]},
        {"group": "Modules", "items": list(MODULES)},
    ]
    return Project(name=name, type="exe", startup=SUB_MAIN, forms=list(FORMS), groups=groups,
                   modules=list(MODULES), color_scheme="system")


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
