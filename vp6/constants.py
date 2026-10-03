"""VB6-compatible constants (vpOK, vpYesNo, vpKeyReturn, ...)."""

# --- MsgBox buttons ---------------------------------------------------------
vpOKOnly = 0
vpOKCancel = 1
vpAbortRetryIgnore = 2
vpYesNoCancel = 3
vpYesNo = 4
vpRetryCancel = 5

# --- MsgBox icons -----------------------------------------------------------
vpCritical = 16
vpQuestion = 32
vpExclamation = 48
vpInformation = 64

# --- MsgBox default button --------------------------------------------------
vpDefaultButton1 = 0
vpDefaultButton2 = 256
vpDefaultButton3 = 512

# --- MsgBox results ---------------------------------------------------------
vpOK = 1
vpCancel = 2
vpAbort = 3
vpRetry = 4
vpIgnore = 5
vpYes = 6
vpNo = 7

# --- Form.Show --------------------------------------------------------------
vpModeless = 0
vpModal = 1

# --- CheckBox.Value ---------------------------------------------------------
vpUnchecked = 0
vpChecked = 1
vpGrayed = 2

# --- Mouse buttons / shift state -------------------------------------------
vpLeftButton = 1
vpRightButton = 2
vpMiddleButton = 4
vpShiftMask = 1
vpCtrlMask = 2
vpAltMask = 4

# --- Alignment --------------------------------------------------------------
vpLeftJustify = 0
vpRightJustify = 1
vpCenter = 2

# --- Form.BorderStyle -------------------------------------------------------
vpBSNone = 0
vpFixedSingle = 1
vpSizable = 2
vpFixedDialog = 3
vpFixedToolWindow = 4
vpSizableToolWindow = 5

# --- Form.WindowState -------------------------------------------------------
vpNormal = 0
vpMinimized = 1
vpMaximized = 2

# --- Form.StartUpPosition ---------------------------------------------------
vpStartUpManual = 0
vpStartUpOwner = 1
vpStartUpScreen = 2
vpStartUpWindowsDefault = 3

# --- Strings ----------------------------------------------------------------
vpCr = "\r"
vpLf = "\n"
vpCrLf = "\r\n"
vpNewLine = "\n"
vpTab = "\t"
vpNullString = ""

# --- Menu.NegotiatePosition ------------------------------------------------------
vpNegotiateNone = 0
vpNegotiateLeft = 1
vpNegotiateMiddle = 2
vpNegotiateRight = 3

# --- Label.BackStyle -------------------------------------------------------------
vpTransparent = 0
vpOpaque = 1

# --- Shape.Shape ------------------------------------------------------------------
vpShapeRectangle = 0
vpShapeSquare = 1
vpShapeOval = 2
vpShapeCircle = 3
vpShapeRoundedRectangle = 4
vpShapeRoundedSquare = 5

# --- FillStyle (Shape, Form, PictureBox) -------------------------------------------
vpFSSolid = 0
vpFSTransparent = 1
vpHorizontalLine = 2
vpVerticalLine = 3
vpUpwardDiagonal = 4
vpDownwardDiagonal = 5
vpCross = 6
vpDiagonalCross = 7

# --- BorderStyle (Shape, Line) -----------------------------------------------------
vpBSTransparent = 0
vpBSSolid = 1
vpBSDash = 2
vpBSDot = 3
vpBSDashDot = 4
vpBSDashDotDot = 5
vpBSInsideSolid = 6

# --- DrawStyle (Form, PictureBox) ---------------------------------------------------
vpSolid = 0
vpDash = 1
vpDot = 2
vpDashDot = 3
vpDashDotDot = 4
vpInvisible = 5
vpInsideSolid = 6

# --- Label.TextFormat -----------------------------------------------------------
vpPlainText = 0
vpRichText = 1
vpMarkdown = 2

# --- ScrollBars (TextBox, PictureBox) -------------------------------------------
vpSBNone = 0
vpHorizontal = 1
vpVertical = 2
vpBoth = 3

# --- PictureBox.Align ----------------------------------------------------------
vpAlignNone = 0
vpAlignTop = 1
vpAlignBottom = 2
vpAlignLeft = 3
vpAlignRight = 4
vpAlignFill = 5

# --- TreeView: Nodes.Add relationship ----------------------------------------
vpTvwFirst = 0
vpTvwLast = 1
vpTvwNext = 2
vpTvwPrevious = 3
vpTvwChild = 4

# --- TreeView.LineStyle -------------------------------------------------------
vpTvwTreeLines = 0
vpTvwRootLines = 1

# --- Orientation (ProgressBar, Slider, UpDown) ----------------------------------
vpOrientationHorizontal = 0
vpOrientationVertical = 1

