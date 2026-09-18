import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from history import History, quantity, integer_setting


class HistoryTests(unittest.TestCase):
    def test_48_hour_and_custom_time_ranges(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test'}):
            h=History(lambda args: '')
            now=time.time()
            h.append('test','changes',[dict(ts=now-36*3600,resource='Service/old'),dict(ts=now-2*3600,resource='Service/new')])
            self.assertEqual(len(h.query('test',1,'changes')['items']),1)
            self.assertEqual(len(h.query('test',2,'changes')['items']),2)
            result=h.query('test',30,'changes',start=now-40*3600,end=now-30*3600)
            self.assertEqual([row['resource'] for row in result['items']],['Service/old'])
            with self.assertRaisesRegex(ValueError,'custom history period'):
                h.query('test',30,'changes',start=now,end=now-1)

    def test_pod_inventory_survives_log_result_cap(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test'}):
            h=History(lambda args: '')
            h.append('test','logs',[dict(ts=time.time(),pod='busy',container='main',text='line') for _ in range(201)]+[dict(ts=time.time(),pod='deleted-pod',container='sidecar',text='saved')])
            result=h.query('test',7,'logs')
            self.assertEqual(result['pods'],['busy','deleted-pod'])
            self.assertTrue(result['truncated'])
            selected=h.query('test',7,'logs',pod='deleted-pod',container='sidecar')
            self.assertEqual(len(selected['items']),1)
            self.assertEqual(selected['containers'],['sidecar'])

    def test_viewed_logs_are_exact_and_persisted(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test', 'DASHBOARD_HISTORY_ENABLED': 'true', 'DASHBOARD_HISTORY_LOGS': 'true'}):
            h=History(lambda args: '')
            output='2026-09-15 java error\nsecond line\n'
            result=h.save_viewed_logs('test','pod','main',output,True,'1h')
            self.assertTrue(result['saved'])
            self.assertEqual(result['retentionDays'],30)
            rows=History(lambda args: '').query('test',30,'logs')['items']
            self.assertEqual(rows[0]['text'],output)
            self.assertTrue(rows[0]['previous'])
            self.assertFalse(h.save_viewed_logs('other','pod','main',output)['saved'])
            h.max_bytes=1
            self.assertFalse(h.save_viewed_logs('test','pod','main',output)['saved'])
            h.prune()
            self.assertEqual(len(h.query('test',30,'logs')['items']),1)

    def test_empty_legacy_logs_and_namespace_errors(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test'}):
            h=History(lambda args: '')
            h.append('test', 'logs', [dict(ts=time.time(), text=''), dict(ts=time.time(), text='actual log')])
            h.errors=['other/pod: logs: EOF', 'test/pod: logs: EOF']
            result=h.query('test', 7, 'logs')
            self.assertEqual(len(result['items']), 1)
            self.assertEqual(result['errors'], ['test/pod: logs: EOF'])

    def test_application_log_filter_includes_replacement_pods(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test'}):
            h=History(lambda args: '')
            now=time.time();h.append('test','logs',[dict(ts=now,pod='pje-old',application='pje-rs1',container='main',text='old'),dict(ts=now,pod='other-1',application='other',container='main',text='other')])
            rows=h.query('test',7,'logs',application='pje')['items']
            self.assertEqual([row['text'] for row in rows],['old'])

    def test_helm_scientific_notation_with_history_disabled(self):
        with patch.dict(os.environ, {'DASHBOARD_HISTORY_ENABLED': 'false', 'DASHBOARD_HISTORY_MAX_BYTES': '1.073741824e+09'}):
            h = History(lambda args: '')
            self.assertFalse(h.enabled)
            self.assertEqual(h.max_bytes, 1073741824)
            h.start()

    def test_invalid_numeric_settings(self):
        for raw in ('NaN', 'Infinity', '1.2', 'text', '1e100'):
            with patch.dict(os.environ, {'TEST_NUMBER': raw}):
                with self.assertRaisesRegex(ValueError, 'TEST_NUMBER'):
                    integer_setting('TEST_NUMBER', 0)

    def test_quantities_and_missing(self):
        self.assertIsNone(quantity(None))
        self.assertEqual(quantity('250000000n'), 250)
        self.assertEqual(quantity('1Gi', True), 1024)
        self.assertEqual(quantity('1048576', True), 1)

    def test_collection_query_scope_and_retention(self):
        pod = {'metadata': {'name': 'app-1', 'uid': 'uid', 'labels': {'app.kubernetes.io/name': 'app'}},
               'spec': {'containers': [{'name': 'main', 'resources': {}}]},
               'status': {'containerStatuses': [{'name': 'main', 'lastState': {'terminated': {'reason': 'OOMKilled'}}}]}}
        def run(args):
            if '--raw' in args:
                return json.dumps({'items': [{'metadata': {'name': 'app-1'}, 'containers': [{'name': 'main', 'usage': {'cpu': '10m', 'memory': '10Mi'}}]}]})
            return json.dumps({'items': [pod]})
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test'}):
            h = History(run)
            h.collect('test')
            result = h.query('test', 7, 'metrics')['items'][0]
            self.assertEqual(result['peakMemory'], 10)
            self.assertIsNone(result['candidateMemoryLimit'])
            self.assertTrue(any('OOM' in s for s in result['suggestions']))
            with self.assertRaises(ValueError):
                h.query('../test', 7, 'metrics')
            old = Path(folder) / 'test' / '2000-01-01-logs.jsonl'
            old.write_text('{}\n')
            os.utime(old, (1, 1))
            h.prune()
            self.assertFalse(old.exists())
            self.assertEqual(len(h.query('test', 7, 'metrics')['items']), 1)

    def test_metrics_failure_is_not_zero(self):
        def run(args):
            if '--raw' in args:
                raise RuntimeError('metrics unavailable')
            return json.dumps({'items': [{'metadata': {'name': 'p', 'uid': 'u'}, 'spec': {'containers': [{'name': 'c'}]}}]})
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DASHBOARD_HISTORY_PATH': folder, 'DASHBOARD_HISTORY_NAMESPACES': 'test'}):
            h=History(run); h.collect('test')
            self.assertIsNone(h.query('test', 7, 'metrics')['items'][0]['peakMemory'])
            self.assertTrue(h.errors)

if __name__ == '__main__':
    unittest.main()
