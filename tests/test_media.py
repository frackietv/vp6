"""SvgImage (and SVG files as pictures), MediaPlayer and PdfViewer."""

import os

import pytest

import vp6
from conftest import wait_for
from vp6 import Form, Image, MediaPlayer, PdfViewer, Printer, SvgImage
from vp6.ide.kitchensink import write_svg, write_tone
from vp6.picture import picture_pixmap


@pytest.fixture
def folder(qapp, tmp_path):
    write_svg(str(tmp_path / "logo.svg"))
    write_tone(str(tmp_path / "tone.wav"), seconds=0.3)
    return tmp_path


def _form(folder, build):
    class Media(Form):
        def InitializeComponent(self):
            self.events = []
            build(self)

        def _base_dir(self):
            return str(folder)

        def pdfDoc_PageChange(self):
            self.events.append(("Page", self.pdfDoc.Page))

        def mpTone_StateChange(self):
            self.events.append(("State", self.mpTone.State))

    return Media()


def test_svg_image(folder):
    form = _form(folder, lambda f: setattr(f, "svgLogo", SvgImage(f, Picture="logo.svg",
                                                                   Width=240, Height=60)))
    try:
        svg = form.svgLogo
        assert (svg.PictureWidth, svg.PictureHeight) == (120, 80) and svg.Width == 240
        image = svg._widget.grab().toImage()
        assert image.pixelColor(2, 30).alpha() == 0  # (shape kept: centred, space beside)
        svg.KeepAspect = False
        assert svg._widget.grab().toImage().pixelColor(4, 30).alpha() > 0
        svg.Stretch = False
        assert (svg.Width, svg.Height) == (120, 80)
    finally:
        form.Unload()


def test_svg_files_as_pictures(folder):
    path = str(folder / "logo.svg")
    pixmap = picture_pixmap(None, path)
    assert pixmap.deviceIndependentSize().toSize().width() == 120
    assert vp6.LoadPicture(path).Width == 120
    form = _form(folder, lambda f: setattr(f, "imgLogo", Image(f, Picture="logo.svg")))
    try:
        assert (form.imgLogo.Width, form.imgLogo.Height) == (120, 80)
    finally:
        form.Unload()


def test_media_player(folder):
    form = _form(folder, lambda f: setattr(f, "mpTone", MediaPlayer(f, FileName="tone.wav",
                                                                     Mute=True, Volume=30)))
    try:
        player = form.mpTone
        assert player.State == vp6.vpMediaStopped and player._audio.isMuted()
        assert abs(player._audio.volume() - 0.3) < 0.01
        wait_for(lambda: player.Duration > 0, 5000)
        assert 0.2 < player.Duration < 0.5
        player.Loop = True
        assert player._player.loops() == -1
        player.PlaybackRate = 1.5
        assert player._player.playbackRate() == 1.5
        player.ShowControls = False
        assert player._widget.bar.isHidden()
    finally:
        form.Unload()


def _print_pdf(path):
    Printer.OutputFile = path
    try:
        Printer.Print("Page one")
        Printer.NewPage()
        Printer.Print("Page two: a kangaroo")
        Printer.EndDoc()
    finally:
        Printer.OutputFile = ""


def test_pdf_viewer(folder):
    pdf = str(folder / "doc.pdf")
    _print_pdf(pdf)
    form = _form(folder, lambda f: setattr(f, "pdfDoc", PdfViewer(f, FileName="doc.pdf")))
    form.Show()
    try:
        viewer = form.pdfDoc
        assert viewer.PageCount == 2 and viewer.Page == 1
        assert "kangaroo" in viewer.PageText(2) and viewer.PageText(9) == ""
        assert viewer.Find("KANGAROO") and viewer.Page == 2 and viewer.SelectedText == "kangaroo"
        assert ("Page", 2) in form.events
        assert not viewer.Find("wombat") and viewer.SelectedText == ""
        viewer.Page = 1
        assert viewer.Page == 1
        viewer.ZoomMode, viewer.Zoom = vp6.vpZoomCustom, 2
        assert viewer.Zoom == 2
        viewer.PageMode = vp6.vpPageSingle
        assert viewer._widget.pageMode() == viewer._widget.PageMode.SinglePage
        from vp6 import printer

        before = set(os.listdir(printer.REDIRECT_DIR))
        viewer.PrintOut()
        assert set(os.listdir(printer.REDIRECT_DIR)) - before
        with pytest.raises(FileNotFoundError):
            viewer.FileName = "missing.pdf"
    finally:
        form.Unload()
