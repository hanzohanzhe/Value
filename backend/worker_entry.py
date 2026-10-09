"""``python -m backend.worker_entry``: the light model-worker entry point.

The implementation lives in :mod:`backend.lifecycle.worker_entry` (standard
library only until the lease is held); see P0_CONVENTIONS section 8.
"""

from backend.lifecycle.worker_entry import main

if __name__ == "__main__":
    raise SystemExit(main())
