# Changelog

Historical release notes; use README.md and chart/README.md for current deployment instructions.

# 0.1.57 — Clickable worker node describe

Click a worker node card, or focus it and press Enter/Space, to open its Kubernetes
describe output. Available to authenticated read and write users. Node data is
cluster-scoped. If supplementary Pod/event reads are denied, readable Node JSON is
shown with an explicit warning. No additional Kubernetes permissions are granted.

# 0.1.56 — Workspace header clarification

- Removes the global `R refresh · / search` shortcut pill because search is not available
  consistently across all dashboard views.
- Keeps the selected namespace indicator as the only workspace metadata chip.
- Includes the v4 visual system and the ReplicaSet RBAC compatibility fix.

No API, RBAC, PVC history or recommendation behavior changed.

# 0.1.55 — Operations workspace visual system

This release applies selected Tech/SaaS and dashboard UX principles from UI UX Pro Max
without converting the product into a marketing interface or changing its security model.

- Adds a persistent workspace context bar showing the active view and namespace.
- Introduces consistent color, spacing, border, surface, typography and focus tokens.
- Improves selected tab and namespace states, header status chips and page hierarchy.
- Adds accessible scroll regions, sticky headers and consistent density for live data tables.
- Refines operational status badges, warning surfaces, summary cards, dialogs and filters.
- Adds useful loading treatments and stronger empty-state presentation.
- Improves layouts at desktop, tablet and mobile widths and respects reduced-motion settings.

The 0.1.54 ReplicaSet RBAC correction is included. APIs, action authorization, retained
history, PVC formats and capacity recommendations are unchanged. No migration is required.

# 0.1.54 — Application context RBAC fix

- Restores Context and View application for existing installations by treating the
  ReplicaSet topology layer as optional when the ServiceAccount cannot list ReplicaSets.
- Adds the required read-only `get` and `list` ReplicaSet permissions to the Helm chart.
- Makes the Applications landing page visibly operational with health totals, attention and
  recent-change counts, status badges, changed-row highlighting and application search.
- Keeps the dashboard user model unchanged: both `read`/viewer and `write`/admin users can
  inspect Context, Applications, Recent changes, History and the read-only resource browser.
  Restart, scale, CronJob and HPA mutations continue to require the write role and their
  corresponding feature flags.
- Dynamic resources remain limited by the dashboard ServiceAccount's Kubernetes RBAC;
  Secrets remain excluded from discovery and cannot be opened.

No PVC migration is required.

# 0.1.53 — Live operations foundation

This release adopts selected interaction ideas from modern desktop Kubernetes clients
while preserving the dashboard's in-cluster, namespace-RBAC security model.

- Near-live namespace change detection checks Kubernetes resourceVersions every 15 seconds
  and refreshes the active view when state changes. It does not grant new permissions.
- Application topology adds the Deployment-to-ReplicaSet layer and highlights mapped
  resources that have retained changes during the last 24 hours.
- Saved logs can be opened from an application and include retained logs from its current
  and replacement Pods, while keeping the existing Pod-level log workflow unchanged.
- Resources adds a dynamically discovered, read-only namespaced resource browser. Secrets
  are excluded. A resource opens only when the dashboard ServiceAccount can list it.
- Namespace, history period, change period/source and discovered resource selection are
  remembered locally in the operator's browser. Credentials and cluster data are not stored.
- Optional rbac.extraReadRules lets an environment explicitly grant get/list for selected
  CRDs; the default remains empty and no wildcard access is added.

This is not a terminal, YAML editor or arbitrary mutation surface. Existing history,
recommendations, PVC data and action controls are unchanged. No PVC migration is required.

# 0.1.52 — Consolidated resource changes

Repeated snapshot changes for the same observed resource are consolidated into one
entry within the selected time range. The entry reports the number of observations,
the first and latest observation times, and the latest before/after difference. This
reduces noise from operator-managed resources that are repeatedly recreated or reconciled.

Dashboard actions remain separate audit entries and are never merged. Selecting a
different time range recalculates the consolidation from records in that range. The
underlying JSONL history is retained unchanged, so no evidence is deleted and no PVC
migration is required.

Build and push image 0.1.52, then upgrade with the included chart and existing private
prod-values.yaml. RBAC and history collection settings are unchanged.

