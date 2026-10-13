@echo off
setlocal
cd /d "%~dp0.."
echo ==================================================
echo  APOLLO FOUNDRY SANDBOX - MANUAL IMAGE SETUP
echo ==================================================
echo This requires Docker Desktop running in Linux container mode.
echo It downloads public Python and PySide6 packages only during setup.
echo The actual generated-app test containers run with NO NETWORK.
echo Do not run this on untrusted shared computers.
echo.
where docker >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker CLI not found. Install and start Docker Desktop.
  exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Docker engine is not available. Start Docker Desktop in Linux mode.
  exit /b 1
)
echo Docker is available.
choice /C YN /M "Build isolated Foundry Qt test image now"
if errorlevel 2 exit /b 0
docker build --pull -t apollo-foundry-qt:phase1 -f foundry_sandbox\Dockerfile foundry_sandbox
if errorlevel 1 (
  echo [ERROR] Image build failed. Foundry will refuse runtime sandbox tests.
  exit /b 1
)
docker image inspect apollo-foundry-qt:phase1 >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Built image was not found.
  exit /b 1
)
echo [OK] Image ready: apollo-foundry-qt:phase1
echo Open Apollo Foundry, then Sandbox Testing to run tests with no network.
exit /b 0
