@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - Install Git Source Beside Existing Apollo
set "EXIT_CODE=1"
set "CHECK_ONLY=0"
set "NO_PAUSE=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if defined CI set "NO_PAUSE=1"

rem This setup script is inside <Apollo root>\apollo_ui\Setup.
rem It NEVER converts, overwrites, moves or deletes the current ZIP install.
for %%I in ("%~dp0..\..") do set "SOURCE_ROOT=%%~fI"
for %%I in ("%SOURCE_ROOT%\..") do set "SOURCE_PARENT=%%~fI"
set "DEST=%SOURCE_PARENT%\Apollo-Git"
set "LOG=%TEMP%\Apollo_Git_Source_Install.log"
> "%LOG%" echo Apollo Git source bootstrap %DATE% %TIME%

echo =========================================================
echo  APOLLO GIT SOURCE INSTALLER - SIDE BY SIDE
echo =========================================================
echo [CURRENT] "%SOURCE_ROOT%"
echo [NEW]     "%DEST%"
echo [INFO] This is source code, NOT an Ed25519-signed release.
echo [INFO] Existing memory, voices, models and projects are untouched.
echo.

if not exist "%SOURCE_ROOT%\apollo_ui\main.py" (
    echo [ERROR] Run this script from an Apollo source or ZIP installation.
    goto :DONE
)
where git.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git for Windows was not found in PATH.
    echo [FIX] Install Git from https://git-scm.com/downloads/win
    goto :DONE
)
if /I "%SOURCE_ROOT%"=="%DEST%" (
    echo [STOPPED] Apollo is already in the reserved Git install folder.
    echo [FIX] Use Setup\03_UPDATE_APOLLO.bat to update an existing Git checkout.
    set "EXIT_CODE=2"
    goto :DONE
)
if exist "%DEST%\" (
    echo [STOPPED] The destination already exists. Nothing has been replaced.
    echo [FIX] Inspect "%DEST%" manually. Do not delete saved files to rerun setup.
    set "EXIT_CODE=2"
    goto :DONE
)
if "%CHECK_ONLY%"=="1" (
    echo [CHECK] Git available and destination unused. No files downloaded.
    set "EXIT_CODE=0"
    goto :DONE
)

echo [DOWNLOAD] Cloning the latest main source from the canonical GitHub repository...
git clone --depth 1 --single-branch --branch main "https://github.com/oscarccx-coder/codespaces-blank.git" "%DEST%"
if errorlevel 1 (
    echo [ERROR] Git clone failed. Any partial destination is left for manual inspection.
    echo [FIX] Review network, disk space and the destination before retrying.
    goto :DONE
)
if not exist "%DEST%\apollo_ui\main.py" (
    echo [ERROR] Clone finished but Apollo's entry point was not found.
    goto :DONE
)
if not exist "%DEST%\.git\" (
    echo [ERROR] New folder does not contain Git metadata.
    goto :DONE
)
echo.
echo [OK] Git-connected Apollo source downloaded successfully.
echo [NEXT] Run "%DEST%\apollo_ui\Setup\01_INSTALL_APOLLO.bat" once to install dependencies.
echo [NEXT] Then use "%DEST%\apollo_ui\Setup\02_START_APOLLO.bat" to launch.
echo [LATER] Updates use "%DEST%\apollo_ui\Setup\03_UPDATE_APOLLO.bat".
echo [DATA] Your old install is untouched. Use Apollo's backup/restore to move user data.
echo [NOTE] Optional OpenJarvis submodules and XTTS dependencies need separate setup.
set "EXIT_CODE=0"

:DONE
>>"%LOG%" echo Finished with result code %EXIT_CODE% at %DATE% %TIME%.
echo.
echo [RESULT] Git source installer exit code %EXIT_CODE%.
echo [LOG] "%LOG%"
if "%NO_PAUSE%"=="0" (
    echo Press any key to close this window.
    pause >nul
)
endlocal & exit /b %EXIT_CODE%
