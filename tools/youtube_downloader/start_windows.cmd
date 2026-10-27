@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
    py -3 app.py
) else (
    python app.py
)
if errorlevel 1 (
    echo.
    echo Python launcher failed. Install Python 3.11+ and retry.
    pause
)
