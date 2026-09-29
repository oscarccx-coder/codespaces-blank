@echo off
setlocal
cd /d "%~dp0"

echo [Apollo 7] Building a cleaner onedir Windows release...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto :fail

if exist build rmdir /s /q build
if exist dist\Apollo rmdir /s /q dist\Apollo

python -m PyInstaller --noconfirm --clean --windowed --noupx ^
  --name Apollo ^
  --version-file version_info.txt ^
  --icon apollo_logo.ico ^
  --add-data "modules;modules" ^
  --add-data "pending_modules;pending_modules" ^
  --add-data "config.json;." ^
  --add-data "modules_state.json;." ^
  launch_apollo.pyw
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -File .\make_release_hash.ps1

echo.
echo Build complete: dist\Apollo\Apollo.exe
echo This ONEDIR build intentionally avoids UPX and one-file packing, which can reduce false-positive AV heuristics.
echo It is still UNSIGNED unless you run sign_apollo.ps1 with a real code-signing certificate.
pause
exit /b 0

:fail
echo Build failed.
pause
exit /b 1
