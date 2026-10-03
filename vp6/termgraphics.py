"""Pictures in the Terminal: the Kitty graphics protocol, iTerm2's inline
images and sixel graphics. ``TerminalGraphics`` keeps a screen's images (by id, and the number
a program may give one instead) and their placements on its cells.

The Kitty graphics protocol: a program sends an APC string, ``ESC _ G keys ;
payload ESC \\``: the keys (``a=T,f=100,i=1...``) say what to do, the payload
is base64:

* transmitting (``a=t``, ``a=T`` to show it too, ``a=q`` to only check it):
  PNG (``f=100``), RGBA (32, the default) or RGB (24) pixels of ``s`` x
  ``v``, zlib-compressed (``o=z``), in the payload (``t=d``, in chunks with
  ``m=1``) or in a file (``t=f``; ``t=t``: a temporary file, deleted once
  read; ``S`` bytes from offset ``O``); shared memory (``t=s``) isn't
  supported;
* placing (``a=p``): at the cursor, part of the image (``x``, ``y``, ``w``,
  ``h``), ``X``/``Y`` pixels into the cell, scaled to ``c`` columns and
  ``r`` rows (one of them: keeping its shape), ``z`` (below zero: under the
  text; below -1073741824: under the cells' backgrounds too), ``p`` (a
  placement id: placing it again moves it), ``C=1`` (the cursor stays);
  else the cursor goes to the right of the image, on its last row;
* deleting (``a=d``, ``d=``): all of them, by id, by number, at the cursor,
  at a cell, in a column, a row, a z-index, a range of ids; capital letters
  free the images too;
* answering (unless ``q=1``: not OKs; ``q=2``: nothing): ``ESC _ G i=id ;
  OK ESC \\`` or an error (``ENOENT:...``), when the program gave an id or a
  number.

iTerm2's inline images: an OSC string, ``ESC ] 1337 ; File = args : base64
BEL`` (or ST), the file a picture Qt reads (PNG, JPEG, GIF, BMP...). With
``inline=1`` it shows at the cursor (else it's a download: left out),
``width`` and ``height`` in cells (``N``), pixels (``Npx``), percent of the
screen (``N%``) or ``auto``, ``preserveAspectRatio=0`` to stretch it; the
cursor goes to the right of it on its last row (unless ``doNotMoveCursor=1``).
A large one comes in parts: ``MultipartFile=args``, ``FilePart=base64``...,
``FileEnd``. ``ReportCellSize`` is answered with a cell's height and width in
points, and the scale. Its pictures have no ids: one is forgotten once its
placement has gone.

Sixel graphics (the VT340's, as xterm has them): a DCS string, ``ESC P P1 ;
P2 ; P3 q data ESC \\``. ``P1`` gives the pixels' shape (0, 1, 5, 6: twice
as tall as wide; 2: five times; 3, 4: three times; 7, 8, 9: square) unless
the raster attributes (``"Pan;Pad;Ph;Pv``) do; ``P2=1`` leaves the pixels
not drawn transparent (else they are the terminal's background); the picture
is at least the raster attributes' width and height. In the data, ``#c`` picks color
register ``c`` (1024 of them, starting as the VT340's 16 colors: private to
each picture while mode 1070 is set, as it starts, else shared), ``#c;2;r;g;b``
sets it (percents) and ``#c;1;h;l;s`` too (HLS, the VT340's hue: 0 is
blue); each of ``?`` to ``~`` draws a column of six pixels (its bits, the
lowest at the top) in that color, ``!n`` repeats the next one ``n`` times,
``$`` goes back to the band's left and ``-`` down to the next band. Before
any color is picked it draws in the terminal's foreground. One pixel is a
device pixel. The picture goes at the cursor, which then goes to the line
below it at the same column (or, with mode 8452 set, to its right on its last
row); with mode 80 (DECSDM) set it goes at the screen's top left instead,
cut to the screen, and the cursor stays. Its pictures are anonymous, like
iTerm2's.

Placements are on lines counted from the first one the screen ever had
(``AnsiScreen.scrolled`` lines have gone into its history), so they scroll
with the text, into the history too. Sizes are in device pixels: the screen's
``cell_pixels`` (the Terminal sets it from its font) gives a cell's.
"""

from __future__ import annotations

import base64
import binascii
import math
import os
import re
import tempfile
import zlib
from array import array
from dataclasses import dataclass

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QImage

