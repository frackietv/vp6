"""Pictures that scale, sound and video, and PDF documents: ``SvgImage``,
``MediaPlayer`` and ``PdfViewer``.

* **SvgImage** is an Image for SVG files that stays sharp at any size:
  ``Picture`` (an .svg file), ``Stretch`` (fill the control; else it takes
  the picture's own size), ``KeepAspect`` (stretched, the picture keeps its
  shape, centred). LoadPicture, PictureBox and Image read SVG files too
  (drawn sharp for the screen at their own size).
* **MediaPlayer** plays sound and video (VB's MMControl and Animation):
  ``FileName`` (a file, relative to the form's folder, or a URL), ``Play()``,
  ``Pause()``, ``Stop()``, ``Position`` and ``Duration`` (seconds),
  ``Volume`` (0 to 100), ``Mute``, ``Loop``, ``PlaybackRate``, ``AutoPlay``,
  ``State`` (vpMediaStopped, vpMediaPlaying, vpMediaPaused), ``HasVideo``;
  ``ShowControls`` puts a bar under the video (play/pause, position, time).
  Events: ``StateChange``, ``PositionChange`` (while it plays), ``Done`` (it
  reached the end), ``Error(Description)``. Invisible, it plays sound only.
* **PdfViewer** shows a PDF: ``FileName``, ``Page`` (from 1) and
  ``PageCount``, ``ZoomMode`` (vpZoomCustom with ``Zoom``, vpZoomFitWidth,
  vpZoomFitPage), ``PageMode`` (vpPageSingle, vpPageMulti: the pages one
  under the other), ``Find(Text)`` (the next place it is, highlighted; False
  when there is none), ``SelectedText`` (what Find found), ``PageText(Page)``,
  ``PrintOut()``; ``PageChange`` fires when another page is shown.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSlider, QStyle, QToolButton,
                               QVBoxLayout, QWidget)

from ._props import P, enum_choices
from .controls import (_COMMON, CONTROL_TYPES, EVENT_ARGS, Control, _add_mouse_members,
                       _add_validation, _geometry, resolve_path)

EVENT_ARGS.update({"StateChange": "", "PositionChange": "", "Done": "", "PageChange": "",
                   "Error": "Description"})

_BASIC = tuple(spec for spec in _COMMON if spec.name != "TabIndex")


def _placeholder(parent: QWidget, text: str) -> QLabel:
    """What the designer (or a missing Qt module) shows instead of the real thing."""
    label = QLabel(text, parent)
    label.setAlignment(Qt.AlignCenter)
    label.setWordWrap(True)
    label.setFrameStyle(QFrame.Box | QFrame.Plain)
    return label


# --- SvgImage --------------------------------------------------------------------------------

class _SvgWidget(QWidget):
    """Draws an SVG with QSvgRenderer, at whatever size it has."""

    def __init__(self, parent):
        super().__init__(parent)
        self.renderer = None
        self.keep_aspect = True
        self.setAttribute(Qt.WA_TranslucentBackground)

    def load(self, path: str) -> bool:
        try:
            from PySide6.QtSvg import QSvgRenderer
        except ImportError:
            self.renderer = None
            return False
        renderer = QSvgRenderer(path, self) if path else None
        self.renderer = renderer if renderer is not None and renderer.isValid() else None
        self.update()
        return self.renderer is not None

    def paintEvent(self, event):
        if self.renderer is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        area = QRectF(self.contentsRect())
        if self.keep_aspect:
            size = QSize(self.renderer.defaultSize())
            if not size.isEmpty():
                size.scale(area.size().toSize(), Qt.KeepAspectRatio)
                area = QRectF(area.center() - QPointF(size.width() / 2, size.height() / 2),
                              size.toSizeF())
        self.renderer.render(painter, area)
        painter.end()


class SvgImage(Control):
    """An Image for SVG files, sharp at any size (the module's documentation)."""

    TypeName = "SvgImage"
    DefaultSize = (97, 97)
    Events = ("Click", "DblClick", "MouseDown", "MouseMove", "MouseUp")
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("Stretch", "bool", True,
          description="True: the picture is drawn to fill the control. False: the control "
                      "takes the picture's own size"),
        P("KeepAspect", "bool", True,
          description="Stretched, the picture keeps its shape (centred) instead of filling "
                      "the control"),
        P("Picture", "file", "", description="The SVG file (relative to the form's folder)"),
        *_BASIC,
    )

    def _create_widget(self, parent):
        widget = _SvgWidget(parent)
        widget.setFocusPolicy(Qt.NoFocus)
        return widget

    def _apply_Picture(self, v):
        self._widget.load(resolve_path(self, str(v)) if v else "")
        self._fit()

    def _fit(self) -> None:
        renderer = self._widget.renderer
        if not self._values.get("Stretch", True) and renderer is not None:
            self._widget.resize(renderer.defaultSize())

    def _apply_Stretch(self, v):
        self._fit()

    def _apply_KeepAspect(self, v):
        self._widget.keep_aspect = bool(v)
        self._widget.update()

    @property
    def PictureWidth(self) -> int:
        """The picture's own width (as its file says), 0 without one."""
        renderer = self._widget.renderer
        return renderer.defaultSize().width() if renderer is not None else 0

    @property
    def PictureHeight(self) -> int:
        renderer = self._widget.renderer
        return renderer.defaultSize().height() if renderer is not None else 0


