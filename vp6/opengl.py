"""Drawing with OpenGL, and user interfaces in QML: ``OpenGLView`` and
``QuickView``.

* **OpenGLView** is a control drawn with OpenGL. ``InitializeGL`` fires once
  when its OpenGL context is ready, ``Resize`` when its size changes, and
  ``Paint`` whenever it must be drawn: draw there with ``GL`` (Qt's
  ``QOpenGLFunctions``: ``self.glv.GL.glClearColor(0, 0, 0.3, 1)``,
  ``glClear``, ``glViewport``...) or PyOpenGL if it is installed (``from
  OpenGL.GL import *``); ``PixelRatio`` is how many of the screen's pixels
  (OpenGL's) one of its pixels is. ``Update()`` asks for a Paint; ``Animate`` paints
  ``FrameRate`` times a second (a render loop), ``FrameCount`` and
  ``ElapsedTime`` (seconds) tell how far it got.
* **QuickView** shows a Qt Quick (QML) user interface: ``Source`` (a .qml
  file, relative to the form's folder) or ``QmlText`` (the QML itself).
  In QML, ``context`` holds the values of its ``Context``
  (``self.qml.Context["count"] = 3`` gives ``context.count``) and ``vp6``
  talks to the form: ``vp6.raiseEvent("Clicked", [x, y])`` fires
  ``QmlEvent(Name, Args)`` (the root item's own signals fire it too, with
  their arguments), ``vp6.get("txtName", "Text")`` reads a control's
  property, ``vp6.set("lblHello", "Caption", "Hi")`` sets one.
  ``ResizeMode`` (vpQmlRootToView: the root item takes the control's size;
  vpQmlViewToRoot: the other way), ``Root`` (the root item),
  ``SetProperty(Name, Value)`` / ``GetProperty(Name)`` on it, ``Errors``.
"""

from __future__ import annotations

import os
import tempfile
import time
import warnings

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ._props import P, enum_choices
from .controls import (_COMMON, CONTROL_TYPES, EVENT_ARGS, Control, _add_mouse_members,
                       _add_validation, _geometry, resolve_path)

EVENT_ARGS.update({"InitializeGL": "", "Paint": "", "QmlEvent": "Name, Args"})


def _placeholder(parent: QWidget, text: str) -> QLabel:
    label = QLabel(text, parent)
    label.setAlignment(Qt.AlignCenter)
    label.setWordWrap(True)
    label.setFrameStyle(QFrame.Box | QFrame.Plain)
    return label


# --- OpenGLView -------------------------------------------------------------------------------

def _gl_widget_class():
    try:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
    except ImportError:
        return None

    class _GLWidget(QOpenGLWidget):
        """Its initializeGL, resizeGL and paintGL are the control's events."""

        def __init__(self, parent, control: "OpenGLView"):
            super().__init__(parent)
            self._vp_control = control

        def initializeGL(self):
            self._vp_control._fire("InitializeGL")

        def resizeGL(self, width, height):
            self._vp_control._fire("Resize")

        def paintGL(self):
            control = self._vp_control
            control.__dict__["_frames"] += 1
            control._fire("Paint")

    return _GLWidget