QUOTA = 320 * 1024 * 1024  # bytes of pixels a screen keeps (older pictures go first)
MAX_SIDE = 10000  # pixels
UNDER_BACKGROUNDS = -1073741824  # (a z-index below this: under the cells' backgrounds)
_FORMATS = {24: (3, QImage.Format_RGB888), 32: (4, QImage.Format_RGBA8888)}

SIXEL_REGISTERS = 1024  # (the color registers a sixel picture has)
# The VT340's 16 colors (percents of red, green and blue): the sixel registers as they start
_VT340_COLORS = ((0, 0, 0), (20, 20, 80), (80, 13, 13), (20, 80, 20), (80, 20, 80),
                 (20, 80, 80), (80, 80, 20), (53, 53, 53), (26, 26, 26), (33, 33, 60),
                 (60, 26, 26), (33, 60, 33), (60, 33, 60), (33, 60, 60), (60, 60, 33),
                 (80, 80, 80))
# The pixels' shape (how many times as tall as wide) by a sixel string's P1
_SIXEL_ASPECT = {0: 2, 1: 2, 2: 5, 3: 3, 4: 3, 5: 2, 6: 2, 7: 1, 8: 1, 9: 1}
# Sixel data: sixels, #color, !repeat, "raster attributes, $ (back to the left), - (down)
_SIXEL_TOKENS = re.compile(r'([?-~]+)|#([0-9;]*)|!([0-9]*)([?-~])|"([0-9;]*)|([$-])')
_SIXEL_BITS = [tuple(bit for bit in range(6) if value >> bit & 1) for value in range(64)]


class GraphicsError(Exception):
    """An error the program is told about: "ENOENT:No image with id 3"..."""


@dataclass
class TerminalImage:
    id: int
    number: int  # (the I the program gave it: 0 none)
    image: QImage
    order: int  # (when it came: the oldest go first when there are too many)
    anonymous: bool = False  # (iTerm2's: forgotten once no longer placed)

    @property
    def size(self) -> int:
        return self.image.sizeInBytes()


@dataclass
class Placement:
    """An image shown on the screen: its top left cell (``line``: counted from
    the screen's first line ever), the cells it covers, the part of the image
    it shows (``source``), drawn ``width`` x ``height`` device pixels from
    ``offset`` pixels into its first cell."""
    image: int
    id: int
    line: int
    col: int
    cols: int
    rows: int
    source: QRect
    width: float
    height: float
    offset: tuple[int, int] = (0, 0)
    z: int = 0


