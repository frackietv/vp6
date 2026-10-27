"""Markdown to HTML, in pure Python (no Qt): what the help maker turns ``.md``
pages into.

It covers what documentation uses, GitHub-style: ATX and setext headings,
paragraphs, emphasis (``*``, ``_``, ``**``, ``__``, ``~~``), code spans and
fenced or indented code blocks, links and images (inline, ``<autolinks>`` and
bare URLs), block quotes, nested bullet and ordered lists (task items too),
tables with alignment, horizontal rules, hard line breaks and raw HTML (blocks,
comments and inline tags pass through untouched); formulas, ``$…$`` in the text
and ``$$…$$`` displayed (``vp6help.tex``), as ``<img src="vp6math:...">`` pictures
that the viewer draws (``vp6help.texdraw.install``).

    html = to_html(text)
"""

from __future__ import annotations

import html as _html
import re

from . import tex

__all__ = ["to_html", "escape", "math_html"]

TAB = 4

_FENCE = re.compile(r"^( {0,3})(`{3,}|~{3,})\s*([^`\s]*)[^`]*$")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
_HR = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_QUOTE = re.compile(r"^ {0,3}> ?")
_LIST = re.compile(r"^( {0,3})([-*+]|\d{1,9}[.)])([ \t]+|$)")
_HTML_BLOCK = re.compile(r"^ {0,3}<(?:!--|/?[A-Za-z][\w-]*(?:[\s/>]|$)|!\[CDATA\[|\?|![A-Z])")
_TABLE_RULE = re.compile(r"^ {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$")
_TASK = re.compile(r"^\[([ xX])\][ \t]+")
_DISPLAY_MATH = re.compile(r"^ {0,3}\$\$")


def escape(text: str, quote: bool = False) -> str:
    """HTML-escape text (and double quotes, for attribute values)."""
    return _html.escape(text, quote=quote)


def math_html(source: str, display: bool = False) -> str:
    """A formula's HTML: a picture the viewer draws (its source as the alt text)."""
    from urllib.parse import quote

    kind = "display" if display else "inline"
    return (f'<img class="math" src="vp6math:{kind},{quote(source, safe="")}" '
            f'alt="{escape(source, True)}" />')


