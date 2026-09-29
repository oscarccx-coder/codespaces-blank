@echo off
cd /d "%~dp0"
python apollo_update_server.py --root storage\updates\server --port 8765
