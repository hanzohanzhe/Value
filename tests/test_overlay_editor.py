"""Only the isolated overlay edit/validate/promote lifecycle; no model execution."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from gridform_core.data_workbench.overlay_editor import OverlayEditor, MAX_UPLOAD
from gridform_core.zonal_contracts import load_zonal_network_pack

SOURCE = Path(__file__).resolve().parents[1] / 'data-packs/value-101-network-v1'


class OverlayEditorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.source = self.state / 'installed-packs/value-101-network-v1'
        shutil.copytree(SOURCE, self.source)
        self.editor = OverlayEditor(self.state)

    def tearDown(self): self.temporary.cleanup()

    def clone(self):
        row = self.editor.overlays()['overlays'][0]
        self.assertEqual(row['installation_origin'], 'local_copy')
        result = self.editor.clone(row['pack_id'], {'schema_version': 'value.network-overlay-clone/v1',
            'source_manifest_sha256': row['source_manifest_sha256'], 'new_pack_id': 'edited-network-v1', 'name': 'Edited network'})
        manifest = json.loads((self.state / 'candidates' / result['directory_id'] / 'pack/manifest.json').read_text())
        self.assertIs(manifest['scientific_baseline_eligible'], False)
        self.assertEqual(manifest['scientific_validation_status'], 'not_evaluated')
        self.assertNotIn('owner_approval', manifest)
        self.assertIn('source_qualification', manifest['overlay_editor_provenance'])
        return result

    def test_independent_edit_review_and_promote(self):
        before = {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        current = self.clone()
        role = 'value.zonal.zones'
        manifest = json.loads((self.source / 'manifest.json').read_text())
        payload = json.loads((self.source / manifest['bindings'][role]['uri']).read_text())
        payload['zones'][0]['display_name'] = 'Edited teaching zone'
        raw = json.dumps(payload).encode()
        changed = self.editor.upload(current['directory_id'], role, raw, 'zones.json', current['candidate_id'])
        self.assertNotEqual(current['candidate_id'], changed['candidate_id'])
        self.assertIsNone(changed['validation'])
        candidate_pack = self.state / 'candidates' / changed['directory_id'] / 'pack'
        edited_manifest = json.loads((candidate_pack / 'manifest.json').read_text())
        replacement = edited_manifest['bindings'][role]
        self.assertEqual(replacement['licence'], 'unknown')
        self.assertTrue(replacement['source_url'].startswith('local-upload://'))
        self.assertEqual(replacement['redistribution_class'], 'unresolved_local_upload')
        self.assertNotIn('copyright_affirmer', edited_manifest)
        old_binding = edited_manifest['overlay_editor_provenance']['replaced_binding_history'][role][0]
        self.assertEqual(old_binding['licence'], 'CC0-1.0')
        self.assertTrue(old_binding['source_url'].startswith('generated://'))
        rights = json.loads((candidate_pack / 'RIGHTS.json').read_text())
        self.assertEqual(rights['replacement_roles'], [role])
        self.assertIn('does not establish redistribution permission', rights['note'])
        self.assertTrue(all((candidate_pack / path).is_file() for path in rights['parent_rights_records']))
        unchanged = next(key for key in manifest['bindings'] if key != role)
        self.assertEqual(edited_manifest['bindings'][unchanged], manifest['bindings'][unchanged])

        downloaded, filename, media = self.editor.download_role(changed['directory_id'], role, changed['candidate_id'])
        self.assertEqual(downloaded, raw)
        self.assertEqual((filename, media), ('zones.json', 'application/json'))
        with self.assertRaisesRegex(ValueError, 'Stale'):
            self.editor.validate(changed['directory_id'], current['candidate_id'])
        report = self.editor.validate(changed['directory_id'], changed['candidate_id'])
        self.assertEqual(report['errors'], [])
        receipt = self.editor.promote(changed['directory_id'], {'schema_version': 'value.data-promotion-request/v1', 'candidate_id': changed['candidate_id'], 'version': '1.0.0', 'reviewer': 'Test reviewer', 'accepted_waivers': []})
        self.assertEqual(receipt['network_pack_id'], 'edited-network-v1')
        self.assertEqual(receipt['version'], '1.0.0')
        load_zonal_network_pack(self.state / 'installed-packs/edited-network-v1', topology_policy='enforce')
        after = {p.relative_to(self.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaisesRegex(ValueError, 'already installed'):
            self.editor.promote(changed['directory_id'], {'schema_version': 'value.data-promotion-request/v1', 'candidate_id': changed['candidate_id'], 'version': '1.0.0', 'reviewer': 'Test reviewer', 'accepted_waivers': []})

    def test_cross_role_reference_blocks_and_source_identity_pinned(self):
        current = self.clone(); role = 'value.zonal.corridors'
        manifest = json.loads((self.source / 'manifest.json').read_text())
        payload = json.loads((self.source / manifest['bindings'][role]['uri']).read_text())
        payload['corridors'][0]['to_zone_id'] = 'missing-zone'
        changed = self.editor.upload(current['directory_id'], role, json.dumps(payload).encode(), 'corridors.json', current['candidate_id'])
        report = self.editor.validate(changed['directory_id'], changed['candidate_id'])
        self.assertEqual(report['status'], 'blocked')
        self.assertTrue(any('dangling' in error for error in report['errors']))
        with self.assertRaisesRegex(ValueError, 'blocked'):
            self.editor.promote(changed['directory_id'], {'schema_version': 'value.data-promotion-request/v1', 'candidate_id': changed['candidate_id'], 'version': '1.0.0', 'reviewer': 'Test reviewer', 'accepted_waivers': []})
        self.assertFalse((self.state / 'installed-packs/edited-network-v1').exists())
        (self.source / 'manifest.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Source overlay changed'):
            self.editor.validate(changed['directory_id'], changed['candidate_id'])

    def test_upload_boundaries_and_stale_clone(self):
        row = self.editor.overlays()['overlays'][0]
        with self.assertRaisesRegex(ValueError, 'Source manifest changed'):
            self.editor.clone(row['pack_id'], {'schema_version': 'value.network-overlay-clone/v1', 'source_manifest_sha256': '0' * 64, 'new_pack_id': 'edited-network-v1', 'name': 'Edited'})
        current = self.clone()
        for role, raw, filename in [('not-declared', b'{}', 'data.json'), ('value.zonal.zones', b'{}', '../data.json'), ('value.zonal.zones', b'x' * (MAX_UPLOAD + 1), 'data.json')]:
            with self.assertRaises(ValueError): self.editor.upload(current['directory_id'], role, raw, filename, current['candidate_id'])
        self.assertEqual(self.editor.detail(current['directory_id'])['candidate_id'], current['candidate_id'])


if __name__ == '__main__': unittest.main()
