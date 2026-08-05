@echo off
REM Fursuitability Index - Quick Access Script
cd /d "%~dp0"
python fsi_cli.py --dwd %*
