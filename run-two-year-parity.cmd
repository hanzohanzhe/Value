@echo off
setlocal
cd /d "%~dp0"

set "GRIDFORM_PYTHON=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
set "GRIDFORM_RUN=.gridform\runs\scheme-c-authoritative-python310-2025-2026"

if not exist "%GRIDFORM_PYTHON%" (
  echo Python 3.10 was not found at:
  echo %GRIDFORM_PYTHON%
  echo.
  echo Install the Python 3.10 environment used by the retained Scheme C run.
  pause
  exit /b 1
)

echo Running authoritative Scheme C for 2025-2026.
echo This full test can take several hours.
echo Output: %GRIDFORM_RUN%
echo.

"%GRIDFORM_PYTHON%" scripts\run_scheme_c_parity.py ^
  --output "%GRIDFORM_RUN%\model-output" ^
  --start-year 2025 ^
  --end-year 2026 ^
  --periods 17520
if errorlevel 1 goto :failed

"%GRIDFORM_PYTHON%" scripts\compare_scheme_c_parity.py ^
  --actual "%GRIDFORM_RUN%\model-output\exact-run.json" ^
  --output "%GRIDFORM_RUN%\parity-report.json"
if errorlevel 1 goto :failed

echo.
echo PASS: all retained-output parity checks matched.
pause
exit /b 0

:failed
echo.
echo FAIL: the run or numerical parity check did not pass.
echo Inspect %GRIDFORM_RUN% before changing the model.
pause
exit /b 1
