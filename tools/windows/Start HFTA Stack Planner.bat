@echo off
rem HFTA Stack Planner: runs on this computer only. Projects are kept in the "data" folder next to this file.
setlocal
cd /d "%~dp0"
set "OPENHFTA_DIR=%~dp0openhfta"
set "OPENHFTA_LIB=%~dp0openhfta\OpenYTWCore.dll"
set "PROJECTS_DIR=%~dp0data\projects"
set "PORT=5055"
set "HOST=127.0.0.1"
set "VOACAPL=%~dp0voacap\bin\voacapl.exe"
set "ITSHFBC=%~dp0voacap\itshfbc"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%~dp0data\projects" mkdir "%~dp0data\projects"
echo HFTA Stack Planner is starting. Keep this window open while you use it.
echo Open http://localhost:5055 in your browser (it opens by itself in a moment).
start "" /b cmd /c "timeout /t 3 >nul & start http://localhost:5055"
"%~dp0runtime\python.exe" "%~dp0app\app.py"
if errorlevel 1 (
  echo.
  echo The planner stopped with an error. The text above says why. Press any key to close.
  pause >nul
)
