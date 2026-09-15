# History and experience preview — 0.1.40

## Enable

Build and publish the image using your existing registry workflow with tag 0.1.40.
Merge these values into your private deployment values, replacing the placeholders:

```yaml
replicaCount: 1
history:
  enabled: true
  namespaces: [your-application-namespace]
  intervalSeconds: 300
  retentionDays: 30
  maxBytes: 1073741824
  logsEnabled: true
  storageClassName: your-storage-class
  size: 5Gi
rbac:
  allowedNamespaces: [your-application-namespace]
```

The existing ServiceAccount must have read access in every collected namespace.
History uses a single writer and Recreate upgrades; this introduces upgrade downtime.
An existing writable claim can be supplied using history.existingClaim. The chart-created
PVC is kept after uninstall. Storage is outside the web root and is not served as static files.
All authenticated dashboard users share the existing ServiceAccount namespace visibility;
this feature does not introduce per-user namespace authorization.

## Storage and collection

One UTC-dated JSONL file per namespace and record type is written on the PVC.
Resource samples contain main-container CPU (millicores), memory (MiB), actual Pod
requests/limits, restart counts and the last termination reason. Init-container usage,
JVM internal metrics and CPU throttling are not collected. Application grouping uses
app.kubernetes.io/name, then controller name, then Pod name; ReplicaSet-owned groups
may split on rollout. Group values are per-container observations, not namespace totals.

Optional stdout/stderr log snapshots collect the previous interval, capped at 256 KiB
per container per cycle. These are best-effort snapshots, not full lossless retention:
deleted Pods, rotations, prior containers, collection delays and high-volume output can
cause gaps; overlap can produce duplicate lines. File-only logs are not captured.
Use a continuous logging collector and backend when complete archival is required.
Logs can contain sensitive application content. Enable only for intended namespaces.

Files older than retention are removed. Since 0.1.43, reaching maxBytes blocks new writes
with an explicit error instead of deleting unexpired records. Increase storage if needed.
The Pod Logs button also archives its exact response; see RELEASE-0.1.43.md. Query results are bounded; narrow searches
when capped. Errors are visible in the History view and collection retries next cycle.

## Suggestions

OOM evidence prompts JVM/native-memory and log investigation; it does not diagnose
the cause. A memory-limit candidate uses observed peak plus 30% headroom only after
seven observed days. This heuristic is not automatic rightsizing: assess missing samples,
traffic cycles, replica differences and version changes. Data starts at installation.
CSV export contains the displayed results and suggestions. No cluster mutation occurs.

## UI references

Original CSS adapts visual ideas from https://github.com/unovue/inspira-ui and
https://github.com/imskyleen/animate-ui: calmer cards, clearer hierarchy, focus states
and short transitions with reduced-motion support. No source components were copied.
https://github.com/darkroomengineering/lenis was reviewed; native table scrolling is retained.
https://github.com/github/spec-kit informed the explicit scope and acceptance checks;
it is a development toolkit, not a runtime UI dependency.

## Acceptance checks

- Existing views still load; new JavaScript passes syntax validation.
- Missing measurements remain null, never zero.
- Unknown namespace and traversal attempts cannot query stored data.
- Retention and capacity prune only collector JSONL files.
- History cannot run with two replicas via this chart.
- Validate actual PVC provisioning, metrics access and collector errors in your cluster.
