@echo off
setlocal

REM Apollo EXE builder
REM Put this file, apollo_logo.ico and apollo.spec in the root of your Apollo project,
REM or edit APP_MAIN below.

set APP_NAME=Apollo
set APP_MAIN=main.py

echo Installing build tools...
py -m pip install --upgrade pip
py -m pip install pyinstaller pillow

if not exist "%APP_MAIN%" (
    echo.
    echo ERROR: %APP_MAIN% was not found in this folder.
    echo Put this build script in your Apollo project root or edit APP_MAIN.
    pause
    exit /b 1
)

echo.
echo Building %APP_NAME%...
py -m PyInstaller --noconfirm --clean --windowed --onefile --name "%APP_NAME%" --icon "apollo_logo.ico" "%APP_MAIN%"

echo.
echo Done.
echo Your EXE should be in the dist folder:
echo %CD%\dist\%APP_NAME%.exe
pause
