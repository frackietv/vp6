"""The code window's model, VB's way: the Object list (the form, or the user
control, and its controls, each with its events) and the Procedure list (the
object's events, the procedures in "(General)"), where an event's handler is
written (its stub at the end of the form's class), the procedure a line is
in, and the completion list's words.

A document here is anything with ``text`` and ``name``; a form's (or a user
control's) also has ``form_def`` (``formfile.parse`` of its text) and
``kind`` ("form" or "usercontrol"). Lines count from 0, as a text's
``split("\\n")``.
"""

from __future__ import annotations

import builtins
import keyword
import re

GENERAL = "(General)"
DECLARATIONS = "(Declarations)"
INDENT = "    "

_DEF_LINE = re.compile(r"^\s*def\s+(\w+)\s*\(")


def is_form(document) -> bool:
    """Whether it is a form's (or a user control's) file."""
    return getattr(document, "form_def", None) is not None


def vp6_names() -> set[str]:
    import vp6

    return set(vp6.__all__)


def builtin_names() -> set[str]:
    return {n for n in dir(builtins) if not n.startswith("_")} - set(keyword.kwlist)


def objects(document) -> list[tuple[str, tuple[str, ...]]]:
    """(object, its events) for the Object list: "Form" (a wizard's events
    too), or "UserControl" for a user control, then its controls by name
    (an array once); none for a module."""
    if not is_form(document):
        return []
    from vp6 import formfile
    from vp6.controls import CONTROL_TYPES
    from vp6.form import Form
    from vp6.usercontrol import OWN_EVENTS
    from vp6.wizard import WizardForm

    result = []
    if document.kind == "usercontrol":  # its own events: UserControl_Resize...
        result.append(("UserControl", OWN_EVENTS))
    elif formfile.find_form_base(document.text) == "WizardForm":
        result.append(("Form", WizardForm.Events))  # (ValidatePage, Finish...)
    else:
        result.append(("Form", Form.Events))
    controls = {c.name: c for c in document.form_def.controls}  # arrays: once
    for name in sorted(controls, key=str.lower):
        cls = CONTROL_TYPES.get(controls[name].type)
        result.append((name, cls.Events if cls is not None else ()))
    return result


def events_of(document, obj: str) -> tuple[str, ...]:
    return next((events for name, events in objects(document) if name == obj), ())


def defined_procedures(text: str) -> list[str]:
    """The methods of the form's class and the module's functions, in order."""
    from vp6 import formfile

    return list(dict.fromkeys(formfile.defined_methods(text) +
                              re.findall(r"^def\s+(\w+)", text, re.M)))


def general_procedures(document) -> list[str]:
    """The procedures listed under (General): every method or function that
    isn't an event handler (nor InitializeComponent)."""
    handlers = {f"{obj}_{event}" for obj, events in objects(document) for event in events}
    return [m for m in defined_procedures(document.text)
            if m not in handlers and m != "InitializeComponent"]


def handlers_written(document, obj: str) -> list[str]:
    """The events of ``obj`` that have a handler in the code, in order."""
    from vp6 import formfile

    defined = set(formfile.defined_methods(document.text))
    return [e for e in events_of(document, obj) if f"{obj}_{e}" in defined]


def default_event(document, obj: str) -> str:
    """The event choosing the object goes to (VB: its default event)."""
    if obj == "Form":
        from vp6.form import Form

        return Form.DefaultEvent
    if obj == "UserControl":
        return "Initialize"
    from vp6.controls import CONTROL_TYPES

    elements = document.form_def.elements(obj)
    cls = CONTROL_TYPES.get(elements[0].type) if elements else None
    return cls.DefaultEvent if cls is not None else ""


