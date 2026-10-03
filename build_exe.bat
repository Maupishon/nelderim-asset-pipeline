@echo off
REM Builds dist\Nelderim\ (Nelderim.exe + app\ + lab\ + pipeline\ + uo3d\) with PyInstaller. Run on Windows.
cd /d "%~dp0"
python -m pip install pyinstaller pillow numpy || goto :fail
python -m PyInstaller --onefile --noconfirm --name Nelderim --paths lab --paths pipeline ^
  --hidden-import nelderim_app --hidden-import nelderim_hub ^
  --hidden-import nelderim_patch --hidden-import nelderim_search --hidden-import nelderim_core --hidden-import uopatch ^
  --hidden-import uop_gump_patch --hidden-import uop_probe --hidden-import vd_inject --hidden-import anim_wire ^
  --collect-submodules uo3d --hidden-import numpy --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFilter --hidden-import PIL.ImageOps --hidden-import PIL.ImageChops ^
  --hidden-import argparse --hidden-import hashlib --hidden-import struct --hidden-import math --hidden-import csv ^
  nelderim.py || goto :fail
if exist dist\Nelderim rmdir /s /q dist\Nelderim
mkdir dist\Nelderim
move /y dist\Nelderim.exe dist\Nelderim\ >nul
for %%f in (nelderim.py requirements.txt README.md CLAUDE.md) do copy /y %%f dist\Nelderim\ >nul
for %%d in (app lab pipeline uo3d client-config examples docs) do if exist %%d xcopy /e /i /y %%d dist\Nelderim\%%d >nul
for /d /r dist\Nelderim %%p in (__pycache__) do if exist "%%p" rmdir /s /q "%%p"
echo.
echo Done: dist\Nelderim\Nelderim.exe
exit /b 0
:fail
echo BUILD FAILED
pause
exit /b 1
