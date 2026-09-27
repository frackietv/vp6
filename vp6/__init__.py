"""VP6 - VB6-style GUI programming for Python.

    from vp6 import *
"""

from .appearance import (vpSchemeDark, vpSchemeIDE, vpSchemeLight, vpSchemeProjectDefault,
                         vpSchemeSystem)
from .app import App, Beep, Clipboard, Debug, DoEvents, End, Screen
from .colors import (RGB, QBColor, vpBlack, vpBlue, vpCyan, vpGreen, vpMagenta, vpRed,
                     vpWhite, vpYellow)
from .constants import *  # noqa: F403
from .constants import __all__ as _constants_all
from .controls import (CheckBox, ComboBox, CommandButton, Control, ControlArray, Frame,
                       HScrollBar, Image, Label, Line, ListBox, Menu, Node, OptionButton,
                       Panel, PictureBox, ProgressBar, Slider, Splitter, StatusBar, TextBox,
                       Timer, TreeView, UpDown, VScrollBar)
from .dialogs import InputBox, MsgBox
from .form import Form, Forms, Load, Unload, run

__version__ = "0.3.30"

__all__ = [
    "App", "Beep", "Clipboard", "Debug", "DoEvents", "End", "Screen",
    "RGB", "QBColor", "vpBlack", "vpBlue", "vpCyan", "vpGreen", "vpMagenta", "vpRed",
    "vpWhite", "vpYellow",
    "CheckBox", "ComboBox", "CommandButton", "Control", "ControlArray", "Frame", "HScrollBar",
    "Image", "Label", "Line", "ListBox", "Menu", "Node", "OptionButton", "PictureBox",
    "Panel", "ProgressBar", "Slider", "Splitter", "StatusBar", "TextBox", "Timer", "TreeView",
    "UpDown", "VScrollBar",
    "InputBox", "MsgBox",
    "Form", "Forms", "Load", "Unload", "run",
    "vpSchemeProjectDefault", "vpSchemeSystem", "vpSchemeLight", "vpSchemeDark", "vpSchemeIDE",
    *_constants_all,
]
