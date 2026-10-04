"""VALUE Data Workbench command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.data_workbench.cli import execute_command
from gridform_core.data_workbench.local_service import LocalDataWorkbenchService
from gridform_core.data_workbench.state import resolve_data_workbench_root


def main() -> int:
    service = LocalDataWorkbenchService(resolve_data_workbench_root())
    result = execute_command(service, sys.argv[1:])
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
