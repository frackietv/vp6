import pytest

from vp6 import formfile
from vp6.formfile import ControlDef, FormDef, FormFileError


def test_new_form_round_trip():
    source = formfile.new_form_source("Form1")
    compile(source, "Form1.py", "exec")
    form = formfile.parse(source)
    assert form.class_name == "Form1"
    assert form.props == {"Caption": "Form1", "Width": 480, "Height": 360}
    assert formfile.is_form_source(source)


def test_replace_region_keeps_user_code():
    source = formfile.new_form_source("Form1").replace(
        "        pass", "        print('user code')")
    form = formfile.parse(source)
    form.controls.append(ControlDef("Frame", "Frame1", None,
                                    {"Caption": "F", "Left": 8, "Top": 8, "Width": 100,
                                     "Height": 80}))
    form.controls.append(ControlDef("CommandButton", "Command1", "Frame1",
                                    {"Caption": "Go", "Left": 8, "Top": 16, "Width": 80,
                                     "Height": 30, "BackColor": 0x00FF00}))
    new_source = formfile.replace_region(source, form)
    assert "print('user code')" in new_source
    assert "self.Command1 = CommandButton(self.Frame1, Caption='Go'" in new_source
    assert "BackColor=0x00FF00" in new_source
    assert formfile.parse(new_source) == form
    compile(new_source, "Form1.py", "exec")


def test_defaults_are_omitted_but_always_props_kept():
    form = FormDef("F", {"Caption": "F", "Width": 480, "Height": 360, "BorderStyle": 2},
                   [ControlDef("Label", "Label1", None,
                               {"Caption": "", "Left": 0, "Top": 0, "Width": 97,
                                "Height": 25, "Alignment": 0, "Visible": True})])
    region = formfile.generate_region(form)
    assert "BorderStyle" not in region
    assert "Visible" not in region and "Alignment" not in region
    assert "Label(self, Caption='', Left=0, Top=0, Width=97, Height=25)" in region


def test_long_lines_are_wrapped():
    form = FormDef("F", {}, [ControlDef("TextBox", "Text1", None, {
        "Text": "x" * 40, "Left": 1, "Top": 2, "Width": 3, "Height": 4, "MultiLine": True,
        "ScrollBars": 2, "ToolTipText": "tip"})])
    region = formfile.generate_region(form)
    assert all(len(line) <= formfile.MAX_LINE for line in region.splitlines())
    assert formfile.parse_region_body(
        "\n".join(l[4:] for l in region.splitlines()[1:-1]), "F") == form


@pytest.mark.parametrize("body, message", [
    ("def InitializeComponent(self):\n    print('x')\n", "Unexpected statement"),
    ("def InitializeComponent(self):\n    self.B = Bogus(self)\n", "Unknown control type"),
    ("def InitializeComponent(self):\n    self.C = Label(self.Nope)\n", "not defined"),
    ("def InitializeComponent(self):\n    self.Caption = compute()\n", "literals"),
    ("x = 1\n", "no InitializeComponent"),
])
def test_invalid_regions(body, message):
    with pytest.raises(FormFileError, match=message):
        formfile.parse_region_body(body, "F")


def test_missing_endregion():
    source = "class F(Form):\n    # region VP6 Designer\n    def InitializeComponent(self):\n"
    with pytest.raises(FormFileError):
        formfile.parse(source)


def test_rename_control_references_skips_region():
    source = formfile.new_form_source("Form1")
    form = formfile.parse(source)
    form.controls.append(ControlDef("CommandButton", "Command1", None, {"Caption": "Command1"}))
    source = formfile.replace_region(source, form)
    source += (
        "\n    def Command1_Click(self):\n        self.Command1.Caption = 'x'\n"
        "    def Command10_Click(self):\n        pass\n"
    )
    renamed = formfile.rename_control_references(source, "Command1", "cmdOK")
    assert "def cmdOK_Click(self):" in renamed
    assert "self.cmdOK.Caption" in renamed
    assert "def Command10_Click" in renamed  # not a prefix match
    assert "self.Command1 = CommandButton" in renamed  # region is regenerated separately


def test_rename_form_class():
    source = formfile.new_form_source("Form1")
    renamed = formfile.rename_form_class(source, "Form1", "frmMain")
    assert "class frmMain(Form):" in renamed and "run(frmMain)" in renamed
    assert formfile.find_form_class(renamed) == "frmMain"


def test_console_module_template_runs(capsys, monkeypatch):
    namespace = {}
    exec(formfile.new_module_source(with_main=True, console=True), namespace)
    monkeypatch.setattr("builtins.input", lambda prompt: "Ada")
    namespace["Main"]()
    assert "Hello, Ada!" in capsys.readouterr().out


def test_rename_class_and_module_references():
    source = ("from Form1 import Form1\nimport Module1\n\n\ndef Main():\n"
              "    run(Form1)\n    Module1.helper(Form1)\n    x.Form1 = 1\n")
    renamed = formfile.rename_class_references(source, "Form1", "frmMain")
    assert "from Form1 import frmMain\n" in renamed  # the module (file) keeps its name
    assert "run(frmMain)" in renamed and "Module1.helper(frmMain)" in renamed
    assert "x.Form1 = 1" in renamed  # attributes of other objects are left alone
    renamed = formfile.rename_module_references(source, "Module1", "Utils")
    assert "import Utils\n" in renamed and "Utils.helper(Form1)" in renamed
    assert "from Form1 import Form1" in renamed
    assert formfile.rename_module_references("from Module1 import Main\n", "Module1", "U") \
        == "from U import Main\n"
