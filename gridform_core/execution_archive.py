"""Stdlib-only, content-addressed execution source and runtime archives.

This records bytes, not scientific acceptance or cross-OS portability. Archives
contain no input datasets or arbitrary environment variables. Runtime symbolic
links are materialized as their verified target bytes; source links are refused.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import sysconfig
import tempfile
import time
import zipfile

SCHEMA = 'value.execution-bundle/v1'
MAX_FILES = 100_000
MAX_BYTES = 4 * 1024 ** 3
MAX_LDD_FILES = 2048
LDD_BUDGET_SECONDS = 120
SKIP_DIRS = {'__pycache__', '.git', '.cache', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
SKIP_SUFFIXES = {'.pyc', '.pyo', '.log'}
LOADER_ENV = ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT', 'LD_BIND_NOW', 'LD_HWCAP_MASK',
              'LD_ORIGIN_PATH', 'LD_ASSUME_KERNEL', 'LD_PREFER_MAP_32BIT_EXEC', 'GLIBC_TUNABLES',
              'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES',
              'DYLD_FRAMEWORK_PATH', 'DYLD_FALLBACK_FRAMEWORK_PATH', 'DYLD_FORCE_FLAT_NAMESPACE')
PYTHON_SEMANTIC_ENV = ('PYTHONOPTIMIZE', 'PYTHONHASHSEED', 'PYTHONUTF8', 'PYTHONCOERCECLOCALE',
                       'PYTHONINTMAXSTRDIGITS', 'PYTHONWARNINGS')
SEMANTIC_FLAGS = ('optimize', 'hash_randomization', 'utf8_mode', 'safe_path', 'isolated',
                  'ignore_environment', 'no_user_site', 'bytes_warning')

THREAD_ENV = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'BLIS_NUM_THREADS',
              'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'OMP_DYNAMIC', 'MKL_DYNAMIC', 'PYTHONHASHSEED')


class ExecutionArchiveError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()


def _safe_key(key):
    if not isinstance(key, str) or '\\' in key or '\x00' in key or ':' in key:
        raise ExecutionArchiveError('Unsafe archive member path')
    path = PurePosixPath(key)
    if path.is_absolute() or not path.parts or any(part in {'.', '..'} for part in path.parts) or path.as_posix() != key:
        raise ExecutionArchiveError('Unsafe archive member path')
    return key


def _no_links(path):
    path = path.absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ExecutionArchiveError('Source/managed path contains a symbolic link: ' + str(path))
    return path.resolve(strict=True)


def _scan_roots(roots, *, allow_runtime_links=False):
    """Return stable inventory and verified file sources; fixture tests use this helper."""
    rows, sources, root_records = [], {}, []
    total = 0
    for logical, supplied in roots:
        _safe_key(logical)
        original = Path(supplied).absolute()
        root = original.resolve(strict=True) if allow_runtime_links else _no_links(original)
        if root == Path('/') or root in {Path('/usr'), Path('/usr/local'), Path('/home'), Path('/opt')}:
            raise ExecutionArchiveError('Refusing a broad runtime/source root: ' + str(root))
        root_records.append({'path': logical, 'origin': str(original), 'resolved_origin': str(root)})
        stack = [(root, logical, frozenset())]
        while stack:
            path, key, ancestors = stack.pop()
            if path.is_symlink():
                if not allow_runtime_links: raise ExecutionArchiveError('Source symbolic links are refused: ' + str(path))
                path = path.resolve(strict=True)
            info = path.stat()
            if stat.S_ISDIR(info.st_mode):
                if path in ancestors: raise ExecutionArchiveError('Runtime directory link cycle: ' + str(path))
                descendants = ancestors | {path}
                for entry in sorted(path.iterdir(), reverse=True):
                    if entry.name not in SKIP_DIRS and entry.suffix.lower() not in SKIP_SUFFIXES:
                        stack.append((entry, key + '/' + entry.name, descendants))
                continue
            if not stat.S_ISREG(info.st_mode): raise ExecutionArchiveError('Nonregular execution file: ' + str(path))
            total += info.st_size
            if len(rows) >= MAX_FILES or total > MAX_BYTES: raise ExecutionArchiveError('Execution inventory exceeds the bounded file/byte limit')
            _safe_key(key)
            if key in sources: raise ExecutionArchiveError('Duplicate execution logical path')
            before = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            digest = _hash_file(path); after = path.stat()
            if before != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns): raise ExecutionArchiveError('Execution file changed while hashing')
            rows.append({'path': key, 'bytes': info.st_size, 'sha256': digest, 'mode': stat.S_IMODE(info.st_mode) & 0o777,
                         'origin': str(path)})
            sources[key] = path
    rows.sort(key=lambda row: row['path'])
    return rows, sources, root_records


def _tree_hash(rows):
    return hashlib.sha256(_canonical([{key: row[key] for key in ('path', 'bytes', 'sha256', 'mode')} for row in rows])).hexdigest()


def _source_roots(source_root, data_home):
    source = _no_links(Path(source_root))
    roots = [('app/' + name, source / name) for name in ('backend', 'gridform_core', 'requirements', 'pyproject.toml')]
    # Manifests are already within gridform_core; pyproject/requirements are
    # captured alongside all helpers and scientific resources, with no suffix gate.
    modules = Path(data_home).absolute() / 'modules'
    if modules.exists():
        _no_links(modules)
        for active_folder, label in ((modules, 'modules'), (modules / 'extensions', 'modules/extensions')):
            if active_folder.exists():
                _no_links(active_folder)
                for manifest in sorted(active_folder.glob('*.json')): roots.append((label + '/' + manifest.name, _no_links(manifest)))
        for category, manifest_name in (('installed', 'value-module.json'), ('installed-extensions', 'force-extension.json')):
            folder = modules / category
            if not folder.exists(): continue
            _no_links(folder)
            for identifier in sorted(folder.iterdir()):
                if not identifier.is_dir() or identifier.is_symlink(): raise ExecutionArchiveError('Unsafe installer-owned module directory')
                for version in sorted(identifier.iterdir()):
                    if not version.is_dir() or version.is_symlink(): raise ExecutionArchiveError('Unsafe installer-owned version directory')
                    record_path = _no_links(version / 'installation.json')
                    record = json.loads(record_path.read_text(encoding='utf-8'))
                    if not isinstance(record, dict): raise ExecutionArchiveError('Invalid installation record')
                    if not record.get('enabled'): continue
                    label = 'modules/' + category + '/' + identifier.name + '/' + version.name
                    roots.extend([(label + '/installation.json', record_path), (label + '/' + manifest_name, version / manifest_name)])
                    source_kind = record.get('source_root')
                    if source_kind == 'src': roots.append((label + '/src', version / 'src'))
                    elif source_kind is not None: raise ExecutionArchiveError('Enabled external module declares an unsupported source root')
                    elif category == 'installed': raise ExecutionArchiveError('Enabled module has no installer-owned source')
    return roots


def _environment_roots():
    prefix, base = Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()
    if prefix == Path('/') or base == Path('/'): raise ExecutionArchiveError('Refusing runtime prefix /')
    roots = []
    for logical, path in (('runtime', prefix), ('base-runtime', base)):
        if path in {Path('/usr'), Path('/usr/local')}:
            continue  # Actual stdlib/site-package paths below are the boundary.
        if not any(path == existing for _, existing in roots): roots.append((logical, path))
    for key in ('stdlib', 'platstdlib', 'purelib', 'platlib'):
        value = sysconfig.get_path(key)
        if value:
            path = Path(value).resolve()
            if path.exists() and not any(path.is_relative_to(existing) for _, existing in roots):
                roots.append((key, path))
    executable = Path(sys.executable).resolve(strict=True)
    if not any(executable.is_relative_to(existing) for _, existing in roots): roots.append(('interpreter/' + executable.name, executable))
    return roots


def _metadata():
    return {'sys_version': sys.version, 'python_executable': str(Path(sys.executable).resolve()),
            'sys_prefix': sys.prefix, 'sys_base_prefix': sys.base_prefix, 'platform': platform.system(),
            'platform_release': platform.release(), 'machine': platform.machine(),
            'implementation': sys.implementation.name, 'cache_tag': sys.implementation.cache_tag,
            'soabi': sysconfig.get_config_var('SOABI'),
            'loader_environment': {key: os.environ.get(key) for key in LOADER_ENV},
            'python_semantic_environment': {key: os.environ.get(key) for key in PYTHON_SEMANTIC_ENV},
            'python_semantic_flags': {key: getattr(sys.flags, key, None) for key in SEMANTIC_FLAGS},
            'thread_environment': {key: os.environ.get(key) for key in THREAD_ENV}}


def _semantic_metadata(metadata):
    return {key: value for key, value in metadata.items() if key not in {'python_executable', 'sys_prefix', 'sys_base_prefix'}}


def _elf_soname(path):
    """Read bounded ELF dynamic metadata without loading or executing the binary."""
    try:
        with path.open('rb') as stream:
            header = stream.read(64)
            if header[:4] != b'\x7fELF' or len(header) < 64: return None
            endian = '<' if header[5] == 1 else '>' if header[5] == 2 else None
            if endian is None: return None
            wide = header[4] == 2
            if header[4] not in (1, 2): return None
            phoff = struct.unpack_from(endian + ('Q' if wide else 'I'), header, 32 if wide else 28)[0]
            phsize, phcount = struct.unpack_from(endian + 'HH', header, 54 if wide else 42)
            if phcount > 1024 or phsize > 256 or phsize < (56 if wide else 32): return None
            loads, dynamic = [], None
            for index in range(phcount):
                stream.seek(phoff + index * phsize); raw = stream.read(phsize)
                kind = struct.unpack_from(endian + 'I', raw, 0)[0]
                offset = struct.unpack_from(endian + ('Q' if wide else 'I'), raw, 8 if wide else 4)[0]
                address = struct.unpack_from(endian + ('Q' if wide else 'I'), raw, 16 if wide else 8)[0]
                size = struct.unpack_from(endian + ('Q' if wide else 'I'), raw, 32 if wide else 16)[0]
                if kind == 1: loads.append((offset, address, size))
                if kind == 2: dynamic = (offset, size)
            if dynamic is None or dynamic[1] > 1024 * 1024: return None
            stream.seek(dynamic[0]); raw = stream.read(dynamic[1]); width = 16 if wide else 8
            string_address, name_offset = None, None
            for index in range(0, len(raw) - width + 1, width):
                tag, value = struct.unpack_from(endian + ('qQ' if wide else 'iI'), raw, index)
                if tag == 0: break
                if tag == 5: string_address = value
                if tag == 14: name_offset = value
            if string_address is None or name_offset is None: return None
            for offset, address, size in loads:
                if address <= string_address < address + size:
                    stream.seek(offset + string_address - address + name_offset)
                    value = stream.read(4096).split(b'\0', 1)[0].decode('utf-8')
                    return value if value and '/' not in value else None
    except (OSError, ValueError, UnicodeError, struct.error): return None
    return None


def _ldd_closure(sources):
    """Distinguish missing host libraries from verified runtime-contained bytes."""
    evidence = {'unresolved': [], 'runtime_matches': [], 'discovery_errors': []}
    limitations, libraries = [], {}
    if platform.system() != 'Linux':
        evidence['discovery_errors'].append({'binary': 'environment', 'reason': 'unsupported_platform'})
        return [], ['Shared-library closure is implemented only for Linux; cross-OS restoration is unverified.'], evidence
    tool = shutil.which('ldd')
    if not tool:
        evidence['discovery_errors'].append({'binary': 'environment', 'reason': 'ldd_unavailable'})
        return [], ['ldd is unavailable; Linux shared-library closure is incomplete.'], evidence
    names, labels, queue, visited = {}, {}, [], set()
    for logical, path in sorted(sources.items()):
        labels.setdefault(path, logical)
        if '.so' in path.name or path == Path(sys.executable).resolve():
            with path.open('rb') as stream: is_elf = stream.read(4) == b'\x7fELF'
            if is_elf:
                names.setdefault(Path(logical).name, set()).add(logical)
                names.setdefault(path.name, set()).add(logical)
                soname = _elf_soname(path)
                if soname: names.setdefault(soname, set()).add(logical)
                queue.append(path)
    loader_environment = {key: os.environ[key] for key in LOADER_ENV if key in os.environ}
    ldd_environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', **loader_environment}
    # Explicit injected libraries may not appear in ldd's ordinary DT_NEEDED
    # output (notably LD_AUDIT). Capture their actual bytes, or fail identity.
    for variable in ('LD_PRELOAD', 'LD_AUDIT'):
        for value in re.split(r'[:\s]+', loader_environment.get(variable, '')):
            if not value: continue
            candidate = Path(value)
            if candidate.is_absolute() and candidate.is_file():
                candidate = candidate.resolve()
                with candidate.open('rb') as stream: is_elf = stream.read(4) == b'\x7fELF'
                if is_elf:
                    libraries[candidate] = True; queue.append(candidate); continue
            # An unqualified loader name cannot safely be identified by guessing
            # search order. A real ldd-resolved path below is checked afterward.
            evidence['discovery_errors'].append({'binary': 'loader/' + variable,
                'reason': 'injected_library_identity_unresolved', 'library': value})
            limitations.append('Injected native library identity is unresolved: ' + variable + '=' + value)
    deadline = time.monotonic() + LDD_BUDGET_SECONDS
    while queue:
        path = queue.pop()
        if path in visited: continue
        if len(visited) >= MAX_LDD_FILES or time.monotonic() >= deadline:
            evidence['discovery_errors'].append({'binary': 'environment', 'reason': 'file_or_time_budget_exceeded'})
            limitations.append('Linux ldd closure exceeded the bounded file/time budget.'); break
        visited.add(path); binary = labels.get(path) or ('system-libraries/' + _hash_file(path) + '/' + path.name)
        try:
            checked = subprocess.run([tool, str(path)], capture_output=True, text=True, timeout=min(5, max(.1, deadline - time.monotonic())), env=ldd_environment)
        except (OSError, subprocess.SubprocessError):
            evidence['discovery_errors'].append({'binary': binary, 'reason': 'ldd_failed_or_timed_out'})
            limitations.append('ldd could not inspect ' + binary); continue
        output = checked.stdout + checked.stderr
        if len(output) > 65536:
            evidence['discovery_errors'].append({'binary': binary, 'reason': 'ldd_output_truncated'})
            limitations.append('Oversized ldd response for ' + binary); continue
        if 'cannot be preloaded' in output or 'cannot be loaded as audit interface' in output:
            evidence['discovery_errors'].append({'binary': binary, 'reason': 'loader_injection_rejected'})
            limitations.append('The dynamic loader rejected an injected library for ' + binary)
        missing = re.findall(r'^\s*(\S+)\s+=>\s+not found\s*$', output, re.MULTILINE)
        unresolved = []
        for needed in sorted(set(missing)):
            matches = sorted(names.get(needed, set()))
            if matches:
                evidence['runtime_matches'].append({'binary': binary, 'needed': needed, 'matched_files': matches})
                queue.extend(sources[key] for key in matches)
            else: unresolved.append(needed)
        if unresolved:
            evidence['unresolved'].append({'binary': binary, 'needed': unresolved, 'reason': 'not_found_on_host_or_in_archived_runtime'})
            limitations.append('Original runtime lacks native dependencies for ' + binary + ': ' + ', '.join(unresolved))
        if checked.returncode and 'statically linked' not in output:
            evidence['discovery_errors'].append({'binary': binary, 'reason': 'ldd_nonzero_exit'})
            limitations.append('Incomplete ldd response for ' + binary)
        for line in output.splitlines():
            match = re.search(r'(?:=>\s*)?(/[^\s]+)\s*\(', line)
            if not match: continue
            candidate = Path(match.group(1)).resolve()
            if not candidate.is_file():
                evidence['discovery_errors'].append({'binary': binary, 'reason': 'resolved_library_disappeared'})
                limitations.append('A discovered native library disappeared for ' + binary); continue
            if candidate not in visited: queue.append(candidate)
            libraries[candidate] = True
    unique = {}
    for path in sorted(libraries): unique.setdefault('system-libraries/' + _hash_file(path) + '/' + path.name, path)
    for key in evidence: evidence[key].sort(key=lambda row: json.dumps(row, sort_keys=True))
    return list(unique.items()), sorted(set(limitations)), evidence


def _write_artifact(rows, sources, archive_root):
    root = Path(archive_root).absolute()
    if any(item.is_symlink() for item in (root, *root.parents)): raise ExecutionArchiveError('CAS path contains a symbolic link')
    root.mkdir(mode=0o700, parents=True, exist_ok=True); _no_links(root)
    objects = root / 'objects'; objects.mkdir(mode=0o700, exist_ok=True); _no_links(objects)
    indexes = root / 'inventory-index'; indexes.mkdir(mode=0o700, exist_ok=True); _no_links(indexes)
    index = indexes / (_tree_hash(rows) + '.json')
    if index.exists():
        _no_links(index)
        artifact = json.loads(index.read_text(encoding='utf-8'))
        path = _artifact_path({'artifact': artifact}, root)
        with _verified_members({'files': rows}, path): pass
        return artifact

    descriptor, temporary_name = tempfile.mkstemp(prefix='.execution-', suffix='.zip', dir=objects)
    os.close(descriptor); temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for row in rows:
                path = sources[row['path']]
                if path.stat().st_size != row['bytes'] or _hash_file(path) != row['sha256']: raise ExecutionArchiveError('Source changed before archive capture')
                entry = zipfile.ZipInfo(row['path'], date_time=(1980, 1, 1, 0, 0, 0)); entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = (stat.S_IFREG | row['mode']) << 16
                digest = hashlib.sha256(); count = 0
                with path.open('rb') as source, archive.open(entry, 'w', force_zip64=True) as destination:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        count += len(block); digest.update(block); destination.write(block)
                if count != row['bytes'] or digest.hexdigest() != row['sha256'] or _hash_file(path) != row['sha256']:
                    raise ExecutionArchiveError('Source changed during archive capture')
        digest = _hash_file(temporary); destination = objects / (digest + '.zip')
        if destination.exists():
            _no_links(destination)
            if _hash_file(destination) != digest: raise ExecutionArchiveError('Existing CAS object is corrupt')
        else:
            # Hard-link publishes a completed immutable object without replacing
            # another capturer's object. Same-directory staging keeps it atomic.
            try: os.link(temporary, destination)
            except FileExistsError:
                if _hash_file(destination) != digest: raise ExecutionArchiveError('Concurrent CAS object is corrupt')
        artifact = {'path': 'objects/' + digest + '.zip', 'sha256': digest, 'bytes': destination.stat().st_size}
        # The inventory index only avoids recompression; every reuse verifies
        # its CAS bytes and exact member inventory before trusting it.
        descriptor, index_name = tempfile.mkstemp(prefix='.inventory-', dir=indexes)
        with os.fdopen(descriptor, 'wb') as stream: stream.write(_canonical(artifact))
        pending_index = Path(index_name)
        try: pending_index.replace(index)
        finally: pending_index.unlink(missing_ok=True)
        return artifact
    finally: temporary.unlink(missing_ok=True)


def _capture_bundle(*, source_roots, environment_roots, metadata, archive_root, archive, shared_libraries=True):
    """Internal injectable fixture boundary; never substitute a fake runtime in production."""
    source_rows, source_files, source_records = _scan_roots(source_roots)
    env_rows, env_files, env_records = _scan_roots(environment_roots, allow_runtime_links=True)
    limitations = []
    metadata = dict(metadata)
    native_evidence = {'unresolved': [], 'runtime_matches': [], 'discovery_errors': []}
    if shared_libraries:
        extra_roots, limitations, native_evidence = _ldd_closure(env_files)
        extra_rows, extra_files, extra_records = _scan_roots(extra_roots, allow_runtime_links=True)
        env_rows = sorted(env_rows + extra_rows, key=lambda row: row['path']); env_files.update(extra_files); env_records.extend(extra_records)
    metadata['native_dependency_evidence'] = native_evidence
    identity_complete = not metadata.get('unarchived_import_paths') and not native_evidence['discovery_errors']
    native_complete = not native_evidence['unresolved'] and not native_evidence['discovery_errors']
    if metadata.get('unarchived_import_paths'): limitations.append('Existing import roots are outside the managed source/runtime inventory.')
    source_sha = _tree_hash(source_rows)
    environment_sha = hashlib.sha256(_canonical({'files_sha256': _tree_hash(env_rows), 'metadata': _semantic_metadata(metadata)})).hexdigest()
    identity_sha = hashlib.sha256(_canonical({'source_sha256': source_sha, 'environment_sha256': environment_sha})).hexdigest()
    record = {'schema_version': SCHEMA, 'source_sha256': source_sha, 'environment_sha256': environment_sha,
              'identity_sha256': identity_sha, 'identity_complete': identity_complete, 'native_closure_complete': native_complete, 'archive_requested': bool(archive), 'archive_complete': False,
              'limitations': limitations,
              'source': {'sha256': source_sha, 'files': source_rows, 'roots': source_records, 'artifact': None},
              'environment': {'sha256': environment_sha, 'files': env_rows, 'roots': env_records, 'metadata': metadata, 'artifact': None}}
    if archive: record['archive_complete'] = bool(identity_complete and native_complete)
    _validate_record(record)
    if archive:
        record['source']['artifact'] = _write_artifact(source_rows, source_files, archive_root)
        record['environment']['artifact'] = _write_artifact(env_rows, env_files, archive_root)
        record['archive_complete'] = bool(identity_complete and native_complete)
        verify_execution_bundle(record, archive_root=archive_root)
    return record


def capture_execution_bundle(*, source_root: Path, data_home: Path, archive_root: Path, archive: bool = False) -> dict:
    source_roots = _source_roots(source_root, data_home)
    # Admission and worker verification must use the same real import order.
    # Validate installer-owned roots above before activating them; never omit
    # unrelated paths from the semantic identity or unarchived-path checks.
    from gridform_core.runtime_paths import activate_external_module_sources
    activate_external_module_sources(Path(data_home) / 'modules')
    environment_roots = _environment_roots()
    covered_roots = [Path(path).resolve() for _, path in source_roots + environment_roots]
    # The controlled workspace import root is the parent of archived backend
    # and core packages; it is not itself a request to archive user state.
    workspace_import_root = Path(source_root).resolve()
    import_paths, uncovered = [], []
    for raw in sys.path:
        path = Path(raw or os.getcwd()).resolve()
        if path == workspace_import_root:
            import_paths.append({'path': 'workspace', 'exists': path.exists()}); continue
        matched = next(((logical, Path(root).resolve()) for logical, root in source_roots + environment_roots
                        if path == Path(root).resolve() or path.is_relative_to(Path(root).resolve())), None)
        if matched:
            logical, root = matched
            label = logical if path == root else logical + '/' + path.relative_to(root).as_posix()
            import_paths.append({'path': label, 'exists': path.exists()})
        else:
            import_paths.append({'path': str(path), 'exists': path.exists(), 'managed': False})
            if path.exists(): uncovered.append(str(path))
    metadata = _metadata(); metadata['import_paths'] = import_paths
    metadata['unarchived_import_paths'] = sorted(set(uncovered))
    return _capture_bundle(source_roots=source_roots, environment_roots=environment_roots, metadata=metadata,
                           archive_root=archive_root, archive=archive)


def _validate_record(record):
    if not isinstance(record, dict) or record.get('schema_version') != SCHEMA: raise ExecutionArchiveError('Unsupported execution bundle record')
    if record.get('archive_complete') and (not record.get('archive_requested') or record.get('limitations')):
        raise ExecutionArchiveError('Execution archive completeness contradicts its limitations')
    for kind in ('source', 'environment'):
        block = record.get(kind)
        if not isinstance(block, dict) or not isinstance(block.get('files'), list): raise ExecutionArchiveError('Missing execution file inventory')
        if not isinstance(block.get('roots'), list): raise ExecutionArchiveError('Missing execution root mapping')
        for root_row in block['roots']: _safe_key(root_row['path'])
        seen, total = set(), 0
        if len(block['files']) > MAX_FILES: raise ExecutionArchiveError('Oversized execution inventory')
        for row in block['files']:
            key = _safe_key(row['path'])
            if key in seen or not re.fullmatch('[0-9a-f]{64}', str(row['sha256'])): raise ExecutionArchiveError('Invalid/duplicate execution file identity')
            seen.add(key)
            if isinstance(row['bytes'], bool) or not isinstance(row['bytes'], int) or row['bytes'] < 0 or not isinstance(row['mode'], int) or row['mode'] < 0 or row['mode'] > 0o777: raise ExecutionArchiveError('Invalid execution size/mode')
            total += row['bytes']
        if total > MAX_BYTES: raise ExecutionArchiveError('Oversized execution inventory bytes')
    metadata = record['environment']['metadata']
    native = metadata.get('native_dependency_evidence')
    if not isinstance(native, dict) or any(not isinstance(native.get(key), list) for key in ('unresolved', 'runtime_matches', 'discovery_errors')):
        raise ExecutionArchiveError('Native dependency evidence is missing')
    identity_complete = not metadata.get('unarchived_import_paths') and not native['discovery_errors']
    native_complete = not native['unresolved'] and not native['discovery_errors']
    if record.get('identity_complete') != identity_complete or record.get('native_closure_complete') != native_complete:
        raise ExecutionArchiveError('Execution completeness flags do not match recorded evidence')
    if record.get('archive_complete') != bool(record.get('archive_requested') and identity_complete and native_complete):
        raise ExecutionArchiveError('Archive completeness does not match recorded evidence')
    source_sha = _tree_hash(record['source']['files'])
    environment_sha = hashlib.sha256(_canonical({'files_sha256': _tree_hash(record['environment']['files']), 'metadata': _semantic_metadata(record['environment']['metadata'])})).hexdigest()
    identity_sha = hashlib.sha256(_canonical({'source_sha256': source_sha, 'environment_sha256': environment_sha})).hexdigest()
    if (source_sha != record['source_sha256'] or source_sha != record['source']['sha256'] or
        environment_sha != record['environment_sha256'] or environment_sha != record['environment']['sha256'] or identity_sha != record['identity_sha256']):
        raise ExecutionArchiveError('Execution identity does not match its inventories')


def _artifact_path(block, archive_root):
    artifact = block.get('artifact')
    if not isinstance(artifact, dict) or not re.fullmatch('[0-9a-f]{64}', str(artifact.get('sha256'))): raise ExecutionArchiveError('Execution bytes have not been archived')
    if artifact.get('path') != 'objects/' + artifact['sha256'] + '.zip': raise ExecutionArchiveError('Unsafe CAS object path')
    root = _no_links(Path(archive_root)); path = _no_links(root / artifact['path'])
    if path.stat().st_size != artifact.get('bytes') or _hash_file(path) != artifact['sha256']: raise ExecutionArchiveError('CAS artifact bytes/hash mismatch')
    return path


def _verified_members(block, path):
    archive = zipfile.ZipFile(path)
    try:
        entries = archive.infolist(); expected = {row['path']: row for row in block['files']}
        if len(entries) != len(expected): raise ExecutionArchiveError('CAS archive inventory mismatch')
        observed = set()
        for entry in entries:
            key = _safe_key(entry.filename)
            if key in observed or key not in expected: raise ExecutionArchiveError('Unknown/duplicate CAS archive member')
            observed.add(key); row = expected[key]
            mode = entry.external_attr >> 16
            if entry.is_dir() or not stat.S_ISREG(mode) or stat.S_IMODE(mode) != row['mode'] or entry.file_size != row['bytes'] or entry.flag_bits & 1:
                raise ExecutionArchiveError('Invalid CAS archive member metadata')
            count, digest = 0, hashlib.sha256()
            with archive.open(entry) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    count += len(chunk)
                    if count > row['bytes']: raise ExecutionArchiveError('Oversized CAS member')
                    digest.update(chunk)
            if count != row['bytes'] or digest.hexdigest() != row['sha256']: raise ExecutionArchiveError('CAS member hash mismatch')
        return archive
    except Exception:
        archive.close(); raise


def verify_execution_bundle(record: dict, *, archive_root: Path) -> None:
    _validate_record(record)
    for kind in ('source', 'environment'):
        path = _artifact_path(record[kind], archive_root)
        with _verified_members(record[kind], path): pass


def materialize_execution_bundle(record: dict, *, archive_root: Path, destination: Path) -> dict:
    verify_execution_bundle(record, archive_root=archive_root)
    destination = Path(destination).absolute()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())): raise ExecutionArchiveError('Restore destination must be new or empty')
    destination.parent.mkdir(parents=True, exist_ok=True); _no_links(destination.parent)
    if destination.is_symlink(): raise ExecutionArchiveError('Restore destination cannot be a symbolic link')
    staging = Path(tempfile.mkdtemp(prefix='.execution-restore-', dir=destination.parent))
    try:
        for kind in ('source', 'environment'):
            path = _artifact_path(record[kind], archive_root)
            with _verified_members(record[kind], path) as archive:
                for row in record[kind]['files']:
                    target = staging / kind / _safe_key(row['path']); target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(row['path']) as source, target.open('xb') as output: shutil.copyfileobj(source, output, 1024 * 1024)
                    target.chmod(row['mode'])
                    if _hash_file(target) != row['sha256']: raise ExecutionArchiveError('Restored execution file differs')
        if destination.exists() and any(destination.iterdir()): raise ExecutionArchiveError('Restore destination changed during extraction')
        staging.replace(destination)
        return {'schema_version': 'value.execution-materialization/v1', 'identity_sha256': record['identity_sha256'],
                'source_root': str(destination / 'source/app'), 'environment_root': str(destination / 'environment'),
                'roots': {kind: [{'path': row['path'], 'materialized_path': str(destination / kind / _safe_key(row['path']))} for row in record[kind]['roots']] for kind in ('source', 'environment')},
                'identity_complete': record['identity_complete'], 'native_closure_complete': record['native_closure_complete'],
                'archive_complete': record['archive_complete'], 'limitations': record['limitations'], 'executed': False}
    finally:
        if staging.exists(): shutil.rmtree(staging)
