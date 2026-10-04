"""Independent, hash-pinned R0 source loader for bounded doctoral comparisons.

This is a test oracle, never a production engine. It compiles original AST nodes
unchanged into a fresh namespace. It does not import the original module, run its
main loop, or borrow implementations from the candidate. Only qualified exports
and their dependency closure can be loaded. This prevents accidental top-level
execution; it is not a general sandbox for arbitrary hostile Python.

The reference environment is explicit and frozen: half-hour accounting and no
market debug output by default. Source function bodies retain their getenv calls.
Caller-provided environment values are fixture inputs, not source rewrites.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Iterable, Mapping
import hashlib
import importlib
import json
from pathlib import Path, PurePosixPath
import symtable
from types import MappingProxyType, SimpleNamespace


SOURCE_MANIFEST_SCHEMA = "value.doctoral-reference-source-manifest/v1"
SOURCE_MANIFEST_PATH = Path(__file__).parent / "fixtures/doctoral_alignment/source_manifest.json"
DEFAULT_ENVIRONMENT = {"PHYSICAL_PERIOD_HOURS": "0.5", "SIM_DEBUG_MARKET": "0"}

QUALIFIED_EXPORTS = {
    "simulation_model.py": frozenset({
        "Generator", "Battery", "GasGenerator", "ExpensiverenewableGenerator",
        "BiomassGenerator", "NuclearGenerator", "WaterGenerator", "Connection",
        "Electrolyzer", "IterLimit", "IterLimit_new", "decay_func", "acm_income",
        "acm_income_balance", "store_service_three", "ahead_market_bidding",
        "curtailment_market_bidding", "balancing_market_bidding", "physical_period_hours",
    }),
    "run_investment_analysis.py": frozenset({
        "critical_capacity_for_threshold", "calculate_expansion_limit",
    }),
}

_SAFE_BUILTINS = {
    name: getattr(builtins, name) for name in (
        "__build_class__", "object", "super", "type", "len", "abs", "float", "int",
        "str", "bool", "list", "tuple", "dict", "set", "range", "enumerate", "sum",
        "min", "max", "any", "all", "next", "iter", "hasattr", "getattr", "isinstance",
        "print", "sorted", "zip", "round", "ValueError", "TypeError", "RuntimeError",
        "StopIteration", "KeyError", "IndexError", "Exception",
    )
}


def _read_validated_sources(manifest_path: Path | None, source_root: Path | None):
    path = Path(manifest_path) if manifest_path is not None else SOURCE_MANIFEST_PATH
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise ValueError("source identity: unrecognized manifest schema")
    root = Path(source_root or manifest["source_root"]).resolve()
    entries = manifest.get("sources")
    if not isinstance(entries, dict) or not entries:
        raise ValueError("source identity: manifest has no sources")
    contents = {}
    for relative, entry in entries.items():
        logical = PurePosixPath(relative)
        if logical.is_absolute() or ".." in logical.parts or "\\" in relative or ":" in relative:
            raise ValueError(f"source identity: invalid relative path {relative!r}")
        source = (root / relative).resolve()
        if root not in source.parents:
            raise ValueError(f"source identity: escaped source root {relative!r}")
        expected = entry.get("sha256") if isinstance(entry, dict) else None
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"source identity: missing SHA-256 for {relative}")
        try:
            contents[relative] = source.read_bytes()
        except OSError as error:
            raise ValueError(f"source identity: cannot read {relative}: {error}") from error
        actual = hashlib.sha256(contents[relative]).hexdigest()
        if actual != expected:
            raise ValueError(f"source identity changed: {relative}: expected {expected}, got {actual}")
    return manifest, root, contents


def validate_source_manifest(manifest_path: Path | None = None, *,
                             source_root: Path | None = None) -> dict:
    """Validate every pinned original file, including annual source not executed."""
    manifest, _, _ = _read_validated_sources(manifest_path, source_root)
    return manifest


def _safe_expression(node: ast.AST) -> bool:
    # Defaults, class bases/attributes and constants execute while defining a
    # symbol. Exclude calls except the explicit read-only original getenv use.
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_safe_expression(item) for item in node.elts)
    if isinstance(node, ast.Dict):
        return all(key is not None and _safe_expression(key) and _safe_expression(value)
                   for key, value in zip(node.keys, node.values))
    if isinstance(node, ast.UnaryOp):
        return _safe_expression(node.operand)
    if isinstance(node, ast.BinOp):
        return _safe_expression(node.left) and _safe_expression(node.right)
    if isinstance(node, ast.BoolOp):
        return all(_safe_expression(item) for item in node.values)
    if isinstance(node, ast.Compare):
        return _safe_expression(node.left) and all(_safe_expression(item) for item in node.comparators)
    if isinstance(node, ast.Call):
        return (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os" and node.func.attr == "getenv"
                and not node.keywords and all(isinstance(arg, ast.Constant) for arg in node.args))
    return False


def _check_definition_safety(node: ast.AST) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.decorator_list:
            raise ValueError(f"unsafe decorator on {node.name}")
        arguments = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        eager = node.args.defaults + [item for item in node.args.kw_defaults if item is not None]
        eager += [arg.annotation for arg in arguments if arg.annotation is not None]
        if node.returns is not None:
            eager.append(node.returns)
        if not all(_safe_expression(item) for item in eager):
            raise ValueError(f"unsafe definition-time expression in {node.name}")
        if any(isinstance(item, (ast.Import, ast.ImportFrom)) for item in ast.walk(node)):
            raise ValueError(f"unsafe runtime import in {node.name}")
    elif isinstance(node, ast.ClassDef):
        if node.decorator_list or node.keywords or not all(isinstance(base, ast.Name) for base in node.bases):
            raise ValueError(f"unsafe class definition {node.name}")
        for child in node.body:
            _check_definition_safety(child)
    elif isinstance(node, ast.Assign):
        if not all(isinstance(target, ast.Name) for target in node.targets) or not _safe_expression(node.value):
            raise ValueError("unsafe top-level/class assignment")
    elif isinstance(node, ast.AnnAssign):
        if (not isinstance(node.target, ast.Name) or not _safe_expression(node.annotation)
                or node.value is not None and not _safe_expression(node.value)):
            raise ValueError("unsafe annotated assignment")
    elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        pass  # Docstrings have no execution side effect.
    elif isinstance(node, ast.Pass):
        pass
    else:
        raise ValueError(f"unsafe definition node: {type(node).__name__}")


def _global_dependencies(node: ast.AST, filename: str) -> set[str]:
    table = symtable.symtable(ast.unparse(node), filename, "exec")

    def walk(scope):
        names = {symbol.get_name() for symbol in scope.get_symbols()
                 if symbol.is_global() and symbol.is_referenced()}
        for child in scope.get_children():
            names.update(walk(child))
        return names

    dependencies = walk(table)
    # An assigned global is only an output if every read is preceded by an
    # assignment on every reaching branch. In particular, never excuse a missing
    # opening state merely because the function writes it later.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        function_scope = table.get_children()[0]
        for symbol in function_scope.get_symbols():
            name = symbol.get_name()
            if symbol.is_global() and symbol.is_assigned() and name in dependencies:
                if _global_reads_are_initialized(node.body, name):
                    dependencies.remove(name)
    return dependencies


def _global_reads_are_initialized(statements: list[ast.stmt], name: str) -> bool:
    def contains_read(node):
        return any(isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load) and item.id == name
                   for item in ast.walk(node))

    def block(items, initialized):
        for item in items:
            if isinstance(item, ast.If):
                if not initialized and contains_read(item.test):
                    return False, initialized
                valid_left, after_left = block(item.body, initialized)
                valid_right, after_right = block(item.orelse, initialized)
                if not valid_left or not valid_right:
                    return False, initialized
                initialized = after_left and after_right
            elif isinstance(item, ast.Assign):
                if not initialized and contains_read(item.value):
                    return False, initialized
                for target in item.targets:
                    if not initialized and contains_read(target):
                        return False, initialized
                if any(isinstance(target, ast.Name) and target.id == name for target in item.targets):
                    initialized = True
            elif not initialized and contains_read(item):
                # Other control flow cannot establish guaranteed initialization
                # here. This deliberately fails closed for unqualified patterns.
                return False, initialized
        return True, initialized

    return block(statements, False)[0]


def _load_source(source: str, names: Iterable[str], *, filename: str,
                 environment: Mapping[str, str] | None = None) -> dict:
    """Compile a source dependency closure; private entry also supports safety fixtures."""
    tree = ast.parse(source, filename=filename)
    definitions: dict[str, list[ast.AST]] = {}
    imports = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definitions.setdefault(node.name, []).append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    definitions.setdefault(target.id, []).append(node)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
    environment_snapshot = dict(DEFAULT_ENVIRONMENT)
    environment_snapshot.update(environment or {})
    frozen_environment = MappingProxyType(environment_snapshot)
    namespace = {"__builtins__": dict(_SAFE_BUILTINS), "__name__": "doctoral_reference_r0",
                 "__file__": filename}
    selected = set()
    resolving = set()

    def resolve(name: str):
        if name in namespace or name in _SAFE_BUILTINS or name in resolving:
            return
        if name in imports:
            module = imports[name]
            if module == "os":
                namespace[name] = SimpleNamespace(getenv=frozen_environment.get)
            elif module == "gc":
                namespace[name] = SimpleNamespace(collect=importlib.import_module("gc").collect)
            elif module in {"numpy", "pandas", "math"}:
                namespace[name] = importlib.import_module(module)
            else:
                raise ValueError(f"unsafe import dependency: {module}")
            return
        candidates = definitions.get(name, [])
        if len(candidates) != 1:
            reason = "ambiguous" if candidates else "unresolved"
            raise ValueError(f"{reason} reference dependency: {name}")
        node = candidates[0]
        _check_definition_safety(node)
        resolving.add(name)
        for dependency in sorted(_global_dependencies(node, filename)):
            resolve(dependency)
        selected.add(node)

    for name in names:
        resolve(name)
    # Preserve exact original nodes, locations, and order. No ast rewriting.
    module = ast.Module(body=[node for node in tree.body if node in selected], type_ignores=[])
    try:
        exec(compile(module, filename, "exec", dont_inherit=True), namespace, namespace)
    except Exception as error:
        raise ValueError(f"reference definition dependency execution failed: {error}") from error
    namespace["__reference_environment__"] = frozen_environment
    namespace["__reference_symbols__"] = tuple(sorted(resolving))
    return namespace


def load_reference_symbols(names: Iterable[str] | None = None, *,
                           relative_path: str = "simulation_model.py",
                           manifest_path: Path | None = None, source_root: Path | None = None,
                           environment: Mapping[str, str] | None = None) -> dict:
    """Load qualified unchanged R0 symbols after validating all pinned sources.

    Optional alternate roots/manifests support relocated original sources and
    integrity-negative tests. They never permit importing candidate functions.
    The returned objects and mutable state are fresh for every invocation.
    """
    requested = set(QUALIFIED_EXPORTS.get(relative_path, ())) if names is None else set(names)
    allowed = QUALIFIED_EXPORTS.get(relative_path, frozenset())
    if not requested or not requested <= allowed:
        raise ValueError(f"reference symbols not qualified: {relative_path}: {sorted(requested - allowed)}")
    manifest, root, contents = _read_validated_sources(manifest_path, source_root)
    if relative_path not in contents:
        raise ValueError(f"source identity: {relative_path} absent from manifest")
    namespace = _load_source(contents[relative_path].decode("utf-8-sig"), sorted(requested),
                             filename=str(root / relative_path), environment=environment)
    namespace["__source_manifest__"] = manifest
    namespace["__source_sha256__"] = manifest["sources"][relative_path]["sha256"]
    return namespace
