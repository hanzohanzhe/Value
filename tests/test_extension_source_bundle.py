import hashlib
import json
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace
import zipfile
from pathlib import Path
from unittest.mock import patch

from gridform_core.extension_framework import ExtensionManifest, ExtensionRegistry, ExtensionRuntime, ConditionalDataRole, ArtifactDeclaration, HookDeclaration, ResolvedExtensionGraph, canonical_hash
from gridform_core.extension_bundle import install_extension_bundle, set_extension_enabled, ExtensionBundleError, validate_extension_bundle, list_extension_installations
from gridform_core.v2.module_manifest import workspace_registry
from gridform_core.runtime_paths import activate_external_module_sources


class ExtensionSourceBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.modules = self.root / 'modules'
        self.package = 'value_audit_' + uuid.uuid4().hex[:12]
        self.original_path = list(sys.path)
        self.addCleanup(self.clean)

    def clean(self):
        sys.path[:] = self.original_path
        for name in list(sys.modules):
            if name.startswith('value_audit_'):
                del sys.modules[name]

    def bundle(self, *, package=None, version='0.1.0', bad=False):
        package = package or self.package
        manifest = {'schema_version':'value.extension-bundle/v1','id':'vendor-audit-extension','name':'Audit','version':version,'licence':'Apache-2.0','namespace':'vendor.audit','provided_capabilities':[],'hooks':[{'hook':'initialize','implementation':package+'.hooks:AuditHooks'}], 'state_schema_version':'vendor.audit.state/v1','state_migrations':{'0.1.0':'declaration-only'}}
        source = "class AuditHooks:\n    def initialize(self, payload):\n        return {'owner':'vendor-audit-extension','schema_version':'vendor.audit.state/v1'}\n"
        if bad:
            source = 'class AuditHooks: pass\n'
        files = {'force-extension.json':json.dumps(manifest).encode(), 'LICENSE':b'Apache-2.0', 'src/'+package+'/__init__.py':b'', 'src/'+package+'/hooks.py':source.encode()}
        descriptor = {'schema_version':'value.extension-bundle/v1','files':[{'path':name,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()} for name,value in files.items()]}
        path = self.root / (package+'-'+version+'.zip')
        with zipfile.ZipFile(path, 'w') as archive:
            for name,value in files.items():
                archive.writestr(name,value)
            archive.writestr('force-extension-bundle.json',json.dumps(descriptor))
        return path

    def test_role_projection_roundtrip_strict_marker(self):
        role = ConditionalDataRole('vendor.audit.series','audit/v1','Extension','Series',('csv',))
        self.assertEqual(ConditionalDataRole.from_dict(role.to_dataset_slot()),role)
        with self.assertRaises(ValueError):
            ConditionalDataRole.from_dict({**role.to_dataset_slot(),'extension_role':False})
        with self.assertRaises(TypeError):
            ConditionalDataRole.from_dict({**role.to_dataset_slot(),'unknown':True})

    def test_trust_source_install_and_frozen_runtime_identity(self):
        path = self.bundle()
        with self.assertRaises(ExtensionBundleError):
            install_extension_bundle(path,trust_acknowledged=False,modules_root=self.modules)
        report = install_extension_bundle(path,trust_acknowledged=True,modules_root=self.modules)
        self.assertEqual(report['source_root'],'src')
        self.assertFalse(any(name.startswith(self.package) for name in sys.modules))
        registry = workspace_registry(self.modules).extension_registry
        graph = registry.resolve(['vendor-audit-extension'])
        frozen = graph.to_dict()
        self.assertIn('vendor-audit-extension',frozen['manifests'])
        self.assertEqual(len(frozen['hook_source_identities']['vendor-audit-extension'][0]['source_sha256']),64)
        ExtensionRuntime(graph)
        source = self.modules / 'installed-extensions/vendor-audit-extension/0.1.0/src' / self.package / 'hooks.py'
        source.write_text(source.read_text()+'# changed\n')
        with self.assertRaises(ValueError):
            ExtensionRuntime(graph)

    def test_collision_unique_version_and_enable_disable(self):
        path = self.bundle()
        install_extension_bundle(path,trust_acknowledged=True,modules_root=self.modules)
        set_extension_enabled('vendor-audit-extension',False,modules_root=self.modules)
        self.assertNotIn('vendor-audit-extension',workspace_registry(self.modules).extension_manifests())
        set_extension_enabled('vendor-audit-extension',True,modules_root=self.modules)
        self.assertIn('vendor-audit-extension',workspace_registry(self.modules).extension_manifests())
        with self.assertRaises(ExtensionBundleError):
            install_extension_bundle(self.bundle(version='0.2.0'),trust_acknowledged=True,modules_root=self.modules)
        new_package = self.package+'_v2'
        install_extension_bundle(self.bundle(package=new_package,version='0.2.0'),trust_acknowledged=True,modules_root=self.modules)
        self.assertTrue((self.modules/'installed-extensions/vendor-audit-extension/0.1.0/installation.json').exists())
        with self.assertRaises(ExtensionBundleError):
            install_extension_bundle(self.bundle(package='json',version='0.3.0'),trust_acknowledged=True,modules_root=self.modules)

    def test_bad_hook_and_publication_failure_roll_back(self):
        with self.assertRaises(ExtensionBundleError):
            install_extension_bundle(self.bundle(bad=True),trust_acknowledged=True,modules_root=self.modules)
        self.assertFalse((self.modules/'extensions/vendor-audit-extension.json').exists())
        path = self.bundle()
        original_replace = Path.replace
        def fail_publish(item,target):
            if item.name == 'vendor-audit-extension.json.tmp':
                raise OSError('injected publication failure')
            return original_replace(item,target)
        with patch.object(Path,'replace',fail_publish), self.assertRaises(OSError):
            install_extension_bundle(path,trust_acknowledged=True,modules_root=self.modules)
        self.assertFalse((self.modules/'installed-extensions/vendor-audit-extension/0.1.0').exists())
        self.assertFalse((self.modules/'extensions/vendor-audit-extension.json').exists())
        self.assertFalse(any(name.startswith(self.package) for name in sys.modules))

    def test_installer_source_path_is_not_arbitrary(self):
        record = self.modules/'installed-extensions/evil/0.1.0/installation.json'
        record.parent.mkdir(parents=True)
        record.write_text(json.dumps({'enabled':True,'source_root':'../../../../outside'}))
        self.assertEqual(activate_external_module_sources(self.modules),())

    def test_nonobject_json_rejected_and_modified_manifest_report_not_reused(self):
        original = self.bundle()
        for member in ('force-extension-bundle.json', 'force-extension.json'):
            invalid = self.root / ('invalid-' + member + '.zip')
            with zipfile.ZipFile(original) as archive:
                files = {name:archive.read(name) for name in archive.namelist()}
            files[member] = b'[]'
            with zipfile.ZipFile(invalid,'w') as archive:
                for name,value in files.items():
                    archive.writestr(name,value)
            with self.assertRaises(ExtensionBundleError) as caught:
                validate_extension_bundle(invalid)
            self.assertEqual(caught.exception.code,'GF_EXTENSION_JSON')
        install_extension_bundle(original,trust_acknowledged=True,modules_root=self.modules)
        self.assertEqual(list_extension_installations(self.modules)[0]['conformance']['status'],'passed')
        path = self.modules/'installed-extensions/vendor-audit-extension/0.1.0/force-extension.json'
        manifest = json.loads(path.read_text())
        manifest['name'] = 'Changed after validation'
        path.write_text(json.dumps(manifest))
        self.assertEqual(list_extension_installations(self.modules)[0]['conformance']['status'],'not_run')

    def test_frozen_graph_checkpoint_identity_json_roundtrip(self):
        from gridform_core.v2.orchestrator import checkpoint_identity
        manifest = ExtensionManifest(id='audit-roundtrip',name='Audit',version='0.1.0',licence='Apache-2.0',namespace='vendor.roundtrip',provided_capabilities=(),artifacts=(ArtifactDeclaration('audit.summary','application/json','audit.schema/v1',('year','source_inputs_sha256')),),hooks=(HookDeclaration('after_psm','gridform_core.toy_extension:ToyAuditHooks',(),()),))
        graph = ResolvedExtensionGraph((manifest,),{}, {}, {'after_psm':('audit-roundtrip',)}, 'a'*64)
        frozen = graph.to_dict()
        self.assertEqual(frozen,json.loads(json.dumps(frozen)))
        self.assertEqual(canonical_hash(manifest.to_dict()),canonical_hash(frozen['manifests']['audit-roundtrip']))
        run = SimpleNamespace(run_id='fixture',project_id='study',data_pack_id='pack',start_year=2025,end_year=2025,modules={},scientific_parameters={},extensions={'extension_graph':frozen})
        identity = checkpoint_identity(run)
        self.assertEqual(identity,json.loads(json.dumps(identity)))

if __name__ == '__main__':
    unittest.main()
