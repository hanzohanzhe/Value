"""Read-only integrity of recorded normalized inputs, without loading implementations.

This proves internal recorded identities and saved data bytes. It does not prove
availability of historical Python source, dependencies or an executable runtime.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re


class FrozenInputIntegrityError(ValueError):
    pass


SHA = re.compile(r"^[0-9a-fA-F]{64}$")
IDENTITY_FIELDS = ("project_sha256", "pack_manifest_sha256", "objects", "modules")
MODULE_FIELDS = ("slot", "module_id", "module_version", "contract_version", "entry_point", "source_sha256")
HOOKS = ("preflight", "initialize", "before_psm", "after_psm", "before_cem", "after_cem", "transition", "finalize")


def _fail(message: str):
    raise FrozenInputIntegrityError(message)


def _mapping(value, label):
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _array(value, label):
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be nonempty text")
    return value


def _sha(value, label):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        _fail(f"{label} must be a SHA-256")
    return value.lower()


def _hash(value, *, ascii=False):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=ascii, allow_nan=False).encode("utf-8")).hexdigest()


def _uri(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        _fail("Frozen file URI must be a safe relative path")
    parts = value.split("/")
    if PurePosixPath(value).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        _fail("Frozen file URI must be a safe relative path")
    return value


def _file(root, relative):
    relative = _uri(relative)
    path = root
    if path.is_symlink():
        _fail("Snapshot root must not be a symbolic link")
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            _fail("Frozen file path contains a symbolic link")
    if not path.is_file():
        _fail(f"Frozen file is missing or non-regular: {relative}")
    return path


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail(f"Duplicate JSON field: {key}")
        value[key] = item
    return value


def _json(root, relative):
    path = _file(root, relative)
    if path.stat().st_size > 32 * 1024 * 1024:
        _fail("Frozen JSON metadata exceeds the 32 MiB bound")
    return _mapping(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs,
                              parse_constant=lambda value: _fail(f"Nonfinite JSON: {value}")), relative)


def _file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        before = path.stat()
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
        after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        _fail("Frozen data changed while being read")
    return digest.hexdigest(), before.st_size


def _extensions(graph, project, module_ids, available_roles):
    selected = _array(project.get("selected_extensions", []), "Project extensions")
    if any(not isinstance(item, str) or not item for item in selected) or len(set(selected)) != len(selected):
        _fail("Project extension selection is invalid or repeated")
    if graph is None:
        if selected:
            _fail("Frozen extension graph is missing")
        return {"complete": True, "extension_graph_self_check": "verified", "missing_recorded_fields": []}
    graph = _mapping(graph, "Extension graph")
    if graph.get("schema_version") != "value.resolved-extension-graph/v1":
        _fail("Unsupported frozen extension graph")
    entries = _array(graph.get("extensions"), "Extension entries")
    if "manifests" not in graph and "hook_source_identities" not in graph:
        # Production pre-source-archive v1 to_dict omitted the full manifests
        # used to calculate graph_sha256. Preserve that original projection;
        # it is covered by the outer snapshot/module hash, but cannot itself
        # prove declarations, hook code or hidden default/scope constraints.
        expected_fields = {"schema_version", "graph_sha256", "extensions", "parameters", "parameter_schema_hashes", "hook_order"}
        if set(graph) != expected_fields:
            _fail("Unsupported incomplete extension graph projection")
        _sha(graph.get("graph_sha256"), "Legacy extension graph hash")
        ids = []
        for entry in entries:
            entry = _mapping(entry, "Legacy extension identity")
            if set(entry) != {"id", "version", "namespace", "manifest_sha256"}:
                _fail("Legacy extension identity coverage differs")
            ids.append(_text(entry["id"], "Legacy extension ID"))
            _text(entry["version"], "Legacy extension version")
            _text(entry["namespace"], "Legacy extension namespace")
            _sha(entry["manifest_sha256"], "Legacy extension manifest hash")
        if len(set(ids)) != len(ids) or set(ids) != set(selected):
            _fail("Legacy extension selection differs from project")
        schemas = _mapping(graph["parameter_schema_hashes"], "Legacy parameter schema hashes")
        if set(schemas) != set(ids):
            _fail("Legacy extension parameter schema coverage differs")
        for digest in schemas.values():
            _sha(digest, "Legacy parameter schema hash")
        parameters = _mapping(graph["parameters"], "Legacy resolved parameters")
        supplied = _mapping(project.get("extension_parameters", {}), "Project extension parameters")
        if any(name not in parameters or parameters[name] != value for name, value in supplied.items()):
            _fail("Legacy extension parameters differ from project overrides")
        order = _mapping(graph["hook_order"], "Legacy hook order")
        if set(order) != set(HOOKS):
            _fail("Legacy hook lifecycle coverage differs")
        for values in order.values():
            values = _array(values, "Legacy hook ordering")
            if any(not isinstance(item, str) or item not in ids for item in values) or len(set(values)) != len(values):
                _fail("Legacy hook ordering references unknown or repeated extensions")
        return {"complete": False, "extension_graph_self_check": "unavailable_legacy_projection",
                "missing_recorded_fields": ["extension_graph.manifests", "extension_graph.hook_source_identities",
                    "extension_graph.parameter_defaults", "extension_graph.required_data_roles",
                    "extension_graph.composed_module_ids", "extension_graph.hook_order_constraints"]}
    manifests = _mapping(graph.get("manifests"), "Frozen extension manifests")
    source = _mapping(graph.get("hook_source_identities"), "Frozen extension hook identities")
    ids = []
    declared_hooks = {}
    hook_declarations = {}
    declarations = {}
    schema_hashes = {}
    for entry in entries:
        entry = _mapping(entry, "Extension entry")
        extension_id = _text(entry.get("id"), "Extension ID")
        ids.append(extension_id)
        manifest = _mapping(manifests.get(extension_id), "Frozen extension manifest")
        if manifest.get("schema_version") != "value.extension-bundle/v1":
            _fail("Unsupported frozen extension manifest")
        if any(entry.get(key) != manifest.get(key) for key in ("id", "version", "namespace")):
            _fail("Frozen extension declaration identity differs")
        if _sha(entry.get("manifest_sha256"), "Extension manifest hash") != _hash(manifest):
            _fail("Frozen extension manifest hash differs")
        composed = _array(manifest.get("composed_module_ids"), "Composed module IDs")
        if any(not isinstance(item, str) or item not in module_ids for item in composed):
            _fail("Frozen extension requires an unselected composed module")
        for role in _array(manifest.get("data_roles"), "Extension data roles"):
            role = _mapping(role, "Extension data role")
            role_name = _text(role.get("role"), "Extension role name")
            if not isinstance(role.get("required"), bool):
                _fail("Extension role required flag is invalid")
            if role["required"] and role_name not in available_roles:
                _fail("Frozen extension required input role is missing")
        hooks = _array(manifest.get("hooks"), "Frozen hooks")
        identities = _array(source.get(extension_id), "Frozen hook source identities")
        if len(hooks) != len(identities):
            _fail("Frozen hook identity coverage differs")
        hook_names = set()
        for hook, identity in zip(hooks, identities):
            hook, identity = _mapping(hook, "Hook"), _mapping(identity, "Hook identity")
            if any(hook.get(key) != identity.get(key) for key in ("hook", "implementation")):
                _fail("Frozen hook entry identity differs")
            _sha(identity.get("source_sha256"), "Frozen hook source hash")
            name = _text(hook.get("hook"), "Hook name")
            if name not in HOOKS:
                _fail("Unknown frozen lifecycle hook")
            if name in hook_names:
                _fail("Repeated extension hook")
            hook_names.add(name)
            declared_hooks.setdefault(name, set()).add(extension_id)
            hook_declarations.setdefault(name, {})[extension_id] = hook
        for declaration in _array(manifest.get("parameters"), "Extension parameters"):
            declaration = _mapping(declaration, "Extension parameter")
            parameter_name = _text(declaration.get("name"), "Extension parameter name")
            declarations[parameter_name] = declaration
        schema_hashes[extension_id] = _hash(_array(manifest.get("parameters"), "Extension parameter schema"))
    if len(set(ids)) != len(ids) or set(ids) != set(selected) or set(manifests) != set(ids) or set(source) != set(ids):
        _fail("Frozen extension selection coverage differs")
    if graph.get("parameter_schema_hashes") != schema_hashes:
        _fail("Frozen extension parameter schema hash differs")
    order = _mapping(graph.get("hook_order"), "Hook order")
    for name, values in order.items():
        values = _array(values, "Hook order entries")
        if any(not isinstance(item, str) for item in values) or len(set(values)) != len(values) or set(values) != declared_hooks.get(name, set()):
            _fail("Frozen hook order coverage differs")
    if set(order) != set(HOOKS):
        _fail("Frozen hook order lifecycle coverage differs")
    for name in HOOKS:
        hooks = hook_declarations.get(name, {})
        edges = {item: set() for item in hooks}
        for extension_id, hook in hooks.items():
            for predecessor in _array(hook.get("after"), "Hook predecessors"):
                if predecessor in hooks:
                    edges[extension_id].add(predecessor)
            for successor in _array(hook.get("before"), "Hook successors"):
                if successor in hooks:
                    edges[successor].add(extension_id)
        expected_order = []
        while edges:
            ready = sorted(item for item, dependencies in edges.items() if not dependencies)
            if not ready:
                _fail("Frozen hook ordering is cyclic")
            expected_order.extend(ready)
            for item in ready:
                edges.pop(item)
                for dependencies in edges.values():
                    dependencies.discard(item)
        if expected_order != order[name]:
            _fail("Frozen hook order differs from its declarations")
    parameters = _mapping(graph.get("parameters"), "Extension parameters")
    supplied = _mapping(project.get("extension_parameters", {}), "Project extension parameters")
    if set(parameters) != set(declarations) or not set(supplied).issubset(declarations):
        _fail("Frozen extension parameter coverage differs")
    for name, declaration in declarations.items():
        if parameters[name] != supplied.get(name, declaration.get("default")):
            _fail("Frozen extension parameters differ from project/default declarations")
    payload = {"extensions": [manifests[item] for item in ids], "hook_source_identities": source,
               "parameters": parameters,
               "parameter_schema_hashes": graph["parameter_schema_hashes"], "hook_order": order}
    if _sha(graph.get("graph_sha256"), "Extension graph hash") != _hash(payload):
        _fail("Frozen extension graph hash differs")
    return {"complete": True, "extension_graph_self_check": "verified", "missing_recorded_fields": []}


def _modules(snapshot, project, available_roles):
    graph = _mapping(snapshot.get("module_resolution_graph"), "Frozen module graph")
    if graph.get("schema_version") != "value.module-resolution-graph/v1":
        _fail("Unsupported frozen module graph")
    graph_modules = _mapping(graph.get("modules"), "Frozen module identities")
    selection = _mapping(project.get("modules"), "Project module selection")
    normalized = {}
    for slot, module_id in selection.items():
        _text(slot, "Project module slot")
        if module_id in (None, ""):
            continue
        normalized[slot] = _text(module_id, "Selected module")
    if "psm" not in normalized:
        _fail("Project PSM selection is missing")
    rows = _array(snapshot.get("modules"), "Snapshot module identities")
    actual = {}
    for row in rows:
        row = _mapping(row, "Snapshot module identity")
        slot = _text(row.get("slot"), "Snapshot module slot")
        if slot in actual:
            _fail("Repeated snapshot module slot")
        identity = _mapping(graph_modules.get(slot), "Frozen module graph identity")
        if not (set(MODULE_FIELDS) | {"distribution", "scientific_version", "execution_kind"}).issubset(identity):
            _fail("Frozen module graph identity coverage is incomplete")
        _text(identity.get("distribution"), "Module distribution")
        _text(identity.get("execution_kind"), "Module execution kind")
        if identity.get("scientific_version") is not None:
            _text(identity["scientific_version"], "Module scientific version")
        for field in MODULE_FIELDS:
            value = _text(row.get(field), f"Module {field}")
            if field == "source_sha256":
                if _sha(value, "Module source hash") != _sha(identity.get(field), "Graph module source hash"):
                    _fail("Module source identity differs from frozen graph")
            elif value != identity.get(field):
                _fail("Module identity differs from frozen graph")
        actual[slot] = row["module_id"]
    if set(actual) != set(graph_modules):
        _fail("Snapshot module coverage differs from frozen graph")
    # These are the only additions made by server/model_runner for historical
    # project selections. A recorded graph row must independently confirm them.
    normalized.setdefault("transition", "value-annual-state-transition")
    if "storage_cost" not in normalized and actual.get("storage_cost") == "dynamic-annual-storage-cost":
        psm = graph_modules["psm"]
        if (normalized["psm"] not in {"value-bid-at-cost-psm", "value-staged-bid-at-cost-psm"}
                or psm.get("entry_point") not in {
                    "gridform_core.builtin.value_modules:ValueBidAtCostPSM",
                    "gridform_core.builtin.value_modules:ValueStagedBidAtCostPSM"}):
            _fail("Default storage-cost selection lacks frozen PSM evidence")
        normalized["storage_cost"] = actual["storage_cost"]
    psm_identity = graph_modules.get("psm", {})
    if (normalized["psm"] in {"value-bid-at-cost-psm", "value-staged-bid-at-cost-psm"}
            and psm_identity.get("entry_point") in {
                "gridform_core.builtin.value_modules:ValueBidAtCostPSM",
                "gridform_core.builtin.value_modules:ValueStagedBidAtCostPSM"}):
        normalized.setdefault("storage_cost", "dynamic-annual-storage-cost")
    if actual != normalized:
        _fail("Snapshot module scope differs from project selection/default evidence")
    extension = graph.get("extension_graph")
    if snapshot.get("extension_graph") != extension:
        _fail("Snapshot extension graph differs from module graph")
    declarations = _extensions(extension, project, set(actual.values()), available_roles)
    payload = dict(graph_modules)
    if extension is not None:
        payload["$extensions"] = extension
    if _sha(graph.get("graph_sha256"), "Module graph hash") != _hash(payload, ascii=True):
        _fail("Frozen module graph hash differs")
    return declarations


def verify_frozen_input_integrity(snapshot_root: Path) -> dict:
    """Verify saved v1 normalized inputs and recorded graphs, never current code."""
    root = Path(snapshot_root).absolute()
    try:
        # Reject a symlink in any supplied parent component as well as members.
        if any(path.is_symlink() for path in (root, *root.parents)):
            _fail("Snapshot path contains a symbolic link")
        snapshot = _json(root, "snapshot.json")
        if snapshot.get("schema_version") != "value.run-input-snapshot/v1" or snapshot.get("state") != "ready":
            _fail("Snapshot is not a ready v1 recorded input")
        project = _json(root, "project.json")
        _text(project.get("id"), "Frozen project ID")
        base = _json(root, "pack/manifest.json")
        if _sha(snapshot.get("project_sha256"), "Project hash") != _hash(project) or _sha(snapshot.get("pack_manifest_sha256"), "Pack hash") != _hash(base):
            _fail("Frozen project or BASE manifest hash differs")
        if project.get("data_pack_id") != base.get("id"):
            _fail("Project BASE identity differs")
        network = None
        if "network_pack_manifest_sha256" in snapshot or "network_pack_id" in snapshot:
            network = _json(root, "network-pack/manifest.json")
            configuration = _mapping(project.get("market_configuration"), "Market configuration")
            if (_sha(snapshot.get("network_pack_manifest_sha256"), "Network manifest hash") != _hash(network)
                    or snapshot.get("network_pack_id") != network.get("id")
                    or configuration.get("network_pack_id") != network.get("id")
                    or network.get("data_pack_type") != "network_overlay"):
                _fail("Frozen network identity differs")
        elif (root / "network-pack").exists() or (isinstance(project.get("market_configuration"), dict) and project["market_configuration"].get("network_pack_id")):
            _fail("Unrecorded or missing network overlay")
        products = {"pack": ("base", base)}
        if network is not None:
            products["network-pack"] = ("network_overlay", network)
        expected = {}
        for directory, (kind, manifest) in products.items():
            if manifest.get("schema_version") != "value.data-pack/v1" or manifest.get("snapshot_frozen") is not True:
                _fail("Frozen data manifest is not a v1 frozen pack")
            _text(manifest.get("id"), "Data-pack ID")
            for role, binding in _mapping(manifest.get("bindings"), "Pack bindings").items():
                _text(role, "Binding role")
                binding = _mapping(binding, "Frozen binding")
                if binding.get("role", role) != role:
                    _fail("Frozen binding role differs")
                uri = _uri(binding.get("uri"))
                if not uri.startswith("files/"):
                    _fail("Frozen binding must identify a data file")
                expected[(directory, role)] = (kind, binding)
        observed = set()
        canonical = []
        for row in _array(snapshot.get("objects"), "Snapshot objects"):
            row = _mapping(row, "Snapshot object")
            # The existing v1 verifier explicitly treats absent pack_directory
            # as pack. It cannot infer a separate overlay from an omitted field.
            directory = row.get("pack_directory", "pack")
            if directory not in products:
                _fail("Unsafe or unrecorded snapshot pack directory")
            role = _text(row.get("role"), "Object role")
            key = (directory, role)
            if key in observed or key not in expected:
                _fail("Repeated or unbound snapshot object")
            observed.add(key)
            kind, binding = expected[key]
            if row.get("pack_kind", "base") != kind:
                _fail("Snapshot object pack kind differs")
            digest = _sha(row.get("sha256"), "Object hash")
            source = _sha(row.get("source_sha256"), "Object source hash")
            if (digest != _sha(binding.get("sha256"), "Binding hash")
                    or digest != _sha(binding.get("normalized_sha256"), "Normalized binding hash")
                    or source != _sha(binding.get("source_sha256"), "Source binding hash")
                    or row.get("snapshot_uri") != binding.get("uri")):
                _fail("Snapshot object and binding identities differ")
            size = row.get("bytes")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0 or isinstance(binding.get("bytes"), bool) or not isinstance(binding.get("bytes"), int) or binding.get("bytes") != size:
                _fail("Snapshot byte counts differ or are invalid")
            transformation = _text(binding.get("transformation_id"), "Transformation identity")
            adapter = binding.get("adapter")
            if adapter is not None:
                adapter = _mapping(adapter, "Recorded adapter")
                if (adapter.get("canonical_role") != role or adapter.get("canonical_format") != binding.get("format")
                        or transformation != f"{adapter.get('adapter_id')}@{adapter.get('version')}"):
                    _fail("Recorded adapter transformation differs")
            elif transformation != "identity/v1" or digest != source:
                _fail("Identity transformation source differs")
            path = _file(root, f"{directory}/{binding['uri']}")
            actual_hash, actual_size = _file_digest(path)
            if actual_hash != digest or actual_size != size:
                _fail("Frozen data bytes differ from recorded identity")
            canonical.append({"pack_directory": directory, "pack_kind": kind, "role": role,
                "uri": binding["uri"], "format": _text(binding.get("format"), "Binding format"),
                "unit": binding.get("unit"), "sha256": digest, "source_sha256": source,
                "normalized_sha256": digest, "bytes": size, "transformation_id": transformation})
        if observed != set(expected):
            _fail("Snapshot object coverage is incomplete")
        declarations = _modules(snapshot, project, {role for _, role in expected})
        identity = {key: snapshot[key] for key in IDENTITY_FIELDS}
        for key in ("network_pack_id", "network_pack_manifest_sha256", "extension_graph"):
            if key in snapshot:
                identity[key] = snapshot[key]
        base_hash = _hash(identity)
        tree_hash = base_hash
        snapshot_id = base_hash
        resource = None
        if "resource_readiness_sha256" in snapshot or "resource_readiness_path" in snapshot:
            if snapshot.get("resource_readiness_path") != "resource-readiness.json":
                _fail("Unsafe resource readiness path")
            resource = _json(root, "resource-readiness.json")
            if resource.get("schema_version") != "value.resource-readiness-snapshot/v1":
                _fail("Unsupported frozen resource readiness")
            required = {"trace_profile", "run_context_sha256", "year_context_sha256", "calibration_key",
                        "calibration_basis", "free_space_observation", "quota_decision", "selected_output_root"}
            if not required.issubset(resource) or resource["trace_profile"] not in {"off", "summary", "full"}:
                _fail("Frozen resource readiness coverage is incomplete")
            _sha(resource["run_context_sha256"], "Resource run context hash")
            _sha(resource["year_context_sha256"], "Resource year context hash")
            digest = _hash(resource)
            if _sha(snapshot.get("resource_readiness_sha256"), "Resource readiness hash") != digest:
                _fail("Frozen resource readiness hash differs")
            resource_identity = {"base_input_tree_sha256": base_hash, "resource_readiness_sha256": digest}
            tree_hash = _hash(resource_identity)
            snapshot_id = _hash({"base_snapshot_id": base_hash, **resource_identity})
        elif (root / "resource-readiness.json").exists():
            _fail("Unrecorded resource readiness evidence")
        if _sha(snapshot.get("input_tree_sha256"), "Input tree hash") != tree_hash or _sha(snapshot.get("snapshot_id"), "Snapshot ID") != snapshot_id:
            _fail("Overall snapshot identity differs")
        return {"schema_version": "value.frozen-input-integrity/v1", "snapshot": snapshot, "project": project,
                "base_manifest": base, "network_manifest": network, "resource_readiness": resource,
                "declaration_evidence": declarations,
                "canonical_roles": sorted(canonical, key=lambda row: (row["pack_directory"], row["role"])),
                "base_input_tree_sha256": base_hash, "input_tree_sha256": tree_hash, "snapshot_id": snapshot_id,
                "limitations": ["Recorded metadata and normalized data bytes only; historical source and runtime are not restored."]
                    + (["Legacy extension projection cannot self-verify complete declarations or hidden scope; only explicit current-method migration may be considered."] if not declarations["complete"] else [])}
    except FrozenInputIntegrityError:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise FrozenInputIntegrityError(f"Frozen input evidence is missing or malformed: {exc}") from exc
