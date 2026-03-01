@echo off
echo ========================================
echo  Starting Trading Platform Web Server
echo ========================================
echo.

cd /d "%~dp0"

call .venv\Scripts\activate.bat

python run_web.py

pause
