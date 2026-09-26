"""Kitchen Sink: Sub Main starts the program."""

from vp6 import *
from Form1 import Form1


def Main():
    Debug.Print("Kitchen Sink starting")
    # Show the startup form and run until it is closed
    run(Form1)


if __name__ == "__main__":
    Main()
