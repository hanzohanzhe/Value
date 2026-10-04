"""Pure launcher boundaries; real archived server/worker acceptance is separate."""
import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('archived_value', ROOT / 'packaging/linux-local/archived_value.py')
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)

class ArchivedLauncherTests(unittest.TestCase):
    def test_recorded_environment_and_flags_not_host_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            flags = dict(optimize=0,hash_randomization=0,utf8_mode=1,safe_path=None,isolated=0,ignore_environment=0,no_user_site=0,bytes_warning=0)
            metadata = {'loader_environment':{'LD_LIBRARY_PATH':'/usr/local/cuda/lib64:'},'python_semantic_environment':{'PYTHONUTF8':'1','PYTHONHASHSEED':'0'},'thread_environment':{'PYTHONHASHSEED':'0','OMP_NUM_THREADS':'3'},'python_semantic_flags':flags,'import_paths':[{'path':'workspace'}]}
            config = {'prefix':folder,'data_home':str(Path(folder)/'state'),'python_executable':str(Path(folder)/'python'),'execution_record':{'environment':{'metadata':metadata}},'environment':{},'prepared_host_environment':{key:None for key in launcher.HOST_ENV}}
            with patch.dict(os.environ, {'PYTHONPATH':'/bad','PYTHONHOME':'/bad','PYTHONNOUSERSITE':'1','OMP_NUM_THREADS':'99','LD_LIBRARY_PATH':'/bad','NODE_OPTIONS':'--inspect'}):
                env = launcher.archived_environment(config)
            self.assertEqual(env['LD_LIBRARY_PATH'],'/usr/local/cuda/lib64:')
            self.assertEqual(env['OMP_NUM_THREADS'],'3')
            self.assertEqual(env['PYTHONHASHSEED'],'0')
            self.assertTrue(all(name not in env for name in ('PYTHONPATH','PYTHONHOME','PYTHONNOUSERSITE','NODE_OPTIONS')))
            command = launcher.archived_python_command(config,'-m','backend.server')
            self.assertNotIn('-s',command)
            self.assertIn('utf8=1',command)
            self.assertEqual(command[-2:],['-m','backend.server'])
            flags['isolated']=1
            with self.assertRaisesRegex(ValueError,'Unsupported'): launcher.archived_python_command(config,'-c','pass')
            config['environment']={'PYTHONPATH':'/bad'}
            with self.assertRaisesRegex(ValueError,'Unknown transport'): launcher.archived_environment(config)

    def test_recorded_two_workspace_paths_restore_only_controlled_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source = str(Path(folder)/'capsule/source/app')
            metadata = {'import_paths':[{'path':'workspace'},{'path':'workspace'}], 'loader_environment':{}, 'python_semantic_environment':{}, 'thread_environment':{}}
            config = {'prefix':folder,'data_home':str(Path(folder)/'state'),'source_root':source,'execution_record':{'environment':{'metadata':metadata}},'environment':{},'prepared_host_environment':{key:None for key in launcher.HOST_ENV}}
            with patch.dict(os.environ, {'PYTHONPATH':'/untrusted'}):
                self.assertEqual(launcher.archived_environment(config)['PYTHONPATH'],source)
            metadata['import_paths'] = [{'path':'workspace'}]
            self.assertNotIn('PYTHONPATH',launcher.archived_environment(config))
            metadata['import_paths'] = [{'path':'workspace'}]*3
            with self.assertRaisesRegex(ValueError,'multiplicity'): launcher.archived_environment(config)

    def test_interpreter_uses_recorded_root_and_url_selects_study(self):
        record = {'environment':{'roots':[{'path':'runtime','origin':'/original/python','resolved_origin':'/original/python'}]}}
        self.assertEqual(launcher.archived_path(record,'/new/capsule','/original/python/bin/python3.10'),'/new/capsule/environment/runtime/bin/python3.10')
        with self.assertRaises(ValueError): launcher.archived_path(record,'/new/capsule','/original/python-other/bin/python')
        self.assertEqual(launcher.workspace_url({'ui_port':8800,'project_id':'recovered-study'}),'http://127.0.0.1:8800/?view=run&study=recovered-study')

    def test_occupied_port_and_changed_process_ownership_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as listener:
            listener.bind(('127.0.0.1',0)); listener.listen(1)
            config = {'api_port':listener.getsockname()[1],'ui_port':8800}
            with patch.object(launcher,'probe_workspace') as probe:
                with self.assertRaisesRegex(ValueError,'occupied'): launcher.start(Path(folder),config)
                probe.assert_not_called()
        entry={'pid':123,'start_time':'original','argv':['python','-m','backend.server']}
        actual={'state':'S','group':123,'start_time':'reused','argv':[b'python',b'-m',b'backend.server'],'environment':[b'VALUE_LOCAL_INSTANCE=token']}
        with patch.object(launcher,'process_info',return_value=actual), patch.object(launcher.os,'killpg') as kill:
            with self.assertRaisesRegex(ValueError,'ownership'): launcher.stop_record({'token':'token','processes':{'api':entry}})
            kill.assert_not_called()

if __name__=='__main__': unittest.main()