# 0.1.51 — Cleaner change access and time filtering

The namespace change action is now labelled Recent changes and aligned with the
Applications heading instead of appearing as a detached namespace button.

Change history supports Last 24 hours, Last 48 hours, Last 7 days, Last 30 days,
and an exact local From/To date-time range. Custom ranges are validated by the
server and must be ordered, not in the future, and within configured retention.
The active interval is displayed after loading. All filters remain scoped to the
namespace selected in the dashboard.

No history/PVC migration or RBAC change is required. Build and push image 0.1.51,
then upgrade with the included chart and the existing private values file.

# 0.1.50 — Namespace clarity and highlighted changes

The Applications history button and heading now explicitly name the selected namespace.
History responses and individual change records include the namespace inferred from the
namespace-specific archive, including older records. No cross-namespace history query
is introduced. Expanded records highlight changed fields with before/after values and
display a changed-field count. These reflect collected snapshots, not instant alerts.

Namespace changes clear old namespaced views, reload active Resources/Capacity views,
close old-resource dialogs and reject late namespace API responses. Refresh preserves
the selected namespace. Nodes and node utilization remain cluster-wide by design.

Existing history files, PVCs, permissions and recommendations are unchanged. Build/push
image 0.1.50 and upgrade using this chart and your private prod-values.yaml.

# 0.1.49 — Application-centred change history

Applications now provides All namespace changes. View application provides topology,
existing rollout details and Recent changes for the workload and currently related
Pods, Services, Ingresses, HPAs and referenced PVCs. The separate Changes navigation
tab is removed. Historical records and resource recommendations are unchanged.

The application list includes Deployments, StatefulSets, DaemonSets, CronJobs and,
when history.weblogicEnabled is true, WebLogic Domains. Domain Pods are matched by
owner UID; CronJob Pods are matched through owned Jobs. Domain/CronJob views do not
show misleading Deployment rollout counters or offer the unsupported diagnostics ZIP.
Existing standard-workload diagnostics remain available.

Application history uses exact resource identifiers, filtered before the history
result cap. It is not a historical topology reconstruction: removed relationships
and deleted applications remain accessible through All namespace changes. Namespace
policies and quotas remain in that namespace-wide view. Snapshot collection timing,
RBAC and storage limits are unchanged. There is no retrospective backfill.

Build and push image 0.1.49, then use this chart with your existing private values.
Keep history.weblogicEnabled: true for WebLogic. No PVC migration is required.

# 0.1.48 — Expanded namespace change tracking

Adds configuration snapshots for Pods, Services, Ingresses, PVCs, ResourceQuotas,
LimitRanges and NetworkPolicies. Creation/removal and selected spec differences are
recorded after each resource type has established a baseline. Runtime status changes
are not configuration changes. Existing workload/HPA/CronJob and dashboard action
tracking continues unchanged.

## WebLogic

Add to the existing history section in your private prod-values.yaml:

```yaml
history:
  weblogicEnabled: true
```

Keep enabled, namespaces, storage and retention settings already present. The chart adds
get/list permissions on weblogic.oracle Domains/Clusters using existing namespace bindings.
WebLogic tracking covers images, serverStartPolicy, replicas, restart/introspection versions,
serverPod resource settings and auxiliary-image names at Domain, cluster and server scopes.
Domain v8 inline clusters and newer standalone Cluster resources are supported. Missing
standalone Cluster resources on old operators are skipped. Forbidden responses remain errors.

Field reference: https://oracle.github.io/weblogic-kubernetes-operator/managing-domains/domain-resource/

No Secret, ConfigMap content, environment-variable values, arbitrary custom resources or
cluster-wide configuration is captured. This is selected namespace configuration history,
not a complete Kubernetes audit log. Exact times and external actors still require audit logs.
Each newly covered resource type starts a baseline after upgrade; old changes are not recovered.
Existing baselines and PVC history remain intact. Failed resource reads do not generate deletions.

The maxBytes Helm value now passes through as a quoted string without int64 conversion.
Keep maxBytes quoted in private values. The history budget still applies to the shared archive;
ensure sufficient capacity. This release does not split log/metrics/change storage budgets.

