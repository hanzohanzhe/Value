"""Build a deterministic uploadable VALUE module ZIP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gridform_core.module_bundle import build_module_bundle  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a value.module-bundle/v1 ZIP")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--license", type=Path, required=True)
    parser.add_argument("--readme", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = build_module_bundle(
        manifest_path=arguments.manifest,
        source_root=arguments.source_root,
        license_path=arguments.license,
        readme_path=arguments.readme,
        destination=arguments.output,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
