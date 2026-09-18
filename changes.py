"""Allowlisted configuration snapshots and dashboard action receipts."""
import json
import os
import time
import uuid


def configuration(doc):
    spec = doc.get('spec', {})
    kind = doc.get('kind', '')
    fields = {
        'Service': ('type', 'selector', 'ports', 'externalTrafficPolicy', 'sessionAffinity'),
        'Ingress': ('ingressClassName', 'rules', 'defaultBackend', 'tls'),
        'PersistentVolumeClaim': ('accessModes', 'storageClassName', 'resources', 'volumeMode', 'volumeName'),
        'ResourceQuota': ('hard', 'scopes', 'scopeSelector'),
        'LimitRange': ('limits',),
        'NetworkPolicy': ('podSelector', 'policyTypes', 'ingress', 'egress'),
    }
    if kind in fields:
        return {k: spec.get(k) for k in fields[kind]}
    if kind in ('Domain', 'Cluster') and doc.get('apiVersion', '').startswith('weblogic.oracle/'):
        def server_settings(value):
            result = {k: value.get(k) for k in ('name', 'clusterName', 'serverName', 'replicas', 'image', 'imagePullPolicy', 'serverStartPolicy', 'restartVersion', 'introspectVersion')}
            result['resources'] = value.get('serverPod', {}).get('resources', {})
            result['auxiliaryImages'] = [{'image': x.get('image')} for x in value.get('serverPod', {}).get('auxiliaryImages', [])]
            return result
        result = server_settings(spec)
        result['adminServer'] = server_settings(spec.get('adminServer', {}))
        result['managedServers'] = sorted([server_settings(x) for x in spec.get('managedServers', [])], key=lambda x: x.get('serverName') or '')
        result['clusters'] = sorted([server_settings(x) for x in spec.get('clusters', [])], key=lambda x: x.get('clusterName') or x.get('name') or '')
        return result
    if kind == 'HorizontalPodAutoscaler':
        return {k: spec.get(k) for k in ('minReplicas', 'maxReplicas', 'scaleTargetRef')}
    if kind == 'CronJob':
        result = {k: spec.get(k) for k in ('schedule', 'suspend', 'timeZone', 'concurrencyPolicy')}
        template = spec.get('jobTemplate', {}).get('spec', {}).get('template', {})
    elif kind == 'Pod':
        result, template = {}, {'spec': spec}
    else:
        result, template = {'replicas': spec.get('replicas')}, spec.get('template', {})
    result['containers'] = {}
    for group in ('containers', 'initContainers'):
        for c in template.get('spec', {}).get(group, []):
            result['containers'][group + '/' + c['name']] = {
                'image': c.get('image'),
                'requests': c.get('resources', {}).get('requests', {}),
                'limits': c.get('resources', {}).get('limits', {})}
    result['restartedAt'] = template.get('metadata', {}).get('annotations', {}).get('kubectl.kubernetes.io/restartedAt')
    return result


class Changes:
    def __init__(self, history):
        self.history = history

    def collect_extended(self, namespace):
        resources = ['pods', 'services', 'ingresses', 'persistentvolumeclaims', 'resourcequotas', 'limitranges', 'networkpolicies']
        if os.getenv('DASHBOARD_HISTORY_WEBLOGIC', 'false').lower() == 'true':
            resources += ['domains.weblogic.oracle', 'clusters.weblogic.oracle']
        for resource in resources:
            try:
                docs = self.history.get(['get', resource, '-n', namespace, '-o', 'json'])['items']
                self.compare_extended(namespace, resource, docs)
            except Exception as error:
                # A failed list must never be treated as an empty resource list.
                if resource == 'clusters.weblogic.oracle' and "doesn't have a resource type" in str(error):
                    continue  # Older WebLogic operators use inline clusters in Domain v8.
                self.history.errors.append(namespace + ': changes/' + resource + ': ' + str(error)[:250])

    def compare_extended(self, namespace, resource, docs):
        h = self.history
        current = {d['kind'] + '/' + d['metadata']['name']: {'uid': d['metadata']['uid'], 'config': configuration(d)} for d in docs}
        now = time.time()
        with h.lock:
            folder = h.root / namespace
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / ('baseline-' + resource + '.json')
            previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
            records = []
            if previous is not None:
                for name in sorted(set(previous['resources']) | set(current)):
                    before, after = previous['resources'].get(name), current.get(name)
                    if before != after:
                        records.append(dict(ts=now, source='observed', resource=name, actor=None,
                                            action='created' if before is None else 'removed' if after is None else 'changed',
                                            status='observed', previousObserved=previous['ts'], before=before, after=after))
            h.append(namespace, 'changes', records)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'ts': now, 'resources': current}), encoding='utf-8')
            os.replace(str(temporary), str(path))

    def collect(self, namespace):
        h = self.history
        document = h.get(['get', 'deployments,statefulsets,daemonsets,hpa,cronjobs', '-n', namespace, '-o', 'json'])
        current = {d['kind'] + '/' + d['metadata']['name']: {'uid': d['metadata']['uid'], 'config': configuration(d)} for d in document['items']}
        now = time.time()
        with h.lock:
            folder = h.root / namespace
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / 'configuration-baseline.json'
            previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
            records = []
            if previous is not None:
                for resource in sorted(set(previous['resources']) | set(current)):
                    before, after = previous['resources'].get(resource), current.get(resource)
                    if before == after:
                        continue
                    records.append(dict(ts=now, source='observed', resource=resource, actor=None,
                                        action='created' if before is None else 'removed' if after is None else 'changed',
                                        status='observed', previousObserved=previous['ts'],
                                        before=before, after=after))
            h.append(namespace, 'changes', records)
            temporary = folder / 'configuration-baseline.tmp'
            temporary.write_text(json.dumps({'ts': now, 'resources': current}), encoding='utf-8')
            os.replace(str(temporary), str(path))

    def execute(self, namespace, kind, name, action, actor, command):
        h = self.history
        if not h.enabled or namespace not in h.namespaces:
            return h.run(command), 'Action history disabled for this namespace.'
        # Persist an attempt before mutation so a process crash cannot erase all evidence.
        # Only whitelisted fields are retained, never environment values or whole specs.
        def snapshot():
            try:
                return configuration(h.get(['get', kind, name, '-n', namespace, '-o', 'json']))
            except Exception:
                return None
        receipt = dict(ts=time.time(), id=str(uuid.uuid4()), source='dashboard', actor=actor,
                       resource=kind + '/' + name, action=action, status='attempted', before=snapshot(), after=None)
        try:
            h.append(namespace, 'changes', [receipt])
        except (OSError, RuntimeError, ValueError) as error:
            raise RuntimeError('Action not executed: could not record action history: ' + str(error))
        try:
            output = h.run(command)
        except Exception:
            receipt.update(ts=time.time(), status='failed-or-unknown')
            try:
                h.append(namespace, 'changes', [receipt])
            except Exception:
                pass  # Attempt is retained; never conceal the original command failure.
            raise
        receipt.update(ts=time.time(), status='succeeded', after=snapshot())
        try:
            h.append(namespace, 'changes', [receipt])
            return output, 'Action recorded in Changes.'
        except (OSError, RuntimeError, ValueError):
            return output, 'Action succeeded, but final history write failed; only the attempt is retained.'
