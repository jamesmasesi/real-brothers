@echo off
echo ================================================
echo   REAL BROTHERS Savings App - Setup
echo ================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    echo Please install Python from https://python.org
    echo Make sure to check "Add Python to PATH" during install
    pause
    exit /b 1
)

echo [1/3] Installing Flask...
pip install flask -q
if %errorlevel% neq 0 (
    echo ERROR: Could not install Flask
    pause
    exit /b 1
)

echo [2/3] Setup complete!
echo.
echo ================================================
echo   Starting Real Brothers App...
echo   Open your browser to: http://localhost:5000
echo   Admin login: admin / admin123
echo ================================================
echo.
echo Press Ctrl+C to stop the server
echo.

python app.py
pause
