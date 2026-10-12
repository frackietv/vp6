"""Wizard forms: a ``WizardForm`` is a form whose window is a wizard (Qt's
QWizard), its pages edited in the designer like a ToolBox's.

    class frmSetup(WizardForm):
        def InitializeComponent(self):
            self.Pages = ['Welcome|What this wizard does', 'Your name|', 'Done|']
            self.txtName = TextBox(self, Page=1, Left=16, Top=16, ...)

        def Form_ValidatePage(self, Page):
            if Page == 1 and not self.txtName.Text:
                MsgBox("Please type your name")
                return True                     # stays on the page

        def Form_Finish(self):
            SaveSetting("Setup", "User", "Name", self.txtName.Text)

* ``Pages``: one per line, ``Title|SubTitle`` (shown in the header at the
  top of the page). Every control is on one page (its ``Page``, from 0);
  the designer edits the page ``CurrentPage`` says (Previous Page / Next Page
  in its context menu).
* Back, Next, Finish and Cancel are the wizard's own buttons; ``Next()`` and
  ``Back()`` press them from code. ``WizardStyle``: vpWizardClassic,
  vpWizardModern, vpWizardMac or vpWizardAero.
* Events (``Form_...``): ``ValidatePage(Page)`` when Next or Finish is
  clicked (returning True stays on the page), ``NextPage(Page)`` (return the
  number of the page to go to instead of the next one, or -1 to make it the
  last), ``PageChange`` once another page is shown, ``Finish`` (then the form
  unloads; ``Accepted`` is True) and ``Cancel`` (returning True keeps the
  wizard open; else it unloads).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QWizard, QWizardPage

from ._props import P, enum_choices
from .controls import EVENT_ARGS
from .form import Form

EVENT_ARGS.update({"ValidatePage": "Page", "NextPage": "Page", "PageChange": "", "Finish": "",
                   "Cancel": ""})

_STYLES = (QWizard.ClassicStyle, QWizard.ModernStyle, QWizard.MacStyle, QWizard.AeroStyle)


class _Page(QWizardPage):
    """A page: Next asks the form (ValidatePage), and where to go (NextPage)."""

    def __init__(self, form: "WizardForm"):
        super().__init__()
        self._form = form

    def validatePage(self):
        return self._form._validate_page(self)

    def nextId(self):
        return self._form._next_id(self)


class _Wizard(QWizard):
    """The wizard inside the form's window: finishing or cancelling it is the
    form's business (it isn't a dialog of its own)."""

    def __init__(self, form: "WizardForm", parent: QWidget):
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget)  # (a part of the form's window, not a window)
        self._form = form
        self.setOption(QWizard.NoDefaultButton, False)

    def done(self, result):
        self._form._done(result == QWizard.Accepted)


class WizardForm(Form):
    """A form that is a wizard (the module's documentation)."""

    _vp_base = True  # (WizardForm itself has no default instance: a project's has)
    TypeName = "WizardForm"
    Events = Form.Events + ("ValidatePage", "NextPage", "PageChange", "Finish", "Cancel")
    EventArgs = {"ValidatePage": "Page", "NextPage": "Page"}
    Properties = Form.Properties + (
        P("Pages", "list", ["Welcome|", "Done|"],
          description="Its pages, one per line: Title|SubTitle (shown in the page's header)"),
        P("CurrentPage", "int", 0,
          description="The page shown first (from 0); in the designer, the page being edited"),
        P("WizardStyle", "enum", 1, enum_choices("Classic", "Modern", "macOS", "Aero"),
          description="How the wizard looks: its header, its buttons"),
    )

    def __init__(self):
        self.__dict__.update(_wizard=None, _accepted=False, _closing=False, _quiet=0)
        super().__init__()
        self._show_page(self._values.get("CurrentPage", 0))

    def _wizard_widget(self) -> _Wizard:
        wizard = self._wizard
        if wizard is None:
            wizard = _Wizard(self, self._container_widget())
            wizard.currentIdChanged.connect(self._on_page_changed)
            self.__dict__["_wizard"] = wizard
            wizard.show()
        return wizard

    def _layout_aligned(self) -> None:
        super()._layout_aligned()
        wizard = self._wizard
        if wizard is not None:
            if wizard.parent() is not self._container_widget():  # (a menu bar's client area)
                wizard.setParent(self._container_widget())
                wizard.show()
            wizard.setGeometry(self._container_widget().rect())

    # -- pages (as a ToolBox's: Control.Page) ----------------------------------------------------
    def _pages(self) -> list[QWidget]:
        wizard = self._wizard_widget()
        return [wizard.page(page_id) for page_id in wizard.pageIds()]

    def _page_widget(self, page: int) -> QWidget:
        pages = self._pages()
        if not pages:
            self._set_pages(["|"])
            pages = self._pages()
        return pages[max(0, min(int(page), len(pages) - 1))]

    def _page_index_of(self, widget) -> int | None:
        pages = self._pages()
        return pages.index(widget) if widget in pages else None

    def _current(self) -> int:
        current = self._wizard_widget().currentId()
        return current if current >= 0 else self._values.get("CurrentPage", 0)

    def _show_page(self, page: int) -> None:
        wizard = self._wizard_widget()
        count = len(wizard.pageIds())
        if not count:
            return
        self.__dict__["_quiet"] = self._quiet + 1  # (shown by code: no PageChange)
        try:
            wizard.setStartId(max(0, min(int(page), count - 1)))
            wizard.restart()
        finally:
            self.__dict__["_quiet"] = self._quiet - 1

    def _show_page_for(self, control) -> None:
        page = self._page_index_of(control._widget.parentWidget()) \
            if control._widget is not None else None
        if page is not None and page != self._current():
            self._show_page(page)

    def _set_pages(self, lines) -> None:
        wizard = self._wizard_widget()
        old = self._pages()
        wanted = max(1, len(lines))
        for index in range(wanted):
            title, _, subtitle = (str(lines[index]) if index < len(lines) else "").partition("|")
            if index < len(old):
                page = old[index]
            else:
                page = _Page(self)
                wizard.setPage(index, page)
            page.setTitle(title.strip())
            page.setSubTitle(subtitle.strip())
        for index in range(wanted, len(old)):  # (in the designer: its controls to the last)
            page = old[index]
            if self._design_mode:
                target = old[wanted - 1]
                for child in [c for c in page.children() if isinstance(c, QWidget)]:
                    shown = not child.isHidden()
                    child.setParent(target)
                    if shown:
                        child.show()
            wizard.removePage(index)
            page.deleteLater()

    def _apply_Pages(self, lines):
        self._set_pages(list(lines or []))
        self._show_page(self._values.get("CurrentPage", 0))

    def _apply_CurrentPage(self, v):
        self._show_page(int(v))

    def _read_CurrentPage(self):
        return self._current()

    def _apply_WizardStyle(self, v):
        self._wizard_widget().setWizardStyle(_STYLES[int(v) if 0 <= int(v) <= 3 else 1])

    @property
    def PageCount(self) -> int:
        return len(self._pages())

    def PageTitle(self, Page: int) -> str:
        """Page's title (from 0)."""
        return self._pages()[int(Page)].title()

    # -- going through it --------------------------------------------------------------------------
    def _validate_page(self, page) -> bool:
        if self._design_mode:
            return True
        return self._fire("ValidatePage", self._pages().index(page)) is not True

    def _next_id(self, page) -> int:
        pages = self._pages()
        index = pages.index(page)
        if not self._design_mode:
            result = self._fire("NextPage", index)
            if isinstance(result, int) and not isinstance(result, bool):
                return result if 0 <= result < len(pages) else -1
        return index + 1 if index + 1 < len(pages) else -1

    def _on_page_changed(self, page_id):
        if page_id >= 0 and not self._design_mode and not self._quiet:
            self._values["CurrentPage"] = page_id
            self._fire("PageChange")

    def _done(self, accepted: bool) -> None:
        if self._design_mode or self._closing:
            return
        if accepted:
            self.__dict__["_accepted"] = True
            self._fire("Finish")
        elif self._fire("Cancel") is True:
            return
        self.__dict__["_closing"] = True
        try:
            self.Unload()
        finally:
            self.__dict__["_closing"] = False

    def Next(self) -> None:
        """Go on to the next page (as the Next button: ValidatePage first)."""
        self._wizard_widget().next()

    def Back(self) -> None:
        """Back to the page before (as the Back button)."""
        self._wizard_widget().back()

    @property
    def Accepted(self) -> bool:
        """Whether it was finished with Finish (False: cancelled, or not yet)."""
        return self._accepted

    @property
    def VisitedPages(self) -> list[int]:
        """The pages shown so far, in order (Back goes back along them)."""
        return list(self._wizard_widget().visitedIds())