class TerminalGraphics:
    """A screen's images and placements (the module's documentation)."""

    def __init__(self, screen):
        self.screen = screen
        self.images: dict[int, TerminalImage] = {}
        self.placements: list[Placement] = []
        self._loading = None  # (the keys and payload so far, while chunks come: m=1)
        self._multipart = None  # (iTerm2's: the args and parts so far)
        self._order = 0
        self._next_id = 1 << 31  # (ids it gives pictures: above the programs' usual ones)

    # -- the Kitty graphics protocol's commands ----------------------------------------------
    def kitty(self, text: str) -> None:
        """An APC string's text (after ``ESC _``): ``G`` and a command."""
        if not text.startswith("G"):
            return
        control, _, payload = text[1:].partition(";")
        keys = {}
        for item in control.split(","):
            key, _, value = item.partition("=")
            if key:
                keys[key] = value
        if self._loading is not None:  # (a chunk: the first one's keys hold)
            first, parts = self._loading
            parts.append(payload)
            if sum(map(len, parts)) > QUOTA * 4 // 3:
                self._loading = None
                self._answer(first, "EFBIG:Too much data")
                return
            if keys.get("m") == "1":
                return
            self._loading = None
            keys, payload = first, "".join(parts)
        elif keys.get("m") == "1" and keys.get("a", "t") in ("t", "T", "q"):
            self._loading = (keys, [payload])
            return
        try:
            self._run(keys, payload)
        except GraphicsError as error:
            self._answer(keys, str(error))

    def _run(self, keys: dict, payload: str) -> None:
        action = keys.get("a", "t")
        if "i" in keys and "I" in keys and action != "d":
            raise GraphicsError("EINVAL:Both an id and a number")
        if action == "d":
            self._delete(keys)
            return
        if action in ("t", "T", "q"):
            image = self._image_from(keys, payload)
            if action == "q":  # (only checked: nothing kept)
                self._answer(keys, "OK")
                return
            stored = self._store(keys, image)
            if action == "T":
                self._place(stored, keys)
            self._answer(keys, "OK", stored.id)
        elif action == "p":
            stored = self._find(keys)
            self._place(stored, keys)
            self._answer(keys, "OK", stored.id)
        else:  # (animation: f, a, c)
            raise GraphicsError("EINVAL:Animation isn't supported")

    @staticmethod
    def _number(keys: dict, key: str, default: int = 0) -> int:
        try:
            return int(keys.get(key, default))
        except ValueError:
            raise GraphicsError(f"EINVAL:{key} isn't a number") from None

    def _answer(self, keys: dict, message: str, image_id: int | None = None) -> None:
        """Tell the program (only when it gave an id or a number, and as quietly
        as it asked)."""
        quiet = keys.get("q", "0")
        if (message == "OK" and quiet in ("1", "2")) or quiet == "2":
            return
        if "i" not in keys and "I" not in keys:
            return
        number = keys.get("I")
        parts = [f"i={image_id if image_id is not None and number else keys.get('i', 0)}"]
        if number:
            parts.append(f"I={number}")
        if keys.get("p", "0") != "0":
            parts.append(f"p={keys['p']}")
        self.screen._reply(f"\x1b_G{','.join(parts)};{message}\x1b\\")

    # -- transmitting ------------------------------------------------------------------------
    def _image_from(self, keys: dict, payload: str) -> QImage:
        try:
            data = base64.b64decode(payload + "=" * (-len(payload) % 4), validate=False)
        except (binascii.Error, ValueError):
            raise GraphicsError("EINVAL:The payload isn't base64") from None
        medium = keys.get("t", "d")
        if medium in ("f", "t"):
            data = self._read_file(data.decode("utf-8", "replace"), keys, medium == "t")
        elif medium != "d":
            raise GraphicsError("EINVAL:Shared memory isn't supported")
        if keys.get("o") == "z":
            try:
                data = zlib.decompress(data)
            except zlib.error:
                raise GraphicsError("EINVAL:The data isn't zlib's") from None
        kind = self._number(keys, "f", 32)
        if kind == 100:
            image = QImage.fromData(data)
            if image.isNull():
                raise GraphicsError("EBADPNG:Not a PNG picture")
        elif kind in _FORMATS:
            width, height = self._number(keys, "s"), self._number(keys, "v")
            if not (0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE):
                raise GraphicsError("EINVAL:The width (s) and height (v) are needed")
            depth, qformat = _FORMATS[kind]
            if len(data) < width * height * depth:
                raise GraphicsError("ENODATA:Too little data for the size")
            image = QImage(data, width, height, width * depth, qformat).copy()
        else:
            raise GraphicsError(f"EINVAL:Unknown format {kind}")
        if image.width() > MAX_SIDE or image.height() > MAX_SIDE:
            raise GraphicsError("EFBIG:The picture is too big")
        return image.convertToFormat(QImage.Format_ARGB32_Premultiplied)

    def _read_file(self, path: str, keys: dict, temporary: bool) -> bytes:
        size, offset = self._number(keys, "S"), self._number(keys, "O")
        try:
            with open(path, "rb") as file:
                file.seek(offset)
                data = file.read(size if size > 0 else QUOTA)
        except OSError as error:
            raise GraphicsError(f"EBADF:{error.strerror or error}") from None
        finally:  # (a temporary file the program left for it: gone, once read)
            if temporary and "tty-graphics-protocol" in path and os.path.realpath(
                    path).startswith(os.path.realpath(tempfile.gettempdir()) + os.sep):
                try:
                    os.remove(path)
                except OSError:
                    pass
        return data

    def _store(self, keys: dict, image: QImage) -> TerminalImage:
        image_id, number = self._number(keys, "i"), self._number(keys, "I")
        if image_id:
            self._forget(image_id)  # (the same id again: a new picture, and not shown)
        else:
            image_id = self._new_id()
        return self._keep(TerminalImage(image_id, number, image, 0))

    def _keep(self, stored: TerminalImage) -> TerminalImage:
        self._drop_unplaced()
        self._order += 1
        stored.order = self._order
        self.images[stored.id] = stored
        self._within_quota()
        return stored

    def _drop_unplaced(self) -> None:
        """iTerm2's pictures no longer placed (no program can show them again)."""
        shown = {placement.image for placement in self.placements}
        for image_id in [image.id for image in self.images.values()
                         if image.anonymous and image.id not in shown]:
            del self.images[image_id]

    def _new_id(self) -> int:
        while self._next_id in self.images:
            self._next_id += 1
        self._next_id += 1
        return self._next_id - 1

    def _within_quota(self) -> None:
        def total():
            return sum(image.size for image in self.images.values())

        shown = {placement.image for placement in self.placements}
        for keep_shown in (True, False):  # (the hidden ones first)
            for image in sorted(self.images.values(), key=lambda image: image.order)[:-1]:
                if total() <= QUOTA:
                    return
                if not (keep_shown and image.id in shown):
                    self._forget(image.id)

    def _forget(self, image_id: int) -> None:
        self.images.pop(image_id, None)
        self.placements = [p for p in self.placements if p.image != image_id]

    def _find(self, keys: dict) -> TerminalImage:
        if "I" in keys:
            number = self._number(keys, "I")
            found = [image for image in self.images.values() if image.number == number]
            if not found:
                raise GraphicsError(f"ENOENT:No image with number {number}")
            return max(found, key=lambda image: image.order)  # (the newest)
        image_id = self._number(keys, "i")
        if image_id not in self.images:
            raise GraphicsError(f"ENOENT:No image with id {image_id}")
        return self.images[image_id]

    # -- placing -----------------------------------------------------------------------------
    def _place(self, stored: TerminalImage, keys: dict) -> None:
        if keys.get("U") == "1":  # (a virtual placement, for Unicode placeholders: not drawn)
            return
        screen = self.screen
        cell_width, cell_height = screen.cell_pixels
        image = stored.image
        x = max(0, min(image.width(), self._number(keys, "x")))
        y = max(0, min(image.height(), self._number(keys, "y")))
        source = QRect(x, y, self._number(keys, "w") or image.width() - x,
                       self._number(keys, "h") or image.height() - y)
        source = source.intersected(image.rect())
        if source.isEmpty():
            raise GraphicsError("EINVAL:The part of the picture to show is empty")
        cols, rows = max(0, self._number(keys, "c")), max(0, self._number(keys, "r"))
        offset = (max(0, min(cell_width - 1, self._number(keys, "X"))),
                  max(0, min(cell_height - 1, self._number(keys, "Y"))))
        if cols and rows:
            width, height = cols * cell_width - offset[0], rows * cell_height - offset[1]
        elif cols:
            width = cols * cell_width - offset[0]
            height = source.height() * width / source.width()
        elif rows:
            height = rows * cell_height - offset[1]
            width = source.width() * height / source.height()
        else:
            width, height = source.width(), source.height()
        cols = cols or max(1, math.ceil((offset[0] + width) / cell_width))
        rows = rows or max(1, math.ceil((offset[1] + height) / cell_height))
        placement_id = self._number(keys, "p")
        if placement_id:  # (placed again: moved)
            self.placements = [p for p in self.placements
                               if not (p.image == stored.id and p.id == placement_id)]
        self._put(Placement(stored.id, placement_id, 0, 0, cols, rows, source, width, height,
                            offset, self._number(keys, "z")), keys.get("C") != "1")

    def _put(self, placement: Placement, move_cursor: bool) -> None:
        """A placement at the cursor; the cursor then to the right of it, on its
        last row."""
        screen = self.screen
        placement.line, placement.col = screen.scrolled + screen.row, screen.col
        self.placements.append(placement)
        if move_cursor:
            for _ in range(placement.rows - 1):
                screen._line_feed()
            screen.col = min(screen.cols - 1, screen.col + placement.cols)
            screen.wrap_pending = False

    # -- iTerm2's inline images (OSC 1337) ----------------------------------------------------
    def iterm2(self, text: str) -> None:
        """An OSC 1337 string's text after ``1337;``."""
        command, _, rest = text.partition("=")
        if text == "ReportCellSize":
            scale = self.screen.pixel_ratio
            width, height = (size / scale for size in self.screen.cell_pixels)
            self.screen._reply(f"\x1b]1337;ReportCellSize={height:g};{width:g};{scale:g}\x1b\\")
        elif command == "File":
            args, _, data = rest.partition(":")
            self._iterm2_file(args, data)
        elif command == "MultipartFile":
            self._multipart = (rest, [])
        elif command == "FilePart" and self._multipart is not None:
            parts = self._multipart[1]
            parts.append(rest)
            if sum(map(len, parts)) > QUOTA:
                self._multipart = None
        elif text == "FileEnd" and self._multipart is not None:
            args, parts = self._multipart
            self._multipart = None
            self._iterm2_file(args, "".join(parts))

    def _iterm2_file(self, args: str, data: str) -> None:
        keys = {}
        for item in args.split(";"):
            key, _, value = item.partition("=")
            keys[key.strip()] = value.strip()
        if keys.get("inline") != "1":  # (a file to download: not shown)
            return
        try:
            image = QImage.fromData(base64.b64decode(data + "=" * (-len(data) % 4)))
        except (binascii.Error, ValueError):
            return
        if image.isNull() or image.width() > MAX_SIDE or image.height() > MAX_SIDE:
            return
        image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        stored = self._keep(TerminalImage(self._new_id(), 0, image, 0, anonymous=True))
        width, height = self._iterm2_size(image, keys)
        cell_width, cell_height = self.screen.cell_pixels
        self._put(Placement(stored.id, 0, 0, 0, max(1, math.ceil(width / cell_width)),
                            max(1, math.ceil(height / cell_height)), image.rect(), width,
                            height), keys.get("doNotMoveCursor") != "1")

    def _iterm2_size(self, image: QImage, keys: dict) -> tuple[float, float]:
        """The size to draw it, in device pixels: from width and height (cells,
        px, %, auto), its shape kept unless preserveAspectRatio=0; auto: its
        own size, but no wider than the screen."""
        screen = self.screen
        cell_width, cell_height = screen.cell_pixels
        whole_width, whole_height = screen.cols * cell_width, screen.rows * cell_height

        def length(spec: str, cell: int, whole: int):
            try:
                if spec.endswith("px"):
                    return max(1.0, float(spec[:-2]))
                if spec.endswith("%"):
                    return max(1.0, float(spec[:-1]) * whole / 100)
                return max(1.0, float(spec) * cell)
            except ValueError:  # (auto)
                return None

        natural_width, natural_height = image.width(), image.height()
        width = length(keys.get("width", "auto"), cell_width, whole_width)
        height = length(keys.get("height", "auto"), cell_height, whole_height)
        if width is None and height is None:
            scale = min(1.0, whole_width / natural_width)
            return natural_width * scale, natural_height * scale
        if width is None:
            return natural_width * height / natural_height, height
        if height is None:
            return width, natural_height * width / natural_width
        if keys.get("preserveAspectRatio", "1") != "0":  # (within the box)
            scale = min(width / natural_width, height / natural_height)
            return natural_width * scale, natural_height * scale
        return width, height

    # -- sixel graphics (DCS ... q) ------------------------------------------------------------
    def sixel(self, params: str, data: str) -> None:
        """A sixel DCS string: its parameters (before ``q``) and its data."""
        image = self._sixel_image(params, data)
        if image is None:
            return
        screen = self.screen
        stored = self._keep(TerminalImage(self._new_id(), 0, image, 0, anonymous=True))
        cell_width, cell_height = screen.cell_pixels
        width, height = image.width(), image.height()
        if 80 in screen.modes:  # DECSDM: at the top left, cut to the screen; the cursor stays
            width = min(width, screen.cols * cell_width)
            height = min(height, screen.rows * cell_height)
            self.placements.append(Placement(
                stored.id, 0, screen.scrolled, 0, math.ceil(width / cell_width),
                math.ceil(height / cell_height), QRect(0, 0, width, height), width, height))
            return
        placement = Placement(stored.id, 0, 0, 0, math.ceil(width / cell_width),
                              math.ceil(height / cell_height), image.rect(), width, height)
        if 8452 in screen.modes:  # (the cursor to its right, on its last row)
            self._put(placement, True)
            return
        col = screen.col
        self._put(placement, False)
        for _ in range(placement.rows):  # (the cursor to the line below it)
            screen._line_feed()
        screen.col, screen.wrap_pending = col, False

    def _sixel_image(self, params: str, data: str) -> QImage | None:
        """The picture a sixel string draws (None: nothing drawn)."""
        fields = [int(field) if field.isdigit() else 0 for field in params.split(";")]
        fields += [0] * (2 - len(fields))
        aspect = _SIXEL_ASPECT.get(fields[0], 2)
        transparent = fields[1] == 1
        foreground, background = (0xffe5e5e5, 0xff000000)
        if self.screen.colors is not None:
            foreground, background = (0xff000000 | r << 16 | g << 8 | b
                                      for r, g, b in self.screen.colors())
        blank = 0 if transparent else background
        private = 1070 in self.screen.modes
        if private or self.screen.sixel_colors is None:
            registers = [_sixel_rgb(*rgb) for rgb in _VT340_COLORS]
            registers += [0xff000000] * (SIXEL_REGISTERS - len(registers))
            if not private:
                self.screen.sixel_colors = registers  # (shared: this picture's changes stay)
        else:
            registers = self.screen.sixel_colors
        color = foreground
        rows: list[array] = []  # (one per pixel row)
        capacity = 0  # (the rows' length)
        x = y = 0  # (y: the band's top row)
        right = bottom = 0  # (how far it has drawn)
        raster = (0, 0)
        started = False

        def make_room(width: int, height: int) -> None:
            nonlocal capacity
            if width > capacity:
                grown = min(MAX_SIDE, max(width, capacity * 2, 64))
                for row in rows:
                    row.extend(array("I", [blank]) * (grown - capacity))
                capacity = grown
            while len(rows) < height:
                rows.append(array("I", [blank]) * capacity)

        for match in _SIXEL_TOKENS.finditer(data):
            sixels, color_spec, repeat, repeated, raster_spec, move = match.groups()
            if sixels is not None or repeated is not None:
                count = 1
                if repeated is not None:
                    sixels, count = repeated, max(1, int(repeat or 1))
                started = True
                if y + 6 > MAX_SIDE // aspect or x >= MAX_SIDE:
                    continue
                count = min(count, MAX_SIDE - x)
                end = x + len(sixels) * count
                make_room(min(end, MAX_SIDE), y + 6)
                band = rows[y:y + 6]
                if count > 1:
                    bits = _SIXEL_BITS[ord(sixels) - 63]
                    if bits:
                        run = array("I", [color]) * count
                        for bit in bits:
                            band[bit][x:x + count] = run
                        bottom = max(bottom, y + bits[-1] + 1)
                        right = max(right, x + count)
                    x += count
                    continue
                for char in sixels[:MAX_SIDE - x]:
                    bits = _SIXEL_BITS[ord(char) - 63]
                    if bits:
                        for bit in bits:
                            band[bit][x] = color
                        bottom = max(bottom, y + bits[-1] + 1)
                        right = max(right, x + 1)
                    x += 1
                x = min(x, MAX_SIDE)
            elif color_spec is not None:
                numbers = [int(field) if field.isdigit() else 0
                           for field in color_spec.split(";")]
                register = numbers[0]
                if register >= SIXEL_REGISTERS:
                    continue
                if len(numbers) >= 5 and numbers[1] in (1, 2):
                    if numbers[1] == 2:
                        registers[register] = _sixel_rgb(*numbers[2:5])
                    else:  # (HLS, the VT340's hue: blue at 0, red at 120, green at 240)
                        hue, light, saturation = numbers[2:5]
                        rgb = QColor.fromHslF((hue + 240) % 360 / 360,
                                              min(100, saturation) / 100,
                                              min(100, light) / 100).rgb()
                        registers[register] = rgb | 0xff000000
                color = registers[register]
            elif raster_spec is not None:
                if not started:  # (only before the pixels)
                    numbers = [int(field) if field.isdigit() else 0
                               for field in raster_spec.split(";")]
                    numbers += [0] * (4 - len(numbers))
                    if numbers[0] and numbers[1]:
                        aspect = max(1, min(10, round(numbers[0] / numbers[1])))
                    raster = (min(MAX_SIDE, numbers[2]), min(MAX_SIDE, numbers[3]))
            elif move == "$":
                x = 0
            else:  # "-": the next band
                x, y = 0, y + 6
        width, height = max(right, raster[0]), max(bottom, -(-raster[1] // aspect))
        if not width or not height:
            return None
        make_room(width, height)
        lines = [rows[row][:width].tobytes() for row in range(height)]
        pixels = b"".join(line for line in lines for _ in range(aspect))
        height = min(MAX_SIDE, height * aspect)
        image = QImage(pixels, width, height, width * 4, QImage.Format_ARGB32).copy()
        return image.convertToFormat(QImage.Format_ARGB32_Premultiplied)

    # -- deleting ----------------------------------------------------------------------------
    def _delete(self, keys: dict) -> None:
        how = keys.get("d", "a") or "a"
        which, free = how.lower(), how.isupper()
        screen = self.screen
        number = self._number
        cell_x, cell_y = number(keys, "x"), number(keys, "y")
        if which == "a":
            gone = [p for p in self.placements if self.screen_row(p) >= 0]
        elif which in "in":
            try:
                image_id = self._find(keys if which == "n" else {"i": keys.get("i", "0")}).id
            except GraphicsError:
                return
            placement_id = number(keys, "p")
            gone = [p for p in self.placements
                    if p.image == image_id and (not placement_id or p.id == placement_id)]
            if free and not placement_id:
                self._forget(image_id)
        elif which == "c":
            gone = [p for p in self.placements if self._covers(p, screen.row, screen.col)]
        elif which in "pq":
            gone = [p for p in self.placements if self._covers(p, cell_y - 1, cell_x - 1) and
                    (which == "p" or p.z == number(keys, "z"))]
        elif which == "x":
            gone = [p for p in self.placements if p.col <= cell_x - 1 < p.col + p.cols]
        elif which == "y":
            gone = [p for p in self.placements
                    if self.screen_row(p) <= cell_y - 1 < self.screen_row(p) + p.rows]
        elif which == "z":
            gone = [p for p in self.placements if p.z == number(keys, "z")]
        elif which == "r":
            gone = [p for p in self.placements if cell_x <= p.image <= cell_y]
            if free:
                for image_id in [i for i in self.images if cell_x <= i <= cell_y]:
                    self._forget(image_id)
        else:  # (f: animation frames)
            return
        self._remove(gone, free)

    def _remove(self, gone: list[Placement], free: bool = False) -> None:
        gone_ids = {id(p) for p in gone}
        self.placements = [p for p in self.placements if id(p) not in gone_ids]
        if free:  # (and the pictures no longer shown)
            shown = {p.image for p in self.placements}
            for image_id in {p.image for p in gone} - shown:
                self.images.pop(image_id, None)

    def _covers(self, placement: Placement, row: int, col: int) -> bool:
        top = self.screen_row(placement)
        return top <= row < top + placement.rows and \
            placement.col <= col < placement.col + placement.cols

    # -- following the screen ---------------------------------------------------------------
    def screen_row(self, placement: Placement) -> int:
        """Its row on the screen (below 0: in the history)."""
        return placement.line - self.screen.scrolled

    def scrolled(self, top: int, bottom: int, step: int, into_history: bool) -> None:
        """Lines top..bottom moved one line up (step -1) or down (1); into_history:
        the top one went into the history (the screen's ``scrolled`` is about to
        count it)."""
        if into_history:  # (the region's lines move with the count; the ones below don't)
            for placement in self.placements:
                if self.screen_row(placement) > bottom:
                    placement.line += 1
            return
        kept = []
        for placement in self.placements:
            row = self.screen_row(placement)
            if top <= row <= bottom:
                if not top <= row + step <= bottom:
                    continue  # (out of the region: gone)
                placement.line += step
            kept.append(placement)
        self.placements = kept

    def clear(self, history: bool = False) -> None:
        """The screen cleared (ED 2): its placements go; the history's too (ED 3)."""
        self.placements = [p for p in self.placements
                           if not history and self.screen_row(p) < 0]

    def prune(self) -> None:
        """Placements on lines no longer there (the history's limit, a resize) go."""
        screen = self.screen
        first = -len(screen.history)
        self.placements = [p for p in self.placements if first <= self.screen_row(p) < screen.rows]
        self._drop_unplaced()

    def reset(self) -> None:
        self.images.clear()
        self.placements = []
        self._loading = self._multipart = None


def _sixel_rgb(red: int, green: int, blue: int) -> int:
    """A sixel color (percents of red, green, blue) as an ARGB value."""
    def byte(percent):
        return round(min(100, percent) * 255 / 100)

    return 0xff000000 | byte(red) << 16 | byte(green) << 8 | byte(blue)
