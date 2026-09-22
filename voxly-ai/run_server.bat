@echo off
setlocal enabledelayedexpansion
title Voxly AI - Setup and Server Launcher

:: Navigate to the directory of this batch script
cd /d "%~dp0"

echo =====================================================================
echo                VOXLY AI - SERVER SETUP AND LAUNCHER
echo =====================================================================
echo.

:: 1. Check if Node.js is installed
echo [*] Checking system prerequisites...
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js was not found on your system!
    echo.
    echo Please download and install Node.js (v18 or higher recommended) from:
    echo   https://nodejs.org/
    echo.
    echo After installing Node.js, restart your terminal and re-run this script.
    echo.
    pause
    exit /b 1
)

:: Display detected Node and npm versions
for /f "tokens=*" %%v in ('node -v 2^>nul') do set NODE_VER=%%v
for /f "tokens=*" %%v in ('call npm -v 2^>nul') do set NPM_VER=%%v
echo [OK] Detected Node.js: %NODE_VER%
echo [OK] Detected npm:     v%NPM_VER%
echo.

:: 2. Install dependencies
echo [1/3] Installing / verifying dependencies with npm install...
echo (This may take a moment on first launch...)
echo.
call npm install
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] npm install failed! Please check your network connection and try again.
    echo.
    pause
    exit /b 1
)
echo [OK] All dependencies installed successfully!
echo.

:: 3. Verify 3D Model Asset
echo [2/3] Verifying 3D robot model asset...
if exist "public\models\VoxlyBot_AIEmployee_Interactive.glb" (
    echo [OK] 3D Model found: public\models\VoxlyBot_AIEmployee_Interactive.glb
) else (
    echo [WARNING] 3D Model file not found at public\models\VoxlyBot_AIEmployee_Interactive.glb!
)
echo.

:: 4. Launch development server and open browser
echo [3/3] Starting Voxly AI Server (npm run server)...
echo.
echo =====================================================================
echo   Local Address: http://localhost:5173
echo   (Press Ctrl+C in this window to stop the server)
echo =====================================================================
echo.

:: Launch browser in background after 3 seconds
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:5173"

:: Start the Vite server
call npm run server

if %errorlevel% neq 0 (
    echo.
    echo [INFO] Server stopped.
)
pause
