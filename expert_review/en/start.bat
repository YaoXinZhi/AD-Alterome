@echo off
setlocal
cd /d "%~dp0"
py -3 --version >nul 2>&1
if not errorlevel 1 (
    py -3 server.py %*
    if errorlevel 1 pause
    exit /b
)
python --version >nul 2>&1
if not errorlevel 1 (
    python -c "import sys; sys.exit(sys.version_info.major != 3)" >nul 2>&1
    if not errorlevel 1 (
        python server.py %*
        if errorlevel 1 pause
        exit /b
    )
)
echo Python 3 is required. Install it from https://www.python.org/ and try again.
echo No pip packages are needed.
pause
exit /b 1
