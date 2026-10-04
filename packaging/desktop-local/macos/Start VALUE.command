#!/bin/bash
set -u
BUNDLE="$(cd -- "$(dirname -- "$0")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:$PATH"
CONTROL_PYTHON=""
if [ -n "${VALUE_PYTHON:-}" ]; then
  if "$VALUE_PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3,10))' >/dev/null 2>&1; then CONTROL_PYTHON="$VALUE_PYTHON"; fi
else
  for candidate in python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,10))' >/dev/null 2>&1; then
      CONTROL_PYTHON="$(command -v "$candidate")"; break
    fi
  done
fi
if [ -z "$CONTROL_PYTHON" ]; then
  echo "VALUE needs Python 3.10 or newer to run this installer/controller."
  echo "Install Python from https://www.python.org/downloads/ or set VALUE_PYTHON to its absolute executable path."
  echo "The application runtime itself requires Python 3.10 with its scientific dependencies."
  if [ -t 0 ]; then read -r -p "Press Return to close this command..." _value_reply; fi
  exit 1
fi
"$CONTROL_PYTHON" "$BUNDLE/installer/desktop_value.py" start "$@"
status=$?
if [ "$status" -ne 0 ]; then
  echo "VALUE start failed (exit $status). Review the message above."
  if [ -t 0 ]; then read -r -p "Press Return to close this command..." _value_reply; fi
fi
exit "$status"
