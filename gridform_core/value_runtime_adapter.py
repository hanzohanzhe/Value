"""Public VALUE boundary around the protected doctoral-reproduction kernel."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from .builtin.scheme_c_1000twh.scheme_c_context import (
    SchemeCRunContext,
    build_scheme_c_run_context as build_value_run_context,
    persist_or_verify_context as _persist_protected_context,
)


_KEY_NAMES = {
    "live_scheme_c_clearing_invocation": "live_value_clearing_invocation",
}
_STRING_VALUES = {
    "force.live-state-coupling/v1": "value.live-state-coupling/v1",
    "force.fleet-economics-summary/v1": "value.fleet-economics-summary/v1",
    "force.legacy-config-session/v1": "value.legacy-config-session/v1",
    "force.scheme-c-run-context/v1": "value.run-context/v1",
    "force-scheme-c-compatibility-storage": "value-doctoral-reproduction-storage",
    "scheme_c_thesis_compatibility": "doctoral_thesis_reproduction",
    "scheme_c_no_separate_non_storage_fom_term": "no_separate_non_storage_fom_term",
}
_RECOVERABLE_RUNTIME_KEYS = frozenset({"runtime.market_trace_level"})


def public_value_payload(value: object) -> object:
    """Rename protected implementation labels at the public artifact boundary."""

    if isinstance(value, Mapping):
        return {
            _KEY_NAMES.get(str(key), str(key)): public_value_payload(child)
            for key, child in value.items()
        }
    if isinstance(value, tuple):
        return tuple(public_value_payload(child) for child in value)
    if isinstance(value, list):
        return [public_value_payload(child) for child in value]
    if isinstance(value, str):
        return _STRING_VALUES.get(value, value.replace("native-scheme-c-session", "value-kernel-session"))
    return value


def persist_or_verify_value_context(context: SchemeCRunContext) -> Path:
    """Persist one resume-safe VALUE context without changing the protected code."""

    destination = context.output_dir / "value-run-context.json"
    if destination.is_file():
        previous = json.loads(destination.read_text(encoding="utf-8"))
        if previous.get("context_sha256") != context.context_sha256:
            previous_payload = {
                key: value
                for key, value in previous.items()
                if key not in {"schema_version", "context_sha256"}
            }
            current_payload = dict(public_value_payload(context.identity_payload()))

            def without_recoverable_runtime(payload: Mapping[str, object]) -> dict[str, object]:
                normalized = dict(payload)
                runtime = dict(normalized.get("runtime_options") or {})
                for key in _RECOVERABLE_RUNTIME_KEYS:
                    runtime.pop(key, None)
                normalized["runtime_options"] = runtime
                return normalized

            if without_recoverable_runtime(previous_payload) != without_recoverable_runtime(current_payload):
                raise ValueError("VALUE run context changed after the checkpoint was created")
            previous_runtime = dict(previous_payload.get("runtime_options") or {})
            current_runtime = dict(current_payload.get("runtime_options") or {})
            recovery = destination.with_name("value-run-context-recovery.json")
            temporary = recovery.with_suffix(".json.incomplete")
            temporary.write_text(
                json.dumps(
                    {
                        "schema_version": "value.run-context-recovery/v1",
                        "original_context_sha256": previous["context_sha256"],
                        "resumed_context_sha256": context.context_sha256,
                        "scientific_identity_unchanged": True,
                        "runtime_changes": {
                            key: {
                                "from": previous_runtime.get(key),
                                "to": current_runtime.get(key),
                            }
                            for key in sorted(_RECOVERABLE_RUNTIME_KEYS)
                            if previous_runtime.get(key) != current_runtime.get(key)
                        },
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            temporary.replace(recovery)
        return destination

    protected = _persist_protected_context(context)
    payload = public_value_payload(json.loads(protected.read_text(encoding="utf-8")))
    temporary = destination.with_suffix(".json.incomplete")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(destination)
    protected.unlink(missing_ok=True)
    return destination


def finalize_value_runtime_artifacts(output_dir: Path) -> None:
    """Rewrite the small compatibility-session audit file at the public boundary."""

    path = Path(output_dir) / "legacy-config-session.json"
    if not path.is_file():
        return
    payload = public_value_payload(json.loads(path.read_text(encoding="utf-8")))
    temporary = path.with_suffix(".json.incomplete")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    temporary.replace(path)
