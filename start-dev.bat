@echo off
setlocal
title Option Fair Value Dashboard
cd /d "%~dp0"

if not defined FRED_API_KEY (
    echo [WARNING] FRED_API_KEY is not set. /fairvalue will 503 unless
    echo           risk_free_rate is overridden. Get a free key at:
    echo           https://fredaccount.stlouisfed.org
    echo.
)

echo Starting backend (FastAPI) on http://127.0.0.1:8000 ...
start "OFV Backend" /min cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting frontend (Vite) on http://localhost:5173 ...
start "OFV Frontend" /min cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo ============================================================
echo   Backend  : http://127.0.0.1:8000/docs
echo   Frontend : http://localhost:5173
echo ------------------------------------------------------------
echo   To stop the servers: close this window AND the two
echo   minimized server windows, OR run stop-dev.bat
echo ============================================================
echo.
echo This window will close in 5 seconds...
timeout /t 5 /nobreak >nul
