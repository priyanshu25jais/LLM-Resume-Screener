@echo off
REM Starts the whole app (API + dashboard) on http://localhost:8000
cd /d "%~dp0backend"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
if not exist venv (
  echo First run: creating the virtual environment and installing packages. This takes a few minutes...
  python -m venv venv
  call venv\Scripts\activate
  python -m pip install -r requirements.txt
) else (
  call venv\Scripts\activate
)
if not exist .env copy .env.example .env
echo.
echo Open http://localhost:8000 in your browser. Press Ctrl+C here to stop the app.
echo First time? Make the admin account in another terminal: python scripts\create_admin.py
echo.
python -m uvicorn app.main:app --reload --port 8000
pause
