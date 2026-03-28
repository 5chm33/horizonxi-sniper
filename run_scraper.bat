@echo off
title HorizonXI Bazaar + AH Sniper v2.0
echo ============================================
echo   HorizonXI Bazaar + AH Sniper  v2.0
echo   CEO Edition - Bazaar AND Auction House
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Install dependencies
echo [INFO] Checking dependencies...
pip install requests plyer --quiet

:: Launch
echo [INFO] Starting HorizonXI Sniper...
echo.
python "%~dp0horizonxi_scraper.py"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Scraper exited with error code %errorlevel%
    pause
)