class OpenGLView(Control):
    """A control drawn with OpenGL (the module's documentation)."""

    TypeName = "OpenGLView"
    DefaultEvent = "Paint"
    DefaultSize = (241, 181)
    Events = ("Paint", "InitializeGL", "Resize", "Click", "DblClick", "GotFocus", "LostFocus",
              "KeyDown", "KeyPress", "KeyUp", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("FrameRate", "int", 60, description="How many times a second Animate paints it"),
        P("Animate", "bool", False,
          description="Paint it again and again, FrameRate times a second (at run time)"),
        *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_frames=0, _started=time.monotonic(), _loop=None)
        widget_class = _gl_widget_class()
        no_gl = QGuiApplication.platformName() in ("offscreen", "minimal")  # (no OpenGL there)
        if self._design_mode or widget_class is None or no_gl:
            return _placeholder(parent, "OpenGLView" if self._design_mode else
                                "OpenGLView: no OpenGL here" if widget_class is not None
                                else "OpenGLView needs PySide6's QtOpenGLWidgets")
        widget = widget_class(parent, self)
        widget.setFocusPolicy(Qt.StrongFocus)
        return widget

    @property
    def GL(self):
        """Qt's OpenGL functions (QOpenGLFunctions) for its context: use them in
        InitializeGL, Resize and Paint (or after MakeCurrent)."""
        context = self._widget.context() if hasattr(self._widget, "context") else None
        return context.functions() if context is not None else None

    def MakeCurrent(self) -> None:
        """Make its OpenGL context the current one (for OpenGL calls outside its events)."""
        if hasattr(self._widget, "makeCurrent"):
            self._widget.makeCurrent()

    @property
    def PixelRatio(self) -> float:
        """The screen's pixels to one of the control's (2 on a Retina display):
        OpenGL's sizes (glViewport, glScissor) count the screen's pixels."""
        return self._widget.devicePixelRatioF()

    def Update(self) -> None:
        """Paint it again (soon)."""
        self._widget.update()

    @property
    def FrameCount(self) -> int:
        """How many times it was painted."""
        return self._frames

    @property
    def ElapsedTime(self) -> float:
        """Seconds since Animate started (or since it was made)."""
        return time.monotonic() - self._started

    def _apply_Animate(self, v):
        if self._design_mode:
            return
        loop = self._loop
        if v and loop is None:
            loop = QTimer(self._widget)
            loop.timeout.connect(self._widget.update)
            self.__dict__["_loop"] = loop
            self.__dict__["_started"] = time.monotonic()
        if loop is not None:
            loop.setInterval(max(1, round(1000 / max(1, self._values.get("FrameRate", 60)))))
            loop.start() if v else loop.stop()

    def _apply_FrameRate(self, v):
        if self._loop is not None:
            self._apply_Animate(self._values.get("Animate", False))

    def _dispose(self) -> None:
        if self._loop is not None:
            self._loop.stop()
        super()._dispose()


# --- QuickView ------------------------------------------------------------------------------------

def _python(value):
    """A value from QML (a QJSValue: a JavaScript array or object) as Python's."""
    if hasattr(value, "toVariant"):
        value = value.toVariant()
    if isinstance(value, (list, tuple)):
        return [_python(v) for v in value]
    if isinstance(value, dict):
        return {k: _python(v) for k, v in value.items()}
    return value


class _Bridge(QObject):
    """``vp6`` in QML: talks to the form."""

    def __init__(self, view: "QuickView", parent: QObject):
        super().__init__(parent)
        self._view = view

    @Slot(str)
    @Slot(str, "QVariant")
    def raiseEvent(self, name, args=None):  # noqa: N802 - (QML's name)
        self._view._fire("QmlEvent", str(name), _python(args) if args is not None else [])

    def _control(self, name: str):
        control = self._view._form.__dict__.get(str(name))
        if control is None:
            raise AttributeError(f"QuickView '{self._view.Name}': the form has no {name!r}")
        return control

    @Slot(str, str, result="QVariant")
    def get(self, name, prop):
        return getattr(self._control(name), str(prop))

    @Slot(str, str, "QVariant")
    def set(self, name, prop, value):  # noqa: A003 - (QML's name)
        setattr(self._control(name), str(prop), value)


class _Context:
    """QuickView.Context: values QML reads as ``context.<name>`` (a dict-like
    object: ``Context["count"] = 3``, ``Context["count"]``, ``"count" in
    Context``)."""

    def __init__(self, values):
        self._map = values

    def __getitem__(self, name):
        return self._map.value(str(name))

    def __setitem__(self, name, value):
        self._map.insert(str(name), value)

    def __contains__(self, name):
        return self._map.contains(str(name))

    def __iter__(self):
        return iter(self._map.keys())

    def __len__(self):
        return len(self._map.keys())


def _quick():
    """(QQuickWidget, QQmlPropertyMap) or None."""
    try:
        from PySide6.QtQml import QQmlPropertyMap
        from PySide6.QtQuickWidgets import QQuickWidget
    except ImportError:
        return None
    return QQuickWidget, QQmlPropertyMap


