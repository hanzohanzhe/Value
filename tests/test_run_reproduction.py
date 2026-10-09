import json
from pathlib import Path

import backend.run_reproduction as run_reproduction
from backend.run_reproduction import assess_run_reproduction


def _accept_frozen_inputs(monkeypatch, calls=None):
    """Stand in for verify_frozen_input_integrity (the fixtures carry no real v1 inputs)."""

    def accept(path):
        if calls is not None:
            calls.append(path)
        return {}

    monkeypatch.setattr(run_reproduction, "verify_frozen_input_integrity", accept)


def test_missing_snapshot_is_unavailable_and_read_only(tmp_path):
    before = list(tmp_path.iterdir())
    report = assess_run_reproduction(tmp_path, object())
    assert report["assessment"] == "unavailable"
    assert report["checks"]["snapshot_verification"] == "not_checked"
    assert list(tmp_path.iterdir()) == before


def test_verified_snapshot_uses_existing_validator_and_preserves_files(tmp_path, monkeypatch):
    root = tmp_path / "input-snapshot"
    root.mkdir()
    manifest = root / "snapshot.json"
    manifest.write_text(json.dumps({"snapshot_id": "saved", "objects": [], "modules": []}))
    before = manifest.read_bytes()
    integrity_calls = []
    _accept_frozen_inputs(monkeypatch, integrity_calls)
    calls = []
    def verify(path, registry):
        calls.append((path, registry))
        return {}
    registry = object()
    report = assess_run_reproduction(tmp_path, registry, verifier=verify)
    assert integrity_calls == [root]
    assert calls == [(root, registry)]
    assert report["assessment"] == "verified_recorded_inputs_and_modules"
    assert report["fresh_replay_supported"] is False
    assert report["checks"]["frozen_input_hashes"] == "verified"
    assert manifest.read_bytes() == before
    assert len(list(root.iterdir())) == 1


def test_failed_validator_does_not_claim_partial_verification(tmp_path, monkeypatch):
    root = tmp_path / "input-snapshot"
    root.mkdir()
    (root / "snapshot.json").write_text(json.dumps({"objects": [], "modules": []}))
    _accept_frozen_inputs(monkeypatch)
    def reject(*args):
        raise ValueError("Module source changed after enqueue")
    report = assess_run_reproduction(tmp_path, object(), verifier=reject)
    assert report["assessment"] == "blocked"
    assert report["checks"]["current_module_compatibility"] == "not_checked"
    assert report["checks"]["snapshot_verification"] == "failed"
    # The frozen inputs were verified before the module check failed.
    assert report["checks"]["frozen_input_hashes"] == "verified"
    assert report["blocking_reasons"] == ["Module source changed after enqueue"]


def test_unready_snapshot_blocks_before_the_module_validator(tmp_path):
    root = tmp_path / "input-snapshot"
    root.mkdir()
    (root / "snapshot.json").write_text(json.dumps({"objects": [], "modules": []}))
    calls = []
    report = assess_run_reproduction(tmp_path, object(), verifier=lambda *args: calls.append(args))
    assert calls == []
    assert report["assessment"] == "blocked"
    assert report["checks"]["frozen_input_hashes"] == "not_checked"
    assert report["checks"]["current_module_compatibility"] == "not_checked"
    assert report["checks"]["snapshot_verification"] == "failed"
    assert report["blocking_reasons"] == ["Snapshot is not a ready v1 recorded input"]
