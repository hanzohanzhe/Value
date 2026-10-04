"""Portable identity for the author-selected final9.6 thesis interpretation."""
from pathlib import Path
import hashlib
import json

THESIS96_CONTRACT = Path(__file__).parent / "data/doctoral_alignment/thesis_final96_contract.json"


def load_thesis96_contract() -> dict:
    payload = json.loads(THESIS96_CONTRACT.read_text(encoding="utf-8"))
    if (payload.get("schema_version") != "value.doctoral-thesis-contract/v1"
            or payload.get("profile_id") != "thesis_final9.6"
            or payload.get("source_sha256") != "47983aea5c201549cb3b212c554e5f04cfcfb5d7fce413fb5a28ddd939b16d22"):
        raise ValueError("Incompatible final9.6 thesis contract")
    return payload


def thesis96_contract_identity() -> dict[str, str]:
    payload = load_thesis96_contract()
    return {"profile_id": payload["profile_id"], "source_sha256": payload["source_sha256"],
            "contract_sha256": hashlib.sha256(THESIS96_CONTRACT.read_bytes()).hexdigest()}
