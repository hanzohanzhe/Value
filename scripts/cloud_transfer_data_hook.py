"""Fail-closed hook placeholder; replace with the separately reviewed fixture builder.

Contract: --full-root, --fixture-dir, --output-dir, --receipt; local
VALUE_APPROVED_REUSE_SOURCE and VALUE_DATA_TARGET_TAG environment variables.
This placeholder never reads a dataset, downloads, builds, or uploads anything.
"""
import argparse

parser = argparse.ArgumentParser(description="Reviewed offline data-fixture hook")
parser.add_argument("--full-root", required=True)
parser.add_argument("--fixture-dir", required=True)
parser.add_argument("--output-dir", required=True)
parser.add_argument("--receipt", required=True)
parser.parse_args()
raise SystemExit("Reviewed data-fixture builder is not installed; no output produced")
