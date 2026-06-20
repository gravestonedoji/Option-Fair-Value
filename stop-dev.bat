@echo off
REM Stops the Option Fair Value servers by killing anything on ports 8000/5173.
echo Stopping servers...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /pid %%a /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /pid %%a /f >nul 2>&1
echo Done.
timeout /t 2 /nobreak >nul
