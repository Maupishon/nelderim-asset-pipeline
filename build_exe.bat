@echo off
REM Builds dist\Nelderim\ (Nelderim.exe + app\ + uo3d\ + pipeline scripts) with PyInstaller. Run on Windows.
cd /d "%~dp0"
python -m pip install pyinstaller pillow numpy || goto :fail
python -m PyInstaller --onefile --noconfirm --name Nelderim ^
  --hidden-import nelderim_app --hidden-import nelderim_hub --hidden-import nelderim_hub_ui --hidden-import uo3d_py ^
  --hidden-import nelderim_patch --hidden-import nelderim_search --hidden-import nelderim_core --hidden-import uopatch ^
  --hidden-import uop_gump_patch --hidden-import uop_probe --hidden-import vd_inject ^
  --collect-submodules uo3d --hidden-import numpy --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFilter --hidden-import PIL.ImageOps --hidden-import PIL.ImageChops ^
  --hidden-import argparse --hidden-import hashlib --hidden-import struct --hidden-import math --hidden-import csv ^
  nelderim.py || goto :fail
if exist dist\Nelderim rmdir /s /q dist\Nelderim
mkdir dist\Nelderim
move /y dist\Nelderim.exe dist\Nelderim\ >nul
for %%f in (nelderim_app.py nelderim_hub.py nelderim_hub_ui.py uo3d_py.py nelderim_core.py nelderim_gui.py nelderim_patch.py nelderim_search.py uopatch.py uop_gump_patch.py uop_probe.py vd_inject.py requirements.txt README.md CLAUDE.md) do copy /y %%f dist\Nelderim\ >nul
xcopy /e /i /y app dist\Nelderim\app >nul
xcopy /e /i /y client-config dist\Nelderim\client-config >nul
xcopy /e /i /y examples dist\Nelderim\examples >nul
xcopy /e /i /y uo3d dist\Nelderim\uo3d >nul
if exist dist\Nelderim\uo3d\__pycache__ rmdir /s /q dist\Nelderim\uo3d\__pycache__
echo.
echo Done: dist\Nelderim\Nelderim.exe
exit /b 0
:fail
echo BUILD FAILED
pause
exit /b 1
