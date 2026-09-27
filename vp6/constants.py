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
