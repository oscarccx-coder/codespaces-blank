@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - Updater Self-Test (No Installation)
set "EXIT_CODE=0"
set "TESTS_ONLY=0"
set "NO_PAUSE=0"
if /I "%~1"=="--tests-only" set "TESTS_ONLY=1"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if defined CI set "NO_PAUSE=1"
set "TEST_LOG=%TEMP%\Apollo_Updater_Self_Test.log"

pushd "%~dp0.." >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot find the Apollo source folder.
  set "EXIT_CODE=2"
  goto :FINISH
)
echo ===========================================================
echo  APOLLO UPDATER SELF-TEST - NO REAL UPDATE OR DOWNLOAD
echo ===========================================================
echo.
echo [INFO] All signed release tests use temporary directories and test-only keys.
echo [INFO] Git integration tests clone a disposable LOCAL Git origin.
echo [INFO] Your real Apollo code, profiles and models will not be updated.
echo.
if "%TESTS_ONLY%"=="0" (
  echo [CHECK] Inspecting this Apollo checkout without changing Git files...
  call "%~dp013_UPDATE_GIT_MAIN.bat" --check
  if errorlevel 1 (
    echo [WARNING] This checkout is NOT ready for a Git source update.
    echo [INFO] Independent updater regression tests can still run below.
    set "EXIT_CODE=1"
  )
) else (
  echo [INFO] Tests-only mode: current checkout/branch preflight intentionally skipped.
)
echo.
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Apollo private Python is not installed.
  echo [FIX] Run Setup\01_INSTALL_APOLLO.bat, then retry this self-test.
  set "EXIT_CODE=3"
  goto :DONE
)
echo [TEST] Testing safe signed install, rollback, process launch, and Git BAT updates...
".venv\Scripts\python.exe" -m unittest -v tests.test_updater_launch_and_restart tests.test_git_updater_windows tests.test_update_preflight tests.test_update_backup_failure tests.test_github_updates >"%TEST_LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] One or more updater tests FAILED.
  set "EXIT_CODE=4"
) else (
  echo [OK] All updater tests passed on this machine.
)
echo.
echo ======================= TEST RESULTS ========================
type "%TEST_LOG%"
:DONE
popd
:FINISH
echo.
echo [RESULT] Apollo updater self-test exit code: %EXIT_CODE%
echo [TEST LOG] "%TEST_LOG%"
echo [GIT LOG] "%TEMP%\Apollo_Git_Main_Update.log"
echo [INFO] No updates were installed by this test.
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this window.
  pause >nul
)
endlocal & exit /b %EXIT_CODE%
