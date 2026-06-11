@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM run_windows.bat — MDR Surveillance System Windows Setup & Launch
REM ─────────────────────────────────────────────────────────────────────────────
title MDR Surveillance System

echo.
echo ================================================================
echo    MDR Disease Risk Prediction ^& Contact Tracing System
echo                    Windows Setup Script
echo ================================================================
echo.

REM Check Python
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo ERROR: Python not found. Install Python 3.10+ from https://python.org
    pause & exit /b 1
)
echo [OK] Python found

REM Create venv
IF NOT EXIST venv (
    echo Creating virtual environment...
    python -m venv venv
    echo [OK] Virtual environment created
) ELSE (
    echo [OK] Virtual environment already exists
)

REM Activate
call venv\Scripts\activate.bat

REM Install packages
echo.
echo Installing Python packages (may take several minutes)...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo [OK] Packages installed

REM Copy .env
IF NOT EXIST .env (
    copy .env.example .env >nul
    echo [OK] .env created. Edit it to change settings.
)

REM Create dirs
IF NOT EXIST uploads\patients mkdir uploads\patients
IF NOT EXIST uploads\frames   mkdir uploads\frames
IF NOT EXIST uploads\reports  mkdir uploads\reports
IF NOT EXIST logs             mkdir logs

REM Init DB
echo.
echo Initialising MongoDB database...
python db_init.py

REM Launch
echo.
echo ================================================================
echo   Starting MDR Surveillance System on http://localhost:5000
echo   Press Ctrl+C to stop.
echo ================================================================
echo.
python app.py

pause
