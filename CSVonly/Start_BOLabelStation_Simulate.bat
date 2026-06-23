@echo off
cd /d "%~dp0"
set DYMO_SIMULATE=1
set LABEL_AUTO_PRINT=1
set LABEL_OPEN_BROWSER=1
start "" /b cmd /c "timeout /t 2 >nul && explorer http://127.0.0.1:5000"
echo Starting BO Label Station in SIMULATE mode...
echo.
echo Leave this window open while using the app.
echo Open: http://127.0.0.1:5000
echo.
BOLabelStation.exe
echo.
echo BO Label Station has stopped.
pause
