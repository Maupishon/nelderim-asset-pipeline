@echo off
REM Builds dist\NelderimHub\ (NelderimHub.exe + pipeline scripts) with PyInstaller. Run on Windows.
cd /d "%~dp0"
python -m pip install pyinstaller pillow || goto :fail
python -m PyInstaller --onefile --windowed --noconfirm --name NelderimHub --hidden-import nelderim_hub_ui nelderim_hub.py || goto :fail
if exist dist\NelderimHub rmdir /s /q dist\NelderimHub
mkdir dist\NelderimHub
move /y dist\NelderimHub.exe dist\NelderimHub\ >nul
for %%f in (uo3d_job.py nelderim_core.py nelderim_gui.py nelderim_patch.py nelderim_search.py uopatch.py uop_gump_patch.py uop_probe.py vd_inject.py requirements.txt README.md CLAUDE.md run_nelderim.bat) do copy /y %%f dist\NelderimHub\ >nul
xcopy /e /i /y client-config dist\NelderimHub\client-config >nul
xcopy /e /i /y examples dist\NelderimHub\examples >nul
echo.
echo Done: dist\NelderimHub\NelderimHub.exe
exit /b 0
:fail
echo BUILD FAILED
pause
exit /b 1
