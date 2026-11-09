@echo off
setlocal
cd /d "%~dp0"

echo Starting Ray5 Pilot...
echo Web UI opens at the configured address after the server is ready.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python was not found in PATH.
  echo Install Python 3, then rerun this launcher.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Failed to create .venv
    echo If .venv is partially created, delete it and rerun:
    echo   rmdir /s /q .venv
    echo.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo ERROR: Failed to activate virtual environment.
  echo.
  pause
  exit /b 1
)

python tools\prepare_environment.py
if errorlevel 1 (
  echo ERROR: requirements install failed.
  echo Check internet access and Python package availability, then retry.
  echo.
  pause
  exit /b 1
)

if not exist "config.json" (
  copy "config.example.json" "config.json" >nul
  if errorlevel 1 (
    echo ERROR: Failed to create config.json from config.example.json
    echo.
    pause
    exit /b 1
  )
)

python app.py
if errorlevel 1 (
  echo.
  echo Ray5 Pilot stopped with an error.
  pause
  exit /b 1
)

echo.
echo Ray5 Pilot exited. Press any key to close.
pause >nul

