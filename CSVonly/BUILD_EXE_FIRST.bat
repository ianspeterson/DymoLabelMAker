@echo off
setlocal
cd /d "%~dp0"

echo =============================================
echo BO Label Station - Windows EXE Builder
echo =============================================
echo.

echo Checking Python...
py -3 --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python 3 was not found.
    echo Install Python from https://www.python.org/downloads/windows/
    echo Make sure "Add python.exe to PATH" is checked.
    echo.
    pause
    exit /b 1
)

echo Creating build virtual environment...
if not exist .venv (
    py -3 -m venv .venv
    if errorlevel 1 goto :fail
)

call .venv\Scripts\activate.bat
if errorlevel 1 goto :fail

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo Installing app and build requirements...
pip install -r requirements.txt
if errorlevel 1 goto :fail
pip install -r requirements-build.txt
if errorlevel 1 goto :fail

echo Cleaning old build folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building portable EXE folder...
pyinstaller --clean BOLabelStation.spec
if errorlevel 1 goto :fail

echo Copying startup files and default data...
copy /Y Start_BOLabelStation_Real_Print.bat dist\BOLabelStation\Start_BOLabelStation_Real_Print.bat >nul
copy /Y Start_BOLabelStation_Simulate.bat dist\BOLabelStation\Start_BOLabelStation_Simulate.bat >nul
copy /Y README.md dist\BOLabelStation\README.md >nul
if exist data robocopy data dist\BOLabelStation\data /E >nul
if exist sample_data robocopy sample_data dist\BOLabelStation\sample_data /E >nul

echo Creating distributable ZIP...
if exist dist\BO_LabelStation_Windows_Portable.zip del /q dist\BO_LabelStation_Windows_Portable.zip
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\BOLabelStation\*' -DestinationPath 'dist\BO_LabelStation_Windows_Portable.zip' -Force"
if errorlevel 1 goto :fail

echo.
echo =============================================
echo BUILD COMPLETE
echo =============================================
echo.
echo Test the app by running:
echo   dist\BOLabelStation\Start_BOLabelStation_Real_Print.bat
echo.
echo Give users this zip:
echo   dist\BO_LabelStation_Windows_Portable.zip
echo.
pause
exit /b 0

:fail
echo.
echo =============================================
echo BUILD FAILED
echo =============================================
echo Copy the first real error above this line and send it for troubleshooting.
echo.
pause
exit /b 1
