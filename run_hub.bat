@echo off
cd /d "%~dp0"
where python >nul 2>nul && (python nelderim_hub.py & goto :end)
where py >nul 2>nul && (py -3 nelderim_hub.py & goto :end)
echo Python 3.10+ not found. Install it from https://www.python.org/downloads/ (tick "Add Python to PATH").
:end
if errorlevel 1 pause