def to_html(text: str) -> str:
    """The HTML of a Markdown document."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(TAB).split("\n")
    return "\n".join(_render(_blocks(lines), tight=False)) + "\n"


# --- blocks ---------------------------------------------------------------------------------

def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _dedent(line: str, count: int) -> str:
    return line[min(count, _indent(line)):]


def _starts_block(line: str) -> bool:
    """Whether a line interrupts a paragraph."""
    if _FENCE.match(line) or _ATX.match(line) or _HR.match(line) or _QUOTE.match(line):
        return True
    m = _LIST.match(line)
    if m and line[m.end():].strip():  # (an empty item doesn't interrupt a paragraph)
        return m.group(2)[0] in "-*+" or m.group(2)[:-1] == "1"
    return bool(re.match(r"^ {0,3}<(?:!--|/?(?:div|table|pre|p|ul|ol|h[1-6]|blockquote|"
                         r"details|summary|section|hr|br|img|dl|figure)\b)", line, re.I))


def _blocks(lines: list[str]) -> list[tuple[str, object]]:
    """The blocks of some lines: (kind, data) pairs."""
    blocks: list[tuple[str, object]] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            blocks.append(("blank", None))
            i += 1
            continue
        m = _FENCE.match(line)
        if m:
            indent, fence, lang = len(m.group(1)), m.group(2), m.group(3)
            i += 1
            code = []
            while i < n:
                close = re.match(r"^ {0,3}(" + re.escape(fence[0]) + r"{%d,})[ \t]*$"
                                 % len(fence), lines[i])
                if close:
                    i += 1
                    break
                code.append(_dedent(lines[i], indent))
                i += 1
            blocks.append(("code", (lang, "\n".join(code))))
            continue
        m = _ATX.match(line)
        if m:
            blocks.append(("heading", (len(m.group(1)), (m.group(2) or "").strip())))
            i += 1
            continue
        if _HR.match(line):
            blocks.append(("hr", None))
            i += 1
            continue
        if _DISPLAY_MATH.match(line):  # $$ ... $$ on lines of their own: a displayed formula
            j, found = i, None
            text = "\n".join(lines[i:])
            spans = tex.math_spans(text)
            if spans and spans[0].start == len(line) - len(line.lstrip(" ")) and \
                    spans[0].display:
                rest = text[spans[0].end:]
                if not rest.split("\n", 1)[0].strip():
                    found = spans[0]
                    j = i + text[:spans[0].end].count("\n") + 1
            if found is not None:
                blocks.append(("math", found.tex))
                i = j
                continue
        if _indent(line) >= 4:
            code = []
            while i < n and (not lines[i].strip() or _indent(lines[i]) >= 4):
                code.append(lines[i][4:])
                i += 1
            while code and not code[-1].strip():
                code.pop()
            blocks.append(("code", ("", "\n".join(code))))
            continue
        if _QUOTE.match(line):
            quoted = []
            while i < n and lines[i].strip():
                m = _QUOTE.match(lines[i])
                if m:
                    quoted.append(lines[i][m.end():])
                elif _starts_block(lines[i]):
                    break
                else:  # a lazy continuation line
                    quoted.append(lines[i])
                i += 1
            blocks.append(("quote", _blocks(quoted)))
            continue
        m = _LIST.match(line)
        if m:
            i = _list(lines, i, blocks)
            continue
        if _HTML_BLOCK.match(line):
            raw = []
            if line.lstrip().startswith("<!--"):
                while i < n:
                    raw.append(lines[i])
                    i += 1
                    if "-->" in raw[-1]:
                        break
            else:
                while i < n and lines[i].strip():
                    raw.append(lines[i])
                    i += 1
            blocks.append(("html", "\n".join(raw)))
            continue
        if "|" in line and i + 1 < n and _TABLE_RULE.match(lines[i + 1]) \
                and "-" in lines[i + 1]:
            header = _cells(line)
            aligns = []
            for cell in _cells(lines[i + 1]):
                cell = cell.strip()
                aligns.append("center" if cell.startswith(":") and cell.endswith(":") else
                              "right" if cell.endswith(":") else
                              "left" if cell.startswith(":") else "")
            i += 2
            rows = []
            while i < n and lines[i].strip() and "|" in lines[i]:
                rows.append(_cells(lines[i]))
                i += 1
            blocks.append(("table", (header, aligns, rows)))
            continue
        # A paragraph, perhaps a setext heading
        para = [line.strip()]
        i += 1
        while i < n and lines[i].strip():
            m = _SETEXT.match(lines[i])
            if m:
                level = 1 if m.group(1)[0] == "=" else 2
                blocks.append(("heading", (level, " ".join(para))))
                para = None
                i += 1
                break
            if _starts_block(lines[i]):
                break
            para.append(lines[i] if lines[i].endswith("  ") else lines[i].strip())
            i += 1
        if para is not None:
            blocks.append(("para", para))
    return blocks


def _cells(line: str) -> list[str]:
    """A table row's cells (pipes in code spans or escaped don't split)."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, current, ticks, j = [], [], 0, 0
    while j < len(line):
        ch = line[j]
        if ch == "\\" and j + 1 < len(line) and line[j + 1] == "|":
            current.append("|")
            j += 2
            continue
        if ch == "`":
            run = len(line[j:]) - len(line[j:].lstrip("`"))
            ticks = 0 if ticks == run else (ticks or run)
            current.append("`" * run)
            j += run
            continue
        if ch == "|" and not ticks:
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        j += 1
    cells.append("".join(current).strip())
    return cells


def _list(lines: list[str], i: int, blocks: list) -> int:
    """Parse the list starting at lines[i]; returns the line after it."""
    n = len(lines)
    first = _LIST.match(lines[i])
    ordered = first.group(2)[0].isdigit()
    delimiter = first.group(2)[-1]
    start = int(first.group(2)[:-1]) if ordered else 1
    items, loose = [], False
    def sibling(line):
        m = _LIST.match(line)
        return m if m and m.group(2)[0].isdigit() == ordered and \
            m.group(2)[-1] == delimiter else None

    while i < n:
        m = sibling(lines[i])
        if not m:
            break
        if _HR.match(lines[i]) and not ordered:
            break
        spaces = len(m.group(3))
        content = len(m.group(1)) + len(m.group(2)) + (spaces if 1 <= spaces <= 4 else 1)
        item = [lines[i][m.end():] if spaces <= 4 else lines[i][content:]]
        i += 1
        blank_before = False
        while i < n:
            line = lines[i]
            if not line.strip():
                item.append("")
                blank_before = True
                i += 1
                continue
            if _indent(line) >= content:
                item.append(line[content:])
                blank_before = False
                i += 1
                continue
            if not blank_before and not _starts_block(line) and not _LIST.match(line):
                item.append(line.strip())  # a lazy continuation of the item's paragraph
                i += 1
                continue
            break
        # A blank line between items, or between an item's blocks, makes the list loose
        trailing = 0
        while item and not item[-1].strip():
            item.pop()
            trailing += 1
        sub = _blocks(item)
        kinds = [kind for kind, _ in sub]
        if any(kinds[k] == "blank" and "blank" not in (kinds[k - 1], kinds[k + 1])
               for k in range(1, len(kinds) - 1)):
            loose = True
        items.append(sub)
        if trailing and i < n and sibling(lines[i]):
            loose = True
        if trailing and (i >= n or not sibling(lines[i])):
            break
    blocks.append(("list", (ordered, start, items, loose)))
    return i


