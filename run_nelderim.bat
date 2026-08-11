@echo off
setlocal enabledelayedexpansion
REM ===========================================================================
REM run_nelderim.bat
REM
REM Double-click this file to launch the Nelderim Asset Pipeline GUI.
REM What it does, step by step:
REM   1. Looks for Python 3.10+ on your system (tries "python" then "py").
REM   2. Makes sure the "Pillow" library is installed (installs it if not).
REM   3. Starts the graphical tool (nelderim_gui.py).
REM   4. If anything goes wrong, it prints a plain-language explanation and
REM      keeps this window open (instead of vanishing instantly) so you can
REM      actually read what happened.
REM
REM You do not need to know Python to use this - if a step fails, the
REM message printed will tell you what to do next.
REM ===========================================================================

cd /d "%~dp0"

echo Nelderim Asset Pipeline - launcher
echo.

REM ---------------------------------------------------------------------
REM Step 1: find a usable Python
REM ---------------------------------------------------------------------
set "PYEXE="

where python >nul 2>nul
if %errorlevel%==0 (
    python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
    if !errorlevel!==0 (
        set "PYEXE=python"
    )
)

if not defined PYEXE (
    where py >nul 2>nul
    if !errorlevel!==0 (
        py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul
        if !errorlevel!==0 (
            set "PYEXE=py -3"
        )
    )
)

if not defined PYEXE (
    echo [PROBLEM] Python 3.10 or newer was not found on this computer.
    echo.
    echo What to do:
    echo   1. Go to https://www.python.org/downloads/ and download Python.
    echo   2. Run the installer.
    echo   3. IMPORTANT: on the first install screen, tick the box that
    echo      says "Add Python to PATH" before clicking Install. This is
    echo      the most common thing people forget, and without it this
    echo      launcher will not be able to find Python.
    echo   4. After installing, close this window and double-click
    echo      run_nelderim.bat again.
    echo.
    pause
    exit /b 1
)

echo Found Python: !PYEXE!
echo.

REM ---------------------------------------------------------------------
REM Step 2: make sure Pillow is installed
REM ---------------------------------------------------------------------
!PYEXE! -c "import PIL" >nul 2>nul
if not %errorlevel%==0 (
    echo Pillow ^(an image library this tool needs^) is not installed yet.
    echo Installing it now - this only happens once and may take a moment...
    echo.

    !PYEXE! -m pip install -r requirements.txt
    if not !errorlevel!==0 (
        echo.
        echo Trying again with --break-system-packages ^(needed on some setups^)...
        !PYEXE! -m pip install -r requirements.txt --break-system-packages
    )

    !PYEXE! -c "import PIL" >nul 2>nul
    if not !errorlevel!==0 (
        echo.
        echo [PROBLEM] Could not install Pillow automatically. The error
        echo above from pip explains why. Common fixes:
        echo   - Make sure you have an internet connection.
        echo   - Try running this .bat file as Administrator.
        echo   - Ask for help, with the error text above, at:
        echo     https://github.com/anthropics/claude-code/issues
        echo     ^(or wherever this project's support/issues page is^)
        echo.
        pause
        exit /b 1
    )
    echo Pillow installed successfully.
    echo.
)

REM ---------------------------------------------------------------------
REM Step 3: launch the GUI
REM ---------------------------------------------------------------------
echo Starting the Nelderim Asset Pipeline...
echo.
!PYEXE! nelderim_gui.py
set "EXITCODE=%errorlevel%"

REM ---------------------------------------------------------------------
REM Step 4: if it crashed, keep the window open so the error is readable
REM ---------------------------------------------------------------------
if not %EXITCODE%==0 (
    echo.
    echo [PROBLEM] The program closed with an error ^(exit code %EXITCODE%^).
    echo Scroll up to read the error message above for details.
    echo.
    pause
)

endlocal