def event_args(document, obj: str, event: str) -> str:
    """A handler's parameters: a user control's own, or the control's declared
    ones."""
    from vp6.controls import CONTROL_TYPES, EVENT_ARGS
    from vp6.usercontrol import OWN_EVENT_ARGS

    if obj == "UserControl":
        return OWN_EVENT_ARGS.get(event, EVENT_ARGS.get(event, ""))
    elements = document.form_def.elements(obj) if is_form(document) else []
    cls = CONTROL_TYPES.get(elements[0].type) if elements else None
    declared = getattr(cls, "EventArgs", None) or {}
    return declared.get(event, EVENT_ARGS.get(event, ""))


def def_line(text: str, name: str) -> int | None:
    """The line of ``def name(`` (a method or a function), or None."""
    match = re.search(rf"^[ \t]*def\s+{re.escape(name)}\s*\(", text, re.M)
    return None if match is None else text.count("\n", 0, match.start())


def class_end_line(text: str, class_name: str) -> int:
    """The last non-blank line of the form's class body."""
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines)
                  if re.match(rf"class\s+{re.escape(class_name)}\b", line)), 0)
    last = start
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and not line[0].isspace() and not line.startswith("#"):
            break
        if line.strip():
            last = i
    return last


def handler_stub(document, obj: str, event: str) -> tuple[int, str] | None:
    """Where an event's new handler goes and what it is: (the line after which
    it is added, its text: a blank line, then the stub, its body ``pass``).
    None when it is there already, or for a module."""
    from vp6 import formfile

    if not event or not is_form(document) or \
            def_line(document.text, f"{obj}_{event}") is not None:
        return None
    stub = formfile.event_stub(obj, event, event_args(document, obj, event),
                               index=document.form_def.is_array(obj))
    return class_end_line(document.text, document.name), "\n\n" + stub.rstrip("\n")


def procedure_at(document, line: int) -> tuple[str, str]:
    """(object, procedure) of the procedure the line is in, as the lists show
    it: (General, Declarations) outside any; (General, name) for a procedure
    that isn't an event's handler."""
    lines = document.text.split("\n")
    name = None
    index = min(max(line, 0), len(lines) - 1)
    while index >= 0:
        text = lines[index]
        match = _DEF_LINE.match(text)
        if match:
            name = match.group(1)
            break
        if text.strip() and not text[0].isspace() and not text.startswith(("#", "@")):
            break  # reached module level code
        index -= 1
    if not name:
        return GENERAL, DECLARATIONS
    for candidate, events in objects(document):
        prefix = candidate + "_"
        if name.startswith(prefix) and name[len(prefix):] in events:
            return candidate, name[len(prefix):]
    return GENERAL, name


def members_of(cls) -> list[str]:
    """A class's public VB-style members (its properties and the capitalized
    names it and its bases define)."""
    names = set(getattr(cls, "_specs", {}))
    for klass in cls.__mro__:
        for name in vars(klass):
            if name[:1].isupper() and not name.startswith("_"):
                names.add(name)
    return sorted(names)


def complete(context: str, document) -> list[str]:
    """Completion candidates for the text before the cursor.

    ``self.``          -> the form's controls and members
    ``self.Command1.`` -> the members of a CommandButton
    anything else      -> vp6 names, keywords, builtins and words in the file
    """
    form_def = document.form_def if is_form(document) else None
    if context == "self.":
        from vp6.form import Form

        names = members_of(Form)
        if form_def:
            names += list(dict.fromkeys(c.name for c in form_def.controls))
        return names
    # self.Command1. or, for a control array, self.cmdDigit. / self.cmdDigit[i]. / (i).
    match = re.fullmatch(r"self\.(\w+)(\[[^\]]*\]|\([^)]*\))?\.", context)
    if match and form_def:
        from vp6.controls import CONTROL_TYPES, ControlArray

        elements = form_def.elements(match.group(1))
        if not elements:
            return []
        if form_def.is_array(match.group(1)) and not match.group(2):
            return members_of(ControlArray)
        return members_of(CONTROL_TYPES[elements[0].type])
    if context.endswith("."):
        return []
    words = set(re.findall(r"\b[A-Za-z_]\w{2,}\b", document.text))
    return sorted(vp6_names() | set(keyword.kwlist) | builtin_names() | words)
