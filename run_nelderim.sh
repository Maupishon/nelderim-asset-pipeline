#!/usr/bin/env bash
# ===========================================================================
# run_nelderim.sh
#
# Double-click (if your file manager allows it) or run from a terminal to
# launch the Nelderim Asset Pipeline GUI on Linux/macOS. Mirrors
# run_nelderim.bat's checks:
#   1. Finds a usable Python 3.10+.
#   2. Makes sure Pillow is installed (installs it if not).
#   3. Makes sure tkinter is importable - on many Linux distros this is a
#      separate OS package, not bundled with Python the way it is on
#      Windows, so this is checked explicitly with distro-specific
#      install hints rather than assumed.
#   4. Starts the GUI.
#   5. If anything fails, prints a plain-language explanation and waits
#      for a keypress before closing, so the terminal window doesn't just
#      vanish before you can read what happened (same reasoning as the
#      Windows .bat).
# ===========================================================================

set -u
cd "$(dirname "${BASH_SOURCE[0]}")"

pause_on_exit() {
    echo
    read -r -p "Press Enter to close..." _ignored
}

echo "Nelderim Asset Pipeline - launcher"
echo

# ---------------------------------------------------------------------
# Step 1: find a usable Python
# ---------------------------------------------------------------------
PYEXE=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >/dev/null 2>&1; then
            PYEXE="$candidate"
            break
        fi
    fi
done

if [ -z "$PYEXE" ]; then
    echo "[PROBLEM] Python 3.10 or newer was not found on this computer."
    echo
    echo "What to do:"
    echo "  Debian/Ubuntu:  sudo apt install python3"
    echo "  Fedora:         sudo dnf install python3"
    echo "  Arch:           sudo pacman -S python"
    echo "  macOS:          brew install python3   (or python.org installer)"
    echo
    echo "After installing, run this script again."
    pause_on_exit
    exit 1
fi

echo "Found Python: $PYEXE ($("$PYEXE" --version 2>&1))"
echo

# ---------------------------------------------------------------------
# Step 2: make sure tkinter is available (often a separate OS package
# on Linux, unlike the Windows python.org installer which bundles it)
# ---------------------------------------------------------------------
if ! "$PYEXE" -c "import tkinter" >/dev/null 2>&1; then
    echo "[PROBLEM] Python's 'tkinter' module (needed for the GUI window)"
    echo "is not installed. On Linux this is usually a separate package"
    echo "from Python itself:"
    echo "  Debian/Ubuntu:  sudo apt install python3-tk"
    echo "  Fedora:         sudo dnf install python3-tkinter"
    echo "  Arch:           sudo pacman -S tk"
    echo "  macOS:          tkinter should already be bundled - try"
    echo "                  reinstalling Python via python.org or brew."
    echo
    echo "After installing, run this script again."
    echo
    echo "(You can still use the command-line tools - nelderim_patch.py"
    echo "and nelderim_search.py - without tkinter; only the GUI needs it.)"
    pause_on_exit
    exit 1
fi

# ---------------------------------------------------------------------
# Step 3: make sure Pillow is installed
# ---------------------------------------------------------------------
if ! "$PYEXE" -c "import PIL" >/dev/null 2>&1; then
    echo "Pillow (an image library this tool needs) is not installed yet."
    echo "Installing it now - this only happens once and may take a moment..."
    echo

    if ! "$PYEXE" -m pip install -r requirements.txt; then
        echo
        echo "Trying again with --break-system-packages (needed on some setups)..."
        "$PYEXE" -m pip install -r requirements.txt --break-system-packages
    fi

    if ! "$PYEXE" -c "import PIL" >/dev/null 2>&1; then
        echo
        echo "[PROBLEM] Could not install Pillow automatically. The error"
        echo "above from pip explains why. Common fixes:"
        echo "  - Make sure you have an internet connection."
        echo "  - Try: $PYEXE -m pip install --user Pillow"
        echo "  - On some distros: sudo apt install python3-pil (or your"
        echo "    distro's equivalent), instead of pip."
        echo
        pause_on_exit
        exit 1
    fi
    echo "Pillow installed successfully."
    echo
fi

# ---------------------------------------------------------------------
# Step 4: launch the GUI
# ---------------------------------------------------------------------
echo "Starting the Nelderim Asset Pipeline..."
echo
"$PYEXE" nelderim_gui.py
EXITCODE=$?

# ---------------------------------------------------------------------
# Step 5: if it crashed, keep the window open so the error is readable
# ---------------------------------------------------------------------
if [ "$EXITCODE" -ne 0 ]; then
    echo
    echo "[PROBLEM] The program closed with an error (exit code $EXITCODE)."
    echo "Scroll up to read the error message above for details."
    pause_on_exit
fi
