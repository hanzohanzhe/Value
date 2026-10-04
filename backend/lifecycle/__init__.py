"""Run lifecycle primitives that import only the Python standard library.

The package is deliberately light: the model worker imports it before any
scientific dependency (numpy, pandas, the copied kernel) so that a worker can
take its lease, install signal handlers and record an import failure even when
those dependencies are broken.  ``gridform_core`` re-exports the state table
from here, so nothing in this package may import ``gridform_core`` or any
third-party module (enforced by ``tests/test_lifecycle_primitives.py``).

Modules:

``file_locks``  advisory inter-process locks (POSIX flock / Windows msvcrt)
``atomic_io``   unique-temporary, fsync'd, atomically replaced writes
``states``      the run state table (single source of truth)
``run_status``  the only writer API for ``status.json``
``worker_lease``/``worker_entry``  worker liveness lease and light entry point
``python_argv`` interpreter argv that never reads source-tree bytecode
"""
