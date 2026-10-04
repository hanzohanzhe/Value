# External module conformance fixtures

These deliberately small modules prove that VALUE resolves and executes Python
implementations selected through public `value.module/v2` manifests. They are
test fixtures, not scientific alternatives.

Copy the desired manifest from `manifests/` into the directory reported by
`python scripts/doctor.py` (`VALUE_DATA_HOME/modules`). Ensure this repository or
the installed fixture package is on Python's import path, then run:

```powershell
python -m gridform_core.module_conformance --modules examples/external_modules/manifests
```

The marked PSM adds exactly £123.45 to its delegated LP result and records
`external_fixture_executed=true`. That bounded difference is used by the real
application-service test to prove the selected code ran.
