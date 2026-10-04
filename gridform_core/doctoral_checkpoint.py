"""Atomic national JSON checkpoints, separate from legacy/zonal recovery.

The independently published index anchors the accepted ledger prefix. A crash
between bundle and index publication leaves the previous indexed bundle active.
This is an accidental corruption/identity guard, not protection against an
attacker who can rewrite both the data and its local trust anchors. No pickle,
historical-checkpoint migration, automatic replay or deletion is performed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Mapping
import uuid

from .builtin.scheme_c_1000twh.doctoral_market import ENGINE_SCHEMA, _hash, _rule_identity
from .builtin.scheme_c_1000twh.doctoral_period_ledger import DoctoralPeriodLedger
from .builtin.scheme_c_1000twh.doctoral_state import DoctoralRuntimeState

SCHEMA = "value.doctoral-disk-checkpoint/v1"
INDEX_SCHEMA = "value.doctoral-checkpoint-index/v1"
_IDENTITY_KEYS = {"run_id", "year", "engine_input_sha256", "source_rule_sha256",
    "weather_sha256", "data_pack_sha256", "parameters_sha256", "thesis_contract_sha256",
    "planning_state_sha256", "nuclear_policy_sha256"}


def month_end_periods() -> tuple[int, ...]:
    """Model calendar: 365 days, 48 half hours/day; no inserted leap day."""
    total, ends = 0, []
    for days in (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31):
        total += days * 48
        ends.append(total)
    return tuple(ends)


def _encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_bytes(path: Path, raw: bytes) -> None:
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class DoctoralCheckpointStore:
    """One model year's immutable-input checkpoint stream.

    The caller supplies freshly verified identities, not values copied out of
    an old checkpoint. Every validated checkpoint is retained; at least the last
    two remain recoverable. A new model year uses a separate store/identity.
    """
    def __init__(self, directory: Path, *, frozen_identity: Mapping):
        identity = dict(frozen_identity)
        if not _IDENTITY_KEYS <= set(identity):
            raise ValueError("Incomplete doctoral checkpoint frozen identity")
        if not isinstance(identity["run_id"], str) or not identity["run_id"] or type(identity["year"]) is not int:
            raise ValueError("Invalid doctoral checkpoint run/year identity")
        for field in _IDENTITY_KEYS - {"run_id", "year"}:
            value = identity[field]
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"Invalid doctoral checkpoint {field}")
        self._identity = json.loads(_encode(identity))
        self.directory = Path(directory).resolve()
        self.index_path = self.directory / "index.json"

    def _index(self) -> dict:
        if not self.index_path.exists():
            return {"schema_version": INDEX_SCHEMA, "identity": self._identity, "records": []}
        payload = json.loads(self.index_path.read_bytes())
        if (payload.get("schema_version") != INDEX_SCHEMA or payload.get("identity") != self._identity
                or not isinstance(payload.get("records"), list)):
            raise ValueError("Doctoral checkpoint index identity mismatch")
        previous = -1
        for row in payload["records"]:
            period = row.get("next_period_index")
            if type(period) is not int or not previous < period <= 17520:
                raise ValueError("Doctoral checkpoint index periods are not strictly increasing")
            filename = row.get("filename")
            if not isinstance(filename, str) or filename != f"checkpoint-{period:05d}.json":
                raise ValueError("Invalid checkpoint filename; directory traversal is not allowed")
            previous = period
        return payload

    def _publish_index(self, index: Mapping) -> None:
        _atomic_bytes(self.index_path, _encode(index))

    def latest_record(self) -> dict | None:
        records = self._index()["records"]
        return dict(records[-1]) if records else None

    def _validate_payload(self, payload: Mapping, record: Mapping) -> None:
        if payload.get("schema_version") != SCHEMA or payload.get("identity") != self._identity:
            raise ValueError("Doctoral checkpoint bundle identity mismatch")
        if _hash(payload.get("annual_state")) != self._identity["planning_state_sha256"]:
            raise ValueError("Doctoral checkpoint planning state identity mismatch")
        engine = payload.get("engine", {})
        if (engine.get("schema_version") != ENGINE_SCHEMA
                or engine.get("input_sha256") != self._identity["engine_input_sha256"]
                or engine.get("rule_identity") != _rule_identity()
                or _hash(engine.get("rule_identity")) != self._identity["source_rule_sha256"]):
            raise ValueError("Doctoral checkpoint engine identity mismatch")
        if _hash(engine.get("state")) != engine.get("state_sha256"):
            raise ValueError("Doctoral checkpoint engine state hash mismatch")
        state = DoctoralRuntimeState.from_dict(engine["state"])
        if state.year != self._identity["year"] or state.next_period_index != record["next_period_index"]:
            raise ValueError("Doctoral checkpoint year/period identity mismatch")
        ledger = DoctoralPeriodLedger.from_snapshot(payload["ledger"],
            expected_input_sha256=self._identity["engine_input_sha256"],
            expected_source_rule_sha256=self._identity["source_rule_sha256"],
            expected_weather_sha256=self._identity["weather_sha256"],
            expected_prefix_sha256=record["ledger_prefix_sha256"])
        if ledger.current_state.to_dict() != state.to_dict():
            raise ValueError("Doctoral checkpoint engine and ledger state disagree")
        if payload["ledger"]["header"]["run_id"] != self._identity["run_id"]:
            raise ValueError("Doctoral checkpoint ledger run identity mismatch")
        boundary = payload.get("boundary")
        if boundary not in {"diagnostic", "monthly", "annual"}:
            raise ValueError("Unknown doctoral checkpoint boundary")
        if boundary == "monthly" and state.next_period_index not in month_end_periods():
            raise ValueError("Not a monthly model-calendar boundary")
        if boundary == "annual" and not ledger.coverage["annual_complete"]:
            raise ValueError("Not a complete annual ledger boundary")

    def publish(self, engine, ledger: DoctoralPeriodLedger, *, annual_state: Mapping,
                boundary: str = "monthly", runtime_artifacts: Mapping | None = None) -> dict:
        payload = {"schema_version": SCHEMA, "identity": self._identity,
            "boundary": boundary, "engine": engine.export_state(),
            "ledger": ledger.snapshot(), "annual_state": dict(annual_state)}
        if runtime_artifacts is not None:
            payload["runtime_artifacts"] = dict(runtime_artifacts)
        period = engine.state.next_period_index
        record = {"next_period_index": period, "next_absolute_period": engine.state.next_absolute_period,
            "filename": f"checkpoint-{period:05d}.json", "ledger_prefix_sha256": ledger.prefix_sha256,
            "bundle_sha256": _sha(_encode(payload)), "boundary": boundary}
        self._validate_payload(payload, record)
        index = self._index()
        if index["records"] and period <= index["records"][-1]["next_period_index"]:
            if record == index["records"][-1]:
                self.load_latest()  # Idempotence also checks bytes on disk.
                return record
            raise ValueError("Cannot overwrite or rewind an accepted doctoral checkpoint")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / record["filename"]
        raw = _encode(payload)
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError("Conflicting unindexed checkpoint bundle; preserve for diagnosis")
        else:
            _atomic_bytes(path, raw)
        reread = path.read_bytes()
        if _sha(reread) != record["bundle_sha256"]:
            raise ValueError("Doctoral checkpoint readback hash mismatch")
        self._validate_payload(json.loads(reread), record)
        self._publish_index({**index, "records": index["records"] + [record]})
        if self.latest_record() != record:
            raise ValueError("Doctoral checkpoint index readback mismatch")
        return record

    def load_latest(self) -> dict | None:
        record = self.latest_record()
        if record is None:
            return None
        raw = (self.directory / record["filename"]).read_bytes()
        if _sha(raw) != record["bundle_sha256"]:
            raise ValueError("Doctoral checkpoint bundle hash mismatch")
        payload = json.loads(raw)
        self._validate_payload(payload, record)
        return payload
