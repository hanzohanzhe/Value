import importlib.util
import json
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

spec = importlib.util.spec_from_file_location('desktop_value_full', Path(__file__).parents[1] / 'packaging/desktop-local/desktop_value.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def make_bundle(root):
    paths = ['app/backend/server.py', 'app/dist/server/index.js', 'app/gridform_core/application.py', 'app/scripts/serve-value-ui.mjs', 'app/scripts/install_synthetic_pack.py']
    runtimes = {'python': 'runtime/python/python.exe', 'node': 'runtime/node/node.exe'} if sys.platform == 'win32' else {'python': 'runtime/python/bin/python3.10', 'node': 'runtime/node/bin/node'}
    paths += list(runtimes.values())
    for name in paths:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('fixture')
    manifest = {'schema_version': controller.SCHEMA, 'target_platform': sys.platform, 'architectures': [controller.architecture(platform.machine())], 'teaching_packs': controller.PACKS, 'bundled_runtimes': runtimes, 'files': [{'path': name, 'bytes': (root/name).stat().st_size, 'sha256': controller.digest(root/name)} for name in paths]}
    (root/'release-manifest.json').write_text(json.dumps(manifest))
    return manifest


def test_private_paths_without_path_lookup(tmp_path):
    manifest = make_bundle(tmp_path)
    with mock.patch.object(controller.shutil, 'which', side_effect=AssertionError('PATH lookup')):
        paths = controller.runtime_paths(tmp_path, manifest)
        assert controller.executable(paths[0]) == paths[0]
    with pytest.raises(ValueError, match='overrides'):
        controller.runtime_paths(tmp_path, manifest, '/external/python')


def test_install_validates_temp_and_records_final_paths(tmp_path):
    bundle = tmp_path/'bundle'; bundle.mkdir()
    manifest = make_bundle(bundle)
    prefix = tmp_path/'installed'
    probed = []
    def probe(python, node, manifest):
        probed.append(python)
        return {name: {'path': path, 'sha256': controller.digest(path)} for name, path in [('python', python), ('node', node)]}
    with mock.patch.object(controller, 'check_runtimes', side_effect=probe), mock.patch.object(controller.subprocess, 'run'):
        controller.install(SimpleNamespace(bundle=str(bundle), prefix=str(prefix), python=None, node=None))
    assert '.value-install-' in probed[0]
    receipt = json.loads((prefix/'install-receipt.json').read_text())
    assert receipt['runtimes']['python']['path'] == str(prefix/manifest['bundled_runtimes']['python'])
    with mock.patch.object(controller, 'check_runtimes', side_effect=probe):
        controller.validate_install(prefix)
    assert probed[-1] == receipt['runtimes']['python']['path']


@pytest.mark.parametrize('damage', ['missing', 'tamper', 'os', 'arch'])
def test_rejects_invalid_full_bundle(tmp_path, damage):
    manifest = make_bundle(tmp_path)
    python = tmp_path/manifest['bundled_runtimes']['python']
    if damage == 'missing': python.unlink()
    if damage == 'tamper': python.write_text('modified')
    if damage == 'os': manifest['target_platform'] = 'invalid'
    if damage == 'arch': manifest['architectures'] = ['invalid']
    (tmp_path/'release-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError): controller.verify_inventory(tmp_path)


def test_removes_ambient_python_state():
    with mock.patch.dict(controller.os.environ, {'PYTHONUSERBASE': '/untrusted', 'PYTHONHOME': '/untrusted', 'PYTHONPATH': '/untrusted'}):
        env = controller.clean_environment()
    assert 'PYTHONUSERBASE' not in env and 'PYTHONHOME' not in env and 'PYTHONPATH' not in env
    assert env['PYTHONNOUSERSITE'] == '1'


def test_failed_runtime_probe_cleans_only_current_temporary(tmp_path):
    bundle = tmp_path/'bundle'; bundle.mkdir(); make_bundle(bundle)
    existing = tmp_path/'existing'; existing.mkdir(); (existing/'state').write_text('preserved')
    prefix = tmp_path/'new-install'
    with mock.patch.object(controller, 'check_runtimes', side_effect=ValueError('broken runtime')):
        with pytest.raises(ValueError, match='broken runtime'):
            controller.install(SimpleNamespace(bundle=str(bundle), prefix=str(prefix), python=None, node=None))
    assert not prefix.exists()
    assert not list(tmp_path.glob('.value-install-*'))
    assert (existing/'state').read_text() == 'preserved'
