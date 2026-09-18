import json
import unittest
from unittest.mock import patch
import server


class ApplicationTests(unittest.TestCase):
    def test_node_describe_and_restricted_fallback(self):
        def run(args):
            if args[0] == 'get':
                return json.dumps({'metadata': {'name': 'worker-1'}})
            return 'Name: worker-1\nConditions: Ready'
        result = self.request('/api/node-describe?node=worker-1', run)
        self.assertIn('Conditions: Ready', result['output'])
        self.assertEqual(result['warning'], '')
        def restricted(args):
            if args[0] == 'describe':
                raise RuntimeError('Forbidden: cannot list pods at cluster scope')
            return run(args)
        result = self.request('/api/node-describe?node=worker-1', restricted)
        self.assertEqual(json.loads(result['output'])['metadata']['name'], 'worker-1')
        self.assertIn('Forbidden', result['warning'])

    def request(self,path,run):
        handler=server.Handler.__new__(server.Handler);handler.path=path;handler.require=lambda: True
        result=[];handler.json=lambda data: result.append(data);handler.api_error=lambda error: self.fail(str(error))
        with patch.object(server,'run_kubectl',run): handler.do_GET()
        return result[0]

    def test_discovery_excludes_secrets_and_revision_is_stable(self):
        def run(args):
            if args[0]=='api-resources': return 'widgets.example.com\nsecrets\npods\n'
            return json.dumps({'items':[{'kind':'Pod','metadata':{'name':'p','resourceVersion':'7'}}]})
        discovery=self.request('/api/resource-discovery?namespace=test',run)
        self.assertEqual(discovery['resources'],['pods','widgets.example.com'])
        revision=self.request('/api/namespace-revision?namespace=test',run)
        self.assertEqual(revision['namespace'],'test')
        self.assertEqual(len(revision['revision']),64)

    def context(self, kind, replica_denied=False):
        workload = {'kind': kind.title(), 'metadata': {'name': 'app', 'uid': 'root'}, 'spec': {}}
        def pod(name, owner):
            return {'kind': 'Pod', 'metadata': {'name': name, 'uid': name, 'ownerReferences': [{'uid': owner}], 'labels': {'app': name}}, 'spec': {}}
        pods = [pod('owned', 'root' if kind == 'domain' else 'job'), pod('unrelated', 'other')]
        def run(args):
            if args[1] in ('domains.weblogic.oracle', 'cronjob'):
                return json.dumps(workload)
            if args[1] == 'pods':
                return json.dumps({'items': pods})
            if args[1] == 'jobs':
                return json.dumps({'items': [{'metadata': {'uid': 'job', 'ownerReferences': [{'uid': 'root'}]}}]})
            if args[1] == 'replicaset':
                if replica_denied:
                    raise RuntimeError('Forbidden')
                return json.dumps({'items': []})
            return '{"items": []}'
        handler = server.Handler.__new__(server.Handler)
        handler.path = '/api/workload-context?namespace=test&kind=' + kind + '&name=app'
        handler.require = lambda: True
        result = []
        handler.json = lambda data: result.append(data)
        handler.api_error = lambda error: self.fail(str(error))
        with patch.object(server, 'run_kubectl', run):
            handler.do_GET()
        self.assertEqual([p['metadata']['name'] for p in result[0]['pods']], ['owned'])
        self.assertIn('Pod/owned', result[0]['relatedResources'])
        self.assertNotIn('Pod/unrelated', result[0]['relatedResources'])
        return result[0]

    def test_domain_owner_mapping(self):
        self.context('domain')

    def test_cronjob_job_pod_mapping(self):
        self.context('cronjob')

    def test_context_survives_missing_replicaset_permission(self):
        result = self.context('domain', replica_denied=True)
        self.assertEqual(result['replicaSets'], [])
        self.assertIn('ServiceAccount', result['warnings'][0])
