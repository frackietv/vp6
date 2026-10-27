# vp6help

Help files that work like the old Windows `.chm` help, for VP6 and any
other Python program: **vp6help-make** makes one `.vp6help` file of Markdown
and HTML documents (with the pictures and files they link to) and of Python
packages documented from their code; **vp6help** shows it, with a table of
contents, an index and full-text search on the left and the pages on the
right.

```bash
pip install vp6help
vp6help-make -o MyHelp.vp6help --title "My Help" README.md docs/
vp6help-make -o MyApi.vp6help --package mypackage --follow
vp6help MyHelp.vp6help                                # the contents
vp6help MyHelp.vp6help docs/guide.html#installing     # a page, at a heading
vp6help MyHelp.vp6help --keyword Open                 # what the index has for Open
vp6help MyHelp.vp6help --index "^Show" --regex        # the index, narrowed
vp6help MyHelp.vp6help --search "save|load" --regex   # a search, matches highlighted
vp6help MyHelp.vp6help --list --search Open           # print the results instead
```

From a Qt program:

```python
from vp6help import show_help
show_help("MyHelp.vp6help", keyword="Open")
```

## Making a help file

* **Documents:** Markdown (`.md`, GitHub-style: tables, fenced code, task
  lists...) and HTML (`.html`), or folders of them. The contents follow the
  order given (a folder's documents by name, its README or index first), each
  with its headings down to `--toc-depth` (3); `--flat PATTERN` keeps a
  document's headings out. Links between the documents become links between
  pages, and pictures and files they link to (inside the root folder) go
  into the help file.
* **Index:** headings; a name in code starting a table row or standing alone
  in a paragraph (`` **`Open(path)`** `` gives `Open`); the keywords of a
  `<!-- keywords: a, b -->` comment (for the section it is in) and of an HTML
  page's `<meta name="keywords">`.
* **Search:** every section's text (a heading and what follows).
* **Python packages** (`--package NAME`, repeatable): a page per module with
  its classes (methods, properties, attributes, and what they inherit),
  functions and constants (grouped by `# --- Title ---` comments), read from
  the source with `ast` (nothing is imported or run; compiled modules are
  imported and inspected). `--follow` also documents the packages they
  import (not the standard library unless `--follow-stdlib`); `--private`
  includes `_private` names; `--exclude` leaves modules out.

Arguments can come from a file: `vp6help-make @MyHelp.args`.

## Mathematics

Markdown documents can have formulas in TeX: `$…$` in the text, `$$…$$` on
lines of their own (displayed, centred). The viewer draws them in the page's
font and colours (dark too, zoomed too, sharp on any screen), and copying
them gives their TeX. A `$` that opens a formula is followed by something
other than a space and the closing one isn't followed by a digit, so
`$5 and $10` stays text; `\$` is a dollar sign; code is never maths. A
formula that can't be read shows its source in red.

The TeX understood is what mathematics lessons need: fractions, exponents and
subscripts, roots, Greek letters, relations, operators and arrows, absolute
values, delimiters that grow (`\left( … \right)`), sums, products, integrals
and limits with their bounds, functions, matrices, `cases`, `aligned`, text,
fonts (`\mathbb{R}`...), accents and vectors, `\overline` for repeating
decimals, braces, `\boxed`, `\cancel`, colours, spaces and styles.

* `vp6help.tex` (pure Python) finds the formulas in Markdown (`math_spans`),
  reads them (`parse`, `TexError`) and lays them out as TeX does (`layout`,
  `render`: boxes with baselines, TeX's spacing classes and styles), as text,
  rules and shapes to draw, measured through a `Metrics`.
* `vp6help.texdraw` (Qt) measures a QFont (`QtMetrics`), paints a layout
  (`paint`), and puts formulas into a `QTextDocument` as inline objects that
  follow the text's font and colour (`insert_math`, `install`, `text_of`,
  `mime_data` for copying, `insert_text` for pasting).

## The file

A `.vp6help` file is a zip archive: `vp6help.json` (the title, home page,
contents, index and the searchable text of each section) and the pages and
files at their paths. Pages are addressed `docs/guide.html#anchor`.
