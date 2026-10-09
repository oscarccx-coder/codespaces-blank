@echo off
setlocal EnableExtensions
title Apollo - Install and Setup
cd /d "%~dp0.."
call "%~dp0..\INSTALL_REQUIREMENTS.bat"
if errorlevel 1 exit /b 1
if defined CI exit /b 0
call "%~dp0\10_SETUP_WIZARD.bat"
exit /b %ERRORLEVEL%
