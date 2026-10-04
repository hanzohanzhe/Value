"""Temporary source/runtime fixtures only: never archive the live Python runtime."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import sys
import subprocess
from unittest.mock import patch
import unittest

from gridform_core.execution_archive import (_capture_bundle, ExecutionArchiveError,
    capture_execution_bundle, materialize_execution_bundle, verify_execution_bundle)


class ExecutionArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.source = self.root / 'app'; self.source.mkdir()
        (self.source / 'helper.py').write_text('constant = 1\n')
        (self.source / 'resource.csv').write_text('year,value\n2025,42\n')
        self.environment = self.root / 'runtime'; self.environment.mkdir()
        (self.environment / 'python').write_bytes(b'fixture interpreter bytes')
        (self.environment / 'lib.so').write_bytes(b'fixture native dependency bytes')
        self.cas = self.root / 'cas'
        self.metadata = {'sys_version': 'fixture-python', 'python_executable': '/host/python',
            'sys_prefix': '/host/runtime', 'sys_base_prefix': '/host/runtime',
            'platform': 'fixture', 'machine': 'fixture', 'soabi': 'fixture', 'thread_environment': {'OMP_NUM_THREADS': '1'}}

    def tearDown(self): self.temp.cleanup()

    def capture(self, archive=False):
        return _capture_bundle(source_roots=[('app', self.source)], environment_roots=[('runtime', self.environment)],
            metadata=self.metadata, archive_root=self.cas, archive=archive, shared_libraries=False)

    def test_helpers_resources_dependency_bytes_and_host_independence(self):
        initial = self.capture()
        self.assertFalse(self.cas.exists())
        (self.source / 'helper.py').write_text('constant = 2\n')
        helper = self.capture(); self.assertNotEqual(initial['source_sha256'], helper['source_sha256'])
        (self.source / 'resource.csv').write_text('year,value\n2025,43\n')
        resource = self.capture(); self.assertNotEqual(helper['source_sha256'], resource['source_sha256'])
        (self.environment / 'lib.so').write_bytes(b'different dependency bytes')
        changed = self.capture(); self.assertNotEqual(resource['environment_sha256'], changed['environment_sha256'])
        self.metadata['sys_prefix'] = '/different/host/runtime'
        self.assertEqual(changed['identity_sha256'], self.capture()['identity_sha256'])
        self.metadata['thread_environment']['OMP_NUM_THREADS'] = '2'
        self.assertNotEqual(changed['environment_sha256'], self.capture()['environment_sha256'])

    def test_deduplicated_archive_and_tamper_rejection(self):
        hashed = self.capture(); archived = self.capture(True)
        self.assertEqual(hashed['identity_sha256'], archived['identity_sha256'])
        self.assertTrue(archived['archive_complete'])
        again = self.capture(True)
        self.assertEqual(archived, again)
        self.assertEqual(len(list((self.cas / 'objects').glob('*.zip'))), 2)
        verify_execution_bundle(archived, archive_root=self.cas)
        path = self.cas / archived['source']['artifact']['path']
        with path.open('ab') as stream: stream.write(b'tampered')
        with self.assertRaisesRegex(ExecutionArchiveError, 'hash mismatch'): verify_execution_bundle(archived, archive_root=self.cas)

    def test_safe_restore_and_source_symlink_rejection(self):
        archived = self.capture(True); destination = self.root / 'restored'
        restored = materialize_execution_bundle(archived, archive_root=self.cas, destination=destination)
        self.assertFalse(restored['executed'])
        self.assertEqual((destination / 'source/app/resource.csv').read_bytes(), (self.source / 'resource.csv').read_bytes())
        with self.assertRaisesRegex(ExecutionArchiveError, 'new or empty'):
            materialize_execution_bundle(archived, archive_root=self.cas, destination=destination)
        unsafe = deepcopy(archived); unsafe['source']['files'][0]['path'] = '../escape'
        with self.assertRaisesRegex(ExecutionArchiveError, 'Unsafe'):
            materialize_execution_bundle(unsafe, archive_root=self.cas, destination=self.root / 'unsafe')
        (self.source / 'linked.py').symlink_to(self.source / 'helper.py')
        with self.assertRaisesRegex(ExecutionArchiveError, 'symbolic'):
            self.capture()
        self.assertFalse((self.root / 'escape').exists())

    def test_loaded_server_clean_worker_and_unmanaged_path_identity(self):
        app = self.root / 'workspace'; app.mkdir()
        for name in ('backend', 'gridform_core', 'requirements'):
            (app / name).mkdir()
        (app / 'pyproject.toml').write_text('[project]\nname="fixture"\n')
        state = self.root / 'state'; sources = []
        for category, identifier, manifest in (
                ('installed', 'offer', 'value-module.json'),
                ('installed-extensions', 'observer', 'force-extension.json')):
            version = state / 'modules' / category / identifier / '0.1.0'
            source = version / 'src'; source.mkdir(parents=True)
            (source / (identifier + '.py')).write_text('VALUE = 73\n')
            (version / 'installation.json').write_text(json.dumps(
                {'enabled': True, 'source_root': 'src'}))
            (version / manifest).write_text('{}'); sources.append(str(source))
        # Two fresh interpreters also exercise the process boundary. Only the
        # server process imports plugin code before admission.
        code = """
