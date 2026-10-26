"""What the IDE (``vp6.ide``) does that needs no Qt, kept apart from its
windows so it can be tested (and used) without them.

Nothing here imports PySide6 when it is imported (a test checks): the
command line, a file's outline, searching and replacing in texts, the Menu
Editor's entries, the Object Browser's library, the code window's objects and
procedures, the editor themes, the project templates, Claude's and Codex's
sessions and protocols, and the debugger's descriptions. Some functions use
VP6 itself when they are called (the Object Browser lists VP6's classes).

Settings (the names given to sessions, the commands chosen) go through a
``Settings`` object the IDE gives (``settings.use``): by default the IDE's
QSettings.
"""
