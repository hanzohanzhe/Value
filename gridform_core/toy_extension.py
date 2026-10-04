"""Harmless built-in extension used to prove the Prompt 65 execution path."""

from __future__ import annotations

from typing import Mapping


class ToyAuditHooks:
    def initialize(self, payload: Mapping[str, object]) -> dict[str, object]:
        return {
            "schema_version": "value.toy-audit-state/v1",
            "owner": "value-toy-audit-extension",
            "years_seen": [],
            "input_year": payload.get("year"),
        }

    def after_psm(self, payload: Mapping[str, object]) -> dict[str, object]:
        return {
            "schema_version": "value.toy-audit-artifact/v1",
            "producer_extension": "value-toy-audit-extension",
            "artifact_type": "toy.audit.year-summary",
            "source_inputs_sha256": payload.get("input_sha256", "bounded-test-input"),
            "year": payload.get("year"),
        }
