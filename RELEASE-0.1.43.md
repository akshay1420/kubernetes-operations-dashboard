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
