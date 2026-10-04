#!/bin/sh
set -u
BUNDLE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
unset PYTHONHOME PYTHONPATH PYTHONUSERBASE PYTHONPYCACHEPREFIX PYTHONSTARTUP PYTHONINSPECT PYTHONEXECUTABLE __PYVENV_LAUNCHER__ NODE_OPTIONS NODE_PATH
"$BUNDLE/runtime/python/bin/python3.10" -B -s "$BUNDLE/installer/desktop_value.py" diagnose "$@"
status=$?
if [ "$#" -eq 0 ] && [ -t 0 ]; then
  printf "Press Return to close this window... "
  read -r _value_reply
fi
exit "$status"