# --- Slider.TickStyle ------------------------------------------------------------
vpTickBottomRight = 0
vpTickTopLeft = 1
vpTickBoth = 2
vpTickNone = 3

# --- StatusBar.Style -------------------------------------------------------------
vpSbrNormal = 0
vpSbrSimple = 1

# --- Panel.Style (StatusBar) -----------------------------------------------------
vpSbrText = 0
vpSbrCaps = 1
vpSbrNum = 2
vpSbrIns = 3
vpSbrScrl = 4
vpSbrTime = 5
vpSbrDate = 6

# --- Panel.AutoSize (StatusBar) --------------------------------------------------
vpSbrNoAutoSize = 0
vpSbrSpring = 1
vpSbrContents = 2

# --- Panel.Alignment (StatusBar) -------------------------------------------------
vpSbrLeft = 0
vpSbrCenter = 1
vpSbrRight = 2

# --- TabStrip.Placement ----------------------------------------------------------
vpTabPlacementTop = 0
vpTabPlacementBottom = 1
vpTabPlacementLeft = 2
vpTabPlacementRight = 3

# --- Button.Style (Toolbar) -------------------------------------------------------
vpTbrDefault = 0
vpTbrCheck = 1
vpTbrButtonGroup = 2
vpTbrSeparator = 3

# --- Button.Value (Toolbar) -------------------------------------------------------
vpTbrUnpressed = 0
vpTbrPressed = 1

# --- Toolbar.TextAlignment --------------------------------------------------------
vpTbrTextAlignBottom = 0
vpTbrTextAlignRight = 1

# --- ListView.View ---------------------------------------------------------------
vpLvwIcon = 0
vpLvwSmallIcon = 1
vpLvwList = 2
vpLvwReport = 3

# --- ColumnHeader.Alignment (ListView) ------------------------------------------
vpLvwColumnLeft = 0
vpLvwColumnRight = 1
vpLvwColumnCenter = 2

# --- ListView.SortOrder ---------------------------------------------------------
vpLvwAscending = 0
vpLvwDescending = 1

# --- RichTextBox: LoadFile / SaveFile file types ----------------------------------
vpRtfHTML = 0
vpRtfText = 1

# --- RichTextBox.Find options (added together) ------------------------------------
vpRtfWholeWord = 2
vpRtfMatchCase = 4
vpRtfNoHighlight = 8

# --- FlexGrid: ColEditor / CellEditor -------------------------------------------
vpGridEditNone = 0
vpGridEditText = 1
vpGridEditList = 2
vpGridEditCheck = 3
vpGridEditColor = 4
vpGridEditButton = 5

# --- FlexGrid.Sort ----------------------------------------------------------------
vpGridSortGenericAscending = 1
vpGridSortGenericDescending = 2
vpGridSortNumericAscending = 3
vpGridSortNumericDescending = 4
vpGridSortStringNoCaseAscending = 5
vpGridSortStringNoCaseDescending = 6
vpGridSortStringAscending = 7
vpGridSortStringDescending = 8

# --- FlexGrid.SelectionMode ----------------------------------------------------------
vpGridSelectionFree = 0
vpGridSelectionByRow = 1
vpGridSelectionByColumn = 2

# --- PopupMenu flags (added together) ------------------------------------------------
vpPopupMenuLeftAlign = 0
vpPopupMenuCenterAlign = 4
vpPopupMenuRightAlign = 8
vpPopupMenuLeftButton = 0
vpPopupMenuRightButton = 2

# --- Form_QueryUnload: UnloadMode --------------------------------------------------------
vpFormControlMenu = 0  # the user closed it (its close button, Alt+F4, Cmd+W)
vpFormCode = 1  # Unload in code
vpAppWindows = 2  # the session is ending (not reported yet)
vpAppTaskManager = 3  # the program is being stopped (Ctrl+C in its terminal)
vpFormMDIForm = 4  # its MDI form is closing
vpFormOwner = 5  # the form it is shown in (ShowIn) is closing

# --- MousePointer (controls, forms, Screen) ------------------------------------------
vpDefault = 0
vpArrow = 1
vpCrosshair = 2
vpIbeam = 3
vpIconPointer = 4
vpSizePointer = 5
vpSizeNESW = 6
vpSizeNS = 7
vpSizeNWSE = 8
vpSizeWE = 9
vpUpArrow = 10
vpHourglass = 11
vpNoDrop = 12
vpArrowHourglass = 13
vpArrowQuestion = 14
vpSizeAll = 15
vpCustom = 99

