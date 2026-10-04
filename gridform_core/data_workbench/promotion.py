"""Review-gated atomic promotion into the existing VALUE data-bundle installer."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from gridform_core.data_bundle import (
    build_data_bundle,
    install_data_bundle,
    validate_data_bundle,
)

from .contracts import PromotionRequest, SignedBundleReceipt
from .validation import registered_waiver, validate_candidate_directory


class PromotionError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def promote_candidate(
    candidate_root: Path,
    request: PromotionRequest,
    *,
    state_root: Path,
    dataset_slots: Sequence[Mapping[str, object]],
    before_revalidate: Callable[[], None] | None = None,
    approved_at: str | None = None,
) -> SignedBundleReceipt:
    root = Path(candidate_root).resolve()
    manifest_path = root / "workbench-candidate.json"
    first_manifest_sha = _sha(manifest_path)
    first = validate_candidate_directory(root, reviewer=request.reviewer)
    if first.candidate_id != request.candidate_id:
        raise PromotionError("Promotion request refers to a stale or different candidate")
    nonwaivable = [issue for issue in first.issues if not issue.waivable]
    if nonwaivable:
        raise PromotionError("Candidate has non-waivable validation failures")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    observed = {str(item) for item in payload.get("requested_waivers", [])}
    accepted = {str(item) for item in request.accepted_waivers}
    unknown = sorted(item for item in accepted if not registered_waiver(item))
    if unknown:
        raise PromotionError("Promotion request contains unknown waiver IDs: " + ", ".join(unknown))
    unrelated = sorted(accepted - observed)
    if unrelated:
        raise PromotionError("Promotion request contains unrelated waiver IDs: " + ", ".join(unrelated))
    missing = sorted(observed - accepted)
    if missing:
        raise PromotionError("Promotion request has not accepted every required waiver: " + ", ".join(missing))

    if before_revalidate is not None:
        before_revalidate()
    second = validate_candidate_directory(root, reviewer=request.reviewer)
    if _sha(manifest_path) != first_manifest_sha or second.candidate_id != first.candidate_id:
        raise PromotionError("Candidate changed and became stale during promotion")
    if any(not issue.waivable for issue in second.issues):
        raise PromotionError("Candidate changed or failed revalidation before promotion")

    state = Path(state_root).resolve()
    staging = state / "promotion-staging"
    staging.mkdir(parents=True, exist_ok=True)
    archive = staging / f"{request.candidate_id}-{request.version}.zip"
    bundle_result = build_data_bundle(pack_root=root / "pack", destination=archive)
    validated = validate_data_bundle(archive)
    installation = install_data_bundle(
        archive,
        packs_root=state / "installed-packs",
        dataset_slots=dataset_slots,
        rights_acknowledged=True,
        minimum_free_space_bytes=0,
    )
    timestamp = approved_at or datetime.now(timezone.utc).isoformat()
    receipt = SignedBundleReceipt(
        network_pack_id=str(installation["pack_id"]),
        candidate_id=request.candidate_id,
        bundle_sha256=str(bundle_result["sha256"]),
        manifest_sha256=_sha(root / "pack" / "manifest.json"),
        approved_by=request.reviewer,
        approved_at=timestamp,
        accepted_waivers=tuple(sorted(accepted)),
    )
    if receipt.bundle_sha256 != validated.bundle_sha256:
        raise PromotionError("Existing bundle validator reported a different archive identity")
    _atomic_json(
        state / "approvals" / f"{request.candidate_id}.json",
        receipt.to_dict(),
    )
    return receipt
