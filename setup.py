"""Building the wheel also makes VP6's help file (vp6/help/vp6.vp6help) from
the documents and the code: ``vp6.helpdocs`` with vp6help's maker. (The rest
of the build is in pyproject.toml.)"""

import importlib.util
import os
import sys

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = os.path.dirname(os.path.abspath(__file__))


class BuildWithHelp(build_py):
    def run(self):
        super().run()
        if getattr(self, "editable_mode", False):
            return  # (run from the source, VP6 makes its help when it's needed)
        try:
            import vp6help  # noqa: F401
        except ImportError:  # (the help system's source, beside VP6's)
            sys.path.insert(0, os.path.join(ROOT, "packages", "vp6help"))
        spec = importlib.util.spec_from_file_location(
            "vp6_helpdocs", os.path.join(ROOT, "vp6", "helpdocs.py"))
        helpdocs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helpdocs)
        if not all(os.path.isfile(os.path.join(ROOT, d)) for d in helpdocs.DOCUMENTS):
            return  # (built from a source distribution without the documents)
        output = os.path.join(self.build_lib, "vp6", "help", helpdocs.FILE_NAME)
        helpdocs.make_help(output, ROOT)


setup(cmdclass={"build_py": BuildWithHelp})
