# VP6 backlog

- **[Language and runtime]** `Printer` object and `Printers` collection: printing text and graphics (with the drawing methods above)
- **[IDE]** Find and Replace in all files of the project (today: the current code window only)
- **[IDE]** Designer and Properties window: the Properties window's Categorized view (VB's Alphabetic / Categorized tabs); locking controls in the designer (Format > Lock Controls)
- **[IDE]** Object Browser: the classes, members, events and constants of `vp6` and of the project's forms and modules
- **[IDE]** Project files: Save Project As (copying a project to a new folder); renaming and deleting files from the Project Explorer's Project view (today Remove only takes a file out of the project; the Files view can already rename and delete files on disk)
- **[Language and runtime]** Light and dark: an event when the OS switches between light and dark and a way to ask which one is active (self-hosting: repainting custom-drawn surfaces and icons); picking up a macOS light/dark change live for System forms in the designer while the IDE is forced to Light or Dark (today they update on the next redraw); programs started from the IDE with the "IDE" color scheme following later IDE theme changes (today: its appearance at launch only)
- **[Language and runtime]** Form kinds: MDI forms (MDI parent and child forms); borderless popup forms that don't take the focus from the form that opened them (self-hosting: the code completion list)
- **[Language and runtime]** Starting a program asynchronously with output, exit and error events and a way to write to its stdin (a Process object beyond VB's `Shell`) (self-hosting: F5 and the Immediate window)
- **[Language and runtime]** Twips and VB's `ScaleMode`; VP6 uses pixels only
- **[Controls]** Data-bound controls
- **[IDE]** Designer window frames with rounded bottom corners on macOS
- **[Appearance]** Per-window title bar color: a forced Light or Dark form still gets a title bar in the OS appearance, since Qt can't set it per window on macOS
- **[IDE - Debugging]** A debugger: breakpoints, stepping, watches, and evaluating expressions in the Immediate window while the program is paused
- **[IDE - Debugging]** Editing code while the program is paused
- **[Self-hosting]** Write the VP6 IDE in VP6 itself; blocked by the self-hosting items above and by existing backlog items: MDI forms
- **[IDE - Help]** IDE needs a help system that works like the old .chm help.  The help should contain all documentation for VB6, including api and development guides, and should support table of contents, index, and search. 
- **[IDE - Terminal]** Add a terminal emulator panel (default position same as immediate panel) to allow a shell to be opened in the IDE.
- **[IDE - AI]** Add Claude integration to allow use of Claude straight from the IDE.  By default Claude panel should go same place as the output or immediate.
