"""Minimal, dependency-free Kubernetes operations dashboard.

Run this only on a trusted host that has kubectl and an approved kubeconfig.
The browser never receives kubeconfig credentials.
"""
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
from http.cookies import SimpleCookie
import base64
import io
import hashlib
import hmac
import json
import os
import posixpath
import subprocess
import time
import zipfile
from history import History

ROOT = Path(__file__).parent
HOST = os.environ.get("K8S_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("K8S_DASHBOARD_PORT", "8787"))
KUBECTL = os.environ.get("KUBECTL", "kubectl")
REALTIME_CONFIG = {
    "refreshSeconds": int(os.environ.get("DASHBOARD_REFRESH_SECONDS", "30")),
    "nodeCpuWarning": int(os.environ.get("DASHBOARD_NODE_CPU_WARNING", "85")),
    "nodeMemoryWarning": int(os.environ.get("DASHBOARD_NODE_MEMORY_WARNING", "85")),
    "podRestartWarning": int(os.environ.get("DASHBOARD_POD_RESTART_WARNING", "5")),
    "pendingPodWarningSeconds": int(os.environ.get("DASHBOARD_PENDING_WARNING_SECONDS", "600")),
    "scaleEnabled": os.environ.get("DASHBOARD_SCALE_ENABLED", "false").lower() == "true",
    "cronJobSuspendEnabled": os.environ.get("DASHBOARD_CRONJOB_SUSPEND_ENABLED", "false").lower() == "true",
    "cronJobEditEnabled": os.environ.get("DASHBOARD_CRONJOB_EDIT_ENABLED", "false").lower() == "true",
    "hpaEditEnabled": os.environ.get("DASHBOARD_HPA_EDIT_ENABLED", "false").lower() == "true",
}
AUTH_REQUIRED = os.environ.get("DASHBOARD_AUTH_REQUIRED", "false").lower() == "true"
SCALE_ENABLED = os.environ.get("DASHBOARD_SCALE_ENABLED", "false").lower() == "true"
CRONJOB_SUSPEND_ENABLED = os.environ.get("DASHBOARD_CRONJOB_SUSPEND_ENABLED", "false").lower() == "true"
CRONJOB_EDIT_ENABLED = os.environ.get("DASHBOARD_CRONJOB_EDIT_ENABLED", "false").lower() == "true"
HPA_EDIT_ENABLED = os.environ.get("DASHBOARD_HPA_EDIT_ENABLED", "false").lower() == "true"

def cron_schedule(value):
    """Permit normal CronJob schedule characters, while keeping input bounded."""
    text = str(value or "").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789*/,-? #@"
    if not text or len(text) > 200 or any(char not in allowed for char in text):
        raise ValueError("Invalid CronJob schedule")
    return text
AUTH_FILE = os.environ.get("DASHBOARD_AUTH_FILE", "/etc/kubernetes-dashboard-auth/users.json")
SESSION_SECRET = os.environ.get("DASHBOARD_SESSION_SECRET", "")

def users():
    try:
        with open(AUTH_FILE) as source:
            return {u["username"]: u for u in json.load(source).get("users", [])}
    except (OSError, ValueError, KeyError):
        return {}

def password_valid(password, encoded):
    """Check a PBKDF2 record: pbkdf2_sha256$iterations$salthex$hashhex."""
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def sign_session(username, role, expires):
    message = "%s|%s|%s" % (username, role, expires)
    return hmac.new(SESSION_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

# ThreadingHTTPServer was added in Python 3.7.  The jump host may still run
# Python 3.6, so use this equivalent implementation for broad compatibility.
class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def run_kubectl(args):
    """Run an argument list only: never invoke a shell with browser input."""
    command = [KUBECTL, *args]
    try:
        # capture_output= was added in Python 3.7; spell it out for 3.6.
        result = subprocess.run(
            command, universal_newlines=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60
        )
    except FileNotFoundError:
        raise RuntimeError("kubectl is not installed or not in PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError("kubectl timed out")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "kubectl command failed")
    return result.stdout

HISTORY = History(run_kubectl)

def value(params, name, required=True):
    item = params.get(name, [""])[0].strip()
    if required and not item:
        raise ValueError("Missing " + name)
    # Resource identifiers received from the UI must be simple Kubernetes names.
    if item and any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in item.lower()):
        raise ValueError("Invalid " + name)
    return item

def top_rows(args, columns):
    """Convert stable `kubectl top --no-headers` output to JSON."""
    rows = []
    for line in run_kubectl(args).splitlines():
        parts = line.split()
        if len(parts) >= len(columns):
            rows.append(dict(zip(columns, parts)))
    return rows

def top_container_rows(namespace):
    """Return current Metrics API values keyed by (pod, container), if available."""
    try:
        output = run_kubectl(["top", "pod", "-n", namespace, "--containers", "--no-headers"])
    except RuntimeError:
        return {}, False
    metrics = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            metrics[(parts[0], parts[1])] = {"cpu": parts[2], "memory": parts[3]}
    return metrics, True

def labels_match(selector, labels):
    """Return True when every Service selector label is present on a Pod."""
    selector, labels = selector or {}, labels or {}
    return bool(selector) and all(labels.get(key) == val for key, val in selector.items())

def ingress_routes(ingresses, service_name):
    """Extract only the HTTP routes which target a selected Service."""
    routes = []
    for ingress in ingresses:
        for rule in ingress.get("spec", {}).get("rules", []) or []:
            host = rule.get("host", "*")
            for path in rule.get("http", {}).get("paths", []) or []:
                backend = path.get("backend", {}).get("service", {})
                if backend.get("name") == service_name:
                    routes.append({"host": host, "path": path.get("path", "/")})
    return routes

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # The UI is deployed as a single image; never let a browser retain old
        # JavaScript after a rollout.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def translate_path(self, path):
        """Python 3.6-compatible equivalent of the directory= handler option."""
        clean = posixpath.normpath(unquote(urlparse(path).path))
        result = str(ROOT)
        for part in clean.split("/"):
            if not part or part in (os.curdir, os.pardir) or os.path.dirname(part):
                continue
            result = os.path.join(result, part)
        return result

    def principal(self):
        if not AUTH_REQUIRED: return {"username": "local", "role": "write"}
        try:
            cookies = SimpleCookie(self.headers.get("Cookie", ""))
            username, role, expires, signature = cookies["kubernetes_operations_dashboard"].value.split("|", 3)
            if int(expires) < time.time() or not hmac.compare_digest(signature, sign_session(username, role, expires)):
                return None
            record = users().get(username)
            return {"username": username, "role": role} if record and record.get("role") == role else None
        except (KeyError, ValueError):
            return None

    def require(self, write=False):
        current = self.principal()
        if not current: return None
        return current if not write or current["role"] in {"write", "admin"} else None

    def json(self, data, status=200, cookie=None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie: self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def binary(self, body, filename, content_type="application/octet-stream"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
        self.end_headers()
        self.wfile.write(body)

    def api_error(self, err, status=400):
        self.json({"error": str(err)}, status)

    def do_GET(self):
        parsed = urlparse(self.path)
        public = {"/login.html", "/login.js", "/styles.css"}
        if parsed.path == "/api/me":
            current = self.require()
            return self.json({"username": current["username"], "role": current["role"]} if current else {"error": "Unauthorized"}, 200 if current else 401)
        if parsed.path == "/api/config":
            return self.json(REALTIME_CONFIG)
        if parsed.path == "/api/time":
            return self.json({"epoch": time.time(), "timezone": time.tzname[0]})
        if parsed.path not in public and not self.require():
            if parsed.path.startswith("/api/"): return self.api_error("Unauthorized", 401)
            self.send_response(302); self.send_header("Location", "/login.html"); self.end_headers(); return
        if not parsed.path.startswith("/api/"):
            return super().do_GET()
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/history":
                namespace = value(params, "namespace")
                # Recheck current access before returning retained data.
                run_kubectl(["get", "pods", "-n", namespace, "-o", "name"])
                self.json(HISTORY.query(namespace, int(value(params, "days", False) or "7"),
                                        value(params, "kind", False) or "metrics", value(params, "search", False), value(params, "pod", False), value(params, "container", False)))
            elif parsed.path == "/api/namespaces":
                raw = run_kubectl(["get", "namespaces", "-o", "json"])
                self.json(json.loads(raw))
            elif parsed.path == "/api/nodes":
                self.json(json.loads(run_kubectl(["get", "nodes", "-o", "json"])))
            elif parsed.path == "/api/node-metrics":
                self.json({"items": top_rows(["top", "nodes", "--no-headers"], ["name", "cpu", "cpuPercent", "memory", "memoryPercent"])})
            elif parsed.path == "/api/workloads":
                namespace = value(params, "namespace")
                self.json(json.loads(run_kubectl(["get", "deployments,statefulsets,daemonsets", "-n", namespace, "-o", "json"])))
            elif parsed.path == "/api/pods":
                namespace = value(params, "namespace")
                self.json(json.loads(run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])))
            elif parsed.path == "/api/pod-detail":
                namespace, pod = value(params, "namespace"), value(params, "pod")
                self.json(json.loads(run_kubectl(["get", "pod", pod, "-n", namespace, "-o", "json"])))
            elif parsed.path == "/api/pod-describe":
                namespace, pod = value(params, "namespace"), value(params, "pod")
                self.json({"output": run_kubectl(["describe", "pod", pod, "-n", namespace])})
            elif parsed.path == "/api/resource-describe":
                namespace, kind, name = value(params, "namespace"), value(params, "kind"), value(params, "name")
                allowed = {"hpa", "service", "ingress", "pvc", "job", "cronjob", "resourcequota", "limitrange"}
                if kind not in allowed:
                    raise ValueError("Unsupported resource kind")
                self.json({"output": run_kubectl(["describe", kind, name, "-n", namespace])})
            elif parsed.path == "/api/pod-events":
                namespace, pod = value(params, "namespace"), value(params, "pod")
                self.json(json.loads(run_kubectl(["get", "events", "-n", namespace, "--field-selector=involvedObject.name=" + pod, "--sort-by=.lastTimestamp", "-o", "json"])))
            elif parsed.path == "/api/workload-detail":
                namespace, kind, name = value(params, "namespace"), value(params, "kind"), value(params, "name")
                if kind not in {"deployment", "statefulset", "daemonset"}:
                    raise ValueError("Unsupported workload kind")
                self.json(json.loads(run_kubectl(["get", kind, name, "-n", namespace, "-o", "json"])))
            elif parsed.path == "/api/workload-context":
                namespace, kind, name = value(params, "namespace"), value(params, "kind"), value(params, "name")
                if kind not in {"deployment", "statefulset", "daemonset"}:
                    raise ValueError("Unsupported workload kind")
                workload = json.loads(run_kubectl(["get", kind, name, "-n", namespace, "-o", "json"]))
                pod_selector = workload.get("spec", {}).get("selector", {}).get("matchLabels", {})
                all_pods = json.loads(run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])).get("items", [])
                pods = [pod for pod in all_pods if labels_match(pod_selector, pod.get("metadata", {}).get("labels", {}))]
                all_services = json.loads(run_kubectl(["get", "service", "-n", namespace, "-o", "json"])).get("items", [])
                services = [service for service in all_services if any(labels_match(service.get("spec", {}).get("selector", {}), pod.get("metadata", {}).get("labels", {})) for pod in pods)]
                all_ingresses = json.loads(run_kubectl(["get", "ingress", "-n", namespace, "-o", "json"])).get("items", [])
                all_hpas = json.loads(run_kubectl(["get", "hpa", "-n", namespace, "-o", "json"])).get("items", [])
                all_endpoint_slices = json.loads(run_kubectl(["get", "endpointslice", "-n", namespace, "-o", "json"])).get("items", [])
                selected_services = []
                for service in services:
                    service_name = service.get("metadata", {}).get("name")
                    endpoint_slices = [item for item in all_endpoint_slices if item.get("metadata", {}).get("labels", {}).get("kubernetes.io/service-name") == service_name]
                    selected_services.append({
                        "name": service_name,
                        "type": service.get("spec", {}).get("type", "ClusterIP"),
                        "clusterIP": service.get("spec", {}).get("clusterIP", "—"),
                        "ports": service.get("spec", {}).get("ports", []),
                        "routes": ingress_routes(all_ingresses, service_name),
                        "endpointCount": sum(len(item.get("endpoints", [])) for item in endpoint_slices),
                        "readyEndpoints": sum(sum(1 for endpoint in item.get("endpoints", []) if endpoint.get("conditions", {}).get("ready") is not False) for item in endpoint_slices)
                    })
                hpas = [item for item in all_hpas if item.get("spec", {}).get("scaleTargetRef", {}).get("kind", "").lower() == kind and item.get("spec", {}).get("scaleTargetRef", {}).get("name") == name]
                self.json({"workload": workload, "pods": pods, "services": selected_services, "hpas": hpas})
            elif parsed.path == "/api/workload-diagnostics":
                namespace, kind, name = value(params, "namespace"), value(params, "kind"), value(params, "name")
                if kind not in {"deployment", "statefulset", "daemonset"}:
                    raise ValueError("Unsupported workload kind")
                workload = json.loads(run_kubectl(["get", kind, name, "-n", namespace, "-o", "json"]))
                selector = workload.get("spec", {}).get("selector", {}).get("matchLabels", {})
                all_pods = json.loads(run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])).get("items", [])
                pods = [pod for pod in all_pods if labels_match(selector, pod.get("metadata", {}).get("labels", {}))]
                events = json.loads(run_kubectl(["get", "events", "-n", namespace, "--field-selector=involvedObject.name=" + name, "--sort-by=.lastTimestamp", "-o", "json"]))
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                    bundle.writestr("README.txt", "Diagnostics bundle for %s/%s in namespace %s. Generated by Kubernetes Operations Dashboard.\n" % (kind, name, namespace))
                    bundle.writestr("workload.json", json.dumps(workload, indent=2, sort_keys=True))
                    bundle.writestr("workload-describe.txt", run_kubectl(["describe", kind, name, "-n", namespace]))
                    bundle.writestr("workload-events.json", json.dumps(events, indent=2, sort_keys=True))
                    for pod in pods:
                        pod_name = pod.get("metadata", {}).get("name")
                        if not pod_name:
                            continue
                        prefix = "pods/%s/" % pod_name
                        bundle.writestr(prefix + "pod.json", json.dumps(pod, indent=2, sort_keys=True))
                        bundle.writestr(prefix + "describe.txt", run_kubectl(["describe", "pod", pod_name, "-n", namespace]))
                        pod_events = json.loads(run_kubectl(["get", "events", "-n", namespace, "--field-selector=involvedObject.name=" + pod_name, "--sort-by=.lastTimestamp", "-o", "json"]))
                        bundle.writestr(prefix + "events.json", json.dumps(pod_events, indent=2, sort_keys=True))
                        try:
                            bundle.writestr(prefix + "logs-all-containers.txt", run_kubectl(["logs", pod_name, "-n", namespace, "--all-containers=true", "--tail=500"]))
                        except RuntimeError as err:
                            bundle.writestr(prefix + "logs-error.txt", str(err))
                filename = "%s-%s-%s-diagnostics.zip" % (namespace, kind, name)
                self.binary(archive.getvalue(), filename, "application/zip")
            elif parsed.path == "/api/node-detail":
                namespace, node = value(params, "namespace"), value(params, "node")
                node_doc = json.loads(run_kubectl(["get", "node", node, "-o", "json"]))
                pods = json.loads(run_kubectl(["get", "pods", "-n", namespace, "--field-selector=spec.nodeName=" + node, "-o", "json"]))
                self.json({"node": node_doc, "pods": pods.get("items", [])})
            elif parsed.path == "/api/namespace-health":
                namespace = value(params, "namespace")
                self.json({
                    "quotas": json.loads(run_kubectl(["get", "resourcequota", "-n", namespace, "-o", "json"])),
                    "limitRanges": json.loads(run_kubectl(["get", "limitrange", "-n", namespace, "-o", "json"])),
                    "hpas": json.loads(run_kubectl(["get", "hpa", "-n", namespace, "-o", "json"])),
                    "cronjobs": json.loads(run_kubectl(["get", "cronjob", "-n", namespace, "-o", "json"]))
                })
            elif parsed.path == "/api/storage-network":
                namespace = value(params, "namespace")
                self.json({
                    "pvcs": json.loads(run_kubectl(["get", "pvc", "-n", namespace, "-o", "json"])),
                    "services": json.loads(run_kubectl(["get", "service", "-n", namespace, "-o", "json"])),
                    "ingresses": json.loads(run_kubectl(["get", "ingress", "-n", namespace, "-o", "json"])),
                    "endpointSlices": json.loads(run_kubectl(["get", "endpointslice", "-n", namespace, "-o", "json"]))
                })
            elif parsed.path == "/api/resources":
                namespace = value(params, "namespace")
                self.json({
                    "hpas": json.loads(run_kubectl(["get", "hpa", "-n", namespace, "-o", "json"])),
                    "services": json.loads(run_kubectl(["get", "service", "-n", namespace, "-o", "json"])),
                    "ingresses": json.loads(run_kubectl(["get", "ingress", "-n", namespace, "-o", "json"])),
                    "endpointSlices": json.loads(run_kubectl(["get", "endpointslice", "-n", namespace, "-o", "json"])),
                    "pvcs": json.loads(run_kubectl(["get", "pvc", "-n", namespace, "-o", "json"])),
                    "quotas": json.loads(run_kubectl(["get", "resourcequota", "-n", namespace, "-o", "json"])),
                    "limitRanges": json.loads(run_kubectl(["get", "limitrange", "-n", namespace, "-o", "json"])),
                    "jobs": json.loads(run_kubectl(["get", "job", "-n", namespace, "-o", "json"])),
                    "cronjobs": json.loads(run_kubectl(["get", "cronjob", "-n", namespace, "-o", "json"]))
                })
            elif parsed.path == "/api/capacity":
                namespace = value(params, "namespace")
                pods = json.loads(run_kubectl(["get", "pods", "-n", namespace, "-o", "json"])).get("items", [])
                limit_ranges = json.loads(run_kubectl(["get", "limitrange", "-n", namespace, "-o", "json"])).get("items", [])
                workloads = json.loads(run_kubectl(["get", "deployments,statefulsets,daemonsets", "-n", namespace, "-o", "json"])).get("items", [])
                metrics, metrics_available = top_container_rows(namespace)
                defaults, default_requests = {}, {}
                for limit_range in limit_ranges:
                    for rule in limit_range.get("spec", {}).get("limits", []) or []:
                        if rule.get("type") == "Container":
                            defaults.update(rule.get("default", {}) or {})
                            default_requests.update(rule.get("defaultRequest", {}) or {})
                items = []
                for pod in pods:
                    pod_name = pod.get("metadata", {}).get("name", "")
                    labels = pod.get("metadata", {}).get("labels", {})
                    workload = next((item for item in workloads if labels_match(item.get("spec", {}).get("selector", {}).get("matchLabels", {}), labels)), None)
                    workload_status = workload.get("status", {}) if workload else {}
                    workload_spec = workload.get("spec", {}) if workload else {}
                    desired_replicas = workload_spec.get("replicas", workload_status.get("desiredNumberScheduled"))
                    ready_replicas = workload_status.get("readyReplicas", workload_status.get("numberReady"))
                    replica_state = (str(ready_replicas if ready_replicas is not None else 0) + "/" + str(desired_replicas)) if workload else "—"
                    owner = next((entry for entry in pod.get("metadata", {}).get("ownerReferences", []) if entry.get("controller")), {})
                    workload_name = workload.get("metadata", {}).get("name") if workload else owner.get("name", "—")
                    workload_kind = workload.get("kind") if workload else owner.get("kind", "—")
                    statuses = {entry.get("name"): entry for entry in pod.get("status", {}).get("containerStatuses", [])}
                    groups = (("App", pod.get("spec", {}).get("containers", [])), ("Init", pod.get("spec", {}).get("initContainers", [])))
                    for container_type, containers in groups:
                        for container in containers:
                            container_name = container.get("name", "")
                            resources = container.get("resources", {}) or {}
                            requests, limits = resources.get("requests", {}) or {}, resources.get("limits", {}) or {}
                            cpu_request = requests.get("cpu", default_requests.get("cpu", "—"))
                            memory_request = requests.get("memory", default_requests.get("memory", "—"))
                            cpu_limit = limits.get("cpu", defaults.get("cpu", "—"))
                            memory_limit = limits.get("memory", defaults.get("memory", "—"))
                            usage, status = metrics.get((pod_name, container_name), {}), statuses.get(container_name, {})
                            items.append({
                                "pod": pod_name, "container": container_name, "containerType": container_type,
                                "phase": pod.get("status", {}).get("phase", "Unknown"),
                                "replicas": replica_state,
                                "workload": (str(workload_kind) + "/" + str(workload_name)) if workload_name != "—" else "—",
                                "cpuRequest": cpu_request, "memoryRequest": memory_request,
                                "cpuLimit": cpu_limit, "memoryLimit": memory_limit,
                                "cpuRequestDefaulted": "cpu" not in requests and "cpu" in default_requests,
                                "memoryRequestDefaulted": "memory" not in requests and "memory" in default_requests,
                                "cpuLimitDefaulted": "cpu" not in limits and "cpu" in defaults,
                                "memoryLimitDefaulted": "memory" not in limits and "memory" in defaults,
                                "cpuUsage": usage.get("cpu", "—"), "memoryUsage": usage.get("memory", "—"),
                                "restarts": status.get("restartCount", 0)
                            })
                self.json({"namespace": namespace, "metricsAvailable": metrics_available, "items": items})
            elif parsed.path == "/api/logs":
                namespace, pod = value(params, "namespace"), value(params, "pod")
                container = value(params, "container", False)
                previous = params.get("previous", ["false"])[0] == "true"
                since = params.get("since", ["15m"])[0]
                if since not in {"5m", "15m", "1h", "6h", "24h", "all"}:
                    raise ValueError("Invalid log time range")
                args = ["logs", pod, "-n", namespace, "--tail=500"]
                if container: args.extend(["-c", container])
                if previous: args.append("--previous")
                if since != "all": args.append("--since=" + since)
                output = run_kubectl(args)
                archive = HISTORY.save_viewed_logs(namespace, pod, container, output, previous, since)
                self.json({"logs": output, "archive": archive})
            elif parsed.path == "/api/events":
                namespace = value(params, "namespace")
                self.json(json.loads(run_kubectl(["get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "-o", "json"])))
            elif parsed.path == "/api/pod-metrics":
                namespace = value(params, "namespace")
                self.json({"items": top_rows(["top", "pod", "-n", namespace, "--no-headers"], ["name", "cpu", "memory"])})
            else:
                self.api_error("Not found", 404)
        except (ValueError, RuntimeError, json.JSONDecodeError) as err:
            self.api_error(err)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            try:
                size = int(self.headers.get("Content-Length", "0")); data = json.loads(self.rfile.read(size))
                record = users().get(str(data.get("username", "")))
                supplied = str(data.get("password", ""))
                valid = record and (password_valid(supplied, record.get("passwordHash", "")) or hmac.compare_digest(supplied, str(record.get("password", ""))))
                if not valid:
                    return self.api_error("Invalid username or password", 401)
                expires = str(int(time.time() + 28800)); role = record.get("role", "read")
                token = "%s|%s|%s|%s" % (record["username"], role, expires, sign_session(record["username"], role, expires))
                return self.json({"username": record["username"], "role": role}, cookie="kubernetes_operations_dashboard=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800" % token)
            except (ValueError, json.JSONDecodeError):
                return self.api_error("Invalid login request", 400)
        if parsed.path == "/api/logout":
            return self.json({"ok": True}, cookie="kubernetes_operations_dashboard=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        if parsed.path not in {"/api/restart", "/api/restart-pod", "/api/scale", "/api/cronjob-suspend", "/api/cronjob-edit", "/api/hpa-edit"}:
            return self.api_error("Not found", 404)
        if not self.require(write=True):
            return self.api_error("Write permission required", 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            namespace = value({"namespace": [str(payload.get("namespace", ""))]}, "namespace")
            kind = value({"kind": [str(payload.get("kind", ""))]}, "kind")
            name = value({"name": [str(payload.get("name", ""))]}, "name")
            confirmation = str(payload.get("confirmation", ""))
            if parsed.path == "/api/restart-pod":
                if confirmation != "RESTART":
                    raise ValueError("Type RESTART to confirm")
                pod_doc = json.loads(run_kubectl(["get", "pod", name, "-n", namespace, "-o", "json"]))
                owners = pod_doc.get("metadata", {}).get("ownerReferences", [])
                controller = next((o for o in owners if o.get("controller")), None)
                if not controller or controller.get("kind") not in {"ReplicaSet", "StatefulSet", "DaemonSet", "Job"}:
                    raise ValueError("This pod is not controller-managed; restart is not allowed")
                output = run_kubectl(["delete", "pod", name, "-n", namespace])
                self.json({"message": output.strip() + "; Kubernetes will recreate it", "resource": "pod/" + name})
                return
            if parsed.path == "/api/scale":
                if not SCALE_ENABLED:
                    raise ValueError("Replica scaling is disabled by the Helm actions.scale.enabled setting")
                if kind not in {"deployment", "statefulset"}:
                    raise ValueError("Only Deployments and StatefulSets can be scaled")
                replicas = int(payload.get("replicas", -1))
                if replicas < 0 or replicas > 100:
                    raise ValueError("Replicas must be between 0 and 100")
                if confirmation != "SCALE":
                    raise ValueError("Type SCALE to confirm")
                output = run_kubectl(["scale", kind + "/" + name, "-n", namespace, "--replicas=" + str(replicas)])
                self.json({"message": output.strip(), "resource": kind + "/" + name})
                return
            if parsed.path == "/api/cronjob-suspend":
                if not CRONJOB_SUSPEND_ENABLED:
                    raise ValueError("CronJob suspend/resume is disabled by the Helm actions.cronJobSuspend.enabled setting")
                if kind != "cronjob":
                    raise ValueError("Unsupported resource kind")
                suspend = bool(payload.get("suspend", True))
                expected = "SUSPEND" if suspend else "RESUME"
                if confirmation != expected:
                    raise ValueError("Type %s to confirm" % expected)
                patch = json.dumps({"spec": {"suspend": suspend}})
                output = run_kubectl(["patch", "cronjob", name, "-n", namespace, "--type=merge", "-p", patch])
                self.json({"message": output.strip(), "resource": "cronjob/" + name})
                return
            if parsed.path == "/api/cronjob-edit":
                if not CRONJOB_EDIT_ENABLED:
                    raise ValueError("CronJob editing is disabled by the Helm actions.cronJobEdit.enabled setting")
                if kind != "cronjob":
                    raise ValueError("Unsupported resource kind")
                if confirmation != "UPDATE SCHEDULE":
                    raise ValueError("Type UPDATE SCHEDULE to confirm")
                patch = json.dumps({"spec": {"schedule": cron_schedule(payload.get("schedule"))}})
                output = run_kubectl(["patch", "cronjob", name, "-n", namespace, "--type=merge", "-p", patch])
                self.json({"message": output.strip(), "resource": "cronjob/" + name})
                return
            if parsed.path == "/api/hpa-edit":
                if not HPA_EDIT_ENABLED:
                    raise ValueError("HPA editing is disabled by the Helm actions.hpaEdit.enabled setting")
                if kind != "hpa":
                    raise ValueError("Unsupported resource kind")
                minimum, maximum = int(payload.get("minReplicas", -1)), int(payload.get("maxReplicas", -1))
                if minimum < 1 or maximum < minimum or maximum > 100:
                    raise ValueError("HPA replicas must be between 1 and 100, with maximum not less than minimum")
                if confirmation != "UPDATE HPA":
                    raise ValueError("Type UPDATE HPA to confirm")
                patch = json.dumps({"spec": {"minReplicas": minimum, "maxReplicas": maximum}})
                output = run_kubectl(["patch", "hpa", name, "-n", namespace, "--type=merge", "-p", patch])
                self.json({"message": output.strip(), "resource": "hpa/" + name})
                return
            resource = f"{kind}/{name}"
            if kind not in {"deployment", "statefulset", "daemonset"}:
                raise ValueError("Unsupported workload kind")
            if confirmation != "RESTART":
                raise ValueError("Type RESTART to confirm")
            output = run_kubectl(["rollout", "restart", resource, "-n", namespace])
            self.json({"message": output.strip(), "resource": resource})
        except (ValueError, RuntimeError, json.JSONDecodeError) as err:
            self.api_error(err)

if __name__ == "__main__":
    HISTORY.start()
    print(f"Kubernetes Operations Dashboard: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
