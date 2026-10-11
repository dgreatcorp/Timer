@echo off
rem ===========================================================================
rem  Build a single-file Windows executable:  dist\KeyboardTimer.exe
rem  Usage:  build.bat          (from a "Developer" command prompt is fine)
rem ===========================================================================
setlocal
cd /d "%~dp0"

echo [1/3] Installing build dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail

rem Application icon (asset\timer.ico); falls back to none if missing.
set ICON_ARGS=
if exist "%~dp0asset\timer.ico" set ICON_ARGS=--icon "%~dp0asset\timer.ico"

echo [2/3] Running self test...
python main.py --smoke
if errorlevel 1 goto :fail

echo [3/3] Building executable (this can take a minute)...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name KeyboardTimer ^
    --collect-data tzdata ^
    --collect-submodules tzdata ^
    --add-data "asset;asset" ^
    %ICON_ARGS% main.py
if errorlevel 1 goto :fail

echo.
echo Done. Your application is:  %~dp0dist\KeyboardTimer.exe
echo Copy that single file anywhere and double-click it to run.
exit /b 0

:fail
echo.
echo BUILD FAILED - see the messages above.
exit /b 1
