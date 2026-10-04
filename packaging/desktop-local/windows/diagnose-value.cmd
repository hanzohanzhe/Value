@echo off
setlocal
py -3.10 "%~dp0installer\desktop_value.py" diagnose %*
set "VALUE_EXIT=%ERRORLEVEL%"
if not "%VALUE_EXIT%"=="0" pause
exit /b %VALUE_EXIT%
