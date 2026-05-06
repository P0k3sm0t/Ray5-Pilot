@echo off
setlocal
cd /d "%~dp0"

echo Starting Ray5 Pilot...

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.11 or newer and try again.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist "config.json" (
    copy "config.example.json" "config.json" >nul
    echo.
    echo Created config.json from config.example.json.
    echo Open Settings or edit config.json and set your Ray5 IP before use.
    echo Default web UI: http://127.0.0.1:5050
    echo.
)

python app.py
pause
