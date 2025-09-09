@echo off
REM freeMarkable (Windows)
REM Easy launcher script for freeMarkable

title freeMarkable

echo ======================================================
echo                freeMarkable
echo ======================================================
echo.
echo Starting freeMarkable...
echo.

REM Get the directory where this batch file is located
set DIR=%~dp0
set RESOURCES_DIR=%DIR%resources

REM Remove trailing backslash if present
if %RESOURCES_DIR:~-1%==\ set RESOURCES_DIR=%RESOURCES_DIR:~0,-1%

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python and try again.
    echo.
    pause
    exit /b 1
)

REM Check if resources directory exists
if not exist "%RESOURCES_DIR%" (
    echo ERROR: Resources directory not found at %RESOURCES_DIR%
    echo Please make sure the resources folder is in the same directory as this launcher script.
    echo.
    pause
    exit /b 1
)

REM Check if main.py exists in resources
if not exist "%RESOURCES_DIR%\main.py" (
    echo ERROR: main.py not found in resources directory
    echo Please make sure all application files are in the resources folder.
    echo.
    pause
    exit /b 1
)

REM Install requirements if needed
if exist "%RESOURCES_DIR%\requirements.txt" (
    echo Installing Python dependencies...
    python -m pip install -r "%RESOURCES_DIR%\requirements.txt" --user
    echo.
)

REM Change to resources directory and run the Python application
cd /d "%RESOURCES_DIR%"
python main.py

REM Check exit status
if %ERRORLEVEL% equ 0 (
    echo.
    echo Application closed successfully.
) else (
    echo.
    echo Application exited with an error (Exit Code: %ERRORLEVEL%^).
    pause
)