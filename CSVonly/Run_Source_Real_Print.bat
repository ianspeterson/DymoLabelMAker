@echo off
cd /d "%~dp0"
set DYMO_SIMULATE=0
set LABEL_AUTO_PRINT=1
set LABEL_OPEN_BROWSER=1
start "" /b cmd /c "timeout /t 2 >nul && explorer http://127.0.0.1:5000"
python app.py
pause
