@echo off
REM Starts the React dashboard on http://localhost:5173
cd /d "%~dp0frontend"
if not exist node_modules npm install
npm run dev
pause