def _render(blocks, tight: bool) -> list[str]:
    out = []
    for kind, data in blocks:
        if kind == "blank":
            continue
        if kind == "heading":
            level, text = data
            out.append(f"<h{level}>{inline(text)}</h{level}>")
        elif kind == "para":
            body = _join_lines(data)
            out.append(body if tight else f"<p>{body}</p>")
        elif kind == "code":
            lang, code = data
            cls = f' class="language-{escape(lang, True)}"' if lang else ""
            out.append(f"<pre><code{cls}>{escape(code)}</code></pre>")
        elif kind == "hr":
            out.append("<hr />")
        elif kind == "math":
            out.append(f'<p align="center">{math_html(data, True)}</p>')
        elif kind == "html":
            out.append(data)
        elif kind == "quote":
            out.append("<blockquote>\n" + "\n".join(_render(data, False)) + "\n</blockquote>")
        elif kind == "table":
            header, aligns, rows = data

            def row(cells, tag):
                parts = []
                for k in range(len(header)):
                    cell = cells[k] if k < len(cells) else ""
                    align = aligns[k] if k < len(aligns) else ""
                    attr = f' align="{align}"' if align else ""
                    parts.append(f"<{tag}{attr}>{inline(cell)}</{tag}>")
                return "<tr>" + "".join(parts) + "</tr>"

            body = [row(header, "th")] + [row(r, "td") for r in rows]
            out.append("<table>\n" + "\n".join(body) + "\n</table>")
        elif kind == "list":
            ordered, start, items, loose = data
            tag = "ol" if ordered else "ul"
            attr = f' start="{start}"' if ordered and start != 1 else ""
            parts = []
            for item in items:
                check = ""
                if item and item[0][0] == "para":
                    m = _TASK.match(item[0][1][0])
                    if m:
                        check = "\u2612 " if m.group(1) in "xX" else "\u2610 "
                        item = [("para", [item[0][1][0][m.end():]] + item[0][1][1:])] + item[1:]
                body = "\n".join(_render(item, tight=not loose))
                parts.append(f"<li>{check}{body}</li>")
            out.append(f"<{tag}{attr}>\n" + "\n".join(parts) + f"\n</{tag}>")
    return out


def _join_lines(lines: list[str]) -> str:
    if any("$" in line for line in lines) and len(lines) > 1:
        lines = _keep_formulas_whole(lines)
    parts = []
    for k, line in enumerate(lines):
        last = k == len(lines) - 1
        if not last and line.endswith("  "):
            parts.append(inline(line.rstrip()) + "<br />")
        elif not last and line.endswith("\\") and not line.endswith("\\\\"):
            parts.append(inline(line[:-1]) + "<br />")
        else:
            parts.append(inline(line.strip()))
    return "\n".join(parts)


def _keep_formulas_whole(lines: list[str]) -> list[str]:
    """A paragraph's lines, those a formula spans joined into one."""
    text = "\n".join(lines)
    starts, offset = [], 0
    for line in lines:
        starts.append(offset)
        offset += len(line) + 1

    def line_of(position):
        k = 0
        while k + 1 < len(starts) and starts[k + 1] <= position:
            k += 1
        return k

    merged = list(lines)
    for span in reversed(tex.math_spans(text)):
        first, last = line_of(span.start), line_of(span.end - 1)
        if first < last:
            merged[first:last + 1] = [" ".join(merged[first:last + 1])]
    return merged


# --- inline ---------------------------------------------------------------------------------

_ESCAPABLE = re.compile(r"\\([!-/:-@\[-`{-~])")
_AUTOLINK = re.compile(r"<((?:https?|ftp|mailto|file):[^\s<>]+)>")
_EMAIL = re.compile(r"<([\w.+-]+@[\w-]+(?:\.[\w-]+)+)>")
_TAG = re.compile(r"</?[A-Za-z][\w-]*(?:\s+[\w:-]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?)*"
                  r"\s*/?>|<!--.*?-->")
