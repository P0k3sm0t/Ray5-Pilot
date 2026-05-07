@echo off
setlocal
cd /d "C:\Users\jmden\OneDrive\Documents\GitHub\Ray5 Pilot Using"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist "config.json" (
  copy "config.example.json" "config.json" >nul
)

start "" "http://127.0.0.1:5050"
python app.py

echo.
echo Ray5 Pilot exited. Press any key to close.
pause >nul