# --- MediaPlayer -----------------------------------------------------------------------------

def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}" if hours else \
        f"{rest // 60}:{rest % 60:02d}"


class _PlayerWidget(QWidget):
    """The video, and under it the bar of controls (ShowControls)."""

    def __init__(self, parent, video: QWidget):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.video = video
        layout.addWidget(video, 1)
        self.bar = QWidget(self)
        row = QHBoxLayout(self.bar)
        row.setContentsMargins(2, 0, 2, 2)
        self.play = QToolButton(self.bar)
        self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play.setAutoRaise(True)
        self.position = QSlider(Qt.Horizontal, self.bar)
        self.time = QLabel("0:00 / 0:00", self.bar)
        row.addWidget(self.play)
        row.addWidget(self.position, 1)
        row.addWidget(self.time)
        layout.addWidget(self.bar)


class MediaPlayer(Control):
    """Sound and video (the module's documentation)."""

    TypeName = "MediaPlayer"
    DefaultEvent = "Done"
    DefaultSize = (321, 241)
    Events = ("Done", "StateChange", "PositionChange", "Error", "Click", "DblClick",
              "MouseDown", "MouseMove", "MouseUp")
    EventArgs = {"Error": "Description"}
    _synthesize_click = True
    Properties = (
        *_geometry(*DefaultSize),
        P("Volume", "int", 100, description="How loud, from 0 to 100"),
        P("Mute", "bool", False, description="No sound"),
        P("Loop", "bool", False, description="Start again at the end, until stopped"),
        P("PlaybackRate", "number", 1,
          description="How fast it plays: 1 is normal, 2 twice as fast, 0.5 half"),
        P("ShowControls", "bool", True,
          description="A bar under the video: play/pause, the position and the time"),
        P("AutoPlay", "bool", False, description="Play as soon as FileName is set"),
        P("FileName", "str", "",
          description="What it plays: a sound or video file (relative to the form's folder), "
                      "or a URL"),
        *_BASIC,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_player=None, _audio=None, _seeking=False)
        if self._design_mode:
            return _placeholder(parent, "▶  MediaPlayer")
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PySide6.QtMultimediaWidgets import QVideoWidget
        except ImportError:
            return _placeholder(parent, "MediaPlayer needs PySide6's QtMultimedia")
        video = QVideoWidget()
        widget = _PlayerWidget(parent, video)
        player = QMediaPlayer(widget)
        audio = QAudioOutput(widget)
        player.setAudioOutput(audio)
        player.setVideoOutput(video)
        self.__dict__.update(_player=player, _audio=audio)
        player.playbackStateChanged.connect(self._on_state)
        player.positionChanged.connect(self._on_position)
        player.durationChanged.connect(self._on_position)
        player.mediaStatusChanged.connect(self._on_status)
        player.errorOccurred.connect(lambda _error, text: self._fire("Error", text))
        widget.play.clicked.connect(self._toggle)
        widget.position.sliderMoved.connect(lambda ms: player.setPosition(int(ms)))
        return widget

    def _event_targets(self):
        widget = self._widget
        return [widget] + ([widget.video] if isinstance(widget, _PlayerWidget) else [])

    # -- events -----------------------------------------------------------------------------
    def _on_state(self, _state):
        widget = self._widget
        if isinstance(widget, _PlayerWidget):
            widget.play.setIcon(widget.style().standardIcon(
                QStyle.SP_MediaPause if self.State == 1 else QStyle.SP_MediaPlay))
        self._fire("StateChange")

    def _on_position(self, *_):
        player, widget = self._player, self._widget
        widget.position.setRange(0, max(0, player.duration()))
        if not widget.position.isSliderDown():
            widget.position.setValue(player.position())
        widget.time.setText(f"{_clock(player.position() / 1000)} / "
                            f"{_clock(player.duration() / 1000)}")
        if self.State == 1:
            self._fire("PositionChange")

    def _on_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer

        if status == QMediaPlayer.EndOfMedia:
            self._fire("Done")

    def _toggle(self):
        self.Pause() if self.State == 1 else self.Play()

    # -- playing ------------------------------------------------------------------------------
    def Play(self) -> None:
        if self._player is not None:
            self._player.play()

    def Pause(self) -> None:
        if self._player is not None:
            self._player.pause()

    def Stop(self) -> None:
        if self._player is not None:
            self._player.stop()

    @property
    def State(self) -> int:
        """vpMediaStopped, vpMediaPlaying or vpMediaPaused."""
        if self._player is None:
            return 0
        from PySide6.QtMultimedia import QMediaPlayer

        return {QMediaPlayer.PlayingState: 1, QMediaPlayer.PausedState: 2}.get(
            self._player.playbackState(), 0)

    @property
    def Position(self) -> float:
        """Where it is, in seconds; set it to go there."""
        return self._player.position() / 1000 if self._player is not None else 0.0

    @Position.setter
    def Position(self, value):
        if self._player is not None:
            self._player.setPosition(int(float(value) * 1000))

    @property
    def Duration(self) -> float:
        """How long it is, in seconds (0 until it is known)."""
        return self._player.duration() / 1000 if self._player is not None else 0.0

    @property
    def HasVideo(self) -> bool:
        return self._player is not None and self._player.hasVideo()

    # -- properties --------------------------------------------------------------------------
    def _apply_FileName(self, v):
        player = self._player
        if player is None:
            return
        if not v:
            player.setSource(QUrl())
            return
        url = QUrl(v) if "://" in str(v) else QUrl.fromLocalFile(resolve_path(self, str(v)))
        player.setSource(url)
        if self._values.get("AutoPlay"):
            QTimer.singleShot(0, self._widget, self.Play)

    def _apply_Volume(self, v):
        if self._audio is not None:
            self._audio.setVolume(max(0, min(int(v), 100)) / 100)

    def _apply_Mute(self, v):
        if self._audio is not None:
            self._audio.setMuted(bool(v))

    def _apply_Loop(self, v):
        if self._player is not None:
            self._player.setLoops(-1 if v else 1)  # (QMediaPlayer.Infinite, Once)

    def _apply_PlaybackRate(self, v):
        if self._player is not None:
            self._player.setPlaybackRate(float(v))

    def _apply_ShowControls(self, v):
        if isinstance(self._widget, _PlayerWidget):
            self._widget.bar.setVisible(bool(v))

    def _dispose(self) -> None:
        self.Stop()
        super()._dispose()

    def _form_unloaded(self) -> None:
        self.Stop()


# --- PdfViewer ---------------------------------------------------------------------------------

class PdfViewer(Control):
    """Shows a PDF document (the module's documentation)."""

    TypeName = "PdfViewer"
    DefaultEvent = "PageChange"
    DefaultSize = (321, 401)
    Events = ("PageChange", "GotFocus", "LostFocus", "KeyDown", "KeyPress", "KeyUp",
              "MouseDown", "MouseMove", "MouseUp")
    Properties = (
        *_geometry(*DefaultSize),
        P("ZoomMode", "enum", 1, enum_choices("Custom", "Fit Width", "Fit Page"),
          description="How large the pages are: Zoom, as wide as the control, or a whole page "
                      "in it"),
        P("Zoom", "number", 1, description="With ZoomMode Custom: 1 = actual size"),
        P("PageMode", "enum", 1, enum_choices("Single", "Multi-page"),
          description="One page at a time, or the pages one under the other"),
        P("FileName", "str", "", description="The PDF file (relative to the form's folder)"),
        *_COMMON,
    )

    def _create_widget(self, parent):
        self.__dict__.update(_document=None, _search=None, _found="", _result=-1)
        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView
        except ImportError:
            return _placeholder(parent, "PdfViewer needs PySide6's QtPdf")
        view = QPdfView(parent)
        document = QPdfDocument(view)
        view.setDocument(document)
        self.__dict__["_document"] = document
        view.pageNavigator().currentPageChanged.connect(lambda *_: self._fire("PageChange"))
        return view

    def _event_targets(self):
        viewport = getattr(self._widget, "viewport", None)
        return [self._widget] + ([viewport()] if viewport is not None else [])

    def _apply_FileName(self, v):
        document = self._document
        if document is None:
            return
        document.close()
        self.__dict__.update(_found="", _result=-1)
        if v:
            path = resolve_path(self, str(v))
            if not os.path.isfile(path):
                raise FileNotFoundError(f"PdfViewer '{self.Name}': file not found: {path}")
            document.load(path)
        if self._search is not None:
            self._search.setDocument(document)

    def _apply_ZoomMode(self, v):
        from PySide6.QtPdfWidgets import QPdfView

        if self._document is not None:
            self._widget.setZoomMode((QPdfView.ZoomMode.Custom, QPdfView.ZoomMode.FitToWidth,
                                      QPdfView.ZoomMode.FitInView)[int(v) if 0 <= int(v) <= 2
                                                                   else 1])

    def _apply_Zoom(self, v):
        if self._document is not None:
            self._widget.setZoomFactor(max(0.05, float(v)))

    def _read_Zoom(self):
        return self._widget.zoomFactor() if self._document is not None else \
            self._values.get("Zoom", 1)

    def _apply_PageMode(self, v):
        from PySide6.QtPdfWidgets import QPdfView

        if self._document is not None:
            self._widget.setPageMode(QPdfView.PageMode.MultiPage if v == 1
                                     else QPdfView.PageMode.SinglePage)

    @property
    def PageCount(self) -> int:
        return self._document.pageCount() if self._document is not None else 0

    @property
    def Page(self) -> int:
        """The page shown (from 1; 0 without a document); set it to go there."""
        if self._document is None or not self.PageCount:
            return 0
        return self._widget.pageNavigator().currentPage() + 1

    @Page.setter
    def Page(self, value):
        if self._document is None or not self.PageCount:
            return
        page = max(1, min(int(value), self.PageCount)) - 1
        self._widget.pageNavigator().jump(page, QPointF(), self._widget.zoomFactor())

    def PageText(self, Page: int) -> str:
        """All the text on a page (from 1)."""
        if self._document is None or not 1 <= int(Page) <= self.PageCount:
            return ""
        return self._document.getAllText(int(Page) - 1).text()

    def Find(self, Text: str) -> bool:
        """Go to the next place Text is (any case; from the start after a new
        Text), its page shown and the matches highlighted; False when there is
        none."""
        if self._document is None or not Text or not self.PageCount:
            self.__dict__["_found"] = ""
            return False
        from PySide6.QtPdf import QPdfSearchModel

        if self._search is None:  # (highlights the matches, as it finds them)
            search = QPdfSearchModel(self._widget)
            search.setDocument(self._document)
            self._widget.setSearchModel(search)
            self.__dict__["_search"] = search
        text = str(Text)
        if self._search.searchString() != text:
            self._search.setSearchString(text)
            self.__dict__["_result"] = (-1, -1)
        page, offset = self._result if isinstance(self._result, tuple) else (-1, -1)
        wanted = text.casefold()
        count = self.PageCount
        for step in range(count + 1):
            number = (max(page, 0) + step) % count
            content = self._document.getAllText(number).text().casefold()
            start = offset + 1 if step == 0 and number == page else 0
            found = content.find(wanted, start)
            if found >= 0:
                self.__dict__["_result"] = (number, found)
                self.__dict__["_found"] = self._document.getAllText(number).text()[
                    found:found + len(text)]
                self._widget.pageNavigator().jump(number, QPointF(), self._widget.zoomFactor())
                return True
        self.__dict__["_found"] = ""
        return False

    @property
    def SelectedText(self) -> str:
        """The text Find found ("" if none)."""
        return self._found

    def PrintOut(self) -> None:
        """Print every page on the Printer (as large as fits) and end the document."""
        if self._document is None or not self.PageCount:
            return
        from .picture import Picture
        from .printer import Printer

        for page in range(self.PageCount):
            if page:
                Printer.NewPage()
            points = self._document.pagePointSize(page)
            scale = 2.0  # (144 dots per inch: sharp enough on paper)
            image = self._document.render(page, QSize(int(points.width() * scale),
                                                      int(points.height() * scale)))
            picture = Picture(_image=image)
            width = Printer.ScaleX(picture.Width, 3)
            height = Printer.ScaleY(picture.Height, 3)
            fit = min(Printer.ScaleWidth / max(width, 1e-9),
                      Printer.ScaleHeight / max(height, 1e-9))
            Printer.PaintPicture(picture, 0, 0, width * fit, height * fit)
        Printer.EndDoc()


_TYPES = (SvgImage, MediaPlayer, PdfViewer)
for _cls in _TYPES:
    _add_validation(_cls)
    _add_mouse_members(_cls)
    CONTROL_TYPES[_cls.TypeName] = _cls  # (the Toolbox: after the other controls)
CONTROL_TYPES["Menu"] = CONTROL_TYPES.pop("Menu")
