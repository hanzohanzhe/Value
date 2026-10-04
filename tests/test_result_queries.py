"""Bounded result adapter checks using existing small scientific fixtures."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.result_queries import query_vre_curtailment_results, FIELDS
from gridform_core.run_bundle import _included
from gridform_core.vre_curtailment_attribution import ATTRIBUTION_METHOD_ID
from tests.test_prompt102_zonal_results_api import _write_fixture


class ResultQueriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'zonal-run'
        self.root.mkdir()
        self.status = {'id': 'zonal-run', 'status': 'completed', 'mode': 'annual', 'run_policy': {'start_year': 2025, 'end_year': 2025, 'periods_per_year': 17520}}
        self.write_status()
        _write_fixture(self.root / 'model-output' / 'market' / 'market.sqlite', 'summary')

    def write_status(self):
        (self.root / 'status.json').write_text(json.dumps(self.status))

    def compact(self):
        database = self.root / 'model-output' / 'market' / 'market.sqlite'
        with sqlite3.connect(database) as conn:
            for table in ('vre_curtailment_period', 'zonal_period_accounting'):
                columns = [r[1] for r in conn.execute('PRAGMA table_info(' + table + ')')]
                projection = ','.join('n' if c == 'period' else "'2025:' || n" if c == 'period_id' else 's.' + c for c in columns)
                conn.execute('WITH RECURSIVE seq(n) AS (SELECT 2 UNION ALL SELECT n+1 FROM seq WHERE n<17519) INSERT INTO ' + table + ' SELECT ' + projection + ' FROM seq JOIN ' + table + ' s ON s.period=n%2')
        annual = query_vre_curtailment_results(self.root, {'source': 'sqlite'})['items'][0]
        artifact = {'schema_version': 'value.vre-curtailment-run-evidence/v1', 'contract_version': 'value.vre-curtailment-attribution/v2', 'attribution_method_id': ATTRIBUTION_METHOD_ID, 'capability_status': 'reconciled', 'matched_counterfactual_proof': {'period_count':17520, 'period_sets_match':True, 'realised_input_hashes_match':True, 'period_identity_set_sha256':'a'*64}, 'counterfactual_realised_input_set_sha256':'b'*64, 'maximum_absolute_period_residual_mwh':0, 'maximum_period_tolerance_mwh':1e-7, 'annual_totals':[annual]}
        path = self.root / 'model-output' / 'network' / 'vre-curtailment-attribution.json'
        path.parent.mkdir()
        path.write_text(json.dumps(artifact))
        return path

    def test_sources_preserve_metric_semantics_and_hash(self):
        self.compact()
        first = query_vre_curtailment_results(self.root, {'source': 'sqlite'})
        second = query_vre_curtailment_results(self.root, {'source': 'compact'})
        self.assertEqual(second['status'], 'reconciled')
        for field in FIELDS:
            self.assertEqual(first['items'][0][field], second['items'][0][field])
        self.assertEqual(len(second['source']['artifact_sha256']), 64)
        self.assertEqual(first['identity']['recorded_run_id'], 'zonal-run')

    def test_window_pagination(self):
        query = {'resolution': 'half_hour', 'year': 2025, 'period_from': 0, 'period_to': 1, 'limit': 1}
        first = query_vre_curtailment_results(self.root, query)
        second = query_vre_curtailment_results(self.root, {**query, 'offset': 1})
        self.assertEqual(first['total'], 2)
        self.assertTrue(first['has_more'])
        self.assertFalse(second['has_more'])
        self.assertEqual([first['items'][0]['period'], second['items'][0]['period']], [0,1])

    def test_compact_missing_dimension_and_invalid_queries(self):
        self.compact()
        for query in ({'source':'compact','resolution':'half_hour','year':2025}, {'period_from':0}, {'limit':0}, {'offset':-1}, {'year':True}, {'year':1.2}, {'unknown':1}, {'limit':None}, {'offset':None}, {'year':0}, {'year':-1}):
            with self.subTest(query=query), self.assertRaises(ValueError):
                query_vre_curtailment_results(self.root, query)

    def test_bad_proof_and_completed_boundary(self):
        path = self.compact()
        payload = json.loads(path.read_text())
        payload['attribution_method_id'] = 'different-method'
        path.write_text(json.dumps(payload))
        response = query_vre_curtailment_results(self.root, {'source':'compact'})
        self.assertEqual(response['status'], 'invalid')
        self.assertEqual(response['items'], [])
        self.status['status'] = 'running'
        self.write_status()
        self.assertEqual(query_vre_curtailment_results(self.root, {})['status'], 'withheld')

    def test_partial_annual_and_identity_mismatch(self):
        result = query_vre_curtailment_results(self.root, {'source': 'sqlite'})
        self.assertEqual(result['status'], 'withheld')
        self.status['id'] = 'other-run'
        self.write_status()
        result = query_vre_curtailment_results(self.root, {'source': 'sqlite', 'resolution': 'half_hour', 'year': 2025})
        self.assertEqual(result['reason_code'], 'attribution_run_identity_mismatch')

    def test_null_counterfactual_rejected(self):
        database = self.root / 'model-output' / 'market' / 'market.sqlite'
        with sqlite3.connect(database) as conn:
            conn.execute("UPDATE vre_curtailment_period SET counterfactual_realised_input_sha256='bad' WHERE period=0")
        result = query_vre_curtailment_results(self.root, {'source': 'sqlite', 'resolution': 'half_hour', 'year': 2025})
        self.assertEqual(result['status'], 'invalid')
        self.assertEqual(result['items'], [])

    def test_missing_year_and_bad_period_cannot_hide_in_annual(self):
        self.compact()
        self.status['run_policy']['end_year'] = 2026
        self.write_status()
        self.assertEqual(query_vre_curtailment_results(self.root, {'source':'sqlite', 'year':2025})['reason_code'], 'vre_curtailment_annual_year_set_invalid')
        self.status['run_policy']['end_year'] = 2025
        self.write_status()
        database = self.root / 'model-output' / 'market' / 'market.sqlite'
        with sqlite3.connect(database) as conn:
            conn.execute('UPDATE vre_curtailment_period SET identity_residual_mwh=1 WHERE period=0')
            conn.execute('UPDATE vre_curtailment_period SET identity_residual_mwh=-1 WHERE period=1')
        result = query_vre_curtailment_results(self.root, {'source':'sqlite'})
        self.assertEqual(result['reason_code'], 'attribution_period_value_invalid')

    def test_missing_metadata_run_not_filled_from_container(self):
        database = self.root / 'model-output' / 'market' / 'market.sqlite'
        with sqlite3.connect(database) as conn:
            conn.execute("DELETE FROM metadata WHERE key='run_id'")
        result = query_vre_curtailment_results(self.root, {'source':'sqlite'})
        self.assertIsNone(result['identity']['recorded_run_id'])
        self.assertEqual(result['status'], 'invalid')

    def test_compact_invalid_proof_and_container_binding(self):
        path = self.compact()
        result = query_vre_curtailment_results(self.root, {'source':'compact'})
        self.assertIsNone(result['identity']['recorded_run_id'])
        self.assertIn('recorded_run_id', result['identity']['missing_fields'])
        data = json.loads(path.read_text())
        data['matched_counterfactual_proof']['period_sets_match'] = False
        path.write_text(json.dumps(data))
        self.assertEqual(query_vre_curtailment_results(self.root, {'source':'compact'})['status'], 'invalid')

    def test_nested_artifact_shape_is_stable_valueerror(self):
        for document, key in ((self.root / 'status.json', 'run_policy'), (self.root / 'model-output' / 'resolved-run.json', 'extensions')):
            document.write_text(json.dumps({**self.status, key:['wrong']}))
            with self.assertRaises(ValueError):
                query_vre_curtailment_results(self.root, {})
            self.write_status()
            if document.name == 'resolved-run.json':
                document.unlink()

    def test_annual_period_bounds_and_negative_gross_components(self):
        self.compact()
        database = self.root / 'model-output' / 'market' / 'market.sqlite'
        with sqlite3.connect(database) as conn:
            for table in ('vre_curtailment_period', 'zonal_period_accounting'):
                conn.execute("UPDATE " + table + " SET period=17520,period_id='2025:17520' WHERE period=0")
        result = query_vre_curtailment_results(self.root, {'source':'sqlite'})
        self.assertEqual(result['status'], 'withheld')
        with sqlite3.connect(database) as conn:
            conn.execute('UPDATE vre_curtailment_period SET forecast_added_curtailment_mwh=-1,forecast_avoided_curtailment_mwh=-1 WHERE period=1')
        result = query_vre_curtailment_results(self.root, {'source':'sqlite','resolution':'half_hour','year':2025})
        self.assertEqual(result['reason_code'], 'attribution_period_value_invalid')

    def test_bundle_keeps_compact_attribution(self):
        self.assertTrue(_included('model-output/network/vre-curtailment-attribution.json', 'compact_results'))

if __name__ == '__main__':
    unittest.main()
