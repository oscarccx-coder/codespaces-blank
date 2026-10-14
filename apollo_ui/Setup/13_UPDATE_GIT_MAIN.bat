@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.." || (echo [ERROR] Apollo repository directory unavailable. & exit /b 1)
git rev-parse --is-inside-work-tree >nul 2>&1 || (echo [ERROR] Not a Git checkout. & exit /b 1)
echo [Apollo] Updating source from origin/main ...
git -c pull.rebase=false pull --ff-only --progress origin main
if errorlevel 1 (
  echo [ERROR] Git could not fast-forward. No local edits were intentionally discarded.
  exit /b 1
)
echo [OK] Git update complete.
exit /b 0
