@echo off
setlocal
rem Expose the locally running dashboard over your tailnet via HTTPS, using
rem the Tailscale client already installed on this machine.
rem
rem   serve-tailscale.bat          - serve the Vite dev server (port 5173)
rem   serve-tailscale.bat 8000     - serve the backend (built frontend) instead
rem   serve-tailscale.bat off      - stop serving
rem
rem Requires MagicDNS + HTTPS certificates enabled for your tailnet
rem (https://login.tailscale.com/admin/dns).

where tailscale >nul 2>nul
if errorlevel 1 (
    echo [ERROR] tailscale CLI not found. Install Tailscale from
    echo         https://tailscale.com/download and sign in first.
    exit /b 1
)

if /i "%~1"=="off" (
    tailscale serve reset
    echo Tailscale serve stopped.
    exit /b 0
)

set "PORT=%~1"
if "%PORT%"=="" set "PORT=5173"

echo Serving http://127.0.0.1:%PORT% over your tailnet (HTTPS)...
tailscale serve --bg %PORT%
if errorlevel 1 (
    echo [ERROR] tailscale serve failed. Are you signed in? (tailscale status)
    exit /b 1
)

echo.
tailscale serve status
echo.
echo Open the https://...ts.net URL above from any device on your tailnet.
echo Stop with: serve-tailscale.bat off
