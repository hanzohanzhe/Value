@echo off
setlocal
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONUSERBASE="
set "PYTHONPYCACHEPREFIX=%TEMP%\value-pycache-%RANDOM%-%RANDOM%"
set "PYTHONSTARTUP="
set "PYTHONINSPECT="
set "PYTHONEXECUTABLE="
set "__PYVENV_LAUNCHER__="
set "NODE_OPTIONS="
set "NODE_PATH="
"%~dp0runtime\python\python.exe" -B -s "%~dp0installer\desktop_value.py" diagnose %*
set "VALUE_EXIT=%ERRORLEVEL%"
if "%~1"=="" pause
exit /b %VALUE_EXIT%