# --- Drag and drop -------------------------------------------------------------------
vpManual = 0  # DragMode
vpAutomatic = 1
vpCancelDrag = 0  # Drag's Action (VB's vbCancel: vpCancel is MsgBox's)
vpBeginDrag = 1
vpEndDrag = 2
vpEnter = 0  # DragOver's and OLEDragOver's State
vpLeave = 1
vpOver = 2
vpOLEDropNone = 0  # OLEDropMode
vpOLEDropManual = 1

# --- Shell: WindowStyle (accepted, as in VB; programs open their windows themselves) ----
vpHide = 0
vpNormalFocus = 1
vpMinimizedFocus = 2
vpMaximizedFocus = 3
vpNormalNoFocus = 4
vpMinimizedNoFocus = 6

# --- ScaleMode (Form, PictureBox, Printer, Picture; ScaleX / ScaleY) -----------------------
vpUser = 0
vpTwips = 1
vpPoints = 2
vpPixels = 3
vpCharacters = 4
vpInches = 5
vpMillimeters = 6
vpCentimeters = 7
vpHimetric = 8

# --- Terminal.TerminalType ----------------------------------------------------------------
vpTermXterm256Color = 0
vpTermXterm = 1
vpTermVT100 = 2
vpTermVT102 = 3
vpTermVT220 = 4
vpTermAnsi = 5

# --- MDIForm.Arrange -------------------------------------------------------------------
vpCascade = 0
vpTileHorizontal = 1
vpTileVertical = 2
vpArrangeIcons = 3

# --- Printer.Orientation ---------------------------------------------------------------
vpPRORPortrait = 1
vpPRORLandscape = 2

# --- Printer.PaperSize ----------------------------------------------------------------
vpPRPSLetter = 1
vpPRPSTabloid = 3
vpPRPSLedger = 4
vpPRPSLegal = 5
vpPRPSExecutive = 7
vpPRPSA3 = 8
vpPRPSA4 = 9
vpPRPSA5 = 11
vpPRPSB5 = 13
vpPRPSEnv10 = 20
vpPRPSEnvDL = 27

# --- Printer.ColorMode and Printer.Duplex ------------------------------------------------
vpPRCMMonochrome = 1
vpPRCMColor = 2
vpPRDPSimplex = 1
vpPRDPHorizontal = 2
vpPRDPVertical = 3

# --- Clipboard and OLEDragDrop's Data: formats ---------------------------------------
vpCFText = 1
vpCFBitmap = 2  # a picture
vpCFDIB = 8  # a picture too (VB's device-independent bitmap)
vpCFFiles = 15  # files (from another program)
vpCFRTF = -16639  # rich text

# --- Picture.Type -------------------------------------------------------------------
vpPicTypeNone = 0
vpPicTypeBitmap = 1
vpDropEffectNone = 0  # OLEDragOver's Effect
vpDropEffectCopy = 1
vpDropEffectMove = 2

# --- CommonDialog Flags (added together) ---------------------------------------------
vpOFNReadOnly = 0x1  # Open, Save As
vpOFNOverwritePrompt = 0x2
vpOFNHideReadOnly = 0x4
vpOFNNoChangeDir = 0x8
vpOFNAllowMultiselect = 0x200
vpOFNPathMustExist = 0x800
vpOFNFileMustExist = 0x1000
vpOFNCreatePrompt = 0x2000
vpOFNExplorer = 0x80000
vpCCRGBInit = 0x1  # Color
vpCCFullOpen = 0x2
vpCFScreenFonts = 0x1  # Font
vpCFEffects = 0x100
vpPDAllPages = 0x0  # ShowPrinter
vpPDSelection = 0x1
vpPDPageNums = 0x2
vpCdlCancel = 32755  # the error a cancelled dialog raises with CancelError (DialogCancelled)

# --- Key codes (KeyDown / KeyUp) -------------------------------------------
vpKeyBack = 8
vpKeyTab = 9
vpKeyReturn = 13
vpKeyShift = 16
vpKeyControl = 17
vpKeyMenu = 18
vpKeyPause = 19
vpKeyCapital = 20
vpKeyEscape = 27
vpKeySpace = 32
vpKeyPageUp = 33
vpKeyPageDown = 34
vpKeyEnd = 35
vpKeyHome = 36
vpKeyLeft = 37
vpKeyUp = 38
vpKeyRight = 39
vpKeyDown = 40
vpKeyInsert = 45
vpKeyDelete = 46

for _i in range(10):
    globals()[f"vpKey{_i}"] = 48 + _i
for _i in range(26):
    globals()[f"vpKey{chr(65 + _i)}"] = 65 + _i
for _i in range(1, 13):
    globals()[f"vpKeyF{_i}"] = 111 + _i
del _i

__all__ = [name for name in globals() if name.startswith("vp")]
