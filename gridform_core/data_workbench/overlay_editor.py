"""Independent network-overlay editing with byte-bound review and atomic installation."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import threading
try:
    import fcntl
except ImportError:  # Windows retains the same cross-process mutation boundary.
    fcntl = None
    import msvcrt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import uuid

from gridform_core.dataset_slots import DATASET_SLOTS
from gridform_core.data_bundle import build_data_bundle, install_data_bundle
from gridform_core.data_pack_validation import validate_data_pack
from gridform_core.zonal_contracts import ZONAL_ROLES, ZonalNetworkPack, load_zonal_network_pack
from .contracts import PromotionRequest, SignedBundleReceipt
from .validation import candidate_identity

MAX_UPLOAD = 32 * 1024 * 1024
MAX_TREE = 256 * 1024 * 1024
ID = re.compile(r"^[a-z][a-z0-9_-]{1,119}$")


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON: ' + value)))


def write(path, value):
    temporary = path.with_name(path.name + '.pending')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def child(root, identifier):
    if not ID.fullmatch(identifier): raise ValueError('Use a lowercase versioned ID (2–120 letters, digits, underscores or hyphens).')
    target = root / identifier
    if target.is_symlink() or target.resolve().parent != root.resolve(): raise ValueError('Unsafe overlay directory')
    return target


def inventory(root):
    result, total = {}, 0
    for path in sorted(root.rglob('*')):
        if path.is_symlink(): raise ValueError('Overlay symlinks are not accepted')
        if path.is_file():
            total += path.stat().st_size
            if total > MAX_TREE: raise ValueError('Overlay exceeds 256 MiB editor limit')
            result[path.relative_to(root).as_posix()] = digest(path)
    return result


def bound(root, binding):
    uri = PurePosixPath(str(binding.get('uri') or ''))
    if uri.is_absolute() or not uri.parts or '..' in uri.parts: raise ValueError('Unsafe binding URI')
    path = root / str(uri)
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file(): raise ValueError('Bound file is unavailable')
    return path


def roles(manifest):
    bindings = manifest.get('bindings')
    if not isinstance(bindings, dict): return []
    return [{'role': role, 'format': binding.get('format'), 'filename': binding.get('filename'),
             'sha256': binding.get('sha256'), 'bytes': binding.get('bytes'), 'unit': binding.get('unit')}
            for role, binding in sorted(bindings.items()) if isinstance(binding, dict)]


def reconstruct(root, manifest):
    """Use the runtime contract's exact fields and canonical hash, without bypassing validation."""
    payload = dict(manifest['zonal_network_pack'])
    fields = ('zones', 'corridors', 'cutsets', 'asset_mappings', 'zonal_demand', 'rating_profiles', 'interconnector_landings', 'spatial_audit')
    for role, field in zip(ZONAL_ROLES, fields):
        document = read(bound(root, manifest['bindings'][role]))
        payload[field] = document if field == 'spatial_audit' else document[field]
    payload['spatial_audit'] = {**payload['spatial_audit'], 'source_sha256_by_role': {role: manifest['bindings'][role]['sha256'] for role in ZONAL_ROLES}}
    return ZonalNetworkPack.from_dict(payload)


