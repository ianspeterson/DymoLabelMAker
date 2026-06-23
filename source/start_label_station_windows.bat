@echo off
cd /d "%~dp0"
set DYMO_SIMULATE=1
python app.py
pause
