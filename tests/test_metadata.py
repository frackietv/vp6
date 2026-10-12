"""The control metadata API: ControlTypes (the Toolbox's order and categories),
ControlCategories, ControlInfo (properties, events and their arguments, default
size, icon) for the controls, Menu, Form and MDIForm."""

import pytest

from vp6 import ControlCategories, ControlInfo, ControlTypes, Picture
from vp6.controls import CONTROL_TYPES
from vp6.metadata import TOOLBOX_CATEGORIES, category_of_type


def test_control_types_in_the_toolboxs_order(qapp):
    types = ControlTypes()
    assert types[:3] == ["Label", "TextBox", "CommandButton"]
    assert "Menu" not in types and set(types) == {name for name, cls in CONTROL_TYPES.items()
                                                  if cls.InToolbox}
    assert ControlTypes("System") == ["Timer", "Process", "Terminal", "Winsock"]
    assert ControlTypes("Nothing") == []
    categories = ControlCategories()
    assert categories[:2] == ["Common", "Input"] and "Other" not in categories
    assert categories == [title for title, _names in TOOLBOX_CATEGORIES]
    assert category_of_type("FileWatcher") == "Files" and category_of_type("Mine") == "Other"


def test_control_info(qapp):
    info = ControlInfo("TextBox")
    assert info.Name == "TextBox" and info.Category == "Common" and info.InToolbox
    assert info.DefaultSize == CONTROL_TYPES["TextBox"].DefaultSize
    assert info.DefaultEvent == "Change" and not info.IsContainer
    assert info.Description.startswith("VB's TextBox") or info.Description
    names = [p.Name for p in info.Properties]
    assert names == sorted(names, key=str.lower) and "MaxLength" in names
    text = info.Property("maxlength")
    assert text.Kind == "int" and text.Default == 0 and text.Description
    assert info.Property("Alignment").Choices[0] == (0, "0 - Left Justify")
    assert info.Property("Text").Category == "Text"
    key_down = info.Event("KeyDown")
    assert key_down.Arguments == ["KeyCode", "Shift"] and not key_down.IsDefault
    assert info.Event("Change").IsDefault and info.Event("Change").Arguments == []
    with pytest.raises(KeyError):
        info.Property("Nonesuch")
    with pytest.raises(KeyError):
        info.Event("Nonesuch")
    with pytest.raises(KeyError):
        ControlInfo("Nonesuch")
    assert ControlInfo("Frame").IsContainer
    assert ControlInfo("Winsock").Event("Error").Arguments == ["Number", "Description"]
    assert ControlInfo("Data").Event("Validate").Arguments == ["Action", "Save"]  # (its own)
    assert not ControlInfo("Menu").InToolbox
    form = ControlInfo("Form")
    assert form.Category == "Forms" and form.Event("QueryUnload").Arguments == ["UnloadMode"]
    assert "AutoShowChildren" in [p.Name for p in ControlInfo("MDIForm").Properties]
    icon = info.Icon
    assert isinstance(icon, Picture) and icon.Width >= 24 and repr(info) and \
        repr(text) and repr(key_down)