class OverlayEditor:
    def __init__(self, state_root, dataset_slots=DATASET_SLOTS):
        self.state = Path(state_root).resolve(); self.slots = dataset_slots
        self.state.mkdir(parents=True, exist_ok=True)
        self.mutation_lock = threading.RLock()

    @contextmanager
    def locked(self):
        with self.mutation_lock, (self.state / 'overlay-editor.lock').open('a+b') as stream:
            if fcntl is not None:
                fcntl.flock(stream, fcntl.LOCK_EX)
            else:
                if stream.seek(0, 2) == 0: stream.write(b'0'); stream.flush()
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None: fcntl.flock(stream, fcntl.LOCK_UN)
                else:
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def overlays(self):
        rows = []
        installed = self.state / 'installed-packs'
        for path in sorted(installed.glob('*/manifest.json')) if installed.exists() else []:
            manifest = None
            try:
                manifest = read(path)
                if not manifest.get('zonal_network_pack'): continue
                root = child(installed, path.parent.name)
                inventory(root)
                network = load_zonal_network_pack(root, manifest)
                reason, status = None, 'available'
                years = sorted({int(period[:4]) for period in network.zonal_demand.period_ids if period[:4].isdigit()})
            except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
                if not isinstance(manifest, dict) or not manifest.get('zonal_network_pack'): continue
                reason, status, years = str(exc), 'invalid', []
            try: manifest_sha = digest(path)
            except OSError: continue
            rows.append({'pack_id': manifest.get('id'), 'name': manifest.get('name'), 'source_manifest_sha256': manifest_sha,
                         'scientific_sha256': (manifest['zonal_network_pack'].get('scientific_sha256') if isinstance(manifest.get('zonal_network_pack'), dict) else None),
                         'installation_origin': 'bundle' if (path.parent / 'installation.json').is_file() else 'local_copy',
                         'roles': roles(manifest), 'years': years, 'status': status, 'reason': reason})
        return {'schema_version': 'value.network-overlays/v1', 'overlays': rows}

    def _root(self, directory_id):
        root = child(self.state / 'candidates', directory_id)
        if not (root / 'workbench-candidate.json').is_file(): raise KeyError('Unknown overlay candidate')
        if read(root / 'workbench-candidate.json').get('editor_kind') != 'network_overlay': raise ValueError('Candidate is not a network overlay')
        return root

    def _check(self, root, expected=None):
        payload = read(root / 'workbench-candidate.json')
        if payload.get('candidate_id') != candidate_identity(payload) or payload.get('artifact_hashes') != {'pack/' + key: value for key, value in inventory(root / 'pack').items()}:
            raise ValueError('Candidate bytes changed outside the editor; clone a new candidate')
        if expected is not None and expected != payload['candidate_id']: raise ValueError('Stale candidate identity; reload before editing or approving')
        return payload

    def _source(self, payload):
        source = child(self.state / 'installed-packs', payload['parent_pack_id'])
        if inventory(source) != payload['source_inventory']: raise ValueError('Source overlay changed since cloning')
        return source

    def _pin(self, root, payload):
        payload['artifact_hashes'] = {'pack/' + key: value for key, value in inventory(root / 'pack').items()}
        payload['candidate_id'] = candidate_identity(payload)
        write(root / 'workbench-candidate.json', payload)
        shutil.rmtree(root / 'review', ignore_errors=True)

    def detail(self, directory_id):
        with self.locked(): return self._detail(self._root(directory_id))

    def _detail(self, root):
        payload = self._check(root); manifest = read(root / 'pack/manifest.json')
        report_path = root / 'review/overlay-validation.json'
        report = read(report_path) if report_path.is_file() else None
        if report and report.get('candidate_id') != payload['candidate_id']: report = None
        return {'schema_version': 'value.network-overlay-candidate/v1', 'directory_id': root.name,
                'candidate_id': payload['candidate_id'], 'pack_id': manifest['id'], 'name': manifest.get('name'),
                'parent_pack_id': payload['parent_pack_id'], 'source_manifest_sha256': payload['source_manifest_sha256'],
                'roles': roles(manifest), 'validation': report}

    def clone(self, source_id, request):
        if set(request) != {'schema_version', 'new_pack_id', 'name', 'source_manifest_sha256'} or request['schema_version'] != 'value.network-overlay-clone/v1':
            raise ValueError('Clone requires schema, new_pack_id, name and exact source_manifest_sha256')
        new_id = str(request['new_pack_id']); name = str(request['name']).strip()
        if not name or len(name) > 200: raise ValueError('Provide a name of at most 200 characters')
        with self.locked():
            source = child(self.state / 'installed-packs', source_id)
            target = child(self.state / 'installed-packs', new_id)
            if target.exists() or source_id == new_id: raise ValueError('New overlay ID is already installed')
            source_hash = digest(source / 'manifest.json'); original = inventory(source)
            if source_hash != request['source_manifest_sha256']: raise ValueError('Source manifest changed; refresh installed overlays')
            manifest = read(source / 'manifest.json'); load_zonal_network_pack(source, manifest)
            candidates = self.state / 'candidates'; candidates.mkdir(exist_ok=True)
            directory_id = 'overlay-' + uuid.uuid4().hex
            stage = Path(tempfile.mkdtemp(prefix='.overlay-', dir=candidates))
            try:
                shutil.copytree(source, stage / 'pack')
                (stage / 'pack/installation.json').unlink(missing_ok=True)
                # Built-in teaching packs retain derivation at their root; the
                # existing bundle contract requires this evidence under files/.
                derivation = stage / 'pack/derivation.json'
                if derivation.is_file():
                    preserved = stage / 'pack/files/overlay-parent-records/derivation.json'
                    preserved.parent.mkdir(parents=True, exist_ok=True)
                    derivation.replace(preserved)
                inherited_qualification = {key: manifest.get(key) for key in (
                    'scientific_baseline_eligible', 'scientific_baseline_status', 'scientific_validation_status',
                    'contract_validation_status', 'validation_status', 'owner_approval') if key in manifest}
                manifest['overlay_editor_provenance'] = {'source_pack_id': source_id,
                    'source_manifest_sha256': source_hash, 'source_qualification': inherited_qualification}
                manifest['scientific_baseline_eligible'] = False
                manifest['scientific_baseline_status'] = 'independent_edit_pending_scientific_validation'
                manifest['scientific_validation_status'] = 'not_evaluated'
                for key in ('contract_validation_status', 'validation_status'):
                    if key in manifest: manifest[key] = 'not_evaluated'
                manifest.pop('owner_approval', None)
                previous_provenance = manifest['zonal_network_pack'].get('provenance', {})
                manifest['zonal_network_pack']['provenance'] = {'editor_version': 'value.network-overlay-editor/v1',
                    'parent_pack_id': source_id, 'source_manifest_sha256': source_hash,
                    'source_provenance': previous_provenance, 'runtime_downloads': False,
                    'status': 'independent_edit_pending_scientific_validation'}
                manifest['id'], manifest['name'] = new_id, name
                manifest['zonal_network_pack']['network_pack_id'] = new_id
                network = reconstruct(stage / 'pack', manifest)
                manifest['zonal_network_pack']['scientific_sha256'] = network.compute_scientific_sha256()
                write(stage / 'pack/manifest.json', manifest)
                payload = {'schema_version': 'value.data-workbench-candidate/v1', 'editor_kind': 'network_overlay',
                           'parent_pack_id': source_id, 'source_manifest_sha256': source_hash, 'source_inventory': original,
                           'requested_waivers': [], 'candidate_id': '', 'artifact_hashes': {}}
                self._pin(stage, payload)
                if inventory(source) != original: raise ValueError('Source changed during cloning')
                stage.replace(candidates / directory_id)
                return self._detail(candidates / directory_id)
            finally:
                if stage.exists(): shutil.rmtree(stage)

    def download_role(self, directory_id, role, expected_candidate_id):
        if not expected_candidate_id: raise ValueError('Exact candidate identity is required')
        with self.locked():
            root = self._root(directory_id); self._check(root, expected_candidate_id)
            manifest = read(root / 'pack/manifest.json')
            binding = manifest['bindings'].get(role)
            if not binding or binding.get('format') not in {'json', 'csv'}: raise ValueError('Only an existing JSON/CSV role can be downloaded')
            path = bound(root / 'pack', binding)
            if path.stat().st_size > MAX_UPLOAD: raise ValueError('Role download exceeds 32 MiB')
            raw = path.read_bytes()
            if len(raw) > MAX_UPLOAD or hashlib.sha256(raw).hexdigest() != binding['sha256']: raise ValueError('Role file bytes changed')
            self._check(root, expected_candidate_id)
            filename = str(binding.get('filename') or path.name)
            if Path(filename).name != filename or '/' in filename or '\\' in filename: filename = path.name
            filename = re.sub(r'[^A-Za-z0-9._-]', '-', filename).strip('.-') or ('role.' + binding['format'])
            return raw, filename, 'application/json' if binding['format'] == 'json' else 'text/csv'

    def upload(self, directory_id, role, raw, filename, expected):
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_UPLOAD: raise ValueError('Upload must contain 1 byte–32 MiB')
        if not expected: raise ValueError('X-Expected-Candidate-Id is required')
        if not filename or Path(filename).name != filename or '/' in filename or '\\' in filename: raise ValueError('Filename must be a basename')
        with self.locked():
            root = self._root(directory_id); payload = self._check(root, expected); self._source(payload)
            manifest = read(root / 'pack/manifest.json'); binding = manifest['bindings'].get(role)
            if not binding: raise ValueError('Only an existing declared role may be replaced')
            file_format = binding.get('format')
            if file_format not in {'json', 'csv'} or Path(filename).suffix.lower() != '.' + file_format: raise ValueError('Replace with the declared JSON or CSV format')
            if file_format == 'json': json.loads(raw.decode('utf-8'), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
            else: raw.decode('utf-8-sig')
            stage = Path(tempfile.mkdtemp(prefix='.overlay-edit-', dir=root.parent))
            backup = root.with_name('.backup-' + uuid.uuid4().hex)
            try:
                shutil.copytree(root, stage, dirs_exist_ok=True)
                destination = bound(stage / 'pack', binding); destination.write_bytes(raw)
                provenance = manifest['overlay_editor_provenance']
                history = provenance.setdefault('replaced_binding_history', {})
                history.setdefault(role, []).append(dict(binding))
                if not provenance.get('parent_rights_records'):
                    records = []
                    parent_records = stage / 'pack/files/overlay-parent-records' / payload['parent_pack_id']
                    parent_records.mkdir(parents=True, exist_ok=True)
                    for rights_name in ('RIGHTS.json', 'LICENSE', 'ATTRIBUTION.md'):
                        original = stage / 'pack' / rights_name
                        if original.is_file():
                            preserved = parent_records / rights_name
                            original.replace(preserved)
                            records.append(preserved.relative_to(stage / 'pack').as_posix())
                    provenance['parent_rights_records'] = records
                    provenance['source_rights_metadata'] = {key: manifest[key] for key in
                        ('licence', 'license', 'publication_status', 'copyright_affirmer') if key in manifest}
                manifest['licence'] = 'mixed-source-with-unresolved-upload-rights'
                manifest.pop('license', None)
                manifest.pop('copyright_affirmer', None)
                manifest['publication_status'] = 'local_use_only_no_redistribution_clearance'
                for key in ('licence', 'license', 'redistribution_class', 'source_url', 'source_version',
                            'transformation_version', 'attribution', 'access_date', 'copyright_affirmer'):
                    binding.pop(key, None)
                binding.update(licence='unknown', redistribution_class='unresolved_local_upload',
                    source_url='local-upload://' + role + '/' + hashlib.sha256(raw).hexdigest(),
                    source_version='sha256:' + hashlib.sha256(raw).hexdigest(),
                    transformation_version='value.network-overlay-editor/v1',
                    attribution='Local replacement upload; authorship and licence have not been declared.')
                binding.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), filename=filename)
                payload['replaced_roles'] = sorted(set(payload.get('replaced_roles', [])) | {role})
                rights_note = ('Parent rights and attribution records apply only to unchanged source files. '
                    'Replacement uploads have no declared licence or authorship. Local installation approval '
                    'acknowledges the review boundary and does not establish redistribution permission.')
                write(stage / 'pack/RIGHTS.json', {'schema_version': 'value.overlay-upload-rights/v1',
                    'status': 'unresolved_replacement_upload_rights', 'note': rights_note,
                    'parent_pack_id': payload['parent_pack_id'], 'parent_rights_records': provenance['parent_rights_records'],
                    'replacement_roles': payload['replaced_roles'],
                    'unchanged_roles': sorted(set(manifest['bindings']) - set(payload['replaced_roles']))})
                (stage / 'pack/LICENSE').write_text(rights_note + '\n', encoding='utf-8')

                try: manifest['zonal_network_pack']['scientific_sha256'] = reconstruct(stage / 'pack', manifest).compute_scientific_sha256()
                except (ValueError, KeyError, TypeError, AttributeError): manifest['zonal_network_pack']['scientific_sha256'] = ''
                write(stage / 'pack/manifest.json', manifest); self._pin(stage, payload)
                self._source(payload); self._check(root, expected)
                root.replace(backup)
                try: stage.replace(root)
                except OSError: backup.replace(root); raise
                shutil.rmtree(backup)
                return self._detail(root)
            finally:
                if stage.exists(): shutil.rmtree(stage)

    def _validate(self, root, expected):
        payload = self._check(root, expected); self._source(payload)
        manifest = read(root / 'pack/manifest.json'); errors, warnings = [], []
        try:
            general = validate_data_pack(root / 'pack', manifest, self.slots, verify_hashes_below_bytes=MAX_TREE)
            errors.extend(general.get('errors', [])); warnings.extend(general.get('warnings', []))
            network = load_zonal_network_pack(root / 'pack', manifest)
            if network.network_pack_id != manifest['id']: errors.append('Manifest and network identity IDs differ')
            years = sorted({int(period[:4]) for period in network.zonal_demand.period_ids if period[:4].isdigit()})
            declared = manifest.get('years')
            if declared and any(year not in declared for year in years): errors.append('Demand clock includes undeclared years')
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as exc: errors.append(str(exc)); years = []
        self._check(root, expected); self._source(payload)
        report = {'schema_version': 'value.network-overlay-validation/v1', 'candidate_id': payload['candidate_id'],
                  'status': 'blocked' if errors else 'passed', 'errors': list(dict.fromkeys(str(e) for e in errors)),
                  'warnings': list(dict.fromkeys(str(w) for w in warnings)), 'years': years,
                  'validators': ['validate_data_pack', 'load_zonal_network_pack'], 'scientific_validation_status': 'not_scientifically_validated',
                  'replaced_roles': payload.get('replaced_roles', [])}
        (root / 'review').mkdir(exist_ok=True); write(root / 'review/overlay-validation.json', report)
        return report

    def validate(self, directory_id, expected):
        with self.locked(): return self._validate(self._root(directory_id), expected)

    def promote(self, directory_id, request):
        promotion = PromotionRequest.from_dict(request)
        if not promotion.reviewer.strip() or not promotion.version.strip() or promotion.accepted_waivers: raise ValueError('Named reviewer/version required; this editor has no waivable failures')
        with self.locked():
            root = self._root(directory_id); payload = self._check(root, promotion.candidate_id)
            report = self._validate(root, promotion.candidate_id)
            if report['status'] != 'passed': raise ValueError('Whole-overlay validation is blocked: ' + '; '.join(report['errors'][:5]))
            manifest = read(root / 'pack/manifest.json')
            target = child(self.state / 'installed-packs', manifest['id'])
            if target.exists(): raise ValueError('Overlay ID already installed; publish a new ID')
            staging = self.state / 'promotion-staging'; staging.mkdir(exist_ok=True)
            archive = staging / (promotion.candidate_id + '.zip')
            result = build_data_bundle(pack_root=root / 'pack', destination=archive)
            self._check(root, promotion.candidate_id); self._source(payload)
            # Installer uses a temporary pack and publishes only after validation.
            installed = install_data_bundle(archive, packs_root=self.state / 'installed-packs', dataset_slots=self.slots,
                                            rights_acknowledged=True, minimum_free_space_bytes=0)
            try:
                self._check(root, promotion.candidate_id); self._source(payload)
                receipt = SignedBundleReceipt(network_pack_id=str(installed['pack_id']), candidate_id=promotion.candidate_id,
                    bundle_sha256=result['sha256'], manifest_sha256=digest(root / 'pack/manifest.json'), approved_by=promotion.reviewer,
                    approved_at=datetime.now(timezone.utc).isoformat(), accepted_waivers=())
                approvals = self.state / 'approvals'; approvals.mkdir(exist_ok=True)
                receipt_payload = {**receipt.to_dict(), 'version': promotion.version}
                write(approvals / (promotion.candidate_id + '.json'), receipt_payload)
            except (OSError, ValueError, TypeError, KeyError):
                if target.is_dir() and read(target / 'installation.json').get('bundle_sha256') == result['sha256']: shutil.rmtree(target)
                raise
            return receipt_payload
