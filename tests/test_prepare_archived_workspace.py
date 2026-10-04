import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('prepare_workspace',Path(__file__).resolve().parents[1]/'scripts/prepare_archived_workspace.py')
MODULE=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)

class ArchivedWorkspacePreparationTests(unittest.TestCase):
    def test_acknowledgement_precedes_any_execution_or_writes(self):
        with tempfile.TemporaryDirectory() as root, patch.object(MODULE,'review') as review:
            destination=Path(root)/'new'
            with self.assertRaisesRegex(MODULE.PreparationError,'acknowledge-code'):
                MODULE.prepare(run_id='run',data_home=Path(root),destination=destination,node=Path(root)/'node',name='Study')
            review.assert_not_called(); self.assertFalse(destination.exists())

    def test_reject_symlinks_and_traversal_before_copy(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); source=root/'source'; source.mkdir(); (source/'evil').symlink_to(root)
            with self.assertRaises(MODULE.PreparationError): MODULE.copy_tree(source,root/'copy')
            self.assertFalse((root/'copy').exists())
            with self.assertRaises(MODULE.PreparationError): MODULE.safe(root/'..'/'escape')

    def test_failed_materialization_cleans_only_owned_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root); (root/'state').mkdir(); node=root/'node'; node.write_text('node'); sentinel=root/'original'; sentinel.write_text('unchanged')
            record={'source':{},'environment':{}}
            with patch.object(MODULE.subprocess,'run',return_value=type('Result',(),{'returncode':0,'stdout':'{"version":"24.19.0","platform":"linux","arch":"x64"}'})()), patch.object(MODULE,'review',return_value={'execution_record':record,'review_sha256':'review'}), patch.object(MODULE,'materialize_execution_bundle',side_effect=ValueError('tamper')):
                with self.assertRaisesRegex(ValueError,'tamper'):
                    MODULE.prepare(run_id='run',data_home=root/'state',destination=root/'new',node=node,name='Study',acknowledge_code=True,review_sha256='review')
            self.assertFalse((root/'new').exists()); self.assertEqual(sentinel.read_text(),'unchanged')
            with self.assertRaisesRegex(MODULE.PreparationError,'must not exist'):
                MODULE.prepare(run_id='run',data_home=root,destination=root,node=node,name='Study',acknowledge_code=True,review_sha256='review')
    def test_stale_copied_evidence_cannot_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); state=root/'original-state'; run=state/'runs'/'run'
            snapshot=run/'input-snapshot'; snapshot.mkdir(parents=True)
            (snapshot/'canonical.csv').write_text('year,value\n2026,42\n')
            for filename in ('status.json','execution-bundle.json'):
                (run/filename).write_text('{}')
            objects=state/'execution-archives'/'objects'; objects.mkdir(parents=True)
            record={kind:{'artifact':{'path':f'objects/{kind}.zip'}} for kind in ('source','environment')}
            for kind in record: (objects/f'{kind}.zip').write_bytes(kind.encode())
            sentinel=state/'sentinel'; sentinel.write_text('original bytes')
            node=root/'node'; node.write_text('mock node')
            destination=root/'prepared'
            original={'review_sha256':'original','execution_record':record}
            copied={'review_sha256':'copied-changed','execution_record':record}

            def materialize(*args, **kwargs):
                kwargs['destination'].mkdir()
                return {}

            def inspect_review(*,run_id,data_home):
                if data_home == state: return original
                # The real prepare path must have independently copied all inputs/CAS
                # before the changed copied evidence is discovered.
                copied_run=data_home/'runs'/run_id
                self.assertEqual((copied_run/'input-snapshot/canonical.csv').read_bytes(),
                                 (snapshot/'canonical.csv').read_bytes())
                for kind in record:
                    self.assertEqual((data_home/'execution-archives/objects'/f'{kind}.zip').read_bytes(),kind.encode())
                return copied

            result=type('NodeResult',(),{'returncode':0,'stdout':'{"version":"24.19.0","platform":"linux","arch":"x64"}'})()
            with patch.object(MODULE.subprocess,'run',return_value=result) as subprocess_run, \
                 patch.object(MODULE,'review',side_effect=inspect_review) as review, \
                 patch.object(MODULE,'materialize_execution_bundle',side_effect=materialize), \
                 patch.object(MODULE,'launcher_module') as launcher:
                with self.assertRaisesRegex(MODULE.PreparationError,'changed since review'):
                    MODULE.prepare(run_id='run',data_home=state,destination=destination,node=node,
                                   name='Study',acknowledge_code=True,review_sha256='original')
                self.assertEqual(review.call_count,2)
                launcher.assert_not_called()
                subprocess_run.assert_called_once()
                self.assertEqual(subprocess_run.call_args.args[0][:2],[str(node),'-p'])
            self.assertFalse(destination.exists())
            self.assertEqual(sentinel.read_text(),'original bytes')
            self.assertEqual((snapshot/'canonical.csv').read_text(),'year,value\n2026,42\n')

if __name__=='__main__': unittest.main()