_LINK_TARGET = r"\(\s*<?([^\s()<>]*(?:\([^\s()]*\)[^\s()<>]*)*)>?(?:\s+(\"[^\"]*\"|'[^']*'))?\s*\)"
_IMAGE = re.compile(r"!\[([^\]]*)\]" + _LINK_TARGET)
_LINK = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]" + _LINK_TARGET)
_BARE_URL = re.compile(r"(?<![\w\"'=/>])(https?://[^\s<>\x00]*[^\s<>\x00.,:;\"')\]!?*_])")
_PLACEHOLDER = re.compile("\x00(\\d+)\x00")


def inline(text: str) -> str:
    """The HTML of a line of Markdown text (code spans, links, emphasis...)."""
    store: list[str] = []

    def keep(fragment: str) -> str:
        store.append(fragment)
        return f"\x00{len(store) - 1}\x00"

    text = _code_spans(text, keep)
    if "$" in text:  # (formulas before escapes and emphasis: TeX has backslashes and stars)
        pieces, position = [], 0
        for span in tex.math_spans(text):
            pieces.append(text[position:span.start])
            pieces.append(keep(math_html(span.tex, span.display)))
            position = span.end
        text = "".join(pieces) + text[position:]
    text = _ESCAPABLE.sub(lambda m: keep(escape(m.group(1))), text)
    text = _AUTOLINK.sub(lambda m: keep(f'<a href="{escape(m.group(1), True)}">'
                                        f'{escape(m.group(1))}</a>'), text)
    text = _EMAIL.sub(lambda m: keep(f'<a href="mailto:{escape(m.group(1), True)}">'
                                     f'{escape(m.group(1))}</a>'), text)
    text = _TAG.sub(lambda m: keep(m.group(0)), text)

    def title_attr(title):
        return f' title="{escape(title[1:-1], True)}"' if title else ""

    text = _IMAGE.sub(lambda m: keep(
        f'<img src="{escape(m.group(2), True)}" alt="{escape(_plain(m.group(1), store), True)}"'
        f'{title_attr(m.group(3))} />'), text)
    text = _LINK.sub(lambda m: keep(
        f'<a href="{escape(m.group(2), True)}"{title_attr(m.group(3))}>'
        f'{_emphasis(escape(m.group(1)))}</a>'), text)
    text = _BARE_URL.sub(lambda m: keep(f'<a href="{escape(m.group(1), True)}">'
                                        f'{escape(m.group(1))}</a>'), text)
    text = _emphasis(escape(text))
    for _ in range(8):  # (placeholders inside placeholders: links around code)
        text, count = _PLACEHOLDER.subn(lambda m: store[int(m.group(1))], text)
        if not count:
            break
    return text


def _plain(text: str, store: list[str]) -> str:
    """Alt text: the text without its markup (code spans keep their text)."""
    text = _PLACEHOLDER.sub(lambda m: re.sub(r"<[^>]+>", "", _html.unescape(store[int(m.group(1))])),
                            text)
    return re.sub(r"[*_`]", "", text)


def _code_spans(text: str, keep) -> str:
    out, i = [], 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] == "`":
            out.append(text[i:i + 2])
            i += 2
            continue
        if text[i] != "`":
            out.append(text[i])
            i += 1
            continue
        run = len(text[i:]) - len(text[i:].lstrip("`"))
        close = re.compile(r"(?<!`)" + "`" * run + r"(?!`)").search(text, i + run)
        if close is None:
            out.append("`" * run)
            i += run
            continue
        code = text[i + run:close.start()].replace("\n", " ")
        if code.startswith(" ") and code.endswith(" ") and code.strip():
            code = code[1:-1]
        out.append(keep(f"<code>{escape(code)}</code>"))
        i = close.end()
    return "".join(out)


_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_EM_STAR = re.compile(r"\*(?=[^\s*])(.+?)(?<=[^\s*])\*")
_EM_UNDERSCORE = re.compile(r"(?<![\w\\])_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)")
_STRIKE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")


def _emphasis(text: str) -> str:
    def strong(m):
        if m.group(1) == "__" and (re.search(r"\w$", text[:m.start()]) or
                                   re.match(r"\w", text[m.end():])):
            return m.group(0)  # (snake__case words)
        return f"<strong>{m.group(2)}</strong>"

    text = _STRONG.sub(strong, text)
    text = _EM_STAR.sub(r"<em>\1</em>", text)
    text = _EM_UNDERSCORE.sub(r"<em>\1</em>", text)
    return _STRIKE.sub(r"<del>\1</del>", text)
