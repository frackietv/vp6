# VP6

VB6-style programming for Python: an IDE where you draw forms,
set properties, double-click a control to write its event handler and press
**F5** to run, plus the `vp6` framework that makes the resulting code work
(also usable without the IDE).

Built on PySide6 (Qt).

## Note

This project stated as a weekend exercise in using Claude for code
development, initially took three days, during which it consumed all of my
weekly token usage.  It is 99.9% vibe-coded, tested, and documented (this
sections is the only documentation written by a human).  None of the
documentation has been verified by me, so your milage may vary.

All features and controls of VP6 should be demonstrated in the Kitchen
Sink project; any of the manual testing and verification was ad-hoc and used 
the Kitchen Sink project.

### Disclaimer

Given the above, it is particularly important to note:

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.**

## Getting started

From PyPI:

```bash
pip install vp6                      # then: vp6 (the IDE), vp6-run Project.vp6p
pip install "vp6[make]"              # also vp6-make --exe: standalone executables
```

From the source:

```bash
python3 -m venv .venv
.venv/bin/pip install -e packages/vp6help   # the help system (vp6help), first
.venv/bin/pip install -e packages/vp6edu    # the courses (vp6edu), also first
.venv/bin/pip install -e ".[dev]"
.venv/bin/vp6                       # start the IDE (or: python -m vp6.ide)
.venv/bin/vp6 path/to/Project.vp6p      # open a project
.venv/bin/vp6 --no-splash           # without the two-second splash screen
.venv/bin/vp6 --help                # the command line options (vp6-run and vp6-make too)
```

To package a program as a wheel for pip (Project > Build Wheel, or `vp6-make
Project.vp6p`), nothing more is needed; see [Building a wheel](docs/api.md#building-a-wheel).
To make standalone executables (File > Make Executable…, or `vp6-make --exe
Project.vp6p`), install PyInstaller too: `.venv/bin/pip install -e ".[dev,make]"`.
Executables are made for the system they are made on (macOS, Windows,
Linux); see [Making an executable](docs/api.md#making-an-executable).

The IDE opens with a VB-style **New Project** dialog. A Standard EXE or a
Console Application has `Form1` and `Module1` and starts in `Sub Main`, the
`Main()` function in `Module1`:

* *Standard EXE:* `Main()` shows `Form1` with `run(Form1)`.
* *Console Application:* `Main()` talks through `print()` / `input()`.

The samples are in the **Sample Projects** folder:

* *Kitchen Sink:* a demo project showing every VP6 control and feature,
  explorer-style: choose a topic in the tree on the left and its page, a form
  of its own, is shown beside it. Open the pages to see how things work, and
  copy code out of them.
* *Graphics > Projection:* a model turning in a parallel projection on a
  single form (elevation, plan, isometric, dimetric or trimetric orthographic;
  military, cavalier or top-down oblique): a cube, a pyramid, a torus, a
  house, a few boxes or a downtown, solid or as a wireframe, with the axes
  behind it; drag an axis to move just that one, the space around to turn
  them all, the model to turn it; sliders for its roll, pitch and tumble and
  their rates, and the angles between the axes.
* *Graphics > Perspectives:* the same models in 1-, 2- or 3-point linear
  perspective, or 4-, 5- or 6-point curvilinear perspective (cylindrical,
  fisheye, the whole sphere), with perspective lines to the vanishing points
  and the horizon; drag a vanishing point to move it, the space around to
  turn the scene, the model to turn it; put any axis's vanishing point at
  infinity up, down, left or right; move the eye nearer, farther or inside
  the model.

## Further documentation

| Document | Read it to… |
|---|---|
| [ide.md](docs/ide.md) | understand how to use the IDE |
| [architecture.md](docs/architecture.md) | understand how VP6 is designed: runtime vs IDE, processes, data flows, file formats, color schemes, settings |
| [source-reference.md](docs/source-reference.md) | find what each source file contains and how it connects to the rest |
| [api.md](docs/api.md) | write VP6 programs: forms, controls, properties, events, functions, constants |
| [development-guide.md](docs/development-guide.md) | set up a dev environment and extend VP6: new properties, events, controls, IDE commands, panels, themes, settings, frame styles, icons; testing and pitfalls |
| [education.md](docs/education.md) | write lessons for vp6edu's courses: `lesson.md` with maths, `exercises.py` and the answer kinds, the lab project, attribution, `vp6edu-check` |

**Suggested reading order.**

* **Using VP6:** the project [ide.md](docs/ide.md), then [api.md](docs/api.md).
* **Working on VP6:** [architecture.md](docs/architecture.md), then
  [development-guide.md](docs/development-guide.md), using
  [source-reference.md](docs/source-reference.md) as a map.


## Features and backlog

[FEATURES.md](FEATURES.md) lists everything VP6 implements.
[BACKLOG.md](BACKLOG.md) lists what isn't implemented yet.

## Development process

Claude AI has been used to vibe-code this project.  The project was initially
described in [BACKLOG.md](BACKLOG.md) and Claude was used to implement the
features contained, as well as to analyze the backlog to reorder or group the
features, as well as to come up with new backlog items.
