import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from history import History
from changes import configuration


class ChangesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {'DASHBOARD_HISTORY_ENABLED':'true','DASHBOARD_HISTORY_NAMESPACES':'test','DASHBOARD_HISTORY_PATH':self.tmp.name})
        self.env.start()
        self.doc={'kind':'Deployment','metadata':{'name':'app','uid':'abc'},'spec':{'replicas':1,'template':{'spec':{'containers':[{'name':'app','image':'image:1','env':[{'name':'PASSWORD','value':'secret-data'}]}]}}}}
        self.calls=[]
        self.fail=False
        self.history=History(self.kubectl)

    def tearDown(self):
        self.env.stop();self.tmp.cleanup()

    def kubectl(self,args):
        self.calls.append(args)
        if self.fail:
            raise RuntimeError('simulated failure')
        if args[0]=='scale':
            self.doc['spec']['replicas']=2
            return 'scaled'
        return json.dumps({'items':[self.doc]} if ',' in args[1] else self.doc)

    def test_application_scope_exact_match(self):
        self.history.changes.collect('test')
        self.doc['spec']['replicas']=2
        self.history.changes.collect('test')
        self.assertEqual(len(self.history.query('test',7,'changes',resources={'deployment/app'})['items']),1)
        self.assertEqual(self.history.query('test',7,'changes',resources={'deployment/app-other'})['items'],[])
        result=self.history.query('test',7,'changes')
        self.assertEqual(result['items'][0]['namespace'],'test')
        self.history.namespaces.append('other')
        self.assertEqual(self.history.query('other',7,'changes')['items'],[])

    def test_baseline_diff_and_restart(self):
        self.history.changes.collect('test')
        self.assertEqual(self.history.query('test',7,'changes')['items'],[])
        self.doc['spec']['replicas']=2
        # A fresh object reads the persisted baseline.
        History(self.kubectl).changes.collect('test')
        rows=self.history.query('test',7,'changes')['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['before']['config']['replicas'],1)
        self.assertEqual(rows[0]['after']['config']['replicas'],2)
        self.assertIsNone(rows[0]['actor'])
        self.assertNotIn('secret-data',json.dumps(rows))
        self.fail=True
        with self.assertRaises(RuntimeError):
            self.history.changes.collect('test')
        self.assertEqual(len(self.history.query('test',7,'changes')['items']),1)

    def test_action_success_and_before_after(self):
        output,note=self.history.changes.execute('test','deployment','app','scale','operator',['scale','deployment/app'])
        self.assertEqual(output,'scaled')
        rows=self.history.query('test',7,'changes')['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['actor'],'operator')
        self.assertEqual(rows[0]['status'],'succeeded')
        self.assertEqual(rows[0]['before']['replicas'],1)
        self.assertEqual(rows[0]['after']['replicas'],2)

    def test_weblogic_v8_image_and_resource_changes(self):
        domain={'apiVersion':'weblogic.oracle/v8','kind':'Domain','metadata':{'name':'bcws-domain','uid':'domain-uid'},'spec':{'image':'bcws:1','serverPod':{'resources':{'limits':{'memory':'2Gi'}},'env':[{'name':'PASSWORD','value':'must-not-store'}]},'clusters':[{'clusterName':'cluster-1','replicas':2}]}}
        self.history.changes.compare_extended('test','domains.weblogic.oracle',[domain])
        domain['spec']['image']='bcws:2'
        domain['spec']['serverPod']['resources']['limits']['memory']='3Gi'
        self.history.changes.compare_extended('test','domains.weblogic.oracle',[domain])
        rows=self.history.query('test',7,'changes')['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['before']['config']['image'],'bcws:1')
        self.assertEqual(rows[0]['after']['config']['image'],'bcws:2')
        self.assertNotIn('must-not-store',json.dumps(rows))

    def test_service_creation_and_removal_after_baseline(self):
        self.history.changes.compare_extended('test','services',[])
        svc={'kind':'Service','metadata':{'name':'api','uid':'svc-uid'},'spec':{'type':'ClusterIP','ports':[{'port':80,'targetPort':8080}]}}
        self.history.changes.compare_extended('test','services',[svc])
        self.history.changes.compare_extended('test','services',[])
        rows=self.history.query('test',7,'changes')['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['action'],'removed')
        self.assertEqual(rows[0]['occurrenceCount'],2)

    def test_repeated_observations_are_consolidated_per_resource(self):
        self.history.changes.collect('test')
        for replicas in (2, 3, 4):
            self.doc['spec']['replicas']=replicas
            self.history.changes.collect('test')
        rows=self.history.query('test',7,'changes')['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['occurrenceCount'],3)
        self.assertEqual(rows[0]['before']['config']['replicas'],3)
        self.assertEqual(rows[0]['after']['config']['replicas'],4)
        self.assertLessEqual(rows[0]['firstTs'],rows[0]['ts'])

    def test_extended_failure_keeps_baseline(self):
        self.history.changes.compare_extended('test','pods',[dict(self.doc,kind='Pod')])
        self.fail=True
        self.history.changes.collect_extended('test')
        self.assertEqual(self.history.query('test',7,'changes')['items'],[])
        self.assertTrue(any('changes/pods' in e for e in self.history.errors))

    def test_failed_command_and_full_store(self):
        self.fail=True
        with self.assertRaises(RuntimeError):
            self.history.changes.execute('test','deployment','app','scale','operator',['scale','deployment/app'])
        self.assertEqual(self.history.query('test',7,'changes')['items'][0]['status'],'failed-or-unknown')
        self.fail=False
        self.history.max_bytes=1
        self.calls=[]
        with self.assertRaisesRegex(RuntimeError,'Action not executed'):
            self.history.changes.execute('test','deployment','app','scale','operator',['scale','deployment/app'])
        self.assertFalse(any(c[0]=='scale' for c in self.calls))

if __name__=='__main__':
    unittest.main()
