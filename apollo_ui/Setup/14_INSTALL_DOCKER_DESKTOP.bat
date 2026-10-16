@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo - Docker Desktop Installer
set "APOLLO_ROOT=%~dp0.."
set "SETUP_LOG=%TEMP%\Apollo_Docker_Desktop_Setup.log"
set "NO_PAUSE=0"
set "CHECK_ONLY=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--check" (
  set "NO_PAUSE=1"
  set "CHECK_ONLY=1"
)
if defined CI set "NO_PAUSE=1"
> "%SETUP_LOG%" echo Apollo Docker Desktop setup started %DATE% %TIME%

pushd "%APOLLO_ROOT%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Cannot open Apollo folder: "%APOLLO_ROOT%"
  >>"%SETUP_LOG%" echo ERROR: Apollo source folder unavailable.
  set "EXIT_CODE=2"
  goto :FINISH
)
call :MAIN
set "EXIT_CODE=%errorlevel%"
popd

:FINISH
echo.
if "%EXIT_CODE%"=="0" (
  echo [RESULT] Docker Desktop setup finished without an error.
) else (
  echo [RESULT] Docker Desktop setup needs attention. Exit code: %EXIT_CODE%
)
>>"%SETUP_LOG%" echo Finished with exit code %EXIT_CODE% at %DATE% %TIME%
echo [LOG] "%SETUP_LOG%"
if "%NO_PAUSE%"=="0" (
  echo Press any key to close this window.
  pause >nul
)
endlocal & exit /b %EXIT_CODE%

:MAIN
echo ===============================================================
echo  APOLLO FOUNDRY - DOCKER DESKTOP INSTALLER
echo ===============================================================
echo.
echo [INFO] Docker Desktop requires Windows, WSL 2 and virtualization.
echo [INFO] Installation requires permission; nothing installs silently.
echo [INFO] Docker and its Linux engine must run before image setup.
echo.
if not exist "foundry_sandbox\Dockerfile" (
  echo [ERROR] Foundry Dockerfile is missing from this Apollo checkout.
  echo [FIX] Update or restore the complete Apollo source directory.
  >>"%SETUP_LOG%" echo ERROR: Foundry Dockerfile missing.
  exit /b 2
)

set "DOCKER_EXE="
where docker >nul 2>&1
if not errorlevel 1 set "DOCKER_EXE=docker"
if not defined DOCKER_EXE if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
if defined DOCKER_EXE (
  echo [CHECK] Docker CLI found. Checking the engine...
  set "INFO_FILE=%TEMP%\Apollo_Docker_Desktop_Info_%RANDOM%_%RANDOM%.txt"
  "%DOCKER_EXE%" info --format "{{.OSType}}" >"%INFO_FILE%" 2>&1
  if errorlevel 1 (
    echo [ERROR] Docker is installed but its engine is not running.
    echo [FIX] Start Docker Desktop and complete any WSL 2 prompts.
    echo [FIX] Wait for Engine running, then retry.
    type "%INFO_FILE%"
    >>"%SETUP_LOG%" echo ERROR: Docker installed, engine unavailable.
    type "%INFO_FILE%" >>"%SETUP_LOG%"
    del /q "%INFO_FILE%" >nul 2>&1
    exit /b 3
  )
  set /p "DOCKER_OS="<"%INFO_FILE%"
  del /q "%INFO_FILE%" >nul 2>&1
  if /I not "%DOCKER_OS%"=="linux" (
    echo [ERROR] Docker Desktop is running Windows containers.
    echo [FIX] Switch to Linux containers before building the sandbox.
    >>"%SETUP_LOG%" echo ERROR: Wrong Docker container mode.
    exit /b 3
  )
  echo [OK] Docker Desktop Linux engine is available.
  if "%CHECK_ONLY%"=="1" exit /b 0
  echo [NEXT] Starting the separate, owner-confirmed Foundry image setup.
  call "%~dp009_SETUP_FOUNDRY_SANDBOX.bat" --no-pause
  if errorlevel 1 (
    echo [ERROR] Foundry sandbox setup did not succeed.
    >>"%SETUP_LOG%" echo ERROR: Nested sandbox setup failed.
    exit /b 6
  )
  exit /b 0
)

echo [CHECK] Docker CLI is not installed or not available in PATH.
if "%CHECK_ONLY%"=="1" (
  echo [NEXT] Run this installer normally to approve Docker Desktop installation.
  >>"%SETUP_LOG%" echo CHECK: Docker missing.
  exit /b 3
)
if defined CI (
  echo [ERROR] Docker installation requires interactive owner approval, not CI.
  exit /b 5
)
where winget >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows Package Manager - winget - was not found.
  echo [FIX] Install Docker Desktop from https://www.docker.com/products/docker-desktop/
  echo [NEXT] Start Docker Desktop and run Setup\09_SETUP_FOUNDRY_SANDBOX.bat.
  >>"%SETUP_LOG%" echo ERROR: Docker and winget missing.
  exit /b 3
)
echo.
echo [PRECHECK] Use wsl --status in a Windows terminal to inspect WSL.
echo [PRECHECK] If WSL 2 is missing, use wsl --install as administrator.
echo [PRECHECK] A Windows restart and available disk space may be needed.
echo.
choice /C YN /N /M "Install official Docker Desktop with winget now? [Y/N] "
if errorlevel 3 (
  echo [ERROR] Unable to read your selection.
  exit /b 5
)
if errorlevel 2 (
  echo [INFO] Cancelled. Nothing was installed.
  exit /b 0
)
echo.
echo [INSTALL] Running the official Windows Package Manager installer.
echo [INSTALL] Keep this window open and follow any installer prompts.
>>"%SETUP_LOG%" echo Docker Desktop installation approved by user.
winget install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo [ERROR] Docker Desktop installation failed. Read the winget output above.
  echo [FIX] Check Windows compatibility, installation permissions and disk space.
  >>"%SETUP_LOG%" echo ERROR: winget installation failed.
  exit /b 7
)
echo.
echo [OK] Docker Desktop installer returned success.
echo [NEXT] Restart Windows if prompted, then open Docker Desktop.
echo [NEXT] Complete WSL 2 setup and wait for the Linux engine to start.
echo [NEXT] Run Setup\09_SETUP_FOUNDRY_SANDBOX.bat to build the image.
>>"%SETUP_LOG%" echo SUCCESS: winget returned success; Docker setup still requires first run.
exit /b 0