Build/push image 0.1.48 and upgrade using the included chart with your private values.
Check read access with kubectl auth can-i list domains.weblogic.oracle using the dashboard
ServiceAccount identity. Wait for one full collection cycle for a Domain baseline; later
image or supported configuration changes will appear as first observed.

# 0.1.46 — Changes tab

## Included

- Period and source filters, resource/user search, and before/after configuration views.
- Periodic observation of Deployment, StatefulSet and DaemonSet images, replicas,
  container requests/limits, and rollout restart annotations.
- HPA minimum/maximum replica ranges and target; CronJob schedule, suspension,
  time zone, concurrency policy and container configuration.
- Dashboard restart, Pod restart, scale, HPA and CronJob actions: authenticated
  dashboard username, attempted/succeeded/failed-or-unknown status, before/after
  snapshots where retrievable. These snapshots contain selected fields only.

## Enable and deploy

Uses the existing history.enabled, history.namespaces, intervalSeconds, retentionDays
and PVC. No new RBAC verbs are required. With history disabled, existing actions
continue without persistent action records. Build/push image 0.1.46 and upgrade
with the included chart and your private values; reuse the existing PVC.

The first successful read establishes a baseline. Later reads compare against the
persisted baseline, including after dashboard restarts. Snapshot timestamps mean
first observed, not exact change time. Changes between polls can be missed. An actor
is unknown for observed changes; external attribution requires Kubernetes audit logs.
An automated controller can make the observed change. Dashboard and observed entries
can describe the same operation; they are not automatically causally linked.

## Action history behavior

For configured namespaces, the attempt must be saved before executing an action.
If this write fails (for example, full history budget), the action is not executed.
If execution succeeds but the final write fails, the response warns that only the
attempt was retained. An attempted entry can mean the process stopped before recording
an outcome. A failed/unknown command can have an uncertain server-side outcome.
Succeeded means kubectl succeeded, not that the subsequent rollout is healthy.
Validation/authentication rejections before execution are not recorded. Local mode
has no authenticated actor. This is operational history, not a tamper-proof audit trail.

Configuration collection uses the existing namespace service account permissions and
does not store Secrets, environment values or arbitrary resource specifications.
Baseline files use a separate small JSON file per configured namespace. Existing
metrics, recommendations and logs are unchanged. Results show at most 500 records.

# 0.1.44 — One log window

The Pod Logs window now offers Current logs and Saved logs (PVC).
Current logs retain the existing range, container, previous-container and download controls,
and still save fetched responses to the PVC. Saved logs read the same archive with a
24-hour, 7-day or 30-day period, exact Pod name, container filter, text search and download.

History & insights displays resource recommendations only. Open saved logs opens the
same log window for the selected namespace, including records for deleted Pods.
Blank Pod name means all saved Pods. Storage and RBAC configuration are unchanged.
Archive snapshots can overlap; this is not a continuous lossless log stream.

Build and push image 0.1.44, then upgrade with your private values and image.tag=0.1.44.
Existing PVC records are reused; no migration or deletion is performed.

# 0.1.43 — Save the Pod Logs view to PVC

Every successful Pod Logs request (including reload, range selection and previous-container
logs) archives the exact returned text in the same JSONL log store read by History & insights.
The modal reports whether saving succeeded and includes View saved logs, which opens
30-day history filtered to that Pod. Empty responses are not archived. Browser text search
does not change the saved response. Repeated requests may produce overlapping snapshots.

Private Helm values must include:

```yaml
replicaCount: 1
history:
  enabled: true
  logsEnabled: true
  retentionDays: 30
  namespaces: [your-namespace]
  storageClassName: your-storage-class
  size: 5Gi
  maxBytes: "1073741824"
```

Keep namespace RBAC as configured. Build/push 0.1.43 and upgrade using these private values.
The existing claim and its records remain in use. Application requests and the collector
serialize writes through a shared lock. When the storage budget is full, new writes report
failure instead of deleting unexpired records. Increase the budget/PVC capacity as needed.
Expiry is daily-file based, so records may remain for roughly one extra day.

This archives what the Logs button fetched: currently the last 500 lines in the selected
range, not every log ever produced. Background periodic captures continue independently.
Kubernetes fetch failures return no new logs to save. No historical data can be recovered
from before capture began. Saved application text may contain sensitive data; the existing
dashboard access controls apply.


