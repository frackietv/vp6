"""VP6 - VB6-style GUI programming for Python.

    from vp6 import *
"""

from .appearance import (vpSchemeDark, vpSchemeIDE, vpSchemeLight, vpSchemeProjectDefault,
                         vpSchemeSystem)
from .app import (App, Beep, Clipboard, Command, Debug, DeleteSetting, DoEvents, End,
                  GetAllSettings, GetSetting, MoveToTrash, SaveSetting, Screen, SendKeys,
                  ShowHelp)
from .colors import (RGB, RGBA, QBColor, vpBlack, vpBlue, vpCyan, vpGreen, vpMagenta, vpRed,
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
from .dialogs import InputBox, InputNumber, MsgBox, ProgressBox, ShowError
from .form import Form, Forms, Load, Unload, run
from .mdi import MDIForm
from .wizard import WizardForm
from .process import Process, Shell, ShellExecute
from .winsock import Winsock
from .filewatcher import FileWatcher
from .terminal import Terminal
from .markdown import MarkdownBox
from .data import CreateDatabase, Data, Database, Field, OpenDatabase, Recordset
from .inputs import DTPicker, Dial, FontComboBox, HotKey, LCDNumber, MonthView, SpinBox
from .buttons import ButtonBox, CommandLink, ToolButton
from .containers import PageFrame, ScrollPanel, ToolBox
from .views import ColumnView, UndoStack, UndoView
from .dbgrid import DBGrid
from .graphicsview import GraphicsView
from .chart import Chart
from .graph import Graph, GraphItem
from .media import MediaPlayer, PdfViewer, SvgImage
from .opengl import OpenGLView, QuickView
from .designerview import DesignerView
from .drawing import GraphicsPath, LinearGradient
from .metadata import ControlCategories, ControlInfo, ControlTypes
from .picture import FileIcon, LoadPicture, Picture, SavePicture
from .printer import Printer, Printers
from .usercontrol import Property, UserControl

__version__ = "0.4.71"

__all__ = [
    "App", "Beep", "Clipboard", "Command", "Debug", "DeleteSetting", "DoEvents", "End",
    "GetAllSettings", "GetSetting", "MoveToTrash", "SaveSetting", "Screen", "SendKeys",
    "ShowHelp", "FileIcon", "LoadPicture", "Picture", "SavePicture", "Printer", "Printers", "MDIForm",
    "WizardForm",
    "Process", "Shell", "ShellExecute", "Winsock", "FileWatcher", "DesignerView",
    "ControlTypes", "ControlInfo", "ControlCategories", "GraphicsPath", "LinearGradient",
    "Terminal", "MarkdownBox",
    "Data", "Database", "Recordset", "Field", "OpenDatabase", "CreateDatabase",
    "SpinBox", "DTPicker", "MonthView", "Dial", "LCDNumber", "FontComboBox", "HotKey",
    "CommandLink", "ToolButton", "ButtonBox", "ToolBox", "PageFrame", "ScrollPanel",
    "ColumnView", "UndoView", "UndoStack", "DBGrid", "GraphicsView", "Chart", "Graph", "GraphItem",
    "SvgImage", "MediaPlayer", "PdfViewer", "OpenGLView", "QuickView",
    "RGB", "RGBA", "QBColor", "vpBlack", "vpBlue", "vpCyan", "vpGreen", "vpMagenta", "vpRed",
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
    "InputBox", "InputNumber", "MsgBox", "ProgressBox", "ShowError",
    "Form", "Forms", "Load", "Unload", "run",
    "vpSchemeProjectDefault", "vpSchemeSystem", "vpSchemeLight", "vpSchemeDark", "vpSchemeIDE",
    *_constants_all,
]
