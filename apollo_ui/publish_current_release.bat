@echo off
cd /d "%~dp0"
python apollo_release.py --source . --out storage\updates\server --channel development
pause