class QuickView(Control):
    """A Qt Quick (QML) user interface (the module's documentation)."""

    TypeName = "QuickView"
    DefaultEvent = "QmlEvent"
    DefaultSize = (241, 181)
    Events = ("QmlEvent", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp")
    Properties = (
        *_geometry(*DefaultSize),
        P("ResizeMode", "enum", 1, enum_choices("View To Root", "Root To View"),
          description="Root To View: the QML's root item takes the control's size; View To "
                      "Root: the root item keeps its own (the control doesn't follow)"),
        P("Source", "str", "", description="A .qml file (relative to the form's folder)"),
        P("QmlText", "text", "",
          description="The QML itself (used when there is no Source)"),
        *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_map=None, _temp=None, _connected=[])
        quick = _quick()
        if self._design_mode or quick is None:
            return _placeholder(parent, "QuickView (QML)" if quick is not None
                                else "QuickView needs PySide6's QtQuickWidgets")
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

            QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        widget_class, property_map = quick
        widget = widget_class(parent)
        with warnings.catch_warnings():  # (PySide's only constructor is marked deprecated)
            warnings.simplefilter("ignore", DeprecationWarning)
            values = property_map(widget)
        bridge = _Bridge(self, widget)
        context = widget.rootContext()
        context.setContextProperty("context", values)
        context.setContextProperty("vp6", bridge)
        self.__dict__.update(_map=values, _bridge_object=bridge)
        widget.statusChanged.connect(self._on_status)
        return widget

    def _apply_ResizeMode(self, v):
        if self._map is not None:
            widget_class = type(self._widget)
            self._widget.setResizeMode(widget_class.SizeRootObjectToView if v == 1
                                       else widget_class.SizeViewToRootObject)

    def _load(self) -> None:
        if self._map is None:
            return
        source = self._values.get("Source", "")
        text = self._values.get("QmlText", "")
        if source:
            url = QUrl.fromLocalFile(resolve_path(self, source))
        elif text:
            temp = self._temp
            if temp is None:  # (QML from text: a file of its own, in the form's folder's place)
                handle, temp = tempfile.mkstemp(suffix=".qml", prefix="vp6_")
                os.close(handle)
                self.__dict__["_temp"] = temp
            with open(temp, "w", encoding="utf-8") as file:
                file.write(text)
            url = QUrl.fromLocalFile(temp)
            self._widget.engine().clearComponentCache()
        else:
            return
        self._widget.setSource(url)

    def _apply_Source(self, v):
        self._load()

    _apply_QmlText = _apply_Source

    def _on_status(self, status):
        root = self._widget.rootObject()
        if root is None or root in self._connected:
            return
        self._connected.append(root)
        meta = root.metaObject()
        from PySide6.QtQuick import QQuickItem

        first = QQuickItem.staticMetaObject.methodCount()
        notifiers = {meta.property(i).notifySignalIndex() for i in range(meta.propertyCount())}
        for index in range(first, meta.methodCount()):
            method = meta.method(index)
            if method.methodType() != method.MethodType.Signal or index in notifiers:
                continue  # (a property's change signal isn't an event)
            name = bytes(method.name()).decode()
            signal = getattr(root, name, None)
            if signal is None or not hasattr(signal, "connect"):
                continue
            signal.connect(lambda *args, n=name: self._fire("QmlEvent", n, _python(list(args))))

    # -- run time ----------------------------------------------------------------------------
    @property
    def Context(self) -> _Context:
        """Values QML reads as ``context.<name>``."""
        if self._map is None:
            raise RuntimeError(f"QuickView '{self.Name}' has no QML engine (in the designer, "
                               "or without QtQuickWidgets)")
        return _Context(self._map)

    @property
    def Root(self):
        """The QML's root item (a QQuickItem), or None."""
        return self._widget.rootObject() if self._map is not None else None

    def SetProperty(self, Name: str, Value) -> None:
        """Set a property of the root item (``width``, or one the QML declares)."""
        root = self.Root
        if root is None:
            raise RuntimeError(f"QuickView '{self.Name}': no QML loaded")
        root.setProperty(str(Name), Value)

    def GetProperty(self, Name: str):
        root = self.Root
        if root is None:
            raise RuntimeError(f"QuickView '{self.Name}': no QML loaded")
        return root.property(str(Name))

    @property
    def Errors(self) -> list[str]:
        """What went wrong loading the QML (empty: nothing)."""
        if self._map is None:
            return []
        return [error.toString() for error in self._widget.errors()]

    def _dispose(self) -> None:
        self._remove_temp()
        super()._dispose()

    def _form_unloaded(self) -> None:
        self._remove_temp()

    def _remove_temp(self) -> None:
        if self._temp is not None:
            try:
                os.remove(self._temp)
            except OSError:
                pass
            self.__dict__["_temp"] = None


_TYPES = (OpenGLView, QuickView)
for _cls in _TYPES:
    _add_validation(_cls)
    _add_mouse_members(_cls)
    CONTROL_TYPES[_cls.TypeName] = _cls  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
