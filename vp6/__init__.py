"""VP6 - VB6-style GUI programming for Python.

    from vp6 import *
"""

from .appearance import (vpSchemeDark, vpSchemeIDE, vpSchemeLight, vpSchemeProjectDefault,
                         vpSchemeSystem)
from .app import (App, Beep, Clipboard, Command, Debug, DeleteSetting, DoEvents, End,
                  GetAllSettings, GetSetting, SaveSetting, Screen, SendKeys)
from .colors import (RGB, QBColor, vpBlack, vpBlue, vpCyan, vpGreen, vpMagenta, vpRed,
                     vpWhite, vpYellow)
from .constants import *  # noqa: F403
from .constants import __all__ as _constants_all
from .controls import (Button, CheckBox, CodeBox, ColumnHeader, ComboBox, CommandButton,
                       CommonDialog, Control, ControlArray, DialogCancelled, DirListBox, DockPanel,
                       DriveListBox, FileListBox, FlexGrid, Frame, HScrollBar, Image, ImageList,
                       Label, Line, ListBox, ListImage, ListItem, ListView, Menu, Node,
                       OptionButton, Panel, PictureBox, ProgressBar, RichTextBox, Shape, Slider,
                       Splitter, StatusBar, Tab, TabStrip, TextBox, Timer, Toolbar, TreeView,
                       UpDown, VScrollBar, WebBrowser, WebView)
from .dialogs import InputBox, MsgBox
from .form import Form, Forms, Load, Unload, run
from .usercontrol import Property, UserControl

__version__ = "0.4.24"

__all__ = [
    "App", "Beep", "Clipboard", "Command", "Debug", "DeleteSetting", "DoEvents", "End",
    "GetAllSettings", "GetSetting", "SaveSetting", "Screen", "SendKeys",
    "RGB", "QBColor", "vpBlack", "vpBlue", "vpCyan", "vpGreen", "vpMagenta", "vpRed",
    "vpWhite", "vpYellow",
    "Button", "CheckBox", "CodeBox", "ColumnHeader", "CommonDialog", "DialogCancelled", "ComboBox",
    "CommandButton", "Control",
    "ControlArray", "DirListBox", "DockPanel", "DriveListBox", "FlexGrid",
    "FileListBox", "Frame", "HScrollBar",
    "Image", "ImageList", "Label", "Line", "ListBox", "ListImage", "ListItem", "ListView",
    "Menu", "Node",
    "OptionButton", "PictureBox",
    "Panel", "ProgressBar", "RichTextBox", "Shape", "Slider", "Splitter", "StatusBar", "Tab",
    "TabStrip", "TextBox",
    "Timer", "Toolbar", "TreeView", "UpDown", "UserControl", "Property", "VScrollBar",
    "WebBrowser", "WebView",
    "InputBox", "MsgBox",
    "Form", "Forms", "Load", "Unload", "run",
    "vpSchemeProjectDefault", "vpSchemeSystem", "vpSchemeLight", "vpSchemeDark", "vpSchemeIDE",
    *_constants_all,
]
