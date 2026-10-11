"""vp6help: help files that work like the old .chm help.

* ``vp6help-make`` (``vp6help.maker``) makes one ``.vp6help`` file of
  Markdown and HTML documents, the pictures and files they link to, and
  Python packages documented from their code;
* ``vp6help`` (``vp6help.viewer``) shows it: the contents, the index and
  search on the left, the pages on the right; any page, index keyword or
  search can be opened from the command line or with ``show_help``.

    from vp6help import show_help
    show_help("MyHelp.vp6help", keyword="Open")
"""

__version__ = "0.1.0"

from .helpfile import HelpFile, IndexEntry, SearchHit  # noqa: E402

__all__ = ["__version__", "HelpFile", "IndexEntry", "SearchHit", "HelpMaker", "show_help"]


def __getattr__(name):
    # (the maker and the viewer only when used: the viewer needs Qt)
    if name == "HelpMaker":
        from .maker import HelpMaker
        return HelpMaker
    if name == "show_help":
        from .viewer import show_help
        return show_help
    raise AttributeError(name)
