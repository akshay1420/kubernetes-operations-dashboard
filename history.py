"""Optional single-writer, PVC-backed JSONL history. No external database."""
import datetime
from decimal import Decimal, InvalidOperation
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from changes import Changes


def integer_setting(name, default):
    """Accept exact integral Helm values, including scientific notation."""
    raw = os.getenv(name, str(default))
    try:
        number = Decimal(raw)
        if not number.is_finite() or number != number.to_integral_value() or abs(number) > 2**63 - 1:
            raise ValueError()
        return int(number)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError(name + ' must be a finite whole number; received ' + repr(raw))


def quantity(value, memory=False):
    if value is None:
        return None
    match = re.fullmatch(r'([0-9.]+)([a-zA-Z]*)', str(value))
    if not match:
        return None
    n, unit = float(match[1]), match[2]
    factors = ({'': 1 / 1048576, 'Ki': 1 / 1024, 'Mi': 1, 'Gi': 1024,
                'Ti': 1048576, 'k': 1000 / 1048576, 'M': 1000000 / 1048576,
                'G': 1000000000 / 1048576} if memory else {'': 1000, 'm': 1, 'u': .001, 'n': .000001})
    return n * factors[unit] if unit in factors else None


class History:
    def __init__(self, run):
        self.run = run
        self.enabled = os.getenv('DASHBOARD_HISTORY_ENABLED', 'false') == 'true'
        self.root = Path(os.getenv('DASHBOARD_HISTORY_PATH', '/data/history')).resolve()
        self.namespaces = [s.strip() for s in os.getenv('DASHBOARD_HISTORY_NAMESPACES', '').split(',') if s.strip()]
        if any(not re.fullmatch(r'[a-z0-9][a-z0-9-]*', s) for s in self.namespaces):
            raise ValueError('Invalid history namespace')
        self.interval = max(60, integer_setting('DASHBOARD_HISTORY_INTERVAL', 300))
        self.retention = max(1, min(90, integer_setting('DASHBOARD_HISTORY_RETENTION', 30)))
        self.max_bytes = max(1048576, integer_setting('DASHBOARD_HISTORY_MAX_BYTES', 1073741824))
        self.logs = os.getenv('DASHBOARD_HISTORY_LOGS', 'false') == 'true'
        self.errors = []
        self.last = None
        self.lock = threading.RLock()
        self.changes = Changes(self)

    def start(self):
        if self.enabled:
            if not self.namespaces:
                raise ValueError('History requires explicit namespaces')
            self.root.mkdir(parents=True, exist_ok=True)
            threading.Thread(target=self.loop, daemon=True).start()

    def get(self, args):
        return json.loads(self.run(args))

    def append(self, namespace, kind, rows):
        if not rows:
            return
        if namespace not in self.namespaces:
            raise ValueError('Namespace is not configured for history collection')
        with self.lock:
            folder = self.root / namespace
            folder.mkdir(parents=True, exist_ok=True)
            content = ''.join(json.dumps(row, ensure_ascii=True) + '\n' for row in rows)
            total = sum(p.stat().st_size for p in self.root.glob('*/*.jsonl'))
            if total + len(content.encode('utf-8')) > self.max_bytes:
                raise RuntimeError('History storage budget reached. Increase history.maxBytes and PVC capacity; existing records are retained until expiry.')
            path = folder / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d') + '-' + kind + '.jsonl')
            with path.open('a', encoding='utf-8') as out:
                out.write(content)

    def save_viewed_logs(self, namespace, pod, container, output, previous=False, since='15m'):
        if not self.enabled or not self.logs or namespace not in self.namespaces:
            return dict(saved=False, message='Not saved: enable history and log collection for this namespace.')
        if not output.strip():
            return dict(saved=False, message='No log lines returned; nothing to save.')
        try:
            self.append(namespace, 'logs', [dict(ts=time.time(), pod=pod, container=container or '(default)',
                        application=pod, text=output, source='Pod Logs button', previous=previous, since=since)])
            return dict(saved=True, message='Saved to PVC history for ' + str(self.retention) + ' days.', retentionDays=self.retention)
        except (OSError, RuntimeError, ValueError) as error:
            return dict(saved=False, message='Logs loaded but NOT saved: ' + str(error))

    def collect(self, namespace):
        pods = self.get(['get', 'pods', '-n', namespace, '-o', 'json'])['items']
        usage = {}
        try:
            metrics = self.get(['get', '--raw', '/apis/metrics.k8s.io/v1beta1/namespaces/' + namespace + '/pods'])
            for pod in metrics['items']:
                for c in pod['containers']:
                    usage[(pod['metadata']['name'], c['name'])] = c['usage']
        except Exception as error:
            self.errors.append(namespace + ': metrics: ' + str(error)[:300])
        now = time.time()
        rows = []
        for pod in pods:
            meta = pod['metadata']
            owner = next((x for x in meta.get('ownerReferences', []) if x.get('controller')), {})
            application = meta.get('labels', {}).get('app.kubernetes.io/name') or owner.get('name') or meta['name']
            statuses = {s['name']: s for s in pod.get('status', {}).get('containerStatuses', [])}
            for c in pod['spec'].get('containers', []):
                u = usage.get((meta['name'], c['name']), {})
                resources = c.get('resources', {})
                status = statuses.get(c['name'], {})
                termination = status.get('lastState', {}).get('terminated', {})
                rows.append(dict(ts=now, pod=meta['name'], uid=meta['uid'], application=application,
                                 container=c['name'], cpu=quantity(u.get('cpu')), memory=quantity(u.get('memory'), True),
                                 cpuRequest=quantity(resources.get('requests', {}).get('cpu')),
                                 cpuLimit=quantity(resources.get('limits', {}).get('cpu')),
                                 memoryRequest=quantity(resources.get('requests', {}).get('memory'), True),
                                 memoryLimit=quantity(resources.get('limits', {}).get('memory'), True),
                                 restarts=status.get('restartCount', 0), reason=termination.get('reason', ''),
                                 phase=pod.get('status', {}).get('phase', 'Unknown')))
                if self.logs:
                    try:
                        output = self.run(['logs', meta['name'], '-n', namespace, '-c', c['name'],
                                           '--timestamps=true', '--since=' + str(self.interval) + 's', '--limit-bytes=262144'])
                        if output.strip():
                            self.append(namespace, 'logs', [dict(ts=now, pod=meta['name'], container=c['name'],
                                        application=application, text=output, possiblyTruncated=len(output.encode()) >= 262144)])
                    except Exception as error:
                        self.errors.append(namespace + '/' + meta['name'] + ': logs: ' + str(error)[:200])
        self.append(namespace, 'metrics', rows)

    def prune(self):
        with self.lock:
            self._prune_expired()

    def _prune_expired(self):
        files = sorted(self.root.glob('*/*.jsonl'), key=lambda p: p.stat().st_mtime)
        cutoff = time.time() - self.retention * 86400
        total = sum(p.stat().st_size for p in files)
        for path in files:
            if path.stat().st_mtime < cutoff:
                total -= path.stat().st_size
                path.unlink()

    def loop(self):
        while True:
            started = time.time()
            self.errors = []
            for namespace in self.namespaces:
                self.changes.collect_extended(namespace)
                try:
                    self.changes.collect(namespace)
                except Exception as error:
                    self.errors.append(namespace + ': configuration history: ' + str(error)[:300])
                try:
                    self.collect(namespace)
                except Exception as error:
                    self.errors.append(namespace + ': ' + str(error)[:300])
            try:
                self.prune()
            except Exception as error:
                self.errors.append('Retention: ' + str(error)[:300])
            self.last = time.time()
            time.sleep(max(1, self.interval - (time.time() - started)))

    def query(self, namespace, days, kind, search='', pod='', container='', resources=None, start=None, end=None, application=''):
        if namespace not in self.namespaces:
            raise ValueError('Namespace is not configured for history collection')
        if kind not in ('metrics', 'logs', 'changes') or days not in (1, 2, 7, 30):
            raise ValueError('Invalid history query')
        now = time.time()
        cutoff, until = now - days * 86400, now
        if start is not None or end is not None:
            if start is None or end is None or start >= end or end > now + 300 or start < now - self.retention * 86400:
                raise ValueError('Invalid custom history period')
            cutoff, until = start, end
        rows = []
        pod_names, container_names = set(), set()
        truncated = False
        for path in sorted((self.root / namespace).glob('*-' + kind + '.jsonl'), reverse=True):
            if path.stat().st_mtime < cutoff:
                continue
            with path.open(encoding='utf-8') as source:
                for line in source:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue  # An in-flight final line is retried on the next read.
                    if kind == 'logs' and not str(row.get('text', '')).strip():
                        continue  # Ignore empty snapshots written by earlier versions.
                    if row['ts'] < cutoff or row['ts'] > until:
                        continue
                    if application and not (row.get('application', '') == application or row.get('application', '').startswith(application + '-') or row.get('pod', '').startswith(application + '-')):
                        continue
                    if kind == 'logs':
                        pod_names.add(row.get('pod', ''))
                        if not pod or row.get('pod') == pod:
                            container_names.add(row.get('container', ''))
                    if pod and row.get('pod') != pod:
                        continue
                    if container and row.get('container') != container:
                        continue
                    if kind == 'changes' and resources is not None and str(row.get('resource', '')).lower() not in resources:
                        continue
                    if row['ts'] >= cutoff and search.lower() in (row.get('pod', '') + ' ' + row.get('application', '') + ' ' + row.get('text', '') + ' ' + row.get('resource', '') + ' ' + str(row.get('actor') or '')).lower():
                        if kind == 'logs' and len(rows) >= 200:
                            truncated = True
                            continue
                        rows.append(row)
                        if kind != 'logs' and len(rows) >= 200000:
                            truncated = True
                            break
            if truncated and kind != 'logs':
                break
        rows.sort(key=lambda r: r['ts'])
        scoped_errors = [e for e in self.errors if e.startswith(namespace + ':') or e.startswith(namespace + '/') or e.startswith('Retention:')]
        result = dict(namespace=namespace, rangeStart=cutoff, rangeEnd=until, enabled=self.enabled, lastCollection=self.last, errors=scoped_errors[:20], interval=self.interval,
                      retentionDays=self.retention, logsEnabled=self.logs, truncated=truncated)
        if kind == 'changes':
            rows = [dict(row, namespace=namespace) for row in rows]
            latest = {}
            observed = {}
            for row in rows:
                if row.get('id'):
                    latest[row['id']] = row
                else:
                    key = (row.get('resource'), row.get('source', 'observed'))
                    if key not in observed:
                        row['firstTs'] = row['ts']
                        row['occurrenceCount'] = 1
                        observed[key] = row
                    else:
                        first = observed[key]
                        row['firstTs'] = first['firstTs']
                        row['occurrenceCount'] = first['occurrenceCount'] + 1
                        observed[key] = row
            combined = list(observed.values()) + list(latest.values())
            result['items'] = sorted(combined, key=lambda r: r['ts'], reverse=True)[:500]
            result['rawObservedCount'] = sum(row.get('occurrenceCount', 1) for row in observed.values())
            result['truncated'] = truncated or len(combined) > 500
            result['baselineExists'] = (self.root / namespace / 'configuration-baseline.json').exists()
            return result
        if kind == 'logs':
            result['pods'] = sorted(pod_names - {''})
            result['containers'] = sorted(container_names - {''})
            result['items'] = rows
            return result
        groups = {}
        for row in rows:
            groups.setdefault((row['application'], row['container']), []).append(row)
        items = []
        for (app, container), samples in groups.items():
            latest = samples[-1]
            mem = sorted(s['memory'] for s in samples if s['memory'] is not None)
            cpu = sorted(s['cpu'] for s in samples if s['cpu'] is not None)
            span = (samples[-1]['ts'] - samples[0]['ts']) / 86400
            tips = []
            if any(s['reason'] == 'OOMKilled' for s in samples):
                tips.append('OOM termination observed. Review memory limit, previous logs and JVM native/heap settings. Sampled usage may miss the pre-crash peak.')
            if latest['memoryLimit'] is None:
                tips.append('Memory limit is unset. Review the candidate against batch peaks and application requirements.')
            if latest['cpuRequest'] is None or latest['memoryRequest'] is None:
                tips.append('A resource request is unset. Define requests after reviewing representative demand.')
            if span < 7:
                tips.append('Less than 7 days observed: insufficient history for a sizing recommendation.')
            ticks = sorted(set(int(s['ts'] // self.interval) for s in samples if s['memory'] is not None))
            coverage = min(1, len(ticks) / max(1, span * 86400 / self.interval))
            if coverage < .8:
                tips.append('More than 20% of expected collection intervals lack memory samples; sizing is withheld.')
            candidate = math.ceil(max(mem) * 1.3) if mem and span >= 7 and coverage >= .8 and not truncated else None
            items.append(dict(application=app, container=container, samples=len(samples), metricSamples=len(mem),
                              observedDays=round(span, 2), coveragePercent=round(coverage * 100), first=samples[0]['ts'], last=samples[-1]['ts'],
                              peakMemory=max(mem) if mem else None, p95Memory=mem[math.ceil(len(mem)*.95)-1] if mem else None,
                              peakCpu=max(cpu) if cpu else None, candidateMemoryLimit=candidate,
                              suggestions=tips, confidence='Review required; sampled data, gaps and workload changes may affect sizing'))
        result['items'] = items
        return result
