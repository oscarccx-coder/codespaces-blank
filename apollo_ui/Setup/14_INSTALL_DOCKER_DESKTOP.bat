@echo off
setlocal EnableExtensions
title Apollo - Docker Desktop Setup
cd /d "%~dp0.."
echo ==============================================================
echo   APOLLO FOUNDRY - DOCKER DESKTOP INSTALLATION (WINDOWS)
echo ==============================================================
echo.
echo Docker Desktop requires a supported Windows installation, virtualization,
echo WSL 2, disk space, and possibly administrator approval or a restart.
echo This installer is OPTIONAL and will not run without your confirmation.
echo.
where docker >nul 2>&1
if not errorlevel 1 (
  docker info >nul 2>&1
  if not errorlevel 1 (
    echo [OK] Docker is running. Proceeding to Foundry image setup.
    call "%~dp0\09_SETUP_FOUNDRY_SANDBOX.bat"
    exit /b %ERRORLEVEL%
  )
  echo Docker CLI found, but engine is not running.
  echo Start Docker Desktop, switch to Linux containers and run this file again.
  pause
  exit /b 1
)
where winget >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Windows Package Manager (winget) not found.
  echo Install Docker Desktop from https://www.docker.com/products/docker-desktop/
  echo Then start Docker Desktop and run 09_SETUP_FOUNDRY_SANDBOX.bat.
  pause
  exit /b 1
)
echo To inspect WSL status, run: wsl --status
echo If WSL 2 is missing, run "wsl --install" in an elevated terminal,
echo restart Windows if prompted, then start Docker Desktop.
echo.
choice /C YN /N /M "Install official Docker Desktop with winget now? [Y/N] "
if errorlevel 2 exit /b 0
winget install --id Docker.DockerDesktop --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
  echo [ERROR] Docker Desktop installation did not complete.
  pause
  exit /b 1
)
echo.
echo [OK] Installer finished. You may need to reboot Windows.
echo Open Docker Desktop and complete its first-run setup.
echo When Docker shows its engine is running in Linux container mode,
echo run Setup\09_SETUP_FOUNDRY_SANDBOX.bat to build Apollo's test image.
pause
exit /b 0
