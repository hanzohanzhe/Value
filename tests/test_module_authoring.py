import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.module_authoring import module_authoring_detail, module_authoring_template, module_candidate_identity, MAX_SOURCE_BYTES
from gridform_core.module_conformance import REQUIRED_METHODS
from gridform_core.v2.module_manifest import ModuleManifest, ModuleRegistryV2


class Registry:
    def __init__(self, manifest):
        self.current = manifest
    def manifest(self, module_id, expected_slot=None):
        if module_id != self.current.id:
            raise ValueError('Module is not registered')
        if expected_slot is not None and expected_slot != self.current.slot:
            raise ValueError('Slot mismatch')
        return self.current
    def manifests(self):
        return {self.current.id:self.current}
    def resolve(self, *args, **kwargs):
        raise AssertionError('GET must not instantiate algorithms')


class ModuleAuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'plugin.py'
        self.path.write_text('class Candidate: pass\n')
        self.manifest = ModuleManifest('custom-storage', 'Custom storage', '1.0.0', 'storage_cost', 'author_test.plugin:Candidate', 'value.storage-cost/v1', (), (), (), (), (), 'deterministic', (), 'test')
        self.registry = Registry(self.manifest)
        self.patch = patch.dict(sys.modules, {'author_test.plugin':SimpleNamespace(__file__=str(self.path))})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_identity_hash_tracks_manifest_source_and_slot(self):
        first = module_authoring_detail(self.registry, self.manifest.id)
        self.assertEqual(first['identity_sha256'], module_candidate_identity(self.registry, self.manifest.id))
        self.assertEqual(first['methods'], list(REQUIRED_METHODS['storage_cost']))
        self.assertEqual(first['identity']['source_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.path.write_text('class Candidate: changed=True\n')
        self.assertNotEqual(first['identity_sha256'], module_candidate_identity(self.registry, self.manifest.id))
        second = module_candidate_identity(self.registry, self.manifest.id)
        self.registry.current = replace(self.manifest, state_writes=('changed_state',))
        self.assertNotEqual(second, module_candidate_identity(self.registry, self.manifest.id))
        with self.assertRaises(ValueError):
            module_candidate_identity(self.registry, self.manifest.id, 'psm')

    def test_unknown_id_and_bounded_source(self):
        with self.assertRaises(ValueError):
            module_authoring_detail(self.registry, '../../secret')
        self.path.write_bytes(b'#' * (MAX_SOURCE_BYTES + 9))
        detail = module_authoring_detail(self.registry, self.manifest.id)
        self.assertTrue(detail['source']['truncated'])
        self.assertEqual(len(detail['source']['content']), MAX_SOURCE_BYTES)
        self.assertEqual(detail['identity']['source_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.path.unlink()
        self.assertFalse(module_authoring_detail(self.registry, self.manifest.id)['source']['available'])
        with self.assertRaises(ValueError):
            module_candidate_identity(self.registry, self.manifest.id)

    def test_only_matching_existing_report(self):
        detail = module_authoring_detail(self.registry, self.manifest.id)
        record = {'manifest_sha256':hashlib.sha256(json.dumps(self.manifest.to_dict(),sort_keys=True,separators=(',', ':'),ensure_ascii=False).encode('utf-8')).hexdigest(), 'module_id':self.manifest.id,'module_version':'1.0.0','source_sha256':detail['identity']['source_sha256'],'slot':'storage_cost','contract_version':self.manifest.contract_version,'implementation':self.manifest.implementation,'origin':'local_bundle','conformance':{'module_id':self.manifest.id,'version':'1.0.0','slot':'storage_cost','status':'passed','errors':[],'warnings':[]}}
        self.assertEqual(module_authoring_detail(self.registry, self.manifest.id, installation_records=[record])['conformance']['status'], 'passed')
        for changed in ({'source_sha256':'x'*64},{'module_version':'2.0.0'},{'implementation':'different:Class'}, {'manifest_sha256':None}):
            self.assertEqual(module_authoring_detail(self.registry, self.manifest.id, installation_records=[{**record, **changed}])['conformance']['status'], 'not_run')

        self.registry.current = replace(self.manifest, state_writes=('changed_state',))
        self.assertEqual(module_authoring_detail(self.registry, self.manifest.id, installation_records=[record])['conformance']['status'], 'not_run')

    def test_template_is_safe_editable_project_and_no_claimed_solver(self):
        for slot in ('storage_cost', 'psm'):
            self.registry.current = replace(self.manifest, slot=slot, solver_contract={'backend':'original-solver'}, provides_capabilities=('original.claim',))
            archive = zipfile.ZipFile(io.BytesIO(module_authoring_template(self.registry, self.manifest.id, template_id='new-module', version='0.2.0')))
            self.assertTrue(all(not name.startswith('/') and '..' not in name.split('/') for name in archive.namelist()))
            payload = json.loads(archive.read('value-module.json'))
            self.assertEqual(payload['id'], 'new-module')
            self.assertEqual(payload['version'], '0.2.0')
            self.assertEqual(payload['status'], 'experimental')
            self.assertEqual(payload['solver_contract'], {})
            self.assertEqual(payload['provides_capabilities'], ['storage.bid-cost-function'] if slot == 'storage_cost' else [])
            source = archive.read(next(name for name in archive.namelist() if name.endswith('/plugin.py'))).decode()
            if slot == 'storage_cost':
                self.assertEqual(payload['inputs'], ['storage_technology', 'previous_year_sales'])
                from gridform_core.module_conformance import check_storage_lifecycle
                namespace = {}
                exec(compile(source.replace('42.0', '73.0'), 'downloaded-template.py', 'exec'), namespace)
                definition = namespace['CandidateModule']()
                self.assertEqual(definition.id, payload['id'])
                self.assertEqual(definition.version, payload['version'])
                offer = definition.create(battery_type='1c', period_hours=0.5)
                check_storage_lifecycle(offer)
                self.assertEqual(offer.report()['fixed_offer_gbp_per_mwh'], 73.0)
                candidate = ModuleManifest.from_dict(payload)
                entry = candidate.implementation.split(':')[0]
                with patch.dict(sys.modules, {entry:SimpleNamespace(CandidateModule=type('CandidateModule', (), {})), 'author_test.plugin':SimpleNamespace(Candidate=type('Candidate', (), {}))}):
                    psm = replace(self.manifest, id='requiring-psm', slot='psm', contract_version='value.psm/v2', requires_capabilities=('storage.bid-cost-function',), selection_required=False)
                    real_registry = ModuleRegistryV2((candidate, psm))
                    real_registry.validate_selection({'psm':'requiring-psm', 'storage_cost':'new-module'})
            self.assertIn('42.0' if slot == 'storage_cost' else 'NotImplementedError', source)
            self.assertIn('scripts/build_module_bundle.py', archive.read('README.md').decode())
            self.assertIn('Apache License', archive.read('LICENSE').decode())
        for invalid in ('../bad', self.manifest.id, 'UPPER'):
            with self.assertRaises(ValueError):
                module_authoring_template(self.registry, self.manifest.id, template_id=invalid)

if __name__ == '__main__':
    unittest.main()
