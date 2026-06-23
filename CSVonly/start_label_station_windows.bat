@echo off
cd /d "%~dp0"
set DYMO_SIMULATE=0
set LABEL_AUTO_PRINT=1
python app.py
pause