import json, pathlib, sys
from gridform_core import execution_archive as archive
app, state, runtime = map(pathlib.Path, sys.argv[1:4])
roots = [str(state/'modules'/category/name/'0.1.0/src')
         for category,name in [('installed','offer'),('installed-extensions','observer')]]
sys.path[:] = [str(app), str(runtime)]
if sys.argv[4] == 'server':
    sys.path[:0] = roots
    __import__('offer'); __import__('observer')
archive._environment_roots = lambda: [('runtime', runtime)]
archive._metadata = lambda: {'sys_version':'fixture-python'}
archive._ldd_closure = lambda files: ([], [], {'unresolved':[], 'runtime_matches':[], 'discovery_errors':[]})
result = archive.capture_execution_bundle(source_root=app, data_home=state, archive_root=state/'cas')
print(json.dumps({'identity':result['identity_sha256'], 'paths':sys.path}))
"""
        processes = [subprocess.run([sys.executable, '-c', code, str(app),
                     str(state), str(self.environment), mode], check=True,
                     capture_output=True, text=True) for mode in ('server', 'worker')]
        self.assertEqual(json.loads(processes[0].stdout), json.loads(processes[1].stdout))
        base_paths = [str(app), str(self.environment)]
        native = {'unresolved': [], 'runtime_matches': [], 'discovery_errors': []}
        with patch('gridform_core.execution_archive._environment_roots',
                   return_value=[('runtime', self.environment)]), patch(
                'gridform_core.execution_archive._metadata', return_value=self.metadata), patch(
                'gridform_core.execution_archive._ldd_closure',
                return_value=([], [], native)), patch.object(sys, 'path', base_paths[:]):
            def capture():
                return capture_execution_bundle(source_root=app, data_home=state,
                                                archive_root=self.cas)
            worker = capture(); expected = list(reversed(sources)) + base_paths
            self.assertEqual(sys.path, expected)
            sys.path[:] = sources + sources + base_paths
            server = capture()
            self.assertEqual(sys.path, expected)
            self.assertEqual(server['identity_sha256'], worker['identity_sha256'])
            self.assertTrue(server['identity_complete'])
            from gridform_core.runtime_paths import activate_external_module_sources
            activate_external_module_sources(state / 'modules')
            self.assertEqual(sys.path, expected)
            arbitrary = self.root / 'unmanaged'; arbitrary.mkdir()
            sys.path.append(str(arbitrary)); unsafe = capture()
            self.assertIn(str(arbitrary), sys.path)
            self.assertEqual(unsafe['environment']['metadata']['unarchived_import_paths'],
                             [str(arbitrary)])
            self.assertFalse(unsafe['identity_complete'])
            self.assertNotEqual(unsafe['identity_sha256'], worker['identity_sha256'])


if __name__ == '__main__': unittest.main()
