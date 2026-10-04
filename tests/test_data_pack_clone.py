from __future__ import annotations
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.data_pack_clone import DataPackCloneError, clone_data_pack, guard_clone_upload, manifest_sha256


class DataPackCloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'files').mkdir()
        data = b'original input'
        (self.source / 'files/input.csv').write_bytes(data)
        (self.source / 'RIGHTS.json').write_text('{"licence":"retained"}')
        (self.source / 'value-data-bundle.json').write_text('{}')
        (self.source / 'installation.json').write_text('{"validation":"source-only"}')
        self.manifest = {'schema_version':'value.data-pack/v1', 'id':'source', 'name':'Source',
                         'provenance':{'source':'public'}, 'bindings':{'demand.real':{
                             'uri':'files/input.csv','sha256':hashlib.sha256(data).hexdigest(),
                             'bytes':len(data),'licence':'original','validation':{'status':'passed'}}}}
        self.save()
    def save(self):
        (self.source / 'manifest.json').write_text(json.dumps(self.manifest))
        self.request = {'schema_version':'value.data-pack-clone-request/v1','name':'Copy',
                        'source_manifest_sha256':manifest_sha256(self.source / 'manifest.json')}
    def clone(self):
        return clone_data_pack('source',self.request,packs_root=self.root)
    def test_independent_files_and_metadata(self):
        result = self.clone(); pack = result['data_pack']; dest = self.root / pack['id']
        self.assertFalse(result['run_started'])
        self.assertEqual(pack['bindings'],self.manifest['bindings'])
        self.assertEqual(pack['provenance'],self.manifest['provenance'])
        self.assertTrue((dest / 'RIGHTS.json').exists())
        self.assertFalse((dest / 'installation.json').exists())
        self.assertFalse((dest / 'value-data-bundle.json').exists())
        self.assertNotEqual((dest / 'files/input.csv').stat().st_ino,(self.source / 'files/input.csv').stat().st_ino)
        (dest / 'files/input.csv').write_bytes(b'changed')
        self.assertEqual((self.source / 'files/input.csv').read_bytes(),b'original input')
        self.assertEqual(pack['manifest_sha256'],manifest_sha256(dest / 'manifest.json'))
    def test_stale_corrupt_and_unsafe_sources(self):
        with self.subTest('stale'):
            self.request['source_manifest_sha256']='0'*64
            with self.assertRaises(DataPackCloneError): self.clone()
        self.save()
        with self.subTest('corrupt'):
            (self.source / 'files/input.csv').write_bytes(b'corrupt')
            with self.assertRaises(DataPackCloneError): self.clone()
        with self.subTest('unsafe'):
            self.manifest['bindings']['demand.real']['uri']='../outside.csv'; self.save()
            with self.assertRaises(DataPackCloneError): self.clone()
        (self.source / 'manifest.json').write_text('[]')
        self.request['source_manifest_sha256']=manifest_sha256(self.source / 'manifest.json')
        with self.assertRaises(DataPackCloneError): self.clone()
        with self.subTest('reserved metadata binding'):
            self.manifest['bindings']['demand.real']['uri']='installation.json'; self.save()
            with self.assertRaises(DataPackCloneError): self.clone()
        self.assertEqual([p.name for p in self.root.iterdir()],['source'])
    def test_copy_failure_leaves_no_partial_pack(self):
        with patch('backend.data_pack_clone.shutil.copyfile',side_effect=OSError('disk full')):
            with self.assertRaises(DataPackCloneError): self.clone()
        with patch('backend.data_pack_clone.shutil.disk_usage') as usage:
            usage.return_value.free=0
            with self.assertRaises(DataPackCloneError) as caught: self.clone()
            self.assertEqual(caught.exception.status,507)
        self.assertEqual([p.name for p in self.root.iterdir()],['source'])
    def test_cloned_upload_stale_and_active_or_trash_reference(self):
        pack=self.clone()['data_pack']; path=self.root / pack['id'] / 'manifest.json'
        projects=self.root / 'projects'; trash=self.root / 'trash'; projects.mkdir(); trash.mkdir()
        with self.assertRaises(DataPackCloneError):
            guard_clone_upload(pack,path,'0'*64,projects,trash)
        guard_clone_upload(pack,path,pack['manifest_sha256'],projects,trash)
        saved = path.read_bytes()
        path.write_bytes(saved + b'\n')
        with self.assertRaises(DataPackCloneError):
            guard_clone_upload(pack,path,pack['manifest_sha256'],projects,trash)
        path.write_bytes(saved)
        for base in (projects,trash / 'studies'):
            folder=base / 'study'; folder.mkdir(parents=True)
            record=folder / 'project.json'; record.write_text(json.dumps({'data_pack_id':pack['id']}))
            with self.assertRaises(DataPackCloneError) as caught:
                guard_clone_upload(pack,path,pack['manifest_sha256'],projects,trash)
            self.assertEqual(caught.exception.code,'GF_DATA_PACK_REFERENCED')
            record.unlink()
        for base in (projects,trash / 'studies'):
            folder=base / 'revision-only-study' / 'revisions'; folder.mkdir(parents=True)
            record=folder / 'immutable.json'; record.write_text(json.dumps({'data_pack_id':pack['id']}))
            with self.assertRaises(DataPackCloneError) as caught:
                guard_clone_upload(pack,path,pack['manifest_sha256'],projects,trash)
            self.assertEqual(caught.exception.code,'GF_DATA_PACK_REFERENCED')
            record.write_text('[]')
            with self.assertRaises(DataPackCloneError) as caught:
                guard_clone_upload(pack,path,pack['manifest_sha256'],projects,trash)
            self.assertEqual(caught.exception.code,'GF_DATA_PACK_REFERENCE_UNVERIFIABLE')
            record.unlink()
