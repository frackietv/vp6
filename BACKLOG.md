# VP6 backlog

- **[Controls]** Markdown edit: control must accept plain-text markdown input and syntax highlight it.  The control must also be able to edit text in visuabl mode, and be usable as markdown preview, where the markdown is rendered visually.  KitchenSik should have a page with three markdown controls on a single page, one in plain editor mode, another in visual editor mode, and third in preview mode.  Changes in plain or visual editor controls must be reflected in the other editor and in the preview controls, too.
- **[IDE]** Designer window frames with rounded bottom corners on macOS
- **[Appearance]** Per-window title bar color: a forced Light or Dark form still gets a title bar in the OS appearance, since Qt can't set it per window on macOS
- **[IDE - Debugging]** A debugger: breakpoints, stepping, watches, and evaluating expressions in the Immediate window while the program is paused
- **[IDE - Debugging]** Editing code while the program is paused
- **[IDE - Help]** IDE needs a help system that works like the old .chm help.  The help should contain all documentation for VB6, including api and development guides, and should support table of contents, index, and search. 
- **[IDE - Terminal]** Add a terminal emulator panel (default position same as immediate panel) to allow a shell to be opened in the IDE.
- **[IDE - AI]** Add Claude integration to allow use of Claude straight from the IDE.  By default Claude panel should go same place as the output or immediate.
- **[Self-hosting]** Write the VP6 IDE in VP6 itself; blocked by the self-hosting items above
