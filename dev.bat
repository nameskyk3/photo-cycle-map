@echo off
cd /d "%~dp0"

start "photo-cycle-map backend" cmd /k backend\run.bat
start "photo-cycle-map web" cmd /k web\run.bat
