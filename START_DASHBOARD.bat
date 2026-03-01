@echo off
chcp 65001 >nul
cd /d "%~dp0web"
echo ============================================================
echo Supertrend Bot Dashboard
echo ============================================================
echo.
echo Zapusk veb-interfeysa...
echo Otkroyte v brauzere: http://localhost:5001
echo.
echo Dlya ostanovki nazhmite Ctrl+C
echo ============================================================
echo.
python run.py
