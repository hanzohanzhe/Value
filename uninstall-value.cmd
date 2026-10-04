@echo off
rem VALUE launcher; uninstall-value.ps1 is retained as a compatibility filename.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall-value.ps1"
pause
