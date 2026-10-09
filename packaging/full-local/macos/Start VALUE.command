#!/bin/sh
set -u
BUNDLE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
unset PYTHONHOME PYTHONPATH PYTHONUSERBASE PYTHONPYCACHEPREFIX PYTHONSTARTUP PYTHONINSPECT PYTHONEXECUTABLE __PYVENV_LAUNCHER__ NODE_OPTIONS NODE_PATH
# Never read bytecode from runtime/ or app/: a fresh empty prefix (R1-07).
PYTHONPYCACHEPREFIX="$(mktemp -d "${TMPDIR:-/tmp}/value-pycache.XXXXXX")" || exit 1
export PYTHONPYCACHEPREFIX
"$BUNDLE/runtime/python/bin/python3.10" -B -s "$BUNDLE/installer/desktop_value.py" start "$@"
status=$?
if [ "$#" -eq 0 ] && [ -t 0 ]; then
  printf "Press Return to close this window... "
  read -r _value_reply
fi
exit "$status"
