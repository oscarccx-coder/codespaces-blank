@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Apollo Foundry - Sandbox Setup
set "APOLLO_ROOT=%~dp0.."
set "SETUP_LOG=%TEMP%\Apollo_Foundry_Sandbox_Setup.log"
set "NO_PAUSE=0"
set "CHECK_ONLY=0"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--check" (
  set "NO_PAUSE=1"
  set "CHECK_ONLY=1"
)
if defined CI set "NO_PAUSE=1"
> "%SETUP_LOG%" echo Apollo Foundry sandbox setup started %DATE% %TIME%

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
  echo [RESULT] Sandbox setup finished without an error.
) else (
  echo [RESULT] Sandbox setup did not complete. Exit code: %EXIT_CODE%
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
echo  APOLLO FOUNDRY - DOCKER SANDBOX SETUP
echo ===============================================================
echo.
echo [INFO] Using Apollo folder: "%CD%"
echo [INFO] This setup builds an approved Linux Docker test image.
echo [INFO] Generated application tests remain network-disabled.
echo.
if not exist "foundry_sandbox\Dockerfile" (
  echo [ERROR] Missing foundry_sandbox\Dockerfile.
  echo [FIX] Restore the complete apollo_ui folder before retrying.
  >>"%SETUP_LOG%" echo ERROR: Dockerfile missing.
  exit /b 2
)

set "DOCKER_EXE="
where docker >nul 2>&1
if not errorlevel 1 set "DOCKER_EXE=docker"
if not defined DOCKER_EXE if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
if not defined DOCKER_EXE (
  echo [ERROR] Docker CLI was not found.
  echo [FIX] Install Docker Desktop with Setup\14_INSTALL_DOCKER_DESKTOP.bat.
  echo [FIX] Then start Docker Desktop and reopen this script.
  >>"%SETUP_LOG%" echo ERROR: Docker executable missing.
  exit /b 3
)

set "INFO_FILE=%TEMP%\Apollo_Foundry_Docker_Info_%RANDOM%_%RANDOM%.txt"
set "DOCKER_OS="
echo [CHECK] Looking for a running Docker Linux engine...
"%DOCKER_EXE%" info --format "{{.OSType}}" >"%INFO_FILE%" 2>&1
if errorlevel 1 (
  echo [ERROR] Docker CLI exists, but the Docker engine is unavailable.
  echo [FIX] Start Docker Desktop, complete WSL 2 setup, and wait for the engine.
  echo [FIX] Make sure Docker is using Linux containers.
  type "%INFO_FILE%"
  >>"%SETUP_LOG%" echo ERROR: Docker engine unavailable.
  type "%INFO_FILE%" >>"%SETUP_LOG%"
  del /q "%INFO_FILE%" >nul 2>&1
  exit /b 3
)
set /p "DOCKER_OS="<"%INFO_FILE%"
del /q "%INFO_FILE%" >nul 2>&1
if /I not "%DOCKER_OS%"=="linux" (
  echo [ERROR] Docker engine is not running Linux containers.
  echo [FIX] In Docker Desktop select Switch to Linux containers.
  >>"%SETUP_LOG%" echo ERROR: Docker engine was not in Linux mode.
  exit /b 3
)
echo [OK] Docker Linux engine is running.

if "%CHECK_ONLY%"=="1" (
  "%DOCKER_EXE%" image inspect apollo-foundry-qt:phase1 >nul 2>&1
  if errorlevel 1 (
    echo [CHECK] Docker runs, but Apollo's sandbox image is not built.
    echo [NEXT] Double-click this batch file normally to build the image.
    >>"%SETUP_LOG%" echo CHECK: Sandbox image missing.
    exit /b 4
  )
  echo [OK] Apollo sandbox image is already installed.
  >>"%SETUP_LOG%" echo CHECK: Docker and image ready.
  exit /b 0
)
if defined CI (
  echo [ERROR] Image builds require interactive owner approval, not CI.
  exit /b 5
)
echo.
choice /C YN /N /M "Build Apollo's isolated Foundry test image? [Y/N] "
if errorlevel 3 (
  echo [ERROR] Could not read your selection.
  exit /b 5
)
if errorlevel 2 (
  echo [INFO] Cancelled. No image was changed.
  exit /b 0
)
echo.
echo [BUILD] Docker will download the approved dependencies if needed.
echo [BUILD] This can take time. Docker output follows below.
echo.
>>"%SETUP_LOG%" echo Docker build approved by user at %DATE% %TIME%.
"%DOCKER_EXE%" build --progress=plain --pull -t apollo-foundry-qt:phase1 -f "%CD%\foundry_sandbox\Dockerfile" "%CD%\foundry_sandbox"
if errorlevel 1 (
  echo [ERROR] Docker image build failed. Read the Docker errors above.
  echo [FIX] Check Internet access, available disk space and Docker status.
  >>"%SETUP_LOG%" echo ERROR: Docker image build failed.
  exit /b 6
)
"%DOCKER_EXE%" image inspect apollo-foundry-qt:phase1 >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Build exited successfully but the image is missing.
  >>"%SETUP_LOG%" echo ERROR: Built image missing.
  exit /b 6
)
echo [OK] Image ready: apollo-foundry-qt:phase1
echo [NEXT] Open Apollo Foundry and select Check Docker under Sandbox.
>>"%SETUP_LOG%" echo SUCCESS: Apollo sandbox image built and inspected.
exit /b 0
