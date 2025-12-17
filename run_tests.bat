@echo off
REM run_tests.bat - One-click test execution for Windows
REM This script sets up dependencies and runs the full test suite

echo.
echo ========================================
echo Content Moderation Service - Test Suite
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

echo Setting up environment...

REM Create virtual environment if it doesn't exist
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        exit /b 1
    )
)

REM Activate virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)

echo.
echo ========================================
echo Running Tests
echo ========================================
echo.

REM Run pytest
python -m pytest tests/ -v --tb=short

if errorlevel 1 (
    echo.
    echo ========================================
    echo TESTS FAILED
    echo ========================================
    exit /b 1
) else (
    echo.
    echo ========================================
    echo ALL TESTS PASSED
    echo ========================================
    exit /b 0
)
