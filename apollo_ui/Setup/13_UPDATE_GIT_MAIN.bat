@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - Git Main Update
set "EXIT_CODE=1"
set "CHECK_ONLY=0"
set "NO_PAUSE=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if defined CI set "NO_PAUSE=1"
set "LOG=%TEMP%\Apollo_Git_Main_Update.log"
> "%LOG%" echo Apollo Git main update check %DATE% %TIME%

pushd "%~dp0..\.." >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Apollo repository directory is unavailable.
    goto :FINISH
)
echo =========================================================
echo  APOLLO SAFE GIT MAIN UPDATE
echo =========================================================
echo [INFO] Source checkout: "%CD%"
where git.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git for Windows was not found in PATH.
    goto :DONE
)
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This folder is not in a Git checkout.
    echo [FIX] Source updates require a Git clone; signed releases use Update Apollo.
    goto :DONE
)
set "BRANCH="
for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
if /I not "%BRANCH%"=="main" (
    echo [ERROR] Current branch is "%BRANCH%", not main.
    echo [FIX] Select the main branch manually before updating; no branch will be switched automatically.
    goto :DONE
)
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git origin remote is not configured.
    goto :DONE
)
set "DIRTY="
for /f "delims=" %%C in ('git status --porcelain --untracked-files=normal') do set "DIRTY=1"
if defined DIRTY (
    echo [STOPPED] Uncommitted or untracked files in Git checkout.
    echo [FIX] Commit, stash or move these files safely; updater will not overwrite them.
    set "EXIT_CODE=2"
    goto :DONE
)
echo [OK] Git checkout is clean and on main.
if "%CHECK_ONLY%"=="1" (
    echo [CHECK] Read-only preflight completed. No Git fetch, pull or file changes.
    set "EXIT_CODE=0"
    goto :DONE
)
echo [UPDATE] Fetching origin/main...
git fetch --progress origin main
if errorlevel 1 (
    echo [ERROR] Git fetch failed. Inspect network access, credentials and remote.
    goto :DONE
)
echo [UPDATE] Fast-forward main only...
git merge --ff-only FETCH_HEAD
if errorlevel 1 (
    echo [ERROR] Fast-forward refused. Local history was not overwritten.
    goto :DONE
)
echo [OK] Git main update completed.
echo [NEXT] Restart Apollo to load changed code. Dependencies may require a separate repair.
set "EXIT_CODE=0"
:DONE
>>"%LOG%" echo Finished with code %EXIT_CODE% at %DATE% %TIME%.
popd
:FINISH
echo.
echo [RESULT] Git update result code %EXIT_CODE%.
echo [LOG] "%LOG%"
if "%NO_PAUSE%"=="0" (
    echo Press any key to close this window.
    pause >nul
)
endlocal & exit /b %EXIT_CODE%
