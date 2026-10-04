"""Read-only assessment of preserved run inputs; never launches a replay."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from gridform_core.run_snapshot import verify_run_input_snapshot
from gridform_core.frozen_input_integrity import verify_frozen_input_integrity


def assess_run_reproduction(run_root: Path, registry: object, *, verifier: Callable = verify_run_input_snapshot) -> dict[str, object]:
    snapshot_root = run_root / "input-snapshot"
    metadata_paths = (
        "input-snapshot/snapshot.json", "input-snapshot/project.json",
        "input-snapshot/pack/manifest.json", "input-snapshot/network-pack/manifest.json",
        "project-snapshot.json", "data-pack-snapshot.json", "provenance.json", "execution-bundle.json", "frozen-recovery-lineage.json",
    )
    report: dict[str, object] = {
        "schema_version": "value.run-reproduction-capability/v1", "run_id": run_root.name,
        "assessment": "unavailable", "fresh_replay_supported": False,
        "module_source_bundled": False, "portable_source_data_included": False,
        "environment_fully_pinned": False,
        "checks": {"frozen_input_hashes": "not_checked", "current_module_compatibility": "not_checked", "snapshot_verification": "not_checked"},
        "facts": {"snapshot_manifest_present": (snapshot_root / "snapshot.json").is_file(),
                  "annual_checkpoint_file_count": sum(1 for p in (run_root / "model-output/checkpoints-v2").glob("state-*.json") if p.is_file())},
        "blocking_reasons": [],
        "metadata_artifacts": [{"path": path, "download_url": f"/api/runs/{run_root.name}/artifacts/{path}"} for path in metadata_paths if (run_root / path).is_file()],
        "limitations": ["本检查只核验已保存的输入与当前模块入口身份，不保证完全精确复现，也不创建新 Run。", "完整源码与环境请使用冻结输入恢复审阅；此处不验证执行归档。", "便携 Run 包不包含源输入数据；检查点文件数量不表示可以恢复，请使用现有 Run 恢复检查。"],
    }
    checks = report["checks"]
    facts = report["facts"]
    if not facts["snapshot_manifest_present"]:
        report["blocking_reasons"] = ["未找到冻结输入快照清单。"]
        return report
    try:
        snapshot = json.loads((snapshot_root / "snapshot.json").read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError("快照清单不是对象")
        facts.update({"snapshot_id": snapshot.get("snapshot_id"), "input_tree_sha256": snapshot.get("input_tree_sha256"), "recorded_modules": snapshot.get("modules", [])})
        objects = snapshot.get("objects", [])
        if not isinstance(objects, list):
            raise ValueError("快照对象清单无效")
        present = 0
        for row in objects:
            if not isinstance(row, dict):
                raise ValueError("快照对象记录无效")
            candidate = (snapshot_root / str(row.get("pack_directory") or "pack") / str(row.get("snapshot_uri") or "")).resolve()
            candidate.relative_to(snapshot_root.resolve())
            present += int(candidate.is_file())
        facts.update({"recorded_data_object_count": len(objects), "present_data_object_count": present, "data_object_presence_only": True})
        verify_frozen_input_integrity(snapshot_root)
        checks["frozen_input_hashes"] = "verified"
        verifier(snapshot_root, registry)
    except Exception as exc:
        report["assessment"] = "blocked"
        checks["snapshot_verification"] = "failed"
        report["blocking_reasons"] = [str(exc)]
        return report
    checks.update({"frozen_input_hashes": "verified", "current_module_compatibility": "verified", "snapshot_verification": "verified"})
    report["assessment"] = "verified_recorded_inputs_and_modules"
    return report
