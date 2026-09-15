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
