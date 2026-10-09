@echo off
setlocal
title Apollo - Retired Legacy Launcher
cd /d "%~dp0"
echo.
echo [RETIRED] publish_current_release.bat was an outdated, machine-specific Apollo launcher.
echo It has been disabled to prevent accidental stale updates or repairs.
echo.
echo Replacement: tools\publish_github_release.py
echo Your existing models, voice profiles and user files have not been changed.
echo See docs\architecture\MODULE_CONSOLIDATION_AND_MEMORY.md
echo.
pause
exit /b 2
