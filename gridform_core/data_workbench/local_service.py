"""Local filesystem implementation shared by the CLI and loopback API."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

from gridform_core.dataset_slots import DATASET_SLOTS
from gridform_core.gb_zonal_pack_builder import build_candidate

from .acquisition import UrllibFetchTransport, fetch_revision
from .contracts import PromotionRequest, SourceRevision
from .discovery import UrllibDiscoveryTransport, discover_source_safe
from .object_store import LocalObjectStore
from .promotion import promote_candidate
from .overlay_editor import OverlayEditor
from .registry import JsonSourceRegistry, package_registry_root
from .reporting import render_discovery_reports
from .review_reporting import render_candidate_review
from .validation import candidate_identity, validate_candidate_directory


def _safe_child(root: Path, identifier: str) -> Path:
    part = PurePosixPath(identifier)
    if part.is_absolute() or len(part.parts) != 1 or part.parts[0] in {"", ".", ".."}:
        raise ValueError("Identifier must be one safe path segment")
    target = (root / identifier).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Identifier escaped local Data Workbench state") from exc
    return target


class LocalDataWorkbenchService:
    def __init__(
        self,
        state_root: Path,
        *,
        registry: JsonSourceRegistry | None = None,
        dataset_slots: Sequence[Mapping[str, object]] = DATASET_SLOTS,
    ) -> None:
        self.state_root = Path(state_root).expanduser().resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.registry = registry or JsonSourceRegistry(package_registry_root("uk-network"))
        self.dataset_slots = dataset_slots
        self.object_store = LocalObjectStore(self.state_root / "objects")
        self.overlay_editor = OverlayEditor(self.state_root, dataset_slots)

    def sources(self) -> dict[str, object]:
        return {
            "schema_version": "value.data-sources/v1",
            "sources": [source.to_dict() for source in self.registry.list_sources()],
        }

    def discover(self, request: Mapping[str, object] | None = None) -> dict[str, object]:
        requested = set(str(item) for item in (request or {}).get("source_ids", []))
        sources = {
            source.source_id: source
            for source in self.registry.list_sources()
            if not requested or source.source_id in requested
        }
        unknown = requested - set(sources)
        if unknown:
            raise ValueError("Unknown official source IDs: " + ", ".join(sorted(unknown)))
        revisions = {
            source_id: discover_source_safe(source, UrllibDiscoveryTransport(), None)
            for source_id, source in sources.items()
        }
        report_root = self.state_root / "reports" / "freshness"
        refs = render_discovery_reports(
            revisions,
            report_root,
            source_definitions=sources,
        )
        return {
            "schema_version": "value.data-discovery-report/v1",
            "revisions": [
                revision.to_dict()
                for source_id in sorted(revisions)
                for revision in revisions[source_id]
            ],
            "report_refs": refs,
        }

    def freshness(self, request: Mapping[str, object] | None = None) -> dict[str, object]:
        return self.discover(request)

    def revisions(self) -> dict[str, object]:
        path = self.state_root / "reports" / "freshness" / "source_discovery_report.json"
        if not path.is_file():
            return {"schema_version": "value.data-revisions/v1", "revisions": []}
        payload = json.loads(path.read_text(encoding="utf-8"))
        revisions: list[dict[str, object]] = []
        for raw in payload.get("revisions", []):
            revision = dict(raw)
            try:
                receipt_root = _safe_child(
                    self.state_root / "receipts",
                    str(revision.get("source_id") or ""),
                )
                receipt_path = _safe_child(
                    receipt_root, f"{revision.get('revision_id') or ''}.json"
                )
            except ValueError:
                revisions.append(revision)
                continue
            if receipt_path.is_file():
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                revision["object_key"] = receipt.get("object_key")
                revision["redistribution_decision"] = receipt.get(
                    "redistribution_decision"
                )
                revision["status"] = "pinned"
            revisions.append(revision)
        return {"schema_version": "value.data-revisions/v1", "revisions": revisions}

    def fetch(
        self,
        request: Mapping[str, object],
        *,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> dict[str, object]:
        if request.get("schema_version") != "value.data-fetch-request/v1":
            raise ValueError("Expected value.data-fetch-request/v1")
        revision = SourceRevision.from_dict(request.get("revision", {}))  # type: ignore[arg-type]
        source = self.registry.get_source(revision.source_id)
        receipt_root = self.state_root / "receipts" / source.source_id
        receipt_path = _safe_child(receipt_root, f"{revision.revision_id}.json")
        receipt = fetch_revision(
            source,
            revision,
            UrllibFetchTransport(),
            self.object_store,
            cancel_requested=cancel_requested,
        )
        receipt_root.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt.to_dict()

    def compile(self, request: Mapping[str, object]) -> dict[str, object]:
        if request.get("schema_version") != "value.data-compile-request/v1":
            raise ValueError("Expected value.data-compile-request/v1")
        if request.get("recipe_id") != "prompt98-gb-zonal":
            raise ValueError("Unknown Data Workbench compiler recipe")
        inventory_key = str(request.get("inventory_key") or "")
        inventory = _safe_child(self.state_root / "inventories", inventory_key)
        candidate_name = str(request.get("candidate_name") or "")
        output = _safe_child(self.state_root / "candidates", candidate_name)
        result = build_candidate(inventory, output)
        workbench = self._bridge_prompt98_candidate(output, result)
        return {**result, "workbench_candidate_id": workbench["candidate_id"]}

    @staticmethod
    def _bridge_prompt98_candidate(
        output: Path, build_result: Mapping[str, object]
    ) -> dict[str, object]:
        """Expose Prompt 98 output to review without claiming it is installable."""

        candidate_manifest = json.loads(
            (output / "candidate-manifest.json").read_text(encoding="utf-8")
        )
        review_path = output / "review" / "reconciliation-and-rights.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        waivers = [
            f"etys.{boundary}.symmetric_forward_fallback"
            for boundary in build_result.get("assumed_symmetric_boundaries", [])
        ]
        payload: dict[str, object] = {
            "schema_version": "value.data-workbench-candidate/v1",
            "candidate_id": "",
            # Prompt 98 emits a scientific review tree, not value.data-pack/v1.
            # Keeping this empty makes the schema/hash gate block promotion
            # until a separately tested pack assembly step exists.
            "artifact_hashes": {},
            "source_rights": list(review.get("source_rights") or []),
            "spatial_topology": {
                "dangling_references": [],
                "connected": bool(candidate_manifest.get("bindings")),
                "map_ids_reconcile": (output / "review" / "zone-map.svg").is_file(),
            },
            "scientific_reconciliation": {
                "maximum_demand_residual_mwh": float(
                    build_result.get("maximum_demand_residual_mwh") or 0.0
                ),
            },
            "requested_waivers": sorted(waivers),
            "candidate_inventory": [
                {
                    "item_id": "prompt98-gb-zonal-review-tree",
                    "status": "experimental_candidate",
                    "usable_for": [
                        "scientific owner review",
                        "DSO-zone and ETYS-cut audit",
                        "deterministic build comparison",
                    ],
                    "not_usable_for": [
                        "runtime selection",
                        "formal benchmark installation before pack assembly",
                    ],
                    "blocking_reasons": [
                        "Prompt 98 has not emitted a promotable value.data-pack/v1 tree"
                    ],
                    "required_actions": [
                        "Assemble and validate the reviewed network artifacts as a versioned VALUE data pack"
                    ],
                }
            ],
            "prompt98_candidate_scientific_sha256": candidate_manifest.get(
                "candidate_scientific_sha256"
            ),
            "parent_candidate_id": None,
        }
        payload["candidate_id"] = candidate_identity(payload)
        (output / "workbench-candidate.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return payload

    def run_operation(
        self,
        operation: str,
        declared_input: Mapping[str, object],
        cancel_requested: Callable[[], bool],
    ) -> dict[str, object]:
        if cancel_requested():
            from .jobs import JobCancelled

            raise JobCancelled()
        if operation == "fetch":
            return self.fetch(declared_input, cancel_requested=cancel_requested)
        if operation == "validate":
            result = self.validate(str(declared_input.get("candidate_id") or ""))
        elif operation in {"discover", "compile"}:
            result = getattr(self, operation)(declared_input)
        else:
            raise ValueError(f"Unsupported Data Workbench job operation {operation}")
        if cancel_requested():
            from .jobs import JobCancelled

            raise JobCancelled()
        return result

    def candidates(self) -> dict[str, object]:
        root = self.state_root / "candidates"
        rows: list[dict[str, object]] = []
        for path in sorted(root.glob("*/workbench-candidate.json")) if root.exists() else []:
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "candidate_id": payload.get("candidate_id"),
                    "directory_id": path.parent.name,
                    "requested_waivers": payload.get("requested_waivers", []),
                }
            )
        return {"schema_version": "value.data-candidates/v1", "candidates": rows}

    def _candidate(self, identifier: str) -> Path:
        root = self.state_root / "candidates"
        direct = _safe_child(root, identifier)
        if (direct / "workbench-candidate.json").is_file():
            payload = json.loads((direct / "workbench-candidate.json").read_text(encoding="utf-8"))
            if payload.get("editor_kind") == "network_overlay":
                raise ValueError("Use the network overlay editor to review this candidate")
            return direct
        for path in sorted(root.glob("*/workbench-candidate.json")) if root.exists() else []:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("candidate_id") == identifier:
                if payload.get("editor_kind") == "network_overlay":
                    raise ValueError("Use the network overlay editor to review this candidate")
                return path.parent
        raise KeyError(f"Unknown data candidate {identifier}")

    def validate(self, candidate_id: str) -> dict[str, object]:
        root = self._candidate(candidate_id)
        report = validate_candidate_directory(root)
        render_candidate_review(root, report, root / "review")
        return report.to_dict()

    def promote(self, candidate_id: str, payload: Mapping[str, object]) -> dict[str, object]:
        request = PromotionRequest.from_dict(payload)
        if request.candidate_id != candidate_id:
            raise ValueError("Promotion path and Candidate ID differ")
        return promote_candidate(
            self._candidate(candidate_id),
            request,
            state_root=self.state_root,
            dataset_slots=self.dataset_slots,
        ).to_dict()

    def diff(self, identifier: str, request: Mapping[str, object]) -> dict[str, object]:
        other = str(request.get("other_candidate_id") or "")
        left = json.loads((self._candidate(identifier) / "workbench-candidate.json").read_text("utf-8"))
        right = json.loads((self._candidate(other) / "workbench-candidate.json").read_text("utf-8"))
        left_hashes = dict(left.get("artifact_hashes") or {})
        right_hashes = dict(right.get("artifact_hashes") or {})
        return {
            "schema_version": "value.data-candidate-diff/v1",
            "left_candidate_id": identifier,
            "right_candidate_id": other,
            "added": sorted(set(right_hashes) - set(left_hashes)),
            "removed": sorted(set(left_hashes) - set(right_hashes)),
            "changed": sorted(key for key in set(left_hashes) & set(right_hashes) if left_hashes[key] != right_hashes[key]),
        }

    def report(self, identifier: str) -> dict[str, object]:
        root = self._candidate(identifier)
        path = root / "review" / "candidate-review.json"
        if not path.is_file():
            self.validate(identifier)
        payload = json.loads(path.read_text(encoding="utf-8"))
        map_path = root / "review" / "zone-map.svg"
        if map_path.is_file() and map_path.stat().st_size <= 2 * 1024 * 1024:
            svg = map_path.read_text(encoding="utf-8")
            lowered = svg.lower()
            if not any(token in lowered for token in ("<script", "<foreignobject", "href=")):
                payload["audit_map_svg"] = svg
        return payload

    def bundles(self) -> dict[str, object]:
        installed = self.state_root / "installed-packs"
        rows = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(installed.glob("*/installation.json"))
        ] if installed.exists() else []
        return {"schema_version": "value.data-installed-bundles/v1", "bundles": rows}

    def export(self, identifier: str, request: Mapping[str, object] | None = None) -> dict[str, object]:
        root = self._candidate(identifier)
        payload = (root / "workbench-candidate.json").read_bytes()
        return {
            "schema_version": "value.data-export/v1",
            "candidate_id": identifier,
            "manifest_sha256": hashlib.sha256(payload).hexdigest(),
            "export_boundary": "use promoted value.data-bundle/v1 archive for redistribution",
        }
