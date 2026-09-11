@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m asset_auto.cli serve
