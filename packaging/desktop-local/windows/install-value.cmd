@echo off
setlocal
py -3.10 "%~dp0installer\desktop_value.py" install %*
set "VALUE_EXIT=%ERRORLEVEL%"
if not "%VALUE_EXIT%"=="0" (
  pause
) else if "%~1"=="" (
  pause
)
exit /b %VALUE_EXIT%
