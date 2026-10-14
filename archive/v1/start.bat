@echo off
rem CaptainStems startup script for Windows
rem Creates the virtual environment on first use, then launches the application.
setlocal
cd /d "%~dp0"

if exist "venv\Scripts\python.exe" goto run

echo Creating virtual environment...
rem Prefer Python 3.10: it is the version every model supports
py -3.10 -m venv venv 2>nul
if exist "venv\Scripts\python.exe" goto run
py -3 -m venv venv 2>nul
if exist "venv\Scripts\python.exe" goto run
python -m venv venv
if exist "venv\Scripts\python.exe" goto run

echo Python was not found. Install Python 3.10 from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:run
"venv\Scripts\python.exe" captain.py %*
if errorlevel 1 pause
